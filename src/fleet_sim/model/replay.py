"""Deterministic replay and snapshot support."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from fleet_sim.model.events import Event, EventLog
from fleet_sim.model.state import FleetState


@dataclass(frozen=True, slots=True)
class StateSnapshot:
    event_index: int
    simulation_time: float
    state_hash: str
    state: dict[str, object]

    def to_json(self) -> str:
        return json.dumps(
            {
                "event_index": self.event_index,
                "simulation_time": self.simulation_time,
                "state_hash": self.state_hash,
                "state": self.state,
            },
            sort_keys=True,
            separators=(",", ":"),
        )


class ReplayEngine:
    def __init__(self, initial_state: FleetState, events: EventLog | tuple[Event, ...]) -> None:
        self.initial_state = FleetState.from_dict(initial_state.to_dict())
        self.events = events.events if isinstance(events, EventLog) else events

    def replay(self, through_event: int | None = None) -> FleetState:
        state = FleetState.from_dict(self.initial_state.to_dict())
        limit = len(self.events) if through_event is None else min(through_event, len(self.events))
        for event in self.events[:limit]:
            if event.state_before is not None:
                before = state.state_hash()
                if event.state_before != before:
                    raise ValueError(
                        f"replay state-before mismatch at {event.event_id}: "
                        f"expected {event.state_before}, got {before}"
                    )
            state.apply(event)
            if event.state_after is not None:
                after = state.state_hash()
                if event.state_after != after:
                    raise ValueError(
                        f"replay state-after mismatch at {event.event_id}: "
                        f"expected {event.state_after}, got {after}"
                    )
        return state

    def snapshots(self, interval_events: int) -> list[StateSnapshot]:
        if interval_events < 1:
            raise ValueError("interval_events must be positive")
        state = FleetState.from_dict(self.initial_state.to_dict())
        snapshots = [StateSnapshot(0, 0.0, state.state_hash(), state.to_dict())]
        for index, event in enumerate(self.events, start=1):
            state.apply(event)
            if index % interval_events == 0 or index == len(self.events):
                snapshots.append(
                    StateSnapshot(index, event.simulation_time, state.state_hash(), state.to_dict())
                )
        return snapshots

    def seek_from_snapshot(self, snapshot: StateSnapshot, through_event: int) -> FleetState:
        if through_event < snapshot.event_index:
            raise ValueError("target event precedes snapshot")
        state = FleetState.from_dict(snapshot.state)
        for event in self.events[snapshot.event_index:through_event]:
            state.apply(event)
        return state


def write_snapshots(snapshots: list[StateSnapshot], path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for snapshot in snapshots:
            handle.write(snapshot.to_json())
            handle.write("\n")
    return destination


def read_snapshots(path: str | Path) -> list[StateSnapshot]:
    snapshots: list[StateSnapshot] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            data = json.loads(line)
            snapshots.append(StateSnapshot(**data))
    return snapshots
