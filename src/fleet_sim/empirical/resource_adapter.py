"""Fail-closed adapter from accepted aggregate fits to resource specifications.

The adapter is successor-study engineering infrastructure. It makes every
policy-controlled field needed to construct the current base resource
specifications explicit and records simulator behavior that remains outside that
policy boundary. Generated specifications are never authorized for a
confirmatory or operational run by this component.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, NoReturn

from fleet_sim.control_plane.resource_network import (
    AssuranceResourceSpec,
    OverloadBehavior,
    ResourceType,
    ServiceTimeDistribution,
)
from fleet_sim.empirical.calibration_gate import (
    EmpiricalCalibrationPackageVerification,
    IntervalEstimate,
    ResourceFitResult,
)

ADAPTER_SCHEMA_VERSION = "1.0"
PORTABLE_REFERENCE_PATTERN = (
    r"^(?![Ff][Ii][Ll][Ee]:)(?![/~])(?![A-Za-z]:)(?!.*[\r\n])"
    r"(?!.*\\)(?!.*(?:^|/)\.\.?(?:/|$))\S(?:.*\S)?$"
)
AdapterMode = Literal["interface_verification", "successor_transfer"]
PolicyEvidenceClass = Literal["configured", "inferred", "notional"]
ArrivalCountMode = Literal["poisson_count", "deterministic_expected_count"]
CompletionCountMode = Literal[
    "deterministic_completion_count",
    "poisson_completion_count",
    "gamma_completion_count",
]
IntervalSelection = Literal["point", "lower_interval_bound"]

POLICY_FIELDS = {
    "arrival_count_mode",
    "completion_count_mode",
    "capacity_selection",
    "service_time_selection",
    "max_wait_selection",
    "deadline_semantics",
    "overload_behavior",
    "shedding_threshold",
    "recovery_capacity_multiplier",
}
SIMULATOR_LIMITATIONS = (
    "service_time_mean_ms_is_retained_but_not_consumed_by_the_current_simulator",
    "poisson_completion_count_maps_to_the_legacy_exponential_enum",
    "empirical_arrival_replay_is_not_implemented_and_is_rejected",
    "empirical_service_time_replay_is_not_implemented_and_is_rejected",
    "sybil_restart_and_renewal_workload_multipliers_are_legacy_hard_coded_not_fit_or_policy_bound",
    "closed_loop_admission_thresholds_and_deferred_retry_fraction_are_legacy_hard_coded_not_fit_or_policy_bound",
    "generated_specs_are_engineering_simulation_inputs_only",
)
EVIDENCE_SCOPES = {
    "synthetic_or_mixed_interface_only",
    "measured_input_unreviewed",
    "replayed_input_unreviewed",
    "mixed_nonsynthetic_input_unreviewed",
}
ADAPTER_PACKAGE_FILES = {
    "adapter_manifest.json",
    "adapter_policy.json",
    "adapter_policy_schema.json",
    "assurance_resource_specs.json",
    "assurance_resource_specs_schema.json",
}


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


def _read_bounded_file(path: Path, maximum_bytes: int) -> bytes:
    if maximum_bytes <= 0:
        raise ValueError("maximum file bytes must be positive")
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
                raise ValueError(f"artifact exceeds the byte limit: {path.name}")
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


def _read_json(path: Path, *, maximum_bytes: int = 4 * 1024 * 1024) -> dict[str, Any]:
    return _read_json_bytes(_read_bounded_file(path, maximum_bytes), path.name)


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
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{context} must be a lowercase SHA-256 digest")
    if any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{context} must be a lowercase SHA-256 digest")
    return value


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


def _text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{context} must be a nonempty string")
    return value


def _portable_text(value: object, context: str) -> str:
    selected = _text(value, context)
    if selected != selected.strip() or re.fullmatch(PORTABLE_REFERENCE_PATTERN, selected) is None:
        raise ValueError(f"{context} must be portable and cannot contain a local path")
    return selected


def _positive(value: object, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{context} must be numeric")
    selected = float(value)
    if not math.isfinite(selected) or selected <= 0.0:
        raise ValueError(f"{context} must be finite and positive")
    return selected


def _integer(value: object, context: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{context} must be an integer")
    if value < minimum:
        raise ValueError(f"{context} must be at least {minimum}")
    return value


def _nonnegative(value: object, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{context} must be numeric")
    selected = float(value)
    if not math.isfinite(selected) or selected < 0.0:
        raise ValueError(f"{context} must be finite and nonnegative")
    return selected


@dataclass(frozen=True, slots=True)
class PolicyFieldEvidence:
    field_name: str
    evidence_class: PolicyEvidenceClass
    reference: str

    def __post_init__(self) -> None:
        if self.field_name not in POLICY_FIELDS:
            raise ValueError(f"unsupported policy field evidence: {self.field_name}")
        if self.evidence_class not in {"configured", "inferred", "notional"}:
            raise ValueError("policy evidence class is not supported")
        reference = _portable_text(self.reference, f"{self.field_name} evidence reference")
        if len(reference) > 1024:
            raise ValueError("policy evidence reference cannot exceed 1024 characters")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> PolicyFieldEvidence:
        selected = _exact_keys(
            value,
            {"field_name", "evidence_class", "reference"},
            "policy field evidence",
        )
        return cls(**dict(selected))  # type: ignore[arg-type]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ResourceMappingPolicy:
    resource_id: str
    resource_type: str
    arrival_count_mode: ArrivalCountMode
    completion_count_mode: CompletionCountMode
    capacity_selection: IntervalSelection
    service_time_selection: Literal["point_window_summary"]
    max_wait_selection: IntervalSelection
    deadline_semantics: Literal["maximum_queue_wait_budget"]
    overload_behavior: Literal["queue", "shed", "defer"]
    shedding_threshold: float
    recovery_capacity_multiplier: float
    field_evidence: tuple[PolicyFieldEvidence, ...]

    def __post_init__(self) -> None:
        resource_id = _text(self.resource_id, "resource_id")
        if len(resource_id) > 256:
            raise ValueError("resource_id cannot exceed 256 characters")
        ResourceType(self.resource_type)
        if self.arrival_count_mode not in {
            "poisson_count",
            "deterministic_expected_count",
        }:
            raise ValueError("arrival_count_mode is not supported")
        if self.completion_count_mode not in {
            "deterministic_completion_count",
            "poisson_completion_count",
            "gamma_completion_count",
        }:
            raise ValueError("completion_count_mode is not supported")
        if self.capacity_selection not in {"point", "lower_interval_bound"}:
            raise ValueError("capacity_selection is not supported")
        if self.service_time_selection != "point_window_summary":
            raise ValueError("service_time_selection is not supported")
        if self.max_wait_selection not in {"point", "lower_interval_bound"}:
            raise ValueError("max_wait_selection is not supported")
        if self.deadline_semantics != "maximum_queue_wait_budget":
            raise ValueError("deadline semantics do not support max_wait_s")
        OverloadBehavior(self.overload_behavior)
        _positive(self.shedding_threshold, "shedding_threshold")
        _positive(self.recovery_capacity_multiplier, "recovery_capacity_multiplier")
        evidence_names = {item.field_name for item in self.field_evidence}
        if evidence_names != POLICY_FIELDS or len(self.field_evidence) != len(POLICY_FIELDS):
            raise ValueError("field_evidence must cover every explicit adapter policy field")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> ResourceMappingPolicy:
        expected = set(cls.__dataclass_fields__)
        selected = _exact_keys(value, expected, "resource mapping policy")
        raw_evidence = selected["field_evidence"]
        if not isinstance(raw_evidence, list):
            raise TypeError("field_evidence must be an array")
        return cls(
            resource_id=_text(selected["resource_id"], "resource_id"),
            resource_type=_portable_text(selected["resource_type"], "resource_type"),
            arrival_count_mode=_portable_text(  # type: ignore[arg-type]
                selected["arrival_count_mode"], "arrival_count_mode"
            ),
            completion_count_mode=_portable_text(  # type: ignore[arg-type]
                selected["completion_count_mode"], "completion_count_mode"
            ),
            capacity_selection=_portable_text(  # type: ignore[arg-type]
                selected["capacity_selection"], "capacity_selection"
            ),
            service_time_selection=_portable_text(  # type: ignore[arg-type]
                selected["service_time_selection"], "service_time_selection"
            ),
            max_wait_selection=_portable_text(  # type: ignore[arg-type]
                selected["max_wait_selection"], "max_wait_selection"
            ),
            deadline_semantics=_portable_text(  # type: ignore[arg-type]
                selected["deadline_semantics"], "deadline_semantics"
            ),
            overload_behavior=_portable_text(  # type: ignore[arg-type]
                selected["overload_behavior"], "overload_behavior"
            ),
            shedding_threshold=_positive(selected["shedding_threshold"], "shedding_threshold"),
            recovery_capacity_multiplier=_positive(
                selected["recovery_capacity_multiplier"],
                "recovery_capacity_multiplier",
            ),
            field_evidence=tuple(
                PolicyFieldEvidence.from_mapping(item)
                if isinstance(item, Mapping)
                else (_raise_field_evidence_type())
                for item in raw_evidence
            ),
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["field_evidence"] = [item.to_dict() for item in self.field_evidence]
        return payload


def _raise_field_evidence_type() -> NoReturn:
    raise TypeError("field_evidence entries must be objects")


@dataclass(frozen=True, slots=True)
class ResourceAdapterPolicy:
    policy_id: str
    adapter_mode: AdapterMode
    fit_policy_sha256: str
    simulator_semantics_sha256: str
    target_fleet_size_min: int
    target_fleet_size_max: int
    target_admission_rate_min_per_s: float
    target_admission_rate_max_per_s: float
    no_fallback: Literal[True]
    allowed_source_evidence_scopes: tuple[str, ...]
    resources: tuple[ResourceMappingPolicy, ...]

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
            raise ValueError("adapter policy_id must be a portable identifier")
        if self.adapter_mode not in {"interface_verification", "successor_transfer"}:
            raise ValueError("adapter_mode is not supported")
        _sha256(self.fit_policy_sha256, "fit policy hash")
        _sha256(self.simulator_semantics_sha256, "simulator semantics hash")
        if isinstance(self.target_fleet_size_min, bool) or not isinstance(
            self.target_fleet_size_min, int
        ):
            raise TypeError("target_fleet_size_min must be an integer")
        if isinstance(self.target_fleet_size_max, bool) or not isinstance(
            self.target_fleet_size_max, int
        ):
            raise TypeError("target_fleet_size_max must be an integer")
        if (
            self.target_fleet_size_min < 1
            or self.target_fleet_size_max <= self.target_fleet_size_min
        ):
            raise ValueError("adapter target fleet-size range must have positive width")
        admission_min = _nonnegative(
            self.target_admission_rate_min_per_s,
            "target_admission_rate_min_per_s",
        )
        admission_max = _nonnegative(
            self.target_admission_rate_max_per_s,
            "target_admission_rate_max_per_s",
        )
        if admission_max <= admission_min:
            raise ValueError("adapter target admission-rate range must have positive width")
        if self.no_fallback is not True:
            raise ValueError("adapter policy must be fail-closed with no_fallback=true")
        if not self.allowed_source_evidence_scopes:
            raise ValueError("adapter policy must declare allowed evidence scopes")
        if not set(self.allowed_source_evidence_scopes).issubset(EVIDENCE_SCOPES):
            raise ValueError("adapter policy contains an unsupported evidence scope")
        if len(set(self.allowed_source_evidence_scopes)) != len(
            self.allowed_source_evidence_scopes
        ):
            raise ValueError("allowed evidence scopes cannot contain duplicates")
        resource_types = [item.resource_type for item in self.resources]
        if len(self.resources) != len(ResourceType) or set(resource_types) != {
            item.value for item in ResourceType
        }:
            raise ValueError("adapter policy must cover every resource type exactly once")
        if len({item.resource_id for item in self.resources}) != len(ResourceType):
            raise ValueError("adapter policy resource identifiers must be unique")
        if self.adapter_mode == "successor_transfer" and any(
            evidence.evidence_class == "notional"
            for resource in self.resources
            for evidence in resource.field_evidence
        ):
            raise ValueError("successor_transfer adapter policy cannot contain notional fields")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> ResourceAdapterPolicy:
        selected = _exact_keys(value, set(cls.__dataclass_fields__), "resource adapter policy")
        raw_scopes = selected["allowed_source_evidence_scopes"]
        raw_resources = selected["resources"]
        if not isinstance(raw_scopes, list) or not all(
            isinstance(item, str) for item in raw_scopes
        ):
            raise TypeError("allowed_source_evidence_scopes must be an array of strings")
        if not isinstance(raw_resources, list):
            raise TypeError("adapter resources must be an array")
        resources: list[ResourceMappingPolicy] = []
        for item in raw_resources:
            if not isinstance(item, Mapping):
                raise TypeError("adapter resource entries must be objects")
            resources.append(ResourceMappingPolicy.from_mapping(item))
        return cls(
            policy_id=_portable_text(selected["policy_id"], "adapter policy_id"),
            adapter_mode=_portable_text(  # type: ignore[arg-type]
                selected["adapter_mode"], "adapter_mode"
            ),
            fit_policy_sha256=_sha256(selected["fit_policy_sha256"], "fit policy hash"),
            simulator_semantics_sha256=_sha256(
                selected["simulator_semantics_sha256"], "simulator semantics hash"
            ),
            target_fleet_size_min=_integer(
                selected["target_fleet_size_min"], "target_fleet_size_min", minimum=1
            ),
            target_fleet_size_max=_integer(
                selected["target_fleet_size_max"], "target_fleet_size_max", minimum=1
            ),
            target_admission_rate_min_per_s=_nonnegative(
                selected["target_admission_rate_min_per_s"],
                "target_admission_rate_min_per_s",
            ),
            target_admission_rate_max_per_s=_nonnegative(
                selected["target_admission_rate_max_per_s"],
                "target_admission_rate_max_per_s",
            ),
            no_fallback=selected["no_fallback"],  # type: ignore[arg-type]
            allowed_source_evidence_scopes=tuple(raw_scopes),
            resources=tuple(resources),
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["allowed_source_evidence_scopes"] = list(self.allowed_source_evidence_scopes)
        payload["resources"] = [item.to_dict() for item in self.resources]
        return payload

    @property
    def policy_sha256(self) -> str:
        return _sha256_bytes(_canonical_json_bytes(self.to_dict()))


@dataclass(frozen=True, slots=True)
class VerifiedResourceAdapterPolicy:
    policy: ResourceAdapterPolicy
    policy_sha256: str
    externally_digest_bound: bool


@dataclass(frozen=True, slots=True)
class AdaptedFieldProvenance:
    resource_type: str
    field_name: str
    source: str
    evidence_class: str
    selected_value: float | str
    retained_interval: IntervalEstimate | None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["retained_interval"] = (
            None if self.retained_interval is None else self.retained_interval.to_dict()
        )
        return payload


@dataclass(frozen=True, slots=True)
class AdaptedAssuranceResourceBundle:
    schema_version: str
    adapter_bundle_id: str
    adapter_mode: AdapterMode
    calibration_fit_id: str
    calibration_content_sha256: str
    fit_policy_sha256: str
    fit_evidence_manifest_sha256: str
    adapter_policy_id: str
    adapter_policy_sha256: str
    adapter_implementation_sha256: str
    simulator_semantics_sha256: str
    specification_sha256: str
    evidence_scope: str
    source_package_heldout_verified: bool
    heldout_used_for_adapter: bool
    no_fallback: bool
    external_validation: bool
    scientific_use_authorized: bool
    runner_authorized: bool
    scientific_use: Literal["engineering_simulation_only"]
    simulator_limitations: tuple[str, ...]
    resources: tuple[AssuranceResourceSpec, ...]
    field_provenance: tuple[AdaptedFieldProvenance, ...]

    def specifications_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "adapter_bundle_id": self.adapter_bundle_id,
            "resource_count": len(self.resources),
            "resources": [item.to_dict() for item in self.resources],
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "adapter_bundle_id": self.adapter_bundle_id,
            "adapter_mode": self.adapter_mode,
            "calibration_fit_id": self.calibration_fit_id,
            "calibration_content_sha256": self.calibration_content_sha256,
            "fit_policy_sha256": self.fit_policy_sha256,
            "fit_evidence_manifest_sha256": self.fit_evidence_manifest_sha256,
            "adapter_policy_id": self.adapter_policy_id,
            "adapter_policy_sha256": self.adapter_policy_sha256,
            "adapter_implementation_sha256": self.adapter_implementation_sha256,
            "simulator_semantics_sha256": self.simulator_semantics_sha256,
            "specification_sha256": self.specification_sha256,
            "evidence_scope": self.evidence_scope,
            "source_package_heldout_verified": self.source_package_heldout_verified,
            "heldout_used_for_adapter": self.heldout_used_for_adapter,
            "no_fallback": self.no_fallback,
            "external_validation": self.external_validation,
            "scientific_use_authorized": self.scientific_use_authorized,
            "runner_authorized": self.runner_authorized,
            "scientific_use": self.scientific_use,
            "simulator_limitations": list(self.simulator_limitations),
            "resource_count": len(self.resources),
            "field_provenance": [item.to_dict() for item in self.field_provenance],
        }


def current_simulator_semantics_sha256() -> str:
    """Return the exact aggregate simulator implementation digest."""

    package_root = Path(__file__).resolve().parents[1]
    return _sha256_path(package_root / "control_plane" / "resource_network.py")


def load_resource_adapter_policy(
    path: str | Path,
    *,
    expected_policy_sha256: str,
) -> VerifiedResourceAdapterPolicy:
    """Load a closed policy and bind it to an externally supplied digest."""

    selected = Path(path)
    expected = _sha256(expected_policy_sha256, "expected adapter policy hash")
    policy = ResourceAdapterPolicy.from_mapping(_read_json(selected))
    if policy.policy_sha256 != expected:
        raise ValueError("adapter policy does not match the externally supplied digest")
    return VerifiedResourceAdapterPolicy(
        policy=policy,
        policy_sha256=policy.policy_sha256,
        externally_digest_bound=True,
    )


def _select(interval: IntervalEstimate | None, selection: IntervalSelection, field: str) -> float:
    if interval is None:
        raise ValueError(f"accepted fit is missing the {field} interval")
    selected = interval.point if selection == "point" else interval.lower
    if not math.isfinite(selected) or selected <= 0.0:
        raise ValueError(f"selected {field} value is not finite and positive")
    return float(selected)


def _completion_distribution(mode: CompletionCountMode) -> ServiceTimeDistribution:
    return {
        "deterministic_completion_count": ServiceTimeDistribution.DETERMINISTIC,
        "poisson_completion_count": ServiceTimeDistribution.EXPONENTIAL,
        "gamma_completion_count": ServiceTimeDistribution.GAMMA,
    }[mode]


def _arrival_process(mode: ArrivalCountMode) -> Literal["poisson", "scheduled"]:
    return "poisson" if mode == "poisson_count" else "scheduled"


def _policy_evidence(rule: ResourceMappingPolicy) -> dict[str, PolicyFieldEvidence]:
    return {item.field_name: item for item in rule.field_evidence}


def _resource_spec_and_provenance(
    fit: ResourceFitResult,
    rule: ResourceMappingPolicy,
    fit_id: str,
    policy_id: str,
) -> tuple[AssuranceResourceSpec, tuple[AdaptedFieldProvenance, ...]]:
    if fit.gate_status != "passed":
        raise ValueError(f"resource fit is not accepted: {fit.resource_type}")
    if fit.resource_id != rule.resource_id or fit.resource_type != rule.resource_type:
        raise ValueError(f"resource mapping differs between fit and policy: {fit.resource_type}")
    if fit.background_work_per_agent_s is None or fit.admission_work_units_per_agent is None:
        raise ValueError(f"resource fit is missing coefficient intervals: {fit.resource_type}")
    background = float(fit.background_work_per_agent_s.point)
    admission = float(fit.admission_work_units_per_agent.point)
    if not math.isfinite(background) or background < 0.0:
        raise ValueError("background work estimate must be finite and nonnegative")
    if not math.isfinite(admission) or admission <= 0.0:
        raise ValueError("admission work estimate must be finite and positive")
    capacity = _select(
        fit.capacity_units_per_second,
        rule.capacity_selection,
        "capacity_units_per_second",
    )
    if fit.service_time_window_mean_ms is None:
        raise ValueError("accepted fit is missing service-time window summary")
    service_time = float(fit.service_time_window_mean_ms.point)
    if not math.isfinite(service_time) or service_time <= 0.0:
        raise ValueError("service-time window summary must be finite and positive")
    max_wait = _select(fit.max_wait_s, rule.max_wait_selection, "max_wait_s")
    evidence = _policy_evidence(rule)
    policy_classes = {item.evidence_class for item in evidence.values()}
    parameter_class: Literal["measured", "inferred", "notional"]
    if fit.parameter_class == "notional" or "notional" in policy_classes:
        parameter_class = "notional"
    else:
        parameter_class = "inferred"
    provenance_reference = f"fit:{fit_id};policy:{policy_id};resource:{fit.resource_type}"
    spec = AssuranceResourceSpec(
        resource_id=fit.resource_id,
        resource_type=ResourceType(fit.resource_type),
        arrival_process=_arrival_process(rule.arrival_count_mode),
        admission_work_units=admission,
        background_work_per_agent_s=background,
        capacity_units_per_second=capacity,
        service_time_distribution=_completion_distribution(rule.completion_count_mode),
        service_time_mean_ms=service_time,
        max_wait_s=max_wait,
        overload_behavior=OverloadBehavior(rule.overload_behavior),
        shedding_threshold=rule.shedding_threshold,
        recovery_capacity_multiplier=rule.recovery_capacity_multiplier,
        measurement_provenance=provenance_reference,
        parameter_class=parameter_class,
    )
    fitted = (
        AdaptedFieldProvenance(
            fit.resource_type,
            "background_work_per_agent_s",
            "accepted_fit_point",
            "fitted",
            background,
            fit.background_work_per_agent_s,
        ),
        AdaptedFieldProvenance(
            fit.resource_type,
            "admission_work_units",
            "accepted_fit_point",
            "fitted",
            admission,
            fit.admission_work_units_per_agent,
        ),
        AdaptedFieldProvenance(
            fit.resource_type,
            "capacity_units_per_second",
            (
                f"accepted_fit_{rule.capacity_selection};policy:"
                f"{evidence['capacity_selection'].reference}"
            ),
            (f"observed_summary_with_{evidence['capacity_selection'].evidence_class}_selection"),
            capacity,
            fit.capacity_units_per_second,
        ),
        AdaptedFieldProvenance(
            fit.resource_type,
            "service_time_mean_ms",
            (
                "accepted_fit_point_window_summary_retained_not_consumed;policy:"
                f"{evidence['service_time_selection'].reference}"
            ),
            (
                "observed_summary_with_"
                f"{evidence['service_time_selection'].evidence_class}_selection"
            ),
            service_time,
            fit.service_time_window_mean_ms,
        ),
        AdaptedFieldProvenance(
            fit.resource_type,
            "max_wait_s",
            (
                f"accepted_fit_{rule.max_wait_selection};selection_policy:"
                f"{evidence['max_wait_selection'].reference};deadline_policy:"
                f"{evidence['deadline_semantics'].reference}"
            ),
            (f"{evidence['deadline_semantics'].evidence_class}_deadline_semantics"),
            max_wait,
            fit.max_wait_s,
        ),
    )
    configured = tuple(
        AdaptedFieldProvenance(
            fit.resource_type,
            field_name,
            item.reference,
            item.evidence_class,
            (
                float(getattr(rule, field_name))
                if isinstance(getattr(rule, field_name), (int, float))
                else str(getattr(rule, field_name))
            ),
            None,
        )
        for field_name, item in sorted(evidence.items())
        if field_name
        not in {
            "capacity_selection",
            "service_time_selection",
            "max_wait_selection",
            "deadline_semantics",
        }
    )
    return spec, (*fitted, *configured)


def adapt_accepted_fit_to_resource_specs(
    fit_package: EmpiricalCalibrationPackageVerification,
    policy_verification: VerifiedResourceAdapterPolicy,
) -> AdaptedAssuranceResourceBundle:
    """Generate exactly ten specifications without fallback or held-out access."""

    if not fit_package.externally_digest_bound:
        raise ValueError("adapter requires an externally digest-bound fit package")
    if not policy_verification.externally_digest_bound:
        raise ValueError("adapter requires an externally digest-bound policy")
    fit = fit_package.fit
    policy = policy_verification.policy
    if policy_verification.policy_sha256 != policy.policy_sha256:
        raise ValueError("adapter policy semantic hash mismatch")
    if policy.fit_policy_sha256 != fit.policy_sha256:
        raise ValueError("adapter policy is bound to a different fit policy")
    current_simulator = current_simulator_semantics_sha256()
    if policy.simulator_semantics_sha256 != current_simulator:
        raise ValueError("adapter policy is bound to a different simulator implementation")
    if fit.source_evidence_scope not in set(policy.allowed_source_evidence_scopes):
        raise ValueError("fit evidence scope is not allowed by the adapter policy")
    if policy.adapter_mode == "interface_verification":
        if not fit.interface_verification_ready:
            raise ValueError("fit did not pass the interface-verification gate")
    elif not fit.eligible_for_adapter:
        raise ValueError("fit is not eligible for successor-transfer adaptation")
    if fit.runner_authorized or fit.scientific_use_authorized or fit.external_validation:
        raise ValueError("fit package exceeds the permitted engineering evidence scope")
    if len(fit.resources) != len(ResourceType) or {
        item.resource_type for item in fit.resources
    } != {item.value for item in ResourceType}:
        raise ValueError("fit package does not contain exactly ten resource results")
    if policy.target_fleet_size_min < fit.policy.target_fleet_size_min or (
        policy.target_fleet_size_max > fit.policy.target_fleet_size_max
    ):
        raise ValueError("adapter fleet-size domain exceeds the accepted fit domain")
    if policy.target_admission_rate_min_per_s < (
        fit.policy.target_admission_rate_min_per_s
    ) or policy.target_admission_rate_max_per_s > (fit.policy.target_admission_rate_max_per_s):
        raise ValueError("adapter admission-rate domain exceeds the accepted fit domain")
    fits = {item.resource_type: item for item in fit.resources}
    rules = {item.resource_type: item for item in policy.resources}
    resources: list[AssuranceResourceSpec] = []
    provenance: list[AdaptedFieldProvenance] = []
    for resource_type in ResourceType:
        spec, selected_provenance = _resource_spec_and_provenance(
            fits[resource_type.value],
            rules[resource_type.value],
            fit.calibration_fit_id,
            policy.policy_id,
        )
        resources.append(spec)
        provenance.extend(selected_provenance)
    specs_payload = [item.to_dict() for item in resources]
    specification_sha256 = _sha256_bytes(_canonical_json_bytes(specs_payload))
    implementation_sha256 = _sha256_path(Path(__file__).resolve())
    identity = {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "calibration_fit_id": fit.calibration_fit_id,
        "calibration_content_sha256": fit.calibration_content_sha256,
        "fit_policy_sha256": fit.policy_sha256,
        "adapter_policy_sha256": policy.policy_sha256,
        "adapter_implementation_sha256": implementation_sha256,
        "simulator_semantics_sha256": current_simulator,
        "specification_sha256": specification_sha256,
    }
    adapter_id = f"assurance-resource-adapter-{_sha256_bytes(_canonical_json_bytes(identity))[:20]}"
    return AdaptedAssuranceResourceBundle(
        schema_version=ADAPTER_SCHEMA_VERSION,
        adapter_bundle_id=adapter_id,
        adapter_mode=policy.adapter_mode,
        calibration_fit_id=fit.calibration_fit_id,
        calibration_content_sha256=fit.calibration_content_sha256,
        fit_policy_sha256=fit.policy_sha256,
        fit_evidence_manifest_sha256=fit_package.fit_evidence_manifest_sha256,
        adapter_policy_id=policy.policy_id,
        adapter_policy_sha256=policy.policy_sha256,
        adapter_implementation_sha256=implementation_sha256,
        simulator_semantics_sha256=current_simulator,
        specification_sha256=specification_sha256,
        evidence_scope=fit.source_evidence_scope,
        source_package_heldout_verified=fit.source_package_heldout_verified,
        heldout_used_for_adapter=False,
        no_fallback=True,
        external_validation=False,
        scientific_use_authorized=False,
        runner_authorized=False,
        scientific_use="engineering_simulation_only",
        simulator_limitations=SIMULATOR_LIMITATIONS,
        resources=tuple(resources),
        field_provenance=tuple(provenance),
    )


def resource_adapter_policy_schema() -> dict[str, object]:
    """Return the retained closed-shape adapter policy schema."""

    fields = set(ResourceAdapterPolicy.__dataclass_fields__)
    digest = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    field_evidence = {
        "type": "object",
        "required": ["field_name", "evidence_class", "reference"],
        "properties": {
            "field_name": {"enum": sorted(POLICY_FIELDS)},
            "evidence_class": {"enum": ["configured", "inferred", "notional"]},
            "reference": {
                "type": "string",
                "minLength": 1,
                "maxLength": 1024,
                "pattern": PORTABLE_REFERENCE_PATTERN,
            },
        },
        "additionalProperties": False,
    }
    resource_fields = set(ResourceMappingPolicy.__dataclass_fields__)
    resource = {
        "type": "object",
        "required": sorted(resource_fields),
        "properties": {
            "resource_id": {
                "type": "string",
                "minLength": 1,
                "maxLength": 256,
                "pattern": r"\S",
            },
            "resource_type": {"enum": [item.value for item in ResourceType]},
            "arrival_count_mode": {"enum": ["poisson_count", "deterministic_expected_count"]},
            "completion_count_mode": {
                "enum": [
                    "deterministic_completion_count",
                    "poisson_completion_count",
                    "gamma_completion_count",
                ]
            },
            "capacity_selection": {"enum": ["point", "lower_interval_bound"]},
            "service_time_selection": {"const": "point_window_summary"},
            "max_wait_selection": {"enum": ["point", "lower_interval_bound"]},
            "deadline_semantics": {"const": "maximum_queue_wait_budget"},
            "overload_behavior": {"enum": ["queue", "shed", "defer"]},
            "shedding_threshold": {"type": "number", "exclusiveMinimum": 0.0},
            "recovery_capacity_multiplier": {
                "type": "number",
                "exclusiveMinimum": 0.0,
            },
            "field_evidence": {
                "type": "array",
                "minItems": len(POLICY_FIELDS),
                "maxItems": len(POLICY_FIELDS),
                "uniqueItems": True,
                "items": field_evidence,
                "allOf": [
                    {
                        "contains": {
                            "type": "object",
                            "required": ["field_name"],
                            "properties": {"field_name": {"const": field_name}},
                        },
                        "minContains": 1,
                        "maxContains": 1,
                    }
                    for field_name in sorted(POLICY_FIELDS)
                ],
            },
        },
        "additionalProperties": False,
    }
    properties: dict[str, object] = {
        "policy_id": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
        },
        "adapter_mode": {"enum": ["interface_verification", "successor_transfer"]},
        "fit_policy_sha256": digest,
        "simulator_semantics_sha256": digest,
        "target_fleet_size_min": {"type": "integer", "minimum": 1},
        "target_fleet_size_max": {"type": "integer", "minimum": 1},
        "target_admission_rate_min_per_s": {"type": "number", "minimum": 0.0},
        "target_admission_rate_max_per_s": {"type": "number", "minimum": 0.0},
        "no_fallback": {"const": True},
        "allowed_source_evidence_scopes": {
            "type": "array",
            "minItems": 1,
            "maxItems": len(EVIDENCE_SCOPES),
            "uniqueItems": True,
            "items": {"enum": sorted(EVIDENCE_SCOPES)},
        },
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
        "$id": "https://fleet-assurance.local/schemas/assurance_resource_adapter_policy.schema.json",
        "title": "Assurance resource adapter policy",
        "type": "object",
        "required": sorted(fields),
        "properties": properties,
        "additionalProperties": False,
    }


def assurance_resource_specs_schema() -> dict[str, object]:
    """Return the retained closed-shape generated specification schema."""

    resource_fields = {
        "resource_id",
        "resource_type",
        "arrival_process",
        "admission_work_units",
        "background_work_per_agent_s",
        "capacity_units_per_second",
        "service_time_distribution",
        "service_time_mean_ms",
        "max_wait_s",
        "overload_behavior",
        "shedding_threshold",
        "recovery_capacity_multiplier",
        "measurement_provenance",
        "parameter_class",
    }
    positive = {"type": "number", "exclusiveMinimum": 0.0}
    resource = {
        "type": "object",
        "required": sorted(resource_fields),
        "properties": {
            "resource_id": {
                "type": "string",
                "minLength": 1,
                "maxLength": 256,
                "pattern": r"\S",
            },
            "resource_type": {"enum": [item.value for item in ResourceType]},
            "arrival_process": {"enum": ["poisson", "scheduled"]},
            "admission_work_units": positive,
            "background_work_per_agent_s": {"type": "number", "minimum": 0.0},
            "capacity_units_per_second": positive,
            "service_time_distribution": {"enum": ["deterministic", "exponential", "gamma"]},
            "service_time_mean_ms": positive,
            "max_wait_s": positive,
            "overload_behavior": {"enum": ["queue", "shed", "defer"]},
            "shedding_threshold": positive,
            "recovery_capacity_multiplier": positive,
            "measurement_provenance": {
                "type": "string",
                "minLength": 1,
                "maxLength": 2048,
            },
            "parameter_class": {"enum": ["measured", "inferred", "notional"]},
        },
        "additionalProperties": False,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://fleet-assurance.local/schemas/assurance_resource_specs.schema.json",
        "title": "Adapted assurance resource specifications",
        "type": "object",
        "required": [
            "schema_version",
            "adapter_bundle_id",
            "resource_count",
            "resources",
        ],
        "properties": {
            "schema_version": {"const": ADAPTER_SCHEMA_VERSION},
            "adapter_bundle_id": {
                "type": "string",
                "pattern": "^assurance-resource-adapter-[0-9a-f]{20}$",
            },
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
        },
        "additionalProperties": False,
    }


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


def _adapter_manifest(
    bundle: AdaptedAssuranceResourceBundle,
    artifacts: tuple[Path, ...],
) -> dict[str, object]:
    manifest = bundle.to_dict()
    manifest["artifacts"] = [_artifact_record(path) for path in artifacts]
    manifest["self_integrity_sha256"] = _sha256_bytes(_canonical_json_bytes(manifest))
    return manifest


def write_adapted_resource_bundle(
    bundle: AdaptedAssuranceResourceBundle,
    policy_verification: VerifiedResourceAdapterPolicy,
    output_dir: str | Path,
    *,
    fit_package: EmpiricalCalibrationPackageVerification,
) -> Path:
    """Write an atomic, checksum-bound five-file adapter evidence package."""

    if not policy_verification.externally_digest_bound:
        raise ValueError("adapter package writing requires an externally bound policy")
    recomputed = adapt_accepted_fit_to_resource_specs(fit_package, policy_verification)
    if bundle.to_dict() != recomputed.to_dict() or (
        bundle.specifications_dict() != recomputed.specifications_dict()
    ):
        raise ValueError("adapter bundle differs from deterministic recomputation")
    bundle = recomputed
    destination = Path(output_dir)
    resolved_destination = destination.resolve(strict=False)
    source_roots = (
        fit_package.package_dir.resolve(),
        fit_package._source_campaign_package_dir.resolve(),
    )
    if any(
        resolved_destination == root or root in resolved_destination.parents
        for root in source_roots
    ):
        raise ValueError("adapter output must be outside its source evidence packages")
    if os.path.lexists(destination):
        raise FileExistsError(f"refusing to overwrite adapter package: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock_path = destination.parent / f".{destination.name}.adapter.lock"
    try:
        lock_descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise FileExistsError(f"adapter package is locked: {destination}") from exc
    temporary: Path | None = None
    try:
        if os.path.lexists(destination):
            raise FileExistsError(f"refusing to overwrite adapter package: {destination}")
        temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
        policy_path = temporary / "adapter_policy.json"
        policy_schema_path = temporary / "adapter_policy_schema.json"
        specs_path = temporary / "assurance_resource_specs.json"
        specs_schema_path = temporary / "assurance_resource_specs_schema.json"
        manifest_path = temporary / "adapter_manifest.json"
        _write_json(policy_path, policy_verification.policy.to_dict())
        _write_json(policy_schema_path, resource_adapter_policy_schema())
        _write_json(specs_path, bundle.specifications_dict())
        _write_json(specs_schema_path, assurance_resource_specs_schema())
        artifacts = (policy_path, policy_schema_path, specs_path, specs_schema_path)
        _write_json(manifest_path, _adapter_manifest(bundle, artifacts))
        if {path.name for path in temporary.iterdir()} != ADAPTER_PACKAGE_FILES:
            raise RuntimeError("adapter package construction is incomplete")
        if os.path.lexists(destination):
            raise FileExistsError(f"refusing to overwrite adapter package: {destination}")
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


def _verify_artifacts(manifest: Mapping[str, object], package_bytes: Mapping[str, bytes]) -> None:
    records = manifest.get("artifacts")
    expected = ADAPTER_PACKAGE_FILES - {"adapter_manifest.json"}
    if not isinstance(records, list) or len(records) != len(expected):
        raise ValueError("adapter artifact inventory is incomplete")
    names: set[str] = set()
    for record in records:
        selected = _exact_keys(record, {"path", "bytes", "sha256"}, "adapter artifact")
        name = selected["path"]
        if not isinstance(name, str) or name != Path(name).name or name in names:
            raise ValueError("adapter artifact paths must be unique portable file names")
        if name not in expected:
            raise ValueError(f"invalid adapter artifact role: {name}")
        names.add(name)
        if isinstance(selected["bytes"], bool) or not isinstance(selected["bytes"], int):
            raise TypeError("adapter artifact byte count must be an integer")
        if selected["bytes"] != len(package_bytes[name]):
            raise ValueError(f"adapter artifact size mismatch: {name}")
        if _sha256(selected["sha256"], f"adapter artifact hash for {name}") != _sha256_bytes(
            package_bytes[name]
        ):
            raise ValueError(f"adapter artifact hash mismatch: {name}")
    if names != expected:
        raise ValueError("adapter artifact inventory does not cover the package")


def _read_adapter_package_bytes(
    package: Path,
    maximum_package_bytes: int,
    *,
    expected_manifest_sha256: str | None,
) -> dict[str, bytes]:
    if maximum_package_bytes <= 0:
        raise ValueError("maximum_package_bytes must be positive")
    manifest_name = "adapter_manifest.json"
    manifest = _read_bounded_file(package / manifest_name, maximum_package_bytes)
    if expected_manifest_sha256 is not None and _sha256_bytes(manifest) != (
        expected_manifest_sha256
    ):
        raise ValueError("adapter manifest does not match the externally supplied digest")
    retained = {manifest_name: manifest}
    remaining = maximum_package_bytes - len(manifest)
    for name in sorted(ADAPTER_PACKAGE_FILES - {manifest_name}):
        artifact = _read_bounded_file(package / name, remaining)
        retained[name] = artifact
        remaining -= len(artifact)
    return retained


@dataclass(frozen=True, slots=True)
class AdaptedResourcePackageVerification:
    package_dir: Path
    bundle: AdaptedAssuranceResourceBundle
    adapter_manifest_sha256: str
    externally_digest_bound: bool


def verify_adapted_resource_bundle(
    package_dir: str | Path,
    *,
    fit_package: EmpiricalCalibrationPackageVerification,
    expected_policy_sha256: str,
    expected_adapter_manifest_sha256: str | None = None,
    maximum_package_bytes: int = 64 * 1024 * 1024,
) -> AdaptedResourcePackageVerification:
    """Verify adapter artifacts and recompute every generated specification."""

    package = Path(package_dir)
    if package.is_symlink():
        raise ValueError("adapter package cannot be a symlink")
    if not package.is_dir():
        raise FileNotFoundError(package)
    entries = list(package.iterdir())
    if {path.name for path in entries} != ADAPTER_PACKAGE_FILES:
        raise ValueError("adapter package file set mismatch")
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            raise ValueError("adapter package entries must be regular local files")
    expected_manifest_digest = (
        None
        if expected_adapter_manifest_sha256 is None
        else _sha256(
            expected_adapter_manifest_sha256,
            "expected adapter manifest hash",
        )
    )
    package_bytes = _read_adapter_package_bytes(
        package,
        maximum_package_bytes,
        expected_manifest_sha256=expected_manifest_digest,
    )
    manifest_bytes = package_bytes["adapter_manifest.json"]
    manifest_digest = _sha256_bytes(manifest_bytes)
    manifest = _read_json_bytes(manifest_bytes, "adapter_manifest.json")
    recorded_self_hash = _sha256(
        manifest.pop("self_integrity_sha256", None), "adapter manifest self hash"
    )
    if recorded_self_hash != _sha256_bytes(_canonical_json_bytes(manifest)):
        raise ValueError("adapter manifest self hash mismatch")
    manifest["self_integrity_sha256"] = recorded_self_hash
    for name in (
        "heldout_used_for_adapter",
        "external_validation",
        "scientific_use_authorized",
        "runner_authorized",
    ):
        if manifest.get(name) is not False:
            raise ValueError("adapter manifest exceeds the engineering evidence scope")
    if manifest.get("scientific_use") != "engineering_simulation_only":
        raise ValueError("adapter manifest scientific-use boundary mismatch")
    if manifest.get("source_package_heldout_verified") is not True:
        raise ValueError("adapter manifest does not record source-package verification")
    _verify_artifacts(manifest, package_bytes)
    if (
        _read_json_bytes(package_bytes["adapter_policy_schema.json"], "adapter_policy_schema.json")
        != resource_adapter_policy_schema()
    ):
        raise ValueError("adapter policy schema differs from the implementation")
    if (
        _read_json_bytes(
            package_bytes["assurance_resource_specs_schema.json"],
            "assurance_resource_specs_schema.json",
        )
        != assurance_resource_specs_schema()
    ):
        raise ValueError("resource specification schema differs from the implementation")
    policy = ResourceAdapterPolicy.from_mapping(
        _read_json_bytes(package_bytes["adapter_policy.json"], "adapter_policy.json")
    )
    expected_policy = _sha256(expected_policy_sha256, "expected adapter policy hash")
    if policy.policy_sha256 != expected_policy:
        raise ValueError("retained adapter policy differs from the externally supplied digest")
    verified_policy = VerifiedResourceAdapterPolicy(
        policy=policy,
        policy_sha256=policy.policy_sha256,
        externally_digest_bound=True,
    )
    recomputed = adapt_accepted_fit_to_resource_specs(fit_package, verified_policy)
    if (
        _read_json_bytes(
            package_bytes["assurance_resource_specs.json"],
            "assurance_resource_specs.json",
        )
        != recomputed.specifications_dict()
    ):
        raise ValueError("retained resource specifications differ from recomputation")
    core = recomputed.to_dict()
    if set(manifest) != {*core, "artifacts", "self_integrity_sha256"}:
        raise ValueError("adapter manifest fields differ from the closed contract")
    for key, value in core.items():
        if manifest.get(key) != value:
            raise ValueError(f"adapter manifest field differs from recomputation: {key}")
    return AdaptedResourcePackageVerification(
        package_dir=package.resolve(),
        bundle=recomputed,
        adapter_manifest_sha256=manifest_digest,
        externally_digest_bound=expected_adapter_manifest_sha256 is not None,
    )
