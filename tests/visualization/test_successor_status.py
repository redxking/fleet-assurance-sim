from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import fleet_sim.visualization.successor_status as status_module
from fleet_sim.empirical.calibration_gate import IntervalEstimate
from fleet_sim.empirical.resource_adapter import SIMULATOR_LIMITATIONS
from fleet_sim.visualization.successor_status import (
    assemble_successor_status,
    build_successor_status,
    load_successor_status,
    write_successor_status_assets,
)

DIGESTS = tuple(character * 64 for character in "abcdef")


class _Criterion:
    def __init__(
        self,
        criterion_id: str,
        state: str,
        *,
        observed: float | None,
        operator: str,
        threshold: float | None,
        reason: str,
    ) -> None:
        self.criterion_id = criterion_id
        self.state = state
        self.observed = observed
        self.operator = operator
        self.threshold = threshold
        self.reason = reason

    def to_dict(self) -> dict[str, object]:
        return {
            "criterion_id": self.criterion_id,
            "state": self.state,
            "observed": self.observed,
            "operator": self.operator,
            "threshold": self.threshold,
            "reason": self.reason,
        }


class _Spec:
    def __init__(self, resource_type: str) -> None:
        self.resource_type = SimpleNamespace(value=resource_type)
        self._resource_type = resource_type

    def to_dict(self) -> dict[str, object]:
        return {
            "resource_id": f"resource-{self._resource_type}",
            "resource_type": self._resource_type,
            "arrival_process": "poisson",
            "admission_work_units": 2.0,
            "background_work_per_agent_s": 0.1,
            "capacity_units_per_second": 250.0,
            "service_time_distribution": "deterministic",
            "service_time_mean_ms": 4.0,
            "max_wait_s": 0.5,
            "overload_behavior": "queue",
            "shedding_threshold": 1.0,
            "recovery_capacity_multiplier": 1.1,
            "measurement_provenance": "must-not-enter-public-projection",
            "parameter_class": "inferred",
        }


def _resource(resource_type: str, state: str) -> SimpleNamespace:
    interval = IntervalEstimate(lower=0.8, point=1.0, upper=1.3)
    intervals = {name: interval for name in status_module.INTERVAL_FIELDS}
    return SimpleNamespace(
        resource_id=f"resource-{resource_type}",
        resource_type=resource_type,
        gate_status=state,
        blocking_reasons=() if state == "passed" else (f"{resource_type} gate blocked",),
        observation_count=24,
        time_block_count=24,
        fleet_size_min=100,
        fleet_size_max=1000,
        admission_rate_min_per_s=0.0,
        admission_rate_max_per_s=100.0,
        scaled_design_rank=2,
        scaled_design_condition_number=2.5,
        weighted_normalized_rmse=0.03 if state == "passed" else None,
        absolute_weighted_relative_bias=0.01 if state == "passed" else None,
        weighted_r_squared=0.98 if state == "passed" else None,
        bootstrap_success_fraction=1.0 if state == "passed" else 0.0,
        parameter_class="inferred",
        **intervals,
    )


