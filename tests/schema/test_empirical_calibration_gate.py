from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

import fleet_sim.empirical.calibration_gate as calibration_module
from fleet_sim.control_plane.resource_network import ResourceType
from fleet_sim.empirical.assurance_campaign import (
    read_empirical_campaign,
    write_empirical_campaign_package,
)
from fleet_sim.empirical.calibration_gate import (
    FIT_PACKAGE_FILES,
    FitGatePolicy,
    ResourceFitResult,
    canonical_calibration_partition_sha256,
    fit_empirical_calibration,
    prepare_calibration_fit_input,
    verify_empirical_calibration_package,
    write_empirical_calibration_package,
)

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_TEMPLATE = ROOT / "examples" / "empirical_assurance_campaign_template.json"
CAMPAIGN_SCHEMA = ROOT / "schemas" / "empirical_assurance_campaign.schema.json"
MEASUREMENT_SCHEMA = ROOT / "schemas" / "empirical_assurance_measurements.schema.json"


def _policy(**overrides: object) -> FitGatePolicy:
    values: dict[str, object] = {
        "policy_id": "test-successor-fit-gate-v1",
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
        "root_seed": 731_2026,
    }
    values.update(overrides)
    return FitGatePolicy.from_mapping(values)


def _manifest(
    campaign_id: str,
    *,
    source_type: str = "synthetic",
) -> dict[str, object]:
    manifest = json.loads(CAMPAIGN_TEMPLATE.read_text(encoding="utf-8"))
    manifest["campaign_id"] = campaign_id
    manifest["source_type"] = source_type
    manifest["collection_start"] = "2026-08-20T11:59:59Z"
    manifest["collection_end"] = "2026-08-20T12:02:00Z"
    if source_type != "synthetic":
        authority = manifest["authority"]
        instrumentation = manifest["instrumentation"]
        assert isinstance(authority, dict)
        assert isinstance(instrumentation, dict)
        authority["collection_authorized"] = True
        authority["authorization_reference"] = "authorized-public-test-campaign"
        authority["data_classification"] = "public"
        instrumentation["quality_reviewed"] = True
        instrumentation["quality_review_reference"] = "reviewed-public-test-instrumentation"
    return manifest


