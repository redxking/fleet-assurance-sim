from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd
import pytest

from fleet_sim.control_plane.resource_network import (
    AdmissionPattern,
    ResourceType,
    ServiceTimeDistribution,
    make_admission_trajectory,
    simulate_resource_network,
)
from fleet_sim.empirical.assurance_campaign import (
    read_empirical_campaign,
    write_empirical_campaign_package,
)
from fleet_sim.empirical.calibration_gate import (
    MAX_BOOTSTRAP_REPLICATIONS,
    EmpiricalCalibrationPackageVerification,
    FitGatePolicy,
    calibration_fit_schema,
    calibration_policy_schema,
    fit_empirical_calibration,
    load_fit_gate_policy,
    prepare_calibration_fit_input,
    verify_empirical_calibration_package,
    write_empirical_calibration_package,
)
from fleet_sim.empirical.resource_adapter import (
    ADAPTER_PACKAGE_FILES,
    POLICY_FIELDS,
    PolicyFieldEvidence,
    ResourceAdapterPolicy,
    ResourceMappingPolicy,
    VerifiedResourceAdapterPolicy,
    adapt_accepted_fit_to_resource_specs,
    assurance_resource_specs_schema,
    current_simulator_semantics_sha256,
    load_resource_adapter_policy,
    resource_adapter_policy_schema,
    verify_adapted_resource_bundle,
    write_adapted_resource_bundle,
)

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_TEMPLATE = ROOT / "examples" / "empirical_assurance_campaign_template.json"
CAMPAIGN_SCHEMA = ROOT / "schemas" / "empirical_assurance_campaign.schema.json"
MEASUREMENT_SCHEMA = ROOT / "schemas" / "empirical_assurance_measurements.schema.json"
CALIBRATION_POLICY_SCHEMA = ROOT / "schemas" / "empirical_calibration_policy.schema.json"
CALIBRATION_FIT_SCHEMA = ROOT / "schemas" / "empirical_calibration_fit.schema.json"
ADAPTER_POLICY_SCHEMA = ROOT / "schemas" / "assurance_resource_adapter_policy.schema.json"
RESOURCE_SPECS_SCHEMA = ROOT / "schemas" / "assurance_resource_specs.schema.json"
FIT_POLICY = ROOT / "configs" / "successor" / "empirical_calibration_policy.json"
ADAPTER_POLICY = ROOT / "configs" / "successor" / "assurance_resource_adapter_policy.example.json"
EXPECTED_FIT_POLICY_SHA256 = "dc887ba249064ae8489de41bcf0ba05a1fff454793f4daad70aad89843212e09"
EXPECTED_ADAPTER_POLICY_SHA256 = "cdacb4012e9f190f8110645a0bcf8cd52108ff896085d5c81a82cdffd3f874df"


def _read_json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _assert_schema_closed_and_nonempty(
    value: object,
    *,
    path: tuple[str, ...] = (),
) -> None:
    """Reject permissive empty fragments and open payload object contracts."""

    if isinstance(value, Mapping):
        assert value, f"empty schema fragment at {'/'.join(path) or '$'}"
        if value.get("type") == "object" and "contains" not in path:
            properties = value.get("properties")
            assert isinstance(properties, Mapping) and properties, (
                f"object schema has no properties at {'/'.join(path) or '$'}"
            )
            assert value.get("additionalProperties") is False, (
                f"object schema is not closed at {'/'.join(path) or '$'}"
            )
        if value.get("type") == "array":
            items = value.get("items")
            assert isinstance(items, Mapping) and items, (
                f"array schema has an empty item contract at {'/'.join(path) or '$'}"
            )
        for key, nested in value.items():
            _assert_schema_closed_and_nonempty(nested, path=(*path, str(key)))
        return
    if isinstance(value, list):
        assert value, f"empty schema list at {'/'.join(path) or '$'}"
        for index, nested in enumerate(value):
            _assert_schema_closed_and_nonempty(nested, path=(*path, str(index)))


def _matches_schema_type(value: object, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        )
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, Mapping)
    raise AssertionError(f"unsupported structural schema type: {expected}")


