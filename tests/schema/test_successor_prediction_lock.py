from __future__ import annotations

import hashlib
import inspect
import json
import math
import shutil
from copy import copy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
import pytest

# The predecessor protocol fixture is intentionally imported instead of copied.
# It constructs the complete physical source -> fit -> adapter -> registration
# chain and therefore exercises the same boundary used by the lock API.
from test_successor_protocol import (  # type: ignore[import-not-found]
    ProtocolFixture,
    _adapter_policy,
    _assert_payload_satisfies_schema,
    _fit_policy,
    _measurement_frame,
    _registration_plan,
    _sha256,
    _transfer_contract,
    _verified_campaign,
)
from test_successor_protocol import (
    protocol_fixture as _protocol_fixture,
)

import fleet_sim.empirical.prediction_lock as prediction_module
from fleet_sim.control_plane.resource_network import ResourceType
from fleet_sim.empirical.calibration_gate import (
    fit_empirical_calibration,
    prepare_calibration_fit_input,
    verify_empirical_calibration_package,
    write_empirical_calibration_package,
)
from fleet_sim.empirical.prediction_lock import (
    PREDICTION_LOCK_PACKAGE_FILES,
    PREDICTION_PARAMETER_DRAW_COLUMNS,
    PREDICTION_ROW_COLUMNS,
    SuccessorPredictionLock,
    SuccessorPredictionLockPackageVerification,
    SuccessorPredictionLockRun,
    build_successor_prediction_lock,
    successor_prediction_lock_schema,
    successor_prediction_parameter_draws_schema,
    successor_prediction_rows_schema,
    verify_successor_prediction_lock_package,
    write_successor_prediction_lock_package,
)
from fleet_sim.empirical.resource_adapter import (
    VerifiedResourceAdapterPolicy,
    adapt_accepted_fit_to_resource_specs,
    verify_adapted_resource_bundle,
    write_adapted_resource_bundle,
)
from fleet_sim.empirical.successor_protocol import (
    PROTOCOL_SCHEMA_VERSION,
    UNCERTAINTY_METHOD,
    UNCERTAINTY_QUANTILE_METHOD,
    UNCERTAINTY_SCOPE,
    freeze_successor_registration,
    verify_successor_registration_package,
    write_successor_registration_package,
)

ROOT = Path(__file__).resolve().parents[2]
LOCK_SCHEMA = ROOT / "schemas" / "successor_prediction_lock.schema.json"
ROWS_SCHEMA = ROOT / "schemas" / "successor_prediction_rows.schema.json"
DRAW_SCHEMA = ROOT / "schemas" / "successor_prediction_parameter_draws.schema.json"
COMMITTED_AT = "2030-01-01T11:58:59.000000Z"

TARGET_OR_POSTOUTCOME_COLUMNS = {
    "arrival_count",
    "service_count",
    "queue_depth",
    "service_time_ms",
    "wait_time_ms",
    "capacity_units_per_second",
    "deadline_ms",
    "dropped_work",
    "deferred_work",
    "error_count",
    "is_censored",
    "missing_fraction",
    "measurement_provenance",
    "source_type",
    "partition",
}


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _assert_schema(payload: object, schema: dict[str, object]) -> None:
    assert isinstance(payload, dict)
    _assert_payload_satisfies_schema(payload, schema)


def _copy_package(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination)
    return destination