def _measurement_frame(
    campaign_id: str,
    *,
    rank_deficient: bool = False,
    noisy: bool = False,
    heldout_delta: int = 0,
) -> pd.DataFrame:
    base_time = pd.Timestamp("2026-08-20T12:00:00Z")
    rows: list[dict[str, object]] = []
    partitions = (("calibration", 60), ("heldout", 12))
    for partition, block_count in partitions:
        offset = 0 if partition == "calibration" else 61
        for block_index in range(block_count):
            if rank_deficient and partition == "calibration":
                if block_index < 10:
                    fleet_size = 0
                    admitted = 0
                else:
                    fleet_size = 100 * (1 + block_index % 5)
                    admitted = fleet_size // 10
            else:
                fleet_size = 100 * (1 + block_index % 5)
                admitted = (0, 5, 10, 15, 20)[(block_index // 5) % 5]
            timestamp = base_time + pd.Timedelta(seconds=offset + block_index)
            time_block_id = f"{partition}-window-{block_index:03d}"
            for resource_index, resource_type in enumerate(ResourceType):
                background = (resource_index + 1) / 100.0
                admission_work = float(resource_index + 2)
                arrival_count = int(background * fleet_size + admission_work * admitted)
                if noisy and partition == "calibration" and block_index % 2:
                    arrival_count += 5_000
                if partition == "heldout" and resource_index == 0 and block_index == 0:
                    arrival_count += heldout_delta
                rows.append(
                    {
                        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                        "resource_id": resource_type.value,
                        "resource_type": resource_type.value,
                        "fleet_size": fleet_size,
                        "agents_admitted": admitted,
                        "arrival_count": arrival_count,
                        "service_count": arrival_count,
                        "queue_depth": 0.0,
                        "service_time_ms": 10.0 + resource_index + 0.01 * (block_index % 5),
                        "wait_time_ms": 1.0 + resource_index / 10.0,
                        "capacity_units_per_second": 1_000.0 + 100.0 * resource_index,
                        "deadline_ms": 1_000.0 + 100.0 * resource_index,
                        "dropped_work": 0.0,
                        "deferred_work": 0.0,
                        "error_count": 0,
                        "source_type": "synthetic",
                        "measurement_provenance": "generated calibration-gate fixture",
                        "window_duration_ms": 1_000.0,
                        "campaign_id": campaign_id,
                        "time_block_id": time_block_id,
                        "partition": partition,
                        "is_censored": False,
                        "missing_fraction": 0.0,
                    }
                )
    return pd.DataFrame(rows)


def _campaign_package(
    tmp_path: Path,
    *,
    campaign_id: str = "fit-gate-test-campaign",
    frame: pd.DataFrame | None = None,
    manifest_source_type: str = "synthetic",
) -> tuple[Path, str]:
    source_dir = tmp_path / "sources"
    source_dir.mkdir(parents=True)
    measurement_path = source_dir / "measurements.csv"
    campaign_path = source_dir / "campaign.json"
    selected = _measurement_frame(campaign_id) if frame is None else frame
    selected.to_csv(measurement_path, index=False)
    campaign_path.write_text(
        json.dumps(_manifest(campaign_id, source_type=manifest_source_type), indent=2),
        encoding="utf-8",
    )
    campaign = read_empirical_campaign(
        measurement_path,
        campaign_path,
        campaign_schema_path=CAMPAIGN_SCHEMA,
        measurement_schema_path=MEASUREMENT_SCHEMA,
    )
    package = write_empirical_campaign_package(campaign, tmp_path / "campaign-package")
    evidence_digest = hashlib.sha256((package / "evidence_manifest.json").read_bytes()).hexdigest()
    return package, evidence_digest


def _fit_input(
    tmp_path: Path,
    *,
    campaign_id: str = "fit-gate-test-campaign",
    frame: pd.DataFrame | None = None,
    manifest_source_type: str = "synthetic",
):
    package, evidence_digest = _campaign_package(
        tmp_path,
        campaign_id=campaign_id,
        frame=frame,
        manifest_source_type=manifest_source_type,
    )
    fit_input = prepare_calibration_fit_input(
        package,
        expected_evidence_manifest_sha256=evidence_digest,
    )
    return package, evidence_digest, fit_input


def _refresh_fit_artifact_record(package: Path, artifact_name: str) -> str:
    evidence_path = package / "fit_evidence_manifest.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    artifacts = evidence["artifacts"]
    assert isinstance(artifacts, list)
    record = next(item for item in artifacts if item["path"] == artifact_name)
    artifact_bytes = (package / artifact_name).read_bytes()
    record["bytes"] = len(artifact_bytes)
    record["sha256"] = hashlib.sha256(artifact_bytes).hexdigest()
    evidence.pop("self_integrity_sha256")
    canonical = json.dumps(
        evidence,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    evidence["self_integrity_sha256"] = hashlib.sha256(canonical).hexdigest()
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return hashlib.sha256(evidence_path.read_bytes()).hexdigest()


def _criterion_state(resource: ResourceFitResult, criterion_id: str) -> str:
    return next(item.state for item in resource.criteria if item.criterion_id == criterion_id)


def test_sixty_block_ten_resource_fit_recovers_declared_coefficients(
    tmp_path: Path,
) -> None:
    _, _, fit_input = _fit_input(tmp_path)
    run = fit_empirical_calibration(fit_input, _policy())

    assert run.fit.gate_status == "passed"
    assert run.fit.interface_verification_ready is True
    assert run.fit.eligible_for_adapter is False
    assert len(run.fit.resources) == len(ResourceType)
    assert run.fit.source_package_heldout_verified is True
    assert run.fit.heldout_used_for_fit is False
    for resource_index, resource in enumerate(run.fit.resources):
        assert resource.gate_status == "passed"
        assert resource.observation_count == 60
        assert resource.time_block_count == 60
        assert resource.scaled_design_rank == 2
        assert resource.background_work_per_agent_s is not None
        assert resource.admission_work_units_per_agent is not None
        assert resource.background_work_per_agent_s.point == pytest.approx(
            (resource_index + 1) / 100.0,
            rel=1e-10,
            abs=1e-10,
        )
        assert resource.admission_work_units_per_agent.point == pytest.approx(
            resource_index + 2,
            rel=1e-10,
            abs=1e-10,
        )
        assert resource.service_time_window_mean_ms is not None
        assert resource.service_time_window_mean_ms.lower > 0.0
        assert resource.bootstrap_succeeded >= 80


def test_joint_bootstrap_is_deterministic_row_order_stable_and_shared(
    tmp_path: Path,
) -> None:
    _, _, fit_input = _fit_input(tmp_path)
    policy = _policy()
    original = fit_empirical_calibration(fit_input, policy)
    reversed_input = replace(
        fit_input,
        _calibration=fit_input.calibration.iloc[::-1].reset_index(drop=True),
    )
    reordered = fit_empirical_calibration(reversed_input, policy)

    assert original.fit.to_dict() == reordered.fit.to_dict()
    pd.testing.assert_frame_equal(
        original.bootstrap_draws,
        reordered.bootstrap_draws,
        check_exact=True,
    )
    draws = original.bootstrap_draws
    assert not draws.empty
    per_replication = draws.groupby("bootstrap_replication")
    assert set(per_replication.size()) == {len(ResourceType)}
    assert set(per_replication["sampled_block_sequence_sha256"].nunique()) == {1}


def test_heldout_changes_do_not_change_fit_identity_results_or_draws(
    tmp_path: Path,
) -> None:
    campaign_id = "heldout-independence-campaign"
    original_frame = _measurement_frame(campaign_id)
    changed_frame = _measurement_frame(campaign_id, heldout_delta=999)
    _, _, original_input = _fit_input(
        tmp_path / "original",
        campaign_id=campaign_id,
        frame=original_frame,
    )
    _, _, changed_input = _fit_input(
        tmp_path / "changed",
        campaign_id=campaign_id,
        frame=changed_frame,
    )

    assert original_input.calibration_content_sha256 == changed_input.calibration_content_sha256
    assert (
        original_input.heldout_content_commitment_sha256
        != changed_input.heldout_content_commitment_sha256
    )
    original = fit_empirical_calibration(original_input, _policy())
    changed = fit_empirical_calibration(changed_input, _policy())
    assert original.fit.calibration_fit_id == changed.fit.calibration_fit_id
    assert original.fit.to_dict() == changed.fit.to_dict()
    pd.testing.assert_frame_equal(
        original.bootstrap_draws,
        changed.bootstrap_draws,
        check_exact=True,
    )


def test_heldout_source_classification_does_not_change_fit_identity(
    tmp_path: Path,
) -> None:
    campaign_id = "heldout-source-independence-campaign"
    measured_frame = _measurement_frame(campaign_id)
    measured_frame["source_type"] = "measured"
    mixed_frame = measured_frame.copy(deep=True)
    mixed_frame.loc[mixed_frame["partition"] == "heldout", "source_type"] = "replayed"

    _, _, measured_input = _fit_input(
        tmp_path / "measured",
        campaign_id=campaign_id,
        frame=measured_frame,
        manifest_source_type="measured",
    )
    _, _, mixed_input = _fit_input(
        tmp_path / "mixed",
        campaign_id=campaign_id,
        frame=mixed_frame,
        manifest_source_type="mixed",
    )

    assert measured_input.calibration_content_sha256 == mixed_input.calibration_content_sha256
    assert measured_input.calibration_context_sha256 == mixed_input.calibration_context_sha256
    assert measured_input.source_evidence_scope == mixed_input.source_evidence_scope
    assert (
        measured_input.heldout_content_commitment_sha256
        != mixed_input.heldout_content_commitment_sha256
    )
    measured = fit_empirical_calibration(measured_input, _policy())
    mixed = fit_empirical_calibration(mixed_input, _policy())
    assert measured.fit.calibration_fit_id == mixed.fit.calibration_fit_id
    assert measured.fit.to_dict() == mixed.fit.to_dict()
    pd.testing.assert_frame_equal(measured.bootstrap_draws, mixed.bootstrap_draws, check_exact=True)


def test_joint_target_domain_requires_convex_hull_support(tmp_path: Path) -> None:
    frame = _measurement_frame("joint-domain-gap-campaign")
    resource_index = {item.value: index for index, item in enumerate(ResourceType)}
    calibration = frame["partition"] == "calibration"
    for row_index in frame.index[calibration]:
        fleet_size = int(frame.at[row_index, "fleet_size"])
        block_index = int(str(frame.at[row_index, "time_block_id"]).rsplit("-", 1)[1])
        admitted = {100: 19, 200: 14, 300: 9, 400: 4, 500: 0}[fleet_size]
        admitted += (block_index // 5) % 2
        index = resource_index[str(frame.at[row_index, "resource_type"])]
        arrivals = int(((index + 1) / 100.0) * fleet_size + (index + 2) * admitted)
        frame.at[row_index, "agents_admitted"] = admitted
        frame.at[row_index, "arrival_count"] = arrivals
        frame.at[row_index, "service_count"] = arrivals
    _, _, fit_input = _fit_input(
        tmp_path,
        campaign_id="joint-domain-gap-campaign",
        frame=frame,
    )
    run = fit_empirical_calibration(fit_input, _policy())
    criterion = next(
        item
        for item in run.fit.global_criteria
        if item.criterion_id == "joint_target_domain_hull_distance"
    )
    assert criterion.state == "failed"
    assert criterion.observed is not None and criterion.observed > 0.0
    assert run.fit.gate_status == "failed"
    assert run.fit.interface_verification_ready is False


def test_completed_service_support_is_required_for_adapter_readiness(
    tmp_path: Path,
) -> None:
    frame = _measurement_frame("zero-service-support-campaign")
    calibration = frame["partition"] == "calibration"
    frame.loc[calibration, "service_time_ms"] = 0.0
    _, _, fit_input = _fit_input(
        tmp_path,
        campaign_id="zero-service-support-campaign",
        frame=frame,
    )
    run = fit_empirical_calibration(fit_input, _policy())
    assert run.fit.gate_status == "failed"
    assert run.fit.interface_verification_ready is False
    for resource in run.fit.resources:
        criterion = next(
            item
            for item in resource.criteria
            if item.criterion_id == "positive_service_time_for_completed_work"
        )
        assert criterion.state == "failed"


def test_policy_and_bootstrap_work_limits_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="bootstrap_replications cannot exceed"):
        _policy(bootstrap_replications=calibration_module.MAX_BOOTSTRAP_REPLICATIONS + 1)
    with pytest.raises(ValueError, match="portable identifier"):
        _policy(policy_id="_not-portable")

    _, _, fit_input = _fit_input(tmp_path)
    monkeypatch.setattr(calibration_module, "MAX_BOOTSTRAP_WORK_UNITS", 1)
    with pytest.raises(ValueError, match="bootstrap work-unit safety limit"):
        fit_empirical_calibration(fit_input, _policy())


def test_fit_writer_refuses_output_inside_source_campaign(tmp_path: Path) -> None:
    campaign, _, fit_input = _fit_input(tmp_path)
    run = fit_empirical_calibration(fit_input, _policy())
    before = {path.name for path in campaign.iterdir()}
    with pytest.raises(ValueError, match="outside the source campaign"):
        write_empirical_calibration_package(
            run,
            fit_input,
            campaign / "nested-fit",
        )
    assert {path.name for path in campaign.iterdir()} == before
    assert not (campaign / "nested-fit").exists()


def test_structural_quality_and_fit_failures_are_fail_closed(tmp_path: Path) -> None:
    _, _, fit_input = _fit_input(tmp_path / "valid")
    incomplete = fit_input.calibration[
        fit_input.calibration["resource_type"] != ResourceType.IDENTITY_ISSUANCE.value
    ].reset_index(drop=True)
    structurally_invalid = replace(
        fit_input,
        _calibration=incomplete,
        calibration_content_sha256=canonical_calibration_partition_sha256(incomplete),
    )
    with pytest.raises(ValueError, match="exactly the ten"):
        fit_empirical_calibration(structurally_invalid, _policy())

    quality_frame = _measurement_frame("quality-blocked-campaign")
    calibration_row = quality_frame.index[quality_frame["partition"] == "calibration"][0]
    quality_frame.at[calibration_row, "is_censored"] = True
    quality_frame.at[calibration_row, "missing_fraction"] = 0.25
    _, _, quality_input = _fit_input(
        tmp_path / "quality",
        campaign_id="quality-blocked-campaign",
        frame=quality_frame,
    )
    quality_run = fit_empirical_calibration(quality_input, _policy())
    assert quality_run.fit.gate_status == "failed"
    assert "censored_calibration_rows_not_supported" in quality_run.fit.blocking_reasons
    assert "missing_calibration_values_not_supported" in quality_run.fit.blocking_reasons
    assert quality_run.bootstrap_draws.empty

    noisy_frame = _measurement_frame("fit-failure-campaign", noisy=True)
    _, _, noisy_input = _fit_input(
        tmp_path / "noisy",
        campaign_id="fit-failure-campaign",
        frame=noisy_frame,
    )
    noisy_run = fit_empirical_calibration(noisy_input, _policy())
    assert noisy_run.fit.gate_status == "failed"
    assert "fit_error_exceeds_policy" in noisy_run.fit.blocking_reasons


def test_rank_deficiency_is_not_evaluable_and_never_promoted(tmp_path: Path) -> None:
    campaign_id = "rank-deficient-campaign"
    frame = _measurement_frame(campaign_id, rank_deficient=True)
    _, _, fit_input = _fit_input(tmp_path, campaign_id=campaign_id, frame=frame)
    run = fit_empirical_calibration(fit_input, _policy())

    assert run.fit.gate_status == "not_evaluable"
    assert run.fit.interface_verification_ready is False
    assert run.fit.eligible_for_adapter is False
    assert run.bootstrap_draws.empty
    assert all(
        _criterion_state(resource, "design_rank") == "not_evaluable"
        for resource in run.fit.resources
    )
    assert "rank_deficient_design" in run.fit.blocking_reasons


def test_fit_package_roundtrip_tamper_no_overwrite_and_false_authority_flags(
    tmp_path: Path,
) -> None:
    campaign_package, source_digest, fit_input = _fit_input(tmp_path / "source")
    run = fit_empirical_calibration(fit_input, _policy())
    fit_package = write_empirical_calibration_package(
        run,
        fit_input,
        tmp_path / "fit-package",
    )
    fit_manifest_digest = hashlib.sha256(
        (fit_package / "fit_evidence_manifest.json").read_bytes()
    ).hexdigest()
    checked = verify_empirical_calibration_package(
        fit_package,
        source_campaign_package=campaign_package,
        expected_source_evidence_manifest_sha256=source_digest,
        expected_fit_evidence_manifest_sha256=fit_manifest_digest,
    )

    assert {path.name for path in fit_package.iterdir()} == FIT_PACKAGE_FILES
    assert checked.externally_digest_bound is True
    assert checked.fit.to_dict() == run.fit.to_dict()
    pd.testing.assert_frame_equal(checked.bootstrap_draws, run.bootstrap_draws)
    assert checked.fit.runner_authorized is False
    assert checked.fit.scientific_use_authorized is False
    assert checked.fit.external_validation is False
    with pytest.raises(FileExistsError, match="overwrite"):
        write_empirical_calibration_package(run, fit_input, fit_package)

    (fit_package / "calibration_fit.json").write_bytes(
        (fit_package / "calibration_fit.json").read_bytes() + b"\n"
    )
    with pytest.raises(ValueError, match="artifact (size|hash) mismatch"):
        verify_empirical_calibration_package(
            fit_package,
            source_campaign_package=campaign_package,
            expected_source_evidence_manifest_sha256=source_digest,
        )

    authority_package = write_empirical_calibration_package(
        run,
        fit_input,
        tmp_path / "false-authority-package",
    )
    evidence_path = authority_package / "fit_evidence_manifest.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["external_validation"] = True
    evidence.pop("self_integrity_sha256")
    canonical = json.dumps(
        evidence,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    evidence["self_integrity_sha256"] = hashlib.sha256(canonical).hexdigest()
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="permitted engineering evidence scope"):
        verify_empirical_calibration_package(
            authority_package,
            source_campaign_package=campaign_package,
            expected_source_evidence_manifest_sha256=source_digest,
        )


def test_fit_verifier_rejects_extra_calibration_columns_after_rehash(
    tmp_path: Path,
) -> None:
    campaign_package, source_digest, fit_input = _fit_input(tmp_path / "source")
    run = fit_empirical_calibration(fit_input, _policy())
    fit_package = write_empirical_calibration_package(run, fit_input, tmp_path / "fit-package")
    calibration_path = fit_package / "calibration_measurements.parquet"
    calibration = pd.read_parquet(calibration_path)
    calibration["unexpected_column"] = "not-part-of-the-closed-contract"
    calibration.to_parquet(calibration_path, index=False)
    fit_digest = _refresh_fit_artifact_record(
        fit_package,
        "calibration_measurements.parquet",
    )

    with pytest.raises(ValueError, match="calibration partition columns differ"):
        verify_empirical_calibration_package(
            fit_package,
            source_campaign_package=campaign_package,
            expected_source_evidence_manifest_sha256=source_digest,
            expected_fit_evidence_manifest_sha256=fit_digest,
        )


@pytest.mark.parametrize("mutation", ("extra", "missing"))
def test_fit_verifier_rejects_malformed_empty_bootstrap_columns_after_rehash(
    tmp_path: Path,
    mutation: str,
) -> None:
    campaign_id = f"empty-bootstrap-{mutation}-campaign"
    frame = _measurement_frame(campaign_id, rank_deficient=True)
    campaign_package, source_digest, fit_input = _fit_input(
        tmp_path / mutation / "source",
        campaign_id=campaign_id,
        frame=frame,
    )
    run = fit_empirical_calibration(fit_input, _policy())
    assert run.bootstrap_draws.empty
    fit_package = write_empirical_calibration_package(
        run,
        fit_input,
        tmp_path / mutation / "fit-package",
    )
    draws_path = fit_package / "bootstrap_draws.parquet"
    draws = pd.read_parquet(draws_path)
    if mutation == "extra":
        draws["unexpected_column"] = pd.Series(dtype="float64")
    else:
        draws = draws.drop(columns=[str(draws.columns[0])])
    draws.to_parquet(draws_path, index=False)
    fit_digest = _refresh_fit_artifact_record(
        fit_package,
        "bootstrap_draws.parquet",
    )

    with pytest.raises(ValueError, match="bootstrap draw columns differ"):
        verify_empirical_calibration_package(
            fit_package,
            source_campaign_package=campaign_package,
            expected_source_evidence_manifest_sha256=source_digest,
            expected_fit_evidence_manifest_sha256=fit_digest,
        )