def _verified_chain() -> tuple[Any, Any, Any]:
    campaign = SimpleNamespace(
        dataset_id="dataset-public-commitment",
        evidence_scope="measured_input_unreviewed",
        external_validation=False,
        scientific_use_authorized=False,
        evidence_manifest_sha256=DIGESTS[0],
        externally_digest_bound=True,
        evidence_manifest={
            "intake_status": "accepted_for_engineering_review",
            "partitions": {
                "calibration": {
                    "content_sha256": DIGESTS[1],
                    "row_count": 240,
                    "time_block_count": 24,
                },
                "heldout": {
                    "content_sha256": DIGESTS[2],
                    "row_count": 80,
                    "time_block_count": 8,
                },
            },
        },
        campaign_manifest={
            "campaign_id": "secret-campaign-name",
            "site_alias": "site-that-must-not-appear",
            "system_alias": "system-that-must-not-appear",
            "collection_start": "2026-01-01T00:00:00Z",
            "collection_end": "2026-01-02T00:00:00Z",
            "source_type": "measured",
            "authority": {
                "data_classification": "public",
                "data_rights_confirmed": True,
                "authorization_reference": "private-reference",
            },
            "instrumentation": {
                "quality_reviewed": True,
                "environment_description": "/Users/private/site",
            },
        },
    )
    resources = (
        _resource("authorization_policy_evaluation", "passed"),
        _resource("identity_proof_validation", "failed"),
        _resource("credential_validation", "not_evaluable"),
    )
    fit = SimpleNamespace(
        calibration_fit_id="fit-public-id",
        model_id="duration-weighted-nonnegative-arrival-rate-v1",
        gate_status="failed",
        blocking_reasons=("identity_proof_validation gate blocked",),
        input_partition="calibration",
        source_package_heldout_verified=True,
        heldout_used_for_fit=False,
        calibration_content_sha256=DIGESTS[1],
        policy=SimpleNamespace(
            policy_id="secret-site-fit-policy-v1",
            study_mode="successor_transfer",
        ),
        policy_sha256=DIGESTS[3],
        interface_verification_ready=False,
        eligible_for_adapter=False,
        runner_authorized=False,
        scientific_use_authorized=False,
        external_validation=False,
        global_criteria=(
            _Criterion(
                "calibration_time_blocks",
                "passed",
                observed=24.0,
                operator=">=",
                threshold=20.0,
                reason="Calibration time-block support passed.",
            ),
            _Criterion(
                "joint_target_domain_hull_distance",
                "failed",
                observed=0.18,
                operator="<=",
                threshold=1e-9,
                reason="joint_target_domain_requires_extrapolation",
            ),
        ),
        resources=resources,
    )
    fit_package = SimpleNamespace(
        fit=fit,
        fit_evidence_manifest_sha256=DIGESTS[4],
        externally_digest_bound=True,
    )
    bundle = SimpleNamespace(
        adapter_bundle_id="adapter-public-id",
        adapter_mode="interface_verification",
        calibration_fit_id="fit-public-id",
        adapter_policy_id="private-program-adapter-policy-v1",
        adapter_policy_sha256=DIGESTS[5],
        simulator_semantics_sha256=DIGESTS[0],
        specification_sha256=DIGESTS[1],
        fit_evidence_manifest_sha256=DIGESTS[4],
        no_fallback=True,
        source_package_heldout_verified=True,
        heldout_used_for_adapter=False,
        external_validation=False,
        scientific_use_authorized=False,
        runner_authorized=False,
        scientific_use="engineering_simulation_only",
        simulator_limitations=SIMULATOR_LIMITATIONS,
        field_provenance=(
            SimpleNamespace(field_name="arrival_count_mode", evidence_class="configured"),
            SimpleNamespace(field_name="capacity_units_per_second", evidence_class="fitted"),
        ),
        resources=(_Spec("authorization_policy_evaluation"),),
    )
    adapter_package = SimpleNamespace(
        bundle=bundle,
        adapter_manifest_sha256=DIGESTS[2],
        externally_digest_bound=True,
    )
    return campaign, fit_package, adapter_package


def test_projection_is_data_minimized_and_surfaces_tri_state_fit() -> None:
    campaign, fit, _ = _verified_chain()
    result = assemble_successor_status(
        cast(Any, campaign),
        fit=cast(Any, fit),
    ).payload

    encoded = json.dumps(result, sort_keys=True)
    assert "site-that-must-not-appear" not in encoded
    assert "system-that-must-not-appear" not in encoded
    assert "secret-campaign-name" not in encoded
    assert "/Users/private/site" not in encoded
    assert "measurement_provenance" not in encoded
    assert "resource-authorization_policy_evaluation" not in encoded
    assert "secret-site-fit-policy-v1" not in encoded
    assert "policy_id" not in result["fit"]  # type: ignore[operator]
    assert result["fit"]["resource_status_counts"] == {  # type: ignore[index]
        "passed": 1,
        "failed": 1,
        "not_evaluable": 1,
    }
    states = {item["stage"]: item["state"] for item in result["lifecycle"]}
    assert states["fit"] == "failed"
    assert states["adapter"] == "blocked"
    assert states["registration"] == "not_authorized"
    assert states["evaluation"] == "not_authorized"
    assert result["assurance_boundary"]["runner_authorized"] is False
    assert result["assurance_boundary"]["scientific_use_authorized"] is False
    assert result["assurance_boundary"]["external_validation"] is False
    assert result["fit"]["source_package_heldout_verified"] is True  # type: ignore[index]
    assert result["fit"]["heldout_used_for_fit"] is False  # type: ignore[index]
    criteria = {  # type: ignore[union-attr]
        item["criterion_id"]: item
        for item in result["fit"]["global_criteria"]  # type: ignore[index]
    }
    assert criteria["joint_target_domain_hull_distance"] == {
        "criterion_id": "joint_target_domain_hull_distance",
        "state": "failed",
        "observed": 0.18,
        "operator": "<=",
        "threshold": 1e-9,
        "reason": "joint_target_domain_requires_extrapolation",
    }