def _refresh_manifest_artifact(package: Path, artifact_name: str) -> str:
    manifest_path = package / "prediction_lock_manifest.json"
    manifest = _read_json(manifest_path)
    records = cast(list[dict[str, object]], manifest["artifacts"])
    matches = [item for item in records if item.get("path") == artifact_name]
    assert len(matches) == 1
    artifact = package / artifact_name
    matches[0]["bytes"] = artifact.stat().st_size
    matches[0]["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest.pop("self_integrity_sha256", None)
    manifest["self_integrity_sha256"] = hashlib.sha256(_canonical_json_bytes(manifest)).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def _comparator_coefficient(group: pd.DataFrame) -> float:
    duration_s = group["window_duration_ms"].to_numpy(float) / 1000.0
    fleet_size = group["fleet_size"].to_numpy(float)
    arrival_count = group["arrival_count"].to_numpy(float)
    numerator = math.fsum(
        float(fleet_size[index] * arrival_count[index]) for index in range(len(group))
    )
    denominator = math.fsum(
        float(duration_s[index] * fleet_size[index] ** 2) for index in range(len(group))
    )
    assert denominator > 0.0
    return max(0.0, numerator / denominator)


def _circular_sample(block_count: int, block_length: int, rng: np.random.Generator) -> np.ndarray:
    selected: list[int] = []
    while len(selected) < block_count:
        start = int(rng.integers(0, block_count))
        for offset in range(block_length):
            selected.append((start + offset) % block_count)
            if len(selected) == block_count:
                break
    return np.asarray(selected, dtype=np.int64)


@pytest.fixture(scope="module")
def protocol_fixture(tmp_path_factory: pytest.TempPathFactory) -> ProtocolFixture:
    builder = _protocol_fixture.__wrapped__
    return cast(ProtocolFixture, builder(tmp_path_factory))


@pytest.fixture(scope="module")
def prediction_run(protocol_fixture: ProtocolFixture) -> SuccessorPredictionLockRun:
    return build_successor_prediction_lock(
        protocol_fixture.registration_package,
        source_campaign=protocol_fixture.source_campaign,
        fit_package=protocol_fixture.fit_package,
        adapter_package=protocol_fixture.adapter_package,
        committed_at_utc=COMMITTED_AT,
    )


@pytest.fixture(scope="module")
def prediction_package(
    protocol_fixture: ProtocolFixture,
    prediction_run: SuccessorPredictionLockRun,
    tmp_path_factory: pytest.TempPathFactory,
) -> SuccessorPredictionLockPackageVerification:
    destination = tmp_path_factory.mktemp("successor-prediction-lock") / "package"
    package = write_successor_prediction_lock_package(
        prediction_run,
        destination,
        registration_package=protocol_fixture.registration_package,
        source_campaign=protocol_fixture.source_campaign,
        fit_package=protocol_fixture.fit_package,
        adapter_package=protocol_fixture.adapter_package,
    )
    digest = hashlib.sha256((package / "prediction_lock_manifest.json").read_bytes()).hexdigest()
    return verify_successor_prediction_lock_package(
        package,
        registration_package=protocol_fixture.registration_package,
        source_campaign=protocol_fixture.source_campaign,
        fit_package=protocol_fixture.fit_package,
        adapter_package=protocol_fixture.adapter_package,
        expected_prediction_lock_manifest_sha256=digest,
    )


def test_lock_api_has_no_future_campaign_or_outcome_input(
    prediction_run: SuccessorPredictionLockRun,
) -> None:
    for function in (
        build_successor_prediction_lock,
        write_successor_prediction_lock_package,
        verify_successor_prediction_lock_package,
    ):
        parameters = inspect.signature(function).parameters
        assert all(
            parameter.kind is not inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
        )
        assert not {
            name
            for name in parameters
            if any(token in name.lower() for token in ("evaluation", "outcome", "heldout"))
        }
    assert set(prediction_run.prediction_rows.columns) == set(PREDICTION_ROW_COLUMNS)
    assert TARGET_OR_POSTOUTCOME_COLUMNS.isdisjoint(prediction_run.prediction_rows.columns)
    assert TARGET_OR_POSTOUTCOME_COLUMNS.isdisjoint(prediction_run.parameter_draws.columns)


def test_target_free_commitment_does_not_claim_scientific_preoutcome_custody(
    prediction_run: SuccessorPredictionLockRun,
) -> None:
    lock = prediction_run.lock
    assert lock.source_historical_heldout_used_for_prediction is False
    assert lock.future_evaluation_campaign_not_supplied is True
    assert lock.prediction_rows_target_free is True
    assert lock.local_lock_chronology_consistent is True
    assert lock.workflow_prediction_commitment is True
    assert lock.prediction_lock_time_externally_attested is False
    assert lock.prediction_rows_preoutcome_locked is False
    assert lock.outcome_release_custody_verified is False
    assert lock.execution_chain_ready is False
    assert lock.external_validation is False
    assert lock.scientific_use_authorized is False
    assert lock.runner_authorized is False


@pytest.mark.parametrize(
    "committed_at",
    (
        "2029-12-31T23:59:58.000000Z",
        "2030-01-01T11:59:00.000000Z",
        "2030-01-01T11:59:00.000001Z",
        "2030-01-01T11:58:59Z",
    ),
)
def test_local_commit_chronology_fails_closed_outside_the_canonical_open_window(
    protocol_fixture: ProtocolFixture,
    committed_at: str,
) -> None:
    with pytest.raises(ValueError, match="commitment|canonical"):
        build_successor_prediction_lock(
            protocol_fixture.registration_package,
            source_campaign=protocol_fixture.source_campaign,
            fit_package=protocol_fixture.fit_package,
            adapter_package=protocol_fixture.adapter_package,
            committed_at_utc=committed_at,
        )


def test_candidate_and_comparator_points_match_hand_computation(
    protocol_fixture: ProtocolFixture,
    prediction_run: SuccessorPredictionLockRun,
) -> None:
    rows = prediction_run.prediction_rows
    selected = rows.sort_values(
        ["cell_id", "time_block_id", "resource_type"], kind="mergesort"
    ).iloc[0]
    parameters = {item.resource_type: item for item in prediction_run.lock.resource_parameters}[
        str(selected["resource_type"])
    ]
    duration_s = float(selected["window_duration_ms"]) / 1000.0
    admission_rate = float(selected["agents_admitted"]) / duration_s
    expected_candidate_rate = (
        parameters.candidate_background_work_per_agent_s * float(selected["fleet_size"])
        + parameters.candidate_admission_work_units_per_agent * admission_rate
    )
    assert float(selected["candidate_mean_arrival_rate_point_per_s"]) == pytest.approx(
        expected_candidate_rate,
        rel=0.0,
        abs=1e-12,
    )
    assert float(selected["candidate_mean_arrival_count_point"]) == pytest.approx(
        expected_candidate_rate * duration_s,
        rel=0.0,
        abs=1e-12,
    )

    calibration = protocol_fixture.source_campaign.calibration
    resource_calibration = calibration[
        calibration["resource_type"].astype(str) == str(selected["resource_type"])
    ]
    expected_comparator = _comparator_coefficient(resource_calibration)
    assert parameters.comparator_background_work_per_agent_s == pytest.approx(
        expected_comparator,
        rel=0.0,
        abs=1e-14,
    )
    expected_comparator_rate = expected_comparator * float(selected["fleet_size"])
    assert float(selected["comparator_mean_arrival_rate_point_per_s"]) == pytest.approx(
        expected_comparator_rate,
        rel=0.0,
        abs=1e-12,
    )


def test_parameter_draws_are_paired_with_the_fit_and_reconstruct_the_comparator(
    protocol_fixture: ProtocolFixture,
    prediction_run: SuccessorPredictionLockRun,
) -> None:
    draws = prediction_run.parameter_draws
    assert tuple(draws.columns) == PREDICTION_PARAMETER_DRAW_COLUMNS
    per_replication = draws.groupby("bootstrap_replication", sort=True)
    assert set(per_replication.size().astype(int)) == {len(ResourceType)}
    assert set(per_replication["sampled_block_sequence_sha256"].nunique().astype(int)) == {1}

    retained_fit = protocol_fixture.fit_package.bootstrap_draws.rename(
        columns={
            "background_work_per_agent_s": "candidate_background_work_per_agent_s",
            "admission_work_units_per_agent": "candidate_admission_work_units_per_agent",
        }
    )
    candidate_columns = [
        "bootstrap_replication",
        "sampled_block_sequence_sha256",
        "resource_id",
        "resource_type",
        "candidate_background_work_per_agent_s",
        "candidate_admission_work_units_per_agent",
    ]
    pd.testing.assert_frame_equal(
        draws[candidate_columns].reset_index(drop=True),
        retained_fit[candidate_columns].reset_index(drop=True),
        check_exact=True,
        check_dtype=True,
    )

    first_replication = int(draws["bootstrap_replication"].min())
    rng = np.random.default_rng(protocol_fixture.fit_package.fit.policy.root_seed)
    positions: np.ndarray | None = None
    block_count = protocol_fixture.source_campaign.calibration["time_block_id"].nunique()
    for replication in range(first_replication + 1):
        positions = _circular_sample(
            int(block_count),
            protocol_fixture.fit_package.fit.policy.bootstrap_block_length,
            rng,
        )
    assert positions is not None
    resource_type = ResourceType.IDENTITY_ISSUANCE.value
    group = (
        protocol_fixture.source_campaign.calibration[
            protocol_fixture.source_campaign.calibration["resource_type"] == resource_type
        ]
        .sort_values(["timestamp", "time_block_id"], kind="mergesort")
        .reset_index(drop=True)
    )
    expected_comparator = _comparator_coefficient(group.iloc[positions].reset_index(drop=True))
    retained = draws[
        (draws["bootstrap_replication"] == first_replication)
        & (draws["resource_type"] == resource_type)
    ]
    assert len(retained) == 1
    assert float(retained.iloc[0]["comparator_background_work_per_agent_s"]) == pytest.approx(
        expected_comparator,
        rel=0.0,
        abs=1e-14,
    )


def test_prediction_intervals_reconstruct_from_the_paired_draws(
    prediction_run: SuccessorPredictionLockRun,
) -> None:
    assert prediction_run.lock.uncertainty_method == UNCERTAINTY_METHOD
    assert prediction_run.lock.bootstrap_quantile_method == UNCERTAINTY_QUANTILE_METHOD
    assert prediction_run.lock.uncertainty_scope == UNCERTAINTY_SCOPE
    assert "not_simultaneous_or_future_observation" in prediction_run.lock.uncertainty_scope
    row = prediction_run.prediction_rows.sort_values(
        ["cell_id", "time_block_id", "resource_type"], kind="mergesort"
    ).iloc[0]
    draws = prediction_run.parameter_draws[
        prediction_run.parameter_draws["resource_type"] == row["resource_type"]
    ]
    duration_s = float(row["window_duration_ms"]) / 1000.0
    admission_rate = float(row["agents_admitted"]) / duration_s
    candidate = (
        draws["candidate_background_work_per_agent_s"].to_numpy(float) * float(row["fleet_size"])
        + draws["candidate_admission_work_units_per_agent"].to_numpy(float) * admission_rate
    )
    comparator = draws["comparator_background_work_per_agent_s"].to_numpy(float) * float(
        row["fleet_size"]
    )
    alpha = (1.0 - prediction_run.lock.bootstrap_interval_level) / 2.0
    candidate_bounds = np.quantile(candidate, [alpha, 1.0 - alpha], method="linear")
    comparator_bounds = np.quantile(comparator, [alpha, 1.0 - alpha], method="linear")
    assert float(row["candidate_mean_arrival_rate_lower_per_s"]) == pytest.approx(
        candidate_bounds[0], rel=0.0, abs=1e-12
    )
    assert float(row["candidate_mean_arrival_rate_upper_per_s"]) == pytest.approx(
        candidate_bounds[1], rel=0.0, abs=1e-12
    )
    assert float(row["comparator_mean_arrival_rate_lower_per_s"]) == pytest.approx(
        comparator_bounds[0], rel=0.0, abs=1e-12
    )
    assert float(row["comparator_mean_arrival_rate_upper_per_s"]) == pytest.approx(
        comparator_bounds[1], rel=0.0, abs=1e-12
    )


def test_rows_have_exact_ten_resource_by_block_closure_and_deterministic_order(
    protocol_fixture: ProtocolFixture,
    prediction_run: SuccessorPredictionLockRun,
) -> None:
    rows = prediction_run.prediction_rows
    expected_blocks = {
        block.time_block_id
        for cell in protocol_fixture.registration_package.plan.cells
        for block in cell.planned_blocks
    }
    assert len(rows) == len(expected_blocks) * len(ResourceType)
    assert set(rows["time_block_id"].astype(str)) == expected_blocks
    assert set(rows["resource_type"].astype(str)) == {item.value for item in ResourceType}
    assert not rows.duplicated(["cell_id", "time_block_id", "resource_type"]).any()
    assert set(rows.groupby("time_block_id")["resource_type"].nunique().astype(int)) == {
        len(ResourceType)
    }
    expected = rows.sort_values(
        ["cell_id", "time_block_id", "resource_type"], kind="mergesort"
    ).reset_index(drop=True)
    pd.testing.assert_frame_equal(rows.reset_index(drop=True), expected, check_exact=True)
    expected_design = {
        block.time_block_id: (
            cell.cell_id,
            block.timestamp_utc,
            block.fleet_size,
            block.agents_admitted,
            float(block.window_duration_ms),
        )
        for cell in protocol_fixture.registration_package.plan.cells
        for block in cell.planned_blocks
    }
    for block_id, block_rows in rows.groupby("time_block_id", sort=False):
        expected_values = expected_design[str(block_id)]
        observed = {
            (
                str(row["cell_id"]),
                str(row["timestamp_utc"]),
                int(row["fleet_size"]),
                int(row["agents_admitted"]),
                float(row["window_duration_ms"]),
            )
            for row in block_rows.to_dict("records")
        }
        assert observed == {expected_values}


def test_lock_rebuild_is_byte_semantically_deterministic(
    protocol_fixture: ProtocolFixture,
    prediction_run: SuccessorPredictionLockRun,
) -> None:
    repeated = build_successor_prediction_lock(
        protocol_fixture.registration_package,
        source_campaign=protocol_fixture.source_campaign,
        fit_package=protocol_fixture.fit_package,
        adapter_package=protocol_fixture.adapter_package,
        committed_at_utc=COMMITTED_AT,
    )
    assert repeated.lock.to_dict() == prediction_run.lock.to_dict()
    pd.testing.assert_frame_equal(
        repeated.prediction_rows,
        prediction_run.prediction_rows,
        check_exact=True,
        check_dtype=True,
    )
    pd.testing.assert_frame_equal(
        repeated.parameter_draws,
        prediction_run.parameter_draws,
        check_exact=True,
        check_dtype=True,
    )


def test_historical_heldout_outcomes_cannot_change_prediction_numbers(
    protocol_fixture: ProtocolFixture,
    prediction_run: SuccessorPredictionLockRun,
    tmp_path: Path,
) -> None:
    campaign_id = cast(str, protocol_fixture.source_campaign.evidence_manifest["campaign_id"])
    frame = _measurement_frame(campaign_id, base_time="2026-08-20T12:00:00Z")
    heldout = frame["partition"] == "heldout"
    frame.loc[heldout, "arrival_count"] = (
        frame.loc[heldout, "arrival_count"].astype(int) + 1_000_000
    )
    frame.loc[heldout, "service_count"] = frame.loc[heldout, "arrival_count"]
    altered_source, altered_source_digest = _verified_campaign(
        tmp_path,
        campaign_id=campaign_id,
        base_time="2026-08-20T12:00:00Z",
        collection_start="2026-08-20T11:59:59Z",
        collection_end="2026-08-20T12:02:00Z",
        frame=frame,
    )
    assert altered_source_digest != protocol_fixture.source_campaign_digest
    pd.testing.assert_frame_equal(
        altered_source.calibration,
        protocol_fixture.source_campaign.calibration,
        check_exact=True,
        check_dtype=True,
    )
    assert not altered_source.heldout.equals(protocol_fixture.source_campaign.heldout)

    fit_input = prepare_calibration_fit_input(
        altered_source.package_dir,
        expected_evidence_manifest_sha256=altered_source_digest,
    )
    fit_policy = _fit_policy()
    fit_run = fit_empirical_calibration(fit_input, fit_policy)
    fit_path = write_empirical_calibration_package(
        fit_run,
        fit_input,
        tmp_path / "altered-fit-package",
    )
    fit_digest = _sha256(fit_path / "fit_evidence_manifest.json")
    fit_package = verify_empirical_calibration_package(
        fit_path,
        source_campaign_package=altered_source.package_dir,
        expected_source_evidence_manifest_sha256=altered_source_digest,
        expected_fit_evidence_manifest_sha256=fit_digest,
    )
    adapter_policy = _adapter_policy(fit_policy)
    verified_policy = VerifiedResourceAdapterPolicy(
        policy=adapter_policy,
        policy_sha256=adapter_policy.policy_sha256,
        externally_digest_bound=True,
    )
    adapter_bundle = adapt_accepted_fit_to_resource_specs(fit_package, verified_policy)
    adapter_path = write_adapted_resource_bundle(
        adapter_bundle,
        verified_policy,
        tmp_path / "altered-adapter-package",
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
        altered_source,
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
        tmp_path / "altered-registration-package",
        source_campaign=altered_source,
        fit_package=fit_package,
        adapter_package=adapter_package,
    )
    registration_digest = _sha256(registration_path / "registration_manifest.json")
    registration_package = verify_successor_registration_package(
        registration_path,
        source_campaign=altered_source,
        fit_package=fit_package,
        adapter_package=adapter_package,
        expected_registration_manifest_sha256=registration_digest,
    )
    altered = build_successor_prediction_lock(
        registration_package,
        source_campaign=altered_source,
        fit_package=fit_package,
        adapter_package=adapter_package,
        committed_at_utc=COMMITTED_AT,
    )

    pd.testing.assert_frame_equal(
        altered.prediction_rows,
        prediction_run.prediction_rows,
        check_exact=True,
        check_dtype=True,
    )
    pd.testing.assert_frame_equal(
        altered.parameter_draws,
        prediction_run.parameter_draws,
        check_exact=True,
        check_dtype=True,
    )


def test_v10_lock_payload_is_rejected(prediction_run: SuccessorPredictionLockRun) -> None:
    assert PROTOCOL_SCHEMA_VERSION == "1.1"
    payload = prediction_run.lock.to_dict()
    payload["schema_version"] = "1.0"
    with pytest.raises(ValueError, match="schema_version"):
        SuccessorPredictionLock.from_mapping(payload)


def test_checked_in_schemas_equal_live_contracts() -> None:
    pairs = (
        (LOCK_SCHEMA, successor_prediction_lock_schema()),
        (ROWS_SCHEMA, successor_prediction_rows_schema()),
        (DRAW_SCHEMA, successor_prediction_parameter_draws_schema()),
    )
    for path, live in pairs:
        assert _read_json(path) == live
        assert live["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_live_payloads_satisfy_closed_schemas(
    prediction_run: SuccessorPredictionLockRun,
) -> None:
    _assert_schema(prediction_run.lock.to_dict(), successor_prediction_lock_schema())
    for row in prediction_run.prediction_rows.to_dict("records"):
        _assert_schema(row, successor_prediction_rows_schema())
    for row in prediction_run.parameter_draws.to_dict("records"):
        _assert_schema(row, successor_prediction_parameter_draws_schema())


def test_package_roundtrip_exact_closure_and_external_digest_binding(
    protocol_fixture: ProtocolFixture,
    prediction_run: SuccessorPredictionLockRun,
    prediction_package: SuccessorPredictionLockPackageVerification,
) -> None:
    assert {path.name for path in prediction_package.package_dir.iterdir()} == (
        PREDICTION_LOCK_PACKAGE_FILES
    )
    assert prediction_package.externally_digest_bound is True
    assert prediction_package.lock.to_dict() == prediction_run.lock.to_dict()
    assert (
        prediction_package.prediction_lock_manifest_sha256
        == hashlib.sha256(
            (prediction_package.package_dir / "prediction_lock_manifest.json").read_bytes()
        ).hexdigest()
    )
    pd.testing.assert_frame_equal(
        prediction_package.prediction_rows,
        prediction_run.prediction_rows,
        check_exact=True,
        check_dtype=True,
    )
    pd.testing.assert_frame_equal(
        prediction_package.parameter_draws,
        prediction_run.parameter_draws,
        check_exact=True,
        check_dtype=True,
    )
    unbound = verify_successor_prediction_lock_package(
        prediction_package.package_dir,
        registration_package=protocol_fixture.registration_package,
        source_campaign=protocol_fixture.source_campaign,
        fit_package=protocol_fixture.fit_package,
        adapter_package=protocol_fixture.adapter_package,
    )
    assert unbound.externally_digest_bound is False
    assert unbound.lock.prediction_lock_time_externally_attested is False
    assert unbound.lock.prediction_rows_preoutcome_locked is False
    assert unbound.lock.outcome_release_custody_verified is False
    assert unbound.lock.scientific_use_authorized is False


def test_public_package_excludes_upstream_paths_and_outcome_payload_columns(
    protocol_fixture: ProtocolFixture,
    prediction_package: SuccessorPredictionLockPackageVerification,
) -> None:
    serialized_lock = _canonical_json_bytes(prediction_package.lock.to_dict())
    upstream_paths = (
        protocol_fixture.source_campaign.package_dir,
        protocol_fixture.fit_package.package_dir,
        protocol_fixture.adapter_package.package_dir,
        protocol_fixture.registration_package.package_dir,
    )
    for upstream_path in upstream_paths:
        assert str(upstream_path).encode("utf-8") not in serialized_lock
    assert TARGET_OR_POSTOUTCOME_COLUMNS.isdisjoint(prediction_package.prediction_rows.columns)
    assert TARGET_OR_POSTOUTCOME_COLUMNS.isdisjoint(prediction_package.parameter_draws.columns)
    assert all(
        not path.startswith(("/", "~")) and ".." not in Path(path).parts
        for path, _digest in prediction_package.lock.implementation
    )


def test_wrong_external_digest_and_unrehash_tamper_fail_closed(
    protocol_fixture: ProtocolFixture,
    prediction_package: SuccessorPredictionLockPackageVerification,
    tmp_path: Path,
) -> None:
    kwargs = {
        "registration_package": protocol_fixture.registration_package,
        "source_campaign": protocol_fixture.source_campaign,
        "fit_package": protocol_fixture.fit_package,
        "adapter_package": protocol_fixture.adapter_package,
    }
    with pytest.raises(ValueError, match="externally supplied digest"):
        verify_successor_prediction_lock_package(
            prediction_package.package_dir,
            expected_prediction_lock_manifest_sha256="0" * 64,
            **kwargs,
        )

    changed = _copy_package(prediction_package.package_dir, tmp_path / "tampered")
    rows_path = changed / "prediction_rows.parquet"
    rows_path.write_bytes(rows_path.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="artifact"):
        verify_successor_prediction_lock_package(
            changed,
            expected_prediction_lock_manifest_sha256=prediction_package.prediction_lock_manifest_sha256,
            **kwargs,
        )


def test_fully_rehashed_authority_escalation_is_rejected(
    protocol_fixture: ProtocolFixture,
    prediction_package: SuccessorPredictionLockPackageVerification,
    tmp_path: Path,
) -> None:
    changed = _copy_package(prediction_package.package_dir, tmp_path / "authority-escalation")
    lock_path = changed / "prediction_lock.json"
    payload = _read_json(lock_path)
    payload["prediction_rows_preoutcome_locked"] = True
    payload["prediction_lock_time_externally_attested"] = True
    payload["runner_authorized"] = True
    lock_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    digest = _refresh_manifest_artifact(changed, "prediction_lock.json")
    with pytest.raises(ValueError, match="boundary|authorization|attested"):
        verify_successor_prediction_lock_package(
            changed,
            registration_package=protocol_fixture.registration_package,
            source_campaign=protocol_fixture.source_campaign,
            fit_package=protocol_fixture.fit_package,
            adapter_package=protocol_fixture.adapter_package,
            expected_prediction_lock_manifest_sha256=digest,
        )


@pytest.mark.parametrize("wrapper_kind", ("source", "fit", "adapter", "registration"))
def test_build_rejects_forged_upstream_wrappers(
    protocol_fixture: ProtocolFixture,
    wrapper_kind: str,
) -> None:
    source = protocol_fixture.source_campaign
    fit = protocol_fixture.fit_package
    adapter = protocol_fixture.adapter_package
    registration = protocol_fixture.registration_package
    if wrapper_kind == "source":
        source = replace(source, externally_digest_bound=False)
    elif wrapper_kind == "fit":
        fit = replace(fit, fit=replace(fit.fit, runner_authorized=True))
    elif wrapper_kind == "adapter":
        adapter = replace(
            adapter,
            bundle=replace(adapter.bundle, runner_authorized=True),
        )
    else:
        forged = copy(registration.registration)
        object.__setattr__(forged, "runner_authorized", True)
        registration = replace(registration, registration=forged)
    with pytest.raises(ValueError, match="wrapper|bound|recomputation"):
        build_successor_prediction_lock(
            registration,
            source_campaign=source,
            fit_package=fit,
            adapter_package=adapter,
            committed_at_utc=COMMITTED_AT,
        )


def test_physical_upstream_tamper_is_reverified(
    protocol_fixture: ProtocolFixture,
    tmp_path: Path,
) -> None:
    changed_path = _copy_package(protocol_fixture.fit_package.package_dir, tmp_path / "fit-tamper")
    policy_path = changed_path / "calibration_policy.json"
    policy_path.write_bytes(policy_path.read_bytes() + b" ")
    changed_fit = replace(protocol_fixture.fit_package, package_dir=changed_path)
    with pytest.raises(ValueError, match="artifact|manifest|hash"):
        build_successor_prediction_lock(
            protocol_fixture.registration_package,
            source_campaign=protocol_fixture.source_campaign,
            fit_package=changed_fit,
            adapter_package=protocol_fixture.adapter_package,
            committed_at_utc=COMMITTED_AT,
        )


@pytest.mark.parametrize("mutation", ("missing", "extra", "symlink"))
def test_verifier_rejects_nonclosed_or_symlinked_packages(
    protocol_fixture: ProtocolFixture,
    prediction_package: SuccessorPredictionLockPackageVerification,
    tmp_path: Path,
    mutation: str,
) -> None:
    changed = _copy_package(prediction_package.package_dir, tmp_path / mutation)
    if mutation == "missing":
        (changed / "prediction_rows_schema.json").unlink()
    elif mutation == "extra":
        (changed / "extra.txt").write_text("unexpected", encoding="utf-8")
    else:
        target = changed / "prediction_lock_schema.json"
        retained = tmp_path / "retained-schema.json"
        shutil.copyfile(target, retained)
        target.unlink()
        target.symlink_to(retained)
    with pytest.raises(ValueError, match="file set|regular|symlink"):
        verify_successor_prediction_lock_package(
            changed,
            registration_package=protocol_fixture.registration_package,
            source_campaign=protocol_fixture.source_campaign,
            fit_package=protocol_fixture.fit_package,
            adapter_package=protocol_fixture.adapter_package,
            expected_prediction_lock_manifest_sha256=prediction_package.prediction_lock_manifest_sha256,
        )


def test_verifier_rejects_oversize_and_nonfinite_json(
    protocol_fixture: ProtocolFixture,
    prediction_package: SuccessorPredictionLockPackageVerification,
    tmp_path: Path,
) -> None:
    kwargs = {
        "registration_package": protocol_fixture.registration_package,
        "source_campaign": protocol_fixture.source_campaign,
        "fit_package": protocol_fixture.fit_package,
        "adapter_package": protocol_fixture.adapter_package,
    }
    with pytest.raises(ValueError, match="limit|exceeds|bytes"):
        verify_successor_prediction_lock_package(
            prediction_package.package_dir,
            expected_prediction_lock_manifest_sha256=prediction_package.prediction_lock_manifest_sha256,
            maximum_package_bytes=64,
            **kwargs,
        )
    with pytest.raises(ValueError, match="limit|exceeds|rows"):
        verify_successor_prediction_lock_package(
            prediction_package.package_dir,
            expected_prediction_lock_manifest_sha256=prediction_package.prediction_lock_manifest_sha256,
            maximum_rows=1,
            **kwargs,
        )
    with pytest.raises(ValueError, match="limit|exceeds|uncompressed|bytes"):
        verify_successor_prediction_lock_package(
            prediction_package.package_dir,
            expected_prediction_lock_manifest_sha256=prediction_package.prediction_lock_manifest_sha256,
            maximum_uncompressed_bytes=64,
            **kwargs,
        )

    changed = _copy_package(prediction_package.package_dir, tmp_path / "nonfinite")
    lock_path = changed / "prediction_lock.json"
    text = lock_path.read_text(encoding="utf-8")
    text = text.replace(
        f'"bootstrap_interval_level": {prediction_package.lock.bootstrap_interval_level}',
        '"bootstrap_interval_level": NaN',
    )
    assert "NaN" in text
    lock_path.write_text(text, encoding="utf-8")
    digest = _refresh_manifest_artifact(changed, "prediction_lock.json")
    with pytest.raises(ValueError, match="nonfinite"):
        verify_successor_prediction_lock_package(
            changed,
            expected_prediction_lock_manifest_sha256=digest,
            **kwargs,
        )


@pytest.mark.parametrize("source_name", ("campaign", "fit", "adapter", "registration"))
def test_writer_rejects_output_nested_in_every_source_package(
    protocol_fixture: ProtocolFixture,
    prediction_run: SuccessorPredictionLockRun,
    source_name: str,
) -> None:
    sources = {
        "campaign": protocol_fixture.source_campaign.package_dir,
        "fit": protocol_fixture.fit_package.package_dir,
        "adapter": protocol_fixture.adapter_package.package_dir,
        "registration": protocol_fixture.registration_package.package_dir,
    }
    destination = sources[source_name] / "nested-prediction-lock"
    with pytest.raises(ValueError, match="outside"):
        write_successor_prediction_lock_package(
            prediction_run,
            destination,
            registration_package=protocol_fixture.registration_package,
            source_campaign=protocol_fixture.source_campaign,
            fit_package=protocol_fixture.fit_package,
            adapter_package=protocol_fixture.adapter_package,
        )
    assert not destination.exists()


def test_writer_refuses_overwrite(
    protocol_fixture: ProtocolFixture,
    prediction_run: SuccessorPredictionLockRun,
    prediction_package: SuccessorPredictionLockPackageVerification,
) -> None:
    with pytest.raises(FileExistsError, match="overwrite"):
        write_successor_prediction_lock_package(
            prediction_run,
            prediction_package.package_dir,
            registration_package=protocol_fixture.registration_package,
            source_campaign=protocol_fixture.source_campaign,
            fit_package=protocol_fixture.fit_package,
            adapter_package=protocol_fixture.adapter_package,
        )


def test_publication_race_never_replaces_a_competing_destination(
    protocol_fixture: ProtocolFixture,
    prediction_run: SuccessorPredictionLockRun,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "raced-lock"
    original = prediction_module._rename_noreplace

    def inject(source: Path, selected_destination: Path) -> None:
        assert selected_destination == destination
        destination.mkdir()
        (destination / "competing-owner.txt").write_text("survive", encoding="utf-8")
        original(source, selected_destination)

    monkeypatch.setattr(prediction_module, "_rename_noreplace", inject)
    with pytest.raises(FileExistsError, match="overwrite"):
        write_successor_prediction_lock_package(
            prediction_run,
            destination,
            registration_package=protocol_fixture.registration_package,
            source_campaign=protocol_fixture.source_campaign,
            fit_package=protocol_fixture.fit_package,
            adapter_package=protocol_fixture.adapter_package,
        )
    assert {path.name for path in destination.iterdir()} == {"competing-owner.txt"}
    assert (destination / "competing-owner.txt").read_text(encoding="utf-8") == "survive"


def test_completed_stage3_frozen_files_remain_unchanged() -> None:
    manifest = _read_json(ROOT / "manifests" / "stage3_preexecution_manifest.json")
    frozen = cast(dict[str, str], manifest["files"])
    assert len(frozen) == 151
    mismatches = []
    for relative_path, expected in frozen.items():
        path = ROOT / relative_path
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if actual != expected:
            mismatches.append(relative_path)
    assert mismatches == []
