from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from fleet_sim.control_plane.resource_network import AdmissionPattern
from fleet_sim.experiments.stage3a import (
    Stage3AScenario,
    default_stage3a_scenarios,
    run_stage3a,
)


def _scenario() -> Stage3AScenario:
    return Stage3AScenario(
        scenario_id="tiny-heldout-block-2",
        pattern=AdmissionPattern.PERIODIC,
        initial_n=10,
        final_n=100,
        admission_duration_s=6.0,
        recovery_window_s=4.0,
        dt_s=1.0,
        partition="held_out",
        block_id=2,
        architecture="sharded",
        workload="renewal-heavy",
        shift_label="capacity-down",
    )


def test_stage3a_runner_writes_deterministic_labeled_artifacts(tmp_path: Path) -> None:
    first = run_stage3a(
        [_scenario()],
        tmp_path / "first",
        root_seed=20260819,
        replications=2,
        maximum_trace_rows=50,
    )
    second = run_stage3a(
        [_scenario()],
        tmp_path / "second",
        root_seed=20260819,
        replications=2,
        maximum_trace_rows=50,
    )
    first_raw = pd.read_parquet(first.raw_replications_path)
    second_raw = pd.read_parquet(second.raw_replications_path)
    pd.testing.assert_frame_equal(first_raw, second_raw)
    assert set(first_raw.partition) == {"held_out"}
    assert set(first_raw.block_id) == {2}
    assert set(first_raw.architecture) == {"sharded"}
    assert set(first_raw.workload) == {"renewal-heavy"}
    assert "omega_a" in first_raw
    assert "operational_failure" in first_raw
    assert "total_admitted_agents" in first_raw
    assert "observed_total_admitted_agents" in first_raw
    assert first.resource_trace_path is not None and first.resource_trace_path.exists()
    assert first.admission_trace_path is not None and first.admission_trace_path.exists()
    resource_trace = pd.read_parquet(first.resource_trace_path)
    assert {"omega_observed", "projected_omega", "representation"}.issubset(resource_trace)
    assert len(resource_trace) <= 50
    summary = json.loads(first.summary_path.read_text(encoding="utf-8"))
    assert summary["operational_failure_definition_uses_omega"] is False
    with pytest.raises(FileExistsError, match="overwrite"):
        run_stage3a([_scenario()], first.output_dir, root_seed=20260819, replications=2)


def test_default_matrix_includes_scale_ladder_and_all_patterns() -> None:
    scenarios = default_stage3a_scenarios()
    assert {scenario.final_n for scenario in scenarios} == {100, 1_000, 10_000}
    assert {scenario.pattern for scenario in scenarios} == set(AdmissionPattern)


def test_stage3a_randomization_pairs_share_noise_but_seed_domains_do_not(tmp_path: Path) -> None:
    first = replace(
        _scenario(),
        scenario_id="paired-capacity-080",
        capacity_multiplier=0.8,
        randomization_pair_id="heldout-pair-001",
    )
    second = replace(
        _scenario(),
        scenario_id="paired-capacity-125",
        capacity_multiplier=1.25,
        randomization_pair_id="heldout-pair-001",
    )
    pilot = run_stage3a(
        [first, second],
        tmp_path / "pilot",
        root_seed=111,
        replications=3,
        trace_replications_per_scenario=0,
    )
    confirmatory = run_stage3a(
        [first, second],
        tmp_path / "confirmatory",
        root_seed=222,
        replications=3,
        trace_replications_per_scenario=0,
    )
    pilot_rows = pd.read_parquet(pilot.raw_replications_path)
    confirmatory_rows = pd.read_parquet(confirmatory.raw_replications_path)
    paired = pilot_rows.pivot(
        index="replication", columns="scenario_id", values="replication_seed"
    )
    assert (paired["paired-capacity-080"] == paired["paired-capacity-125"]).all()
    assert set(pilot_rows.replication_seed).isdisjoint(confirmatory_rows.replication_seed)