def test_adapter_projection_surfaces_policy_semantics_and_limitations(tmp_path: Path) -> None:
    campaign, fit, adapter = _verified_chain()
    fit.fit.gate_status = "passed"
    fit.fit.blocking_reasons = ()
    status_bundle = assemble_successor_status(
        cast(Any, campaign),
        fit=cast(Any, fit),
        adapter=cast(Any, adapter),
    )
    result = status_bundle.payload

    assert result["adapter"]["no_fallback"] is True  # type: ignore[index]
    assert "adapter_policy_id" not in result["adapter"]  # type: ignore[operator]
    assert "private-program-adapter-policy-v1" not in json.dumps(result, sort_keys=True)
    assert result["adapter"]["source_package_heldout_verified"] is True  # type: ignore[index]
    assert result["adapter"]["heldout_used_for_adapter"] is False  # type: ignore[index]
    assert result["adapter"]["resources"][0]["arrival_process"] == "poisson"  # type: ignore[index]
    assert result["adapter"]["resources"][0]["overload_behavior"] == "queue"  # type: ignore[index]
    assert "resource_id" not in result["adapter"]["resources"][0]  # type: ignore[index]
    assert result["adapter"]["semantic_field_evidence_classes"] == {  # type: ignore[index]
        "arrival_count_mode": ["configured"],
        "capacity_units_per_second": ["fitted"],
    }
    assert result["adapter"]["simulator_limitations"] == list(SIMULATOR_LIMITATIONS)  # type: ignore[index]

    html_path, _ = write_successor_status_assets(
        status_bundle,
        tmp_path / "public",
    )
    html = html_path.read_text(encoding="utf-8")
    assert "titleLabel(resource.resource_type)" in html
    assert "titleLabel(item)" in html
    for limitation in SIMULATOR_LIMITATIONS:
        assert limitation in html


def test_adapter_requires_bound_matching_fit() -> None:
    campaign, fit, adapter = _verified_chain()
    with pytest.raises(ValueError, match="source fit"):
        assemble_successor_status(cast(Any, campaign), adapter=cast(Any, adapter))
    adapter.bundle.calibration_fit_id = "another-fit"
    with pytest.raises(ValueError, match="different calibration fit"):
        assemble_successor_status(
            cast(Any, campaign),
            fit=cast(Any, fit),
            adapter=cast(Any, adapter),
        )


def test_load_verifies_the_complete_digest_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    campaign, fit, adapter = _verified_chain()
    calls: list[tuple[str, dict[str, object]]] = []

    def campaign_verify(path: object, **kwargs: object) -> Any:
        calls.append(("campaign", kwargs))
        return campaign

    def fit_verify(path: object, **kwargs: object) -> Any:
        calls.append(("fit", kwargs))
        return fit

    def adapter_verify(path: object, **kwargs: object) -> Any:
        calls.append(("adapter", kwargs))
        return adapter

    monkeypatch.setattr(status_module, "verify_empirical_campaign_package", campaign_verify)
    monkeypatch.setattr(status_module, "verify_empirical_calibration_package", fit_verify)
    monkeypatch.setattr(status_module, "verify_adapted_resource_bundle", adapter_verify)
    fit.fit.gate_status = "passed"
    fit.fit.blocking_reasons = ()

    result = load_successor_status(
        "campaign",
        expected_campaign_evidence_manifest_sha256=DIGESTS[0],
        fit_package="fit",
        expected_fit_evidence_manifest_sha256=DIGESTS[4],
        adapter_package="adapter",
        expected_adapter_policy_sha256=DIGESTS[5],
        expected_adapter_manifest_sha256=DIGESTS[2],
    )

    assert [name for name, _ in calls] == ["campaign", "fit", "adapter"]
    assert calls[1][1]["expected_fit_evidence_manifest_sha256"] == DIGESTS[4]
    assert calls[2][1]["expected_adapter_manifest_sha256"] == DIGESTS[2]
    assert result.payload["adapter"] is not None


