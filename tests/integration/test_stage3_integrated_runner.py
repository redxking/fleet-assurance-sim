from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest
import yaml

from fleet_sim.experiments import stage3_runner
from fleet_sim.experiments.stage3_protocol import (
    FrozenInputError,
    build_preexecution_manifest,
    write_new_json,
)
from fleet_sim.experiments.stage3b import Stage3BBaselineSelectionScore

ROOT = Path(__file__).resolve().parents[2]


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")


def _minimal_runner_root(root: Path) -> Path:
    configs = root / "configs" / "stage3"
    manifests = root / "manifests"
    manifests.mkdir(parents=True)
    _write_yaml(
        configs / "protocol.yaml",
        {
            "protocol_id": "FAS-S3-TEST",
            "evidence_scope": "test_only",
            "status_before_freeze": "frozen_for_confirmatory_execution",
            "frozen_files": ["frozen-input.txt"],
            "frozen_globs": [],
            "seed_domains": {
                "pilot": {
                    "stage3a": "pilot-stage3a",
                    "stage3a_bootstrap": "pilot-stage3a-bootstrap",
                    "stage3b": "pilot-stage3b",
                    "stage3b_bootstrap": "pilot-stage3b-bootstrap",
                },
                "confirmatory": {
                    "stage3a": "confirmatory-stage3a",
                    "stage3a_bootstrap": "confirmatory-stage3a-bootstrap",
                    "stage3b": "confirmatory-stage3b",
                    "stage3b_bootstrap": "confirmatory-stage3b-bootstrap",
                },
            },
            "bootstrap_seed_bases": {"stage3a": 1001, "stage3b": 1002},
            "partitions": {
                "training": {"fleet_sizes": [10]},
                "calibration": {"fleet_sizes": [20]},
                "held_out": {"fleet_sizes": [30]},
                "independent_blocks": 1,
            },
        },
    )
    _write_yaml(
        configs / "admission_matrix.yaml",
        {"replications": {"engineering_pilot": 2, "confirmatory": 3}},
    )
    _write_yaml(
        configs / "compromise_matrix.yaml",
        {"replications": {"engineering_pilot": 2, "confirmatory": 4}},
    )
    _write_yaml(
        configs / "compute_budget.yaml",
        {
            "engineering_pilot": {
                "bootstrap_draws": 5,
                "wall_clock_seconds": 60,
                "peak_rss_mb": 4_096,
                "maximum_output_mb": 100,
            },
            "confirmatory": {
                "bootstrap_draws": 7,
                "wall_clock_seconds": 60,
                "peak_rss_mb": 4_096,
                "maximum_output_mb": 100,
            },
        },
    )
    pd.DataFrame(
        [
            {
                "protocol_id": "FAS-S3-TEST",
                "block": 0,
                "partition": partition,
                "graph_seed": 100 + offset,
                "process_seed": 101 + offset,
                "observation_seed": 102 + offset,
                "replication_seed": 103 + offset,
                "use": use,
            }
            for partition, offset, use in (
                ("training", 0, "fit_only"),
                ("calibration", 100, "select_and_calibrate_only"),
                ("held_out", 200, "adjudication_only"),
            )
        ]
    ).to_csv(manifests / "stage3_seed_manifest.csv", index=False)
    return root


def test_execute_stage3_rejects_counts_that_differ_from_protocol(tmp_path: Path) -> None:
    root = _minimal_runner_root(tmp_path)

    with pytest.raises(ValueError, match="counts must match the frozen protocol"):
        stage3_runner.execute_stage3(
            root,
            mode="pilot",
            execution_id="wrong-counts",
            stage3a_replications=1,
            stage3b_replications=2,
            bootstrap_draws=5,
        )

    assert not (root / "results").exists()


def test_seed_manifest_requires_exact_protocol_rows_and_use_labels(tmp_path: Path) -> None:
    root = _minimal_runner_root(tmp_path)
    assert len(stage3_runner._seed_table(root)) == 3
    path = root / "manifests/stage3_seed_manifest.csv"
    frame = pd.read_csv(path)

    wrong_protocol = frame.copy()
    wrong_protocol.loc[0, "protocol_id"] = "WRONG"
    wrong_protocol.to_csv(path, index=False)
    with pytest.raises(ValueError, match="protocol_id"):
        stage3_runner._seed_table(root)

    wrong_use = frame.copy()
    wrong_use.loc[wrong_use.partition == "calibration", "use"] = "fit_only"
    wrong_use.to_csv(path, index=False)
    with pytest.raises(ValueError, match="use labels"):
        stage3_runner._seed_table(root)

    frame.iloc[:-1].to_csv(path, index=False)
    with pytest.raises(ValueError, match="rows are incomplete"):
        stage3_runner._seed_table(root)


