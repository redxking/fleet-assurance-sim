from __future__ import annotations

from fleet_sim.model.agent import AgentHealth
from fleet_sim.model.events import Event, EventLog
from fleet_sim.model.replay import ReplayEngine
from fleet_sim.model.state import FleetState


def _event(state: FleetState, logical_time: int, event_type: str, destination: str) -> Event:
    before = state.state_hash()
    provisional = Event(
        run_id="test",
        configuration_hash="cfg",
        seed=1,
        event_id=f"event-{logical_time}",
        parent_event_id=None,
        simulation_time=float(logical_time),
        logical_time=logical_time,
        event_type=event_type,
        destination_id=destination,
        state_before=before,
    )
    state.apply(provisional)
    return Event(**{**provisional.to_dict(), "state_after": state.state_hash()})


def test_replay_checks_state_hashes_and_snapshot_seek() -> None:
    initial = FleetState.initial(["agent-000000"])
    builder_state = FleetState.from_dict(initial.to_dict())
    log = EventLog()
    for index, event_type in enumerate(["COMPROMISE", "DETECTION", "QUARANTINE", "REVOCATION", "RECOVERY"], start=1):
        event = _event(builder_state, index, event_type, "agent-000000")
        log.append(event)
    replay = ReplayEngine(initial, log)
    final = replay.replay()
    assert final.agents["agent-000000"].health == AgentHealth.RECOVERED
    snapshots = replay.snapshots(2)
    seeked = replay.seek_from_snapshot(snapshots[1], len(log))
    assert seeked.state_hash() == final.state_hash()
