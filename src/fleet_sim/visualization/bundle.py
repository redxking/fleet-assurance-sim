"""Replay-bundle loading utilities shared by visual front ends."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fleet_sim.model.events import EventLog
from fleet_sim.model.replay import StateSnapshot, read_snapshots
from fleet_sim.model.state import FleetState


@dataclass(frozen=True, slots=True)
class ReplayBundle:
    path: Path
    run_id: str
    configuration: dict[str, Any]
    summary: dict[str, Any]
    graph_layers: dict[str, Any]
    initial_state: FleetState
    final_state: FleetState
    events: EventLog
    snapshots: tuple[StateSnapshot, ...]


def load_replay_bundle(path: str | Path) -> ReplayBundle:
    bundle = Path(path)
    required = [
        "config.yaml",
        "summary.json",
        "graph_layers.json",
        "initial_state.json",
        "final_state.json",
        "events.jsonl",
    ]
    missing = [name for name in required if not (bundle / name).exists()]
    if missing:
        raise FileNotFoundError(f"bundle {bundle} is missing: {', '.join(missing)}")

    import yaml

    configuration = yaml.safe_load((bundle / "config.yaml").read_text(encoding="utf-8"))
    summary = json.loads((bundle / "summary.json").read_text(encoding="utf-8"))
    graph_layers = json.loads((bundle / "graph_layers.json").read_text(encoding="utf-8"))
    initial = FleetState.from_dict(json.loads((bundle / "initial_state.json").read_text(encoding="utf-8")))
    final = FleetState.from_dict(json.loads((bundle / "final_state.json").read_text(encoding="utf-8")))
    events = EventLog.read_jsonl(bundle / "events.jsonl")
    snapshots = (
        tuple(read_snapshots(bundle / "snapshots.jsonl"))
        if (bundle / "snapshots.jsonl").exists()
        else tuple()
    )
    return ReplayBundle(
        bundle,
        str(summary.get("run_id", bundle.name)),
        configuration,
        summary,
        graph_layers,
        initial,
        final,
        events,
        snapshots,
    )


def discover_bundles(repository_root: str | Path) -> list[Path]:
    root = Path(repository_root) / "replay_bundles"
    if not root.exists():
        return []
    bundles = [path for path in root.iterdir() if path.is_dir() and (path / "events.jsonl").exists()]
    return sorted(bundles, key=lambda path: path.stat().st_mtime, reverse=True)