def _assert_structural_instance(
    value: object,
    schema: Mapping[str, object],
    *,
    path: str = "$",
) -> None:
    """Small Draft 2020-12 subset used only when jsonschema is unavailable."""

    any_of = schema.get("anyOf")
    if isinstance(any_of, list):
        assert any(
            _structural_schema_match(value, branch, path=path)
            for branch in any_of
            if isinstance(branch, Mapping)
        ), f"{path} does not match any allowed schema branch"

    if "const" in schema:
        assert value == schema["const"], f"{path} differs from its required constant"
    enum = schema.get("enum")
    if isinstance(enum, list):
        assert value in enum, f"{path} is outside the allowed enumeration"

    declared_type = schema.get("type")
    if isinstance(declared_type, str):
        assert _matches_schema_type(value, declared_type), f"{path} is not a JSON {declared_type}"
    elif isinstance(declared_type, list):
        assert any(
            isinstance(item, str) and _matches_schema_type(value, item) for item in declared_type
        ), f"{path} does not match an allowed JSON type"

    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        maximum_length = schema.get("maxLength")
        if isinstance(minimum_length, int):
            assert len(value) >= minimum_length, f"{path} is too short"
        if isinstance(maximum_length, int):
            assert len(value) <= maximum_length, f"{path} is too long"
        pattern = schema.get("pattern")
        if isinstance(pattern, str):
            assert re.search(pattern, value), f"{path} does not match its pattern"

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        exclusive_minimum = schema.get("exclusiveMinimum")
        exclusive_maximum = schema.get("exclusiveMaximum")
        if isinstance(minimum, (int, float)):
            assert number >= float(minimum), f"{path} is below its minimum"
        if isinstance(maximum, (int, float)):
            assert number <= float(maximum), f"{path} exceeds its maximum"
        if isinstance(exclusive_minimum, (int, float)):
            assert number > float(exclusive_minimum), f"{path} is not above its exclusive minimum"
        if isinstance(exclusive_maximum, (int, float)):
            assert number < float(exclusive_maximum), f"{path} is not below its exclusive maximum"

    if isinstance(value, Mapping):
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        assert isinstance(required, list)
        assert isinstance(properties, Mapping)
        assert set(required).issubset(value), f"{path} is missing required fields"
        if schema.get("additionalProperties") is False:
            assert set(value).issubset(properties), f"{path} has undeclared fields"
        for key, nested_value in value.items():
            nested_schema = properties.get(key)
            if isinstance(nested_schema, Mapping):
                _assert_structural_instance(
                    nested_value,
                    nested_schema,
                    path=f"{path}.{key}",
                )

    if isinstance(value, list):
        minimum_items = schema.get("minItems")
        maximum_items = schema.get("maxItems")
        if isinstance(minimum_items, int):
            assert len(value) >= minimum_items, f"{path} has too few items"
        if isinstance(maximum_items, int):
            assert len(value) <= maximum_items, f"{path} has too many items"
        if schema.get("uniqueItems") is True:
            encoded = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in value]
            assert len(encoded) == len(set(encoded)), f"{path} contains duplicates"
        items = schema.get("items")
        if isinstance(items, Mapping):
            for index, item in enumerate(value):
                _assert_structural_instance(item, items, path=f"{path}[{index}]")

    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for clause in all_of:
            assert isinstance(clause, Mapping)
            selector = clause.get("contains")
            if isinstance(selector, Mapping):
                assert isinstance(value, list), f"{path} contains applies to an array"
                match_count = sum(
                    _structural_schema_match(item, selector, path=path) for item in value
                )
                minimum_contains = clause.get("minContains", 1)
                maximum_contains = clause.get("maxContains")
                assert isinstance(minimum_contains, int)
                assert match_count >= minimum_contains, f"{path} does not satisfy minContains"
                if isinstance(maximum_contains, int):
                    assert match_count <= maximum_contains, f"{path} does not satisfy maxContains"
            else:
                _assert_structural_instance(value, clause, path=path)


def _structural_schema_match(
    value: object,
    schema: object,
    *,
    path: str,
) -> bool:
    if not isinstance(schema, Mapping):
        return False
    try:
        _assert_structural_instance(value, schema, path=path)
    except AssertionError:
        return False
    return True


def _assert_payload_satisfies_schema(
    payload: Mapping[str, object],
    schema: dict[str, object],
) -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        assert schema.get("$schema") == ("https://json-schema.org/draft/2020-12/schema")
        _assert_structural_instance(payload, schema)
        return

    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda error: tuple(str(item) for item in error.absolute_path),
    )
    assert not errors, "\n".join(error.message for error in errors)


@dataclass(frozen=True, slots=True)
class VerifiedFitFixture:
    fit_package: EmpiricalCalibrationPackageVerification
    fit_policy: FitGatePolicy
    campaign_package: Path
    campaign_evidence_manifest_sha256: str
    fit_evidence_manifest_sha256: str


def _fit_policy() -> FitGatePolicy:
    return FitGatePolicy.from_mapping(
        {
            "policy_id": "adapter-test-fit-gate-v1",
            "study_mode": "interface_verification",
            "minimum_calibration_time_blocks": 40,
            "minimum_observations_per_resource": 40,
            "minimum_unique_fleet_sizes": 5,
            "minimum_unique_admission_rates": 5,
            "minimum_zero_admission_blocks": 10,
            "minimum_active_admission_blocks": 20,
            "minimum_unique_joint_predictor_vectors": 10,
            "maximum_scaled_condition_number": 30.0,
            "maximum_scaled_target_hull_distance": 1e-9,
            "target_fleet_size_min": 100,
            "target_fleet_size_max": 500,
            "target_admission_rate_min_per_s": 0.0,
            "target_admission_rate_max_per_s": 20.0,
            "maximum_weighted_normalized_rmse": 0.01,
            "maximum_absolute_weighted_relative_bias": 0.01,
            "minimum_weighted_r_squared": 0.99,
            "maximum_capacity_coefficient_of_variation": 0.01,
            "maximum_deadline_coefficient_of_variation": 0.01,
            "bootstrap_replications": 100,
            "bootstrap_block_length": 3,
            "bootstrap_interval_level": 0.95,
            "minimum_bootstrap_success_fraction": 0.80,
            "interval_scale_floor": 1e-9,
            "maximum_background_interval_relative_width": 0.25,
            "maximum_admission_interval_relative_width": 0.25,
            "maximum_capacity_interval_relative_width": 0.10,
            "maximum_service_interval_relative_width": 0.10,
            "maximum_max_wait_interval_relative_width": 0.10,
            "root_seed": 918_2026,
        }
    )


def _campaign_manifest(campaign_id: str) -> dict[str, object]:
    manifest = json.loads(CAMPAIGN_TEMPLATE.read_text(encoding="utf-8"))
    manifest["campaign_id"] = campaign_id
    manifest["collection_start"] = "2026-08-20T11:59:59Z"
    manifest["collection_end"] = "2026-08-20T12:02:00Z"
    return manifest


