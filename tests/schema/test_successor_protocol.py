from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from copy import copy
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

import fleet_sim.empirical.successor_protocol as successor_module
from fleet_sim.control_plane.resource_network import ResourceType
from fleet_sim.empirical.assurance_campaign import (
    CampaignPackageVerification,
    read_empirical_campaign,
    verify_empirical_campaign_package,
    write_empirical_campaign_package,
)
from fleet_sim.empirical.calibration_gate import (
    EmpiricalCalibrationPackageVerification,
    FitGatePolicy,
    fit_empirical_calibration,
    prepare_calibration_fit_input,
    verify_empirical_calibration_package,
    write_empirical_calibration_package,
)
from fleet_sim.empirical.prediction_lock import (
    SuccessorPredictionLockPackageVerification,
    build_successor_prediction_lock,
    verify_successor_prediction_lock_package,
    write_successor_prediction_lock_package,
)
from fleet_sim.empirical.resource_adapter import (
    POLICY_FIELDS,
    AdaptedResourcePackageVerification,
    PolicyFieldEvidence,
    ResourceAdapterPolicy,
    ResourceMappingPolicy,
    VerifiedResourceAdapterPolicy,
    adapt_accepted_fit_to_resource_specs,
    current_simulator_semantics_sha256,
    verify_adapted_resource_bundle,
    write_adapted_resource_bundle,
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
    EVALUATION_INPUT_PACKAGE_FILES,
    METRICS,
    PREDICTION_FORMULA,
    PREDICTOR_FIELDS,
    PRIMARY_ESTIMAND,
    PROTOCOL_SCHEMA_VERSION,
    REGISTRATION_PACKAGE_FILES,
    SCORING_ABSOLUTE_RELATIVE_BIAS_FORMULA,
    SCORING_AGGREGATION,
    SCORING_BLOCK_VALIDITY_RULE,
    SCORING_EVALUATION_UNIT,
    SCORING_MISSING_DATA_POLICY,
    SCORING_NON_EVALUABLE_POLICY,
    SCORING_NRMSE_FORMULA,
    SCORING_RELATIVE_IMPROVEMENT_FORMULA,
    SCORING_WEIGHTING,
    UNCERTAINTY_INTERVAL_LEVEL_SOURCE,
    UNCERTAINTY_INTERVAL_TYPE,
    UNCERTAINTY_METHOD,
    UNCERTAINTY_QUANTILE_METHOD,
    UNCERTAINTY_REPLICATION_SET,
    UNCERTAINTY_SCOPE,
    CandidatePredictionContract,
    ComparatorPredictionContract,
    PlannedEvaluationBlock,
    PlannedEvaluationCell,
    PredictionUncertaintyContract,
    ResourceArrivalTransferContract,
    SuccessorRegistration,
    SuccessorRegistrationPackageVerification,
    SuccessorRegistrationPlan,
    TransferMetricThresholds,
    TransferScoringContract,
    bind_successor_evaluation_inputs,
    freeze_successor_registration,
    load_resource_arrival_transfer_contract,
    load_successor_registration_plan,
    successor_evaluation_inputs_schema,
    successor_registration_plan_schema,
    successor_registration_schema,
    transfer_contract_schema,
    verify_successor_evaluation_inputs_package,
    verify_successor_registration_package,
    write_successor_evaluation_inputs_package,
    write_successor_registration_package,
)

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_TEMPLATE = ROOT / "examples" / "empirical_assurance_campaign_template.json"
CAMPAIGN_SCHEMA = ROOT / "schemas" / "empirical_assurance_campaign.schema.json"
MEASUREMENT_SCHEMA = ROOT / "schemas" / "empirical_assurance_measurements.schema.json"
TRANSFER_CONTRACT_SCHEMA = ROOT / "schemas" / "successor_transfer_contract.schema.json"
REGISTRATION_PLAN_SCHEMA = ROOT / "schemas" / "successor_registration_plan.schema.json"
REGISTRATION_SCHEMA = ROOT / "schemas" / "successor_registration.schema.json"
EVALUATION_INPUTS_SCHEMA = ROOT / "schemas" / "successor_evaluation_inputs.schema.json"
TRANSFER_CONTRACT_EXAMPLE = (
    ROOT / "configs" / "successor" / "resource_arrival_transfer_contract.example.json"
)
REGISTRATION_PLAN_EXAMPLE = (
    ROOT / "configs" / "successor" / "successor_registration_plan.example.json"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _read_json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _assert_payload_satisfies_schema(
    payload: Mapping[str, object], schema: dict[str, object]
) -> None:
    try:
        import jsonschema
    except ImportError:
        _assert_structural_instance(payload, schema)
        return
    validator_type = jsonschema.validators.validator_for(schema)
    validator_type.check_schema(schema)
    errors = sorted(
        validator_type(schema).iter_errors(payload),
        key=lambda error: tuple(str(item) for item in error.absolute_path),
    )
    assert not errors, "\n".join(error.message for error in errors)


def _assert_payload_rejected_by_schema(
    payload: Mapping[str, object], schema: dict[str, object]
) -> None:
    with pytest.raises(AssertionError):
        _assert_payload_satisfies_schema(payload, schema)


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


def _structural_schema_match(value: object, schema: object, *, path: str) -> bool:
    if not isinstance(schema, Mapping):
        return False
    try:
        _assert_structural_instance(value, schema, path=path)
    except AssertionError:
        return False
    return True


def _assert_structural_instance(
    value: object,
    schema: Mapping[str, object],
    *,
    path: str = "$",
) -> None:
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
        pattern = schema.get("pattern")
        if isinstance(minimum_length, int):
            assert len(value) >= minimum_length, f"{path} is too short"
        if isinstance(maximum_length, int):
            assert len(value) <= maximum_length, f"{path} is too long"
        if isinstance(pattern, str):
            assert re.search(pattern, value), f"{path} does not match its pattern"

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)):
            assert float(value) >= float(minimum), f"{path} is below its minimum"
        multiple_of = schema.get("multipleOf")
        if isinstance(multiple_of, (int, float)):
            assert Decimal(str(value)) % Decimal(str(multiple_of)) == 0, (
                f"{path} is not a multiple of {multiple_of}"
            )

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
        prefix_items = schema.get("prefixItems")
        if isinstance(prefix_items, list):
            for index, nested_schema in enumerate(prefix_items):
                assert isinstance(nested_schema, Mapping)
                _assert_structural_instance(
                    value[index],
                    nested_schema,
                    path=f"{path}[{index}]",
                )
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
                continue
            condition = clause.get("if")
            consequence = clause.get("then")
            if isinstance(condition, Mapping) and isinstance(consequence, Mapping):
                if _structural_schema_match(value, condition, path=path):
                    _assert_structural_instance(value, consequence, path=path)
                continue
            _assert_structural_instance(value, clause, path=path)


def _campaign_manifest(
    campaign_id: str,
    *,
    collection_start: str,
    collection_end: str,
) -> dict[str, object]:
    manifest = _read_json_object(CAMPAIGN_TEMPLATE)
    manifest["campaign_id"] = campaign_id
    manifest["collection_start"] = collection_start
    manifest["collection_end"] = collection_end
    return manifest


