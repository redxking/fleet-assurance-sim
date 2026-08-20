"""Two-manifest foundation for a prospective successor transfer study.

The first manifest freezes a transfer contract and a distinct future evaluation
campaign before that campaign begins. The second binds realized campaign inputs
back to the frozen registration. Neither manifest authorizes execution, proves
when a local file was created, authenticates an external party, or establishes
external validation.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
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
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from errno import EEXIST, ENOTEMPTY
from pathlib import Path
from typing import Any, Literal

from fleet_sim.control_plane.resource_network import ResourceType
from fleet_sim.empirical.assurance_campaign import (
    CampaignPackageVerification,
    validate_campaign_manifest,
    verify_empirical_campaign_package,
)
from fleet_sim.empirical.calibration_gate import (
    EmpiricalCalibrationPackageVerification,
    verify_empirical_calibration_package,
)
from fleet_sim.empirical.resource_adapter import (
    AdaptedResourcePackageVerification,
    load_resource_adapter_policy,
    verify_adapted_resource_bundle,
)

PROTOCOL_SCHEMA_VERSION = "1.0"
RegistrationMode = Literal["engineering_dry_run", "prospective_transfer"]

PRIMARY_ESTIMAND = "resource_arrival_rate_transfer"
PREDICTION_FORMULA = (
    "arrival_rate=background_work_per_agent_s*fleet_size+"
    "admission_work_units_per_agent*(agents_admitted/window_duration_s)"
)
PREDICTOR_FIELDS = ("fleet_size", "agents_admitted", "window_duration_ms")
METRICS = (
    "duration_weighted_normalized_rmse",
    "absolute_duration_weighted_relative_bias",
    "candidate_relative_improvement_over_background_only",
)
COMPARATOR = "calibration_background_only_nonnegative_least_squares"
UNCERTAINTY_METHOD = "joint_calibration_time_block_bootstrap"
UNCERTAINTY_SCOPE = "mean_parameter_uncertainty_not_future_observation_interval"

REGISTRATION_PACKAGE_FILES = {
    "registration.json",
    "registration_plan.json",
    "transfer_contract.json",
    "registration_schema.json",
    "registration_plan_schema.json",
    "transfer_contract_schema.json",
    "registration_manifest.json",
}
EVALUATION_INPUT_PACKAGE_FILES = {
    "evaluation_inputs.json",
    "evaluation_inputs_schema.json",
    "evaluation_inputs_manifest.json",
}

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MAX_PACKAGE_BYTES = 64 * 1024 * 1024


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON constant is not permitted: {value}")


def _object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is not permitted: {key}")
        result[key] = value
    return result


def _read_json_bytes(data: bytes, name: str) -> dict[str, Any]:
    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise ValueError(f"{name} must be UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise TypeError(f"{name} must contain one JSON object")
    return value


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
    if not isinstance(value, str):
        raise TypeError(f"{context} must be a string")
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


def _optional_finite(
    value: object,
    context: str,
    *,
    minimum: float | None = None,
) -> float | None:
    if value is None:
        return None
    return _finite(value, context, minimum=minimum)


def _exact_keys(
    value: object,
    expected: set[str],
    context: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{context} must be an object")
    actual = set(value)
    if actual != expected:
        raise ValueError(
            f"{context} fields differ from the closed contract: "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    return value


def _timestamp(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{context} must be an explicit UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{context} is not a valid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError(f"{context} must use UTC")
    return parsed.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _timestamp_without_submicrosecond(value: object, context: str) -> str:
    canonical = _timestamp(value, context)
    assert isinstance(value, str)
    fractional = re.search(r"[.,](\d+)Z$", value)
    if fractional is not None and any(digit != "0" for digit in fractional.group(1)[6:]):
        raise ValueError(f"{context} cannot contain sub-microsecond precision")
    return canonical


def _timestamp_value(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _string_tuple(value: object, context: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{context} must be a nonempty array")
    selected = tuple(_identifier(item, f"{context} item") for item in value)
    if len(selected) != len(set(selected)):
        raise ValueError(f"{context} cannot contain duplicates")
    return selected


@dataclass(frozen=True, slots=True)
class TransferMetricThresholds:
    maximum_duration_weighted_nrmse: float | None
    maximum_absolute_duration_weighted_relative_bias: float | None
    minimum_candidate_relative_improvement: float | None
    minimum_valid_time_blocks_per_cell: int | None
    require_every_resource: bool

    def __post_init__(self) -> None:
        if not self.require_every_resource:
            raise ValueError("the ten-resource transfer contract requires every resource")

    @classmethod
    def from_mapping(cls, value: object) -> TransferMetricThresholds:
        selected = _exact_keys(
            value,
            {
                "maximum_duration_weighted_nrmse",
                "maximum_absolute_duration_weighted_relative_bias",
                "minimum_candidate_relative_improvement",
                "minimum_valid_time_blocks_per_cell",
                "require_every_resource",
            },
            "transfer metric thresholds",
        )
        minimum_blocks = selected["minimum_valid_time_blocks_per_cell"]
        return cls(
            maximum_duration_weighted_nrmse=_optional_finite(
                selected["maximum_duration_weighted_nrmse"],
                "maximum duration-weighted NRMSE",
                minimum=0.0,
            ),
            maximum_absolute_duration_weighted_relative_bias=_optional_finite(
                selected["maximum_absolute_duration_weighted_relative_bias"],
                "maximum absolute duration-weighted relative bias",
                minimum=0.0,
            ),
            minimum_candidate_relative_improvement=_optional_finite(
                selected["minimum_candidate_relative_improvement"],
                "minimum candidate relative improvement",
                minimum=0.0,
            ),
            minimum_valid_time_blocks_per_cell=(
                None
                if minimum_blocks is None
                else _integer(minimum_blocks, "minimum valid time blocks per cell", minimum=1)
            ),
            require_every_resource=_strict_bool(
                selected["require_every_resource"], "require every resource"
            ),
        )

    @property
    def complete(self) -> bool:
        return all(
            value is not None
            for value in (
                self.maximum_duration_weighted_nrmse,
                self.maximum_absolute_duration_weighted_relative_bias,
                self.minimum_candidate_relative_improvement,
                self.minimum_valid_time_blocks_per_cell,
            )
        )


@dataclass(frozen=True, slots=True)
class ResourceArrivalTransferContract:
    schema_version: str
    contract_id: str
    contract_mode: RegistrationMode
    primary_estimand: str
    prediction_formula: str
    predictor_fields: tuple[str, ...]
    outcome_field: str
    resource_types: tuple[str, ...]
    comparator: str
    metrics: tuple[str, ...]
    uncertainty_method: str
    uncertainty_scope: str
    criteria_frozen: bool
    thresholds: TransferMetricThresholds
    operational_outcome_extension_enabled: bool
    prediction_rows_preoutcome_lock_required: bool
    outcome_custody_evidence_required: bool
    external_validation: bool
    scientific_use_authorized: bool
    runner_authorized: bool

    def __post_init__(self) -> None:
        if self.schema_version != PROTOCOL_SCHEMA_VERSION:
            raise ValueError(f"contract schema_version must be {PROTOCOL_SCHEMA_VERSION}")
        _identifier(self.contract_id, "contract_id")
        if self.contract_mode not in {"engineering_dry_run", "prospective_transfer"}:
            raise ValueError("contract_mode is not supported")
        if self.primary_estimand != PRIMARY_ESTIMAND:
            raise ValueError("only resource_arrival_rate_transfer is currently executable")
        if self.prediction_formula != PREDICTION_FORMULA:
            raise ValueError("prediction formula differs from the implemented contract")
        if self.predictor_fields != PREDICTOR_FIELDS:
            raise ValueError("predictor fields differ from the implemented contract")
        if self.outcome_field != "arrival_count":
            raise ValueError("outcome field differs from the implemented contract")
        expected_resources = tuple(sorted(item.value for item in ResourceType))
        if tuple(sorted(self.resource_types)) != expected_resources or len(
            self.resource_types
        ) != len(expected_resources):
            raise ValueError("transfer contract must cover exactly the ten resource types")
        if self.comparator != COMPARATOR:
            raise ValueError("comparator differs from the implemented contract")
        if self.metrics != METRICS:
            raise ValueError("metric set differs from the implemented contract")
        if self.uncertainty_method != UNCERTAINTY_METHOD:
            raise ValueError("uncertainty method differs from the implemented contract")
        if self.uncertainty_scope != UNCERTAINTY_SCOPE:
            raise ValueError("uncertainty scope differs from the implemented contract")
        if self.operational_outcome_extension_enabled:
            raise ValueError("operational outcome transfer is not implemented or authorized")
        if not self.prediction_rows_preoutcome_lock_required:
            raise ValueError("prediction-row preoutcome locking must be required")
        if not self.outcome_custody_evidence_required:
            raise ValueError("outcome custody evidence must be required")
        if self.external_validation or self.scientific_use_authorized or self.runner_authorized:
            raise ValueError("the transfer contract cannot grant authority or external validation")
        if self.contract_mode == "prospective_transfer" and (
            not self.criteria_frozen or not self.thresholds.complete
        ):
            raise ValueError("prospective_transfer requires frozen, complete numeric criteria")

    @classmethod
    def from_mapping(cls, value: object) -> ResourceArrivalTransferContract:
        fields = set(cls.__dataclass_fields__)
        selected = _exact_keys(value, fields, "resource arrival transfer contract")
        return cls(
            schema_version=_string(selected["schema_version"], "schema_version"),
            contract_id=_identifier(selected["contract_id"], "contract_id"),
            contract_mode=_string(  # type: ignore[arg-type]
                selected["contract_mode"], "contract_mode"
            ),
            primary_estimand=_string(selected["primary_estimand"], "primary_estimand"),
            prediction_formula=_string(selected["prediction_formula"], "prediction_formula"),
            predictor_fields=_string_tuple(selected["predictor_fields"], "predictor_fields"),
            outcome_field=_string(selected["outcome_field"], "outcome_field"),
            resource_types=_string_tuple(selected["resource_types"], "resource_types"),
            comparator=_string(selected["comparator"], "comparator"),
            metrics=_string_tuple(selected["metrics"], "metrics"),
            uncertainty_method=_string(selected["uncertainty_method"], "uncertainty_method"),
            uncertainty_scope=_string(selected["uncertainty_scope"], "uncertainty_scope"),
            criteria_frozen=_strict_bool(selected["criteria_frozen"], "criteria_frozen"),
            thresholds=TransferMetricThresholds.from_mapping(selected["thresholds"]),
            operational_outcome_extension_enabled=_strict_bool(
                selected["operational_outcome_extension_enabled"],
                "operational_outcome_extension_enabled",
            ),
            prediction_rows_preoutcome_lock_required=_strict_bool(
                selected["prediction_rows_preoutcome_lock_required"],
                "prediction_rows_preoutcome_lock_required",
            ),
            outcome_custody_evidence_required=_strict_bool(
                selected["outcome_custody_evidence_required"],
                "outcome_custody_evidence_required",
            ),
            external_validation=_strict_bool(
                selected["external_validation"], "external_validation"
            ),
            scientific_use_authorized=_strict_bool(
                selected["scientific_use_authorized"], "scientific_use_authorized"
            ),
            runner_authorized=_strict_bool(selected["runner_authorized"], "runner_authorized"),
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["predictor_fields"] = list(self.predictor_fields)
        payload["resource_types"] = list(self.resource_types)
        payload["metrics"] = list(self.metrics)
        return payload

    @property
    def semantic_sha256(self) -> str:
        return _sha256_bytes(_canonical_json_bytes(self.to_dict()))


@dataclass(frozen=True, slots=True)
class PlannedEvaluationBlock:
    time_block_id: str
    timestamp_utc: str
    fleet_size: int
    agents_admitted: int
    window_duration_ms: float

    def __post_init__(self) -> None:
        _identifier(self.time_block_id, "planned time_block_id")
        timestamp = _timestamp(self.timestamp_utc, "planned timestamp_utc")
        if timestamp != self.timestamp_utc:
            raise ValueError("planned timestamp_utc must use canonical UTC microsecond form")
        _integer(self.fleet_size, "planned fleet_size", minimum=1)
        _integer(self.agents_admitted, "planned agents_admitted")
        if self.agents_admitted > self.fleet_size:
            raise ValueError("planned agents_admitted cannot exceed fleet_size")
        _finite(self.window_duration_ms, "planned window_duration_ms", minimum=0.0)
        if self.window_duration_ms == 0.0:
            raise ValueError("planned window_duration_ms must be positive")
        duration_microseconds = Decimal(str(self.window_duration_ms)) * Decimal(1000)
        if duration_microseconds != duration_microseconds.to_integral_value():
            raise ValueError("planned window_duration_ms must align to whole microseconds")

    @classmethod
    def from_mapping(cls, value: object) -> PlannedEvaluationBlock:
        selected = _exact_keys(
            value,
            {
                "time_block_id",
                "timestamp_utc",
                "fleet_size",
                "agents_admitted",
                "window_duration_ms",
            },
            "planned evaluation block",
        )
        return cls(
            time_block_id=_identifier(selected["time_block_id"], "time_block_id"),
            timestamp_utc=_string(selected["timestamp_utc"], "timestamp_utc"),
            fleet_size=_integer(selected["fleet_size"], "fleet_size", minimum=1),
            agents_admitted=_integer(selected["agents_admitted"], "agents_admitted"),
            window_duration_ms=_finite(
                selected["window_duration_ms"], "window_duration_ms", minimum=0.0
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "time_block_id": self.time_block_id,
            "timestamp_utc": self.timestamp_utc,
            "fleet_size": self.fleet_size,
            "agents_admitted": self.agents_admitted,
            "window_duration_ms": self.window_duration_ms,
        }


@dataclass(frozen=True, slots=True)
class PlannedEvaluationCell:
    cell_id: str
    planned_blocks: tuple[PlannedEvaluationBlock, ...]

    def __post_init__(self) -> None:
        _identifier(self.cell_id, "cell_id")
        if not self.planned_blocks:
            raise ValueError("planned evaluation cell must contain at least one time block")
        block_ids = [item.time_block_id for item in self.planned_blocks]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("planned time_block_id values cannot repeat within a cell")

    @classmethod
    def from_mapping(cls, value: object) -> PlannedEvaluationCell:
        selected = _exact_keys(value, {"cell_id", "planned_blocks"}, "planned evaluation cell")
        blocks = selected["planned_blocks"]
        if not isinstance(blocks, list):
            raise TypeError("planned_blocks must be an array")
        return cls(
            cell_id=_identifier(selected["cell_id"], "cell_id"),
            planned_blocks=tuple(PlannedEvaluationBlock.from_mapping(item) for item in blocks),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "cell_id": self.cell_id,
            "planned_blocks": [item.to_dict() for item in self.planned_blocks],
        }


@dataclass(frozen=True, slots=True)
class SuccessorRegistrationPlan:
    schema_version: str
    plan_id: str
    study_id: str
    registration_mode: RegistrationMode
    planned_evaluation_campaign_id: str
    planned_collection_start_utc: str
    planned_collection_end_utc: str
    cells: tuple[PlannedEvaluationCell, ...]
    one_shot_evaluation: bool
    deviation_policy: Literal["fail_closed"]
    prediction_lock_required: bool
    outcome_custody_required: bool

    def __post_init__(self) -> None:
        if self.schema_version != PROTOCOL_SCHEMA_VERSION:
            raise ValueError(f"plan schema_version must be {PROTOCOL_SCHEMA_VERSION}")
        _identifier(self.plan_id, "plan_id")
        _identifier(self.study_id, "study_id")
        if self.registration_mode not in {"engineering_dry_run", "prospective_transfer"}:
            raise ValueError("registration_mode is not supported")
        _identifier(self.planned_evaluation_campaign_id, "planned_evaluation_campaign_id")
        start = _timestamp(self.planned_collection_start_utc, "planned_collection_start_utc")
        end = _timestamp(self.planned_collection_end_utc, "planned_collection_end_utc")
        if start != self.planned_collection_start_utc or end != self.planned_collection_end_utc:
            raise ValueError("planned timestamps must use canonical UTC microsecond form")
        if _timestamp_value(end) <= _timestamp_value(start):
            raise ValueError("planned collection end must be later than start")
        if not self.cells:
            raise ValueError("registration plan must contain at least one evaluation cell")
        cell_ids = [item.cell_id for item in self.cells]
        if len(cell_ids) != len(set(cell_ids)):
            raise ValueError("planned cell IDs cannot repeat")
        blocks = [block.time_block_id for cell in self.cells for block in cell.planned_blocks]
        if len(blocks) != len(set(blocks)):
            raise ValueError("planned time-block IDs cannot appear in multiple cells")
        for cell in self.cells:
            for block in cell.planned_blocks:
                block_start = _timestamp_value(block.timestamp_utc)
                block_end = block_start + timedelta(milliseconds=block.window_duration_ms)
                if block_start < _timestamp_value(start) or block_end > _timestamp_value(end):
                    raise ValueError("every planned block must fit within the collection window")
        if not self.one_shot_evaluation:
            raise ValueError("successor evaluation must be one-shot")
        if self.deviation_policy != "fail_closed":
            raise ValueError("deviation policy must be fail_closed")
        if not self.prediction_lock_required or not self.outcome_custody_required:
            raise ValueError("prediction lock and outcome custody must both be required")

    @classmethod
    def from_mapping(cls, value: object) -> SuccessorRegistrationPlan:
        fields = set(cls.__dataclass_fields__)
        selected = _exact_keys(value, fields, "successor registration plan")
        cells_raw = selected["cells"]
        if not isinstance(cells_raw, list):
            raise TypeError("registration cells must be an array")
        return cls(
            schema_version=_string(selected["schema_version"], "schema_version"),
            plan_id=_identifier(selected["plan_id"], "plan_id"),
            study_id=_identifier(selected["study_id"], "study_id"),
            registration_mode=_string(  # type: ignore[arg-type]
                selected["registration_mode"], "registration_mode"
            ),
            planned_evaluation_campaign_id=_identifier(
                selected["planned_evaluation_campaign_id"],
                "planned_evaluation_campaign_id",
            ),
            planned_collection_start_utc=_string(
                selected["planned_collection_start_utc"], "planned_collection_start_utc"
            ),
            planned_collection_end_utc=_string(
                selected["planned_collection_end_utc"], "planned_collection_end_utc"
            ),
            cells=tuple(PlannedEvaluationCell.from_mapping(item) for item in cells_raw),
            one_shot_evaluation=_strict_bool(
                selected["one_shot_evaluation"], "one_shot_evaluation"
            ),
            deviation_policy=_string(  # type: ignore[arg-type]
                selected["deviation_policy"], "deviation_policy"
            ),
            prediction_lock_required=_strict_bool(
                selected["prediction_lock_required"], "prediction_lock_required"
            ),
            outcome_custody_required=_strict_bool(
                selected["outcome_custody_required"], "outcome_custody_required"
            ),
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["cells"] = [item.to_dict() for item in self.cells]
        return payload

    @property
    def semantic_sha256(self) -> str:
        return _sha256_bytes(_canonical_json_bytes(self.to_dict()))


@dataclass(frozen=True, slots=True)
class SuccessorRegistration:
    schema_version: str
    registration_id: str
    registered_at_utc: str
    registration_mode: RegistrationMode
    source_campaign_id: str
    source_dataset_id: str
    source_campaign_evidence_manifest_sha256: str
    source_calibration_content_sha256: str
    source_historical_heldout_verified: bool
    source_historical_heldout_used_for_fit: bool
    calibration_fit_id: str
    fit_policy_sha256: str
    fit_evidence_manifest_sha256: str
    adapter_bundle_id: str
    adapter_policy_sha256: str
    adapter_manifest_sha256: str
    adapter_specification_sha256: str
    simulator_semantics_sha256: str
    plan_sha256: str
    transfer_contract_sha256: str
    planned_evaluation_campaign_id: str
    planned_collection_start_utc: str
    planned_collection_end_utc: str
    planned_cell_count: int
    planned_time_block_count: int
    chronology_consistent: bool
    registration_time_externally_attested: bool
    upstream_chain_verified: bool
    prediction_formula_frozen: bool
    operational_outcome_extension_enabled: bool
    implementation: tuple[tuple[str, str], ...]
    implementation_sha256: str
    execution_chain_ready: bool
    external_validation: bool
    scientific_use_authorized: bool
    runner_authorized: bool

    def __post_init__(self) -> None:
        if self.schema_version != PROTOCOL_SCHEMA_VERSION:
            raise ValueError(f"registration schema_version must be {PROTOCOL_SCHEMA_VERSION}")
        for value, context in (
            (self.registration_id, "registration_id"),
            (self.source_campaign_id, "source_campaign_id"),
            (self.source_dataset_id, "source_dataset_id"),
            (self.calibration_fit_id, "calibration_fit_id"),
            (self.adapter_bundle_id, "adapter_bundle_id"),
            (self.planned_evaluation_campaign_id, "planned_evaluation_campaign_id"),
        ):
            _identifier(value, context)
        if self.registration_mode not in {"engineering_dry_run", "prospective_transfer"}:
            raise ValueError("registration_mode is not supported")
        for value, context in (
            (self.source_campaign_evidence_manifest_sha256, "source campaign hash"),
            (self.source_calibration_content_sha256, "calibration content hash"),
            (self.fit_policy_sha256, "fit policy hash"),
            (self.fit_evidence_manifest_sha256, "fit evidence hash"),
            (self.adapter_policy_sha256, "adapter policy hash"),
            (self.adapter_manifest_sha256, "adapter manifest hash"),
            (self.adapter_specification_sha256, "adapter specification hash"),
            (self.simulator_semantics_sha256, "simulator semantics hash"),
            (self.plan_sha256, "plan hash"),
            (self.transfer_contract_sha256, "transfer contract hash"),
            (self.implementation_sha256, "implementation hash"),
        ):
            _sha256(value, context)
        registered = _timestamp(self.registered_at_utc, "registered_at_utc")
        start = _timestamp(self.planned_collection_start_utc, "planned collection start")
        end = _timestamp(self.planned_collection_end_utc, "planned collection end")
        if (registered, start, end) != (
            self.registered_at_utc,
            self.planned_collection_start_utc,
            self.planned_collection_end_utc,
        ):
            raise ValueError("registration timestamps must use canonical UTC microsecond form")
        if not (_timestamp_value(registered) < _timestamp_value(start) < _timestamp_value(end)):
            raise ValueError("registration must precede a positive planned collection window")
        if self.source_campaign_id == self.planned_evaluation_campaign_id:
            raise ValueError("prospective evaluation campaign must differ from source campaign")
        if self.planned_cell_count < 1 or self.planned_time_block_count < 1:
            raise ValueError("registration must plan at least one cell and time block")
        if len(self.implementation) != 5 or len({item[0] for item in self.implementation}) != 5:
            raise ValueError("registration implementation boundary must contain five records")
        for path, digest in self.implementation:
            if not path or path.startswith(("/", "~")) or ".." in Path(path).parts:
                raise ValueError("implementation paths must be portable package-relative names")
            _sha256(digest, f"implementation hash for {path}")
        visible_implementation = [
            {"path": path, "sha256": digest} for path, digest in self.implementation
        ]
        if self.implementation_sha256 != _sha256_bytes(
            _canonical_json_bytes(visible_implementation)
        ):
            raise ValueError("registration implementation hash is inconsistent")
        if not self.source_historical_heldout_verified:
            raise ValueError("source package held-out verification must be retained")
        if self.source_historical_heldout_used_for_fit:
            raise ValueError("historical held-out content cannot be used for fitting")
        if not (
            self.chronology_consistent
            and self.upstream_chain_verified
            and self.prediction_formula_frozen
        ):
            raise ValueError("registration verification gates must be true")
        if (
            self.registration_time_externally_attested
            or self.operational_outcome_extension_enabled
            or self.execution_chain_ready
            or self.external_validation
            or self.scientific_use_authorized
            or self.runner_authorized
        ):
            raise ValueError("registration cannot assert external assurance or execution authority")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["implementation"] = [
            {"path": path, "sha256": digest} for path, digest in self.implementation
        ]
        return payload


@dataclass(frozen=True, slots=True)
class SuccessorRegistrationPackageVerification:
    package_dir: Path
    registration: SuccessorRegistration
    plan: SuccessorRegistrationPlan
    contract: ResourceArrivalTransferContract
    registration_manifest_sha256: str
    externally_digest_bound: bool


@dataclass(frozen=True, slots=True)
class SuccessorEvaluationInputs:
    schema_version: str
    evaluation_input_id: str
    registration_id: str
    registration_manifest_sha256: str
    evaluation_campaign_id: str
    evaluation_campaign_evidence_manifest_sha256: str
    evaluation_heldout_content_sha256: str
    realized_cell_count: int
    realized_time_block_count: int
    realized_cells: tuple[PlannedEvaluationCell, ...]
    campaign_identity_reconciled: bool
    collection_window_reconciled: bool
    cell_block_reconciliation: Literal["exact"]
    predictor_design_reconciled: bool
    chronology_consistent: bool
    registration_time_externally_attested: bool
    prediction_formula_frozen: bool
    prediction_rows_preoutcome_locked: bool
    outcome_release_custody_verified: bool
    execution_chain_ready: bool
    external_validation: bool
    scientific_use_authorized: bool
    runner_authorized: bool

    def __post_init__(self) -> None:
        if self.schema_version != PROTOCOL_SCHEMA_VERSION:
            raise ValueError(f"evaluation-input schema_version must be {PROTOCOL_SCHEMA_VERSION}")
        for value, context in (
            (self.evaluation_input_id, "evaluation_input_id"),
            (self.registration_id, "registration_id"),
            (self.evaluation_campaign_id, "evaluation_campaign_id"),
        ):
            _identifier(value, context)
        for value, context in (
            (self.registration_manifest_sha256, "registration manifest hash"),
            (
                self.evaluation_campaign_evidence_manifest_sha256,
                "evaluation campaign evidence hash",
            ),
            (self.evaluation_heldout_content_sha256, "evaluation heldout hash"),
        ):
            _sha256(value, context)
        if self.realized_cell_count != len(self.realized_cells):
            raise ValueError("realized cell count is inconsistent")
        blocks = [
            block.time_block_id for cell in self.realized_cells for block in cell.planned_blocks
        ]
        if self.realized_time_block_count != len(blocks) or len(blocks) != len(set(blocks)):
            raise ValueError("realized time-block count or uniqueness is inconsistent")
        if self.cell_block_reconciliation != "exact":
            raise ValueError("evaluation inputs require exact cell/block reconciliation")
        if not (
            self.campaign_identity_reconciled
            and self.collection_window_reconciled
            and self.predictor_design_reconciled
            and self.chronology_consistent
            and self.prediction_formula_frozen
        ):
            raise ValueError("evaluation-input reconciliation gates must be true")
        if (
            self.registration_time_externally_attested
            or self.prediction_rows_preoutcome_locked
            or self.outcome_release_custody_verified
            or self.execution_chain_ready
            or self.external_validation
            or self.scientific_use_authorized
            or self.runner_authorized
        ):
            raise ValueError("evaluation-input package cannot assert authorization or execution")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["realized_cells"] = [item.to_dict() for item in self.realized_cells]
        return payload


@dataclass(frozen=True, slots=True)
class SuccessorEvaluationInputsPackageVerification:
    package_dir: Path
    inputs: SuccessorEvaluationInputs
    evaluation_inputs_manifest_sha256: str
    externally_digest_bound: bool


def _implementation_record() -> tuple[tuple[str, str], ...]:
    package_root = Path(__file__).resolve().parents[1]
    files = (
        Path(__file__).resolve(),
        package_root / "empirical" / "assurance_campaign.py",
        package_root / "empirical" / "calibration_gate.py",
        package_root / "empirical" / "resource_adapter.py",
    )
    records = [
        (
            (Path("fleet_sim") / path.relative_to(package_root)).as_posix(),
            _sha256_path(path),
        )
        for path in files
    ]
    runtime = {
        "python": platform.python_version(),
        "pandas": importlib.metadata.version("pandas"),
        "pyarrow": importlib.metadata.version("pyarrow"),
    }
    records.append(("runtime", _sha256_bytes(_canonical_json_bytes(runtime))))
    return tuple(records)


def _artifact_sha256(evidence: Mapping[str, object], name: str) -> str:
    artifacts = evidence.get("artifacts")
    if not isinstance(artifacts, list):
        raise TypeError("campaign artifact inventory is invalid")
    matches = [item for item in artifacts if isinstance(item, Mapping) and item.get("path") == name]
    if len(matches) != 1:
        raise ValueError(f"campaign artifact inventory is missing unique {name}")
    return _sha256(matches[0].get("sha256"), f"campaign {name} hash")


def _partition_sha256(evidence: Mapping[str, object], name: str) -> str:
    partitions = evidence.get("partitions")
    if not isinstance(partitions, Mapping):
        raise TypeError("campaign partition evidence is invalid")
    selected = partitions.get(name)
    if not isinstance(selected, Mapping):
        raise TypeError(f"campaign partition evidence is missing {name}")
    return _sha256(selected.get("content_sha256"), f"{name} content hash")


def _calibration_evidence_scope(campaign: CampaignPackageVerification) -> str:
    source_types = set(campaign.calibration["source_type"].astype(str))
    if "synthetic" in source_types:
        return "synthetic_or_mixed_interface_only"
    if source_types == {"measured"}:
        return "measured_input_unreviewed"
    if source_types == {"replayed"}:
        return "replayed_input_unreviewed"
    if source_types == {"measured", "replayed"}:
        return "mixed_nonsynthetic_input_unreviewed"
    raise ValueError("calibration source types differ from the closed evidence contract")


def _read_bounded_file(path: Path, maximum_bytes: int) -> bytes:
    if maximum_bytes <= 0:
        raise ValueError("maximum_bytes must be positive")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"cannot safely open package artifact: {path.name}") from exc
    chunks: list[bytes] = []
    total = 0
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"package artifact is not a regular file: {path.name}")
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            total += len(chunk)
            if total > maximum_bytes:
                raise ValueError(f"package exceeds the {maximum_bytes}-byte limit")
            chunks.append(chunk)
        after = os.fstat(stream.fileno())
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ValueError(f"package artifact changed while being read: {path.name}")
    return b"".join(chunks)


def _campaign_manifest(campaign: CampaignPackageVerification) -> dict[str, object]:
    evidence = campaign.evidence_manifest
    data = _read_bounded_file(campaign.package_dir / "campaign_manifest.json", 8 * 1024 * 1024)
    if _sha256_bytes(data) != _artifact_sha256(evidence, "campaign_manifest.json"):
        raise ValueError("campaign manifest changed after package verification")
    return validate_campaign_manifest(_read_json_bytes(data, "campaign_manifest.json"))


def _validate_campaign_package_snapshot(
    campaign: CampaignPackageVerification,
) -> CampaignPackageVerification:
    if not campaign.externally_digest_bound:
        raise ValueError("campaign wrapper is not externally digest bound")
    refreshed = verify_empirical_campaign_package(
        campaign.package_dir,
        expected_evidence_manifest_sha256=campaign.evidence_manifest_sha256,
    )
    if (
        refreshed.package_dir.resolve() != campaign.package_dir.resolve()
        or refreshed.dataset_id != campaign.dataset_id
        or refreshed.evidence_scope != campaign.evidence_scope
        or refreshed.external_validation != campaign.external_validation
        or refreshed.scientific_use_authorized != campaign.scientific_use_authorized
        or refreshed.evidence_manifest != campaign.evidence_manifest
        or not refreshed.calibration.equals(campaign.calibration)
        or not refreshed.heldout.equals(campaign.heldout)
        or refreshed.externally_digest_bound != campaign.externally_digest_bound
    ):
        raise ValueError("campaign wrapper differs from its externally bound package")
    return refreshed


def _validate_upstream_package_snapshots(
    source_campaign: CampaignPackageVerification,
    fit_package: EmpiricalCalibrationPackageVerification,
    adapter_package: AdaptedResourcePackageVerification,
) -> tuple[
    CampaignPackageVerification,
    EmpiricalCalibrationPackageVerification,
    AdaptedResourcePackageVerification,
]:
    """Reverify the complete physical upstream chain before package publication."""

    refreshed_source = _validate_campaign_package_snapshot(source_campaign)
    refreshed_fit = verify_empirical_calibration_package(
        fit_package.package_dir,
        source_campaign_package=refreshed_source.package_dir,
        expected_source_evidence_manifest_sha256=(refreshed_source.evidence_manifest_sha256),
        expected_fit_evidence_manifest_sha256=(fit_package.fit_evidence_manifest_sha256),
    )
    if (
        refreshed_fit.package_dir.resolve() != fit_package.package_dir.resolve()
        or refreshed_fit.fit.to_dict() != fit_package.fit.to_dict()
        or not refreshed_fit.bootstrap_draws.equals(fit_package.bootstrap_draws)
        or refreshed_fit._source_campaign_package_dir.resolve()
        != fit_package._source_campaign_package_dir.resolve()
        or refreshed_fit.externally_digest_bound != fit_package.externally_digest_bound
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
        or refreshed_adapter.externally_digest_bound != adapter_package.externally_digest_bound
    ):
        raise ValueError("adapter wrapper differs from its externally bound package")
    return refreshed_source, refreshed_fit, refreshed_adapter


def load_resource_arrival_transfer_contract(
    path: str | Path,
) -> ResourceArrivalTransferContract:
    selected = Path(path)
    return ResourceArrivalTransferContract.from_mapping(
        _read_json_bytes(_read_bounded_file(selected, 4 * 1024 * 1024), selected.name)
    )


def load_successor_registration_plan(path: str | Path) -> SuccessorRegistrationPlan:
    selected = Path(path)
    return SuccessorRegistrationPlan.from_mapping(
        _read_json_bytes(_read_bounded_file(selected, 4 * 1024 * 1024), selected.name)
    )


def _validate_upstream_chain(
    source_campaign: CampaignPackageVerification,
    fit_package: EmpiricalCalibrationPackageVerification,
    adapter_package: AdaptedResourcePackageVerification,
) -> tuple[str, Mapping[str, object], str]:
    if not (
        source_campaign.externally_digest_bound
        and fit_package.externally_digest_bound
        and adapter_package.externally_digest_bound
    ):
        raise ValueError("registration requires externally digest-bound upstream packages")
    if source_campaign.external_validation or source_campaign.scientific_use_authorized:
        raise ValueError("source campaign exceeds the successor engineering boundary")
    evidence = source_campaign.evidence_manifest
    source_campaign_id = _identifier(evidence.get("campaign_id"), "source campaign_id")
    calibration_digest = _partition_sha256(evidence, "calibration")
    fit = fit_package.fit
    adapter = adapter_package.bundle
    if fit_package._source_campaign_package_dir.resolve() != source_campaign.package_dir.resolve():
        raise ValueError("fit package was verified against a different source campaign path")
    if fit.calibration_content_sha256 != calibration_digest:
        raise ValueError("fit is bound to a different calibration partition")
    calibration_scope = _calibration_evidence_scope(source_campaign)
    if (
        fit.source_evidence_scope != calibration_scope
        or adapter.evidence_scope != calibration_scope
    ):
        raise ValueError("fit or adapter evidence scope differs from calibration evidence")
    if adapter.calibration_fit_id != fit.calibration_fit_id:
        raise ValueError("adapter is bound to a different calibration fit")
    if adapter.fit_evidence_manifest_sha256 != fit_package.fit_evidence_manifest_sha256:
        raise ValueError("adapter is bound to a different fit evidence manifest")
    if not fit.source_package_heldout_verified or fit.heldout_used_for_fit:
        raise ValueError("fit held-out boundary differs from the successor contract")
    if not adapter.source_package_heldout_verified or adapter.heldout_used_for_adapter:
        raise ValueError("adapter held-out boundary differs from the successor contract")
    if (
        fit.runner_authorized
        or fit.scientific_use_authorized
        or fit.external_validation
        or adapter.runner_authorized
        or adapter.scientific_use_authorized
        or adapter.external_validation
    ):
        raise ValueError("upstream evidence improperly grants authority or external validation")
    return source_campaign_id, evidence, calibration_scope


def freeze_successor_registration(
    source_campaign: CampaignPackageVerification,
    fit_package: EmpiricalCalibrationPackageVerification,
    adapter_package: AdaptedResourcePackageVerification,
    plan: SuccessorRegistrationPlan,
    contract: ResourceArrivalTransferContract,
    *,
    registered_at_utc: str | None = None,
) -> SuccessorRegistration:
    """Freeze one internally consistent registration without authorizing execution."""

    source_campaign_id, evidence, calibration_scope = _validate_upstream_chain(
        source_campaign, fit_package, adapter_package
    )
    fit = fit_package.fit
    adapter = adapter_package.bundle
    if plan.registration_mode != contract.contract_mode:
        raise ValueError("registration plan and transfer contract modes differ")
    minimum_blocks = contract.thresholds.minimum_valid_time_blocks_per_cell
    if plan.registration_mode == "prospective_transfer" and (
        minimum_blocks is None
        or any(len(cell.planned_blocks) < minimum_blocks for cell in plan.cells)
    ):
        raise ValueError(
            "every prospective cell must plan at least the frozen minimum valid blocks"
        )
    if plan.planned_evaluation_campaign_id == source_campaign_id:
        raise ValueError("prospective evaluation campaign must differ from source campaign")
    registered = _timestamp(
        registered_at_utc
        if registered_at_utc is not None
        else datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "registered_at_utc",
    )
    if _timestamp_value(plan.planned_collection_start_utc) <= _timestamp_value(registered):
        raise ValueError("registration must precede the planned evaluation collection")

    if plan.registration_mode == "prospective_transfer":
        if fit.policy.study_mode != "successor_transfer":
            raise ValueError("prospective registration requires a successor_transfer fit")
        if fit.gate_status != "passed" or not fit.interface_verification_ready:
            raise ValueError("prospective registration requires an accepted fit")
        if not fit.eligible_for_adapter:
            raise ValueError("prospective registration requires successor-transfer eligibility")
        if adapter.adapter_mode != "successor_transfer":
            raise ValueError("prospective registration requires a successor_transfer adapter")
        if calibration_scope == "synthetic_or_mixed_interface_only":
            raise ValueError("prospective registration cannot use synthetic calibration evidence")
        if any(item.evidence_class == "notional" for item in adapter.field_provenance):
            raise ValueError("prospective registration cannot use notional adapter fields")
        adapter_policy = load_resource_adapter_policy(
            adapter_package.package_dir / "adapter_policy.json",
            expected_policy_sha256=adapter.adapter_policy_sha256,
        ).policy
        if (
            adapter_policy.adapter_mode != adapter.adapter_mode
            or adapter_policy.fit_policy_sha256 != fit.policy_sha256
        ):
            raise ValueError("adapter policy differs from the verified adapter and fit chain")
        fleet_min = max(
            fit.policy.target_fleet_size_min,
            adapter_policy.target_fleet_size_min,
        )
        fleet_max = min(
            fit.policy.target_fleet_size_max,
            adapter_policy.target_fleet_size_max,
        )
        admission_min = max(
            fit.policy.target_admission_rate_min_per_s,
            adapter_policy.target_admission_rate_min_per_s,
        )
        admission_max = min(
            fit.policy.target_admission_rate_max_per_s,
            adapter_policy.target_admission_rate_max_per_s,
        )
        for cell in plan.cells:
            for block in cell.planned_blocks:
                if not fleet_min <= block.fleet_size <= fleet_max:
                    raise ValueError(
                        "prospective block fleet size lies outside the accepted fit and adapter "
                        "domain"
                    )
                admission_rate = block.agents_admitted / (block.window_duration_ms / 1000.0)
                if not admission_min <= admission_rate <= admission_max:
                    raise ValueError(
                        "prospective block admission rate lies outside the accepted fit and "
                        "adapter domain"
                    )

    implementation = _implementation_record()
    visible_implementation = [{"path": path, "sha256": digest} for path, digest in implementation]
    implementation_sha256 = _sha256_bytes(_canonical_json_bytes(visible_implementation))
    values: dict[str, object] = {
        "schema_version": PROTOCOL_SCHEMA_VERSION,
        "registered_at_utc": registered,
        "registration_mode": plan.registration_mode,
        "source_campaign_id": source_campaign_id,
        "source_dataset_id": source_campaign.dataset_id,
        "source_campaign_evidence_manifest_sha256": source_campaign.evidence_manifest_sha256,
        "source_calibration_content_sha256": _partition_sha256(evidence, "calibration"),
        "source_historical_heldout_verified": True,
        "source_historical_heldout_used_for_fit": False,
        "calibration_fit_id": fit.calibration_fit_id,
        "fit_policy_sha256": fit.policy_sha256,
        "fit_evidence_manifest_sha256": fit_package.fit_evidence_manifest_sha256,
        "adapter_bundle_id": adapter.adapter_bundle_id,
        "adapter_policy_sha256": adapter.adapter_policy_sha256,
        "adapter_manifest_sha256": adapter_package.adapter_manifest_sha256,
        "adapter_specification_sha256": adapter.specification_sha256,
        "simulator_semantics_sha256": adapter.simulator_semantics_sha256,
        "plan_sha256": plan.semantic_sha256,
        "transfer_contract_sha256": contract.semantic_sha256,
        "planned_evaluation_campaign_id": plan.planned_evaluation_campaign_id,
        "planned_collection_start_utc": plan.planned_collection_start_utc,
        "planned_collection_end_utc": plan.planned_collection_end_utc,
        "planned_cell_count": len(plan.cells),
        "planned_time_block_count": sum(len(item.planned_blocks) for item in plan.cells),
        "chronology_consistent": True,
        "registration_time_externally_attested": False,
        "upstream_chain_verified": True,
        "prediction_formula_frozen": True,
        "operational_outcome_extension_enabled": False,
        "implementation": implementation,
        "implementation_sha256": implementation_sha256,
        "execution_chain_ready": False,
        "external_validation": False,
        "scientific_use_authorized": False,
        "runner_authorized": False,
    }
    identity_payload = dict(values)
    identity_payload["implementation"] = visible_implementation
    identity = _sha256_bytes(_canonical_json_bytes(identity_payload))[:20]
    return SuccessorRegistration(
        registration_id=f"successor-registration-{identity}",
        **values,  # type: ignore[arg-type]
    )


def _registration_from_mapping(value: object) -> SuccessorRegistration:
    fields = set(SuccessorRegistration.__dataclass_fields__)
    selected = _exact_keys(value, fields, "successor registration")
    implementation_raw = selected["implementation"]
    if not isinstance(implementation_raw, list):
        raise TypeError("registration implementation must be an array")
    implementation: list[tuple[str, str]] = []
    for item in implementation_raw:
        record = _exact_keys(item, {"path", "sha256"}, "implementation record")
        path = record["path"]
        if not isinstance(path, str) or not path or path.startswith(("/", "~")):
            raise ValueError("implementation path must be package-relative")
        implementation.append((path, _sha256(record["sha256"], "implementation hash")))
    return SuccessorRegistration(
        schema_version=_string(selected["schema_version"], "schema_version"),
        registration_id=_identifier(selected["registration_id"], "registration_id"),
        registered_at_utc=_string(selected["registered_at_utc"], "registered_at_utc"),
        registration_mode=_string(  # type: ignore[arg-type]
            selected["registration_mode"], "registration_mode"
        ),
        source_campaign_id=_identifier(selected["source_campaign_id"], "source_campaign_id"),
        source_dataset_id=_identifier(selected["source_dataset_id"], "source_dataset_id"),
        source_campaign_evidence_manifest_sha256=_sha256(
            selected["source_campaign_evidence_manifest_sha256"], "source campaign hash"
        ),
        source_calibration_content_sha256=_sha256(
            selected["source_calibration_content_sha256"], "calibration content hash"
        ),
        source_historical_heldout_verified=_strict_bool(
            selected["source_historical_heldout_verified"], "historical heldout verified"
        ),
        source_historical_heldout_used_for_fit=_strict_bool(
            selected["source_historical_heldout_used_for_fit"], "historical heldout used"
        ),
        calibration_fit_id=_identifier(selected["calibration_fit_id"], "calibration_fit_id"),
        fit_policy_sha256=_sha256(selected["fit_policy_sha256"], "fit policy hash"),
        fit_evidence_manifest_sha256=_sha256(
            selected["fit_evidence_manifest_sha256"], "fit evidence hash"
        ),
        adapter_bundle_id=_identifier(selected["adapter_bundle_id"], "adapter_bundle_id"),
        adapter_policy_sha256=_sha256(selected["adapter_policy_sha256"], "adapter policy hash"),
        adapter_manifest_sha256=_sha256(
            selected["adapter_manifest_sha256"], "adapter manifest hash"
        ),
        adapter_specification_sha256=_sha256(
            selected["adapter_specification_sha256"], "adapter specification hash"
        ),
        simulator_semantics_sha256=_sha256(
            selected["simulator_semantics_sha256"], "simulator semantics hash"
        ),
        plan_sha256=_sha256(selected["plan_sha256"], "plan hash"),
        transfer_contract_sha256=_sha256(
            selected["transfer_contract_sha256"], "transfer contract hash"
        ),
        planned_evaluation_campaign_id=_identifier(
            selected["planned_evaluation_campaign_id"], "planned evaluation campaign ID"
        ),
        planned_collection_start_utc=_string(
            selected["planned_collection_start_utc"], "planned collection start"
        ),
        planned_collection_end_utc=_string(
            selected["planned_collection_end_utc"], "planned collection end"
        ),
        planned_cell_count=_integer(
            selected["planned_cell_count"], "planned cell count", minimum=1
        ),
        planned_time_block_count=_integer(
            selected["planned_time_block_count"], "planned time-block count", minimum=1
        ),
        chronology_consistent=_strict_bool(
            selected["chronology_consistent"], "chronology consistent"
        ),
        registration_time_externally_attested=_strict_bool(
            selected["registration_time_externally_attested"],
            "registration time externally attested",
        ),
        upstream_chain_verified=_strict_bool(
            selected["upstream_chain_verified"], "upstream chain verified"
        ),
        prediction_formula_frozen=_strict_bool(
            selected["prediction_formula_frozen"], "prediction formula frozen"
        ),
        operational_outcome_extension_enabled=_strict_bool(
            selected["operational_outcome_extension_enabled"],
            "operational outcome extension enabled",
        ),
        implementation=tuple(implementation),
        implementation_sha256=_sha256(selected["implementation_sha256"], "implementation hash"),
        execution_chain_ready=_strict_bool(
            selected["execution_chain_ready"], "execution chain ready"
        ),
        external_validation=_strict_bool(selected["external_validation"], "external validation"),
        scientific_use_authorized=_strict_bool(
            selected["scientific_use_authorized"], "scientific use authorized"
        ),
        runner_authorized=_strict_bool(selected["runner_authorized"], "runner authorized"),
    )


def _validate_registration_package_snapshot(
    package: SuccessorRegistrationPackageVerification,
) -> None:
    package_bytes = _snapshot_package(
        package.package_dir,
        expected_files=REGISTRATION_PACKAGE_FILES,
        manifest_name="registration_manifest.json",
        expected_manifest_sha256=package.registration_manifest_sha256,
        maximum_package_bytes=_MAX_PACKAGE_BYTES,
    )
    if (
        _read_json_bytes(
            package_bytes["registration_plan_schema.json"], "registration_plan_schema.json"
        )
        != successor_registration_plan_schema()
    ):
        raise ValueError("registration wrapper retained plan schema differs")
    if (
        _read_json_bytes(
            package_bytes["transfer_contract_schema.json"], "transfer_contract_schema.json"
        )
        != transfer_contract_schema()
    ):
        raise ValueError("registration wrapper retained contract schema differs")
    if (
        _read_json_bytes(package_bytes["registration_schema.json"], "registration_schema.json")
        != successor_registration_schema()
    ):
        raise ValueError("registration wrapper retained registration schema differs")
    retained_plan = SuccessorRegistrationPlan.from_mapping(
        _read_json_bytes(package_bytes["registration_plan.json"], "registration_plan.json")
    )
    retained_contract = ResourceArrivalTransferContract.from_mapping(
        _read_json_bytes(package_bytes["transfer_contract.json"], "transfer_contract.json")
    )
    retained_registration = _registration_from_mapping(
        _read_json_bytes(package_bytes["registration.json"], "registration.json")
    )
    if (
        retained_plan.to_dict() != package.plan.to_dict()
        or retained_contract.to_dict() != package.contract.to_dict()
        or retained_registration.to_dict() != package.registration.to_dict()
    ):
        raise ValueError("registration wrapper differs from its externally bound package")
    manifest = _read_json_bytes(
        package_bytes["registration_manifest.json"], "registration_manifest.json"
    )
    _verify_manifest(
        manifest,
        package_bytes,
        manifest_name="registration_manifest.json",
        package_type="successor_registration",
        identity_field="registration_id",
        identity_value=retained_registration.registration_id,
    )


def bind_successor_evaluation_inputs(
    registration_package: SuccessorRegistrationPackageVerification,
    evaluation_campaign: CampaignPackageVerification,
) -> SuccessorEvaluationInputs:
    """Bind a realized distinct campaign without authorizing outcome access."""

    if not registration_package.externally_digest_bound:
        raise ValueError("evaluation binding requires an externally bound registration")
    _validate_registration_package_snapshot(registration_package)
    if not evaluation_campaign.externally_digest_bound:
        raise ValueError("evaluation binding requires an externally bound campaign")
    evaluation_campaign = _validate_campaign_package_snapshot(evaluation_campaign)
    if evaluation_campaign.external_validation or evaluation_campaign.scientific_use_authorized:
        raise ValueError("evaluation campaign exceeds the engineering boundary")
    registration = registration_package.registration
    plan = registration_package.plan
    contract = registration_package.contract
    planned_block_count = sum(len(cell.planned_blocks) for cell in plan.cells)
    if (
        plan.semantic_sha256 != registration.plan_sha256
        or contract.semantic_sha256 != registration.transfer_contract_sha256
        or plan.registration_mode != registration.registration_mode
        or contract.contract_mode != registration.registration_mode
        or plan.planned_evaluation_campaign_id != registration.planned_evaluation_campaign_id
        or plan.planned_collection_start_utc != registration.planned_collection_start_utc
        or plan.planned_collection_end_utc != registration.planned_collection_end_utc
        or len(plan.cells) != registration.planned_cell_count
        or planned_block_count != registration.planned_time_block_count
    ):
        raise ValueError("registration wrapper differs from its frozen plan or transfer contract")
    if (
        registration.registration_mode == "prospective_transfer"
        and evaluation_campaign.evidence_scope == "synthetic_or_mixed_interface_only"
    ):
        raise ValueError("prospective evaluation inputs require nonsynthetic campaign evidence")
    evidence = evaluation_campaign.evidence_manifest
    campaign_id = _identifier(evidence.get("campaign_id"), "evaluation campaign_id")
    if campaign_id != plan.planned_evaluation_campaign_id:
        raise ValueError("realized evaluation campaign does not match registration")
    if campaign_id == registration.source_campaign_id:
        raise ValueError("evaluation campaign cannot reuse the source campaign")
    manifest = _campaign_manifest(evaluation_campaign)
    realized_start = _timestamp_without_submicrosecond(
        manifest["collection_start"], "realized collection start"
    )
    realized_end = _timestamp_without_submicrosecond(
        manifest["collection_end"], "realized collection end"
    )
    if _timestamp_value(realized_start) <= _timestamp_value(registration.registered_at_utc):
        raise ValueError("registration must precede realized evaluation collection")
    if _timestamp_value(realized_start) < _timestamp_value(plan.planned_collection_start_utc):
        raise ValueError("realized collection starts before the registered window")
    if _timestamp_value(realized_end) > _timestamp_value(plan.planned_collection_end_utc):
        raise ValueError("realized collection ends after the registered window")
    heldout = evaluation_campaign.heldout
    if set(heldout["partition"].astype(str)) != {"heldout"}:
        raise ValueError("evaluation input contains a non-heldout row")
    realized_blocks = set(heldout["time_block_id"].astype(str))
    planned_design = {
        block.time_block_id: block for cell in plan.cells for block in cell.planned_blocks
    }
    planned_blocks = set(planned_design)
    if realized_blocks != planned_blocks:
        raise ValueError(
            "realized heldout blocks differ from registration: "
            f"missing={sorted(planned_blocks - realized_blocks)}, "
            f"extra={sorted(realized_blocks - planned_blocks)}"
        )
    per_block_resources = heldout.groupby("time_block_id")["resource_type"].nunique()
    if set(per_block_resources.astype(int)) != {len(ResourceType)}:
        raise ValueError("every realized time block must contain exactly ten resources")
    for block_id, expected in planned_design.items():
        block = heldout[heldout["time_block_id"].astype(str) == block_id]
        timestamp = block["timestamp"].iloc[0]
        if int(getattr(timestamp, "nanosecond", 0)) != 0:
            raise ValueError(
                f"realized timestamp has sub-microsecond precision for block {block_id}"
            )
        realized_timestamp = timestamp.isoformat(timespec="microseconds").replace("+00:00", "Z")
        realized = (
            realized_timestamp,
            int(block["fleet_size"].iloc[0]),
            int(block["agents_admitted"].iloc[0]),
            float(block["window_duration_ms"].iloc[0]),
        )
        planned = (
            expected.timestamp_utc,
            expected.fleet_size,
            expected.agents_admitted,
            expected.window_duration_ms,
        )
        if realized != planned:
            raise ValueError(
                f"realized predictor design differs from registration for block {block_id}"
            )
    values: dict[str, object] = {
        "schema_version": PROTOCOL_SCHEMA_VERSION,
        "registration_id": registration.registration_id,
        "registration_manifest_sha256": registration_package.registration_manifest_sha256,
        "evaluation_campaign_id": campaign_id,
        "evaluation_campaign_evidence_manifest_sha256": (
            evaluation_campaign.evidence_manifest_sha256
        ),
        "evaluation_heldout_content_sha256": _partition_sha256(evidence, "heldout"),
        "realized_cell_count": len(plan.cells),
        "realized_time_block_count": len(realized_blocks),
        "realized_cells": plan.cells,
        "campaign_identity_reconciled": True,
        "collection_window_reconciled": True,
        "cell_block_reconciliation": "exact",
        "predictor_design_reconciled": True,
        "chronology_consistent": True,
        "registration_time_externally_attested": False,
        "prediction_formula_frozen": registration.prediction_formula_frozen,
        "prediction_rows_preoutcome_locked": False,
        "outcome_release_custody_verified": False,
        "execution_chain_ready": False,
        "external_validation": False,
        "scientific_use_authorized": False,
        "runner_authorized": False,
    }
    identity_payload = dict(values)
    identity_payload["realized_cells"] = [item.to_dict() for item in plan.cells]
    identity = _sha256_bytes(_canonical_json_bytes(identity_payload))[:20]
    return SuccessorEvaluationInputs(
        evaluation_input_id=f"successor-evaluation-inputs-{identity}",
        **values,  # type: ignore[arg-type]
    )


def _evaluation_inputs_from_mapping(value: object) -> SuccessorEvaluationInputs:
    fields = set(SuccessorEvaluationInputs.__dataclass_fields__)
    selected = _exact_keys(value, fields, "successor evaluation inputs")
    cells_raw = selected["realized_cells"]
    if not isinstance(cells_raw, list):
        raise TypeError("realized_cells must be an array")
    return SuccessorEvaluationInputs(
        schema_version=_string(selected["schema_version"], "schema_version"),
        evaluation_input_id=_identifier(selected["evaluation_input_id"], "evaluation_input_id"),
        registration_id=_identifier(selected["registration_id"], "registration_id"),
        registration_manifest_sha256=_sha256(
            selected["registration_manifest_sha256"], "registration manifest hash"
        ),
        evaluation_campaign_id=_identifier(
            selected["evaluation_campaign_id"], "evaluation campaign ID"
        ),
        evaluation_campaign_evidence_manifest_sha256=_sha256(
            selected["evaluation_campaign_evidence_manifest_sha256"],
            "evaluation campaign evidence hash",
        ),
        evaluation_heldout_content_sha256=_sha256(
            selected["evaluation_heldout_content_sha256"], "evaluation heldout hash"
        ),
        realized_cell_count=_integer(
            selected["realized_cell_count"], "realized cell count", minimum=1
        ),
        realized_time_block_count=_integer(
            selected["realized_time_block_count"], "realized time-block count", minimum=1
        ),
        realized_cells=tuple(PlannedEvaluationCell.from_mapping(item) for item in cells_raw),
        campaign_identity_reconciled=_strict_bool(
            selected["campaign_identity_reconciled"], "campaign identity reconciled"
        ),
        collection_window_reconciled=_strict_bool(
            selected["collection_window_reconciled"], "collection window reconciled"
        ),
        cell_block_reconciliation=_string(  # type: ignore[arg-type]
            selected["cell_block_reconciliation"], "cell block reconciliation"
        ),
        predictor_design_reconciled=_strict_bool(
            selected["predictor_design_reconciled"], "predictor design reconciled"
        ),
        chronology_consistent=_strict_bool(
            selected["chronology_consistent"], "chronology consistent"
        ),
        registration_time_externally_attested=_strict_bool(
            selected["registration_time_externally_attested"],
            "registration time externally attested",
        ),
        prediction_formula_frozen=_strict_bool(
            selected["prediction_formula_frozen"], "prediction formula frozen"
        ),
        prediction_rows_preoutcome_locked=_strict_bool(
            selected["prediction_rows_preoutcome_locked"],
            "prediction rows preoutcome locked",
        ),
        outcome_release_custody_verified=_strict_bool(
            selected["outcome_release_custody_verified"],
            "outcome release custody verified",
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


def _digest_schema() -> dict[str, object]:
    return {"type": "string", "pattern": "^[0-9a-f]{64}$"}


def _identifier_schema() -> dict[str, object]:
    return {
        "type": "string",
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
    }


def _timestamp_schema() -> dict[str, object]:
    return {
        "type": "string",
        "format": "date-time",
        "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$",
    }


def _closed_object(
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


def transfer_contract_schema() -> dict[str, object]:
    """Return the closed resource-arrival transfer-contract schema."""

    thresholds = _closed_object(
        {
            "maximum_duration_weighted_nrmse": {
                "type": ["number", "null"],
                "minimum": 0.0,
            },
            "maximum_absolute_duration_weighted_relative_bias": {
                "type": ["number", "null"],
                "minimum": 0.0,
            },
            "minimum_candidate_relative_improvement": {
                "type": ["number", "null"],
                "minimum": 0.0,
            },
            "minimum_valid_time_blocks_per_cell": {
                "type": ["integer", "null"],
                "minimum": 1,
            },
            "require_every_resource": {"const": True},
        }
    )
    properties: dict[str, object] = {
        "schema_version": {"const": PROTOCOL_SCHEMA_VERSION},
        "contract_id": _identifier_schema(),
        "contract_mode": {"enum": ["engineering_dry_run", "prospective_transfer"]},
        "primary_estimand": {"const": PRIMARY_ESTIMAND},
        "prediction_formula": {"const": PREDICTION_FORMULA},
        "predictor_fields": {
            "type": "array",
            "prefixItems": [{"const": item} for item in PREDICTOR_FIELDS],
            "minItems": len(PREDICTOR_FIELDS),
            "maxItems": len(PREDICTOR_FIELDS),
        },
        "outcome_field": {"const": "arrival_count"},
        "resource_types": {
            "type": "array",
            "minItems": len(ResourceType),
            "maxItems": len(ResourceType),
            "uniqueItems": True,
            "items": {"enum": sorted(item.value for item in ResourceType)},
            "allOf": [
                {
                    "contains": {"const": item.value},
                    "minContains": 1,
                    "maxContains": 1,
                }
                for item in ResourceType
            ],
        },
        "comparator": {"const": COMPARATOR},
        "metrics": {
            "type": "array",
            "prefixItems": [{"const": item} for item in METRICS],
            "minItems": len(METRICS),
            "maxItems": len(METRICS),
        },
        "uncertainty_method": {"const": UNCERTAINTY_METHOD},
        "uncertainty_scope": {"const": UNCERTAINTY_SCOPE},
        "criteria_frozen": {"type": "boolean"},
        "thresholds": thresholds,
        "operational_outcome_extension_enabled": {"const": False},
        "prediction_rows_preoutcome_lock_required": {"const": True},
        "outcome_custody_evidence_required": {"const": True},
        "external_validation": {"const": False},
        "scientific_use_authorized": {"const": False},
        "runner_authorized": {"const": False},
    }
    schema = _closed_object(properties, title="Successor resource-arrival transfer contract")
    schema.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://fleet-assurance.local/schemas/successor_transfer_contract.schema.json",
            "allOf": [
                {
                    "if": {
                        "properties": {"contract_mode": {"const": "prospective_transfer"}},
                        "required": ["contract_mode"],
                    },
                    "then": {
                        "properties": {
                            "criteria_frozen": {"const": True},
                            "thresholds": _closed_object(
                                {
                                    "maximum_duration_weighted_nrmse": {
                                        "type": "number",
                                        "minimum": 0.0,
                                    },
                                    "maximum_absolute_duration_weighted_relative_bias": {
                                        "type": "number",
                                        "minimum": 0.0,
                                    },
                                    "minimum_candidate_relative_improvement": {
                                        "type": "number",
                                        "minimum": 0.0,
                                    },
                                    "minimum_valid_time_blocks_per_cell": {
                                        "type": "integer",
                                        "minimum": 1,
                                    },
                                    "require_every_resource": {"const": True},
                                }
                            ),
                        }
                    },
                }
            ],
        }
    )
    return schema


def _cell_schema() -> dict[str, object]:
    block = _closed_object(
        {
            "time_block_id": _identifier_schema(),
            "timestamp_utc": _timestamp_schema(),
            "fleet_size": {"type": "integer", "minimum": 1},
            "agents_admitted": {"type": "integer", "minimum": 0},
            "window_duration_ms": {
                "type": "number",
                "exclusiveMinimum": 0.0,
                "multipleOf": 0.001,
            },
        }
    )
    return _closed_object(
        {
            "cell_id": _identifier_schema(),
            "planned_blocks": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": block,
            },
        }
    )


def successor_registration_plan_schema() -> dict[str, object]:
    """Return the closed pre-collection study-plan schema."""

    schema = _closed_object(
        {
            "schema_version": {"const": PROTOCOL_SCHEMA_VERSION},
            "plan_id": _identifier_schema(),
            "study_id": _identifier_schema(),
            "registration_mode": {"enum": ["engineering_dry_run", "prospective_transfer"]},
            "planned_evaluation_campaign_id": _identifier_schema(),
            "planned_collection_start_utc": _timestamp_schema(),
            "planned_collection_end_utc": _timestamp_schema(),
            "cells": {
                "type": "array",
                "minItems": 1,
                "items": _cell_schema(),
            },
            "one_shot_evaluation": {"const": True},
            "deviation_policy": {"const": "fail_closed"},
            "prediction_lock_required": {"const": True},
            "outcome_custody_required": {"const": True},
        },
        title="Successor prospective registration plan",
    )
    schema.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://fleet-assurance.local/schemas/successor_registration_plan.schema.json",
        }
    )
    return schema


def _implementation_schema() -> dict[str, object]:
    return {
        "type": "array",
        "minItems": 5,
        "maxItems": 5,
        "uniqueItems": True,
        "items": _closed_object(
            {
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 256,
                    "pattern": r"^(?![A-Za-z]:)(?![/~])(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9._/-]+$",
                },
                "sha256": _digest_schema(),
            }
        ),
    }


def successor_registration_schema() -> dict[str, object]:
    """Return the closed frozen-registration schema."""

    identifier_fields = {
        "registration_id",
        "source_campaign_id",
        "source_dataset_id",
        "calibration_fit_id",
        "adapter_bundle_id",
        "planned_evaluation_campaign_id",
    }
    digest_fields = {
        "source_campaign_evidence_manifest_sha256",
        "source_calibration_content_sha256",
        "fit_policy_sha256",
        "fit_evidence_manifest_sha256",
        "adapter_policy_sha256",
        "adapter_manifest_sha256",
        "adapter_specification_sha256",
        "simulator_semantics_sha256",
        "plan_sha256",
        "transfer_contract_sha256",
        "implementation_sha256",
    }
    properties: dict[str, object] = {field: _identifier_schema() for field in identifier_fields}
    properties.update({field: _digest_schema() for field in digest_fields})
    properties.update(
        {
            "schema_version": {"const": PROTOCOL_SCHEMA_VERSION},
            "registration_id": {
                "type": "string",
                "pattern": "^successor-registration-[0-9a-f]{20}$",
            },
            "registered_at_utc": _timestamp_schema(),
            "registration_mode": {"enum": ["engineering_dry_run", "prospective_transfer"]},
            "planned_collection_start_utc": _timestamp_schema(),
            "planned_collection_end_utc": _timestamp_schema(),
            "source_historical_heldout_verified": {"const": True},
            "source_historical_heldout_used_for_fit": {"const": False},
            "planned_cell_count": {"type": "integer", "minimum": 1},
            "planned_time_block_count": {"type": "integer", "minimum": 1},
            "chronology_consistent": {"const": True},
            "registration_time_externally_attested": {"const": False},
            "upstream_chain_verified": {"const": True},
            "prediction_formula_frozen": {"const": True},
            "operational_outcome_extension_enabled": {"const": False},
            "implementation": _implementation_schema(),
            "execution_chain_ready": {"const": False},
            "external_validation": {"const": False},
            "scientific_use_authorized": {"const": False},
            "runner_authorized": {"const": False},
        }
    )
    schema = _closed_object(properties, title="Frozen successor study registration")
    schema.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://fleet-assurance.local/schemas/successor_registration.schema.json",
        }
    )
    return schema


def successor_evaluation_inputs_schema() -> dict[str, object]:
    """Return the closed realized-evaluation-input binding schema."""

    schema = _closed_object(
        {
            "schema_version": {"const": PROTOCOL_SCHEMA_VERSION},
            "evaluation_input_id": {
                "type": "string",
                "pattern": "^successor-evaluation-inputs-[0-9a-f]{20}$",
            },
            "registration_id": _identifier_schema(),
            "registration_manifest_sha256": _digest_schema(),
            "evaluation_campaign_id": _identifier_schema(),
            "evaluation_campaign_evidence_manifest_sha256": _digest_schema(),
            "evaluation_heldout_content_sha256": _digest_schema(),
            "realized_cell_count": {"type": "integer", "minimum": 1},
            "realized_time_block_count": {"type": "integer", "minimum": 1},
            "realized_cells": {
                "type": "array",
                "minItems": 1,
                "items": _cell_schema(),
            },
            "campaign_identity_reconciled": {"const": True},
            "collection_window_reconciled": {"const": True},
            "cell_block_reconciliation": {"const": "exact"},
            "predictor_design_reconciled": {"const": True},
            "chronology_consistent": {"const": True},
            "registration_time_externally_attested": {"const": False},
            "prediction_formula_frozen": {"const": True},
            "prediction_rows_preoutcome_locked": {"const": False},
            "outcome_release_custody_verified": {"const": False},
            "execution_chain_ready": {"const": False},
            "external_validation": {"const": False},
            "scientific_use_authorized": {"const": False},
            "runner_authorized": {"const": False},
        },
        title="Successor realized evaluation-input binding",
    )
    schema.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://fleet-assurance.local/schemas/successor_evaluation_inputs.schema.json",
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


def _package_manifest(
    *,
    package_type: str,
    identity_field: str,
    identity_value: str,
    artifacts: Sequence[Path],
) -> dict[str, object]:
    manifest: dict[str, object] = {
        "schema_version": PROTOCOL_SCHEMA_VERSION,
        "package_type": package_type,
        identity_field: identity_value,
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
            raise ValueError("output must be outside every source evidence package")


def _rename_noreplace(source: Path, destination: Path) -> None:
    """Atomically publish one directory without replacing an existing path."""

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
        raise FileExistsError(error, "refusing to overwrite evidence package", destination)
    raise OSError(error, os.strerror(error), destination)


def _write_atomic_package(
    destination: Path,
    *,
    lock_suffix: str,
    expected_files: set[str],
    build: Any,
) -> Path:
    if os.path.lexists(destination):
        raise FileExistsError(f"refusing to overwrite evidence package: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock_path = destination.parent / f".{destination.name}.{lock_suffix}.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise FileExistsError(f"evidence package is locked: {destination}") from exc
    temporary: Path | None = None
    try:
        if os.path.lexists(destination):
            raise FileExistsError(f"refusing to overwrite evidence package: {destination}")
        temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
        build(temporary)
        entries = list(temporary.iterdir())
        if {path.name for path in entries} != expected_files or any(
            path.is_symlink() or not path.is_file() for path in entries
        ):
            raise RuntimeError("evidence package construction is incomplete")
        if os.path.lexists(destination):
            raise FileExistsError(f"refusing to overwrite evidence package: {destination}")
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


def _snapshot_package(
    package: Path,
    *,
    expected_files: set[str],
    manifest_name: str,
    expected_manifest_sha256: str | None,
    maximum_package_bytes: int,
) -> dict[str, bytes]:
    if maximum_package_bytes <= 0:
        raise ValueError("maximum_package_bytes must be positive")
    if package.is_symlink():
        raise ValueError("evidence package cannot be a symlink")
    if not package.is_dir():
        raise FileNotFoundError(package)
    entries = list(package.iterdir())
    if {entry.name for entry in entries} != expected_files:
        raise ValueError("evidence package file set mismatch")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise ValueError("evidence package entries must be regular local files")
    expected = (
        None
        if expected_manifest_sha256 is None
        else _sha256(expected_manifest_sha256, "expected evidence manifest hash")
    )
    manifest = _read_bounded_file(package / manifest_name, maximum_package_bytes)
    if expected is not None and _sha256_bytes(manifest) != expected:
        raise ValueError("evidence manifest does not match the externally supplied digest")
    retained = {manifest_name: manifest}
    remaining = maximum_package_bytes - len(manifest)
    for name in sorted(expected_files - {manifest_name}):
        artifact = _read_bounded_file(package / name, remaining)
        retained[name] = artifact
        remaining -= len(artifact)
    final_entries = list(package.iterdir())
    if {entry.name for entry in final_entries} != expected_files or any(
        entry.is_symlink() or not entry.is_file() for entry in final_entries
    ):
        raise ValueError("evidence package changed while being read")
    return retained


def _verify_manifest(
    manifest: Mapping[str, object],
    package_bytes: Mapping[str, bytes],
    *,
    manifest_name: str,
    package_type: str,
    identity_field: str,
    identity_value: str,
) -> None:
    expected_fields = {
        "schema_version",
        "package_type",
        identity_field,
        "execution_chain_ready",
        "external_validation",
        "scientific_use_authorized",
        "runner_authorized",
        "artifacts",
        "self_integrity_sha256",
    }
    selected = _exact_keys(manifest, expected_fields, "evidence manifest")
    if selected["schema_version"] != PROTOCOL_SCHEMA_VERSION:
        raise ValueError("evidence manifest schema version differs")
    if selected["package_type"] != package_type:
        raise ValueError("evidence manifest package type differs")
    if selected[identity_field] != identity_value:
        raise ValueError("evidence manifest identity differs")
    for field in (
        "execution_chain_ready",
        "external_validation",
        "scientific_use_authorized",
        "runner_authorized",
    ):
        if _strict_bool(selected[field], field):
            raise ValueError(f"evidence manifest cannot assert {field}")
    asserted_self = _sha256(selected["self_integrity_sha256"], "manifest self hash")
    without_self = dict(manifest)
    del without_self["self_integrity_sha256"]
    if asserted_self != _sha256_bytes(_canonical_json_bytes(without_self)):
        raise ValueError("evidence manifest self-integrity hash mismatch")
    expected_artifacts = set(package_bytes) - {manifest_name}
    records = selected["artifacts"]
    if not isinstance(records, list) or len(records) != len(expected_artifacts):
        raise ValueError("evidence artifact inventory is incomplete")
    names: set[str] = set()
    for record in records:
        item = _exact_keys(record, {"path", "bytes", "sha256"}, "evidence artifact")
        name = item["path"]
        if (
            not isinstance(name, str)
            or name != Path(name).name
            or name not in expected_artifacts
            or name in names
        ):
            raise ValueError("evidence artifact path is invalid or duplicated")
        names.add(name)
        count = _integer(item["bytes"], f"artifact bytes for {name}")
        if count != len(package_bytes[name]):
            raise ValueError(f"artifact size mismatch: {name}")
        if _sha256(item["sha256"], f"artifact hash for {name}") != _sha256_bytes(
            package_bytes[name]
        ):
            raise ValueError(f"artifact hash mismatch: {name}")
    if names != expected_artifacts:
        raise ValueError("evidence artifact inventory does not cover the package")


def write_successor_registration_package(
    registration: SuccessorRegistration,
    plan: SuccessorRegistrationPlan,
    contract: ResourceArrivalTransferContract,
    output_dir: str | Path,
    *,
    source_campaign: CampaignPackageVerification,
    fit_package: EmpiricalCalibrationPackageVerification,
    adapter_package: AdaptedResourcePackageVerification,
) -> Path:
    """Write a deterministic, immutable seven-file registration package."""

    source_campaign, fit_package, adapter_package = _validate_upstream_package_snapshots(
        source_campaign,
        fit_package,
        adapter_package,
    )
    recomputed = freeze_successor_registration(
        source_campaign,
        fit_package,
        adapter_package,
        plan,
        contract,
        registered_at_utc=registration.registered_at_utc,
    )
    if registration.to_dict() != recomputed.to_dict():
        raise ValueError("registration differs from deterministic upstream recomputation")
    destination = Path(output_dir)
    _assert_output_outside_sources(
        destination,
        (source_campaign.package_dir, fit_package.package_dir, adapter_package.package_dir),
    )

    def build(temporary: Path) -> None:
        registration_path = temporary / "registration.json"
        plan_path = temporary / "registration_plan.json"
        contract_path = temporary / "transfer_contract.json"
        registration_schema_path = temporary / "registration_schema.json"
        plan_schema_path = temporary / "registration_plan_schema.json"
        contract_schema_path = temporary / "transfer_contract_schema.json"
        manifest_path = temporary / "registration_manifest.json"
        _write_json(registration_path, registration.to_dict())
        _write_json(plan_path, plan.to_dict())
        _write_json(contract_path, contract.to_dict())
        _write_json(registration_schema_path, successor_registration_schema())
        _write_json(plan_schema_path, successor_registration_plan_schema())
        _write_json(contract_schema_path, transfer_contract_schema())
        artifacts = (
            registration_path,
            plan_path,
            contract_path,
            registration_schema_path,
            plan_schema_path,
            contract_schema_path,
        )
        _write_json(
            manifest_path,
            _package_manifest(
                package_type="successor_registration",
                identity_field="registration_id",
                identity_value=registration.registration_id,
                artifacts=artifacts,
            ),
        )
        digest = _sha256_path(manifest_path)
        verify_successor_registration_package(
            temporary,
            source_campaign=source_campaign,
            fit_package=fit_package,
            adapter_package=adapter_package,
            expected_registration_manifest_sha256=digest,
        )

    return _write_atomic_package(
        destination,
        lock_suffix="registration",
        expected_files=REGISTRATION_PACKAGE_FILES,
        build=build,
    )


def verify_successor_registration_package(
    package_dir: str | Path,
    *,
    source_campaign: CampaignPackageVerification,
    fit_package: EmpiricalCalibrationPackageVerification,
    adapter_package: AdaptedResourcePackageVerification,
    expected_registration_manifest_sha256: str | None = None,
    maximum_package_bytes: int = _MAX_PACKAGE_BYTES,
) -> SuccessorRegistrationPackageVerification:
    """Verify a registration against exact upstream evidence and local semantics."""

    source_campaign, fit_package, adapter_package = _validate_upstream_package_snapshots(
        source_campaign,
        fit_package,
        adapter_package,
    )
    package = Path(package_dir)
    package_bytes = _snapshot_package(
        package,
        expected_files=REGISTRATION_PACKAGE_FILES,
        manifest_name="registration_manifest.json",
        expected_manifest_sha256=expected_registration_manifest_sha256,
        maximum_package_bytes=maximum_package_bytes,
    )
    plan_schema = _read_json_bytes(
        package_bytes["registration_plan_schema.json"], "registration_plan_schema.json"
    )
    contract_schema = _read_json_bytes(
        package_bytes["transfer_contract_schema.json"], "transfer_contract_schema.json"
    )
    registration_schema = _read_json_bytes(
        package_bytes["registration_schema.json"], "registration_schema.json"
    )
    if plan_schema != successor_registration_plan_schema():
        raise ValueError("retained registration-plan schema differs from implementation")
    if contract_schema != transfer_contract_schema():
        raise ValueError("retained transfer-contract schema differs from implementation")
    if registration_schema != successor_registration_schema():
        raise ValueError("retained registration schema differs from implementation")
    plan = SuccessorRegistrationPlan.from_mapping(
        _read_json_bytes(package_bytes["registration_plan.json"], "registration_plan.json")
    )
    contract = ResourceArrivalTransferContract.from_mapping(
        _read_json_bytes(package_bytes["transfer_contract.json"], "transfer_contract.json")
    )
    registration = _registration_from_mapping(
        _read_json_bytes(package_bytes["registration.json"], "registration.json")
    )
    recomputed = freeze_successor_registration(
        source_campaign,
        fit_package,
        adapter_package,
        plan,
        contract,
        registered_at_utc=registration.registered_at_utc,
    )
    if registration.to_dict() != recomputed.to_dict():
        raise ValueError("registration does not match deterministic upstream recomputation")
    manifest = _read_json_bytes(
        package_bytes["registration_manifest.json"], "registration_manifest.json"
    )
    _verify_manifest(
        manifest,
        package_bytes,
        manifest_name="registration_manifest.json",
        package_type="successor_registration",
        identity_field="registration_id",
        identity_value=registration.registration_id,
    )
    return SuccessorRegistrationPackageVerification(
        package_dir=package.resolve(),
        registration=registration,
        plan=plan,
        contract=contract,
        registration_manifest_sha256=_sha256_bytes(package_bytes["registration_manifest.json"]),
        externally_digest_bound=expected_registration_manifest_sha256 is not None,
    )


def write_successor_evaluation_inputs_package(
    inputs: SuccessorEvaluationInputs,
    output_dir: str | Path,
    *,
    registration_package: SuccessorRegistrationPackageVerification,
    evaluation_campaign: CampaignPackageVerification,
) -> Path:
    """Write a deterministic, immutable three-file realized-input package."""

    recomputed = bind_successor_evaluation_inputs(registration_package, evaluation_campaign)
    if inputs.to_dict() != recomputed.to_dict():
        raise ValueError("evaluation inputs differ from deterministic upstream recomputation")
    destination = Path(output_dir)
    _assert_output_outside_sources(
        destination,
        (registration_package.package_dir, evaluation_campaign.package_dir),
    )

    def build(temporary: Path) -> None:
        inputs_path = temporary / "evaluation_inputs.json"
        schema_path = temporary / "evaluation_inputs_schema.json"
        manifest_path = temporary / "evaluation_inputs_manifest.json"
        _write_json(inputs_path, inputs.to_dict())
        _write_json(schema_path, successor_evaluation_inputs_schema())
        _write_json(
            manifest_path,
            _package_manifest(
                package_type="successor_evaluation_inputs",
                identity_field="evaluation_input_id",
                identity_value=inputs.evaluation_input_id,
                artifacts=(inputs_path, schema_path),
            ),
        )
        digest = _sha256_path(manifest_path)
        verify_successor_evaluation_inputs_package(
            temporary,
            registration_package=registration_package,
            evaluation_campaign=evaluation_campaign,
            expected_evaluation_inputs_manifest_sha256=digest,
        )

    return _write_atomic_package(
        destination,
        lock_suffix="evaluation-inputs",
        expected_files=EVALUATION_INPUT_PACKAGE_FILES,
        build=build,
    )


def verify_successor_evaluation_inputs_package(
    package_dir: str | Path,
    *,
    registration_package: SuccessorRegistrationPackageVerification,
    evaluation_campaign: CampaignPackageVerification,
    expected_evaluation_inputs_manifest_sha256: str | None = None,
    maximum_package_bytes: int = _MAX_PACKAGE_BYTES,
) -> SuccessorEvaluationInputsPackageVerification:
    """Verify a realized-input binding against registration and campaign evidence."""

    package = Path(package_dir)
    package_bytes = _snapshot_package(
        package,
        expected_files=EVALUATION_INPUT_PACKAGE_FILES,
        manifest_name="evaluation_inputs_manifest.json",
        expected_manifest_sha256=expected_evaluation_inputs_manifest_sha256,
        maximum_package_bytes=maximum_package_bytes,
    )
    schema = _read_json_bytes(
        package_bytes["evaluation_inputs_schema.json"], "evaluation_inputs_schema.json"
    )
    if schema != successor_evaluation_inputs_schema():
        raise ValueError("retained evaluation-input schema differs from implementation")
    inputs = _evaluation_inputs_from_mapping(
        _read_json_bytes(package_bytes["evaluation_inputs.json"], "evaluation_inputs.json")
    )
    recomputed = bind_successor_evaluation_inputs(registration_package, evaluation_campaign)
    if inputs.to_dict() != recomputed.to_dict():
        raise ValueError("evaluation inputs do not match upstream evidence and registration")
    manifest = _read_json_bytes(
        package_bytes["evaluation_inputs_manifest.json"], "evaluation_inputs_manifest.json"
    )
    _verify_manifest(
        manifest,
        package_bytes,
        manifest_name="evaluation_inputs_manifest.json",
        package_type="successor_evaluation_inputs",
        identity_field="evaluation_input_id",
        identity_value=inputs.evaluation_input_id,
    )
    return SuccessorEvaluationInputsPackageVerification(
        package_dir=package.resolve(),
        inputs=inputs,
        evaluation_inputs_manifest_sha256=_sha256_bytes(
            package_bytes["evaluation_inputs_manifest.json"]
        ),
        externally_digest_bound=expected_evaluation_inputs_manifest_sha256 is not None,
    )
