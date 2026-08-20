"""Calibration-only fit and uncertainty gates for successor admission studies.

This module is outside the completed Stage 3 execution boundary. It consumes
only the verified calibration partition of an empirical campaign package. A
successful gate is engineering evidence; it never authorizes a scientific run,
or claims external validation. Source-package verification checks held-out
integrity, but held-out values are not exposed to the estimator.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import io
import json
import math
import os
import platform
import shutil
import stat
import tempfile
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, NoReturn

import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear
from scipy.spatial import ConvexHull, QhullError

from fleet_sim.calibration.measurements import OPTIONAL_COLUMNS, REQUIRED_COLUMNS
from fleet_sim.control_plane.resource_network import ResourceType
from fleet_sim.empirical.assurance_campaign import (
    CampaignPackageVerification,
    validate_campaign_manifest,
    verify_empirical_campaign_package,
)

FIT_SCHEMA_VERSION = "1.0"
FIT_MODEL_ID = "duration-weighted-nonnegative-arrival-rate-v1"
MAX_BOOTSTRAP_REPLICATIONS = 10_000
MAX_BOOTSTRAP_WORK_UNITS = 10_000_000
FIT_PACKAGE_FILES = {
    "bootstrap_draws.parquet",
    "calibration_fit.json",
    "calibration_fit_schema.json",
    "calibration_measurements.parquet",
    "calibration_policy.json",
    "calibration_policy_schema.json",
    "fit_evidence_manifest.json",
}
FitState = Literal["passed", "failed", "not_evaluable"]
StudyMode = Literal["interface_verification", "successor_transfer"]
_CALIBRATION_EXTENSION_COLUMNS = (
    "campaign_id",
    "time_block_id",
    "partition",
    "is_censored",
    "missing_fraction",
)


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"nonfinite JSON value is not allowed: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key is not allowed: {key}")
        result[key] = value
    return result


def _read_json_bytes(value: bytes, display_name: str) -> dict[str, Any]:
    try:
        selected = json.loads(
            value.decode("utf-8"),
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON in {display_name}: {exc}") from exc
    if not isinstance(selected, dict):
        raise TypeError(f"{display_name} must contain one JSON object")
    return selected


def _read_json(path: Path) -> dict[str, Any]:
    return _read_json_bytes(path.read_bytes(), path.name)


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_calibration_partition_sha256(frame: pd.DataFrame) -> str:
    """Hash one validated campaign partition without changing intake code."""

    columns = [
        *REQUIRED_COLUMNS,
        *sorted(OPTIONAL_COLUMNS),
        *_CALIBRATION_EXTENSION_COLUMNS,
    ]
    actual_columns = list(frame.columns)
    if len(actual_columns) != len(columns) or set(actual_columns) != set(columns):
        missing = sorted(set(columns).difference(actual_columns))
        extra = sorted(set(actual_columns).difference(columns))
        raise ValueError(
            "calibration partition columns differ from the closed contract: "
            f"missing={missing}, extra={extra}"
        )
    canonical = (
        frame[columns]
        .sort_values(
            ["partition", "time_block_id", "resource_id", "timestamp"],
            kind="mergesort",
        )
        .reset_index(drop=True)
    )
    timestamps = pd.to_datetime(canonical["timestamp"], utc=True, errors="raise")
    canonical["timestamp"] = timestamps.map(lambda value: value.isoformat().replace("+00:00", "Z"))
    canonical["is_censored"] = canonical["is_censored"].astype(np.int8)
    return _sha256_bytes(canonical.to_csv(index=False, lineterminator="\n").encode("utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _exact_keys(value: object, expected: set[str], context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{context} must be an object")
    actual = set(value)
    if actual != expected:
        raise ValueError(
            f"{context} fields differ from the closed contract: "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    return value


def _integer(value: object, context: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise TypeError(f"{context} must be an integer")
    selected = int(value)
    if selected < minimum:
        raise ValueError(f"{context} must be at least {minimum}")
    return selected


def _finite(value: object, context: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise TypeError(f"{context} must be numeric")
    selected = float(value)
    if not math.isfinite(selected):
        raise ValueError(f"{context} must be finite")
    if minimum is not None and selected < minimum:
        raise ValueError(f"{context} must be at least {minimum}")
    return selected


def _probability(value: object, context: str, *, open_lower: bool = False) -> float:
    selected = _finite(value, context)
    lower_valid = selected > 0.0 if open_lower else selected >= 0.0
    if not lower_valid or selected > 1.0:
        bound = "(0, 1]" if open_lower else "[0, 1]"
        raise ValueError(f"{context} must be within {bound}")
    return selected


def _sha256(value: object, context: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{context} must be a lowercase SHA-256 digest")
    if any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{context} must be a lowercase SHA-256 digest")
    return value


@dataclass(frozen=True, slots=True)
class FitGatePolicy:
    """Closed, explicit engineering gate policy for one calibration campaign."""

    policy_id: str
    study_mode: StudyMode
    minimum_calibration_time_blocks: int
    minimum_observations_per_resource: int
    minimum_unique_fleet_sizes: int
    minimum_unique_admission_rates: int
    minimum_zero_admission_blocks: int
    minimum_active_admission_blocks: int
    minimum_unique_joint_predictor_vectors: int
    maximum_scaled_condition_number: float
    maximum_scaled_target_hull_distance: float
    target_fleet_size_min: int
    target_fleet_size_max: int
    target_admission_rate_min_per_s: float
    target_admission_rate_max_per_s: float
    maximum_weighted_normalized_rmse: float
    maximum_absolute_weighted_relative_bias: float
    minimum_weighted_r_squared: float
    maximum_capacity_coefficient_of_variation: float
    maximum_deadline_coefficient_of_variation: float
    bootstrap_replications: int
    bootstrap_block_length: int
    bootstrap_interval_level: float
    minimum_bootstrap_success_fraction: float
    interval_scale_floor: float
    maximum_background_interval_relative_width: float
    maximum_admission_interval_relative_width: float
    maximum_capacity_interval_relative_width: float
    maximum_service_interval_relative_width: float
    maximum_max_wait_interval_relative_width: float
    root_seed: int

    def __post_init__(self) -> None:
        if (
            not self.policy_id
            or len(self.policy_id) > 128
            or not self.policy_id[0].isalnum()
            or any(
                character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
                for character in self.policy_id
            )
        ):
            raise ValueError("policy_id must be a portable identifier")
        if self.study_mode not in {"interface_verification", "successor_transfer"}:
            raise ValueError("study_mode is not supported")
        for field_name, minimum in (
            ("minimum_calibration_time_blocks", 4),
            ("minimum_observations_per_resource", 4),
            ("minimum_unique_fleet_sizes", 2),
            ("minimum_unique_admission_rates", 2),
            ("minimum_zero_admission_blocks", 1),
            ("minimum_active_admission_blocks", 1),
            ("minimum_unique_joint_predictor_vectors", 2),
            ("bootstrap_replications", 100),
            ("bootstrap_block_length", 1),
        ):
            _integer(getattr(self, field_name), field_name, minimum=minimum)
        if self.bootstrap_block_length > self.minimum_calibration_time_blocks:
            raise ValueError("bootstrap_block_length cannot exceed minimum_calibration_time_blocks")
        if self.bootstrap_replications > MAX_BOOTSTRAP_REPLICATIONS:
            raise ValueError(f"bootstrap_replications cannot exceed {MAX_BOOTSTRAP_REPLICATIONS}")
        _integer(self.target_fleet_size_min, "target_fleet_size_min", minimum=1)
        _integer(self.target_fleet_size_max, "target_fleet_size_max", minimum=1)
        if self.target_fleet_size_max <= self.target_fleet_size_min:
            raise ValueError("target fleet-size range must have positive width")
        _integer(self.root_seed, "root_seed")
        if self.root_seed >= 2**63:
            raise ValueError("root_seed must fit a signed 64-bit integer")
        for field_name in (
            "maximum_scaled_condition_number",
            "maximum_scaled_target_hull_distance",
            "maximum_weighted_normalized_rmse",
            "maximum_absolute_weighted_relative_bias",
            "maximum_capacity_coefficient_of_variation",
            "maximum_deadline_coefficient_of_variation",
            "interval_scale_floor",
            "maximum_background_interval_relative_width",
            "maximum_admission_interval_relative_width",
            "maximum_capacity_interval_relative_width",
            "maximum_service_interval_relative_width",
            "maximum_max_wait_interval_relative_width",
        ):
            if _finite(getattr(self, field_name), field_name, minimum=0.0) <= 0.0:
                raise ValueError(f"{field_name} must be positive")
        _finite(
            self.target_admission_rate_min_per_s,
            "target_admission_rate_min_per_s",
            minimum=0.0,
        )
        _finite(
            self.target_admission_rate_max_per_s,
            "target_admission_rate_max_per_s",
            minimum=0.0,
        )
        if self.target_admission_rate_max_per_s <= self.target_admission_rate_min_per_s:
            raise ValueError("target admission-rate range must have positive width")
        r_squared = _finite(self.minimum_weighted_r_squared, "minimum_weighted_r_squared")
        if not -1.0 <= r_squared <= 1.0:
            raise ValueError("minimum_weighted_r_squared must be within [-1, 1]")
        interval = _probability(
            self.bootstrap_interval_level,
            "bootstrap_interval_level",
            open_lower=True,
        )
        if not 0.5 < interval < 1.0:
            raise ValueError("bootstrap_interval_level must be within (0.5, 1)")
        success = _probability(
            self.minimum_bootstrap_success_fraction,
            "minimum_bootstrap_success_fraction",
            open_lower=True,
        )
        if success < 0.5:
            raise ValueError("minimum_bootstrap_success_fraction must be at least 0.5")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> FitGatePolicy:
        expected = set(cls.__dataclass_fields__)
        selected = _exact_keys(value, expected, "fit-gate policy")
        return cls(**dict(selected))  # type: ignore[arg-type]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @property
    def policy_sha256(self) -> str:
        return _sha256_bytes(_canonical_json_bytes(self.to_dict()))


@dataclass(frozen=True, slots=True)
class IntervalEstimate:
    lower: float
    point: float
    upper: float

    def __post_init__(self) -> None:
        values = (self.lower, self.point, self.upper)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("interval values must be finite")
        if self.lower > self.upper:
            raise ValueError("interval bounds must be ordered")

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GateCriterion:
    criterion_id: str
    state: FitState
    observed: float | None
    operator: str
    threshold: float | None
    reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ResourceFitResult:
    resource_id: str
    resource_type: str
    gate_status: FitState
    blocking_reasons: tuple[str, ...]
    observation_count: int
    time_block_count: int
    fleet_size_min: int
    fleet_size_max: int
    admission_rate_min_per_s: float
    admission_rate_max_per_s: float
    arrival_rate_min_per_s: float
    arrival_rate_max_per_s: float
    scaled_design_rank: int
    scaled_design_condition_number: float | None
    weighted_rmse_work_units_per_s: float | None
    weighted_normalized_rmse: float | None
    absolute_weighted_relative_bias: float | None
    weighted_r_squared: float | None
    capacity_coefficient_of_variation: float
    deadline_coefficient_of_variation: float
    bootstrap_requested: int
    bootstrap_succeeded: int
    bootstrap_success_fraction: float
    median_prediction_interval_relative_width: float | None
    background_work_per_agent_s: IntervalEstimate | None
    admission_work_units_per_agent: IntervalEstimate | None
    capacity_units_per_second: IntervalEstimate | None
    service_time_window_mean_ms: IntervalEstimate | None
    service_time_between_window_standard_deviation_ms: IntervalEstimate | None
    max_wait_s: IntervalEstimate | None
    dropped_work_fraction: IntervalEstimate | None
    deferred_work_fraction: IntervalEstimate | None
    measurement_provenance: tuple[str, ...]
    parameter_class: Literal["inferred", "notional"]
    field_evidence_class: tuple[tuple[str, str], ...]
    criteria: tuple[GateCriterion, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["blocking_reasons"] = list(self.blocking_reasons)
        payload["measurement_provenance"] = list(self.measurement_provenance)
        payload["field_evidence_class"] = dict(self.field_evidence_class)
        payload["criteria"] = [criterion.to_dict() for criterion in self.criteria]
        for field_name in (
            "background_work_per_agent_s",
            "admission_work_units_per_agent",
            "capacity_units_per_second",
            "service_time_window_mean_ms",
            "service_time_between_window_standard_deviation_ms",
            "max_wait_s",
            "dropped_work_fraction",
            "deferred_work_fraction",
        ):
            interval = getattr(self, field_name)
            payload[field_name] = None if interval is None else interval.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class CalibrationFitInput:
    """Calibration-only view; held-out values are deliberately unavailable."""

    _calibration: pd.DataFrame
    campaign_id: str
    calibration_content_sha256: str
    calibration_context_sha256: str
    campaign_manifest_sha256: str
    campaign_schema_sha256: str
    measurement_schema_sha256: str
    source_evidence_scope: str
    source_dataset_id: str
    source_evidence_manifest_sha256: str
    heldout_content_commitment_sha256: str
    externally_digest_bound: bool
    _source_package_dir: Path

    @property
    def calibration(self) -> pd.DataFrame:
        return self._calibration.copy(deep=True)


@dataclass(frozen=True, slots=True)
class EmpiricalCalibrationFit:
    schema_version: str
    calibration_fit_id: str
    model_id: str
    model_formula: str
    input_partition: Literal["calibration"]
    source_package_heldout_verified: bool
    heldout_used_for_fit: bool
    calibration_content_sha256: str
    calibration_context_sha256: str
    campaign_schema_sha256: str
    measurement_schema_sha256: str
    source_evidence_scope: str
    policy: FitGatePolicy
    policy_sha256: str
    implementation: tuple[tuple[str, str], ...]
    implementation_sha256: str
    bootstrap_method: str
    gate_status: FitState
    blocking_reasons: tuple[str, ...]
    interface_verification_ready: bool
    eligible_for_adapter: bool
    runner_authorized: bool
    scientific_use_authorized: bool
    external_validation: bool
    global_criteria: tuple[GateCriterion, ...]
    resources: tuple[ResourceFitResult, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "calibration_fit_id": self.calibration_fit_id,
            "model_id": self.model_id,
            "model_formula": self.model_formula,
            "input_partition": self.input_partition,
            "source_package_heldout_verified": self.source_package_heldout_verified,
            "heldout_used_for_fit": self.heldout_used_for_fit,
            "calibration_content_sha256": self.calibration_content_sha256,
            "calibration_context_sha256": self.calibration_context_sha256,
            "campaign_schema_sha256": self.campaign_schema_sha256,
            "measurement_schema_sha256": self.measurement_schema_sha256,
            "source_evidence_scope": self.source_evidence_scope,
            "policy": self.policy.to_dict(),
            "policy_sha256": self.policy_sha256,
            "implementation": [
                {"path": path, "sha256": digest} for path, digest in self.implementation
            ],
            "implementation_sha256": self.implementation_sha256,
            "bootstrap_method": self.bootstrap_method,
            "gate_status": self.gate_status,
            "blocking_reasons": list(self.blocking_reasons),
            "interface_verification_ready": self.interface_verification_ready,
            "eligible_for_adapter": self.eligible_for_adapter,
            "runner_authorized": self.runner_authorized,
            "scientific_use_authorized": self.scientific_use_authorized,
            "external_validation": self.external_validation,
            "global_criteria": [criterion.to_dict() for criterion in self.global_criteria],
            "resource_count": len(self.resources),
            "resources": [resource.to_dict() for resource in self.resources],
        }


@dataclass(frozen=True, slots=True)
class EmpiricalCalibrationPackageVerification:
    package_dir: Path
    fit: EmpiricalCalibrationFit
    fit_evidence_manifest_sha256: str
    externally_digest_bound: bool
    _bootstrap_draws: pd.DataFrame
    _source_campaign_package_dir: Path

    @property
    def bootstrap_draws(self) -> pd.DataFrame:
        return self._bootstrap_draws.copy(deep=True)


@dataclass(frozen=True, slots=True)
class EmpiricalCalibrationRun:
    fit: EmpiricalCalibrationFit
    _bootstrap_draws: pd.DataFrame

    @property
    def bootstrap_draws(self) -> pd.DataFrame:
        return self._bootstrap_draws.copy(deep=True)


def load_fit_gate_policy(path: str | Path) -> FitGatePolicy:
    """Load a closed fit policy without coercing JSON types."""

    selected = Path(path)
    return FitGatePolicy.from_mapping(
        _read_json_bytes(
            _read_bounded_file(selected, 4 * 1024 * 1024),
            selected.name,
        )
    )


def _evidence_artifact_sha256(evidence: Mapping[str, object], name: str) -> str:
    artifacts = evidence.get("artifacts")
    if not isinstance(artifacts, list):
        raise TypeError("campaign evidence artifact inventory is invalid")
    matches = [item for item in artifacts if isinstance(item, Mapping) and item.get("path") == name]
    if len(matches) != 1:
        raise ValueError(f"campaign evidence is missing the unique {name} artifact")
    return _sha256(matches[0].get("sha256"), f"campaign {name} hash")


def _partition_sha256(evidence: Mapping[str, object], name: str) -> str:
    partitions = evidence.get("partitions")
    if not isinstance(partitions, Mapping):
        raise TypeError("campaign partition evidence is invalid")
    selected = partitions.get(name)
    if not isinstance(selected, Mapping):
        raise TypeError(f"campaign partition evidence is missing {name}")
    return _sha256(selected.get("content_sha256"), f"{name} content hash")


def _calibration_scope(frame: pd.DataFrame) -> str:
    sources = set(frame["source_type"].astype(str))
    if "synthetic" in sources:
        return "synthetic_or_mixed_interface_only"
    if sources == {"measured"}:
        return "measured_input_unreviewed"
    if sources == {"replayed"}:
        return "replayed_input_unreviewed"
    return "mixed_nonsynthetic_input_unreviewed"


def _calibration_context(manifest: Mapping[str, object], frame: pd.DataFrame) -> dict[str, object]:
    return {
        "campaign_id": manifest["campaign_id"],
        "site_alias": manifest["site_alias"],
        "system_alias": manifest["system_alias"],
        "calibration_source_types": sorted(set(frame["source_type"].astype(str))),
        "calibration_evidence_scope": _calibration_scope(frame),
        "collection_start": manifest["collection_start"],
        "authority": deepcopy(manifest["authority"]),
        "instrumentation": deepcopy(manifest["instrumentation"]),
        "units": deepcopy(manifest["units"]),
        "calibration_timestamp_min": frame["timestamp"].min().isoformat().replace("+00:00", "Z"),
        "calibration_timestamp_max": frame["timestamp"].max().isoformat().replace("+00:00", "Z"),
        "calibration_window_end_max": (
            frame["timestamp"] + pd.to_timedelta(frame["window_duration_ms"], unit="ms")
        )
        .max()
        .isoformat()
        .replace("+00:00", "Z"),
    }


def prepare_calibration_fit_input(
    package_dir: str | Path,
    *,
    expected_evidence_manifest_sha256: str,
) -> CalibrationFitInput:
    """Verify a campaign and project it into a calibration-only fit view."""

    expected = _sha256(
        expected_evidence_manifest_sha256,
        "expected campaign evidence manifest hash",
    )
    checked: CampaignPackageVerification = verify_empirical_campaign_package(
        package_dir,
        expected_evidence_manifest_sha256=expected,
    )
    if not checked.externally_digest_bound:
        raise ValueError("calibration fitting requires an externally supplied campaign digest")
    evidence = checked.evidence_manifest
    calibration = checked.calibration
    if set(calibration["partition"]) != {"calibration"}:
        raise ValueError("calibration fit input contains a non-calibration partition")
    campaign_manifest_sha256 = _evidence_artifact_sha256(evidence, "campaign_manifest.json")
    campaign_manifest_bytes = _read_bounded_file(
        checked.package_dir / "campaign_manifest.json", 8 * 1024 * 1024
    )
    if _sha256_bytes(campaign_manifest_bytes) != campaign_manifest_sha256:
        raise ValueError("campaign manifest changed after package verification")
    campaign_manifest = validate_campaign_manifest(
        _read_json_bytes(campaign_manifest_bytes, "campaign_manifest.json")
    )
    context = _calibration_context(campaign_manifest, calibration)
    schemas = evidence.get("schemas")
    if not isinstance(schemas, Mapping):
        raise TypeError("campaign schema evidence is invalid")
    return CalibrationFitInput(
        _calibration=calibration.copy(deep=True),
        campaign_id=str(evidence["campaign_id"]),
        calibration_content_sha256=_partition_sha256(evidence, "calibration"),
        calibration_context_sha256=_sha256_bytes(_canonical_json_bytes(context)),
        campaign_manifest_sha256=campaign_manifest_sha256,
        campaign_schema_sha256=_sha256(
            schemas.get("campaign_schema_sha256"), "campaign schema hash"
        ),
        measurement_schema_sha256=_sha256(
            schemas.get("measurement_schema_sha256"), "measurement schema hash"
        ),
        source_evidence_scope=_calibration_scope(calibration),
        source_dataset_id=checked.dataset_id,
        source_evidence_manifest_sha256=checked.evidence_manifest_sha256,
        heldout_content_commitment_sha256=_partition_sha256(evidence, "heldout"),
        externally_digest_bound=True,
        _source_package_dir=checked.package_dir,
    )


def _criterion(
    criterion_id: str,
    *,
    observed: float | None,
    operator: str,
    threshold: float | None,
    satisfied: bool | None,
    failure_state: FitState,
    reason: str,
) -> GateCriterion:
    if satisfied is not None and bool(satisfied):
        state: FitState = "passed"
        selected_reason = "criterion_satisfied"
    elif satisfied is not None:
        state = failure_state
        selected_reason = reason
    else:
        state = "not_evaluable"
        selected_reason = reason
    return GateCriterion(
        criterion_id=criterion_id,
        state=state,
        observed=observed,
        operator=operator,
        threshold=threshold,
        reason=selected_reason,
    )


def _criteria_state(criteria: tuple[GateCriterion, ...]) -> FitState:
    states = {criterion.state for criterion in criteria}
    if "failed" in states:
        return "failed"
    if "not_evaluable" in states:
        return "not_evaluable"
    return "passed"


def _blocking_reasons(criteria: tuple[GateCriterion, ...]) -> tuple[str, ...]:
    return tuple(
        sorted({criterion.reason for criterion in criteria if criterion.state != "passed"})
    )


def _coefficient_of_variation(values: np.ndarray) -> float:
    mean = float(np.mean(values))
    if mean <= 0.0:
        return math.inf
    return float(np.std(values, ddof=1 if len(values) > 1 else 0) / mean)


def _weighted_service_moments(group: pd.DataFrame) -> tuple[float, float] | None:
    completed = group[group["service_count"] > 0]
    if completed.empty or (completed["service_time_ms"] <= 0.0).any():
        return None
    values = completed["service_time_ms"].to_numpy(float)
    weights = completed["service_count"].to_numpy(float)
    mean = float(np.average(values, weights=weights))
    variance = float(np.average((values - mean) ** 2, weights=weights))
    return mean, math.sqrt(max(0.0, variance))


def _scaled_design_diagnostics(
    design: np.ndarray, duration_s: np.ndarray
) -> tuple[int, float | None]:
    weighted = design * np.sqrt(duration_s)[:, None]
    norms = np.linalg.norm(weighted, axis=0)
    if (norms <= 0.0).any() or not np.isfinite(norms).all():
        return int(np.linalg.matrix_rank(weighted)), None
    scaled = weighted / norms
    rank = int(np.linalg.matrix_rank(scaled))
    if rank < design.shape[1]:
        return rank, None
    condition = float(np.linalg.cond(scaled))
    return rank, condition if math.isfinite(condition) else None


@dataclass(frozen=True, slots=True)
class _PointFit:
    resource_id: str
    resource_type: str
    group: pd.DataFrame
    design: np.ndarray
    arrival_rate: np.ndarray
    duration_s: np.ndarray
    coefficients: np.ndarray | None
    predictions: np.ndarray | None
    rank: int
    condition: float | None
    weighted_rmse: float | None
    normalized_rmse: float | None
    absolute_relative_bias: float | None
    weighted_r_squared: float | None
    capacity_cv: float
    deadline_cv: float
    point_statistics: tuple[float, ...] | None
    criteria: tuple[GateCriterion, ...]


_DRAW_COLUMNS = (
    "background_work_per_agent_s",
    "admission_work_units_per_agent",
    "capacity_units_per_second",
    "service_time_window_mean_ms",
    "service_time_between_window_standard_deviation_ms",
    "max_wait_s",
    "dropped_work_fraction",
    "deferred_work_fraction",
)
_BOOTSTRAP_DRAW_COLUMNS = (
    "bootstrap_replication",
    "sampled_block_sequence_sha256",
    "resource_id",
    "resource_type",
    *_DRAW_COLUMNS,
)


def _empty_bootstrap_draws() -> pd.DataFrame:
    return pd.DataFrame(columns=_BOOTSTRAP_DRAW_COLUMNS)


def _fit_coefficients(
    design: np.ndarray,
    arrival_rate: np.ndarray,
    duration_s: np.ndarray,
) -> tuple[np.ndarray, np.ndarray] | None:
    weighted_design = design * np.sqrt(duration_s)[:, None]
    weighted_response = arrival_rate * np.sqrt(duration_s)
    fit = lsq_linear(weighted_design, weighted_response, bounds=(0.0, np.inf))
    if not fit.success or not np.isfinite(fit.x).all():
        return None
    predictions = design @ fit.x
    if not np.isfinite(predictions).all():
        return None
    return fit.x.astype(float), predictions.astype(float)


def _summary_statistics(group: pd.DataFrame, coefficients: np.ndarray) -> tuple[float, ...] | None:
    service_moments = _weighted_service_moments(group)
    if service_moments is None:
        return None
    service_mean, service_std = service_moments
    arrivals = float(group["arrival_count"].sum())
    return (
        float(coefficients[0]),
        float(coefficients[1]),
        float(np.median(group["capacity_units_per_second"].to_numpy(float))),
        service_mean,
        service_std,
        float(np.median(group["deadline_ms"].to_numpy(float)) / 1000.0),
        float(group["dropped_work"].sum() / max(arrivals, 1.0)),
        float(group["deferred_work"].sum() / max(arrivals, 1.0)),
    )


def _point_fit(group: pd.DataFrame, policy: FitGatePolicy) -> _PointFit:
    ordered = group.sort_values(["timestamp", "time_block_id"], kind="mergesort").reset_index(
        drop=True
    )
    duration_s = ordered["window_duration_ms"].to_numpy(float) / 1000.0
    admission_rate = ordered["agents_admitted"].to_numpy(float) / duration_s
    arrival_rate = ordered["arrival_count"].to_numpy(float) / duration_s
    design = np.column_stack([ordered["fleet_size"].to_numpy(float), admission_rate])
    rank, condition = _scaled_design_diagnostics(design, duration_s)
    capacity_cv = _coefficient_of_variation(ordered["capacity_units_per_second"].to_numpy(float))
    deadline_cv = _coefficient_of_variation(ordered["deadline_ms"].to_numpy(float))
    positive_service_count = int((ordered["service_count"] > 0).sum())
    invalid_completed_service_time = int(
        ((ordered["service_count"] > 0) & (ordered["service_time_ms"] <= 0.0)).sum()
    )
    criteria: list[GateCriterion] = [
        _criterion(
            "minimum_observations",
            observed=len(ordered),
            operator=">=",
            threshold=policy.minimum_observations_per_resource,
            satisfied=len(ordered) >= policy.minimum_observations_per_resource,
            failure_state="not_evaluable",
            reason="insufficient_resource_observations",
        ),
        _criterion(
            "design_rank",
            observed=rank,
            operator="==",
            threshold=2,
            satisfied=rank == 2,
            failure_state="not_evaluable",
            reason="rank_deficient_design",
        ),
        _criterion(
            "scaled_design_condition_number",
            observed=condition,
            operator="<=",
            threshold=policy.maximum_scaled_condition_number,
            satisfied=(
                None if condition is None else condition <= policy.maximum_scaled_condition_number
            ),
            failure_state="not_evaluable",
            reason="design_conditioning_not_acceptable",
        ),
        _criterion(
            "capacity_coefficient_of_variation",
            observed=capacity_cv,
            operator="<=",
            threshold=policy.maximum_capacity_coefficient_of_variation,
            satisfied=(
                math.isfinite(capacity_cv)
                and capacity_cv <= policy.maximum_capacity_coefficient_of_variation
            ),
            failure_state="failed",
            reason="constant_capacity_assumption_not_supported",
        ),
        _criterion(
            "deadline_coefficient_of_variation",
            observed=deadline_cv,
            operator="<=",
            threshold=policy.maximum_deadline_coefficient_of_variation,
            satisfied=(
                math.isfinite(deadline_cv)
                and deadline_cv <= policy.maximum_deadline_coefficient_of_variation
            ),
            failure_state="failed",
            reason="scalar_deadline_assumption_not_supported",
        ),
        _criterion(
            "positive_service_count_support",
            observed=positive_service_count,
            operator=">=",
            threshold=1,
            satisfied=positive_service_count >= 1,
            failure_state="not_evaluable",
            reason="completed_service_support_unavailable",
        ),
        _criterion(
            "positive_service_time_for_completed_work",
            observed=invalid_completed_service_time,
            operator="==",
            threshold=0,
            satisfied=invalid_completed_service_time == 0,
            failure_state="failed",
            reason="completed_work_has_nonpositive_service_time",
        ),
    ]
    if any(item.state == "not_evaluable" for item in criteria):
        return _PointFit(
            resource_id=str(ordered["resource_id"].iloc[0]),
            resource_type=str(ordered["resource_type"].iloc[0]),
            group=ordered,
            design=design,
            arrival_rate=arrival_rate,
            duration_s=duration_s,
            coefficients=None,
            predictions=None,
            rank=rank,
            condition=condition,
            weighted_rmse=None,
            normalized_rmse=None,
            absolute_relative_bias=None,
            weighted_r_squared=None,
            capacity_cv=capacity_cv,
            deadline_cv=deadline_cv,
            point_statistics=None,
            criteria=tuple(criteria),
        )
    solved = _fit_coefficients(design, arrival_rate, duration_s)
    if solved is None:
        criteria.append(
            _criterion(
                "solver_success",
                observed=None,
                operator="is",
                threshold=1,
                satisfied=None,
                failure_state="not_evaluable",
                reason="nonnegative_solver_failed",
            )
        )
        coefficients = None
        predictions = None
        weighted_rmse = None
        normalized_rmse = None
        absolute_relative_bias = None
        weighted_r_squared = None
        point_statistics = None
    else:
        coefficients, predictions = solved
        weight_sum = float(duration_s.sum())
        residuals = predictions - arrival_rate
        weighted_rmse = float(np.sqrt(np.sum(duration_s * residuals**2) / weight_sum))
        response_mean = float(np.sum(duration_s * arrival_rate) / weight_sum)
        normalized_rmse = weighted_rmse / response_mean if response_mean > 0.0 else None
        relative_bias = (
            float(abs(np.sum(duration_s * residuals)) / np.sum(duration_s * arrival_rate))
            if np.sum(duration_s * arrival_rate) > 0.0
            else None
        )
        centered = arrival_rate - response_mean
        total = float(np.sum(duration_s * centered**2))
        weighted_r_squared = (
            1.0 - float(np.sum(duration_s * residuals**2)) / total if total > 0.0 else None
        )
        criteria.extend(
            [
                _criterion(
                    "solver_success",
                    observed=1,
                    operator="is",
                    threshold=1,
                    satisfied=True,
                    failure_state="not_evaluable",
                    reason="nonnegative_solver_failed",
                ),
                _criterion(
                    "weighted_normalized_rmse",
                    observed=normalized_rmse,
                    operator="<=",
                    threshold=policy.maximum_weighted_normalized_rmse,
                    satisfied=(
                        None
                        if normalized_rmse is None
                        else normalized_rmse <= policy.maximum_weighted_normalized_rmse
                    ),
                    failure_state="failed",
                    reason="fit_error_exceeds_policy",
                ),
                _criterion(
                    "absolute_weighted_relative_bias",
                    observed=relative_bias,
                    operator="<=",
                    threshold=policy.maximum_absolute_weighted_relative_bias,
                    satisfied=(
                        None
                        if relative_bias is None
                        else relative_bias <= policy.maximum_absolute_weighted_relative_bias
                    ),
                    failure_state="failed",
                    reason="fit_bias_exceeds_policy",
                ),
                _criterion(
                    "weighted_r_squared",
                    observed=weighted_r_squared,
                    operator=">=",
                    threshold=policy.minimum_weighted_r_squared,
                    satisfied=(
                        None
                        if weighted_r_squared is None
                        else weighted_r_squared >= policy.minimum_weighted_r_squared
                    ),
                    failure_state="failed",
                    reason="fit_explained_variance_below_policy",
                ),
            ]
        )
        absolute_relative_bias = relative_bias
        point_statistics = _summary_statistics(ordered, coefficients)
    return _PointFit(
        resource_id=str(ordered["resource_id"].iloc[0]),
        resource_type=str(ordered["resource_type"].iloc[0]),
        group=ordered,
        design=design,
        arrival_rate=arrival_rate,
        duration_s=duration_s,
        coefficients=coefficients,
        predictions=predictions,
        rank=rank,
        condition=condition,
        weighted_rmse=weighted_rmse,
        normalized_rmse=normalized_rmse,
        absolute_relative_bias=absolute_relative_bias,
        weighted_r_squared=weighted_r_squared,
        capacity_cv=capacity_cv,
        deadline_cv=deadline_cv,
        point_statistics=point_statistics,
        criteria=tuple(criteria),
    )


def _global_criteria(frame: pd.DataFrame, policy: FitGatePolicy) -> tuple[GateCriterion, ...]:
    blocks = (
        frame.sort_values(["timestamp", "time_block_id", "resource_type"], kind="mergesort")
        .drop_duplicates("time_block_id")
        .reset_index(drop=True)
    )
    duration_s = blocks["window_duration_ms"].to_numpy(float) / 1000.0
    admission_rate = blocks["agents_admitted"].to_numpy(float) / duration_s
    fleet_sizes = blocks["fleet_size"].to_numpy(np.int64)
    joint_count = len(set(zip(fleet_sizes.tolist(), admission_rate.tolist(), strict=True)))
    target_minimum = np.asarray(
        [policy.target_fleet_size_min, policy.target_admission_rate_min_per_s],
        dtype=float,
    )
    target_span = np.asarray(
        [
            policy.target_fleet_size_max - policy.target_fleet_size_min,
            (policy.target_admission_rate_max_per_s - policy.target_admission_rate_min_per_s),
        ],
        dtype=float,
    )
    normalized_predictors = (
        np.column_stack([fleet_sizes.astype(float), admission_rate]) - target_minimum
    ) / target_span
    centered_rank = int(np.linalg.matrix_rank(normalized_predictors - normalized_predictors[0]))
    target_hull_distance: float | None = None
    if centered_rank == 2:
        try:
            hull = ConvexHull(normalized_predictors)
        except QhullError:
            hull = None
        if hull is not None:
            target_corners = np.asarray(
                [[0.0, 0.0], [0.0, 1.0], [1.0, 0.0], [1.0, 1.0]],
                dtype=float,
            )
            signed = target_corners @ hull.equations[:, :2].T + hull.equations[:, 2]
            target_hull_distance = float(max(0.0, np.max(signed)))
    censored = int(frame["is_censored"].sum())
    maximum_missing = float(frame["missing_fraction"].max())
    return (
        _criterion(
            "calibration_time_blocks",
            observed=len(blocks),
            operator=">=",
            threshold=policy.minimum_calibration_time_blocks,
            satisfied=len(blocks) >= policy.minimum_calibration_time_blocks,
            failure_state="not_evaluable",
            reason="insufficient_calibration_time_blocks",
        ),
        _criterion(
            "unique_fleet_sizes",
            observed=int(np.unique(fleet_sizes).size),
            operator=">=",
            threshold=policy.minimum_unique_fleet_sizes,
            satisfied=np.unique(fleet_sizes).size >= policy.minimum_unique_fleet_sizes,
            failure_state="not_evaluable",
            reason="insufficient_fleet_size_support",
        ),
        _criterion(
            "unique_admission_rates",
            observed=int(np.unique(admission_rate).size),
            operator=">=",
            threshold=policy.minimum_unique_admission_rates,
            satisfied=np.unique(admission_rate).size >= policy.minimum_unique_admission_rates,
            failure_state="not_evaluable",
            reason="insufficient_admission_rate_support",
        ),
        _criterion(
            "zero_admission_blocks",
            observed=int(np.sum(admission_rate == 0.0)),
            operator=">=",
            threshold=policy.minimum_zero_admission_blocks,
            satisfied=np.sum(admission_rate == 0.0) >= policy.minimum_zero_admission_blocks,
            failure_state="not_evaluable",
            reason="insufficient_zero_admission_baseline_support",
        ),
        _criterion(
            "active_admission_blocks",
            observed=int(np.sum(admission_rate > 0.0)),
            operator=">=",
            threshold=policy.minimum_active_admission_blocks,
            satisfied=np.sum(admission_rate > 0.0) >= policy.minimum_active_admission_blocks,
            failure_state="not_evaluable",
            reason="insufficient_active_admission_support",
        ),
        _criterion(
            "unique_joint_predictor_vectors",
            observed=joint_count,
            operator=">=",
            threshold=policy.minimum_unique_joint_predictor_vectors,
            satisfied=joint_count >= policy.minimum_unique_joint_predictor_vectors,
            failure_state="not_evaluable",
            reason="insufficient_joint_predictor_support",
        ),
        _criterion(
            "joint_target_domain_hull_distance",
            observed=target_hull_distance,
            operator="<=",
            threshold=policy.maximum_scaled_target_hull_distance,
            satisfied=(
                None
                if target_hull_distance is None
                else target_hull_distance <= policy.maximum_scaled_target_hull_distance
            ),
            failure_state="failed",
            reason="joint_target_domain_requires_extrapolation",
        ),
        _criterion(
            "target_fleet_size_min_covered",
            observed=int(fleet_sizes.min()),
            operator="<=",
            threshold=policy.target_fleet_size_min,
            satisfied=int(fleet_sizes.min()) <= policy.target_fleet_size_min,
            failure_state="failed",
            reason="target_fleet_minimum_requires_extrapolation",
        ),
        _criterion(
            "target_fleet_size_max_covered",
            observed=int(fleet_sizes.max()),
            operator=">=",
            threshold=policy.target_fleet_size_max,
            satisfied=int(fleet_sizes.max()) >= policy.target_fleet_size_max,
            failure_state="failed",
            reason="target_fleet_maximum_requires_extrapolation",
        ),
        _criterion(
            "target_admission_rate_min_covered",
            observed=float(admission_rate.min()),
            operator="<=",
            threshold=policy.target_admission_rate_min_per_s,
            satisfied=float(admission_rate.min()) <= policy.target_admission_rate_min_per_s,
            failure_state="failed",
            reason="target_admission_minimum_requires_extrapolation",
        ),
        _criterion(
            "target_admission_rate_max_covered",
            observed=float(admission_rate.max()),
            operator=">=",
            threshold=policy.target_admission_rate_max_per_s,
            satisfied=float(admission_rate.max()) >= policy.target_admission_rate_max_per_s,
            failure_state="failed",
            reason="target_admission_maximum_requires_extrapolation",
        ),
        _criterion(
            "uncensored_complete_case",
            observed=censored,
            operator="==",
            threshold=0,
            satisfied=censored == 0,
            failure_state="failed",
            reason="censored_calibration_rows_not_supported",
        ),
        _criterion(
            "zero_reported_missing_fraction",
            observed=maximum_missing,
            operator="==",
            threshold=0.0,
            satisfied=maximum_missing == 0.0,
            failure_state="failed",
            reason="missing_calibration_values_not_supported",
        ),
    )


def _circular_block_sample(
    block_count: int, block_length: int, rng: np.random.Generator
) -> np.ndarray:
    selected: list[int] = []
    while len(selected) < block_count:
        start = int(rng.integers(0, block_count))
        for offset in range(block_length):
            selected.append((start + offset) % block_count)
            if len(selected) == block_count:
                break
    return np.asarray(selected, dtype=np.int64)


def _joint_bootstrap(
    point_fits: tuple[_PointFit, ...],
    policy: FitGatePolicy,
) -> tuple[pd.DataFrame, int]:
    if any(point.coefficients is None or point.point_statistics is None for point in point_fits):
        return _empty_bootstrap_draws(), 0
    first = point_fits[0].group.sort_values(["timestamp", "time_block_id"], kind="mergesort")
    block_ids = tuple(first["time_block_id"].astype(str))
    if len(set(block_ids)) != len(block_ids):
        raise ValueError("resource calibration contains duplicate time-block rows")
    for point in point_fits:
        ordered_ids = tuple(
            point.group.sort_values(["timestamp", "time_block_id"], kind="mergesort")[
                "time_block_id"
            ].astype(str)
        )
        if ordered_ids != block_ids:
            raise ValueError("resource time-block order differs across the ten-resource vector")
    rng = np.random.default_rng(policy.root_seed)
    rows: list[dict[str, object]] = []
    succeeded = 0
    for replication in range(policy.bootstrap_replications):
        sampled_positions = _circular_block_sample(
            len(block_ids), policy.bootstrap_block_length, rng
        )
        sampled_blocks = tuple(block_ids[index] for index in sampled_positions)
        sample_digest = _sha256_bytes("\n".join(sampled_blocks).encode("utf-8"))
        replication_rows: list[dict[str, object]] = []
        valid = True
        for point in point_fits:
            sampled = point.group.iloc[sampled_positions].reset_index(drop=True)
            duration_s = sampled["window_duration_ms"].to_numpy(float) / 1000.0
            design = np.column_stack(
                [
                    sampled["fleet_size"].to_numpy(float),
                    sampled["agents_admitted"].to_numpy(float) / duration_s,
                ]
            )
            rank, _ = _scaled_design_diagnostics(design, duration_s)
            if rank != 2:
                valid = False
                break
            arrival_rate = sampled["arrival_count"].to_numpy(float) / duration_s
            solved = _fit_coefficients(design, arrival_rate, duration_s)
            if solved is None:
                valid = False
                break
            coefficients, _ = solved
            statistics = _summary_statistics(sampled, coefficients)
            if statistics is None:
                valid = False
                break
            replication_rows.append(
                {
                    "bootstrap_replication": replication,
                    "sampled_block_sequence_sha256": sample_digest,
                    "resource_id": point.resource_id,
                    "resource_type": point.resource_type,
                    **dict(zip(_DRAW_COLUMNS, statistics, strict=True)),
                }
            )
        if valid:
            rows.extend(replication_rows)
            succeeded += 1
    if not rows:
        return _empty_bootstrap_draws(), 0
    frame = (
        pd.DataFrame(rows)
        .sort_values(["bootstrap_replication", "resource_type"], kind="mergesort")
        .reset_index(drop=True)
    )
    return frame, succeeded


def _interval(point: float, draws: np.ndarray, level: float) -> IntervalEstimate:
    alpha = (1.0 - level) / 2.0
    lower, upper = np.quantile(draws, [alpha, 1.0 - alpha], method="linear")
    return IntervalEstimate(lower=float(lower), point=float(point), upper=float(upper))


def _relative_width(interval: IntervalEstimate, scale_floor: float) -> float:
    return float((interval.upper - interval.lower) / max(abs(interval.point), scale_floor))


def _resource_result(
    point: _PointFit,
    bootstrap_draws: pd.DataFrame,
    bootstrap_succeeded: int,
    policy: FitGatePolicy,
) -> ResourceFitResult:
    criteria = list(point.criteria)
    success_fraction = bootstrap_succeeded / policy.bootstrap_replications
    criteria.append(
        _criterion(
            "joint_bootstrap_success_fraction",
            observed=success_fraction,
            operator=">=",
            threshold=policy.minimum_bootstrap_success_fraction,
            satisfied=success_fraction >= policy.minimum_bootstrap_success_fraction,
            failure_state="not_evaluable",
            reason="insufficient_valid_joint_bootstrap_replicates",
        )
    )
    intervals: dict[str, IntervalEstimate | None] = {name: None for name in _DRAW_COLUMNS}
    median_prediction_width: float | None = None
    if point.point_statistics is not None and bootstrap_succeeded > 0 and not bootstrap_draws.empty:
        assert point.predictions is not None
        resource_draws = bootstrap_draws[bootstrap_draws["resource_type"] == point.resource_type]
        for index, name in enumerate(_DRAW_COLUMNS):
            intervals[name] = _interval(
                point.point_statistics[index],
                resource_draws[name].to_numpy(float),
                policy.bootstrap_interval_level,
            )
        beta_draws = resource_draws[
            ["background_work_per_agent_s", "admission_work_units_per_agent"]
        ].to_numpy(float)
        predicted_draws = point.design @ beta_draws.T
        alpha = (1.0 - policy.bootstrap_interval_level) / 2.0
        lower = np.quantile(predicted_draws, alpha, axis=1, method="linear")
        upper = np.quantile(predicted_draws, 1.0 - alpha, axis=1, method="linear")
        denominator = np.maximum(np.abs(point.predictions), policy.interval_scale_floor)
        median_prediction_width = float(np.median((upper - lower) / denominator))

        width_contract = (
            (
                "background_interval_relative_width",
                "background_work_per_agent_s",
                policy.maximum_background_interval_relative_width,
            ),
            (
                "admission_interval_relative_width",
                "admission_work_units_per_agent",
                policy.maximum_admission_interval_relative_width,
            ),
            (
                "capacity_interval_relative_width",
                "capacity_units_per_second",
                policy.maximum_capacity_interval_relative_width,
            ),
            (
                "service_interval_relative_width",
                "service_time_window_mean_ms",
                policy.maximum_service_interval_relative_width,
            ),
            (
                "max_wait_interval_relative_width",
                "max_wait_s",
                policy.maximum_max_wait_interval_relative_width,
            ),
        )
        for criterion_id, name, maximum in width_contract:
            selected = intervals[name]
            assert selected is not None
            width = _relative_width(selected, policy.interval_scale_floor)
            criteria.append(
                _criterion(
                    criterion_id,
                    observed=width,
                    operator="<=",
                    threshold=maximum,
                    satisfied=width <= maximum,
                    failure_state="failed",
                    reason=f"{criterion_id}_exceeds_policy",
                )
            )
        admission = intervals["admission_work_units_per_agent"]
        assert admission is not None
        criteria.append(
            _criterion(
                "admission_lower_interval_positive",
                observed=admission.lower,
                operator=">",
                threshold=0.0,
                satisfied=admission.lower > 0.0,
                failure_state="failed",
                reason="admission_work_interval_touches_zero",
            )
        )
    else:
        for criterion_id in (
            "background_interval_relative_width",
            "admission_interval_relative_width",
            "capacity_interval_relative_width",
            "service_interval_relative_width",
            "max_wait_interval_relative_width",
            "admission_lower_interval_positive",
        ):
            criteria.append(
                _criterion(
                    criterion_id,
                    observed=None,
                    operator="not_evaluable",
                    threshold=None,
                    satisfied=None,
                    failure_state="not_evaluable",
                    reason="bootstrap_interval_not_available",
                )
            )
    criteria_tuple = tuple(criteria)
    status = _criteria_state(criteria_tuple)
    group = point.group
    return ResourceFitResult(
        resource_id=point.resource_id,
        resource_type=point.resource_type,
        gate_status=status,
        blocking_reasons=_blocking_reasons(criteria_tuple),
        observation_count=len(group),
        time_block_count=int(group["time_block_id"].nunique()),
        fleet_size_min=int(group["fleet_size"].min()),
        fleet_size_max=int(group["fleet_size"].max()),
        admission_rate_min_per_s=float(
            (group["agents_admitted"] / (group["window_duration_ms"] / 1000.0)).min()
        ),
        admission_rate_max_per_s=float(
            (group["agents_admitted"] / (group["window_duration_ms"] / 1000.0)).max()
        ),
        arrival_rate_min_per_s=float(
            (group["arrival_count"] / (group["window_duration_ms"] / 1000.0)).min()
        ),
        arrival_rate_max_per_s=float(
            (group["arrival_count"] / (group["window_duration_ms"] / 1000.0)).max()
        ),
        scaled_design_rank=point.rank,
        scaled_design_condition_number=point.condition,
        weighted_rmse_work_units_per_s=point.weighted_rmse,
        weighted_normalized_rmse=point.normalized_rmse,
        absolute_weighted_relative_bias=point.absolute_relative_bias,
        weighted_r_squared=point.weighted_r_squared,
        capacity_coefficient_of_variation=point.capacity_cv,
        deadline_coefficient_of_variation=point.deadline_cv,
        bootstrap_requested=policy.bootstrap_replications,
        bootstrap_succeeded=bootstrap_succeeded,
        bootstrap_success_fraction=success_fraction,
        median_prediction_interval_relative_width=median_prediction_width,
        background_work_per_agent_s=intervals["background_work_per_agent_s"],
        admission_work_units_per_agent=intervals["admission_work_units_per_agent"],
        capacity_units_per_second=intervals["capacity_units_per_second"],
        service_time_window_mean_ms=intervals["service_time_window_mean_ms"],
        service_time_between_window_standard_deviation_ms=intervals[
            "service_time_between_window_standard_deviation_ms"
        ],
        max_wait_s=intervals["max_wait_s"],
        dropped_work_fraction=intervals["dropped_work_fraction"],
        deferred_work_fraction=intervals["deferred_work_fraction"],
        measurement_provenance=tuple(sorted(set(group["measurement_provenance"].astype(str)))),
        parameter_class=(
            "notional" if "synthetic" in set(group["source_type"].astype(str)) else "inferred"
        ),
        field_evidence_class=(
            ("background_work_per_agent_s", "fitted"),
            ("admission_work_units_per_agent", "fitted"),
            ("capacity_units_per_second", "observed_summary"),
            ("service_time_window_mean_ms", "observed_summary"),
            (
                "service_time_between_window_standard_deviation_ms",
                "observed_summary",
            ),
            ("max_wait_s", "configured_summary"),
            ("dropped_work_fraction", "observed_summary"),
            ("deferred_work_fraction", "observed_summary"),
            ("arrival_process", "not_identifiable_from_current_schema"),
            ("service_time_distribution", "not_identifiable_from_current_schema"),
            ("overload_behavior", "not_identifiable_from_current_schema"),
            ("shedding_threshold", "not_identifiable_from_current_schema"),
            ("recovery_capacity_multiplier", "not_identifiable_from_current_schema"),
        ),
        criteria=criteria_tuple,
    )


def _implementation_record() -> tuple[tuple[str, str], ...]:
    package_root = Path(__file__).resolve().parents[1]
    files = (
        Path(__file__).resolve(),
        package_root / "empirical" / "assurance_campaign.py",
        package_root / "control_plane" / "resource_network.py",
    )
    records = [
        (
            (Path("fleet_sim") / path.relative_to(package_root)).as_posix(),
            _sha256_path(path),
        )
        for path in files
    ]
    runtime = {
        "numpy": importlib.metadata.version("numpy"),
        "pandas": importlib.metadata.version("pandas"),
        "python": platform.python_version(),
        "scipy": importlib.metadata.version("scipy"),
    }
    records.append(("runtime", _sha256_bytes(_canonical_json_bytes(runtime))))
    return tuple(records)


def fit_empirical_calibration(
    fit_input: CalibrationFitInput,
    policy: FitGatePolicy,
) -> EmpiricalCalibrationRun:
    """Fit all resources and run the preregisterable engineering gates."""

    if not fit_input.externally_digest_bound:
        raise ValueError("fit input must be externally digest-bound")
    frame = fit_input.calibration
    if set(frame["partition"].astype(str)) != {"calibration"}:
        raise ValueError("fit input must contain only the calibration partition")
    if canonical_calibration_partition_sha256(frame) != fit_input.calibration_content_sha256:
        raise ValueError("fit input calibration content does not match its evidence digest")
    expected_types = {item.value for item in ResourceType}
    if set(frame["resource_type"].astype(str)) != expected_types:
        raise ValueError("fit input must contain exactly the ten assurance resource types")
    bootstrap_work_units = (
        policy.bootstrap_replications * int(frame["time_block_id"].nunique()) * len(ResourceType)
    )
    if bootstrap_work_units > MAX_BOOTSTRAP_WORK_UNITS:
        raise ValueError("fit exceeds the deterministic bootstrap work-unit safety limit")
    global_criteria = _global_criteria(frame, policy)
    point_fits = tuple(
        _point_fit(
            frame[frame["resource_type"] == resource_type.value].copy(deep=True),
            policy,
        )
        for resource_type in ResourceType
    )
    quality_blocked = any(
        criterion.criterion_id in {"uncensored_complete_case", "zero_reported_missing_fraction"}
        and criterion.state != "passed"
        for criterion in global_criteria
    )
    if quality_blocked:
        bootstrap_draws, bootstrap_succeeded = _empty_bootstrap_draws(), 0
    else:
        bootstrap_draws, bootstrap_succeeded = _joint_bootstrap(point_fits, policy)
    resources = tuple(
        _resource_result(point, bootstrap_draws, bootstrap_succeeded, policy)
        for point in point_fits
    )
    combined_criteria = tuple(global_criteria) + tuple(
        criterion for resource in resources for criterion in resource.criteria
    )
    gate_status = _criteria_state(combined_criteria)
    blocking_reasons = tuple(
        sorted(
            {
                *_blocking_reasons(global_criteria),
                *(reason for resource in resources for reason in resource.blocking_reasons),
            }
        )
    )
    implementation = _implementation_record()
    implementation_sha256 = _sha256_bytes(
        _canonical_json_bytes([{"path": path, "sha256": digest} for path, digest in implementation])
    )
    identity = {
        "schema_version": FIT_SCHEMA_VERSION,
        "model_id": FIT_MODEL_ID,
        "calibration_content_sha256": fit_input.calibration_content_sha256,
        "calibration_context_sha256": fit_input.calibration_context_sha256,
        "campaign_schema_sha256": fit_input.campaign_schema_sha256,
        "measurement_schema_sha256": fit_input.measurement_schema_sha256,
        "policy_sha256": policy.policy_sha256,
        "implementation_sha256": implementation_sha256,
    }
    fit_id = f"empirical-calibration-{_sha256_bytes(_canonical_json_bytes(identity))[:20]}"
    fit = EmpiricalCalibrationFit(
        schema_version=FIT_SCHEMA_VERSION,
        calibration_fit_id=fit_id,
        model_id=FIT_MODEL_ID,
        model_formula=(
            "arrival_rate = background_work_per_agent_s * fleet_size + "
            "admission_work_units_per_agent * admission_rate"
        ),
        input_partition="calibration",
        source_package_heldout_verified=True,
        heldout_used_for_fit=False,
        calibration_content_sha256=fit_input.calibration_content_sha256,
        calibration_context_sha256=fit_input.calibration_context_sha256,
        campaign_schema_sha256=fit_input.campaign_schema_sha256,
        measurement_schema_sha256=fit_input.measurement_schema_sha256,
        source_evidence_scope=fit_input.source_evidence_scope,
        policy=policy,
        policy_sha256=policy.policy_sha256,
        implementation=implementation,
        implementation_sha256=implementation_sha256,
        bootstrap_method=(
            "joint circular moving-block bootstrap across ordered calibration time blocks; "
            "same sampled block sequence for all ten resources; percentile intervals with "
            "linear quantiles"
        ),
        gate_status=gate_status,
        blocking_reasons=blocking_reasons,
        interface_verification_ready=gate_status == "passed",
        eligible_for_adapter=(
            gate_status == "passed"
            and policy.study_mode == "successor_transfer"
            and fit_input.source_evidence_scope != "synthetic_or_mixed_interface_only"
        ),
        runner_authorized=False,
        scientific_use_authorized=False,
        external_validation=False,
        global_criteria=global_criteria,
        resources=resources,
    )
    return EmpiricalCalibrationRun(fit=fit, _bootstrap_draws=bootstrap_draws.copy(deep=True))


def calibration_policy_schema() -> dict[str, object]:
    """Return the retained Draft 2020-12 policy schema."""

    integer_minima = {
        "minimum_calibration_time_blocks": 4,
        "minimum_observations_per_resource": 4,
        "minimum_unique_fleet_sizes": 2,
        "minimum_unique_admission_rates": 2,
        "minimum_zero_admission_blocks": 1,
        "minimum_active_admission_blocks": 1,
        "minimum_unique_joint_predictor_vectors": 2,
        "target_fleet_size_min": 1,
        "target_fleet_size_max": 1,
        "bootstrap_replications": 100,
        "bootstrap_block_length": 1,
        "root_seed": 0,
    }
    properties: dict[str, object] = {
        field_name: {"type": "integer", "minimum": minimum}
        for field_name, minimum in integer_minima.items()
    }
    properties["root_seed"] = {
        "type": "integer",
        "minimum": 0,
        "maximum": 2**63 - 1,
    }
    properties["bootstrap_replications"] = {
        "type": "integer",
        "minimum": 100,
        "maximum": MAX_BOOTSTRAP_REPLICATIONS,
    }
    positive_fields = {
        "maximum_scaled_condition_number",
        "maximum_scaled_target_hull_distance",
        "maximum_weighted_normalized_rmse",
        "maximum_absolute_weighted_relative_bias",
        "maximum_capacity_coefficient_of_variation",
        "maximum_deadline_coefficient_of_variation",
        "interval_scale_floor",
        "maximum_background_interval_relative_width",
        "maximum_admission_interval_relative_width",
        "maximum_capacity_interval_relative_width",
        "maximum_service_interval_relative_width",
        "maximum_max_wait_interval_relative_width",
    }
    properties.update(
        {field_name: {"type": "number", "exclusiveMinimum": 0.0} for field_name in positive_fields}
    )
    properties["target_admission_rate_min_per_s"] = {
        "type": "number",
        "minimum": 0.0,
    }
    properties["target_admission_rate_max_per_s"] = {
        "type": "number",
        "minimum": 0.0,
    }
    properties["minimum_weighted_r_squared"] = {
        "type": "number",
        "minimum": -1.0,
        "maximum": 1.0,
    }
    properties["bootstrap_interval_level"] = {
        "type": "number",
        "exclusiveMinimum": 0.5,
        "exclusiveMaximum": 1.0,
    }
    properties["minimum_bootstrap_success_fraction"] = {
        "type": "number",
        "minimum": 0.5,
        "maximum": 1.0,
    }
    properties["policy_id"] = {
        "type": "string",
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
    }
    properties["study_mode"] = {
        "type": "string",
        "enum": ["interface_verification", "successor_transfer"],
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://fleet-assurance.local/schemas/empirical_calibration_policy.schema.json",
        "title": "Empirical assurance calibration fit policy",
        "type": "object",
        "required": sorted(FitGatePolicy.__dataclass_fields__),
        "properties": properties,
        "additionalProperties": False,
    }


def calibration_fit_schema() -> dict[str, object]:
    """Return the retained closed-shape schema for a computed fit artifact."""

    top_fields = {
        "schema_version",
        "calibration_fit_id",
        "model_id",
        "model_formula",
        "input_partition",
        "source_package_heldout_verified",
        "heldout_used_for_fit",
        "calibration_content_sha256",
        "calibration_context_sha256",
        "campaign_schema_sha256",
        "measurement_schema_sha256",
        "source_evidence_scope",
        "policy",
        "policy_sha256",
        "implementation",
        "implementation_sha256",
        "bootstrap_method",
        "gate_status",
        "blocking_reasons",
        "interface_verification_ready",
        "eligible_for_adapter",
        "runner_authorized",
        "scientific_use_authorized",
        "external_validation",
        "global_criteria",
        "resource_count",
        "resources",
    }
    digest = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    nullable_number = {"type": ["number", "null"]}
    nullable_nonnegative = {
        "anyOf": [
            {"type": "number", "minimum": 0.0},
            {"type": "null"},
        ]
    }
    interval = {
        "type": "object",
        "required": ["lower", "point", "upper"],
        "properties": {
            "lower": {"type": "number"},
            "point": {"type": "number"},
            "upper": {"type": "number"},
        },
        "additionalProperties": False,
    }
    nullable_interval = {"anyOf": [interval, {"type": "null"}]}
    criterion_fields = set(GateCriterion.__dataclass_fields__)
    criterion = {
        "type": "object",
        "required": sorted(criterion_fields),
        "properties": {
            "criterion_id": {"type": "string", "minLength": 1},
            "state": {"enum": ["passed", "failed", "not_evaluable"]},
            "observed": nullable_number,
            "operator": {"enum": ["<=", "==", ">", ">=", "is", "not_evaluable"]},
            "threshold": nullable_number,
            "reason": {"type": "string", "minLength": 1},
        },
        "additionalProperties": False,
    }
    field_evidence = {
        "background_work_per_agent_s": "fitted",
        "admission_work_units_per_agent": "fitted",
        "capacity_units_per_second": "observed_summary",
        "service_time_window_mean_ms": "observed_summary",
        "service_time_between_window_standard_deviation_ms": "observed_summary",
        "max_wait_s": "configured_summary",
        "dropped_work_fraction": "observed_summary",
        "deferred_work_fraction": "observed_summary",
        "arrival_process": "not_identifiable_from_current_schema",
        "service_time_distribution": "not_identifiable_from_current_schema",
        "overload_behavior": "not_identifiable_from_current_schema",
        "shedding_threshold": "not_identifiable_from_current_schema",
        "recovery_capacity_multiplier": "not_identifiable_from_current_schema",
    }
    resource_fields = set(ResourceFitResult.__dataclass_fields__)
    resource_properties: dict[str, object] = {
        "resource_id": {"type": "string", "minLength": 1},
        "resource_type": {"enum": [item.value for item in ResourceType]},
        "gate_status": {"enum": ["passed", "failed", "not_evaluable"]},
        "blocking_reasons": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
        },
        "observation_count": {"type": "integer", "minimum": 0},
        "time_block_count": {"type": "integer", "minimum": 0},
        "fleet_size_min": {"type": "integer", "minimum": 0},
        "fleet_size_max": {"type": "integer", "minimum": 0},
        "admission_rate_min_per_s": {"type": "number", "minimum": 0.0},
        "admission_rate_max_per_s": {"type": "number", "minimum": 0.0},
        "arrival_rate_min_per_s": {"type": "number", "minimum": 0.0},
        "arrival_rate_max_per_s": {"type": "number", "minimum": 0.0},
        "scaled_design_rank": {"type": "integer", "minimum": 0},
        "scaled_design_condition_number": nullable_nonnegative,
        "weighted_rmse_work_units_per_s": nullable_nonnegative,
        "weighted_normalized_rmse": nullable_nonnegative,
        "absolute_weighted_relative_bias": nullable_nonnegative,
        "weighted_r_squared": nullable_number,
        "capacity_coefficient_of_variation": {"type": "number", "minimum": 0.0},
        "deadline_coefficient_of_variation": {"type": "number", "minimum": 0.0},
        "bootstrap_requested": {"type": "integer", "minimum": 0},
        "bootstrap_succeeded": {"type": "integer", "minimum": 0},
        "bootstrap_success_fraction": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "median_prediction_interval_relative_width": nullable_nonnegative,
        "measurement_provenance": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
        },
        "parameter_class": {"enum": ["inferred", "notional"]},
        "field_evidence_class": {
            "type": "object",
            "required": sorted(field_evidence),
            "properties": {name: {"const": value} for name, value in field_evidence.items()},
            "additionalProperties": False,
        },
        "criteria": {"type": "array", "minItems": 1, "items": criterion},
    }
    for name in (
        "background_work_per_agent_s",
        "admission_work_units_per_agent",
        "capacity_units_per_second",
        "service_time_window_mean_ms",
        "service_time_between_window_standard_deviation_ms",
        "max_wait_s",
        "dropped_work_fraction",
        "deferred_work_fraction",
    ):
        resource_properties[name] = nullable_interval
    resource = {
        "type": "object",
        "required": sorted(resource_fields),
        "properties": resource_properties,
        "additionalProperties": False,
    }
    policy_contract = {
        key: value
        for key, value in calibration_policy_schema().items()
        if key not in {"$schema", "$id", "title"}
    }
    properties: dict[str, object] = {
        "schema_version": {"const": FIT_SCHEMA_VERSION},
        "calibration_fit_id": {
            "type": "string",
            "pattern": "^empirical-calibration-[0-9a-f]{20}$",
        },
        "model_id": {"const": FIT_MODEL_ID},
        "model_formula": {
            "const": (
                "arrival_rate = background_work_per_agent_s * fleet_size + "
                "admission_work_units_per_agent * admission_rate"
            )
        },
        "input_partition": {"const": "calibration"},
        "source_package_heldout_verified": {"const": True},
        "heldout_used_for_fit": {"const": False},
        "calibration_content_sha256": digest,
        "calibration_context_sha256": digest,
        "campaign_schema_sha256": digest,
        "measurement_schema_sha256": digest,
        "source_evidence_scope": {
            "enum": [
                "synthetic_or_mixed_interface_only",
                "measured_input_unreviewed",
                "replayed_input_unreviewed",
                "mixed_nonsynthetic_input_unreviewed",
            ]
        },
        "policy": policy_contract,
        "policy_sha256": digest,
        "implementation": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "uniqueItems": True,
            "items": {
                "type": "object",
                "required": ["path", "sha256"],
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "sha256": digest,
                },
                "additionalProperties": False,
            },
        },
        "implementation_sha256": digest,
        "bootstrap_method": {"type": "string", "minLength": 1},
        "gate_status": {"enum": ["passed", "failed", "not_evaluable"]},
        "blocking_reasons": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
        },
        "interface_verification_ready": {"type": "boolean"},
        "eligible_for_adapter": {"type": "boolean"},
        "runner_authorized": {"const": False},
        "scientific_use_authorized": {"const": False},
        "external_validation": {"const": False},
        "global_criteria": {"type": "array", "minItems": 1, "items": criterion},
        "resource_count": {"const": len(ResourceType)},
        "resources": {
            "type": "array",
            "minItems": len(ResourceType),
            "maxItems": len(ResourceType),
            "items": resource,
            "allOf": [
                {
                    "contains": {
                        "type": "object",
                        "required": ["resource_type"],
                        "properties": {"resource_type": {"const": item.value}},
                    },
                    "minContains": 1,
                    "maxContains": 1,
                }
                for item in ResourceType
            ],
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://fleet-assurance.local/schemas/empirical_calibration_fit.schema.json",
        "title": "Empirical assurance calibration fit",
        "type": "object",
        "required": sorted(top_fields),
        "properties": properties,
        "additionalProperties": False,
    }


def _artifact_record(path: Path) -> dict[str, object]:
    return {
        "path": path.name,
        "bytes": path.stat().st_size,
        "sha256": _sha256_path(path),
    }


def _fit_evidence_manifest(
    fit_input: CalibrationFitInput,
    run: EmpiricalCalibrationRun,
    artifact_paths: tuple[Path, ...],
) -> dict[str, object]:
    fit = run.fit
    evidence: dict[str, object] = {
        "schema_version": FIT_SCHEMA_VERSION,
        "calibration_fit_id": fit.calibration_fit_id,
        "gate_status": fit.gate_status,
        "interface_verification_ready": fit.interface_verification_ready,
        "eligible_for_adapter": fit.eligible_for_adapter,
        "runner_authorized": False,
        "scientific_use_authorized": False,
        "external_validation": False,
        "input_partition": "calibration",
        "source_package_heldout_verified": True,
        "heldout_used_for_fit": False,
        "source_commitments": {
            "campaign_id": fit_input.campaign_id,
            "source_dataset_id": fit_input.source_dataset_id,
            "source_evidence_manifest_sha256": (fit_input.source_evidence_manifest_sha256),
            "calibration_content_sha256": fit_input.calibration_content_sha256,
            "calibration_context_sha256": fit_input.calibration_context_sha256,
            "heldout_content_commitment_sha256": (fit_input.heldout_content_commitment_sha256),
            "campaign_manifest_sha256": fit_input.campaign_manifest_sha256,
            "campaign_schema_sha256": fit_input.campaign_schema_sha256,
            "measurement_schema_sha256": fit_input.measurement_schema_sha256,
            "source_evidence_scope": fit_input.source_evidence_scope,
            "externally_digest_bound": fit_input.externally_digest_bound,
        },
        "fit_bindings": {
            "model_id": fit.model_id,
            "policy_sha256": fit.policy_sha256,
            "implementation_sha256": fit.implementation_sha256,
            "calibration_fit_content_sha256": _sha256_bytes(_canonical_json_bytes(fit.to_dict())),
            "bootstrap_draws_content_sha256": _bootstrap_draws_sha256(run.bootstrap_draws),
        },
        "artifacts": [_artifact_record(path) for path in artifact_paths],
    }
    evidence["self_integrity_sha256"] = _sha256_bytes(_canonical_json_bytes(evidence))
    return evidence


def _canonical_bootstrap_draws(draws: pd.DataFrame) -> pd.DataFrame:
    expected_columns = _BOOTSTRAP_DRAW_COLUMNS
    actual_columns = list(draws.columns)
    if len(actual_columns) != len(expected_columns) or set(actual_columns) != set(expected_columns):
        raise ValueError("bootstrap draw columns differ from the closed contract")
    if draws.empty:
        return pd.DataFrame(columns=expected_columns)
    return (
        draws[list(expected_columns)]
        .sort_values(["bootstrap_replication", "resource_type"], kind="mergesort")
        .reset_index(drop=True)
    )


def _bootstrap_draws_sha256(draws: pd.DataFrame) -> str:
    canonical = _canonical_bootstrap_draws(draws)
    return _sha256_bytes(canonical.to_csv(index=False, lineterminator="\n").encode("utf-8"))


def write_empirical_calibration_package(
    run: EmpiricalCalibrationRun,
    fit_input: CalibrationFitInput,
    output_dir: str | Path,
) -> Path:
    """Write one atomic, no-overwrite calibration fit evidence package."""

    if run.fit.calibration_content_sha256 != fit_input.calibration_content_sha256:
        raise ValueError("fit and calibration input content hashes differ")
    fit_input_bindings = (
        (run.fit.calibration_context_sha256, fit_input.calibration_context_sha256),
        (run.fit.campaign_schema_sha256, fit_input.campaign_schema_sha256),
        (run.fit.measurement_schema_sha256, fit_input.measurement_schema_sha256),
        (run.fit.source_evidence_scope, fit_input.source_evidence_scope),
    )
    if any(left != right for left, right in fit_input_bindings):
        raise ValueError("fit and calibration input evidence bindings differ")
    if run.fit.policy_sha256 != run.fit.policy.policy_sha256:
        raise ValueError("fit policy hash is inconsistent")
    if importlib.util.find_spec("pyarrow") is None:
        raise RuntimeError("calibration fit packaging requires pyarrow")
    recomputed = fit_empirical_calibration(fit_input, run.fit.policy)
    if recomputed.fit.to_dict() != run.fit.to_dict():
        raise ValueError("fit result differs from deterministic recomputation")
    try:
        pd.testing.assert_frame_equal(
            _canonical_bootstrap_draws(recomputed.bootstrap_draws),
            _canonical_bootstrap_draws(run.bootstrap_draws),
            check_exact=True,
            check_dtype=True,
        )
    except AssertionError as exc:
        raise ValueError("bootstrap draws differ from deterministic recomputation") from exc
    destination = Path(output_dir)
    resolved_destination = destination.resolve(strict=False)
    source_root = fit_input._source_package_dir.resolve()
    if resolved_destination == source_root or source_root in resolved_destination.parents:
        raise ValueError("calibration fit output must be outside the source campaign package")
    if os.path.lexists(destination):
        raise FileExistsError(f"refusing to overwrite calibration fit package: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock_path = destination.parent / f".{destination.name}.fit.lock"
    try:
        lock_descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise FileExistsError(f"calibration fit package is locked: {destination}") from exc
    temporary: Path | None = None
    try:
        if os.path.lexists(destination):
            raise FileExistsError(f"refusing to overwrite calibration fit package: {destination}")
        temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
        calibration_path = temporary / "calibration_measurements.parquet"
        policy_path = temporary / "calibration_policy.json"
        policy_schema_path = temporary / "calibration_policy_schema.json"
        fit_path = temporary / "calibration_fit.json"
        fit_schema_path = temporary / "calibration_fit_schema.json"
        draws_path = temporary / "bootstrap_draws.parquet"
        evidence_path = temporary / "fit_evidence_manifest.json"

        fit_input.calibration.to_parquet(calibration_path, index=False)
        _write_json(policy_path, run.fit.policy.to_dict())
        _write_json(policy_schema_path, calibration_policy_schema())
        _write_json(fit_path, run.fit.to_dict())
        _write_json(fit_schema_path, calibration_fit_schema())
        _canonical_bootstrap_draws(run.bootstrap_draws).to_parquet(draws_path, index=False)
        artifacts = (
            calibration_path,
            policy_path,
            policy_schema_path,
            fit_path,
            fit_schema_path,
            draws_path,
        )
        _write_json(
            evidence_path,
            _fit_evidence_manifest(fit_input, run, artifacts),
        )
        if {path.name for path in temporary.iterdir()} != FIT_PACKAGE_FILES:
            raise RuntimeError("calibration fit package construction is incomplete")
        if os.path.lexists(destination):
            raise FileExistsError(f"refusing to overwrite calibration fit package: {destination}")
        os.rename(temporary, destination)
        temporary = None
        return destination
    except Exception:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)
        raise
    finally:
        os.close(lock_descriptor)
        lock_path.unlink(missing_ok=True)


def _read_bounded_file(path: Path, maximum_bytes: int) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"artifact must be a regular local file: {path.name}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum_bytes - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > maximum_bytes:
                raise ValueError(f"artifact exceeds the {maximum_bytes}-byte limit: {path.name}")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
        if any(getattr(before, name) != getattr(after, name) for name in stable_fields):
            raise ValueError(f"artifact changed while it was being read: {path.name}")
        if total != after.st_size:
            raise ValueError(f"artifact size changed while it was being read: {path.name}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _read_package_bytes(
    package: Path,
    maximum_package_bytes: int,
    *,
    expected_manifest_sha256: str | None,
) -> dict[str, bytes]:
    if maximum_package_bytes <= 0:
        raise ValueError("maximum_package_bytes must be positive")
    evidence_name = "fit_evidence_manifest.json"
    evidence = _read_bounded_file(package / evidence_name, maximum_package_bytes)
    if expected_manifest_sha256 is not None and _sha256_bytes(evidence) != (
        expected_manifest_sha256
    ):
        raise ValueError("fit evidence manifest does not match the externally supplied digest")
    retained = {evidence_name: evidence}
    remaining = maximum_package_bytes - len(evidence)
    for name in sorted(FIT_PACKAGE_FILES - {evidence_name}):
        artifact = _read_bounded_file(package / name, remaining)
        retained[name] = artifact
        remaining -= len(artifact)
    return retained


def _verify_artifact_inventory(
    evidence: Mapping[str, object], package_bytes: Mapping[str, bytes]
) -> None:
    records = evidence.get("artifacts")
    expected = FIT_PACKAGE_FILES - {"fit_evidence_manifest.json"}
    if not isinstance(records, list) or len(records) != len(expected):
        raise ValueError("fit artifact inventory is incomplete")
    names: set[str] = set()
    for record in records:
        selected = _exact_keys(record, {"path", "bytes", "sha256"}, "fit artifact")
        name = selected["path"]
        if not isinstance(name, str) or name != Path(name).name or name in names:
            raise ValueError("fit artifact paths must be unique portable file names")
        if name not in expected:
            raise ValueError(f"fit artifact role is invalid: {name}")
        names.add(name)
        byte_count = _integer(selected["bytes"], f"fit artifact bytes for {name}")
        if byte_count != len(package_bytes[name]):
            raise ValueError(f"fit artifact size mismatch: {name}")
        if _sha256(selected["sha256"], f"fit artifact hash for {name}") != _sha256_bytes(
            package_bytes[name]
        ):
            raise ValueError(f"fit artifact hash mismatch: {name}")
    if names != expected:
        raise ValueError("fit artifact inventory does not cover the package")


def _source_commitments(fit_input: CalibrationFitInput) -> dict[str, object]:
    return {
        "campaign_id": fit_input.campaign_id,
        "source_dataset_id": fit_input.source_dataset_id,
        "source_evidence_manifest_sha256": fit_input.source_evidence_manifest_sha256,
        "calibration_content_sha256": fit_input.calibration_content_sha256,
        "calibration_context_sha256": fit_input.calibration_context_sha256,
        "heldout_content_commitment_sha256": fit_input.heldout_content_commitment_sha256,
        "campaign_manifest_sha256": fit_input.campaign_manifest_sha256,
        "campaign_schema_sha256": fit_input.campaign_schema_sha256,
        "measurement_schema_sha256": fit_input.measurement_schema_sha256,
        "source_evidence_scope": fit_input.source_evidence_scope,
        "externally_digest_bound": True,
    }


def verify_empirical_calibration_package(
    package_dir: str | Path,
    *,
    source_campaign_package: str | Path,
    expected_source_evidence_manifest_sha256: str,
    expected_fit_evidence_manifest_sha256: str | None = None,
    maximum_package_bytes: int = 512 * 1024 * 1024,
    maximum_rows: int = 5_000_000,
    maximum_uncompressed_bytes: int = 2 * 1024 * 1024 * 1024,
) -> EmpiricalCalibrationPackageVerification:
    """Verify package integrity and recompute every fit from calibration only."""

    package = Path(package_dir)
    if package.is_symlink():
        raise ValueError("calibration fit package cannot be a symlink")
    if not package.is_dir():
        raise FileNotFoundError(package)
    entries = list(package.iterdir())
    if {path.name for path in entries} != FIT_PACKAGE_FILES:
        raise ValueError("calibration fit package file set mismatch")
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            raise ValueError("calibration fit package entries must be regular local files")
    expected_fit_digest = (
        None
        if expected_fit_evidence_manifest_sha256 is None
        else _sha256(
            expected_fit_evidence_manifest_sha256,
            "expected fit evidence manifest hash",
        )
    )
    package_bytes = _read_package_bytes(
        package,
        maximum_package_bytes,
        expected_manifest_sha256=expected_fit_digest,
    )
    evidence_bytes = package_bytes["fit_evidence_manifest.json"]
    evidence_digest = _sha256_bytes(evidence_bytes)
    evidence = _read_json_bytes(evidence_bytes, "fit_evidence_manifest.json")
    _exact_keys(
        evidence,
        {
            "schema_version",
            "calibration_fit_id",
            "gate_status",
            "interface_verification_ready",
            "eligible_for_adapter",
            "runner_authorized",
            "scientific_use_authorized",
            "external_validation",
            "input_partition",
            "source_package_heldout_verified",
            "heldout_used_for_fit",
            "source_commitments",
            "fit_bindings",
            "artifacts",
            "self_integrity_sha256",
        },
        "fit evidence manifest",
    )
    recorded_self_hash = _sha256(
        evidence.pop("self_integrity_sha256", None), "fit evidence self hash"
    )
    if recorded_self_hash != _sha256_bytes(_canonical_json_bytes(evidence)):
        raise ValueError("fit evidence manifest self hash mismatch")
    evidence["self_integrity_sha256"] = recorded_self_hash
    if evidence["schema_version"] != FIT_SCHEMA_VERSION:
        raise ValueError("fit evidence schema version mismatch")
    required_false = (
        "runner_authorized",
        "scientific_use_authorized",
        "external_validation",
        "heldout_used_for_fit",
    )
    if any(evidence[name] is not False for name in required_false):
        raise ValueError("fit evidence exceeds the permitted engineering evidence scope")
    if evidence["source_package_heldout_verified"] is not True:
        raise ValueError("fit evidence does not record complete source-package verification")
    if evidence["input_partition"] != "calibration":
        raise ValueError("fit evidence input partition is not calibration")
    _verify_artifact_inventory(evidence, package_bytes)

    if (
        _read_json_bytes(
            package_bytes["calibration_policy_schema.json"],
            "calibration_policy_schema.json",
        )
        != calibration_policy_schema()
    ):
        raise ValueError("retained calibration policy schema differs from the implementation")
    if (
        _read_json_bytes(
            package_bytes["calibration_fit_schema.json"],
            "calibration_fit_schema.json",
        )
        != calibration_fit_schema()
    ):
        raise ValueError("retained calibration fit schema differs from the implementation")
    policy = FitGatePolicy.from_mapping(
        _read_json_bytes(package_bytes["calibration_policy.json"], "calibration_policy.json")
    )
    retained_fit = _read_json_bytes(package_bytes["calibration_fit.json"], "calibration_fit.json")
    expected_source_digest = _sha256(
        expected_source_evidence_manifest_sha256,
        "expected source evidence manifest hash",
    )
    fit_input = prepare_calibration_fit_input(
        source_campaign_package,
        expected_evidence_manifest_sha256=expected_source_digest,
    )
    source_record = _exact_keys(
        evidence["source_commitments"],
        set(_source_commitments(fit_input)),
        "fit source commitments",
    )
    if dict(source_record) != _source_commitments(fit_input):
        raise ValueError("fit source commitments differ from the verified campaign")

    try:
        import pyarrow.parquet
    except ImportError as exc:
        raise RuntimeError("calibration fit verification requires pyarrow") from exc
    calibration_metadata = pyarrow.parquet.ParquetFile(
        io.BytesIO(package_bytes["calibration_measurements.parquet"])
    ).metadata
    draws_metadata = pyarrow.parquet.ParquetFile(
        io.BytesIO(package_bytes["bootstrap_draws.parquet"])
    ).metadata
    if calibration_metadata.num_rows + draws_metadata.num_rows > maximum_rows:
        raise ValueError("calibration fit package exceeds the row verification limit")
    uncompressed = sum(
        metadata.row_group(index).total_byte_size
        for metadata in (calibration_metadata, draws_metadata)
        for index in range(metadata.num_row_groups)
    )
    if uncompressed > maximum_uncompressed_bytes:
        raise ValueError("calibration fit package exceeds the uncompressed-byte limit")
    retained_calibration = pd.read_parquet(
        io.BytesIO(package_bytes["calibration_measurements.parquet"])
    )
    if canonical_calibration_partition_sha256(retained_calibration) != (
        fit_input.calibration_content_sha256
    ):
        raise ValueError("retained calibration measurements differ from the source commitment")
    retained_draws = _canonical_bootstrap_draws(
        pd.read_parquet(io.BytesIO(package_bytes["bootstrap_draws.parquet"]))
    )
    recomputed = fit_empirical_calibration(fit_input, policy)
    if retained_fit != recomputed.fit.to_dict():
        raise ValueError("retained calibration fit differs from deterministic recomputation")
    try:
        pd.testing.assert_frame_equal(
            retained_draws,
            _canonical_bootstrap_draws(recomputed.bootstrap_draws),
            check_exact=True,
            check_dtype=True,
        )
    except AssertionError as exc:
        raise ValueError("retained bootstrap draws differ from recomputation") from exc

    bindings = _exact_keys(
        evidence["fit_bindings"],
        {
            "model_id",
            "policy_sha256",
            "implementation_sha256",
            "calibration_fit_content_sha256",
            "bootstrap_draws_content_sha256",
        },
        "fit bindings",
    )
    expected_bindings = {
        "model_id": recomputed.fit.model_id,
        "policy_sha256": recomputed.fit.policy_sha256,
        "implementation_sha256": recomputed.fit.implementation_sha256,
        "calibration_fit_content_sha256": _sha256_bytes(
            _canonical_json_bytes(recomputed.fit.to_dict())
        ),
        "bootstrap_draws_content_sha256": _bootstrap_draws_sha256(recomputed.bootstrap_draws),
    }
    if dict(bindings) != expected_bindings:
        raise ValueError("fit evidence bindings differ from recomputation")
    if evidence["calibration_fit_id"] != recomputed.fit.calibration_fit_id:
        raise ValueError("fit evidence identifier mismatch")
    if evidence["gate_status"] != recomputed.fit.gate_status:
        raise ValueError("fit evidence gate status mismatch")
    for name in ("interface_verification_ready", "eligible_for_adapter"):
        if evidence[name] is not getattr(recomputed.fit, name):
            raise ValueError(f"fit evidence {name} mismatch")
    return EmpiricalCalibrationPackageVerification(
        package_dir=package.resolve(),
        fit=recomputed.fit,
        fit_evidence_manifest_sha256=evidence_digest,
        externally_digest_bound=expected_fit_evidence_manifest_sha256 is not None,
        _bootstrap_draws=retained_draws.copy(deep=True),
        _source_campaign_package_dir=fit_input._source_package_dir,
    )