def test_load_rejects_partial_optional_evidence_sets() -> None:
    with pytest.raises(ValueError, match="fit package"):
        load_successor_status(
            "campaign",
            expected_campaign_evidence_manifest_sha256=DIGESTS[0],
            fit_package="fit",
        )
    with pytest.raises(ValueError, match="closed set"):
        load_successor_status(
            "campaign",
            expected_campaign_evidence_manifest_sha256=DIGESTS[0],
            adapter_package="adapter",
            expected_adapter_policy_sha256=DIGESTS[1],
        )


def test_writer_builds_strict_offline_accessible_assets(tmp_path: Path) -> None:
    campaign, fit, _ = _verified_chain()
    bundle = assemble_successor_status(cast(Any, campaign), fit=cast(Any, fit))

    html_path, json_path = write_successor_status_assets(bundle, tmp_path / "public")
    html = html_path.read_text(encoding="utf-8")
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert html.startswith("<!doctype html>")
    assert '<html lang="en">' in html
    assert "Content-Security-Policy" in html
    assert "connect-src 'none'" in html
    assert "<script src=" not in html
    assert "fetch(" not in html
    assert "XMLHttpRequest" not in html
    assert "WebSocket" not in html
    assert "https://" not in html
    assert 'aria-labelledby="life-title"' in html
    assert 'aria-label="Generated assurance resource semantics;' in html
    assert 'tabindex="0"' in html
    assert "min-height:2.75rem" in html
    assert "prospective evaluation not authorized" in html
    assert '<div id="globalGates" class="gate-grid">' in html
    assert "fit.global_criteria.forEach" in html
    assert "joint_target_domain_hull_distance" in html
    assert '"state":"failed"' in html
    for field in (
        "resource.time_block_count",
        "resource.scaled_design_rank",
        "resource.scaled_design_condition_number",
        "resource.absolute_weighted_relative_bias",
        "resource.weighted_r_squared",
    ):
        assert field in html
    for label in (
        "Time blocks",
        "Scaled design rank",
        "Scaled condition number",
        "Absolute weighted relative bias",
        "Weighted R²",
    ):
        assert label in html
    assert "Resource fit diagnostics" in html
    assert payload == bundle.payload
    assert payload["projection_sha256"]
    assert "site-that-must-not-appear" not in json_path.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_successor_status_assets(bundle, tmp_path / "public")


@pytest.mark.parametrize("overwrite", (False, True))
def test_writer_accepts_an_existing_empty_destination(
    tmp_path: Path,
    overwrite: bool,
) -> None:
    campaign, fit, _ = _verified_chain()
    bundle = assemble_successor_status(cast(Any, campaign), fit=cast(Any, fit))
    destination = tmp_path / "public"
    destination.mkdir()

    write_successor_status_assets(bundle, destination, overwrite=overwrite)

    assert {path.name for path in destination.iterdir()} == {
        "index.html",
        "successor-status.json",
    }
    assert all(path.is_file() and not path.is_symlink() for path in destination.iterdir())


def test_writer_replaces_only_an_exact_owned_pair_with_overwrite(tmp_path: Path) -> None:
    campaign, fit, _ = _verified_chain()
    bundle = assemble_successor_status(cast(Any, campaign), fit=cast(Any, fit))
    destination = tmp_path / "public"
    destination.mkdir()
    (destination / "index.html").write_text("stale html", encoding="utf-8")
    (destination / "successor-status.json").write_text("stale json", encoding="utf-8")

    html_path, json_path = write_successor_status_assets(
        bundle,
        destination,
        overwrite=True,
    )

    assert html_path.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert json.loads(json_path.read_text(encoding="utf-8")) == bundle.payload
    assert {path.name for path in destination.iterdir()} == {
        "index.html",
        "successor-status.json",
    }