def _measurement_frame(campaign_id: str, *, heldout_delta: int = 0) -> pd.DataFrame:
    base_time = pd.Timestamp("2026-08-20T12:00:00Z")
    rows: list[dict[str, object]] = []
    for partition, block_count, offset in (
        ("calibration", 60, 0),
        ("heldout", 12, 61),
    ):
        for block_index in range(block_count):
            fleet_size = 100 * (1 + block_index % 5)
            admitted = (0, 5, 10, 15, 20)[(block_index // 5) % 5]
            timestamp = base_time + pd.Timedelta(seconds=offset + block_index)
            for resource_index, resource_type in enumerate(ResourceType):
                background = (resource_index + 1) / 100.0
                admission_work = float(resource_index + 2)
                arrivals = int(background * fleet_size + admission_work * admitted)
                if partition == "heldout" and block_index == 0 and resource_index == 0:
                    arrivals += heldout_delta
                rows.append(
                    {
                        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                        "resource_id": resource_type.value,
                        "resource_type": resource_type.value,
                        "fleet_size": fleet_size,
                        "agents_admitted": admitted,
                        "arrival_count": arrivals,
                        "service_count": arrivals,
                        "queue_depth": 0.0,
                        "service_time_ms": 10.0 + resource_index + 0.01 * (block_index % 5),
                        "wait_time_ms": 1.0 + resource_index / 10.0,
                        "capacity_units_per_second": 1_000.0 + 100.0 * resource_index,
                        "deadline_ms": 1_000.0 + 100.0 * resource_index,
                        "dropped_work": 0.0,
                        "deferred_work": 0.0,
                        "error_count": 0,
                        "source_type": "synthetic",
                        "measurement_provenance": "generated adapter-test fixture",
                        "window_duration_ms": 1_000.0,
                        "campaign_id": campaign_id,
                        "time_block_id": f"{partition}-window-{block_index:03d}",
                        "partition": partition,
                        "is_censored": False,
                        "missing_fraction": 0.0,
                    }
                )
    return pd.DataFrame(rows)


def _verified_passed_fit(
    base: Path,
    *,
    campaign_id: str = "adapter-test-campaign",
    heldout_delta: int = 0,
) -> VerifiedFitFixture:
    source_dir = base / "sources"
    source_dir.mkdir(parents=True)
    measurements_path = source_dir / "measurements.csv"
    campaign_path = source_dir / "campaign.json"
    _measurement_frame(campaign_id, heldout_delta=heldout_delta).to_csv(
        measurements_path,
        index=False,
    )
    campaign_path.write_text(
        json.dumps(_campaign_manifest(campaign_id), indent=2),
        encoding="utf-8",
    )
    campaign = read_empirical_campaign(
        measurements_path,
        campaign_path,
        campaign_schema_path=CAMPAIGN_SCHEMA,
        measurement_schema_path=MEASUREMENT_SCHEMA,
    )
    campaign_package = write_empirical_campaign_package(
        campaign,
        base / "campaign-package",
    )
    campaign_digest = hashlib.sha256(
        (campaign_package / "evidence_manifest.json").read_bytes()
    ).hexdigest()
    fit_input = prepare_calibration_fit_input(
        campaign_package,
        expected_evidence_manifest_sha256=campaign_digest,
    )
    policy = _fit_policy()
    run = fit_empirical_calibration(fit_input, policy)
    assert run.fit.gate_status == "passed"
    assert run.fit.interface_verification_ready is True
    fit_package_path = write_empirical_calibration_package(
        run,
        fit_input,
        base / "fit-package",
    )
    fit_digest = hashlib.sha256(
        (fit_package_path / "fit_evidence_manifest.json").read_bytes()
    ).hexdigest()
    verified = verify_empirical_calibration_package(
        fit_package_path,
        source_campaign_package=campaign_package,
        expected_source_evidence_manifest_sha256=campaign_digest,
        expected_fit_evidence_manifest_sha256=fit_digest,
    )
    assert verified.externally_digest_bound is True
    return VerifiedFitFixture(
        fit_package=verified,
        fit_policy=policy,
        campaign_package=campaign_package,
        campaign_evidence_manifest_sha256=campaign_digest,
        fit_evidence_manifest_sha256=fit_digest,
    )


@pytest.fixture(scope="module")
def accepted_fit(tmp_path_factory: pytest.TempPathFactory) -> VerifiedFitFixture:
    return _verified_passed_fit(tmp_path_factory.mktemp("accepted-adapter-fit"))


def _resource_policy(
    resource_type: ResourceType,
    index: int,
    *,
    include_notional: bool,
) -> ResourceMappingPolicy:
    notional_fields = {
        "overload_behavior",
        "shedding_threshold",
        "recovery_capacity_multiplier",
    }
    evidence = tuple(
        PolicyFieldEvidence(
            field_name=field,
            evidence_class=(
                "notional" if include_notional and field in notional_fields else "configured"
            ),
            reference=f"adapter-test-{field}",
        )
        for field in sorted(POLICY_FIELDS)
    )
    completion_modes = (
        "deterministic_completion_count",
        "poisson_completion_count",
        "gamma_completion_count",
    )
    overload_modes = ("queue", "shed", "defer")
    return ResourceMappingPolicy(
        resource_id=resource_type.value,
        resource_type=resource_type.value,
        arrival_count_mode=("poisson_count" if index % 2 == 0 else "deterministic_expected_count"),
        completion_count_mode=completion_modes[index % len(completion_modes)],
        capacity_selection="point" if index % 2 == 0 else "lower_interval_bound",
        service_time_selection="point_window_summary",
        max_wait_selection="point" if index % 2 == 0 else "lower_interval_bound",
        deadline_semantics="maximum_queue_wait_budget",
        overload_behavior=overload_modes[index % len(overload_modes)],
        shedding_threshold=1.20 + index / 100.0,
        recovery_capacity_multiplier=1.05 + index / 100.0,
        field_evidence=evidence,
    )


def _adapter_policy(
    fit: VerifiedFitFixture,
    *,
    mode: str = "interface_verification",
    include_notional: bool = True,
    simulator_sha256: str | None = None,
) -> ResourceAdapterPolicy:
    resources = tuple(
        _resource_policy(resource_type, index, include_notional=include_notional)
        for index, resource_type in reversed(list(enumerate(ResourceType)))
    )
    return ResourceAdapterPolicy.from_mapping(
        {
            "policy_id": f"adapter-test-{mode}-v1",
            "adapter_mode": mode,
            "fit_policy_sha256": fit.fit_policy.policy_sha256,
            "simulator_semantics_sha256": (
                simulator_sha256 or current_simulator_semantics_sha256()
            ),
            "target_fleet_size_min": 100,
            "target_fleet_size_max": 500,
            "target_admission_rate_min_per_s": 0.0,
            "target_admission_rate_max_per_s": 20.0,
            "no_fallback": True,
            "allowed_source_evidence_scopes": ["synthetic_or_mixed_interface_only"],
            "resources": [resource.to_dict() for resource in resources],
        }
    )


def _verified_policy(policy: ResourceAdapterPolicy) -> VerifiedResourceAdapterPolicy:
    return VerifiedResourceAdapterPolicy(
        policy=policy,
        policy_sha256=policy.policy_sha256,
        externally_digest_bound=True,
    )


def _adapted_bundle(accepted_fit: VerifiedFitFixture):
    policy = _adapter_policy(accepted_fit)
    verification = _verified_policy(policy)
    bundle = adapt_accepted_fit_to_resource_specs(
        accepted_fit.fit_package,
        verification,
    )
    return policy, verification, bundle


@pytest.mark.parametrize(
    ("schema_path", "schema_factory"),
    (
        (CALIBRATION_POLICY_SCHEMA, calibration_policy_schema),
        (CALIBRATION_FIT_SCHEMA, calibration_fit_schema),
        (ADAPTER_POLICY_SCHEMA, resource_adapter_policy_schema),
        (RESOURCE_SPECS_SCHEMA, assurance_resource_specs_schema),
    ),
    ids=("fit-policy", "fit-result", "adapter-policy", "resource-specs"),
)
def test_retained_public_schemas_equal_live_contract_generators(
    schema_path: Path,
    schema_factory: Callable[[], dict[str, object]],
) -> None:
    assert _read_json_object(schema_path) == schema_factory()


def test_checked_in_successor_policy_chain_is_coherent() -> None:
    fit_policy = load_fit_gate_policy(FIT_POLICY)
    assert fit_policy.policy_sha256 == EXPECTED_FIT_POLICY_SHA256

    adapter = load_resource_adapter_policy(
        ADAPTER_POLICY,
        expected_policy_sha256=EXPECTED_ADAPTER_POLICY_SHA256,
    )
    assert adapter.externally_digest_bound is True
    assert adapter.policy.fit_policy_sha256 == fit_policy.policy_sha256
    assert adapter.policy.simulator_semantics_sha256 == (current_simulator_semantics_sha256())


@pytest.mark.parametrize(
    "schema_factory",
    (
        calibration_policy_schema,
        calibration_fit_schema,
        resource_adapter_policy_schema,
        assurance_resource_specs_schema,
    ),
    ids=("fit-policy", "fit-result", "adapter-policy", "resource-specs"),
)
def test_live_contract_schemas_are_closed_and_have_no_empty_fragments(
    schema_factory: Callable[[], dict[str, object]],
) -> None:
    _assert_schema_closed_and_nonempty(schema_factory())


def test_live_fit_and_adapter_payloads_satisfy_their_public_schemas(
    accepted_fit: VerifiedFitFixture,
) -> None:
    adapter_policy, _, bundle = _adapted_bundle(accepted_fit)
    cases = (
        (accepted_fit.fit_policy.to_dict(), calibration_policy_schema()),
        (accepted_fit.fit_package.fit.to_dict(), calibration_fit_schema()),
        (adapter_policy.to_dict(), resource_adapter_policy_schema()),
        (bundle.specifications_dict(), assurance_resource_specs_schema()),
    )
    for payload, schema in cases:
        _assert_payload_satisfies_schema(payload, schema)


def test_fit_policy_runtime_and_schema_bounds_remain_aligned() -> None:
    schema = calibration_policy_schema()
    properties = schema["properties"]
    assert isinstance(properties, Mapping)
    assert properties["policy_id"] == {
        "type": "string",
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
    }
    bootstrap_schema = properties["bootstrap_replications"]
    assert isinstance(bootstrap_schema, Mapping)
    assert bootstrap_schema["minimum"] == 100
    assert bootstrap_schema["maximum"] == MAX_BOOTSTRAP_REPLICATIONS
    for name in (
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
        field_schema = properties[name]
        assert isinstance(field_schema, Mapping)
        assert field_schema["exclusiveMinimum"] == 0.0

    payload = _fit_policy().to_dict()
    payload["policy_id"] = "a" * 128
    FitGatePolicy.from_mapping(payload)
    payload["policy_id"] = "a" * 129
    with pytest.raises(ValueError, match="portable identifier"):
        FitGatePolicy.from_mapping(payload)
    payload["policy_id"] = "_not-portable"
    with pytest.raises(ValueError, match="portable identifier"):
        FitGatePolicy.from_mapping(payload)

    payload = _fit_policy().to_dict()
    payload["bootstrap_replications"] = MAX_BOOTSTRAP_REPLICATIONS
    FitGatePolicy.from_mapping(payload)
    payload["bootstrap_replications"] = MAX_BOOTSTRAP_REPLICATIONS + 1
    with pytest.raises(ValueError, match="cannot exceed"):
        FitGatePolicy.from_mapping(payload)

    for lower_name, upper_name in (
        ("target_fleet_size_min", "target_fleet_size_max"),
        (
            "target_admission_rate_min_per_s",
            "target_admission_rate_max_per_s",
        ),
    ):
        payload = _fit_policy().to_dict()
        payload[upper_name] = payload[lower_name]
        with pytest.raises(ValueError, match="positive width"):
            FitGatePolicy.from_mapping(payload)


def test_adapter_runtime_and_schema_bounds_remain_aligned(
    accepted_fit: VerifiedFitFixture,
) -> None:
    schema = resource_adapter_policy_schema()
    properties = schema["properties"]
    assert isinstance(properties, Mapping)
    assert properties["policy_id"] == {
        "type": "string",
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
    }
    resources_schema = properties["resources"]
    assert isinstance(resources_schema, Mapping)
    resource_schema = resources_schema["items"]
    assert isinstance(resource_schema, Mapping)
    resource_properties = resource_schema["properties"]
    assert isinstance(resource_properties, Mapping)
    resource_id_schema = resource_properties["resource_id"]
    assert isinstance(resource_id_schema, Mapping)
    assert resource_id_schema["maxLength"] == 256
    assert resource_id_schema["pattern"] == r"\S"
    field_evidence_schema = resource_properties["field_evidence"]
    assert isinstance(field_evidence_schema, Mapping)
    evidence_item_schema = field_evidence_schema["items"]
    assert isinstance(evidence_item_schema, Mapping)
    evidence_properties = evidence_item_schema["properties"]
    assert isinstance(evidence_properties, Mapping)
    reference_schema = evidence_properties["reference"]
    assert isinstance(reference_schema, Mapping)
    assert reference_schema["minLength"] == 1
    assert reference_schema["maxLength"] == 1024

    payload = _adapter_policy(accepted_fit).to_dict()
    payload["policy_id"] = "a" * 128
    ResourceAdapterPolicy.from_mapping(payload)
    payload["policy_id"] = "a" * 129
    with pytest.raises(ValueError, match="portable identifier"):
        ResourceAdapterPolicy.from_mapping(payload)

    payload = _adapter_policy(accepted_fit).to_dict()
    resources = payload["resources"]
    assert isinstance(resources, list)
    first_resource = resources[0]
    assert isinstance(first_resource, dict)
    first_resource["resource_id"] = "r" * 256
    ResourceAdapterPolicy.from_mapping(payload)
    first_resource["resource_id"] = "r" * 257
    with pytest.raises(ValueError, match="cannot exceed 256"):
        ResourceAdapterPolicy.from_mapping(payload)
    first_resource["resource_id"] = " "
    with pytest.raises(TypeError, match="nonempty string"):
        ResourceAdapterPolicy.from_mapping(payload)
    with pytest.raises(AssertionError):
        _assert_payload_satisfies_schema(payload, resource_adapter_policy_schema())

    payload = _adapter_policy(accepted_fit).to_dict()
    resources = payload["resources"]
    assert isinstance(resources, list)
    first_resource = resources[0]
    assert isinstance(first_resource, dict)
    evidence = first_resource["field_evidence"]
    assert isinstance(evidence, list)
    first_evidence = evidence[0]
    assert isinstance(first_evidence, dict)
    first_evidence["reference"] = "r" * 1024
    ResourceAdapterPolicy.from_mapping(payload)
    first_evidence["reference"] = "r" * 1025
    with pytest.raises(ValueError, match="cannot exceed 1024"):
        ResourceAdapterPolicy.from_mapping(payload)
    first_evidence["reference"] = "/local/absolute/path"
    with pytest.raises(ValueError, match="cannot contain a local path"):
        ResourceAdapterPolicy.from_mapping(payload)


@pytest.mark.parametrize(
    ("lower_name", "upper_name"),
    (
        ("target_fleet_size_min", "target_fleet_size_max"),
        (
            "target_admission_rate_min_per_s",
            "target_admission_rate_max_per_s",
        ),
    ),
    ids=("fleet-size", "admission-rate"),
)
def test_adapter_target_domains_require_positive_width(
    accepted_fit: VerifiedFitFixture,
    lower_name: str,
    upper_name: str,
) -> None:
    payload = _adapter_policy(accepted_fit).to_dict()
    payload[upper_name] = payload[lower_name]
    with pytest.raises(ValueError, match="positive width"):
        ResourceAdapterPolicy.from_mapping(payload)


@pytest.mark.parametrize(
    "invalid_reference",
    (
        "/local/absolute/path",
        "file:///tmp/evidence.json",
        "C:/Users/analyst/evidence.json",
        "C:evidence.json",
        "../evidence.json",
        "records/../evidence.json",
        r"folder\evidence.json",
        "~/.config/evidence.json",
        " leading-space",
        "trailing-space ",
        "record\n",
        "record\r\n",
    ),
)
def test_policy_reference_portability_matches_the_public_schema(
    accepted_fit: VerifiedFitFixture,
    invalid_reference: str,
) -> None:
    payload = _adapter_policy(accepted_fit).to_dict()
    resources = payload["resources"]
    assert isinstance(resources, list)
    first_resource = resources[0]
    assert isinstance(first_resource, dict)
    evidence = first_resource["field_evidence"]
    assert isinstance(evidence, list)
    first_evidence = evidence[0]
    assert isinstance(first_evidence, dict)
    first_evidence["reference"] = invalid_reference

    with pytest.raises(ValueError, match="cannot contain a local path"):
        ResourceAdapterPolicy.from_mapping(payload)
    with pytest.raises(AssertionError):
        _assert_payload_satisfies_schema(payload, resource_adapter_policy_schema())


def test_portable_reference_uri_is_accepted_by_runtime_and_schema(
    accepted_fit: VerifiedFitFixture,
) -> None:
    payload = _adapter_policy(accepted_fit).to_dict()
    resources = payload["resources"]
    assert isinstance(resources, list)
    first_resource = resources[0]
    assert isinstance(first_resource, dict)
    evidence = first_resource["field_evidence"]
    assert isinstance(evidence, list)
    first_evidence = evidence[0]
    assert isinstance(first_evidence, dict)
    first_evidence["reference"] = "https://example.org/evidence/record-1"

    ResourceAdapterPolicy.from_mapping(payload)
    _assert_payload_satisfies_schema(payload, resource_adapter_policy_schema())


def test_exact_ten_resource_and_explicit_field_coverage_aligns_across_contracts(
    accepted_fit: VerifiedFitFixture,
) -> None:
    expected_resources = {item.value for item in ResourceType}

    fit_schema = calibration_fit_schema()
    fit_resources = fit_schema["properties"]["resources"]
    assert isinstance(fit_resources, Mapping)
    assert fit_resources["minItems"] == len(ResourceType)
    assert fit_resources["maxItems"] == len(ResourceType)
    assert len(fit_resources["allOf"]) == len(ResourceType)
    fit_resource_schema = fit_resources["items"]
    assert isinstance(fit_resource_schema, Mapping)
    fit_resource_properties = fit_resource_schema["properties"]
    assert isinstance(fit_resource_properties, Mapping)
    fit_payload_resources = accepted_fit.fit_package.fit.to_dict()["resources"]
    assert isinstance(fit_payload_resources, list)
    assert set(fit_resource_schema["required"]) == set(fit_payload_resources[0])
    fit_evidence_schema = fit_resource_properties["field_evidence_class"]
    assert isinstance(fit_evidence_schema, Mapping)
    fit_evidence = fit_payload_resources[0]["field_evidence_class"]
    assert isinstance(fit_evidence, dict)
    assert set(fit_evidence_schema["required"]) == set(fit_evidence)
    assert set(fit_evidence_schema["properties"]) == set(fit_evidence)

    adapter_schema = resource_adapter_policy_schema()
    adapter_resources = adapter_schema["properties"]["resources"]
    assert isinstance(adapter_resources, Mapping)
    assert adapter_resources["minItems"] == len(ResourceType)
    assert adapter_resources["maxItems"] == len(ResourceType)
    resource_selectors = adapter_resources["allOf"]
    assert isinstance(resource_selectors, list)
    assert {
        selector["contains"]["properties"]["resource_type"]["const"]
        for selector in resource_selectors
    } == expected_resources
    adapter_resource_schema = adapter_resources["items"]
    assert isinstance(adapter_resource_schema, Mapping)
    adapter_field_evidence = adapter_resource_schema["properties"]["field_evidence"]
    assert isinstance(adapter_field_evidence, Mapping)
    assert adapter_field_evidence["minItems"] == len(POLICY_FIELDS)
    assert adapter_field_evidence["maxItems"] == len(POLICY_FIELDS)
    field_selectors = adapter_field_evidence["allOf"]
    assert isinstance(field_selectors, list)
    assert {
        selector["contains"]["properties"]["field_name"]["const"] for selector in field_selectors
    } == POLICY_FIELDS

    specs_schema = assurance_resource_specs_schema()
    specs_resources = specs_schema["properties"]["resources"]
    assert isinstance(specs_resources, Mapping)
    assert specs_resources["minItems"] == len(ResourceType)
    assert specs_resources["maxItems"] == len(ResourceType)
    specs_resource_schema = specs_resources["items"]
    assert isinstance(specs_resource_schema, Mapping)
    _, _, bundle = _adapted_bundle(accepted_fit)
    specs_payload = bundle.specifications_dict()["resources"]
    assert isinstance(specs_payload, list)
    assert set(specs_resource_schema["required"]) == set(specs_payload[0])

    payload = _adapter_policy(accepted_fit).to_dict()
    policy_resources = payload["resources"]
    assert isinstance(policy_resources, list)
    payload["resources"] = policy_resources[:-1]
    with pytest.raises(ValueError, match="cover every resource type exactly once"):
        ResourceAdapterPolicy.from_mapping(payload)

    payload = _adapter_policy(accepted_fit).to_dict()
    policy_resources = payload["resources"]
    assert isinstance(policy_resources, list)
    first_resource = policy_resources[0]
    assert isinstance(first_resource, dict)
    field_evidence = first_resource["field_evidence"]
    assert isinstance(field_evidence, list)
    first_resource["field_evidence"] = field_evidence[:-1]
    with pytest.raises(ValueError, match="cover every explicit adapter policy field"):
        ResourceAdapterPolicy.from_mapping(payload)


def test_adapter_maps_exactly_ten_specs_in_canonical_resource_order(
    accepted_fit: VerifiedFitFixture,
) -> None:
    policy, _, bundle = _adapted_bundle(accepted_fit)
    expected_types = tuple(ResourceType)
    assert tuple(resource.resource_type for resource in bundle.resources) == expected_types
    assert tuple(resource.resource_id for resource in bundle.resources) == tuple(
        resource_type.value for resource_type in expected_types
    )
    assert len(bundle.resources) == len(ResourceType)
    assert len(bundle.field_provenance) == 10 * len(ResourceType)

    fit_by_type = {
        resource.resource_type: resource for resource in accepted_fit.fit_package.fit.resources
    }
    policy_by_type = {resource.resource_type: resource for resource in policy.resources}
    completion_distributions = {
        "deterministic_completion_count": ServiceTimeDistribution.DETERMINISTIC,
        "poisson_completion_count": ServiceTimeDistribution.EXPONENTIAL,
        "gamma_completion_count": ServiceTimeDistribution.GAMMA,
    }
    for spec in bundle.resources:
        fit = fit_by_type[spec.resource_type.value]
        rule = policy_by_type[spec.resource_type.value]
        assert fit.capacity_units_per_second is not None
        assert fit.max_wait_s is not None
        expected_capacity = (
            fit.capacity_units_per_second.point
            if rule.capacity_selection == "point"
            else fit.capacity_units_per_second.lower
        )
        expected_wait = (
            fit.max_wait_s.point if rule.max_wait_selection == "point" else fit.max_wait_s.lower
        )
        assert spec.capacity_units_per_second == pytest.approx(expected_capacity)
        assert spec.max_wait_s == pytest.approx(expected_wait)
        assert spec.arrival_process == (
            "poisson" if rule.arrival_count_mode == "poisson_count" else "scheduled"
        )
        assert (
            spec.service_time_distribution == completion_distributions[rule.completion_count_mode]
        )
        assert spec.overload_behavior.value == rule.overload_behavior
        assert spec.shedding_threshold == pytest.approx(rule.shedding_threshold)
        assert spec.recovery_capacity_multiplier == pytest.approx(rule.recovery_capacity_multiplier)
        assert spec.parameter_class == "notional"

    assert bundle.source_package_heldout_verified is True
    assert bundle.heldout_used_for_adapter is False
    assert bundle.no_fallback is True
    assert bundle.external_validation is False
    assert bundle.scientific_use_authorized is False
    assert bundle.runner_authorized is False


def test_policy_requires_external_digest_binding(
    accepted_fit: VerifiedFitFixture,
    tmp_path: Path,
) -> None:
    policy = _adapter_policy(accepted_fit)
    policy_path = tmp_path / "adapter-policy.json"
    policy_path.write_text(
        json.dumps(policy.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    checked = load_resource_adapter_policy(
        policy_path,
        expected_policy_sha256=policy.policy_sha256,
    )
    assert checked.policy == policy
    assert checked.externally_digest_bound is True
    with pytest.raises(ValueError, match="externally supplied digest"):
        load_resource_adapter_policy(
            policy_path,
            expected_policy_sha256="0" * 64,
        )


def test_simulator_hash_and_unsupported_mode_are_rejected(
    accepted_fit: VerifiedFitFixture,
) -> None:
    mismatched = _adapter_policy(
        accepted_fit,
        simulator_sha256="0" * 64,
    )
    with pytest.raises(ValueError, match="different simulator implementation"):
        adapt_accepted_fit_to_resource_specs(
            accepted_fit.fit_package,
            _verified_policy(mismatched),
        )

    payload = _adapter_policy(accepted_fit).to_dict()
    payload["adapter_mode"] = "confirmatory"
    with pytest.raises(ValueError, match="adapter_mode"):
        ResourceAdapterPolicy.from_mapping(payload)


def test_successor_mode_rejects_synthetic_fit_and_notional_policy(
    accepted_fit: VerifiedFitFixture,
) -> None:
    with pytest.raises(ValueError, match="cannot contain notional"):
        _adapter_policy(
            accepted_fit,
            mode="successor_transfer",
            include_notional=True,
        )

    configured_successor = _adapter_policy(
        accepted_fit,
        mode="successor_transfer",
        include_notional=False,
    )
    with pytest.raises(ValueError, match="not eligible for successor-transfer"):
        adapt_accepted_fit_to_resource_specs(
            accepted_fit.fit_package,
            _verified_policy(configured_successor),
        )


def test_heldout_mutation_does_not_change_adapter_identity_or_specs(
    accepted_fit: VerifiedFitFixture,
    tmp_path: Path,
) -> None:
    changed = _verified_passed_fit(
        tmp_path / "changed-heldout",
        campaign_id="adapter-test-campaign",
        heldout_delta=99_999,
    )
    assert (
        accepted_fit.fit_package.fit.calibration_fit_id
        == changed.fit_package.fit.calibration_fit_id
    )
    assert (
        accepted_fit.fit_package.fit_evidence_manifest_sha256
        != changed.fit_package.fit_evidence_manifest_sha256
    )
    policy = _adapter_policy(accepted_fit)
    original = adapt_accepted_fit_to_resource_specs(
        accepted_fit.fit_package,
        _verified_policy(policy),
    )
    changed_bundle = adapt_accepted_fit_to_resource_specs(
        changed.fit_package,
        _verified_policy(policy),
    )
    assert original.adapter_bundle_id == changed_bundle.adapter_bundle_id
    assert original.specification_sha256 == changed_bundle.specification_sha256
    assert original.specifications_dict() == changed_bundle.specifications_dict()
    assert original.source_package_heldout_verified is True
    assert original.heldout_used_for_adapter is False
    assert changed_bundle.source_package_heldout_verified is True
    assert changed_bundle.heldout_used_for_adapter is False


def test_five_file_package_roundtrip_tamper_and_no_overwrite(
    accepted_fit: VerifiedFitFixture,
    tmp_path: Path,
) -> None:
    policy, verification, bundle = _adapted_bundle(accepted_fit)
    package = write_adapted_resource_bundle(
        bundle,
        verification,
        tmp_path / "adapter-package",
        fit_package=accepted_fit.fit_package,
    )
    manifest_digest = hashlib.sha256((package / "adapter_manifest.json").read_bytes()).hexdigest()
    checked = verify_adapted_resource_bundle(
        package,
        fit_package=accepted_fit.fit_package,
        expected_policy_sha256=policy.policy_sha256,
        expected_adapter_manifest_sha256=manifest_digest,
    )
    assert {path.name for path in package.iterdir()} == ADAPTER_PACKAGE_FILES
    assert checked.externally_digest_bound is True
    assert checked.bundle.to_dict() == bundle.to_dict()
    with pytest.raises(FileExistsError, match="overwrite"):
        write_adapted_resource_bundle(
            bundle,
            verification,
            package,
            fit_package=accepted_fit.fit_package,
        )

    specs_path = package / "assurance_resource_specs.json"
    specs_path.write_bytes(specs_path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="artifact (size|hash) mismatch"):
        verify_adapted_resource_bundle(
            package,
            fit_package=accepted_fit.fit_package,
            expected_policy_sha256=policy.policy_sha256,
        )


def test_writer_rejects_a_caller_supplied_invalid_bundle_before_output(
    accepted_fit: VerifiedFitFixture,
    tmp_path: Path,
) -> None:
    _, verification, bundle = _adapted_bundle(accepted_fit)
    invalid = replace(
        bundle,
        resources=(),
        source_package_heldout_verified=False,
        heldout_used_for_adapter=True,
        no_fallback=False,
        external_validation=True,
        scientific_use_authorized=True,
        runner_authorized=True,
    )
    destination = tmp_path / "invalid-adapter-package"
    with pytest.raises(ValueError, match="deterministic recomputation"):
        write_adapted_resource_bundle(
            invalid,
            verification,
            destination,
            fit_package=accepted_fit.fit_package,
        )
    assert not destination.exists()


def test_adapter_writer_refuses_output_inside_source_fit(
    accepted_fit: VerifiedFitFixture,
) -> None:
    _, verification, bundle = _adapted_bundle(accepted_fit)
    source = accepted_fit.fit_package.package_dir
    before = {path.name for path in source.iterdir()}
    with pytest.raises(ValueError, match="outside its source evidence"):
        write_adapted_resource_bundle(
            bundle,
            verification,
            source / "nested-adapter",
            fit_package=accepted_fit.fit_package,
        )
    assert {path.name for path in source.iterdir()} == before
    assert not (source / "nested-adapter").exists()


def test_adapter_writer_refuses_output_inside_source_campaign(
    accepted_fit: VerifiedFitFixture,
) -> None:
    _, verification, bundle = _adapted_bundle(accepted_fit)
    source = accepted_fit.campaign_package
    before = {path.name for path in source.iterdir()}
    with pytest.raises(ValueError, match="outside its source evidence"):
        write_adapted_resource_bundle(
            bundle,
            verification,
            source / "nested-adapter",
            fit_package=accepted_fit.fit_package,
        )
    assert {path.name for path in source.iterdir()} == before
    assert not (source / "nested-adapter").exists()


def test_fit_cli_refuses_output_inside_source_campaign(
    accepted_fit: VerifiedFitFixture,
    tmp_path: Path,
) -> None:
    policy_path = tmp_path / "fit-policy.json"
    policy_path.write_text(
        json.dumps(accepted_fit.fit_policy.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    destination = accepted_fit.campaign_package / "nested-fit-from-cli"
    before = {path.name for path in accepted_fit.campaign_package.iterdir()}
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "fit_empirical_assurance_calibration.py"),
            str(accepted_fit.campaign_package),
            str(destination),
            "--expected-campaign-evidence-manifest-sha256",
            accepted_fit.campaign_evidence_manifest_sha256,
            "--policy",
            str(policy_path),
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode != 0
    assert "outside the source campaign package" in completed.stderr
    assert {path.name for path in accepted_fit.campaign_package.iterdir()} == before
    assert not destination.exists()


@pytest.mark.parametrize("source_kind", ("campaign", "fit"))
def test_adapter_cli_refuses_output_inside_source_evidence_packages(
    accepted_fit: VerifiedFitFixture,
    tmp_path: Path,
    source_kind: str,
) -> None:
    policy = _adapter_policy(accepted_fit)
    policy_path = tmp_path / f"adapter-policy-{source_kind}.json"
    policy_path.write_text(
        json.dumps(policy.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    source = (
        accepted_fit.campaign_package
        if source_kind == "campaign"
        else accepted_fit.fit_package.package_dir
    )
    destination = source / f"nested-adapter-from-cli-{source_kind}"
    before = {path.name for path in source.iterdir()}
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_assurance_resource_specs.py"),
            str(accepted_fit.campaign_package),
            str(accepted_fit.fit_package.package_dir),
            str(destination),
            "--expected-campaign-evidence-manifest-sha256",
            accepted_fit.campaign_evidence_manifest_sha256,
            "--expected-fit-evidence-manifest-sha256",
            accepted_fit.fit_evidence_manifest_sha256,
            "--adapter-policy",
            str(policy_path),
            "--expected-adapter-policy-sha256",
            policy.policy_sha256,
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode != 0
    assert "outside its source evidence packages" in completed.stderr
    assert {path.name for path in source.iterdir()} == before
    assert not destination.exists()


def test_rehashed_false_authority_flags_are_rejected(
    accepted_fit: VerifiedFitFixture,
    tmp_path: Path,
) -> None:
    policy, verification, bundle = _adapted_bundle(accepted_fit)
    package = write_adapted_resource_bundle(
        bundle,
        verification,
        tmp_path / "false-authority-package",
        fit_package=accepted_fit.fit_package,
    )
    manifest_path = package / "adapter_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["external_validation"] = True
    manifest["scientific_use_authorized"] = True
    manifest["runner_authorized"] = True
    manifest.pop("self_integrity_sha256")
    canonical = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    manifest["self_integrity_sha256"] = hashlib.sha256(canonical).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="engineering evidence scope"):
        verify_adapted_resource_bundle(
            package,
            fit_package=accepted_fit.fit_package,
            expected_policy_sha256=policy.policy_sha256,
        )


def test_specs_support_one_bounded_engineering_only_aggregate_run(
    accepted_fit: VerifiedFitFixture,
) -> None:
    _, _, bundle = _adapted_bundle(accepted_fit)
    trajectory = make_admission_trajectory(
        AdmissionPattern.LINEAR,
        initial_n=100,
        final_n=120,
        admission_duration_s=5.0,
        recovery_window_s=3.0,
        dt_s=1.0,
    )
    result = simulate_resource_network(
        trajectory,
        bundle.resources,
        seed=20260820,
    )
    assert len(result.resource_trace) == len(trajectory.time_s) * len(ResourceType)
    assert len(result.resource_trace) <= 100
    assert len(result.admission_trace) == len(trajectory.time_s)
    assert result.summary["achieved_final_n"] == 120
    assert result.summary["evidence_scope"] == "interface_verification_only"
    assert bundle.runner_authorized is False