def _measurement_frame(
    campaign_id: str,
    *,
    base_time: str,
) -> pd.DataFrame:
    base = pd.Timestamp(base_time)
    rows: list[dict[str, object]] = []
    for partition, block_count, offset in (
        ("calibration", 60, 0),
        ("heldout", 12, 61),
    ):
        for block_index in range(block_count):
            fleet_size = 100 * (1 + block_index % 5)
            agents_admitted = (0, 5, 10, 15, 20)[(block_index // 5) % 5]
            timestamp = base + pd.Timedelta(seconds=offset + block_index)
            for resource_index, resource_type in enumerate(ResourceType):
                background = (resource_index + 1) / 100.0
                admission_work = float(resource_index + 2)
                arrivals = int(background * fleet_size + admission_work * agents_admitted)
                rows.append(
                    {
                        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                        "resource_id": resource_type.value,
                        "resource_type": resource_type.value,
                        "fleet_size": fleet_size,
                        "agents_admitted": agents_admitted,
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
                        "measurement_provenance": "generated successor-protocol fixture",
                        "window_duration_ms": 1_000.0,
                        "campaign_id": campaign_id,
                        "time_block_id": f"{partition}-window-{block_index:03d}",
                        "partition": partition,
                        "is_censored": False,
                        "missing_fraction": 0.0,
                    }
                )
    return pd.DataFrame(rows)


def _verified_campaign(
    base: Path,
    *,
    campaign_id: str,
    base_time: str,
    collection_start: str,
    collection_end: str,
    frame: pd.DataFrame | None = None,
) -> tuple[CampaignPackageVerification, str]:
    source_dir = base / f"{campaign_id}-sources"
    source_dir.mkdir(parents=True)
    measurements_path = source_dir / "measurements.csv"
    manifest_path = source_dir / "campaign.json"
    selected = _measurement_frame(campaign_id, base_time=base_time) if frame is None else frame
    selected.to_csv(measurements_path, index=False)
    manifest_path.write_text(
        json.dumps(
            _campaign_manifest(
                campaign_id,
                collection_start=collection_start,
                collection_end=collection_end,
            ),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    campaign = read_empirical_campaign(
        measurements_path,
        manifest_path,
        campaign_schema_path=CAMPAIGN_SCHEMA,
        measurement_schema_path=MEASUREMENT_SCHEMA,
    )
    package = write_empirical_campaign_package(campaign, base / f"{campaign_id}-package")
    digest = _sha256(package / "evidence_manifest.json")
    verified = verify_empirical_campaign_package(
        package,
        expected_evidence_manifest_sha256=digest,
    )
    assert verified.externally_digest_bound is True
    return verified, digest


def _fit_policy() -> FitGatePolicy:
    return FitGatePolicy.from_mapping(
        {
            "policy_id": "successor-protocol-test-fit-v1",
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
            "root_seed": 820_2026,
        }
    )


def _resource_policy(resource_type: ResourceType, index: int) -> ResourceMappingPolicy:
    field_evidence = tuple(
        PolicyFieldEvidence(
            field_name=field_name,
            evidence_class="notional",
            reference=f"successor-protocol-test-{field_name}",
        )
        for field_name in sorted(POLICY_FIELDS)
    )
    return ResourceMappingPolicy(
        resource_id=resource_type.value,
        resource_type=resource_type.value,
        arrival_count_mode=("poisson_count" if index % 2 == 0 else "deterministic_expected_count"),
        completion_count_mode="poisson_completion_count",
        capacity_selection="point",
        service_time_selection="point_window_summary",
        max_wait_selection="point",
        deadline_semantics="maximum_queue_wait_budget",
        overload_behavior="queue",
        shedding_threshold=1.25,
        recovery_capacity_multiplier=1.15,
        field_evidence=field_evidence,
    )


def _adapter_policy(fit_policy: FitGatePolicy) -> ResourceAdapterPolicy:
    resources = tuple(
        _resource_policy(resource_type, index) for index, resource_type in enumerate(ResourceType)
    )
    return ResourceAdapterPolicy.from_mapping(
        {
            "policy_id": "successor-protocol-test-adapter-v1",
            "adapter_mode": "interface_verification",
            "fit_policy_sha256": fit_policy.policy_sha256,
            "simulator_semantics_sha256": current_simulator_semantics_sha256(),
            "target_fleet_size_min": 100,
            "target_fleet_size_max": 500,
            "target_admission_rate_min_per_s": 0.0,
            "target_admission_rate_max_per_s": 20.0,
            "no_fallback": True,
            "allowed_source_evidence_scopes": ["synthetic_or_mixed_interface_only"],
            "resources": [resource.to_dict() for resource in resources],
        }
    )


def _planned_evaluation_block(index: int) -> PlannedEvaluationBlock:
    timestamp = pd.Timestamp("2030-01-01T12:00:00Z") + pd.Timedelta(seconds=61 + index)
    return PlannedEvaluationBlock(
        time_block_id=f"heldout-window-{index:03d}",
        timestamp_utc=timestamp.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        fleet_size=100 * (1 + index % 5),
        agents_admitted=(0, 5, 10, 15, 20)[(index // 5) % 5],
        window_duration_ms=1_000.0,
    )


def _registration_plan(
    *,
    evaluation_campaign_id: str = "successor-future-evaluation",
) -> SuccessorRegistrationPlan:
    blocks = tuple(_planned_evaluation_block(index) for index in range(12))
    return SuccessorRegistrationPlan(
        schema_version=PROTOCOL_SCHEMA_VERSION,
        plan_id="successor-protocol-test-plan-v1",
        study_id="successor-protocol-test-study-v1",
        registration_mode="engineering_dry_run",
        planned_evaluation_campaign_id=evaluation_campaign_id,
        planned_collection_start_utc="2030-01-01T11:59:00.000000Z",
        planned_collection_end_utc="2030-01-01T12:03:00.000000Z",
        cells=(
            PlannedEvaluationCell("cell-a", blocks[:6]),
            PlannedEvaluationCell("cell-b", blocks[6:]),
        ),
        one_shot_evaluation=True,
        deviation_policy="fail_closed",
        prediction_lock_required=True,
        outcome_custody_required=True,
    )


def _transfer_contract() -> ResourceArrivalTransferContract:
    return ResourceArrivalTransferContract(
        schema_version=PROTOCOL_SCHEMA_VERSION,
        contract_id="successor-protocol-test-contract-v1",
        contract_mode="engineering_dry_run",
        primary_estimand=PRIMARY_ESTIMAND,
        candidate=CandidatePredictionContract(
            model_id=CANDIDATE_MODEL_ID,
            formula=PREDICTION_FORMULA,
            predictor_fields=PREDICTOR_FIELDS,
            fit_partition=CANDIDATE_FIT_PARTITION,
            fit_objective=CANDIDATE_FIT_OBJECTIVE,
            point_parameter_source=CANDIDATE_POINT_PARAMETER_SOURCE,
        ),
        outcome_field="arrival_count",
        resource_types=tuple(resource_type.value for resource_type in ResourceType),
        comparator=ComparatorPredictionContract(
            model_id=COMPARATOR,
            formula=COMPARATOR_FORMULA,
            fit_partition=COMPARATOR_FIT_PARTITION,
            scope=COMPARATOR_SCOPE,
            response=COMPARATOR_RESPONSE,
            predictor=COMPARATOR_PREDICTOR,
            intercept=COMPARATOR_INTERCEPT,
            weighting=COMPARATOR_WEIGHTING,
            constraint=COMPARATOR_CONSTRAINT,
            estimator=COMPARATOR_ESTIMATOR,
            zero_denominator_policy=COMPARATOR_ZERO_DENOMINATOR_POLICY,
        ),
        uncertainty=PredictionUncertaintyContract(
            method=UNCERTAINTY_METHOD,
            replication_set=UNCERTAINTY_REPLICATION_SET,
            interval_type=UNCERTAINTY_INTERVAL_TYPE,
            interval_level_source=UNCERTAINTY_INTERVAL_LEVEL_SOURCE,
            quantile_method=UNCERTAINTY_QUANTILE_METHOD,
            scope=UNCERTAINTY_SCOPE,
        ),
        scoring=TransferScoringContract(
            metrics=METRICS,
            evaluation_unit=SCORING_EVALUATION_UNIT,
            weighting=SCORING_WEIGHTING,
            nrmse_formula=SCORING_NRMSE_FORMULA,
            absolute_relative_bias_formula=SCORING_ABSOLUTE_RELATIVE_BIAS_FORMULA,
            relative_improvement_formula=SCORING_RELATIVE_IMPROVEMENT_FORMULA,
            positive_observed_mean_required=True,
            positive_comparator_rmse_required=True,
            block_validity_rule=SCORING_BLOCK_VALIDITY_RULE,
            missing_data_policy=SCORING_MISSING_DATA_POLICY,
            aggregation=SCORING_AGGREGATION,
            non_evaluable_policy=SCORING_NON_EVALUABLE_POLICY,
        ),
        criteria_frozen=False,
        thresholds=TransferMetricThresholds(
            maximum_duration_weighted_nrmse=None,
            maximum_absolute_duration_weighted_relative_bias=None,
            minimum_candidate_relative_improvement=None,
            minimum_valid_time_blocks_per_cell=None,
            require_every_resource=True,
        ),
        operational_outcome_extension_enabled=False,
        prediction_rows_preoutcome_lock_required=True,
        outcome_custody_evidence_required=True,
        external_validation=False,
        scientific_use_authorized=False,
        runner_authorized=False,
    )


@dataclass(frozen=True, slots=True)
class ProtocolFixture:
    source_campaign: CampaignPackageVerification
    source_campaign_digest: str
    fit_package: EmpiricalCalibrationPackageVerification
    adapter_package: AdaptedResourcePackageVerification
    plan: SuccessorRegistrationPlan
    contract: ResourceArrivalTransferContract
    registration: SuccessorRegistration
    registration_package: SuccessorRegistrationPackageVerification
    prediction_lock_package: SuccessorPredictionLockPackageVerification
    prediction_lock_digest: str
    evaluation_campaign: CampaignPackageVerification
    evaluation_campaign_digest: str


@dataclass(frozen=True, slots=True)
class ProspectiveGuardHarness:
    fit_package: EmpiricalCalibrationPackageVerification
    adapter_package: AdaptedResourcePackageVerification
    plan: SuccessorRegistrationPlan
    contract: ResourceArrivalTransferContract


@pytest.fixture(scope="module")
def protocol_fixture(tmp_path_factory: pytest.TempPathFactory) -> ProtocolFixture:
    base = tmp_path_factory.mktemp("successor-protocol-chain")
    source, source_digest = _verified_campaign(
        base,
        campaign_id="successor-source-campaign",
        base_time="2026-08-20T12:00:00Z",
        collection_start="2026-08-20T11:59:59Z",
        collection_end="2026-08-20T12:02:00Z",
    )
    fit_input = prepare_calibration_fit_input(
        source.package_dir,
        expected_evidence_manifest_sha256=source_digest,
    )
    fit_policy = _fit_policy()
    run = fit_empirical_calibration(fit_input, fit_policy)
    assert run.fit.gate_status == "passed"
    fit_path = write_empirical_calibration_package(
        run,
        fit_input,
        base / "fit-package",
    )
    fit_digest = _sha256(fit_path / "fit_evidence_manifest.json")
    fit_package = verify_empirical_calibration_package(
        fit_path,
        source_campaign_package=source.package_dir,
        expected_source_evidence_manifest_sha256=source_digest,
        expected_fit_evidence_manifest_sha256=fit_digest,
    )
    adapter_policy = _adapter_policy(fit_policy)
    verified_policy = VerifiedResourceAdapterPolicy(
        policy=adapter_policy,
        policy_sha256=adapter_policy.policy_sha256,
        externally_digest_bound=True,
    )
    adapter_bundle = adapt_accepted_fit_to_resource_specs(
        fit_package,
        verified_policy,
    )
    adapter_path = write_adapted_resource_bundle(
        adapter_bundle,
        verified_policy,
        base / "adapter-package",
        fit_package=fit_package,
    )
    adapter_digest = _sha256(adapter_path / "adapter_manifest.json")
    adapter_package = verify_adapted_resource_bundle(
        adapter_path,
        fit_package=fit_package,
        expected_policy_sha256=adapter_policy.policy_sha256,
        expected_adapter_manifest_sha256=adapter_digest,
    )
    plan = _registration_plan()
    contract = _transfer_contract()
    registration = freeze_successor_registration(
        source,
        fit_package,
        adapter_package,
        plan,
        contract,
        registered_at_utc="2029-12-31T23:59:59.000000Z",
    )
    registration_path = write_successor_registration_package(
        registration,
        plan,
        contract,
        base / "registration-package",
        source_campaign=source,
        fit_package=fit_package,
        adapter_package=adapter_package,
    )
    registration_digest = _sha256(registration_path / "registration_manifest.json")
    registration_package = verify_successor_registration_package(
        registration_path,
        source_campaign=source,
        fit_package=fit_package,
        adapter_package=adapter_package,
        expected_registration_manifest_sha256=registration_digest,
    )
    prediction_run = build_successor_prediction_lock(
        registration_package,
        source_campaign=source,
        fit_package=fit_package,
        adapter_package=adapter_package,
        committed_at_utc="2030-01-01T11:58:59.000000Z",
    )
    prediction_path = write_successor_prediction_lock_package(
        prediction_run,
        base / "prediction-lock-package",
        registration_package=registration_package,
        source_campaign=source,
        fit_package=fit_package,
        adapter_package=adapter_package,
    )
    prediction_lock_digest = _sha256(prediction_path / "prediction_lock_manifest.json")
    prediction_lock_package = verify_successor_prediction_lock_package(
        prediction_path,
        registration_package=registration_package,
        source_campaign=source,
        fit_package=fit_package,
        adapter_package=adapter_package,
        expected_prediction_lock_manifest_sha256=prediction_lock_digest,
    )
    evaluation, evaluation_digest = _verified_campaign(
        base,
        campaign_id=plan.planned_evaluation_campaign_id,
        base_time="2030-01-01T12:00:00Z",
        collection_start="2030-01-01T11:59:59Z",
        collection_end="2030-01-01T12:02:00Z",
    )
    return ProtocolFixture(
        source_campaign=source,
        source_campaign_digest=source_digest,
        fit_package=fit_package,
        adapter_package=adapter_package,
        plan=plan,
        contract=contract,
        registration=registration,
        registration_package=registration_package,
        prediction_lock_package=prediction_lock_package,
        prediction_lock_digest=prediction_lock_digest,
        evaluation_campaign=evaluation,
        evaluation_campaign_digest=evaluation_digest,
    )


def _prospective_guard_harness(fixture: ProtocolFixture) -> ProspectiveGuardHarness:
    """Build a no-write unit harness while preserving exact upstream chain bindings."""

    fit_policy = replace(fixture.fit_package.fit.policy, study_mode="successor_transfer")
    fit = replace(
        fixture.fit_package.fit,
        policy=fit_policy,
        policy_sha256=fit_policy.policy_sha256,
        gate_status="passed",
        blocking_reasons=(),
        interface_verification_ready=True,
        eligible_for_adapter=True,
    )
    fit_package = replace(fixture.fit_package, fit=fit)
    provenance = tuple(
        replace(
            item,
            evidence_class=item.evidence_class.replace("notional", "configured"),
        )
        for item in fixture.adapter_package.bundle.field_provenance
    )
    adapter = replace(
        fixture.adapter_package.bundle,
        adapter_mode="successor_transfer",
        fit_policy_sha256=fit_policy.policy_sha256,
        field_provenance=provenance,
    )
    adapter_package = replace(fixture.adapter_package, bundle=adapter)
    plan = replace(fixture.plan, registration_mode="prospective_transfer")
    contract = replace(
        fixture.contract,
        contract_mode="prospective_transfer",
        criteria_frozen=True,
        thresholds=TransferMetricThresholds(
            maximum_duration_weighted_nrmse=0.20,
            maximum_absolute_duration_weighted_relative_bias=0.10,
            minimum_candidate_relative_improvement=0.05,
            minimum_valid_time_blocks_per_cell=6,
            require_every_resource=True,
        ),
    )
    return ProspectiveGuardHarness(fit_package, adapter_package, plan, contract)


def _prospective_domain_guard_harness(
    fixture: ProtocolFixture,
    destination: Path,
    *,
    adapter_fleet_size_max: int = 500,
    adapter_admission_rate_min_per_s: float = 0.0,
) -> ProspectiveGuardHarness:
    """Build a physical successor adapter solely to isolate predictor-domain checks."""

    harness = _prospective_guard_harness(fixture)
    fit_package = replace(
        harness.fit_package,
        fit=replace(
            harness.fit_package.fit,
            source_evidence_scope="measured_input_unreviewed",
        ),
    )
    interface_policy = _adapter_policy(fit_package.fit.policy)
    configured_resources = tuple(
        replace(
            resource,
            field_evidence=tuple(
                replace(evidence, evidence_class="configured")
                for evidence in resource.field_evidence
            ),
        )
        for resource in interface_policy.resources
    )
    adapter_policy = replace(
        interface_policy,
        adapter_mode="successor_transfer",
        target_fleet_size_max=adapter_fleet_size_max,
        target_admission_rate_min_per_s=adapter_admission_rate_min_per_s,
        allowed_source_evidence_scopes=("measured_input_unreviewed",),
        resources=configured_resources,
    )
    verified_policy = VerifiedResourceAdapterPolicy(
        policy=adapter_policy,
        policy_sha256=adapter_policy.policy_sha256,
        externally_digest_bound=True,
    )
    bundle = adapt_accepted_fit_to_resource_specs(fit_package, verified_policy)
    package = write_adapted_resource_bundle(
        bundle,
        verified_policy,
        destination,
        fit_package=fit_package,
    )
    adapter_package = verify_adapted_resource_bundle(
        package,
        fit_package=fit_package,
        expected_policy_sha256=adapter_policy.policy_sha256,
        expected_adapter_manifest_sha256=_sha256(package / "adapter_manifest.json"),
    )
    return replace(
        harness,
        fit_package=fit_package,
        adapter_package=adapter_package,
    )


def _bind_verified_evaluation_inputs(
    fixture: ProtocolFixture,
    *,
    registration_package: SuccessorRegistrationPackageVerification | None = None,
    prediction_lock_package: SuccessorPredictionLockPackageVerification | None = None,
    evaluation_campaign: CampaignPackageVerification | None = None,
):
    return bind_successor_evaluation_inputs(
        registration_package or fixture.registration_package,
        prediction_lock_package or fixture.prediction_lock_package,
        evaluation_campaign or fixture.evaluation_campaign,
        source_campaign=fixture.source_campaign,
        fit_package=fixture.fit_package,
        adapter_package=fixture.adapter_package,
    )


def test_coherent_two_manifest_chain_is_identity_bound_and_fail_closed(
    protocol_fixture: ProtocolFixture,
) -> None:
    fixture = protocol_fixture
    registration = fixture.registration
    assert registration.registration_mode == "engineering_dry_run"
    assert registration.source_campaign_id == "successor-source-campaign"
    assert registration.planned_evaluation_campaign_id == "successor-future-evaluation"
    assert registration.source_campaign_id != registration.planned_evaluation_campaign_id
    assert registration.source_historical_heldout_verified is True
    assert registration.source_historical_heldout_used_for_fit is False
    assert registration.chronology_consistent is True
    assert registration.registration_time_externally_attested is False
    assert registration.upstream_chain_verified is True
    assert registration.prediction_formula_frozen is True
    visible_implementation = registration.to_dict()["implementation"]
    assert (
        registration.implementation_sha256
        == hashlib.sha256(_canonical_json_bytes(visible_implementation)).hexdigest()
    )
    assert registration.operational_outcome_extension_enabled is False
    assert registration.execution_chain_ready is False
    assert registration.external_validation is False
    assert registration.scientific_use_authorized is False
    assert registration.runner_authorized is False

    inputs = _bind_verified_evaluation_inputs(fixture)
    assert inputs.registration_id == registration.registration_id
    assert inputs.prediction_lock_id == fixture.prediction_lock_package.lock.prediction_lock_id
    assert inputs.prediction_lock_manifest_sha256 == fixture.prediction_lock_digest
    assert inputs.evaluation_campaign_id == registration.planned_evaluation_campaign_id
    assert inputs.realized_cell_count == 2
    assert inputs.realized_time_block_count == 12
    assert inputs.campaign_identity_reconciled is True
    assert inputs.collection_window_reconciled is True
    assert inputs.cell_block_reconciliation == "exact"
    assert inputs.prediction_lock_binding_reconciled is True
    assert inputs.prediction_rows_target_free is True
    assert inputs.workflow_prediction_commitment is True
    assert inputs.chronology_consistent is True
    assert inputs.registration_time_externally_attested is False
    assert inputs.prediction_lock_time_externally_attested is False
    assert inputs.prediction_formula_frozen is True
    assert inputs.prediction_rows_preoutcome_locked is False
    assert inputs.outcome_release_custody_verified is False
    assert inputs.execution_chain_ready is False
    assert inputs.external_validation is False
    assert inputs.scientific_use_authorized is False
    assert inputs.runner_authorized is False


@pytest.mark.parametrize(
    ("schema_path", "schema_factory"),
    (
        (TRANSFER_CONTRACT_SCHEMA, transfer_contract_schema),
        (REGISTRATION_PLAN_SCHEMA, successor_registration_plan_schema),
        (REGISTRATION_SCHEMA, successor_registration_schema),
        (EVALUATION_INPUTS_SCHEMA, successor_evaluation_inputs_schema),
    ),
    ids=("transfer-contract", "registration-plan", "registration", "evaluation-inputs"),
)
def test_checked_in_successor_schemas_equal_live_contracts(
    schema_path: Path,
    schema_factory: Callable[[], dict[str, object]],
) -> None:
    assert _read_json_object(schema_path) == schema_factory()


def test_checked_in_successor_examples_use_the_closed_v11_contract() -> None:
    contract = load_resource_arrival_transfer_contract(TRANSFER_CONTRACT_EXAMPLE)
    plan = load_successor_registration_plan(REGISTRATION_PLAN_EXAMPLE)

    assert contract.schema_version == "1.1"
    assert contract.candidate.model_id == CANDIDATE_MODEL_ID
    assert contract.comparator.model_id == COMPARATOR
    assert contract.uncertainty.scope == UNCERTAINTY_SCOPE
    assert contract.scoring.aggregation == SCORING_AGGREGATION
    assert plan.schema_version == "1.1"
    _assert_payload_satisfies_schema(contract.to_dict(), transfer_contract_schema())
    _assert_payload_satisfies_schema(plan.to_dict(), successor_registration_plan_schema())


def test_live_successor_payloads_satisfy_closed_public_schemas(
    protocol_fixture: ProtocolFixture,
) -> None:
    fixture = protocol_fixture
    inputs = _bind_verified_evaluation_inputs(fixture)
    for payload, schema in (
        (fixture.contract.to_dict(), transfer_contract_schema()),
        (fixture.plan.to_dict(), successor_registration_plan_schema()),
        (fixture.registration.to_dict(), successor_registration_schema()),
        (inputs.to_dict(), successor_evaluation_inputs_schema()),
    ):
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["additionalProperties"] is False
        _assert_payload_satisfies_schema(payload, schema)


def test_registration_rejects_source_campaign_reuse_and_nonprospective_chronology(
    protocol_fixture: ProtocolFixture,
) -> None:
    fixture = protocol_fixture
    reused = _registration_plan(evaluation_campaign_id="successor-source-campaign")
    with pytest.raises(ValueError, match="must differ from source"):
        freeze_successor_registration(
            fixture.source_campaign,
            fixture.fit_package,
            fixture.adapter_package,
            reused,
            fixture.contract,
            registered_at_utc="2029-12-31T23:59:59.000000Z",
        )

    with pytest.raises(ValueError, match="must precede"):
        freeze_successor_registration(
            fixture.source_campaign,
            fixture.fit_package,
            fixture.adapter_package,
            fixture.plan,
            fixture.contract,
            registered_at_utc=fixture.plan.planned_collection_start_utc,
        )


def test_registration_rejects_fit_verified_against_a_different_source_path_without_output(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
) -> None:
    fixture = protocol_fixture
    different_source = tmp_path / "different-source-campaign"
    different_source.mkdir()
    mismatched_fit = replace(
        fixture.fit_package,
        _source_campaign_package_dir=different_source,
    )
    with pytest.raises(ValueError, match="different source campaign path"):
        freeze_successor_registration(
            fixture.source_campaign,
            mismatched_fit,
            fixture.adapter_package,
            fixture.plan,
            fixture.contract,
            registered_at_utc="2029-12-31T23:59:59.000000Z",
        )

    destination = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="fit wrapper differs from its externally bound package"):
        write_successor_registration_package(
            fixture.registration,
            fixture.plan,
            fixture.contract,
            destination,
            source_campaign=fixture.source_campaign,
            fit_package=mismatched_fit,
            adapter_package=fixture.adapter_package,
        )
    assert not destination.exists()


def test_plan_rejects_duplicate_cells_blocks_and_open_deviation_policy() -> None:
    blocks = tuple(_planned_evaluation_block(index) for index in range(6))
    with pytest.raises(ValueError, match="cell IDs cannot repeat"):
        replace(
            _registration_plan(),
            cells=(
                PlannedEvaluationCell("cell-a", blocks),
                PlannedEvaluationCell("cell-a", tuple(reversed(blocks))),
            ),
        )
    with pytest.raises(ValueError, match="cannot appear in multiple cells"):
        replace(
            _registration_plan(),
            cells=(
                PlannedEvaluationCell("cell-a", blocks),
                PlannedEvaluationCell("cell-b", blocks),
            ),
        )
    with pytest.raises(ValueError, match="fail_closed"):
        replace(_registration_plan(), deviation_policy="allow")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("timestamp_utc", "window_duration_ms"),
    (
        ("2030-01-01T11:58:59.000000Z", 1_000.0),
        ("2030-01-01T12:02:59.500000Z", 1_000.0),
    ),
    ids=("starts-before-window", "ends-after-window"),
)
def test_plan_rejects_blocks_outside_the_collection_window(
    timestamp_utc: str,
    window_duration_ms: float,
) -> None:
    plan = _registration_plan()
    first = plan.cells[0]
    changed_block = replace(
        first.planned_blocks[0],
        timestamp_utc=timestamp_utc,
        window_duration_ms=window_duration_ms,
    )
    changed_cell = replace(
        first,
        planned_blocks=(changed_block, *first.planned_blocks[1:]),
    )
    with pytest.raises(ValueError, match="fit within the collection window"):
        replace(plan, cells=(changed_cell, *plan.cells[1:]))


@pytest.mark.parametrize("mutation", ("missing", "extra", "resource-gap"))
def test_evaluation_binding_requires_exact_registered_blocks_and_ten_resources(
    protocol_fixture: ProtocolFixture,
    mutation: str,
) -> None:
    fixture = protocol_fixture
    heldout = fixture.evaluation_campaign.heldout
    if mutation == "missing":
        heldout = heldout[heldout["time_block_id"] != "heldout-window-011"].copy()
    elif mutation == "extra":
        heldout = heldout.copy()
        heldout.loc[heldout["time_block_id"] == "heldout-window-011", "time_block_id"] = (
            "unregistered-block"
        )
    else:
        heldout = heldout[
            ~(
                (heldout["time_block_id"] == "heldout-window-000")
                & (heldout["resource_type"] == next(iter(ResourceType)).value)
            )
        ].copy()
    changed = replace(fixture.evaluation_campaign, _heldout=heldout)
    with pytest.raises(ValueError, match="campaign wrapper differs"):
        _bind_verified_evaluation_inputs(
            fixture,
            evaluation_campaign=changed,
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("fleet_size", 900),
        ("agents_admitted", 7),
        ("window_duration_ms", 2_000.0),
    ),
)
def test_evaluation_binding_rejects_any_realized_predictor_change(
    protocol_fixture: ProtocolFixture,
    field: str,
    replacement: float,
) -> None:
    fixture = protocol_fixture
    heldout = fixture.evaluation_campaign.heldout
    heldout.loc[heldout["time_block_id"] == "heldout-window-000", field] = replacement
    changed = replace(fixture.evaluation_campaign, _heldout=heldout)
    with pytest.raises(ValueError, match="campaign wrapper differs"):
        _bind_verified_evaluation_inputs(
            fixture,
            evaluation_campaign=changed,
        )


def test_evaluation_binding_rejects_realized_timestamp_change(
    protocol_fixture: ProtocolFixture,
) -> None:
    fixture = protocol_fixture
    heldout = fixture.evaluation_campaign.heldout
    selector = heldout["time_block_id"] == "heldout-window-000"
    heldout.loc[selector, "timestamp"] = heldout.loc[selector, "timestamp"] + pd.Timedelta(
        milliseconds=500
    )
    changed = replace(fixture.evaluation_campaign, _heldout=heldout)
    with pytest.raises(ValueError, match="campaign wrapper differs"):
        _bind_verified_evaluation_inputs(
            fixture,
            evaluation_campaign=changed,
        )


def test_real_verified_campaign_with_changed_predictor_fails_semantic_reconciliation(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
) -> None:
    fixture = protocol_fixture
    frame = _measurement_frame(
        fixture.plan.planned_evaluation_campaign_id,
        base_time="2030-01-01T12:00:00Z",
    )
    selector = (frame["partition"] == "heldout") & (frame["time_block_id"] == "heldout-window-000")
    frame.loc[selector, "fleet_size"] = 900
    changed_campaign, _ = _verified_campaign(
        tmp_path,
        campaign_id=fixture.plan.planned_evaluation_campaign_id,
        base_time="2030-01-01T12:00:00Z",
        collection_start="2030-01-01T11:59:59Z",
        collection_end="2030-01-01T12:02:00Z",
        frame=frame,
    )
    with pytest.raises(ValueError, match="realized predictor design differs"):
        _bind_verified_evaluation_inputs(
            fixture,
            evaluation_campaign=changed_campaign,
        )


def test_real_verified_campaign_rejects_submicrosecond_realized_timestamp(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
) -> None:
    fixture = protocol_fixture
    frame = _measurement_frame(
        fixture.plan.planned_evaluation_campaign_id,
        base_time="2030-01-01T12:00:00Z",
    )
    selector = frame["partition"] == "heldout"
    planned_timestamp = pd.Timestamp(fixture.plan.cells[0].planned_blocks[0].timestamp_utc)
    frame.loc[selector, "timestamp"] = frame.loc[selector, "timestamp"].map(
        lambda value: (
            (pd.Timestamp(value) + pd.Timedelta(nanoseconds=999)).isoformat().replace("+00:00", "Z")
        )
    )
    first_realized = frame.loc[
        frame["time_block_id"] == "heldout-window-000",
        "timestamp",
    ].iloc[0]
    assert first_realized == (
        planned_timestamp + pd.Timedelta(nanoseconds=999)
    ).isoformat().replace("+00:00", "Z")
    changed_campaign, _ = _verified_campaign(
        tmp_path,
        campaign_id=fixture.plan.planned_evaluation_campaign_id,
        base_time="2030-01-01T12:00:00Z",
        collection_start="2030-01-01T11:59:59Z",
        collection_end="2030-01-01T12:02:00Z",
        frame=frame,
    )
    with pytest.raises(ValueError, match="sub-microsecond precision"):
        _bind_verified_evaluation_inputs(
            fixture,
            evaluation_campaign=changed_campaign,
        )


@pytest.mark.parametrize("boundary", ("start", "end"))
def test_real_verified_campaign_rejects_submicrosecond_manifest_boundary(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
    boundary: str,
) -> None:
    fixture = protocol_fixture
    collection_start = "2030-01-01T11:59:59Z"
    collection_end = "2030-01-01T12:02:00Z"
    if boundary == "start":
        collection_start = "2030-01-01T11:59:59.000000999Z"
    else:
        collection_end = "2030-01-01T12:02:00.000000999Z"
    changed_campaign, _ = _verified_campaign(
        tmp_path,
        campaign_id=fixture.plan.planned_evaluation_campaign_id,
        base_time="2030-01-01T12:00:00Z",
        collection_start=collection_start,
        collection_end=collection_end,
    )
    with pytest.raises(
        ValueError,
        match=rf"realized collection {boundary} cannot contain sub-microsecond precision",
    ):
        _bind_verified_evaluation_inputs(
            fixture,
            evaluation_campaign=changed_campaign,
        )


def test_evaluation_binding_rejects_wrong_campaign_and_unbound_evidence(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
) -> None:
    fixture = protocol_fixture
    wrong_campaign, _ = _verified_campaign(
        tmp_path,
        campaign_id="wrong-future-campaign",
        base_time="2030-01-01T12:00:00Z",
        collection_start="2030-01-01T11:59:59Z",
        collection_end="2030-01-01T12:02:00Z",
    )
    with pytest.raises(ValueError, match="does not match registration"):
        _bind_verified_evaluation_inputs(
            fixture,
            evaluation_campaign=wrong_campaign,
        )

    with pytest.raises(ValueError, match="externally bound registration"):
        _bind_verified_evaluation_inputs(
            fixture,
            registration_package=replace(
                fixture.registration_package,
                externally_digest_bound=False,
            ),
        )
    with pytest.raises(ValueError, match="externally bound prediction lock"):
        _bind_verified_evaluation_inputs(
            fixture,
            prediction_lock_package=replace(
                fixture.prediction_lock_package,
                externally_digest_bound=False,
            ),
        )
    with pytest.raises(ValueError, match="externally bound campaign"):
        _bind_verified_evaluation_inputs(
            fixture,
            evaluation_campaign=replace(
                fixture.evaluation_campaign,
                externally_digest_bound=False,
            ),
        )


@pytest.mark.parametrize("mutation", ("plan-cell-id", "plan-design", "contract-mode"))
def test_evaluation_rejects_registration_wrapper_drift_without_output(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
    mutation: str,
) -> None:
    fixture = protocol_fixture
    registration = _write_verified_registration(
        fixture,
        tmp_path / f"registration-{mutation}",
    )
    valid_inputs = _bind_verified_evaluation_inputs(
        fixture,
        registration_package=registration,
    )
    changed = registration
    if mutation == "plan-cell-id":
        first_cell = registration.plan.cells[0]
        changed_plan = replace(
            registration.plan,
            cells=(
                replace(first_cell, cell_id="drifted-cell-id"),
                *registration.plan.cells[1:],
            ),
        )
        changed = replace(registration, plan=changed_plan)
    elif mutation == "plan-design":
        first_cell = registration.plan.cells[0]
        first_block = first_cell.planned_blocks[0]
        changed_cell = replace(
            first_cell,
            planned_blocks=(
                replace(first_block, fleet_size=first_block.fleet_size + 1),
                *first_cell.planned_blocks[1:],
            ),
        )
        changed = replace(
            registration,
            plan=replace(
                registration.plan,
                cells=(changed_cell, *registration.plan.cells[1:]),
            ),
        )
    else:
        changed_contract = replace(
            registration.contract,
            contract_mode="prospective_transfer",
            criteria_frozen=True,
            thresholds=TransferMetricThresholds(
                maximum_duration_weighted_nrmse=0.20,
                maximum_absolute_duration_weighted_relative_bias=0.10,
                minimum_candidate_relative_improvement=0.05,
                minimum_valid_time_blocks_per_cell=6,
                require_every_resource=True,
            ),
        )
        changed = replace(registration, contract=changed_contract)

    with pytest.raises(ValueError, match="wrapper differs from its externally bound package"):
        _bind_verified_evaluation_inputs(
            fixture,
            registration_package=changed,
        )

    destination = tmp_path / f"must-not-write-{mutation}"
    with pytest.raises(ValueError, match="wrapper differs from its externally bound package"):
        write_successor_evaluation_inputs_package(
            valid_inputs,
            destination,
            registration_package=changed,
            prediction_lock_package=fixture.prediction_lock_package,
            evaluation_campaign=fixture.evaluation_campaign,
            source_campaign=fixture.source_campaign,
            fit_package=fixture.fit_package,
            adapter_package=fixture.adapter_package,
        )
    assert not destination.exists()


def test_prospective_contract_requires_complete_frozen_thresholds() -> None:
    with pytest.raises(ValueError, match="frozen, complete numeric criteria"):
        replace(_transfer_contract(), contract_mode="prospective_transfer")


def test_synthetic_calibration_cannot_be_registered_as_prospective(
    protocol_fixture: ProtocolFixture,
) -> None:
    fixture = protocol_fixture
    harness = _prospective_guard_harness(fixture)
    with pytest.raises(ValueError, match="synthetic calibration evidence"):
        freeze_successor_registration(
            fixture.source_campaign,
            harness.fit_package,
            harness.adapter_package,
            harness.plan,
            harness.contract,
            registered_at_utc="2029-12-31T23:59:59.000000Z",
        )


def test_relabeling_fit_and_adapter_scope_cannot_launder_synthetic_calibration(
    protocol_fixture: ProtocolFixture,
) -> None:
    fixture = protocol_fixture
    harness = _prospective_guard_harness(fixture)
    fit_package = replace(
        harness.fit_package,
        fit=replace(
            harness.fit_package.fit,
            source_evidence_scope="measured_input_unreviewed",
        ),
    )
    adapter_package = replace(
        harness.adapter_package,
        bundle=replace(
            harness.adapter_package.bundle,
            evidence_scope="measured_input_unreviewed",
        ),
    )
    with pytest.raises(ValueError, match="scope differs from calibration evidence"):
        freeze_successor_registration(
            fixture.source_campaign,
            fit_package,
            adapter_package,
            harness.plan,
            harness.contract,
            registered_at_utc="2029-12-31T23:59:59.000000Z",
        )


@pytest.mark.parametrize(
    ("guard", "expected"),
    (
        ("fit-mode", "successor_transfer fit"),
        ("fit-status", "accepted fit"),
        ("fit-readiness", "accepted fit"),
        ("fit-eligibility", "successor-transfer eligibility"),
        ("synthetic-calibration", "synthetic calibration evidence"),
        ("adapter-mode", "successor_transfer adapter"),
        ("too-few-blocks", "frozen minimum valid blocks"),
    ),
)
def test_each_prospective_registration_guard_fails_closed(
    protocol_fixture: ProtocolFixture,
    guard: str,
    expected: str,
) -> None:
    fixture = protocol_fixture
    harness = _prospective_guard_harness(fixture)
    fit_package = harness.fit_package
    adapter_package = harness.adapter_package
    contract = harness.contract
    if guard == "fit-mode":
        policy = replace(fit_package.fit.policy, study_mode="interface_verification")
        fit_package = replace(
            fit_package,
            fit=replace(
                fit_package.fit,
                policy=policy,
                policy_sha256=policy.policy_sha256,
            ),
        )
    elif guard == "fit-status":
        fit_package = replace(
            fit_package,
            fit=replace(fit_package.fit, gate_status="blocked"),
        )
    elif guard == "fit-readiness":
        fit_package = replace(
            fit_package,
            fit=replace(fit_package.fit, interface_verification_ready=False),
        )
    elif guard == "fit-eligibility":
        fit_package = replace(
            fit_package,
            fit=replace(fit_package.fit, eligible_for_adapter=False),
        )
    elif guard == "synthetic-calibration":
        pass
    elif guard == "adapter-mode":
        adapter_package = replace(
            adapter_package,
            bundle=replace(adapter_package.bundle, adapter_mode="interface_verification"),
        )
    elif guard == "too-few-blocks":
        contract = replace(
            contract,
            thresholds=replace(
                contract.thresholds,
                minimum_valid_time_blocks_per_cell=7,
            ),
        )
    else:
        raise AssertionError(f"unsupported guard fixture: {guard}")

    with pytest.raises(ValueError, match=expected):
        freeze_successor_registration(
            fixture.source_campaign,
            fit_package,
            adapter_package,
            harness.plan,
            contract,
            registered_at_utc="2029-12-31T23:59:59.000000Z",
        )


@pytest.mark.parametrize(
    ("guard", "expected"),
    (
        ("fleet-below-fit", "fleet size lies outside the accepted fit and adapter domain"),
        ("fleet-above-fit", "fleet size lies outside the accepted fit and adapter domain"),
        (
            "admission-below-adapter",
            "admission rate lies outside the accepted fit and adapter domain",
        ),
        (
            "admission-above-fit",
            "admission rate lies outside the accepted fit and adapter domain",
        ),
        (
            "fleet-above-narrower-adapter",
            "fleet size lies outside the accepted fit and adapter domain",
        ),
    ),
)
def test_prospective_predictors_must_stay_inside_fit_and_adapter_domains(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    guard: str,
    expected: str,
) -> None:
    fixture = protocol_fixture
    harness = _prospective_domain_guard_harness(
        fixture,
        tmp_path / f"{guard}-adapter",
        adapter_fleet_size_max=(400 if guard == "fleet-above-narrower-adapter" else 500),
        adapter_admission_rate_min_per_s=(1.0 if guard == "admission-below-adapter" else 0.0),
    )
    monkeypatch.setattr(
        successor_module,
        "_calibration_evidence_scope",
        lambda _campaign: "measured_input_unreviewed",
    )
    plan = harness.plan
    if guard in {"fleet-below-fit", "fleet-above-fit", "admission-above-fit"}:
        first_cell = plan.cells[0]
        first_block = first_cell.planned_blocks[0]
        if guard == "fleet-below-fit":
            changed_block = replace(first_block, fleet_size=99)
        elif guard == "fleet-above-fit":
            changed_block = replace(first_block, fleet_size=501)
        else:
            changed_block = replace(first_block, agents_admitted=21)
        changed_cell = replace(
            first_cell,
            planned_blocks=(changed_block, *first_cell.planned_blocks[1:]),
        )
        plan = replace(plan, cells=(changed_cell, *plan.cells[1:]))

    with pytest.raises(ValueError, match=expected):
        freeze_successor_registration(
            fixture.source_campaign,
            harness.fit_package,
            harness.adapter_package,
            plan,
            harness.contract,
            registered_at_utc="2029-12-31T23:59:59.000000Z",
        )


def test_engineering_dry_run_does_not_claim_prospective_predictor_domain_gating(
    protocol_fixture: ProtocolFixture,
) -> None:
    fixture = protocol_fixture
    first_cell = fixture.plan.cells[0]
    first_block = first_cell.planned_blocks[0]
    changed_cell = replace(
        first_cell,
        planned_blocks=(
            replace(first_block, fleet_size=501, agents_admitted=21),
            *first_cell.planned_blocks[1:],
        ),
    )
    plan = replace(
        fixture.plan,
        cells=(changed_cell, *fixture.plan.cells[1:]),
    )
    registration = freeze_successor_registration(
        fixture.source_campaign,
        fixture.fit_package,
        fixture.adapter_package,
        plan,
        fixture.contract,
        registered_at_utc="2029-12-31T23:59:59.000000Z",
    )
    assert registration.registration_mode == "engineering_dry_run"
    assert registration.execution_chain_ready is False


@pytest.mark.parametrize(
    ("loader", "payload"),
    (
        (
            load_resource_arrival_transfer_contract,
            _transfer_contract().to_dict(),
        ),
        (
            load_successor_registration_plan,
            _registration_plan().to_dict(),
        ),
    ),
    ids=("transfer-contract", "registration-plan"),
)
def test_public_loaders_reject_duplicate_keys_and_nonfinite_json(
    tmp_path: Path,
    loader: Callable[[Path], object],
    payload: dict[str, object],
) -> None:
    duplicate_path = tmp_path / "duplicate.json"
    encoded = json.dumps(payload, sort_keys=True)
    duplicate_path.write_text(
        '{"schema_version":"1.0",' + encoded[1:],
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        loader(duplicate_path)

    nonfinite_path = tmp_path / "nonfinite.json"
    if "thresholds" in payload:
        thresholds = payload["thresholds"]
        assert isinstance(thresholds, dict)
        thresholds["maximum_duration_weighted_nrmse"] = float("nan")
    else:
        payload["planned_collection_start_utc"] = float("nan")
    nonfinite_path.write_text(
        json.dumps(payload, allow_nan=True),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="nonfinite JSON constant"):
        loader(nonfinite_path)


@pytest.mark.parametrize(
    ("loader", "payload"),
    (
        (
            load_resource_arrival_transfer_contract,
            _transfer_contract().to_dict(),
        ),
        (
            load_successor_registration_plan,
            _registration_plan().to_dict(),
        ),
    ),
    ids=("transfer-contract", "registration-plan"),
)
def test_schema_version_is_not_coerced_from_a_json_number(
    tmp_path: Path,
    loader: Callable[[Path], object],
    payload: dict[str, object],
) -> None:
    payload["schema_version"] = 1.0
    path = tmp_path / "numeric-schema-version.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises((TypeError, ValueError), match="schema_version"):
        loader(path)


@pytest.mark.parametrize("timestamp_kind", ("collection", "planned-block"))
def test_plan_runtime_and_schema_reject_nonmicrosecond_timestamp_json(
    tmp_path: Path,
    timestamp_kind: str,
) -> None:
    payload = _registration_plan().to_dict()
    if timestamp_kind == "collection":
        payload["planned_collection_start_utc"] = "2030-01-01T11:59:00Z"
    else:
        cells = payload["cells"]
        assert isinstance(cells, list)
        first_cell = cells[0]
        assert isinstance(first_cell, dict)
        blocks = first_cell["planned_blocks"]
        assert isinstance(blocks, list)
        first_block = blocks[0]
        assert isinstance(first_block, dict)
        first_block["timestamp_utc"] = "2030-01-01T12:01:01Z"
    _assert_payload_rejected_by_schema(payload, successor_registration_plan_schema())
    path = tmp_path / f"nonmicrosecond-{timestamp_kind}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical UTC microsecond form"):
        load_successor_registration_plan(path)


def test_plan_runtime_and_schema_reject_submicrosecond_window_duration_json(
    tmp_path: Path,
) -> None:
    payload = _registration_plan().to_dict()
    cells = payload["cells"]
    assert isinstance(cells, list)
    first_cell = cells[0]
    assert isinstance(first_cell, dict)
    blocks = first_cell["planned_blocks"]
    assert isinstance(blocks, list)
    first_block = blocks[0]
    assert isinstance(first_block, dict)
    first_block["window_duration_ms"] = 0.0005
    _assert_payload_rejected_by_schema(payload, successor_registration_plan_schema())
    path = tmp_path / "submicrosecond-window-duration.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="align to whole microseconds"):
        load_successor_registration_plan(path)


def _copy_package(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination)
    return destination


def _refresh_manifest_artifact(
    package: Path,
    *,
    manifest_name: str,
    artifact_name: str,
) -> str:
    manifest_path = package / manifest_name
    manifest = _read_json_object(manifest_path)
    records = manifest["artifacts"]
    assert isinstance(records, list)
    record = next(
        item for item in records if isinstance(item, dict) and item.get("path") == artifact_name
    )
    artifact = package / artifact_name
    record["bytes"] = artifact.stat().st_size
    record["sha256"] = _sha256(artifact)
    manifest.pop("self_integrity_sha256", None)
    manifest["self_integrity_sha256"] = hashlib.sha256(_canonical_json_bytes(manifest)).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return _sha256(manifest_path)


def _write_verified_registration(
    fixture: ProtocolFixture,
    destination: Path,
) -> SuccessorRegistrationPackageVerification:
    package = write_successor_registration_package(
        fixture.registration,
        fixture.plan,
        fixture.contract,
        destination,
        source_campaign=fixture.source_campaign,
        fit_package=fixture.fit_package,
        adapter_package=fixture.adapter_package,
    )
    digest = _sha256(package / "registration_manifest.json")
    checked = verify_successor_registration_package(
        package,
        source_campaign=fixture.source_campaign,
        fit_package=fixture.fit_package,
        adapter_package=fixture.adapter_package,
        expected_registration_manifest_sha256=digest,
    )
    assert checked.externally_digest_bound is True
    return checked


def _write_verified_evaluation_inputs(
    fixture: ProtocolFixture,
    registration: SuccessorRegistrationPackageVerification,
    destination: Path,
):
    inputs = _bind_verified_evaluation_inputs(
        fixture,
        registration_package=registration,
    )
    package = write_successor_evaluation_inputs_package(
        inputs,
        destination,
        registration_package=registration,
        prediction_lock_package=fixture.prediction_lock_package,
        evaluation_campaign=fixture.evaluation_campaign,
        source_campaign=fixture.source_campaign,
        fit_package=fixture.fit_package,
        adapter_package=fixture.adapter_package,
    )
    digest = _sha256(package / "evaluation_inputs_manifest.json")
    checked = verify_successor_evaluation_inputs_package(
        package,
        registration_package=registration,
        prediction_lock_package=fixture.prediction_lock_package,
        evaluation_campaign=fixture.evaluation_campaign,
        source_campaign=fixture.source_campaign,
        fit_package=fixture.fit_package,
        adapter_package=fixture.adapter_package,
        expected_evaluation_inputs_manifest_sha256=digest,
    )
    assert checked.externally_digest_bound is True
    return checked


def test_registration_package_roundtrip_exact_closure_and_no_overwrite(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
) -> None:
    fixture = protocol_fixture
    checked = _write_verified_registration(fixture, tmp_path / "registration-package")
    assert {path.name for path in checked.package_dir.iterdir()} == REGISTRATION_PACKAGE_FILES
    assert checked.registration.to_dict() == fixture.registration.to_dict()
    assert checked.plan.to_dict() == fixture.plan.to_dict()
    assert checked.contract.to_dict() == fixture.contract.to_dict()
    assert checked.registration_manifest_sha256 == _sha256(
        checked.package_dir / "registration_manifest.json"
    )

    with pytest.raises(FileExistsError, match="overwrite"):
        write_successor_registration_package(
            fixture.registration,
            fixture.plan,
            fixture.contract,
            checked.package_dir,
            source_campaign=fixture.source_campaign,
            fit_package=fixture.fit_package,
            adapter_package=fixture.adapter_package,
        )


def test_evaluation_input_package_roundtrip_exact_closure_and_no_overwrite(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
) -> None:
    fixture = protocol_fixture
    registration = _write_verified_registration(fixture, tmp_path / "registration")
    checked = _write_verified_evaluation_inputs(
        fixture,
        registration,
        tmp_path / "evaluation-inputs",
    )
    assert {path.name for path in checked.package_dir.iterdir()} == (EVALUATION_INPUT_PACKAGE_FILES)
    assert checked.inputs.execution_chain_ready is False
    assert checked.inputs.prediction_rows_preoutcome_locked is False
    assert checked.inputs.outcome_release_custody_verified is False
    assert checked.evaluation_inputs_manifest_sha256 == _sha256(
        checked.package_dir / "evaluation_inputs_manifest.json"
    )

    with pytest.raises(FileExistsError, match="overwrite"):
        write_successor_evaluation_inputs_package(
            checked.inputs,
            checked.package_dir,
            registration_package=registration,
            prediction_lock_package=fixture.prediction_lock_package,
            evaluation_campaign=fixture.evaluation_campaign,
            source_campaign=fixture.source_campaign,
            fit_package=fixture.fit_package,
            adapter_package=fixture.adapter_package,
        )


def test_final_publication_race_never_replaces_a_new_destination(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = protocol_fixture
    destination = tmp_path / "raced-registration"
    original_rename = successor_module._rename_noreplace

    def inject_competing_destination(source: Path, selected_destination: Path) -> None:
        assert selected_destination == destination
        destination.mkdir()
        (destination / "competing-owner.txt").write_text(
            "must survive publication race",
            encoding="utf-8",
        )
        original_rename(source, selected_destination)

    monkeypatch.setattr(
        successor_module,
        "_rename_noreplace",
        inject_competing_destination,
    )
    with pytest.raises(FileExistsError, match="refusing to overwrite evidence package"):
        write_successor_registration_package(
            fixture.registration,
            fixture.plan,
            fixture.contract,
            destination,
            source_campaign=fixture.source_campaign,
            fit_package=fixture.fit_package,
            adapter_package=fixture.adapter_package,
        )
    assert {path.name for path in destination.iterdir()} == {"competing-owner.txt"}
    assert (destination / "competing-owner.txt").read_text(encoding="utf-8") == (
        "must survive publication race"
    )
    assert not (tmp_path / ".raced-registration.registration.lock").exists()


def test_registration_package_rejects_external_digest_mismatch_and_artifact_tamper(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
) -> None:
    fixture = protocol_fixture
    original = _write_verified_registration(fixture, tmp_path / "original")
    with pytest.raises(ValueError, match="externally supplied digest"):
        verify_successor_registration_package(
            original.package_dir,
            source_campaign=fixture.source_campaign,
            fit_package=fixture.fit_package,
            adapter_package=fixture.adapter_package,
            expected_registration_manifest_sha256="0" * 64,
        )

    tampered = _copy_package(original.package_dir, tmp_path / "tampered")
    registration_path = tampered / "registration.json"
    registration_path.write_bytes(registration_path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="artifact size mismatch"):
        verify_successor_registration_package(
            tampered,
            source_campaign=fixture.source_campaign,
            fit_package=fixture.fit_package,
            adapter_package=fixture.adapter_package,
        )


def test_evaluation_package_rejects_external_digest_mismatch_and_schema_tamper(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
) -> None:
    fixture = protocol_fixture
    registration = _write_verified_registration(fixture, tmp_path / "registration")
    original = _write_verified_evaluation_inputs(
        fixture,
        registration,
        tmp_path / "original-evaluation",
    )
    with pytest.raises(ValueError, match="externally supplied digest"):
        verify_successor_evaluation_inputs_package(
            original.package_dir,
            registration_package=registration,
            prediction_lock_package=fixture.prediction_lock_package,
            evaluation_campaign=fixture.evaluation_campaign,
            source_campaign=fixture.source_campaign,
            fit_package=fixture.fit_package,
            adapter_package=fixture.adapter_package,
            expected_evaluation_inputs_manifest_sha256="0" * 64,
        )

    tampered = _copy_package(original.package_dir, tmp_path / "tampered-evaluation")
    schema_path = tampered / "evaluation_inputs_schema.json"
    schema_path.write_bytes(schema_path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="artifact size mismatch"):
        verify_successor_evaluation_inputs_package(
            tampered,
            registration_package=registration,
            prediction_lock_package=fixture.prediction_lock_package,
            evaluation_campaign=fixture.evaluation_campaign,
            source_campaign=fixture.source_campaign,
            fit_package=fixture.fit_package,
            adapter_package=fixture.adapter_package,
        )


@pytest.mark.parametrize("malformation", ("duplicate", "nonfinite"))
def test_registration_package_parser_rejects_duplicate_and_nonfinite_json(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
    malformation: str,
) -> None:
    fixture = protocol_fixture
    original = _write_verified_registration(fixture, tmp_path / "original")
    malformed = _copy_package(original.package_dir, tmp_path / f"{malformation}-package")
    registration_path = malformed / "registration.json"
    if malformation == "duplicate":
        encoded = registration_path.read_text(encoding="utf-8")
        registration_path.write_text(
            '{"schema_version":"1.0",' + encoded.lstrip()[1:],
            encoding="utf-8",
        )
        expected = "duplicate JSON key"
    else:
        payload = _read_json_object(registration_path)
        payload["planned_cell_count"] = float("nan")
        registration_path.write_text(
            json.dumps(payload, allow_nan=True),
            encoding="utf-8",
        )
        expected = "nonfinite JSON constant"
    digest = _refresh_manifest_artifact(
        malformed,
        manifest_name="registration_manifest.json",
        artifact_name="registration.json",
    )
    with pytest.raises(ValueError, match=expected):
        verify_successor_registration_package(
            malformed,
            source_campaign=fixture.source_campaign,
            fit_package=fixture.fit_package,
            adapter_package=fixture.adapter_package,
            expected_registration_manifest_sha256=digest,
        )


def test_registration_runtime_and_schema_reject_nonmicrosecond_timestamp_json(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
) -> None:
    fixture = protocol_fixture
    original = _write_verified_registration(fixture, tmp_path / "original")
    malformed = _copy_package(original.package_dir, tmp_path / "nonmicrosecond")
    registration_path = malformed / "registration.json"
    payload = _read_json_object(registration_path)
    payload["registered_at_utc"] = "2029-12-31T23:59:59Z"
    _assert_payload_rejected_by_schema(payload, successor_registration_schema())
    registration_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    digest = _refresh_manifest_artifact(
        malformed,
        manifest_name="registration_manifest.json",
        artifact_name="registration.json",
    )
    with pytest.raises(ValueError, match="canonical UTC microsecond form"):
        verify_successor_registration_package(
            malformed,
            source_campaign=fixture.source_campaign,
            fit_package=fixture.fit_package,
            adapter_package=fixture.adapter_package,
            expected_registration_manifest_sha256=digest,
        )


def test_fully_rehashed_authority_escalation_is_rejected(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
) -> None:
    fixture = protocol_fixture
    original = _write_verified_registration(fixture, tmp_path / "original")
    forged = _copy_package(original.package_dir, tmp_path / "forged")
    registration_path = forged / "registration.json"
    payload = _read_json_object(registration_path)
    payload["execution_chain_ready"] = True
    payload["external_validation"] = True
    payload["scientific_use_authorized"] = True
    payload["runner_authorized"] = True
    registration_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    digest = _refresh_manifest_artifact(
        forged,
        manifest_name="registration_manifest.json",
        artifact_name="registration.json",
    )
    with pytest.raises(ValueError, match="cannot assert external assurance or execution"):
        verify_successor_registration_package(
            forged,
            source_campaign=fixture.source_campaign,
            fit_package=fixture.fit_package,
            adapter_package=fixture.adapter_package,
            expected_registration_manifest_sha256=digest,
        )


@pytest.mark.parametrize("unexpected_kind", ("file", "directory"))
def test_registration_verifier_rejects_unexpected_package_entries(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
    unexpected_kind: str,
) -> None:
    fixture = protocol_fixture
    original = _write_verified_registration(fixture, tmp_path / "original")
    changed = _copy_package(original.package_dir, tmp_path / f"extra-{unexpected_kind}")
    unexpected = changed / "unexpected"
    if unexpected_kind == "file":
        unexpected.write_text("not retained", encoding="utf-8")
    else:
        unexpected.mkdir()
    with pytest.raises(ValueError, match="file set mismatch"):
        verify_successor_registration_package(
            changed,
            source_campaign=fixture.source_campaign,
            fit_package=fixture.fit_package,
            adapter_package=fixture.adapter_package,
        )


def test_registration_verifier_rejects_symlinked_artifact(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
) -> None:
    fixture = protocol_fixture
    original = _write_verified_registration(fixture, tmp_path / "original")
    changed = _copy_package(original.package_dir, tmp_path / "symlinked")
    target = changed / "registration.json"
    retained_target = tmp_path / "retained-registration.json"
    shutil.copyfile(target, retained_target)
    target.unlink()
    target.symlink_to(retained_target)
    with pytest.raises(ValueError, match="regular local files"):
        verify_successor_registration_package(
            changed,
            source_campaign=fixture.source_campaign,
            fit_package=fixture.fit_package,
            adapter_package=fixture.adapter_package,
        )


def test_evaluation_verifier_rejects_extra_and_symlinked_entries(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
) -> None:
    fixture = protocol_fixture
    registration = _write_verified_registration(fixture, tmp_path / "registration")
    original = _write_verified_evaluation_inputs(
        fixture,
        registration,
        tmp_path / "original-evaluation",
    )

    extra = _copy_package(original.package_dir, tmp_path / "extra-evaluation")
    (extra / "unexpected.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="file set mismatch"):
        verify_successor_evaluation_inputs_package(
            extra,
            registration_package=registration,
            prediction_lock_package=fixture.prediction_lock_package,
            evaluation_campaign=fixture.evaluation_campaign,
            source_campaign=fixture.source_campaign,
            fit_package=fixture.fit_package,
            adapter_package=fixture.adapter_package,
        )

    symlinked = _copy_package(original.package_dir, tmp_path / "symlinked-evaluation")
    target = symlinked / "evaluation_inputs.json"
    retained_target = tmp_path / "retained-evaluation-inputs.json"
    shutil.copyfile(target, retained_target)
    target.unlink()
    target.symlink_to(retained_target)
    with pytest.raises(ValueError, match="regular local files"):
        verify_successor_evaluation_inputs_package(
            symlinked,
            registration_package=registration,
            prediction_lock_package=fixture.prediction_lock_package,
            evaluation_campaign=fixture.evaluation_campaign,
            source_campaign=fixture.source_campaign,
            fit_package=fixture.fit_package,
            adapter_package=fixture.adapter_package,
        )


def test_unbound_local_manifests_do_not_unlock_the_next_stage(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
) -> None:
    fixture = protocol_fixture
    written = write_successor_registration_package(
        fixture.registration,
        fixture.plan,
        fixture.contract,
        tmp_path / "registration",
        source_campaign=fixture.source_campaign,
        fit_package=fixture.fit_package,
        adapter_package=fixture.adapter_package,
    )
    unbound = verify_successor_registration_package(
        written,
        source_campaign=fixture.source_campaign,
        fit_package=fixture.fit_package,
        adapter_package=fixture.adapter_package,
    )
    assert unbound.externally_digest_bound is False
    with pytest.raises(ValueError, match="externally bound registration"):
        _bind_verified_evaluation_inputs(
            fixture,
            registration_package=unbound,
        )


def test_writers_reject_output_nested_in_any_source_evidence(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
) -> None:
    fixture = protocol_fixture
    registration_destination = fixture.source_campaign.package_dir / "nested-registration"
    before_source = {path.name for path in fixture.source_campaign.package_dir.iterdir()}
    with pytest.raises(ValueError, match="outside every source evidence package"):
        write_successor_registration_package(
            fixture.registration,
            fixture.plan,
            fixture.contract,
            registration_destination,
            source_campaign=fixture.source_campaign,
            fit_package=fixture.fit_package,
            adapter_package=fixture.adapter_package,
        )
    assert {path.name for path in fixture.source_campaign.package_dir.iterdir()} == before_source
    assert not registration_destination.exists()

    registration = _write_verified_registration(fixture, tmp_path / "registration")
    inputs = _bind_verified_evaluation_inputs(
        fixture,
        registration_package=registration,
    )
    evaluation_destination = registration.package_dir / "nested-evaluation-inputs"
    before_registration = {path.name for path in registration.package_dir.iterdir()}
    with pytest.raises(ValueError, match="outside every source evidence package"):
        write_successor_evaluation_inputs_package(
            inputs,
            evaluation_destination,
            registration_package=registration,
            prediction_lock_package=fixture.prediction_lock_package,
            evaluation_campaign=fixture.evaluation_campaign,
            source_campaign=fixture.source_campaign,
            fit_package=fixture.fit_package,
            adapter_package=fixture.adapter_package,
        )
    assert {path.name for path in registration.package_dir.iterdir()} == before_registration
    assert not evaluation_destination.exists()


def test_writers_reject_forged_caller_objects_before_creating_output(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
) -> None:
    fixture = protocol_fixture
    forged_registration = copy(fixture.registration)
    object.__setattr__(forged_registration, "runner_authorized", True)
    registration_destination = tmp_path / "forged-registration"
    with pytest.raises(ValueError, match="deterministic upstream recomputation"):
        write_successor_registration_package(
            forged_registration,
            fixture.plan,
            fixture.contract,
            registration_destination,
            source_campaign=fixture.source_campaign,
            fit_package=fixture.fit_package,
            adapter_package=fixture.adapter_package,
        )
    assert not registration_destination.exists()

    registration = _write_verified_registration(fixture, tmp_path / "registration")
    inputs = _bind_verified_evaluation_inputs(
        fixture,
        registration_package=registration,
    )
    forged_inputs = copy(inputs)
    object.__setattr__(forged_inputs, "runner_authorized", True)
    evaluation_destination = tmp_path / "forged-evaluation"
    with pytest.raises(ValueError, match="deterministic upstream recomputation"):
        write_successor_evaluation_inputs_package(
            forged_inputs,
            evaluation_destination,
            registration_package=registration,
            prediction_lock_package=fixture.prediction_lock_package,
            evaluation_campaign=fixture.evaluation_campaign,
            source_campaign=fixture.source_campaign,
            fit_package=fixture.fit_package,
            adapter_package=fixture.adapter_package,
        )
    assert not evaluation_destination.exists()


@pytest.mark.parametrize("wrapper_kind", ("fit", "adapter"))
def test_registration_write_and_verify_reject_forged_upstream_wrappers_without_output(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
    wrapper_kind: str,
) -> None:
    fixture = protocol_fixture
    fit_package = fixture.fit_package
    adapter_package = fixture.adapter_package
    if wrapper_kind == "fit":
        fit_package = replace(
            fit_package,
            fit=replace(fit_package.fit, runner_authorized=True),
        )
        expected = "fit wrapper differs from its externally bound package"
    else:
        adapter_package = replace(
            adapter_package,
            bundle=replace(adapter_package.bundle, runner_authorized=True),
        )
        expected = "adapter wrapper differs from its externally bound package"

    destination = tmp_path / f"forged-{wrapper_kind}-registration"
    with pytest.raises(ValueError, match=expected):
        write_successor_registration_package(
            fixture.registration,
            fixture.plan,
            fixture.contract,
            destination,
            source_campaign=fixture.source_campaign,
            fit_package=fit_package,
            adapter_package=adapter_package,
        )
    assert not destination.exists()

    retained_package = fixture.registration_package.package_dir
    before = {path.name: path.read_bytes() for path in retained_package.iterdir() if path.is_file()}
    with pytest.raises(ValueError, match=expected):
        verify_successor_registration_package(
            retained_package,
            source_campaign=fixture.source_campaign,
            fit_package=fit_package,
            adapter_package=adapter_package,
            expected_registration_manifest_sha256=(
                fixture.registration_package.registration_manifest_sha256
            ),
        )
    assert {
        path.name: path.read_bytes() for path in retained_package.iterdir() if path.is_file()
    } == before
    assert not destination.exists()


def test_registration_writer_rejects_unbound_source_wrapper_without_output(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
) -> None:
    fixture = protocol_fixture
    destination = tmp_path / "unbound-source-registration"
    unbound_source = replace(
        fixture.source_campaign,
        externally_digest_bound=False,
    )
    with pytest.raises(ValueError, match="campaign wrapper is not externally digest bound"):
        write_successor_registration_package(
            fixture.registration,
            fixture.plan,
            fixture.contract,
            destination,
            source_campaign=unbound_source,
            fit_package=fixture.fit_package,
            adapter_package=fixture.adapter_package,
        )
    assert not destination.exists()


def _write_cli_protocol_inputs(fixture: ProtocolFixture, tmp_path: Path) -> tuple[Path, Path]:
    plan_path = tmp_path / "registration-plan.json"
    contract_path = tmp_path / "transfer-contract.json"
    plan_path.write_text(
        json.dumps(fixture.plan.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    contract_path.write_text(
        json.dumps(fixture.contract.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return plan_path, contract_path


def _registration_cli_command(
    fixture: ProtocolFixture,
    *,
    output_dir: Path,
    plan_path: Path,
    contract_path: Path,
    campaign_digest: str | None = None,
) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "scripts" / "freeze_successor_registration.py"),
        str(fixture.source_campaign.package_dir),
        str(fixture.fit_package.package_dir),
        str(fixture.adapter_package.package_dir),
        str(output_dir),
        "--expected-campaign-evidence-manifest-sha256",
        campaign_digest or fixture.source_campaign_digest,
        "--expected-fit-evidence-manifest-sha256",
        fixture.fit_package.fit_evidence_manifest_sha256,
        "--expected-adapter-policy-sha256",
        fixture.adapter_package.bundle.adapter_policy_sha256,
        "--expected-adapter-manifest-sha256",
        fixture.adapter_package.adapter_manifest_sha256,
        "--plan",
        str(plan_path),
        "--contract",
        str(contract_path),
        "--registered-at-utc",
        fixture.registration.registered_at_utc,
    ]


def test_cli_roundtrip_freezes_registration_then_binds_evaluation_inputs(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
) -> None:
    fixture = protocol_fixture
    plan_path, contract_path = _write_cli_protocol_inputs(fixture, tmp_path)
    registration_dir = tmp_path / "cli-registration"
    frozen = subprocess.run(
        _registration_cli_command(
            fixture,
            output_dir=registration_dir,
            plan_path=plan_path,
            contract_path=contract_path,
        ),
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert frozen.returncode == 0, frozen.stderr
    frozen_status = json.loads(frozen.stdout)
    assert frozen_status["chronology_consistent"] is True
    assert frozen_status["registration_time_externally_attested"] is False
    assert frozen_status["execution_chain_ready"] is False
    assert frozen_status["external_validation"] is False
    assert frozen_status["scientific_use_authorized"] is False
    assert frozen_status["runner_authorized"] is False
    registration_digest = _sha256(registration_dir / "registration_manifest.json")
    assert frozen_status["registration_manifest_sha256"] == registration_digest
    assert {path.name for path in registration_dir.iterdir()} == REGISTRATION_PACKAGE_FILES

    evaluation_dir = tmp_path / "cli-evaluation-inputs"
    bound = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "bind_successor_evaluation_inputs.py"),
            str(fixture.source_campaign.package_dir),
            str(fixture.fit_package.package_dir),
            str(fixture.adapter_package.package_dir),
            str(registration_dir),
            str(fixture.prediction_lock_package.package_dir),
            str(fixture.evaluation_campaign.package_dir),
            str(evaluation_dir),
            "--expected-source-campaign-manifest-sha256",
            fixture.source_campaign_digest,
            "--expected-fit-manifest-sha256",
            fixture.fit_package.fit_evidence_manifest_sha256,
            "--expected-adapter-policy-sha256",
            fixture.adapter_package.bundle.adapter_policy_sha256,
            "--expected-adapter-manifest-sha256",
            fixture.adapter_package.adapter_manifest_sha256,
            "--expected-registration-manifest-sha256",
            registration_digest,
            "--expected-prediction-lock-manifest-sha256",
            fixture.prediction_lock_digest,
            "--expected-evaluation-campaign-manifest-sha256",
            fixture.evaluation_campaign_digest,
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert bound.returncode == 0, bound.stderr
    bound_status = json.loads(bound.stdout)
    assert bound_status["chronology_consistent"] is True
    assert bound_status["prediction_lock_binding_reconciled"] is True
    assert bound_status["prediction_rows_target_free"] is True
    assert bound_status["prediction_rows_preoutcome_locked"] is False
    assert bound_status["execution_chain_ready"] is False
    assert bound_status["external_validation"] is False
    assert bound_status["scientific_use_authorized"] is False
    assert bound_status["runner_authorized"] is False
    assert bound_status["evaluation_inputs_manifest_sha256"] == _sha256(
        evaluation_dir / "evaluation_inputs_manifest.json"
    )
    assert {path.name for path in evaluation_dir.iterdir()} == (EVALUATION_INPUT_PACKAGE_FILES)


def test_registration_cli_fails_closed_on_wrong_external_digest(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
) -> None:
    fixture = protocol_fixture
    plan_path, contract_path = _write_cli_protocol_inputs(fixture, tmp_path)
    destination = tmp_path / "rejected-cli-registration"
    completed = subprocess.run(
        _registration_cli_command(
            fixture,
            output_dir=destination,
            plan_path=plan_path,
            contract_path=contract_path,
            campaign_digest="0" * 64,
        ),
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode != 0
    assert "externally supplied digest" in completed.stderr
    assert not destination.exists()