@pytest.mark.parametrize(
    "layout",
    ("single_owned_file", "extra_file", "extra_directory", "owned_name_directory"),
)
@pytest.mark.parametrize("overwrite", (False, True))
def test_writer_rejects_non_closed_destinations(
    tmp_path: Path,
    layout: str,
    overwrite: bool,
) -> None:
    campaign, fit, _ = _verified_chain()
    bundle = assemble_successor_status(cast(Any, campaign), fit=cast(Any, fit))
    destination = tmp_path / f"{layout}-{overwrite}"
    destination.mkdir()
    index = destination / "index.html"
    projection = destination / "successor-status.json"
    if layout == "owned_name_directory":
        index.mkdir()
        (index / "private.txt").write_text("retain", encoding="utf-8")
    else:
        index.write_text("retain-index", encoding="utf-8")
    if layout != "single_owned_file":
        projection.write_text("retain-projection", encoding="utf-8")
    if layout == "extra_file":
        (destination / "notes.txt").write_text("retain-extra", encoding="utf-8")
    if layout == "extra_directory":
        extra = destination / "private"
        extra.mkdir()
        (extra / "rows.csv").write_text("retain-extra", encoding="utf-8")

    with pytest.raises(ValueError, match="exactly|regular"):
        write_successor_status_assets(bundle, destination, overwrite=overwrite)

    if index.is_dir():
        assert (index / "private.txt").read_text(encoding="utf-8") == "retain"
    else:
        assert index.read_text(encoding="utf-8") == "retain-index"
    if projection.exists():
        assert projection.read_text(encoding="utf-8") == "retain-projection"
    if layout == "extra_file":
        assert (destination / "notes.txt").read_text(encoding="utf-8") == "retain-extra"
    if layout == "extra_directory":
        assert (destination / "private" / "rows.csv").read_text(encoding="utf-8") == (
            "retain-extra"
        )


@pytest.mark.parametrize("overwrite", (False, True))
def test_writer_rejects_destination_and_child_symlinks(
    tmp_path: Path,
    overwrite: bool,
) -> None:
    campaign, fit, _ = _verified_chain()
    bundle = assemble_successor_status(cast(Any, campaign), fit=cast(Any, fit))
    external = tmp_path / "external"
    external.mkdir()
    destination_link = tmp_path / f"linked-{overwrite}"
    destination_link.symlink_to(external, target_is_directory=True)

    with pytest.raises(ValueError, match="destination must not be a symlink"):
        write_successor_status_assets(bundle, destination_link, overwrite=overwrite)
    assert not tuple(external.iterdir())

    destination = tmp_path / f"child-link-{overwrite}"
    destination.mkdir()
    dangling_target = tmp_path / "missing-private-output"
    (destination / "index.html").symlink_to(dangling_target)
    (destination / "successor-status.json").write_text("retain", encoding="utf-8")

    with pytest.raises(ValueError, match="regular, non-symlink"):
        write_successor_status_assets(bundle, destination, overwrite=overwrite)
    assert (destination / "index.html").is_symlink()
    assert not dangling_target.exists()
    assert (destination / "successor-status.json").read_text(encoding="utf-8") == "retain"


def test_private_cleanup_never_follows_a_replaced_directory_symlink(tmp_path: Path) -> None:
    external = tmp_path / "external"
    external.mkdir()
    private_asset = external / "index.html"
    private_asset.write_text("do not remove", encoding="utf-8")
    staging_link = tmp_path / ".public.staging.raced"
    staging_link.symlink_to(external, target_is_directory=True)

    with pytest.raises(RuntimeError, match="refusing to traverse"):
        status_module._remove_owned_status_directory(staging_link)

    assert staging_link.is_symlink()
    assert private_asset.read_text(encoding="utf-8") == "do not remove"