def test_confirmatory_hash_gate_precedes_no_overwrite_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _minimal_runner_root(tmp_path)
    monkeypatch.setattr(
        stage3_runner,
        "_load_boundary_audit",
        lambda _root: {
            "status": "passed_structural_review",
            "identical_latent_equation_reuse_detected": False,
        },
    )
    frozen = root / "frozen-input.txt"
    frozen.write_text("frozen\n", encoding="utf-8")
    manifest = build_preexecution_manifest(
        root,
        protocol_id="FAS-S3-TEST",
        frozen_files=["frozen-input.txt"],
        evidence_scope="test_only",
        execution_contract={
            "execution_id": "collision",
            "command_argv": [sys.executable, *sys.argv],
            "stage3a_replications_per_scenario": 3,
            "stage3b_replications_per_scenario": 4,
            "bootstrap_draws": 7,
            "seed_domains": {
                "stage3a": "confirmatory-stage3a",
                "stage3a_bootstrap": "confirmatory-stage3a-bootstrap",
                "stage3b": "confirmatory-stage3b",
                "stage3b_bootstrap": "confirmatory-stage3b-bootstrap",
            },
            "bootstrap_seed_bases": {"stage3a": 1001, "stage3b": 1002},
        },
    )
    write_new_json(root / "manifests" / "stage3_preexecution_manifest.json", manifest)

    frozen.write_text("changed\n", encoding="utf-8")
    with pytest.raises(FrozenInputError, match="frozen input verification failed"):
        stage3_runner.execute_stage3(
            root,
            mode="confirmatory",
            execution_id="collision",
            stage3a_replications=3,
            stage3b_replications=4,
            bootstrap_draws=7,
        )
    assert not (root / "results").exists()

    frozen.write_text("frozen\n", encoding="utf-8")
    expected = root / "results" / "stage3" / str(manifest["protocol_hash"]) / "collision"
    expected.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        stage3_runner.execute_stage3(
            root,
            mode="confirmatory",
            execution_id="collision",
            stage3a_replications=3,
            stage3b_replications=4,
            bootstrap_draws=7,
        )


def test_stage3b_specs_preserve_seed_partitions_and_transfer_coverage() -> None:
    protocol = stage3_runner._load_yaml(ROOT / "configs/stage3/protocol.yaml")
    compromise = stage3_runner._load_yaml(ROOT / "configs/stage3/compromise_matrix.yaml")
    seeds = stage3_runner._seed_table(ROOT)
    specs = stage3_runner.build_stage3b_specs(
        protocol,
        compromise,
        seeds,
        replications=2,
    )

    expected_count = 5 * ((3 + 1) * 6 + 2 * 6 * 2)
    assert len(specs) == expected_count
    assert len({spec.scenario_id for spec in specs}) == expected_count
    assert {spec.n_agents for spec in specs if spec.split == "exploratory"} == {
        100,
        250,
        500,
    }
    assert {spec.n_agents for spec in specs if spec.split == "calibration"} == {750}
    assert {spec.n_agents for spec in specs if spec.split == "heldout"} == {1_000, 10_000}
    assert {
        (spec.topology, spec.n_agents) for spec in specs if spec.split == "heldout"
    } == set(product(("barabasi_albert", "hierarchical"), (1_000, 10_000)))
    topology_by_split = {
        "exploratory": {"random_regular", "erdos_renyi"},
        "calibration": {"random_regular", "erdos_renyi"},
        "heldout": {"barabasi_albert", "hierarchical"},
    }
    expected_segmentations = {"none", "partitioned_8_way"}
    for split, topologies in topology_by_split.items():
        for block in range(5):
            block_specs = [
                spec for spec in specs if spec.split == split and spec.block == block
            ]
            assert {
                (spec.topology, spec.segmentation_policy) for spec in block_specs
            } == set(product(topologies, expected_segmentations))
        for attack_class in {
            spec.attack_class for spec in specs if spec.split == split
        }:
            attack_specs = [
                spec
                for spec in specs
                if spec.split == split and spec.attack_class == attack_class
            ]
            assert {spec.topology for spec in attack_specs} == topologies
            assert {
                spec.segmentation_policy for spec in attack_specs
            } == expected_segmentations

    assert all(spec.replications == 2 for spec in specs)
    heldout_pairs: dict[str, list[stage3_runner.Stage3BScenarioSpec]] = {}
    for spec in specs:
        if spec.split == "heldout":
            heldout_pairs.setdefault(spec.scenario_id.rsplit("-", 1)[0], []).append(spec)
    assert heldout_pairs
    assert all(len(pair) == 2 for pair in heldout_pairs.values())
    assert all(
        len(
            {
                (row.graph_seed, row.process_seed, row.observation_seed, row.replication_seed)
                for row in pair
            }
        )
        == 1
        for pair in heldout_pairs.values()
    )

    pilot_specs = stage3_runner.build_stage3b_specs(
        protocol,
        compromise,
        seeds,
        replications=2,
        seed_domain="pilot-stage3b",
    )
    confirmatory_seeds = {
        value
        for spec in specs
        for value in (
            spec.graph_seed,
            spec.process_seed,
            spec.observation_seed,
            spec.replication_seed,
        )
    }
    pilot_seeds = {
        value
        for spec in pilot_specs
        for value in (
            spec.graph_seed,
            spec.process_seed,
            spec.observation_seed,
            spec.replication_seed,
        )
    }
    assert confirmatory_seeds.isdisjoint(pilot_seeds)


