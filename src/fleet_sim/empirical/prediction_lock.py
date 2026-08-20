"""Target-free prediction commitment for the successor transfer study.

This module derives candidate and registered comparator predictions exclusively
from externally digest-bound calibration, fit, adapter, and registration
packages.  It deliberately has no evaluation-campaign input.  A package made
here is a deterministic workflow commitment, not proof that the commitment
preceded outcome access; external receipt, trusted time, and outcome custody
remain separate evidence gates.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import io
import json
import math
import os
import platform
import re
import shutil
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from ctypes import CDLL, c_char_p, c_int, c_uint, get_errno
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from errno import EEXIST, ENOTEMPTY
from pathlib import Path
from typing import Any, NoReturn

import numpy as np
import pandas as pd

from fleet_sim.control_plane.resource_network import ResourceType
from fleet_sim.empirical.assurance_campaign import (
    CampaignPackageVerification,
    verify_empirical_campaign_package,
)
from fleet_sim.empirical.calibration_gate import (
    FIT_MODEL_ID,
    EmpiricalCalibrationPackageVerification,
    IntervalEstimate,
    verify_empirical_calibration_package,
)
from fleet_sim.empirical.resource_adapter import (
    AdaptedResourcePackageVerification,
    verify_adapted_resource_bundle,
)
from fleet_sim.empirical.successor_protocol import (
    CANDIDATE_FIT_OBJECTIVE,
    CANDIDATE_FIT_PARTITION,
    CANDIDATE_MODEL_ID,
    CANDIDATE_POINT_PARAMETER_SOURCE,
    COMPARATOR,
    COMPARATOR_CONSTRAINT,
    COMPARATOR_ESTIMATOR,
    COMPARATOR_FIT_PARTITION,
    COMPARATOR_FORMULA,
    COMPARATOR_INTERCEPT,
    COMPARATOR_PREDICTOR,
    COMPARATOR_RESPONSE,
    COMPARATOR_SCOPE,
    COMPARATOR_WEIGHTING,
    COMPARATOR_ZERO_DENOMINATOR_POLICY,
    PREDICTION_FORMULA,
    PROTOCOL_SCHEMA_VERSION,
    UNCERTAINTY_INTERVAL_LEVEL_SOURCE,
    UNCERTAINTY_INTERVAL_TYPE,
    UNCERTAINTY_METHOD,
    UNCERTAINTY_QUANTILE_METHOD,
    UNCERTAINTY_REPLICATION_SET,
    UNCERTAINTY_SCOPE,
    SuccessorRegistrationPackageVerification,
    verify_successor_registration_package,
)

PREDICTION_LOCK_SCHEMA_VERSION = PROTOCOL_SCHEMA_VERSION
PREDICTION_LOCK_PACKAGE_FILES = {
    "prediction_lock.json",
    "prediction_lock_schema.json",
    "prediction_rows.parquet",
    "prediction_rows_schema.json",
    "prediction_parameter_draws.parquet",
    "prediction_parameter_draws_schema.json",
    "prediction_lock_manifest.json",
}

CANDIDATE_FORMULA = PREDICTION_FORMULA
COMPARATOR_MODEL_ID = COMPARATOR

PREDICTION_ROW_COLUMNS = (
    "cell_id",
    "time_block_id",
    "timestamp_utc",
    "resource_id",
    "resource_type",
    "fleet_size",
    "agents_admitted",
    "window_duration_ms",
    "admission_rate_per_s",
    "candidate_mean_arrival_rate_lower_per_s",
    "candidate_mean_arrival_rate_point_per_s",
    "candidate_mean_arrival_rate_upper_per_s",
    "candidate_mean_arrival_count_lower",
    "candidate_mean_arrival_count_point",
    "candidate_mean_arrival_count_upper",
    "comparator_mean_arrival_rate_lower_per_s",
    "comparator_mean_arrival_rate_point_per_s",
    "comparator_mean_arrival_rate_upper_per_s",
    "comparator_mean_arrival_count_lower",
    "comparator_mean_arrival_count_point",
    "comparator_mean_arrival_count_upper",
)
PREDICTION_PARAMETER_DRAW_COLUMNS = (
    "bootstrap_replication",
    "sampled_block_sequence_sha256",
    "resource_id",
    "resource_type",
    "candidate_background_work_per_agent_s",
    "candidate_admission_work_units_per_agent",
    "comparator_background_work_per_agent_s",
)
_FIT_BOOTSTRAP_DRAW_COLUMNS = (
    "bootstrap_replication",
    "sampled_block_sequence_sha256",
    "resource_id",
    "resource_type",
    "background_work_per_agent_s",
    "admission_work_units_per_agent",
    "capacity_units_per_second",
    "service_time_window_mean_ms",
    "service_time_between_window_standard_deviation_ms",
    "max_wait_s",
    "dropped_work_fraction",
    "deferred_work_fraction",
)

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MAX_PACKAGE_BYTES = 512 * 1024 * 1024
_MAX_ROWS = 5_000_000
_MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"nonfinite JSON constant is not permitted: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is not permitted: {key}")
        result[key] = value
    return result


def _read_json_bytes(data: bytes, name: str) -> dict[str, Any]:
    try:
        selected = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid UTF-8 JSON in {name}: {exc}") from exc
    if not isinstance(selected, dict):
        raise TypeError(f"{name} must contain one JSON object")
    return selected


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


def _sha256(value: object, context: str) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{context} must be a lowercase SHA-256 digest")
    return value


def _identifier(value: object, context: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{context} must be a portable identifier")
    return value


def _string(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{context} must be a nonempty string")
    return value


def _strict_bool(value: object, context: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{context} must be a Boolean")
    return value


def _integer(value: object, context: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{context} must be an integer")
    if value < minimum:
        raise ValueError(f"{context} must be at least {minimum}")
    return value


def _finite(value: object, context: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{context} must be numeric")
    selected = float(value)
    if not math.isfinite(selected):
        raise ValueError(f"{context} must be finite")
    if minimum is not None and selected < minimum:
        raise ValueError(f"{context} must be at least {minimum}")
    return selected


def _timestamp(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{context} must be an explicit UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{context} is not a valid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError(f"{context} must use UTC")
    canonical = parsed.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    if canonical != value:
        raise ValueError(f"{context} must use canonical UTC microsecond form")
    return canonical


def _timestamp_value(value: str) -> datetime:
    return datetime.fromisoformat(value)


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


def _json_scalar(value: object) -> object:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("canonical evidence rows cannot contain nonfinite values")
    return value


def _frame_content_sha256(frame: pd.DataFrame, columns: tuple[str, ...]) -> str:
    records = [
        {column: _json_scalar(row[column]) for column in columns}
        for row in frame[list(columns)].to_dict("records")
    ]
    return _sha256_bytes(_canonical_json_bytes(records))


def _fit_bootstrap_draws_content_sha256(frame: pd.DataFrame) -> str:
    canonical = _canonical_fit_draws(frame)
    return _sha256_bytes(canonical.to_csv(index=False, lineterminator="\n").encode("utf-8"))


@dataclass(frozen=True, slots=True)
class LockedResourcePredictionParameters:
    """Point parameters and paired-bootstrap support for one resource."""

    resource_id: str
    resource_type: str
    candidate_background_work_per_agent_s: float
    candidate_admission_work_units_per_agent: float
    comparator_background_work_per_agent_s: float
    comparator_background_interval: IntervalEstimate
    paired_bootstrap_replication_count: int

    def __post_init__(self) -> None:
        _bounded_text(self.resource_id, "prediction resource_id")
        ResourceType(self.resource_type)
        _finite(
            self.candidate_background_work_per_agent_s,
            "candidate background parameter",
            minimum=0.0,
        )
        if (
            _finite(
                self.candidate_admission_work_units_per_agent,
                "candidate admission parameter",
                minimum=0.0,
            )
            <= 0.0
        ):
            raise ValueError("candidate admission parameter must be positive")
        _finite(
            self.comparator_background_work_per_agent_s,
            "comparator background parameter",
            minimum=0.0,
        )
        _integer(
            self.paired_bootstrap_replication_count,
            "paired bootstrap replication count",
            minimum=1,
        )

    @classmethod
    def from_mapping(cls, value: object) -> LockedResourcePredictionParameters:
        selected = _exact_keys(value, set(cls.__dataclass_fields__), "resource parameters")
        interval = _exact_keys(
            selected["comparator_background_interval"],
            {"lower", "point", "upper"},
            "comparator background interval",
        )
        return cls(
            resource_id=_bounded_text(selected["resource_id"], "resource_id"),
            resource_type=_string(selected["resource_type"], "resource_type"),
            candidate_background_work_per_agent_s=_finite(
                selected["candidate_background_work_per_agent_s"],
                "candidate background parameter",
                minimum=0.0,
            ),
            candidate_admission_work_units_per_agent=_finite(
                selected["candidate_admission_work_units_per_agent"],
                "candidate admission parameter",
                minimum=0.0,
            ),
            comparator_background_work_per_agent_s=_finite(
                selected["comparator_background_work_per_agent_s"],
                "comparator background parameter",
                minimum=0.0,
            ),
            comparator_background_interval=IntervalEstimate(
                lower=_finite(interval["lower"], "comparator interval lower", minimum=0.0),
                point=_finite(interval["point"], "comparator interval point", minimum=0.0),
                upper=_finite(interval["upper"], "comparator interval upper", minimum=0.0),
            ),
            paired_bootstrap_replication_count=_integer(
                selected["paired_bootstrap_replication_count"],
                "paired bootstrap replication count",
                minimum=1,
            ),
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["comparator_background_interval"] = self.comparator_background_interval.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class SuccessorPredictionLock:
    """Closed metadata for one target-free prediction commitment."""

    schema_version: str
    prediction_lock_id: str
    committed_at_utc: str
    registration_id: str
    registration_manifest_sha256: str
    registration_mode: str
    source_campaign_id: str
    source_campaign_evidence_manifest_sha256: str
    source_calibration_content_sha256: str
    source_historical_heldout_used_for_prediction: bool
    calibration_fit_id: str
    candidate_model_id: str
    fit_policy_sha256: str
    fit_evidence_manifest_sha256: str
    fit_bootstrap_draws_content_sha256: str
    adapter_bundle_id: str
    adapter_policy_sha256: str
    adapter_manifest_sha256: str
    adapter_specification_sha256: str
    plan_sha256: str
    transfer_contract_sha256: str
    planned_evaluation_campaign_id: str
    planned_cell_count: int
    planned_time_block_count: int
    resource_count: int
    prediction_row_count: int
    paired_bootstrap_replication_count: int
    prediction_rows_content_sha256: str
    prediction_parameter_draws_content_sha256: str
    candidate_formula: str
    comparator_model_id: str
    comparator_formula: str
    uncertainty_method: str
    uncertainty_scope: str
    bootstrap_interval_level: float
    bootstrap_quantile_method: str
    resource_parameters: tuple[LockedResourcePredictionParameters, ...]
    implementation: tuple[tuple[str, str], ...]
    implementation_sha256: str
    upstream_chain_verified: bool
    registered_semantics_reconciled: bool
    planned_predictor_design_reconciled: bool
    prediction_formula_frozen: bool
    comparator_formula_frozen: bool
    future_evaluation_campaign_not_supplied: bool
    prediction_rows_target_free: bool
    local_lock_chronology_consistent: bool
    workflow_prediction_commitment: bool
    prediction_lock_time_externally_attested: bool
    prediction_rows_preoutcome_locked: bool
    outcome_release_custody_verified: bool
    execution_chain_ready: bool
    external_validation: bool
    scientific_use_authorized: bool
    runner_authorized: bool

    def __post_init__(self) -> None:
        if self.schema_version != PREDICTION_LOCK_SCHEMA_VERSION:
            raise ValueError(
                f"prediction-lock schema_version must be {PREDICTION_LOCK_SCHEMA_VERSION}"
            )
        if not re.fullmatch(r"successor-prediction-lock-[0-9a-f]{20}", self.prediction_lock_id):
            raise ValueError("prediction_lock_id differs from the closed identity format")
        _timestamp(self.committed_at_utc, "committed_at_utc")
        for value, context in (
            (self.registration_id, "registration_id"),
            (self.source_campaign_id, "source_campaign_id"),
            (self.calibration_fit_id, "calibration_fit_id"),
            (self.adapter_bundle_id, "adapter_bundle_id"),
            (self.planned_evaluation_campaign_id, "planned evaluation campaign ID"),
        ):
            _identifier(value, context)
        if self.registration_mode not in {"engineering_dry_run", "prospective_transfer"}:
            raise ValueError("prediction-lock registration mode is unsupported")
        for value, context in (
            (self.registration_manifest_sha256, "registration manifest hash"),
            (self.source_campaign_evidence_manifest_sha256, "source campaign hash"),
            (self.source_calibration_content_sha256, "calibration content hash"),
            (self.fit_policy_sha256, "fit policy hash"),
            (self.fit_evidence_manifest_sha256, "fit evidence hash"),
            (self.fit_bootstrap_draws_content_sha256, "fit bootstrap content hash"),
            (self.adapter_policy_sha256, "adapter policy hash"),
            (self.adapter_manifest_sha256, "adapter manifest hash"),
            (self.adapter_specification_sha256, "adapter specification hash"),
            (self.plan_sha256, "plan hash"),
            (self.transfer_contract_sha256, "transfer contract hash"),
            (self.prediction_rows_content_sha256, "prediction rows hash"),
            (
                self.prediction_parameter_draws_content_sha256,
                "prediction parameter draws hash",
            ),
            (self.implementation_sha256, "implementation hash"),
        ):
            _sha256(value, context)
        for count_value, count_context in (
            (self.planned_cell_count, "planned cell count"),
            (self.planned_time_block_count, "planned time-block count"),
            (self.resource_count, "resource count"),
            (self.prediction_row_count, "prediction row count"),
            (self.paired_bootstrap_replication_count, "paired bootstrap count"),
        ):
            _integer(count_value, count_context, minimum=1)
        if self.resource_count != len(ResourceType):
            raise ValueError("prediction lock must cover exactly ten resources")
        if self.prediction_row_count != self.planned_time_block_count * self.resource_count:
            raise ValueError("prediction-row count differs from the frozen block/resource design")
        if len(self.resource_parameters) != self.resource_count:
            raise ValueError("resource-parameter count differs from the resource contract")
        resource_types = [item.resource_type for item in self.resource_parameters]
        if len(resource_types) != len(set(resource_types)) or set(resource_types) != {
            item.value for item in ResourceType
        }:
            raise ValueError("resource parameters must cover every resource type exactly once")
        if any(
            item.paired_bootstrap_replication_count != self.paired_bootstrap_replication_count
            for item in self.resource_parameters
        ):
            raise ValueError("resource paired-bootstrap counts are inconsistent")
        if self.candidate_model_id != FIT_MODEL_ID or self.candidate_formula != CANDIDATE_FORMULA:
            raise ValueError("candidate model semantics differ from the implemented lock")
        if (
            self.comparator_model_id != COMPARATOR_MODEL_ID
            or self.comparator_formula != COMPARATOR_FORMULA
        ):
            raise ValueError("comparator semantics differ from the implemented lock")
        if (
            self.uncertainty_method != UNCERTAINTY_METHOD
            or self.uncertainty_scope != UNCERTAINTY_SCOPE
        ):
            raise ValueError("uncertainty semantics differ from the implemented lock")
        if self.bootstrap_quantile_method != UNCERTAINTY_QUANTILE_METHOD:
            raise ValueError("bootstrap quantile method differs from the implemented lock")
        level = _finite(self.bootstrap_interval_level, "bootstrap interval level")
        if not 0.5 < level < 1.0:
            raise ValueError("bootstrap interval level must be within (0.5, 1)")
        if len(self.implementation) != 6 or len({item[0] for item in self.implementation}) != 6:
            raise ValueError("prediction-lock implementation boundary must contain six records")
        for path, digest in self.implementation:
            if not path or path.startswith(("/", "~")) or ".." in Path(path).parts:
                raise ValueError("implementation paths must be portable package-relative names")
            _sha256(digest, f"implementation hash for {path}")
        visible = [{"path": path, "sha256": digest} for path, digest in self.implementation]
        if self.implementation_sha256 != _sha256_bytes(_canonical_json_bytes(visible)):
            raise ValueError("prediction-lock implementation hash is inconsistent")
        if not (
            self.upstream_chain_verified
            and self.registered_semantics_reconciled
            and self.planned_predictor_design_reconciled
            and self.prediction_formula_frozen
            and self.comparator_formula_frozen
            and self.future_evaluation_campaign_not_supplied
            and self.prediction_rows_target_free
            and self.local_lock_chronology_consistent
            and self.workflow_prediction_commitment
        ):
            raise ValueError("prediction-lock construction gates must be true")
        if (
            self.source_historical_heldout_used_for_prediction
            or self.prediction_lock_time_externally_attested
            or self.prediction_rows_preoutcome_locked
            or self.outcome_release_custody_verified
            or self.execution_chain_ready
            or self.external_validation
            or self.scientific_use_authorized
            or self.runner_authorized
        ):
            raise ValueError("prediction lock exceeds the target-free workflow boundary")

    @classmethod
    def from_mapping(cls, value: object) -> SuccessorPredictionLock:
        return _lock_from_mapping(value)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["resource_parameters"] = [item.to_dict() for item in self.resource_parameters]
        payload["implementation"] = [
            {"path": path, "sha256": digest} for path, digest in self.implementation
        ]
        return payload


@dataclass(frozen=True, slots=True)
class SuccessorPredictionLockRun:
    lock: SuccessorPredictionLock
    _prediction_rows: pd.DataFrame
    _parameter_draws: pd.DataFrame

    @property
    def prediction_rows(self) -> pd.DataFrame:
        return self._prediction_rows.copy(deep=True)

    @property
    def parameter_draws(self) -> pd.DataFrame:
        return self._parameter_draws.copy(deep=True)


@dataclass(frozen=True, slots=True)
class SuccessorPredictionLockPackageVerification:
    package_dir: Path
    lock: SuccessorPredictionLock
    _prediction_rows: pd.DataFrame
    _parameter_draws: pd.DataFrame
    prediction_lock_manifest_sha256: str
    externally_digest_bound: bool

    @property
    def prediction_rows(self) -> pd.DataFrame:
        return self._prediction_rows.copy(deep=True)

    @property
    def parameter_draws(self) -> pd.DataFrame:
        return self._parameter_draws.copy(deep=True)


def _bounded_text(value: object, context: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{context} must be a nonempty string")
    if value != value.strip() or len(value) > maximum or "\x00" in value:
        raise ValueError(f"{context} is outside the bounded text contract")
    return value


def _canonical_fit_draws(frame: pd.DataFrame) -> pd.DataFrame:
    if len(frame.columns) != len(_FIT_BOOTSTRAP_DRAW_COLUMNS) or set(frame.columns) != set(
        _FIT_BOOTSTRAP_DRAW_COLUMNS
    ):
        raise ValueError("fit bootstrap draw columns differ from the closed contract")
    selected = frame[list(_FIT_BOOTSTRAP_DRAW_COLUMNS)].copy(deep=True)
    if selected.empty:
        raise ValueError("prediction locking requires successful fit bootstrap draws")
    for column in ("bootstrap_replication",):
        values = pd.to_numeric(selected[column], errors="coerce").to_numpy(float)
        if not np.isfinite(values).all() or not np.equal(values, np.floor(values)).all():
            raise ValueError(f"{column} must contain finite integers")
        if (values < 0).any():
            raise ValueError(f"{column} must be nonnegative")
        selected[column] = values.astype(np.int64)
    for column in _FIT_BOOTSTRAP_DRAW_COLUMNS[4:]:
        values = pd.to_numeric(selected[column], errors="coerce").to_numpy(float)
        if not np.isfinite(values).all() or (values < 0.0).any():
            raise ValueError(f"fit bootstrap {column} must be finite and nonnegative")
        selected[column] = values.astype(float)
    selected["resource_id"] = [
        _bounded_text(value, "fit bootstrap resource_id") for value in selected["resource_id"]
    ]
    selected["resource_type"] = selected["resource_type"].astype(str)
    if not set(selected["resource_type"]).issubset({item.value for item in ResourceType}):
        raise ValueError("fit bootstrap contains an unsupported resource type")
    selected["sampled_block_sequence_sha256"] = [
        _sha256(value, "sampled block-sequence hash")
        for value in selected["sampled_block_sequence_sha256"]
    ]
    duplicate = selected.duplicated(["bootstrap_replication", "resource_type"], keep=False)
    if duplicate.any():
        raise ValueError("fit bootstrap contains duplicate replication/resource rows")
    return selected.sort_values(
        ["bootstrap_replication", "resource_type"], kind="mergesort"
    ).reset_index(drop=True)


def _canonical_parameter_draws(frame: pd.DataFrame) -> pd.DataFrame:
    if len(frame.columns) != len(PREDICTION_PARAMETER_DRAW_COLUMNS) or set(frame.columns) != set(
        PREDICTION_PARAMETER_DRAW_COLUMNS
    ):
        raise ValueError("prediction parameter-draw columns differ from the closed contract")
    selected = frame[list(PREDICTION_PARAMETER_DRAW_COLUMNS)].copy(deep=True)
    if selected.empty:
        raise ValueError("prediction parameter draws cannot be empty")
    replication = pd.to_numeric(selected["bootstrap_replication"], errors="coerce").to_numpy(float)
    if (
        not np.isfinite(replication).all()
        or not np.equal(replication, np.floor(replication)).all()
        or (replication < 0).any()
    ):
        raise ValueError("bootstrap_replication must contain nonnegative integers")
    selected["bootstrap_replication"] = replication.astype(np.int64)
    selected["sampled_block_sequence_sha256"] = [
        _sha256(value, "sampled block-sequence hash")
        for value in selected["sampled_block_sequence_sha256"]
    ]
    selected["resource_id"] = [
        _bounded_text(value, "parameter-draw resource_id") for value in selected["resource_id"]
    ]
    selected["resource_type"] = selected["resource_type"].astype(str)
    expected_resources = {item.value for item in ResourceType}
    if set(selected["resource_type"]) != expected_resources:
        raise ValueError("prediction parameter draws must cover all ten resource types")
    for column in PREDICTION_PARAMETER_DRAW_COLUMNS[4:]:
        values = pd.to_numeric(selected[column], errors="coerce").to_numpy(float)
        if not np.isfinite(values).all() or (values < 0.0).any():
            raise ValueError(f"{column} must be finite and nonnegative")
        selected[column] = values.astype(float)
    duplicate = selected.duplicated(["bootstrap_replication", "resource_type"], keep=False)
    if duplicate.any():
        raise ValueError("prediction parameter draws contain duplicate keys")
    expected_count = len(ResourceType)
    per_replication = selected.groupby("bootstrap_replication")["resource_type"].nunique()
    if set(per_replication.astype(int)) != {expected_count}:
        raise ValueError("every paired bootstrap replication must contain ten resources")
    digest_counts = selected.groupby("bootstrap_replication")[
        "sampled_block_sequence_sha256"
    ].nunique()
    if set(digest_counts.astype(int)) != {1}:
        raise ValueError("paired resource draws disagree on the sampled block sequence")
    return selected.sort_values(
        ["bootstrap_replication", "resource_type"], kind="mergesort"
    ).reset_index(drop=True)


def _canonical_prediction_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if len(frame.columns) != len(PREDICTION_ROW_COLUMNS) or set(frame.columns) != set(
        PREDICTION_ROW_COLUMNS
    ):
        raise ValueError("prediction-row columns differ from the closed contract")
    selected = frame[list(PREDICTION_ROW_COLUMNS)].copy(deep=True)
    if selected.empty:
        raise ValueError("prediction rows cannot be empty")
    for column in ("cell_id", "time_block_id"):
        selected[column] = [_identifier(value, column) for value in selected[column]]
    selected["timestamp_utc"] = [
        _timestamp(value, "prediction timestamp_utc") for value in selected["timestamp_utc"]
    ]
    selected["resource_id"] = [
        _bounded_text(value, "prediction resource_id") for value in selected["resource_id"]
    ]
    selected["resource_type"] = selected["resource_type"].astype(str)
    expected_resources = {item.value for item in ResourceType}
    if set(selected["resource_type"]) != expected_resources:
        raise ValueError("prediction rows must cover all ten resource types")
    for column in ("fleet_size", "agents_admitted"):
        values = pd.to_numeric(selected[column], errors="coerce").to_numpy(float)
        if (
            not np.isfinite(values).all()
            or not np.equal(values, np.floor(values)).all()
            or (values < (1 if column == "fleet_size" else 0)).any()
        ):
            raise ValueError(f"{column} differs from the integer predictor contract")
        selected[column] = values.astype(np.int64)
    if (selected["agents_admitted"] > selected["fleet_size"]).any():
        raise ValueError("prediction agents_admitted cannot exceed fleet_size")
    numeric_columns = PREDICTION_ROW_COLUMNS[7:]
    for column in numeric_columns:
        values = pd.to_numeric(selected[column], errors="coerce").to_numpy(float)
        minimum = 0.0
        if not np.isfinite(values).all() or (values < minimum).any():
            raise ValueError(f"{column} must be finite and nonnegative")
        if column == "window_duration_ms" and (values <= 0.0).any():
            raise ValueError("window_duration_ms must be positive")
        selected[column] = values.astype(float)
    duplicate = selected.duplicated(["cell_id", "time_block_id", "resource_type"], keep=False)
    if duplicate.any():
        raise ValueError("prediction rows contain duplicate cell/block/resource keys")
    for prefix in ("candidate", "comparator"):
        for quantity in ("arrival_rate", "arrival_count"):
            lower = selected[
                f"{prefix}_mean_{quantity}_lower" + ("_per_s" if quantity == "arrival_rate" else "")
            ]
            upper = selected[
                f"{prefix}_mean_{quantity}_upper" + ("_per_s" if quantity == "arrival_rate" else "")
            ]
            if (lower > upper).any():
                raise ValueError(f"{prefix} {quantity} interval bounds are unordered")
    return selected.sort_values(
        ["cell_id", "time_block_id", "resource_type"], kind="mergesort"
    ).reset_index(drop=True)


def _circular_block_sample(
    block_count: int,
    block_length: int,
    rng: np.random.Generator,
) -> np.ndarray:
    selected: list[int] = []
    while len(selected) < block_count:
        start = int(rng.integers(0, block_count))
        for offset in range(block_length):
            selected.append((start + offset) % block_count)
            if len(selected) == block_count:
                break
    return np.asarray(selected, dtype=np.int64)


def _background_only_coefficient(frame: pd.DataFrame) -> float:
    duration_s = frame["window_duration_ms"].to_numpy(float) / 1000.0
    fleet_size = frame["fleet_size"].to_numpy(float)
    arrival_count = frame["arrival_count"].to_numpy(float)
    numerator = math.fsum(
        float(fleet * arrivals) for fleet, arrivals in zip(fleet_size, arrival_count, strict=True)
    )
    denominator = math.fsum(
        float(duration * fleet * fleet)
        for duration, fleet in zip(duration_s, fleet_size, strict=True)
    )
    if not math.isfinite(denominator) or denominator <= 0.0:
        raise ValueError("background-only comparator denominator is not positive")
    coefficient = max(0.0, numerator / denominator)
    if not math.isfinite(coefficient):
        raise ValueError("background-only comparator coefficient is nonfinite")
    return coefficient


def _interval(point: float, draws: np.ndarray, level: float) -> IntervalEstimate:
    if draws.size == 0 or not np.isfinite(draws).all():
        raise ValueError("prediction interval draws must be finite and nonempty")
    alpha = (1.0 - level) / 2.0
    lower, upper = np.quantile(draws, [alpha, 1.0 - alpha], method="linear")
    return IntervalEstimate(lower=float(lower), point=float(point), upper=float(upper))


def _implementation_record() -> tuple[tuple[str, str], ...]:
    package_root = Path(__file__).resolve().parents[1]
    files = (
        Path(__file__).resolve(),
        package_root / "empirical" / "assurance_campaign.py",
        package_root / "empirical" / "calibration_gate.py",
        package_root / "empirical" / "resource_adapter.py",
        package_root / "empirical" / "successor_protocol.py",
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
        "pyarrow": importlib.metadata.version("pyarrow"),
        "python": platform.python_version(),
        "scipy": importlib.metadata.version("scipy"),
    }
    records.append(("runtime", _sha256_bytes(_canonical_json_bytes(runtime))))
    return tuple(records)


def _refresh_upstream_packages(
    source_campaign: CampaignPackageVerification,
    fit_package: EmpiricalCalibrationPackageVerification,
    adapter_package: AdaptedResourcePackageVerification,
    registration_package: SuccessorRegistrationPackageVerification,
) -> tuple[
    CampaignPackageVerification,
    EmpiricalCalibrationPackageVerification,
    AdaptedResourcePackageVerification,
    SuccessorRegistrationPackageVerification,
]:
    """Reverify every physical package and reject forged verification wrappers."""

    if not (
        source_campaign.externally_digest_bound
        and fit_package.externally_digest_bound
        and adapter_package.externally_digest_bound
        and registration_package.externally_digest_bound
    ):
        raise ValueError("prediction locking requires externally digest-bound upstream packages")
    refreshed_source = verify_empirical_campaign_package(
        source_campaign.package_dir,
        expected_evidence_manifest_sha256=source_campaign.evidence_manifest_sha256,
    )
    if (
        refreshed_source.package_dir.resolve() != source_campaign.package_dir.resolve()
        or refreshed_source.dataset_id != source_campaign.dataset_id
        or refreshed_source.evidence_scope != source_campaign.evidence_scope
        or refreshed_source.external_validation != source_campaign.external_validation
        or refreshed_source.scientific_use_authorized != source_campaign.scientific_use_authorized
        or refreshed_source.evidence_manifest != source_campaign.evidence_manifest
        or not refreshed_source.calibration.equals(source_campaign.calibration)
        or not refreshed_source.heldout.equals(source_campaign.heldout)
    ):
        raise ValueError("source campaign wrapper differs from its externally bound package")
    refreshed_fit = verify_empirical_calibration_package(
        fit_package.package_dir,
        source_campaign_package=refreshed_source.package_dir,
        expected_source_evidence_manifest_sha256=(refreshed_source.evidence_manifest_sha256),
        expected_fit_evidence_manifest_sha256=fit_package.fit_evidence_manifest_sha256,
    )
    if (
        refreshed_fit.package_dir.resolve() != fit_package.package_dir.resolve()
        or refreshed_fit.fit.to_dict() != fit_package.fit.to_dict()
        or not refreshed_fit.bootstrap_draws.equals(fit_package.bootstrap_draws)
        or refreshed_fit._source_campaign_package_dir.resolve()
        != fit_package._source_campaign_package_dir.resolve()
    ):
        raise ValueError("fit wrapper differs from its externally bound package")
    refreshed_adapter = verify_adapted_resource_bundle(
        adapter_package.package_dir,
        fit_package=refreshed_fit,
        expected_policy_sha256=adapter_package.bundle.adapter_policy_sha256,
        expected_adapter_manifest_sha256=adapter_package.adapter_manifest_sha256,
    )
    if (
        refreshed_adapter.package_dir.resolve() != adapter_package.package_dir.resolve()
        or refreshed_adapter.bundle.to_dict() != adapter_package.bundle.to_dict()
    ):
        raise ValueError("adapter wrapper differs from its externally bound package")
    refreshed_registration = verify_successor_registration_package(
        registration_package.package_dir,
        source_campaign=refreshed_source,
        fit_package=refreshed_fit,
        adapter_package=refreshed_adapter,
        expected_registration_manifest_sha256=(registration_package.registration_manifest_sha256),
    )
    if (
        refreshed_registration.package_dir.resolve() != registration_package.package_dir.resolve()
        or refreshed_registration.registration.to_dict()
        != registration_package.registration.to_dict()
        or refreshed_registration.plan.to_dict() != registration_package.plan.to_dict()
        or refreshed_registration.contract.to_dict() != registration_package.contract.to_dict()
    ):
        raise ValueError("registration wrapper differs from its externally bound package")
    return refreshed_source, refreshed_fit, refreshed_adapter, refreshed_registration


def _validate_registered_semantics(
    registration_package: SuccessorRegistrationPackageVerification,
    fit_package: EmpiricalCalibrationPackageVerification,
) -> None:
    contract = registration_package.contract
    candidate = contract.candidate
    comparator = contract.comparator
    uncertainty = contract.uncertainty
    candidate_expected = {
        "model_id": CANDIDATE_MODEL_ID,
        "formula": PREDICTION_FORMULA,
        "fit_partition": CANDIDATE_FIT_PARTITION,
        "fit_objective": CANDIDATE_FIT_OBJECTIVE,
        "point_parameter_source": CANDIDATE_POINT_PARAMETER_SOURCE,
    }
    comparator_expected = {
        "model_id": COMPARATOR,
        "formula": COMPARATOR_FORMULA,
        "fit_partition": COMPARATOR_FIT_PARTITION,
        "scope": COMPARATOR_SCOPE,
        "response": COMPARATOR_RESPONSE,
        "predictor": COMPARATOR_PREDICTOR,
        "intercept": COMPARATOR_INTERCEPT,
        "weighting": COMPARATOR_WEIGHTING,
        "constraint": COMPARATOR_CONSTRAINT,
        "estimator": COMPARATOR_ESTIMATOR,
        "zero_denominator_policy": COMPARATOR_ZERO_DENOMINATOR_POLICY,
    }
    uncertainty_expected = {
        "method": UNCERTAINTY_METHOD,
        "replication_set": UNCERTAINTY_REPLICATION_SET,
        "interval_type": UNCERTAINTY_INTERVAL_TYPE,
        "interval_level_source": UNCERTAINTY_INTERVAL_LEVEL_SOURCE,
        "quantile_method": UNCERTAINTY_QUANTILE_METHOD,
        "scope": UNCERTAINTY_SCOPE,
    }
    for name, expected in candidate_expected.items():
        if getattr(candidate, name) != expected:
            raise ValueError(f"registered candidate {name} differs from lock implementation")
    for name, expected in comparator_expected.items():
        if getattr(comparator, name) != expected:
            raise ValueError(f"registered comparator {name} differs from lock implementation")
    for name, expected in uncertainty_expected.items():
        if getattr(uncertainty, name) != expected:
            raise ValueError(f"registered uncertainty {name} differs from lock implementation")
    if candidate.model_id != fit_package.fit.model_id or candidate.model_id != FIT_MODEL_ID:
        raise ValueError("registered candidate model differs from the verified calibration fit")
    if tuple(candidate.predictor_fields) != (
        "fleet_size",
        "agents_admitted",
        "window_duration_ms",
    ):
        raise ValueError("registered candidate predictors differ from the lock implementation")


def _paired_parameter_draws(
    calibration: pd.DataFrame,
    fit_package: EmpiricalCalibrationPackageVerification,
) -> pd.DataFrame:
    fit_draws = _canonical_fit_draws(fit_package.bootstrap_draws)
    policy = fit_package.fit.policy
    ordered_by_resource = {
        resource_type.value: calibration[
            calibration["resource_type"].astype(str) == resource_type.value
        ]
        .sort_values(["timestamp", "time_block_id"], kind="mergesort")
        .reset_index(drop=True)
        for resource_type in ResourceType
    }
    first = ordered_by_resource[next(iter(ordered_by_resource))]
    block_ids = tuple(first["time_block_id"].astype(str))
    if not block_ids or len(block_ids) != len(set(block_ids)):
        raise ValueError("calibration time blocks are empty or duplicated")
    for resource_type, group in ordered_by_resource.items():
        if tuple(group["time_block_id"].astype(str)) != block_ids:
            raise ValueError(f"calibration block order differs across resources: {resource_type}")
    successful = set(fit_draws["bootstrap_replication"].astype(int))
    if len(successful) != fit_package.fit.resources[0].bootstrap_succeeded:
        raise ValueError("retained successful bootstrap count differs from the fit")
    if not successful:
        raise ValueError("prediction locking requires at least one successful bootstrap")
    rng = np.random.default_rng(policy.root_seed)
    rows: list[dict[str, object]] = []
    encountered: set[int] = set()
    resource_ids = {
        resource.resource_type: resource.resource_id for resource in fit_package.fit.resources
    }
    for replication in range(policy.bootstrap_replications):
        positions = _circular_block_sample(len(block_ids), policy.bootstrap_block_length, rng)
        sampled_blocks = tuple(block_ids[index] for index in positions)
        sample_digest = _sha256_bytes("\n".join(sampled_blocks).encode("utf-8"))
        if replication not in successful:
            continue
        encountered.add(replication)
        retained = fit_draws[fit_draws["bootstrap_replication"] == replication]
        if len(retained) != len(ResourceType) or set(retained["resource_type"]) != {
            item.value for item in ResourceType
        }:
            raise ValueError("successful fit replication is not a complete ten-resource draw")
        if set(retained["sampled_block_sequence_sha256"]) != {sample_digest}:
            raise ValueError("retained bootstrap sequence differs from deterministic replay")
        for resource_type in ResourceType:
            name = resource_type.value
            candidate = retained[retained["resource_type"] == name].iloc[0]
            sampled = ordered_by_resource[name].iloc[positions].reset_index(drop=True)
            rows.append(
                {
                    "bootstrap_replication": replication,
                    "sampled_block_sequence_sha256": sample_digest,
                    "resource_id": resource_ids[name],
                    "resource_type": name,
                    "candidate_background_work_per_agent_s": float(
                        candidate["background_work_per_agent_s"]
                    ),
                    "candidate_admission_work_units_per_agent": float(
                        candidate["admission_work_units_per_agent"]
                    ),
                    "comparator_background_work_per_agent_s": (
                        _background_only_coefficient(sampled)
                    ),
                }
            )
    if encountered != successful:
        raise ValueError("retained bootstrap replication identifiers exceed the fit request")
    return _canonical_parameter_draws(pd.DataFrame(rows))


def _resource_parameters(
    calibration: pd.DataFrame,
    fit_package: EmpiricalCalibrationPackageVerification,
    adapter_package: AdaptedResourcePackageVerification,
    parameter_draws: pd.DataFrame,
) -> tuple[LockedResourcePredictionParameters, ...]:
    fits = {item.resource_type: item for item in fit_package.fit.resources}
    specs = {item.resource_type.value: item for item in adapter_package.bundle.resources}
    replication_count = int(parameter_draws["bootstrap_replication"].nunique())
    selected: list[LockedResourcePredictionParameters] = []
    for resource_type in sorted(item.value for item in ResourceType):
        fit = fits[resource_type]
        spec = specs[resource_type]
        if fit.gate_status != "passed":
            raise ValueError(f"prediction locking requires a passed fit: {resource_type}")
        if fit.background_work_per_agent_s is None or fit.admission_work_units_per_agent is None:
            raise ValueError(f"prediction locking requires coefficient intervals: {resource_type}")
        if float(spec.background_work_per_agent_s) != float(
            fit.background_work_per_agent_s.point
        ) or float(spec.admission_work_units) != float(fit.admission_work_units_per_agent.point):
            raise ValueError("adapter candidate parameters differ from accepted fit points")
        calibration_resource = calibration[
            calibration["resource_type"].astype(str) == resource_type
        ].sort_values(["timestamp", "time_block_id"], kind="mergesort")
        comparator_point = _background_only_coefficient(calibration_resource)
        comparator_draws = parameter_draws[parameter_draws["resource_type"] == resource_type][
            "comparator_background_work_per_agent_s"
        ].to_numpy(float)
        selected.append(
            LockedResourcePredictionParameters(
                resource_id=fit.resource_id,
                resource_type=resource_type,
                candidate_background_work_per_agent_s=float(spec.background_work_per_agent_s),
                candidate_admission_work_units_per_agent=float(spec.admission_work_units),
                comparator_background_work_per_agent_s=comparator_point,
                comparator_background_interval=_interval(
                    comparator_point,
                    comparator_draws,
                    fit_package.fit.policy.bootstrap_interval_level,
                ),
                paired_bootstrap_replication_count=replication_count,
            )
        )
    return tuple(selected)


def _prediction_rows(
    registration_package: SuccessorRegistrationPackageVerification,
    parameters: tuple[LockedResourcePredictionParameters, ...],
    parameter_draws: pd.DataFrame,
    interval_level: float,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    parameters_by_type = {item.resource_type: item for item in parameters}
    for cell in registration_package.plan.cells:
        for block in cell.planned_blocks:
            duration_s = float(block.window_duration_ms) / 1000.0
            admission_rate = float(block.agents_admitted) / duration_s
            for resource_type in sorted(parameters_by_type):
                parameter = parameters_by_type[resource_type]
                draws = parameter_draws[parameter_draws["resource_type"] == resource_type]
                candidate_rate_draws = (
                    draws["candidate_background_work_per_agent_s"].to_numpy(float)
                    * float(block.fleet_size)
                    + draws["candidate_admission_work_units_per_agent"].to_numpy(float)
                    * admission_rate
                )
                comparator_rate_draws = draws["comparator_background_work_per_agent_s"].to_numpy(
                    float
                ) * float(block.fleet_size)
                candidate_point = (
                    parameter.candidate_background_work_per_agent_s * block.fleet_size
                    + parameter.candidate_admission_work_units_per_agent * admission_rate
                )
                comparator_point = (
                    parameter.comparator_background_work_per_agent_s * block.fleet_size
                )
                candidate_rate = _interval(candidate_point, candidate_rate_draws, interval_level)
                comparator_rate = _interval(comparator_point, comparator_rate_draws, interval_level)
                candidate_count = _interval(
                    candidate_point * duration_s,
                    candidate_rate_draws * duration_s,
                    interval_level,
                )
                comparator_count = _interval(
                    comparator_point * duration_s,
                    comparator_rate_draws * duration_s,
                    interval_level,
                )
                rows.append(
                    {
                        "cell_id": cell.cell_id,
                        "time_block_id": block.time_block_id,
                        "timestamp_utc": block.timestamp_utc,
                        "resource_id": parameter.resource_id,
                        "resource_type": resource_type,
                        "fleet_size": block.fleet_size,
                        "agents_admitted": block.agents_admitted,
                        "window_duration_ms": float(block.window_duration_ms),
                        "admission_rate_per_s": admission_rate,
                        "candidate_mean_arrival_rate_lower_per_s": candidate_rate.lower,
                        "candidate_mean_arrival_rate_point_per_s": candidate_rate.point,
                        "candidate_mean_arrival_rate_upper_per_s": candidate_rate.upper,
                        "candidate_mean_arrival_count_lower": candidate_count.lower,
                        "candidate_mean_arrival_count_point": candidate_count.point,
                        "candidate_mean_arrival_count_upper": candidate_count.upper,
                        "comparator_mean_arrival_rate_lower_per_s": comparator_rate.lower,
                        "comparator_mean_arrival_rate_point_per_s": comparator_rate.point,
                        "comparator_mean_arrival_rate_upper_per_s": comparator_rate.upper,
                        "comparator_mean_arrival_count_lower": comparator_count.lower,
                        "comparator_mean_arrival_count_point": comparator_count.point,
                        "comparator_mean_arrival_count_upper": comparator_count.upper,
                    }
                )
    return _canonical_prediction_rows(pd.DataFrame(rows))


def build_successor_prediction_lock(
    registration_package: SuccessorRegistrationPackageVerification,
    *,
    source_campaign: CampaignPackageVerification,
    fit_package: EmpiricalCalibrationPackageVerification,
    adapter_package: AdaptedResourcePackageVerification,
    committed_at_utc: str | None = None,
) -> SuccessorPredictionLockRun:
    """Build target-free rows from the registered design and calibration chain only."""

    source, fit, adapter, registration = _refresh_upstream_packages(
        source_campaign,
        fit_package,
        adapter_package,
        registration_package,
    )
    _validate_registered_semantics(registration, fit)
    if fit.fit.gate_status != "passed" or not fit.fit.interface_verification_ready:
        raise ValueError("prediction locking requires a fully accepted calibration fit")
    if len(fit.fit.resources) != len(ResourceType) or len(adapter.bundle.resources) != len(
        ResourceType
    ):
        raise ValueError("prediction locking requires exactly ten fit and adapter resources")
    commitment_time = _timestamp(
        committed_at_utc
        if committed_at_utc is not None
        else datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "committed_at_utc",
    )
    if not (
        _timestamp_value(registration.registration.registered_at_utc)
        <= _timestamp_value(commitment_time)
        < _timestamp_value(registration.plan.planned_collection_start_utc)
    ):
        raise ValueError(
            "local prediction commitment must be at or after registration and before collection"
        )
    calibration = source.calibration
    paired_draws = _paired_parameter_draws(calibration, fit)
    parameters = _resource_parameters(calibration, fit, adapter, paired_draws)
    prediction_rows = _prediction_rows(
        registration,
        parameters,
        paired_draws,
        fit.fit.policy.bootstrap_interval_level,
    )
    planned_blocks = sum(len(cell.planned_blocks) for cell in registration.plan.cells)
    if len(prediction_rows) != planned_blocks * len(ResourceType):
        raise ValueError("prediction rows do not cover the exact registered design")
    implementation = _implementation_record()
    visible_implementation = [{"path": path, "sha256": digest} for path, digest in implementation]
    implementation_sha256 = _sha256_bytes(_canonical_json_bytes(visible_implementation))
    contract = registration.contract
    values: dict[str, object] = {
        "schema_version": PREDICTION_LOCK_SCHEMA_VERSION,
        "committed_at_utc": commitment_time,
        "registration_id": registration.registration.registration_id,
        "registration_manifest_sha256": registration.registration_manifest_sha256,
        "registration_mode": registration.registration.registration_mode,
        "source_campaign_id": registration.registration.source_campaign_id,
        "source_campaign_evidence_manifest_sha256": source.evidence_manifest_sha256,
        "source_calibration_content_sha256": (
            registration.registration.source_calibration_content_sha256
        ),
        "source_historical_heldout_used_for_prediction": False,
        "calibration_fit_id": fit.fit.calibration_fit_id,
        "candidate_model_id": contract.candidate.model_id,
        "fit_policy_sha256": fit.fit.policy_sha256,
        "fit_evidence_manifest_sha256": fit.fit_evidence_manifest_sha256,
        "fit_bootstrap_draws_content_sha256": (
            _fit_bootstrap_draws_content_sha256(fit.bootstrap_draws)
        ),
        "adapter_bundle_id": adapter.bundle.adapter_bundle_id,
        "adapter_policy_sha256": adapter.bundle.adapter_policy_sha256,
        "adapter_manifest_sha256": adapter.adapter_manifest_sha256,
        "adapter_specification_sha256": adapter.bundle.specification_sha256,
        "plan_sha256": registration.registration.plan_sha256,
        "transfer_contract_sha256": registration.registration.transfer_contract_sha256,
        "planned_evaluation_campaign_id": (
            registration.registration.planned_evaluation_campaign_id
        ),
        "planned_cell_count": len(registration.plan.cells),
        "planned_time_block_count": planned_blocks,
        "resource_count": len(ResourceType),
        "prediction_row_count": len(prediction_rows),
        "paired_bootstrap_replication_count": int(paired_draws["bootstrap_replication"].nunique()),
        "prediction_rows_content_sha256": _frame_content_sha256(
            prediction_rows, PREDICTION_ROW_COLUMNS
        ),
        "prediction_parameter_draws_content_sha256": _frame_content_sha256(
            paired_draws, PREDICTION_PARAMETER_DRAW_COLUMNS
        ),
        "candidate_formula": contract.candidate.formula,
        "comparator_model_id": contract.comparator.model_id,
        "comparator_formula": contract.comparator.formula,
        "uncertainty_method": contract.uncertainty.method,
        "uncertainty_scope": contract.uncertainty.scope,
        "bootstrap_interval_level": fit.fit.policy.bootstrap_interval_level,
        "bootstrap_quantile_method": contract.uncertainty.quantile_method,
        "resource_parameters": parameters,
        "implementation": implementation,
        "implementation_sha256": implementation_sha256,
        "upstream_chain_verified": True,
        "registered_semantics_reconciled": True,
        "planned_predictor_design_reconciled": True,
        "prediction_formula_frozen": True,
        "comparator_formula_frozen": True,
        "future_evaluation_campaign_not_supplied": True,
        "prediction_rows_target_free": True,
        "local_lock_chronology_consistent": True,
        "workflow_prediction_commitment": True,
        "prediction_lock_time_externally_attested": False,
        "prediction_rows_preoutcome_locked": False,
        "outcome_release_custody_verified": False,
        "execution_chain_ready": False,
        "external_validation": False,
        "scientific_use_authorized": False,
        "runner_authorized": False,
    }
    identity_payload = dict(values)
    identity_payload["resource_parameters"] = [item.to_dict() for item in parameters]
    identity_payload["implementation"] = visible_implementation
    identity = _sha256_bytes(_canonical_json_bytes(identity_payload))[:20]
    lock = SuccessorPredictionLock(
        prediction_lock_id=f"successor-prediction-lock-{identity}",
        **values,  # type: ignore[arg-type]
    )
    return SuccessorPredictionLockRun(
        lock=lock,
        _prediction_rows=prediction_rows.copy(deep=True),
        _parameter_draws=paired_draws.copy(deep=True),
    )


def _lock_from_mapping(value: object) -> SuccessorPredictionLock:
    selected = _exact_keys(value, set(SuccessorPredictionLock.__dataclass_fields__), "lock")
    raw_parameters = selected["resource_parameters"]
    if not isinstance(raw_parameters, list):
        raise TypeError("resource_parameters must be an array")
    raw_implementation = selected["implementation"]
    if not isinstance(raw_implementation, list):
        raise TypeError("implementation must be an array")
    implementation: list[tuple[str, str]] = []
    for raw in raw_implementation:
        record = _exact_keys(raw, {"path", "sha256"}, "implementation record")
        implementation.append(
            (
                _string(record["path"], "implementation path"),
                _sha256(record["sha256"], "implementation hash"),
            )
        )
    return SuccessorPredictionLock(
        schema_version=_string(selected["schema_version"], "schema_version"),
        prediction_lock_id=_identifier(selected["prediction_lock_id"], "prediction_lock_id"),
        committed_at_utc=_string(selected["committed_at_utc"], "committed_at_utc"),
        registration_id=_identifier(selected["registration_id"], "registration_id"),
        registration_manifest_sha256=_sha256(
            selected["registration_manifest_sha256"], "registration manifest hash"
        ),
        registration_mode=_string(selected["registration_mode"], "registration_mode"),
        source_campaign_id=_identifier(selected["source_campaign_id"], "source_campaign_id"),
        source_campaign_evidence_manifest_sha256=_sha256(
            selected["source_campaign_evidence_manifest_sha256"], "source campaign hash"
        ),
        source_calibration_content_sha256=_sha256(
            selected["source_calibration_content_sha256"], "calibration content hash"
        ),
        source_historical_heldout_used_for_prediction=_strict_bool(
            selected["source_historical_heldout_used_for_prediction"],
            "historical heldout used for prediction",
        ),
        calibration_fit_id=_identifier(selected["calibration_fit_id"], "calibration_fit_id"),
        candidate_model_id=_string(selected["candidate_model_id"], "candidate_model_id"),
        fit_policy_sha256=_sha256(selected["fit_policy_sha256"], "fit policy hash"),
        fit_evidence_manifest_sha256=_sha256(
            selected["fit_evidence_manifest_sha256"], "fit evidence hash"
        ),
        fit_bootstrap_draws_content_sha256=_sha256(
            selected["fit_bootstrap_draws_content_sha256"], "fit bootstrap content hash"
        ),
        adapter_bundle_id=_identifier(selected["adapter_bundle_id"], "adapter_bundle_id"),
        adapter_policy_sha256=_sha256(selected["adapter_policy_sha256"], "adapter policy hash"),
        adapter_manifest_sha256=_sha256(
            selected["adapter_manifest_sha256"], "adapter manifest hash"
        ),
        adapter_specification_sha256=_sha256(
            selected["adapter_specification_sha256"], "adapter specification hash"
        ),
        plan_sha256=_sha256(selected["plan_sha256"], "plan hash"),
        transfer_contract_sha256=_sha256(
            selected["transfer_contract_sha256"], "transfer contract hash"
        ),
        planned_evaluation_campaign_id=_identifier(
            selected["planned_evaluation_campaign_id"], "planned evaluation campaign ID"
        ),
        planned_cell_count=_integer(
            selected["planned_cell_count"], "planned cell count", minimum=1
        ),
        planned_time_block_count=_integer(
            selected["planned_time_block_count"], "planned time-block count", minimum=1
        ),
        resource_count=_integer(selected["resource_count"], "resource count", minimum=1),
        prediction_row_count=_integer(
            selected["prediction_row_count"], "prediction row count", minimum=1
        ),
        paired_bootstrap_replication_count=_integer(
            selected["paired_bootstrap_replication_count"],
            "paired bootstrap replication count",
            minimum=1,
        ),
        prediction_rows_content_sha256=_sha256(
            selected["prediction_rows_content_sha256"], "prediction rows hash"
        ),
        prediction_parameter_draws_content_sha256=_sha256(
            selected["prediction_parameter_draws_content_sha256"],
            "prediction parameter draws hash",
        ),
        candidate_formula=_string(selected["candidate_formula"], "candidate formula"),
        comparator_model_id=_string(selected["comparator_model_id"], "comparator model_id"),
        comparator_formula=_string(selected["comparator_formula"], "comparator formula"),
        uncertainty_method=_string(selected["uncertainty_method"], "uncertainty method"),
        uncertainty_scope=_string(selected["uncertainty_scope"], "uncertainty scope"),
        bootstrap_interval_level=_finite(
            selected["bootstrap_interval_level"], "bootstrap interval level"
        ),
        bootstrap_quantile_method=_string(
            selected["bootstrap_quantile_method"], "bootstrap quantile method"
        ),
        resource_parameters=tuple(
            LockedResourcePredictionParameters.from_mapping(item) for item in raw_parameters
        ),
        implementation=tuple(implementation),
        implementation_sha256=_sha256(selected["implementation_sha256"], "implementation hash"),
        upstream_chain_verified=_strict_bool(
            selected["upstream_chain_verified"], "upstream chain verified"
        ),
        registered_semantics_reconciled=_strict_bool(
            selected["registered_semantics_reconciled"], "registered semantics reconciled"
        ),
        planned_predictor_design_reconciled=_strict_bool(
            selected["planned_predictor_design_reconciled"],
            "planned predictor design reconciled",
        ),
        prediction_formula_frozen=_strict_bool(
            selected["prediction_formula_frozen"], "prediction formula frozen"
        ),
        comparator_formula_frozen=_strict_bool(
            selected["comparator_formula_frozen"], "comparator formula frozen"
        ),
        future_evaluation_campaign_not_supplied=_strict_bool(
            selected["future_evaluation_campaign_not_supplied"],
            "future evaluation campaign not supplied",
        ),
        prediction_rows_target_free=_strict_bool(
            selected["prediction_rows_target_free"], "prediction rows target free"
        ),
        local_lock_chronology_consistent=_strict_bool(
            selected["local_lock_chronology_consistent"], "local lock chronology consistent"
        ),
        workflow_prediction_commitment=_strict_bool(
            selected["workflow_prediction_commitment"], "workflow prediction commitment"
        ),
        prediction_lock_time_externally_attested=_strict_bool(
            selected["prediction_lock_time_externally_attested"],
            "prediction lock time externally attested",
        ),
        prediction_rows_preoutcome_locked=_strict_bool(
            selected["prediction_rows_preoutcome_locked"], "prediction rows preoutcome locked"
        ),
        outcome_release_custody_verified=_strict_bool(
            selected["outcome_release_custody_verified"], "outcome release custody verified"
        ),
        execution_chain_ready=_strict_bool(
            selected["execution_chain_ready"], "execution chain ready"
        ),
        external_validation=_strict_bool(selected["external_validation"], "external validation"),
        scientific_use_authorized=_strict_bool(
            selected["scientific_use_authorized"], "scientific use authorized"
        ),
        runner_authorized=_strict_bool(selected["runner_authorized"], "runner authorized"),
    )


def _closed_schema_object(
    properties: Mapping[str, object],
    *,
    title: str | None = None,
) -> dict[str, object]:
    schema: dict[str, object] = {
        "type": "object",
        "required": sorted(properties),
        "properties": dict(properties),
        "additionalProperties": False,
    }
    if title is not None:
        schema["title"] = title
    return schema


def _digest_schema() -> dict[str, object]:
    return {"type": "string", "pattern": "^[0-9a-f]{64}$"}


def _identifier_schema() -> dict[str, object]:
    return {
        "type": "string",
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$",
    }


def _timestamp_schema() -> dict[str, object]:
    return {
        "type": "string",
        "pattern": (
            r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:"
            r"[0-9]{2}\.[0-9]{6}Z$"
        ),
    }


def successor_prediction_rows_schema() -> dict[str, object]:
    """Return the closed schema for one target-free prediction row."""

    nonnegative = {"type": "number", "minimum": 0.0}
    properties: dict[str, object] = {
        "cell_id": _identifier_schema(),
        "time_block_id": _identifier_schema(),
        "timestamp_utc": _timestamp_schema(),
        "resource_id": {"type": "string", "minLength": 1, "maxLength": 256},
        "resource_type": {"enum": sorted(item.value for item in ResourceType)},
        "fleet_size": {"type": "integer", "minimum": 1},
        "agents_admitted": {"type": "integer", "minimum": 0},
        "window_duration_ms": {"type": "number", "exclusiveMinimum": 0.0},
        "admission_rate_per_s": nonnegative,
    }
    properties.update(
        {name: nonnegative for name in PREDICTION_ROW_COLUMNS if name not in properties}
    )
    schema = _closed_schema_object(properties, title="Target-free successor prediction row")
    schema.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://fleet-assurance.local/schemas/successor_prediction_rows.schema.json",
        }
    )
    return schema


def successor_prediction_parameter_draws_schema() -> dict[str, object]:
    """Return the closed schema for one paired prediction-parameter draw."""

    schema = _closed_schema_object(
        {
            "bootstrap_replication": {"type": "integer", "minimum": 0},
            "sampled_block_sequence_sha256": _digest_schema(),
            "resource_id": {"type": "string", "minLength": 1, "maxLength": 256},
            "resource_type": {"enum": sorted(item.value for item in ResourceType)},
            "candidate_background_work_per_agent_s": {
                "type": "number",
                "minimum": 0.0,
            },
            "candidate_admission_work_units_per_agent": {
                "type": "number",
                "minimum": 0.0,
            },
            "comparator_background_work_per_agent_s": {
                "type": "number",
                "minimum": 0.0,
            },
        },
        title="Paired successor prediction-parameter bootstrap draw",
    )
    schema.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": (
                "https://fleet-assurance.local/schemas/"
                "successor_prediction_parameter_draws.schema.json"
            ),
        }
    )
    return schema


def successor_prediction_lock_schema() -> dict[str, object]:
    """Return the closed prediction-lock metadata schema."""

    interval = _closed_schema_object(
        {
            "lower": {"type": "number", "minimum": 0.0},
            "point": {"type": "number", "minimum": 0.0},
            "upper": {"type": "number", "minimum": 0.0},
        }
    )
    resource_parameters = _closed_schema_object(
        {
            "resource_id": {"type": "string", "minLength": 1, "maxLength": 256},
            "resource_type": {"enum": sorted(item.value for item in ResourceType)},
            "candidate_background_work_per_agent_s": {
                "type": "number",
                "minimum": 0.0,
            },
            "candidate_admission_work_units_per_agent": {
                "type": "number",
                "exclusiveMinimum": 0.0,
            },
            "comparator_background_work_per_agent_s": {
                "type": "number",
                "minimum": 0.0,
            },
            "comparator_background_interval": interval,
            "paired_bootstrap_replication_count": {"type": "integer", "minimum": 1},
        }
    )
    implementation_record = _closed_schema_object(
        {
            "path": {
                "type": "string",
                "minLength": 1,
                "maxLength": 256,
                "pattern": (
                    r"^(?![A-Za-z]:)(?![/~])(?!.*(?:^|/)\.\.(?:/|$))"
                    r"[A-Za-z0-9._/-]+$"
                ),
            },
            "sha256": _digest_schema(),
        }
    )
    identifier_fields = {
        "registration_id",
        "source_campaign_id",
        "calibration_fit_id",
        "adapter_bundle_id",
        "planned_evaluation_campaign_id",
    }
    digest_fields = {
        "registration_manifest_sha256",
        "source_campaign_evidence_manifest_sha256",
        "source_calibration_content_sha256",
        "fit_policy_sha256",
        "fit_evidence_manifest_sha256",
        "fit_bootstrap_draws_content_sha256",
        "adapter_policy_sha256",
        "adapter_manifest_sha256",
        "adapter_specification_sha256",
        "plan_sha256",
        "transfer_contract_sha256",
        "prediction_rows_content_sha256",
        "prediction_parameter_draws_content_sha256",
        "implementation_sha256",
    }
    properties: dict[str, object] = {name: _identifier_schema() for name in identifier_fields}
    properties.update({name: _digest_schema() for name in digest_fields})
    properties.update(
        {
            "schema_version": {"const": PREDICTION_LOCK_SCHEMA_VERSION},
            "prediction_lock_id": {
                "type": "string",
                "pattern": "^successor-prediction-lock-[0-9a-f]{20}$",
            },
            "committed_at_utc": _timestamp_schema(),
            "registration_mode": {"enum": ["engineering_dry_run", "prospective_transfer"]},
            "source_historical_heldout_used_for_prediction": {"const": False},
            "candidate_model_id": {"const": CANDIDATE_MODEL_ID},
            "planned_cell_count": {"type": "integer", "minimum": 1},
            "planned_time_block_count": {"type": "integer", "minimum": 1},
            "resource_count": {"const": len(ResourceType)},
            "prediction_row_count": {"type": "integer", "minimum": len(ResourceType)},
            "paired_bootstrap_replication_count": {"type": "integer", "minimum": 1},
            "candidate_formula": {"const": PREDICTION_FORMULA},
            "comparator_model_id": {"const": COMPARATOR},
            "comparator_formula": {"const": COMPARATOR_FORMULA},
            "uncertainty_method": {"const": UNCERTAINTY_METHOD},
            "uncertainty_scope": {"const": UNCERTAINTY_SCOPE},
            "bootstrap_interval_level": {
                "type": "number",
                "exclusiveMinimum": 0.5,
                "exclusiveMaximum": 1.0,
            },
            "bootstrap_quantile_method": {"const": UNCERTAINTY_QUANTILE_METHOD},
            "resource_parameters": {
                "type": "array",
                "minItems": len(ResourceType),
                "maxItems": len(ResourceType),
                "items": resource_parameters,
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
            "implementation": {
                "type": "array",
                "minItems": 6,
                "maxItems": 6,
                "uniqueItems": True,
                "items": implementation_record,
            },
            "upstream_chain_verified": {"const": True},
            "registered_semantics_reconciled": {"const": True},
            "planned_predictor_design_reconciled": {"const": True},
            "prediction_formula_frozen": {"const": True},
            "comparator_formula_frozen": {"const": True},
            "future_evaluation_campaign_not_supplied": {"const": True},
            "prediction_rows_target_free": {"const": True},
            "local_lock_chronology_consistent": {"const": True},
            "workflow_prediction_commitment": {"const": True},
            "prediction_lock_time_externally_attested": {"const": False},
            "prediction_rows_preoutcome_locked": {"const": False},
            "outcome_release_custody_verified": {"const": False},
            "execution_chain_ready": {"const": False},
            "external_validation": {"const": False},
            "scientific_use_authorized": {"const": False},
            "runner_authorized": {"const": False},
        }
    )
    schema = _closed_schema_object(properties, title="Successor target-free prediction lock")
    schema.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://fleet-assurance.local/schemas/successor_prediction_lock.schema.json",
        }
    )
    return schema


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _artifact_record(path: Path) -> dict[str, object]:
    return {
        "path": path.name,
        "bytes": path.stat().st_size,
        "sha256": _sha256_path(path),
    }


def _prediction_lock_manifest(
    lock: SuccessorPredictionLock,
    artifacts: Sequence[Path],
) -> dict[str, object]:
    manifest: dict[str, object] = {
        "schema_version": PREDICTION_LOCK_SCHEMA_VERSION,
        "package_type": "successor_prediction_lock",
        "prediction_lock_id": lock.prediction_lock_id,
        "future_evaluation_campaign_not_supplied": True,
        "prediction_rows_target_free": True,
        "local_lock_chronology_consistent": True,
        "workflow_prediction_commitment": True,
        "prediction_lock_time_externally_attested": False,
        "prediction_rows_preoutcome_locked": False,
        "outcome_release_custody_verified": False,
        "execution_chain_ready": False,
        "external_validation": False,
        "scientific_use_authorized": False,
        "runner_authorized": False,
        "artifacts": [_artifact_record(path) for path in artifacts],
    }
    manifest["self_integrity_sha256"] = _sha256_bytes(_canonical_json_bytes(manifest))
    return manifest


def _assert_output_outside_sources(destination: Path, sources: Sequence[Path]) -> None:
    resolved = destination.resolve(strict=False)
    for source in sources:
        root = source.resolve()
        if resolved == root or root in resolved.parents:
            raise ValueError("prediction-lock output must be outside every source package")


def _rename_noreplace(source: Path, destination: Path) -> None:
    """Atomically publish a directory without replacing a competing path."""

    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    if sys.platform == "darwin":
        libc = CDLL(None, use_errno=True)
        try:
            renamex = libc.renamex_np
        except AttributeError as exc:
            raise RuntimeError(
                "this platform lacks atomic no-replace directory publication"
            ) from exc
        renamex.argtypes = (c_char_p, c_char_p, c_uint)
        renamex.restype = c_int
        result = renamex(source_bytes, destination_bytes, 0x00000004)
    elif sys.platform.startswith("linux"):
        libc = CDLL(None, use_errno=True)
        try:
            renameat2 = libc.renameat2
        except AttributeError as exc:
            raise RuntimeError(
                "this platform lacks atomic no-replace directory publication"
            ) from exc
        renameat2.argtypes = (c_int, c_char_p, c_int, c_char_p, c_uint)
        renameat2.restype = c_int
        result = renameat2(-100, source_bytes, -100, destination_bytes, 0x00000001)
    elif os.name == "nt":
        os.rename(source, destination)
        return
    else:
        raise RuntimeError("this platform lacks atomic no-replace directory publication")
    if result == 0:
        return
    error = get_errno()
    if error in {EEXIST, ENOTEMPTY}:
        raise FileExistsError(error, "refusing to overwrite prediction-lock package", destination)
    raise OSError(error, os.strerror(error), destination)


def _write_atomic_package(destination: Path, build: Any) -> Path:
    if os.path.lexists(destination):
        raise FileExistsError(f"refusing to overwrite prediction-lock package: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock_path = destination.parent / f".{destination.name}.prediction-lock.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise FileExistsError(f"prediction-lock package is locked: {destination}") from exc
    temporary: Path | None = None
    try:
        if os.path.lexists(destination):
            raise FileExistsError(f"refusing to overwrite prediction-lock package: {destination}")
        temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
        build(temporary)
        entries = list(temporary.iterdir())
        if {path.name for path in entries} != PREDICTION_LOCK_PACKAGE_FILES or any(
            path.is_symlink() or not path.is_file() for path in entries
        ):
            raise RuntimeError("prediction-lock package construction is incomplete")
        if os.path.lexists(destination):
            raise FileExistsError(f"refusing to overwrite prediction-lock package: {destination}")
        _rename_noreplace(temporary, destination)
        temporary = None
        return destination
    except Exception:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)
        raise
    finally:
        os.close(descriptor)
        lock_path.unlink(missing_ok=True)


def _read_bounded_file(path: Path, maximum_bytes: int) -> bytes:
    if maximum_bytes <= 0:
        raise ValueError("maximum_bytes must be positive")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"cannot safely open prediction-lock artifact: {path.name}") from exc
    chunks: list[bytes] = []
    total = 0
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"prediction-lock artifact is not a regular file: {path.name}")
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            total += len(chunk)
            if total > maximum_bytes:
                raise ValueError("prediction-lock package exceeds the byte limit")
            chunks.append(chunk)
        after = os.fstat(stream.fileno())
    stable = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(getattr(before, name) != getattr(after, name) for name in stable):
        raise ValueError(f"prediction-lock artifact changed while read: {path.name}")
    if total != after.st_size:
        raise ValueError(f"prediction-lock artifact size changed while read: {path.name}")
    return b"".join(chunks)


def _snapshot_package(
    package: Path,
    *,
    expected_manifest_sha256: str | None,
    maximum_package_bytes: int,
) -> dict[str, bytes]:
    if maximum_package_bytes <= 0:
        raise ValueError("maximum_package_bytes must be positive")
    if package.is_symlink():
        raise ValueError("prediction-lock package cannot be a symlink")
    if not package.is_dir():
        raise FileNotFoundError(package)
    entries = list(package.iterdir())
    if {entry.name for entry in entries} != PREDICTION_LOCK_PACKAGE_FILES:
        raise ValueError("prediction-lock package file set mismatch")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise ValueError("prediction-lock package entries must be regular local files")
    manifest_name = "prediction_lock_manifest.json"
    manifest = _read_bounded_file(package / manifest_name, maximum_package_bytes)
    if expected_manifest_sha256 is not None and _sha256_bytes(manifest) != _sha256(
        expected_manifest_sha256,
        "expected prediction-lock manifest hash",
    ):
        raise ValueError("prediction-lock manifest differs from the externally supplied digest")
    retained = {manifest_name: manifest}
    remaining = maximum_package_bytes - len(manifest)
    for name in sorted(PREDICTION_LOCK_PACKAGE_FILES - {manifest_name}):
        artifact = _read_bounded_file(package / name, remaining)
        retained[name] = artifact
        remaining -= len(artifact)
    final_entries = list(package.iterdir())
    if {entry.name for entry in final_entries} != PREDICTION_LOCK_PACKAGE_FILES or any(
        entry.is_symlink() or not entry.is_file() for entry in final_entries
    ):
        raise ValueError("prediction-lock package changed while being read")
    return retained


def _verify_manifest(
    manifest: Mapping[str, object],
    package_bytes: Mapping[str, bytes],
    prediction_lock_id: str | None,
) -> None:
    expected_fields = {
        "schema_version",
        "package_type",
        "prediction_lock_id",
        "future_evaluation_campaign_not_supplied",
        "prediction_rows_target_free",
        "local_lock_chronology_consistent",
        "workflow_prediction_commitment",
        "prediction_lock_time_externally_attested",
        "prediction_rows_preoutcome_locked",
        "outcome_release_custody_verified",
        "execution_chain_ready",
        "external_validation",
        "scientific_use_authorized",
        "runner_authorized",
        "artifacts",
        "self_integrity_sha256",
    }
    selected = _exact_keys(manifest, expected_fields, "prediction-lock manifest")
    if selected["schema_version"] != PREDICTION_LOCK_SCHEMA_VERSION:
        raise ValueError("prediction-lock manifest schema version differs")
    if selected["package_type"] != "successor_prediction_lock":
        raise ValueError("prediction-lock manifest package type differs")
    retained_id = _identifier(selected["prediction_lock_id"], "manifest prediction_lock_id")
    if prediction_lock_id is not None and retained_id != prediction_lock_id:
        raise ValueError("prediction-lock manifest identity differs")
    for field in (
        "future_evaluation_campaign_not_supplied",
        "prediction_rows_target_free",
        "local_lock_chronology_consistent",
        "workflow_prediction_commitment",
    ):
        if selected[field] is not True:
            raise ValueError(f"prediction-lock manifest must assert {field}")
    for field in (
        "prediction_lock_time_externally_attested",
        "prediction_rows_preoutcome_locked",
        "outcome_release_custody_verified",
        "execution_chain_ready",
        "external_validation",
        "scientific_use_authorized",
        "runner_authorized",
    ):
        if selected[field] is not False:
            raise ValueError(f"prediction-lock manifest cannot assert {field}")
    asserted_self = _sha256(selected["self_integrity_sha256"], "manifest self hash")
    without_self = dict(manifest)
    del without_self["self_integrity_sha256"]
    if asserted_self != _sha256_bytes(_canonical_json_bytes(without_self)):
        raise ValueError("prediction-lock manifest self-integrity hash mismatch")
    expected_artifacts = PREDICTION_LOCK_PACKAGE_FILES - {"prediction_lock_manifest.json"}
    records = selected["artifacts"]
    if not isinstance(records, list) or len(records) != len(expected_artifacts):
        raise ValueError("prediction-lock artifact inventory is incomplete")
    names: set[str] = set()
    for record in records:
        item = _exact_keys(record, {"path", "bytes", "sha256"}, "prediction-lock artifact")
        name = item["path"]
        if (
            not isinstance(name, str)
            or name != Path(name).name
            or name not in expected_artifacts
            or name in names
        ):
            raise ValueError("prediction-lock artifact path is invalid or duplicated")
        names.add(name)
        byte_count = _integer(item["bytes"], f"artifact bytes for {name}")
        if byte_count != len(package_bytes[name]):
            raise ValueError(f"prediction-lock artifact size mismatch: {name}")
        if _sha256(item["sha256"], f"artifact hash for {name}") != _sha256_bytes(
            package_bytes[name]
        ):
            raise ValueError(f"prediction-lock artifact hash mismatch: {name}")
    if names != expected_artifacts:
        raise ValueError("prediction-lock artifact inventory does not cover the package")


def _read_parquet_frames(
    package_bytes: Mapping[str, bytes],
    *,
    maximum_rows: int,
    maximum_uncompressed_bytes: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if maximum_rows <= 0 or maximum_uncompressed_bytes <= 0:
        raise ValueError("Parquet verification limits must be positive")
    try:
        import pyarrow.parquet
    except ImportError as exc:
        raise RuntimeError("prediction-lock verification requires pyarrow") from exc
    names = ("prediction_rows.parquet", "prediction_parameter_draws.parquet")
    metadata = [
        pyarrow.parquet.ParquetFile(io.BytesIO(package_bytes[name])).metadata for name in names
    ]
    if sum(item.num_rows for item in metadata) > maximum_rows:
        raise ValueError("prediction-lock package exceeds the row verification limit")
    uncompressed = sum(
        item.row_group(index).total_byte_size
        for item in metadata
        for index in range(item.num_row_groups)
    )
    if uncompressed > maximum_uncompressed_bytes:
        raise ValueError("prediction-lock package exceeds the uncompressed-byte limit")
    return (
        _canonical_prediction_rows(
            pd.read_parquet(io.BytesIO(package_bytes["prediction_rows.parquet"]))
        ),
        _canonical_parameter_draws(
            pd.read_parquet(io.BytesIO(package_bytes["prediction_parameter_draws.parquet"]))
        ),
    )


def write_successor_prediction_lock_package(
    run: SuccessorPredictionLockRun,
    output_dir: str | Path,
    *,
    registration_package: SuccessorRegistrationPackageVerification,
    source_campaign: CampaignPackageVerification,
    fit_package: EmpiricalCalibrationPackageVerification,
    adapter_package: AdaptedResourcePackageVerification,
) -> Path:
    """Write an immutable, checksum-bound seven-file prediction commitment."""

    recomputed = build_successor_prediction_lock(
        registration_package,
        source_campaign=source_campaign,
        fit_package=fit_package,
        adapter_package=adapter_package,
        committed_at_utc=run.lock.committed_at_utc,
    )
    if run.lock.to_dict() != recomputed.lock.to_dict():
        raise ValueError("prediction lock differs from deterministic upstream recomputation")
    for retained, expected, context in (
        (run.prediction_rows, recomputed.prediction_rows, "prediction rows"),
        (run.parameter_draws, recomputed.parameter_draws, "prediction parameter draws"),
    ):
        try:
            pd.testing.assert_frame_equal(retained, expected, check_exact=True, check_dtype=True)
        except AssertionError as exc:
            raise ValueError(f"{context} differ from deterministic recomputation") from exc
    destination = Path(output_dir)
    _assert_output_outside_sources(
        destination,
        (
            source_campaign.package_dir,
            fit_package.package_dir,
            adapter_package.package_dir,
            registration_package.package_dir,
        ),
    )

    def build(temporary: Path) -> None:
        lock_path = temporary / "prediction_lock.json"
        lock_schema_path = temporary / "prediction_lock_schema.json"
        rows_path = temporary / "prediction_rows.parquet"
        rows_schema_path = temporary / "prediction_rows_schema.json"
        draws_path = temporary / "prediction_parameter_draws.parquet"
        draws_schema_path = temporary / "prediction_parameter_draws_schema.json"
        manifest_path = temporary / "prediction_lock_manifest.json"
        _write_json(lock_path, run.lock.to_dict())
        _write_json(lock_schema_path, successor_prediction_lock_schema())
        _canonical_prediction_rows(run.prediction_rows).to_parquet(rows_path, index=False)
        _write_json(rows_schema_path, successor_prediction_rows_schema())
        _canonical_parameter_draws(run.parameter_draws).to_parquet(draws_path, index=False)
        _write_json(draws_schema_path, successor_prediction_parameter_draws_schema())
        artifacts = (
            lock_path,
            lock_schema_path,
            rows_path,
            rows_schema_path,
            draws_path,
            draws_schema_path,
        )
        _write_json(manifest_path, _prediction_lock_manifest(run.lock, artifacts))
        digest = _sha256_path(manifest_path)
        verify_successor_prediction_lock_package(
            temporary,
            registration_package=registration_package,
            source_campaign=source_campaign,
            fit_package=fit_package,
            adapter_package=adapter_package,
            expected_prediction_lock_manifest_sha256=digest,
        )

    return _write_atomic_package(destination, build)


def verify_successor_prediction_lock_package(
    package_dir: str | Path,
    *,
    registration_package: SuccessorRegistrationPackageVerification,
    source_campaign: CampaignPackageVerification,
    fit_package: EmpiricalCalibrationPackageVerification,
    adapter_package: AdaptedResourcePackageVerification,
    expected_prediction_lock_manifest_sha256: str | None = None,
    maximum_package_bytes: int = _MAX_PACKAGE_BYTES,
    maximum_rows: int = _MAX_ROWS,
    maximum_uncompressed_bytes: int = _MAX_UNCOMPRESSED_BYTES,
) -> SuccessorPredictionLockPackageVerification:
    """Verify and exactly recompute a target-free prediction-lock package."""

    package = Path(package_dir)
    package_bytes = _snapshot_package(
        package,
        expected_manifest_sha256=expected_prediction_lock_manifest_sha256,
        maximum_package_bytes=maximum_package_bytes,
    )
    manifest = _read_json_bytes(
        package_bytes["prediction_lock_manifest.json"], "prediction_lock_manifest.json"
    )
    _verify_manifest(manifest, package_bytes, None)
    retained_lock_schema = _read_json_bytes(
        package_bytes["prediction_lock_schema.json"], "prediction_lock_schema.json"
    )
    retained_rows_schema = _read_json_bytes(
        package_bytes["prediction_rows_schema.json"], "prediction_rows_schema.json"
    )
    retained_draws_schema = _read_json_bytes(
        package_bytes["prediction_parameter_draws_schema.json"],
        "prediction_parameter_draws_schema.json",
    )
    if retained_lock_schema != successor_prediction_lock_schema():
        raise ValueError("retained prediction-lock schema differs from implementation")
    if retained_rows_schema != successor_prediction_rows_schema():
        raise ValueError("retained prediction-row schema differs from implementation")
    if retained_draws_schema != successor_prediction_parameter_draws_schema():
        raise ValueError("retained prediction-parameter schema differs from implementation")
    lock = _lock_from_mapping(
        _read_json_bytes(package_bytes["prediction_lock.json"], "prediction_lock.json")
    )
    if manifest["prediction_lock_id"] != lock.prediction_lock_id:
        raise ValueError("prediction-lock manifest identity differs from lock metadata")
    prediction_rows, parameter_draws = _read_parquet_frames(
        package_bytes,
        maximum_rows=maximum_rows,
        maximum_uncompressed_bytes=maximum_uncompressed_bytes,
    )
    if len(prediction_rows) != lock.prediction_row_count:
        raise ValueError("retained prediction-row count differs from lock metadata")
    if prediction_rows["time_block_id"].nunique() != lock.planned_time_block_count:
        raise ValueError("retained prediction blocks differ from lock metadata")
    if prediction_rows["cell_id"].nunique() != lock.planned_cell_count:
        raise ValueError("retained prediction cells differ from lock metadata")
    if parameter_draws["bootstrap_replication"].nunique() != (
        lock.paired_bootstrap_replication_count
    ):
        raise ValueError("retained paired-bootstrap count differs from lock metadata")
    if _frame_content_sha256(prediction_rows, PREDICTION_ROW_COLUMNS) != (
        lock.prediction_rows_content_sha256
    ):
        raise ValueError("retained prediction-row semantic digest differs")
    if _frame_content_sha256(parameter_draws, PREDICTION_PARAMETER_DRAW_COLUMNS) != (
        lock.prediction_parameter_draws_content_sha256
    ):
        raise ValueError("retained prediction-parameter semantic digest differs")
    recomputed = build_successor_prediction_lock(
        registration_package,
        source_campaign=source_campaign,
        fit_package=fit_package,
        adapter_package=adapter_package,
        committed_at_utc=lock.committed_at_utc,
    )
    if lock.to_dict() != recomputed.lock.to_dict():
        raise ValueError("prediction lock differs from deterministic upstream recomputation")
    for retained, expected, context in (
        (prediction_rows, recomputed.prediction_rows, "prediction rows"),
        (parameter_draws, recomputed.parameter_draws, "prediction parameter draws"),
    ):
        try:
            pd.testing.assert_frame_equal(retained, expected, check_exact=True, check_dtype=True)
        except AssertionError as exc:
            raise ValueError(f"retained {context} differ from deterministic recomputation") from exc
    return SuccessorPredictionLockPackageVerification(
        package_dir=package.resolve(),
        lock=lock,
        _prediction_rows=prediction_rows.copy(deep=True),
        _parameter_draws=parameter_draws.copy(deep=True),
        prediction_lock_manifest_sha256=_sha256_bytes(
            package_bytes["prediction_lock_manifest.json"]
        ),
        externally_digest_bound=expected_prediction_lock_manifest_sha256 is not None,
    )
