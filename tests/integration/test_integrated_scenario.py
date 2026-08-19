from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from fleet_sim.config import load_config
from fleet_sim.experiments.simulator import FleetSimulator
from fleet_sim.model.events import EventLog
from fleet_sim.model.replay import ReplayEngine
from fleet_sim.model.state import FleetState
from fleet_sim.visualization.console import build_console


def test_integrated_scenario_and_console(tmp_path: Path) -> None:
    source = load_config(Path("configs/experiments/stage0_demo.yaml"))
    config = replace(source, n_agents=24, duration_s=22.0, attack_start_s=7.0, timing_denial_start_s=12.0, mass_revocation_start_s=17.0, task_arrival_rate_per_agent_hz=0.08)
    artifacts = FleetSimulator(config, Path(".")).run(tmp_path)
    summary = json.loads(artifacts.summary_path.read_text(encoding="utf-8"))
    assert artifacts.final_state_hash == artifacts.replay_state_hash
    assert summary["replay_validation"]["passed"] is True
    assert summary["event_counts_by_type"]["SIMULATION_START"] == 1
    assert summary["event_counts_by_type"]["SIMULATION_END"] == 1
    assert summary["event_counts_by_type"].get("GOSSIP_ROUND", 0) > 0
    assert summary["event_counts_by_type"].get("COMPROMISE", 0) > 0
    assert summary["event_counts_by_type"].get("TIMING_UPDATE", 0) > 0
    assert summary["event_counts_by_type"].get("CREDENTIAL_REVOCATION_STORM_START", 0) == 1
    console = build_console(artifacts.bundle_dir)
    assert console.exists()
    text = console.read_text(encoding="utf-8")
    assert "Virtual Fleet Assurance Console" in text
    assert "<script src=" not in text.lower()


def test_seed_determinism(tmp_path: Path) -> None:
    source = load_config(Path("configs/experiments/stage0_demo.yaml"))
    config = replace(source, n_agents=16, duration_s=15.0, attack_start_s=5.0, timing_denial_start_s=9.0, mass_revocation_start_s=12.0, task_arrival_rate_per_agent_hz=0.05)
    first = FleetSimulator(config, Path(".")).run(tmp_path / "one")
    second = FleetSimulator(config, Path(".")).run(tmp_path / "two")
    assert first.event_log_digest == second.event_log_digest
    assert first.final_state_hash == second.final_state_hash
