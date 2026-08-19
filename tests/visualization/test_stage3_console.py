from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from fleet_sim.visualization.stage3_console import (
    ConsoleLimits,
    Stage3ScenarioConfig,
    build_stage3_console,
    export_stage3_console_json,
    load_stage3_execution,
    run_visual_scenario,
    write_scenario_request,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_execution(root: Path, execution_id: str, *, traces: bool) -> Path:
    execution = root / execution_id
    raw = execution / "raw"
    derived = execution / "derived"
    raw.mkdir(parents=True)
    derived.mkdir()
    evidence = {
        "schema_version": "1.0",
        "protocol": {"protocol_id": "FAS-S3-TEST", "protocol_hash": "abc123"},
        "execution": {
            "execution_id": execution_id,
            "mode": "pilot",
            "completed_utc": "2026-08-19T12:00:00+00:00",
        },
        "evidence_scope": "synthetic_model_conditioned",
        "stage3a": {
            "disposition": "not_supported_under_preregistered_rule",
            "brier_improvement_fraction": 0.02,
        },
        "stage3b": {
            "disposition": "not_supported_under_preregistered_rule",
            "final_size_mae_improvement_fraction": 0.03,
        },
        "limitations": ["Synthetic test evidence."],
    }
    (execution / "stage3_evidence.json").write_text(
        json.dumps(evidence, indent=2), encoding="utf-8"
    )
    pd.DataFrame(
        [
            {
                "scenario_id": "scenario-a",
                "replication": 0,
                "operational_failure": 1,
                "deadline_miss_fraction": 0.10,
                "useful_task_throughput_ratio": 0.80,
                "omega_a": 1.3,
            }
        ]
    ).to_parquet(raw / "stage3a_replications.parquet", index=False)
    pd.DataFrame(
        [
            {
                "scenario_id": "scenario-b",
                "record_id": "scenario-b:r0",
                "split": "heldout",
                "block": 0,
                "n_agents": 100,
                "topology": "hierarchical",
                "attack_class": "credential_replay",
                "outbreak": 1,
                "final_compromise_fraction": 0.20,
                "dmp_outbreak_probability": 0.70,
                "dmp_expected_fraction": 0.24,
                "static_nonbacktracking": 0.31,
            },
            {
                "scenario_id": "scenario-z",
                "record_id": "scenario-z:r0",
                "split": "heldout",
                "block": 1,
                "n_agents": 100,
                "topology": "hierarchical",
                "attack_class": "shared_image",
                "outbreak": 0,
                "final_compromise_fraction": 0.01,
                "dmp_outbreak_probability": 0.10,
                "dmp_expected_fraction": 0.02,
                "static_nonbacktracking": 0.09,
            },
        ]
    ).to_parquet(raw / "stage3b_replications.parquet", index=False)
    pd.DataFrame(
        [
            {
                "scenario_id": "scenario-a",
                "block_id": 0,
                "candidate_probability": 0.8,
                "operational_failure": 1,
            }
        ]
    ).to_parquet(derived / "stage3a_heldout_predictions.parquet", index=False)
    pd.DataFrame(
        [
            {
                "record_id": "scenario-b:r0",
                "scenario_id": "scenario-b",
                "block": 0,
                "n_agents": 100,
                "topology": "hierarchical",
                "attack_class": "credential_replay",
                "segmentation_policy": "partitioned",
                "defense_case": "nominal",
                "outbreak": 1,
                "final_compromise_fraction": 0.20,
                "candidate_outbreak_probability": 0.70,
                "candidate_conditional_severity": 0.24,
                "candidate_conditional_severity_lower": 0.18,
                "candidate_conditional_severity_upper": 0.30,
                "candidate_expected_final_fraction": 0.22,
                "candidate_expected_final_fraction_lower": 0.16,
                "candidate_expected_final_fraction_upper": 0.28,
                "baseline_final_fraction": 0.27,
                "baseline_outbreak_probability": 0.61,
            },
            {
                "record_id": "scenario-z:r0",
                "scenario_id": "scenario-z",
                "block": 1,
                "n_agents": 100,
                "topology": "hierarchical",
                "attack_class": "shared_image",
                "segmentation_policy": "partitioned",
                "defense_case": "nominal",
                "outbreak": 0,
                "final_compromise_fraction": 0.01,
                "candidate_outbreak_probability": 0.10,
                "candidate_conditional_severity": 0.08,
                "candidate_conditional_severity_lower": 0.03,
                "candidate_conditional_severity_upper": 0.13,
                "candidate_expected_final_fraction": 0.02,
                "candidate_expected_final_fraction_lower": 0.00,
                "candidate_expected_final_fraction_upper": 0.05,
                "baseline_final_fraction": 0.04,
                "baseline_outbreak_probability": 0.15,
            },
        ]
    ).to_parquet(derived / "stage3b_heldout_predictions.parquet", index=False)

    if traces:
        trace_dir = execution / "stage3a" / "block-0" / "held_out" / "traces"
        trace_dir.mkdir(parents=True)
        pd.DataFrame(
            [
                {
                    "scenario_id": "scenario-a",
                    "replication": 0,
                    "time_s": step,
                    "planned_admissions": 10 if step == 0 else 0,
                    "admitted_agents": 10 if step == 0 else 0,
                    "fleet_size": 10,
                    "projected_fleet_size": 10,
                    "maximum_observed_omega": 0.5 + 0.4 * step,
                    "projected_maximum_omega": 0.6 + 0.4 * step,
                    "representation": "exact",
                }
                for step in range(5)
            ]
        ).to_parquet(trace_dir / "stage3a_admission_timeseries.parquet", index=False)
        pd.DataFrame(
            [
                {
                    "scenario_id": "scenario-a",
                    "replication": 0,
                    "time_s": step,
                    "resource_id": "authorization_policy_evaluation",
                    "queue_depth": float(step),
                    "projected_queue_depth": float(step) + 0.5,
                    "wait_s": float(step),
                    "projected_wait_s": float(step) + 0.5,
                    "omega_observed": float(step) / 2.0,
                    "projected_omega": (float(step) + 0.5) / 2.0,
                    "representation": "exact",
                }
                for step in range(5)
            ]
        ).to_parquet(trace_dir / "stage3a_resource_timeseries.parquet", index=False)
        lifecycle_dir = execution / "stage3b" / "traces"
        lifecycle_dir.mkdir(parents=True)
        pd.DataFrame(
            [
                {
                    "scenario_id": "scenario-b",
                    "step": step,
                    "observed_ever_compromised_fraction": 0.05 * step,
                    "observed_detected_fraction": 0.02 * step,
                    "observed_quarantined_fraction": 0.01 * step,
                    "observed_revoked_fraction": 0.005 * step,
                    "observed_recovered_fraction": 0.002 * step,
                    "predicted_ever_compromised_fraction": 0.04 * step,
                    "representation": "exact_observed_and_estimated_dmp",
                }
                for step in range(5)
            ]
        ).to_parquet(
            lifecycle_dir / "stage3b_lifecycle_timeseries.parquet", index=False
        )
        pd.DataFrame(
            [
                {
                    "record_id": "scenario-b:r0",
                    "scenario_id": "scenario-b",
                    "block": 0,
                    "replication": 0,
                    "step": step,
                    "susceptible_fraction": 1.0 - 0.05 * step,
                    "compromised_undetected_fraction": 0.02 * step,
                    "detected_fraction": 0.01 * step,
                    "quarantined_fraction": 0.005 * step,
                    "revoked_fraction": 0.002 * step,
                    "recovered_fraction": 0.001 * step,
                    "mean_edge_no_transmission": 1.0 - 0.01 * step,
                    "mean_edge_source_active": 0.01 * step,
                    "mean_common_cause_survival": 1.0 - 0.02 * step,
                    "representation": "estimated_dmp_aggregate",
                }
                for step in range(5)
            ]
        ).to_parquet(
            lifecycle_dir / "stage3b_dmp_state_summary.parquet", index=False
        )
        graph = {
            "record_id": "scenario-b:r0",
            "scenario_id": "scenario-b",
            "block": 0,
            "replication": 0,
            "nodes": [
                {"id": 0, "x": 0.0, "y": 0.0, "segment": 0, "initial_probability": 0.1},
                {"id": 1, "x": 1.0, "y": 0.0, "segment": 1, "initial_probability": 0.2},
            ],
            "edges": [{"source": 0, "target": 1, "layer": "authorization"}],
            "representation": "exact",
        }
        (lifecycle_dir / "stage3b_graph_evidence.json").write_text(
            json.dumps(graph), encoding="utf-8"
        )

    artifacts = []
    for path in sorted(candidate for candidate in execution.rglob("*") if candidate.is_file()):
        artifacts.append(
            {
                "path": path.relative_to(execution).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    (execution / "execution_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "execution_id": execution_id,
                "status": "completed",
                "artifacts": artifacts,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return execution


def _snapshot(directory: Path) -> dict[str, tuple[int, str]]:
    return {
        path.relative_to(directory).as_posix(): (path.stat().st_mtime_ns, _sha256(path))
        for path in directory.rglob("*")
        if path.is_file()
    }


def test_loader_is_read_only_and_retains_evidence_labels(tmp_path: Path) -> None:
    execution = _write_execution(tmp_path, "primary", traces=True)
    before = _snapshot(execution)
    bundle = load_stage3_execution(execution)
    after = _snapshot(execution)

    assert before == after
    assert bundle.payload["execution"]["integrity"] == "verified_loaded_artifacts"
    assert bundle.payload["availability"] == {
        "stage3a_admission_trace": True,
        "stage3a_resource_trace": True,
        "stage3b_lifecycle_trace": True,
        "stage3b_dmp_state_summary": True,
        "stage3b_graph": True,
    }
    assert bundle.payload["stage3a"]["representations"]["admission_trace"][
        "representation"
    ] == "exact"
    resource = bundle.payload["stage3a"]["resource_trace"]
    assert resource[-1]["observed_wait_budget_s_derived"] == 2.0
    dmp_state = bundle.payload["stage3b"]["dmp_state_summary"]
    assert dmp_state[-1]["mean_edge_no_transmission"] == 0.96
    assert bundle.payload["stage3b"]["representations"]["dmp_state_summary"] == {
        "representation": "estimated",
        "retention": "exact",
        "source_rows": 5,
        "retained_rows": 5,
        "source_representation": "estimated_dmp_aggregate",
    }
    assert bundle.payload["stage3b"]["representations"]["dmp"] == "estimated"
    assert bundle.payload["stage3b"]["trace_scenario_ids"] == ["scenario-b"]
    assert bundle.payload["stage3b"]["selector_scenario_ids"] == [
        "scenario-b",
        "scenario-z",
    ]
    assert bundle.payload["stage3b"]["graph_scenario_id"] == "scenario-b"
    dmp_integrity = next(
        check
        for check in bundle.payload["integrity_checks"]
        if check["path"] == "stage3b/traces/stage3b_dmp_state_summary.parquet"
    )
    assert dmp_integrity["status"] == "match"


def test_missing_optional_traces_degrade_honestly(tmp_path: Path) -> None:
    execution = _write_execution(tmp_path, "summary-only", traces=False)
    bundle = load_stage3_execution(execution)

    assert not bundle.payload["availability"]["stage3a_admission_trace"]
    assert not bundle.payload["availability"]["stage3b_lifecycle_trace"]
    assert not bundle.payload["availability"]["stage3b_dmp_state_summary"]
    warning_text = " ".join(bundle.payload["warnings"])
    assert (
        "Stage 3B DMP state summary was not retained; node-state, edge-message, "
        "and common-cause views are unavailable and are not inferred."
    ) in bundle.payload["warnings"]
    assert "not retained" in warning_text
    assert "unavailable" in warning_text
    assert bundle.payload["stage3b"]["lifecycle_trace"] == []
    assert bundle.payload["stage3b"]["dmp_state_summary"] == []
    assert bundle.payload["stage3b"]["representations"]["dmp_state_summary"][
        "representation"
    ] == "not_retained"


def test_invalid_dmp_summary_is_unavailable_and_not_reconstructed(
    tmp_path: Path,
) -> None:
    execution = _write_execution(tmp_path, "invalid-dmp", traces=True)
    dmp_path = execution / "stage3b/traces/stage3b_dmp_state_summary.parquet"
    invalid = pd.read_parquet(dmp_path).drop(columns=["mean_common_cause_survival"])
    invalid.to_parquet(dmp_path, index=False)
    before = _snapshot(execution)

    bundle = load_stage3_execution(execution)

    assert _snapshot(execution) == before
    assert not bundle.payload["availability"]["stage3b_dmp_state_summary"]
    assert bundle.payload["stage3b"]["dmp_state_summary"] == []
    assert bundle.payload["stage3b"]["representations"]["dmp_state_summary"][
        "representation"
    ] == "unavailable"
    warning_text = " ".join(bundle.payload["warnings"])
    assert "missing required columns" in warning_text
    assert "not inferred" in warning_text


def test_trace_default_and_graph_display_are_bound_to_retained_scenario(
    tmp_path: Path,
) -> None:
    execution = _write_execution(tmp_path, "scenario-binding", traces=True)
    bundle = load_stage3_execution(execution)
    html = build_stage3_console(
        execution,
        tmp_path / "scenario-binding.html",
    ).read_text(encoding="utf-8")

    assert bundle.payload["stage3b"]["selector_scenario_ids"][0] == "scenario-b"
    assert bundle.payload["stage3b"]["selector_scenario_ids"][1] == "scenario-z"
    assert bundle.payload["stage3b"]["graph_scenario_id"] == "scenario-b"
    assert "renderGraph(scenario)" in html
    assert "String(graphScenario)!==String(scenario)" in html
    assert "It is unavailable for selected scenario" in html
    assert "no graph is reconstructed" in html


def test_console_and_json_exports_are_offline_and_do_not_touch_sources(
    tmp_path: Path,
) -> None:
    primary = _write_execution(tmp_path, "primary", traces=True)
    comparison = _write_execution(tmp_path, "comparison", traces=True)
    before_primary = _snapshot(primary)
    before_comparison = _snapshot(comparison)

    html_path = build_stage3_console(
        primary,
        tmp_path / "stage3-console.html",
        comparison_execution=comparison,
        initial_mode="comparison",
    )
    json_path = export_stage3_console_json(
        primary,
        tmp_path / "stage3-console.json",
        comparison_execution=comparison,
    )
    html = html_path.read_text(encoding="utf-8")
    exported = json.loads(json_path.read_text(encoding="utf-8"))

    assert _snapshot(primary) == before_primary
    assert _snapshot(comparison) == before_comparison
    assert "<script src=" not in html.lower()
    assert "Live, completed-run animation" in html
    assert "Omega(t) and boundary crossing" in html
    assert "Detection, quarantine, revocation, and recovery" in html
    assert "Retained DMP node-state fractions, estimated" in html
    assert "Retained DMP edge and common-cause summaries, estimated" in html
    assert "mean_edge_no_transmission" in html
    assert "mean_common_cause_survival" in html
    assert "Expected final fraction, estimated with calibration-fitted interval" in html
    assert "Comparison expected final fraction, estimated with calibration-fitted interval" in html
    assert "Expected final fraction, estimated; interval not retained" in html
    assert "no interval claimed" not in html
    assert "dmpStatePlot" in html
    assert "dmpMechanismPlot" in html
    assert "dmpFeaturePlot" in html
    assert "Plotly.newPlot('dmpPlot'" not in html
    assert "DMP state '+text(dmpMeta.representation)+', retention '" in html
    assert "PRIMARY.stage3b.selector_scenario_ids" in html
    assert "renderGraph(scenario)" in html
    assert "It is unavailable for selected scenario" in html
    assert all(label in html for label in ("exact", "sampled", "estimated", "observed", "predicted"))
    assert "primary" in html and "comparison" in html
    assert exported["primary"]["execution"]["execution_id"] == "primary"
    assert exported["comparison"]["execution"]["execution_id"] == "comparison"
    assert exported["primary"]["stage3b"]["trace_scenario_ids"][0] == "scenario-b"
    assert exported["primary"]["stage3b"]["selector_scenario_ids"] == [
        "scenario-b",
        "scenario-z",
    ]
    assert exported["primary"]["stage3b"]["graph_scenario_id"] == "scenario-b"


def test_console_applies_deterministic_trace_bound(tmp_path: Path) -> None:
    execution = _write_execution(tmp_path, "bounded", traces=True)
    bundle = load_stage3_execution(
        execution,
        limits=ConsoleLimits(max_table_rows=10, max_trace_rows=3),
    )

    admission = bundle.payload["stage3a"]["admission_trace"]
    dmp_state = bundle.payload["stage3b"]["dmp_state_summary"]
    assert len(admission) == 3
    assert bundle.payload["stage3a"]["representations"]["admission_trace"][
        "representation"
    ] == "sampled"
    assert admission[0]["time_s"] == 0
    assert admission[-1]["time_s"] == 4
    assert len(dmp_state) == 3
    assert bundle.payload["stage3b"]["representations"]["dmp_state_summary"][
        "retention"
    ] == "sampled"


def test_scenario_configuration_and_request_enforce_bounds(tmp_path: Path) -> None:
    config = Stage3ScenarioConfig(
        fleet_size=250,
        injection="sybil",
        injection_fraction=0.20,
    )
    request = write_scenario_request(config, tmp_path / "request.json")
    payload = json.loads(request.read_text(encoding="utf-8"))
    assert payload["configuration"]["injection_fraction"] == 0.20
    assert payload["action"] == "create_new_immutable_visual_demonstration"
    with pytest.raises(ValueError, match="fleet_size"):
        Stage3ScenarioConfig(fleet_size=2_001)
    with pytest.raises(ValueError, match="injection_fraction"):
        Stage3ScenarioConfig(injection="sybil", injection_fraction=0.251)
    with pytest.raises(ValueError, match="must be zero"):
        Stage3ScenarioConfig(injection="none", injection_fraction=0.01)
    with pytest.raises(FileExistsError, match="overwrite"):
        write_scenario_request(config, request)


def test_live_mode_creates_run_before_animation_and_refuses_reuse(tmp_path: Path) -> None:
    config = Stage3ScenarioConfig(
        fleet_size=20,
        admission_duration_s=5.0,
        recovery_window_s=0.0,
        horizon_steps=4,
        seed=1234,
    )
    execution = run_visual_scenario(config, tmp_path / "visual-run")
    evidence = json.loads((execution / "stage3_evidence.json").read_text(encoding="utf-8"))
    manifest = json.loads((execution / "execution_manifest.json").read_text(encoding="utf-8"))

    assert evidence["execution"]["mode"] == "visual_live_demonstration"
    assert evidence["evidence_scope"] == "synthetic_model_demonstration_only"
    assert manifest["status"] == "completed"
    assert (execution / "stage3b/traces/stage3b_lifecycle_timeseries.parquet").is_file()
    assert (execution / "stage3b/traces/stage3b_dmp_state_summary.parquet").is_file()
    assert load_stage3_execution(execution).payload["availability"][
        "stage3b_dmp_state_summary"
    ]
    assert load_stage3_execution(execution).payload["execution"]["integrity"] == (
        "verified_loaded_artifacts"
    )
    with pytest.raises(FileExistsError, match="overwrite"):
        run_visual_scenario(config, execution)


def test_console_outputs_cannot_be_written_inside_source_execution(tmp_path: Path) -> None:
    execution = _write_execution(tmp_path, "immutable", traces=False)
    with pytest.raises(ValueError, match="outside immutable"):
        build_stage3_console(execution, execution / "console.html")
    with pytest.raises(ValueError, match="outside immutable"):
        export_stage3_console_json(execution, execution / "console.json")