@pytest.mark.parametrize("preexisting_state", ("absent", "empty", "complete"))
def test_writer_leaves_no_partial_assets_when_staging_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    preexisting_state: str,
) -> None:
    campaign, fit, _ = _verified_chain()
    bundle = assemble_successor_status(cast(Any, campaign), fit=cast(Any, fit))
    destination = tmp_path / "public"
    index = destination / "index.html"
    projection = destination / "successor-status.json"
    if preexisting_state != "absent":
        destination.mkdir()
    if preexisting_state == "complete":
        index.write_text("previous html", encoding="utf-8")
        projection.write_text("previous json", encoding="utf-8")
    original_atomic_write = status_module._atomic_write
    calls = 0

    def interrupted_write(path: Path, content: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected staging failure")
        original_atomic_write(path, content)

    monkeypatch.setattr(status_module, "_atomic_write", interrupted_write)

    with pytest.raises(OSError, match="injected staging failure"):
        write_successor_status_assets(bundle, destination, overwrite=True)

    if preexisting_state == "absent":
        assert not destination.exists()
        assert not tuple(tmp_path.iterdir())
    elif preexisting_state == "empty":
        assert destination.is_dir()
        assert not tuple(destination.iterdir())
        assert {path.name for path in tmp_path.iterdir()} == {"public"}
    else:
        assert index.read_text(encoding="utf-8") == "previous html"
        assert projection.read_text(encoding="utf-8") == "previous json"
        assert {path.name for path in tmp_path.iterdir()} == {"public"}


def test_writer_restores_the_previous_pair_when_commit_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign, fit, _ = _verified_chain()
    bundle = assemble_successor_status(cast(Any, campaign), fit=cast(Any, fit))
    destination = tmp_path / "public"
    destination.mkdir()
    index = destination / "index.html"
    projection = destination / "successor-status.json"
    index.write_text("previous html", encoding="utf-8")
    projection.write_text("previous json", encoding="utf-8")
    original_replace = status_module.os.replace
    injected = False

    def interrupted_replace(source: str | Path, target: str | Path) -> None:
        nonlocal injected
        source_path = Path(source)
        target_path = Path(target)
        if (
            not injected
            and source_path.is_dir()
            and ".staging." in source_path.name
            and target_path == destination
        ):
            injected = True
            raise OSError("injected commit failure")
        original_replace(source, target)

    monkeypatch.setattr(status_module.os, "replace", interrupted_replace)

    with pytest.raises(OSError, match="injected commit failure"):
        write_successor_status_assets(bundle, destination, overwrite=True)

    assert injected is True
    assert index.read_text(encoding="utf-8") == "previous html"
    assert projection.read_text(encoding="utf-8") == "previous json"
    assert {path.name for path in tmp_path.iterdir()} == {"public"}


@pytest.mark.parametrize(
    "embedded_path",
    (
        "retained at /private/tmp/campaign-package",
        "retained at /tmp/calibration-fit",
        "retained at /var/folders/task/evidence",
        "source=/tmp/calibration-fit",
        "see(/var/folders/task/evidence)",
        r"retained at C:\Users\analyst\evidence",
        "retained at C:/Users/analyst/evidence",
        r"retained at \\research-host\assurance-share\evidence",
        "file:///tmp/evidence.json",
    ),
)
def test_writer_rejects_embedded_local_paths(
    tmp_path: Path,
    embedded_path: str,
) -> None:
    campaign, fit, _ = _verified_chain()
    bundle = assemble_successor_status(cast(Any, campaign), fit=cast(Any, fit))
    bundle.payload["blocking_conditions"].append(embedded_path)

    with pytest.raises(ValueError, match="local path string"):
        write_successor_status_assets(bundle, tmp_path / "public")


@pytest.mark.parametrize(
    ("section", "forbidden_key"),
    (("fit", "policy_id"), ("adapter", "adapter_policy_id")),
)
def test_writer_rejects_human_supplied_policy_identifiers(
    tmp_path: Path,
    section: str,
    forbidden_key: str,
) -> None:
    campaign, fit, adapter = _verified_chain()
    fit.fit.gate_status = "passed"
    fit.fit.blocking_reasons = ()
    bundle = assemble_successor_status(
        cast(Any, campaign),
        fit=cast(Any, fit),
        adapter=cast(Any, adapter),
    )
    projected_section = cast(dict[str, object], bundle.payload[section])
    projected_section[forbidden_key] = "secret-site-policy"

    with pytest.raises(ValueError, match=f"forbidden field: {forbidden_key}"):
        write_successor_status_assets(bundle, tmp_path / "public")


def test_build_refuses_to_write_inside_evidence_package(tmp_path: Path) -> None:
    campaign = tmp_path / "campaign-package"
    campaign.mkdir()
    with pytest.raises(ValueError, match="outside immutable evidence"):
        build_successor_status(
            campaign,
            campaign / "ui",
            expected_campaign_evidence_manifest_sha256=DIGESTS[0],
        )