def test_hierarchical_bootstrap_is_deterministic_paired_and_finite() -> None:
    rows = [
        {
            "block_id": block,
            "scenario_id": f"b{block}-s{scenario}",
            "candidate": 0.1 + 0.01 * replication,
            "baseline": 0.2 + 0.01 * replication,
        }
        for block in range(3)
        for scenario in range(4)
        for replication in range(5)
    ]
    frame = pd.DataFrame(rows)
    first = stage3_runner._hierarchical_bootstrap(
        frame,
        candidate_error="candidate",
        baseline_error="baseline",
        seed=20260819,
        draws=100,
    )
    second = stage3_runner._hierarchical_bootstrap(
        frame,
        candidate_error="candidate",
        baseline_error="baseline",
        seed=20260819,
        draws=100,
    )

    assert first == second
    assert first["absolute_improvement"] == pytest.approx([0.1, 0.1])
    assert all(np.isfinite(value) for interval in first.values() for value in interval)


def test_hierarchical_bootstrap_retains_all_rows_in_aligned_replication_unit() -> None:
    rows = []
    for block in range(2):
        for pair in range(3):
            for replication in range(4):
                rows.extend(
                    (
                        {
                            "block_id": block,
                            "pair_id": f"b{block}-p{pair}",
                            "replication": replication,
                            "scenario_id": f"b{block}-p{pair}-positive",
                            "candidate": 0.0,
                            "baseline": 1.0,
                        },
                        {
                            "block_id": block,
                            "pair_id": f"b{block}-p{pair}",
                            "replication": replication,
                            "scenario_id": f"b{block}-p{pair}-negative",
                            "candidate": 1.0,
                            "baseline": 0.0,
                        },
                    )
                )
    result = stage3_runner._hierarchical_bootstrap(
        pd.DataFrame(rows),
        candidate_error="candidate",
        baseline_error="baseline",
        seed=37,
        draws=200,
        cluster_column="pair_id",
        replication_unit_column="replication",
    )

    assert result["absolute_improvement"] == pytest.approx([0.0, 0.0])
    assert result["fractional_improvement"] == pytest.approx([0.0, 0.0])


def _stage3a_frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    partitions = {
        "training": (
            np.arange(8, dtype=float),
            np.asarray([0, 0, 0, 0, 1, 1, 1, 1], dtype=int),
            100,
        ),
        "calibration": (
            np.asarray([0.5, 2.5, 4.5, 6.5]),
            np.asarray([0, 0, 1, 1], dtype=int),
            750,
        ),
        "held_out": (
            np.asarray([0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5]),
            np.asarray([0, 0, 1, 0, 1, 1, 0, 1], dtype=int),
            10_000,
        ),
    }
    for partition, (scores, outcomes, final_n) in partitions.items():
        for index, (score, outcome) in enumerate(zip(scores, outcomes)):
            heldout = partition == "held_out"
            rows.append(
                {
                    "partition": partition,
                    "block_id": 0,
                    "scenario_id": f"{partition}-{index}",
                    "randomization_pair_id": f"{partition}-pair-{index}",
                    "replication": 0,
                    "operational_failure": int(outcome),
                    "omega_a": float(score),
                    "observed_omega_a": float(100.0 - score),
                    "final_n": final_n,
                    "architecture": (
                        "sharded_workload_shift"
                        if heldout and index % 2 == 0
                        else "pipelined_balanced" if heldout else "centralized_balanced"
                    ),
                    "workload": "gamma" if heldout and index % 2 == 0 else "poisson",
                    "capacity_multiplier": 0.8 if heldout and index % 3 == 0 else 1.0,
                    "final_fleet_size": final_n,
                    "peak_dndt": float(score),
                    "mean_dndt": 1.0,
                    "peak_resource_utilization": 1.0,
                    "maximum_projected_queue_depth": 1.0,
                    "total_admitted_agents": final_n - 10,
                    "cumulative_backlog_area": 1.0,
                    "maximum_projected_deadline_miss_fraction": 0.1,
                }
            )
    return pd.DataFrame(rows)


def _stage3a_acceptance() -> dict[str, object]:
    return {
        "minimum_brier_improvement_fraction": 0.0,
        "bootstrap_improvement_lower_bound_greater_than": -1.0,
        "minimum_auc": 0.0,
        "calibration_slope_range": [-1e6, 1e6],
        "minimum_positive_blocks": 1,
        "minimum_transfer_balanced_accuracy": 0.0,
    }


def test_stage3a_predictions_do_not_consume_heldout_outcomes_or_observed_omega() -> None:
    raw = _stage3a_frame()
    predictions, summary = stage3_runner.analyze_stage3a(
        raw,
        acceptance=_stage3a_acceptance(),
        bootstrap_seed=17,
        bootstrap_draws=12,
    )
    changed = raw.copy()
    heldout = changed.partition == "held_out"
    changed.loc[heldout, "operational_failure"] = (
        1 - changed.loc[heldout, "operational_failure"]
    )
    changed.loc[heldout, "observed_omega_a"] = -999.0
    changed_predictions, changed_summary = stage3_runner.analyze_stage3a(
        changed,
        acceptance=_stage3a_acceptance(),
        bootstrap_seed=17,
        bootstrap_draws=12,
    )

    probability_columns = [
        "candidate_probability",
        "baseline_probability",
        "multivariate_probability",
    ]
    pd.testing.assert_frame_equal(
        predictions.sort_values("scenario_id")[probability_columns].reset_index(drop=True),
        changed_predictions.sort_values("scenario_id")[probability_columns].reset_index(
            drop=True
        ),
    )
    first_block = summary["block_results"][0]
    changed_block = changed_summary["block_results"][0]
    assert first_block["strongest_simple_baseline"] == "peak_dndt"
    assert changed_block["strongest_simple_baseline"] == "peak_dndt"
    assert first_block["baseline_selection_partition"] == "calibration"
    assert changed_block["baseline_selection_partition"] == "calibration"
    assert first_block["probability_mapping_partition"] == "calibration"
    assert first_block["baseline_selection_method"] == "leave_one_scenario_out_crossfit"
    assert (
        summary["criteria"]["threshold_transfers_to_n10000_sublinear_capacity"]["status"]
        == "not_evaluable"
    )
    json.dumps(stage3_runner._json_value(summary), allow_nan=False)


def _stage3b_predictions(candidate_error: float) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    combinations = product(
        ("barabasi_albert", "hierarchical"),
        (1_000, 10_000),
        ("none", "partitioned_8_way"),
        (0, 1),
    )
    for index, (topology, n_agents, segmentation, outbreak) in enumerate(combinations):
        probability = 0.2 if outbreak == 0 else 0.8
        for defense_case in ("nominal", "detection_response_shift"):
            pair_id = f"transfer-{index}"
            rows.append(
                {
                    "block": index % 2,
                    "scenario_id": f"{pair_id}-{defense_case}",
                    "defense_pair_record_id": f"{pair_id}:r0",
                    "defense_pair_id": pair_id,
                    "replication_seed": index + 400,
                    "base_replication_seed": index + 300,
                    "graph_seed": index + 100,
                    "process_seed": index + 200,
                    "observation_seed": index + 250,
                    "topology": topology,
                    "n_agents": n_agents,
                    "segmentation_policy": segmentation,
                    "defense_case": defense_case,
                    "outbreak": outbreak,
                    "candidate_outbreak_probability": probability,
                    "candidate_final_absolute_error": candidate_error,
                    "baseline_final_absolute_error": 0.2,
                    "candidate_brier_component": (probability - outbreak) ** 2,
                    "baseline_brier_component": 0.25,
                }
            )
    return pd.DataFrame(rows)


def _stage3b_result() -> SimpleNamespace:
    return SimpleNamespace(
        candidate_evaluation={"name": "candidate"},
        selection_partition="calibration",
        selection_method="leave_one_block_out_calibration_crossfit",
        comparator_specs=MappingProxyType({"static_adjacency": {"model_class": "univariate"}}),
        strongest_final_size_baseline="static_adjacency",
        strongest_initiation_baseline="static_adjacency",
        baseline_selection_scores=MappingProxyType({"static_adjacency": {"score": 0.2}}),
        baseline_evaluations=MappingProxyType({"static_adjacency": {"score": 0.2}}),
        final_size_mae_improvement_fraction=0.5,
        outbreak_brier_improvement_fraction=0.5,
        positive_final_size_blocks=5,
        positive_outbreak_brier_blocks=5,
        heldout_binary_support_by_block=MappingProxyType({0: True, 1: True}),
        valid_binary_support_blocks=2,
    )


def _stage3b_acceptance() -> dict[str, object]:
    return {
        "minimum_final_size_mae_improvement_fraction": 0.15,
        "minimum_outbreak_brier_improvement_fraction": 0.10,
        "minimum_positive_blocks": 4,
        "bootstrap_improvement_lower_bound_greater_than": -1.0,
        "minimum_transfer_mae_improvement_fraction": 0.0,
        "maximum_calibration_slope_shift": 0.20,
    }


def test_stage3b_transfer_requires_positive_improvement_not_group_presence() -> None:
    no_improvement = stage3_runner.analyze_stage3b(
        _stage3b_result(),
        _stage3b_predictions(candidate_error=0.2),
        acceptance=_stage3b_acceptance(),
        bootstrap_seed=29,
        bootstrap_draws=12,
    )
    improved = stage3_runner.analyze_stage3b(
        _stage3b_result(),
        _stage3b_predictions(candidate_error=0.1),
        acceptance=_stage3b_acceptance(),
        bootstrap_seed=29,
        bootstrap_draws=12,
    )

    assert (
        no_improvement["criteria"]["unseen_topology_transfer_succeeds"]["status"]
        == "failed"
    )
    assert no_improvement["criteria"]["unseen_scale_transfer_succeeds"]["status"] == "failed"
    assert improved["criteria"]["unseen_topology_transfer_succeeds"]["status"] == "passed"
    assert improved["criteria"]["unseen_scale_transfer_succeeds"]["status"] == "passed"
    assert (
        improved["criteria"]["all_heldout_blocks_have_binary_class_support"]["status"]
        == "passed"
    )


def test_stage3b_defense_pair_criterion_requires_exact_cases_and_shared_seeds() -> None:
    predictions = _stage3b_predictions(candidate_error=0.1)
    valid = stage3_runner.analyze_stage3b(
        _stage3b_result(),
        predictions,
        acceptance=_stage3b_acceptance(),
        bootstrap_seed=31,
        bootstrap_draws=12,
    )
    assert valid["criteria"]["paired_defense_scenarios_complete"]["status"] == "passed"

    shifted_index = predictions.index[
        predictions.defense_case == "detection_response_shift"
    ][0]
    predictions.loc[shifted_index, "base_replication_seed"] += 1
    invalid = stage3_runner.analyze_stage3b(
        _stage3b_result(),
        predictions,
        acceptance=_stage3b_acceptance(),
        bootstrap_seed=31,
        bootstrap_draws=12,
    )
    assert invalid["criteria"]["paired_defense_scenarios_complete"]["status"] == "failed"


def test_json_value_serializes_frozen_dataclasses_and_mapping_proxies() -> None:
    score = Stage3BBaselineSelectionScore(
        name="static_adjacency",
        calibration_final_size_mae=np.float64(0.2),
        calibration_outbreak_brier=np.float64(0.1),
    )
    payload = MappingProxyType(
        {
            "selected": score,
            "vector": np.asarray([1, 2], dtype=np.int64),
            "path": Path("derived/stage3b.parquet"),
        }
    )

    converted = stage3_runner._json_value(payload)
    encoded = json.dumps(converted, allow_nan=False, sort_keys=True)

    assert converted["selected"]["name"] == "static_adjacency"
    assert converted["vector"] == [1, 2]
    assert converted["path"] == "derived/stage3b.parquet"
    assert "static_adjacency" in encoded
