"""Fleet state transition model shared by simulation and replay."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from fleet_sim.model.agent import AgentHealth, AgentRuntimeState
from fleet_sim.model.events import Event


@dataclass(slots=True)
class FleetState:
    agents: dict[str, AgentRuntimeState]
    simulation_time: float = 0.0
    logical_time: int = 0
    queues: dict[str, int] = field(default_factory=dict)
    busy_servers: dict[str, int] = field(default_factory=dict)
    queue_utilization: dict[str, float] = field(default_factory=dict)
    counters: dict[str, float] = field(default_factory=dict)
    timing_denial_active: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def initial(
        cls,
        agent_ids: list[str],
        *,
        hierarchy_span: int = 8,
        timing_uncertainty_s: float = 0.0,
    ) -> "FleetState":
        agents: dict[str, AgentRuntimeState] = {}
        for index, agent_id in enumerate(agent_ids):
            supervisor_index = (index - 1) // hierarchy_span if index > 0 else None
            agents[agent_id] = AgentRuntimeState(
                timing_uncertainty_s=timing_uncertainty_s,
                partition=index // max(1, hierarchy_span),
                supervisor_id=(f"agent-{supervisor_index:06d}" if supervisor_index is not None else None),
            )
        return cls(agents=agents)

    def apply(self, event: Event) -> None:
        self.simulation_time = event.simulation_time
        self.logical_time = event.logical_time
        event_type = event.event_type
        source = event.source_id
        destination = event.destination_id

        if event_type == "TASK_ARRIVAL":
            self._increment("tasks_arrived")
        elif event_type == "AUTH_REQUEST":
            self._increment("authorization_requests")
        elif event_type == "AUTH_DECISION":
            self._increment("authorization_decisions")
            if event.authorization_decision == "permit":
                self._increment("authorization_permits")
            else:
                self._increment("authorization_denies")
            if bool(event.metadata.get("false_permit", False)):
                self._increment("authorization_false_permits")
            if bool(event.metadata.get("false_deny", False)):
                self._increment("authorization_false_denies")
        elif event_type == "TASK_DISPATCH" and destination in self.agents:
            agent = self.agents[destination]
            if agent.health in {AgentHealth.IDLE, AgentHealth.RECOVERED}:
                agent.health = AgentHealth.WORKING
            agent.current_task_id = event.task_id
        elif event_type == "TASK_COMPLETE" and source in self.agents:
            agent = self.agents[source]
            if agent.health == AgentHealth.WORKING:
                agent.health = AgentHealth.IDLE
            agent.current_task_id = None
            self._increment("tasks_completed")
            if bool(event.metadata.get("useful", False)):
                self._increment("useful_tasks_completed")
        elif event_type in {"TASK_FAILED", "TASK_DEADLINE_MISSED"}:
            self._increment("tasks_failed")
            agent_id = source if source in self.agents else destination
            if agent_id in self.agents:
                agent = self.agents[agent_id]
                if agent.health == AgentHealth.WORKING:
                    agent.health = AgentHealth.IDLE
                agent.current_task_id = None
        elif event_type == "GOSSIP_SEED" and destination in self.agents:
            if not self.agents[destination].informed:
                self.agents[destination].informed = True
                self._increment("gossip_informed")
        elif event_type == "GOSSIP_INFORMED" and destination in self.agents:
            if not self.agents[destination].informed:
                self.agents[destination].informed = True
                self._increment("gossip_informed")
        elif event_type == "COMPROMISE" and destination in self.agents:
            self.agents[destination].health = AgentHealth.COMPROMISED
            self._increment("compromise_events")
        elif event_type == "DETECTION" and destination in self.agents:
            self.agents[destination].health = AgentHealth.SUSPECTED
            self._increment("detections")
        elif event_type == "QUARANTINE" and destination in self.agents:
            self.agents[destination].health = AgentHealth.ISOLATED
            self._increment("quarantines")
        elif event_type == "REVOCATION" and destination in self.agents:
            agent = self.agents[destination]
            agent.health = AgentHealth.REVOKED
            if event.credential_epoch is not None:
                agent.credential_epoch = event.credential_epoch
            self._increment("revocations")
        elif event_type == "RECOVERY" and destination in self.agents:
            self.agents[destination].health = AgentHealth.RECOVERED
            self._increment("recoveries")
        elif event_type == "CREDENTIAL_RENEWAL" and destination in self.agents:
            if event.credential_epoch is not None:
                self.agents[destination].credential_epoch = event.credential_epoch
            self._increment("credential_renewals")
        elif event_type == "CREDENTIAL_RENEWAL_DENIED":
            self._increment("credential_renewal_denials")
        elif event_type == "CREDENTIAL_REVOCATION_STORM_START":
            self.metadata["credential_storm_active"] = True
        elif event_type == "CREDENTIAL_REVOCATION_STORM_END":
            self.metadata["credential_storm_active"] = False
        elif event_type == "TIMING_DENIAL_START":
            self.timing_denial_active = True
        elif event_type == "TIMING_UPDATE" and destination in self.agents:
            if event.timing_uncertainty is not None:
                self.agents[destination].timing_uncertainty_s = event.timing_uncertainty
        elif event_type == "QUEUE_SAMPLE":
            center = str(event.metadata["service_center"])
            self.queues[center] = int(event.metadata["queue_length"])
            self.busy_servers[center] = int(event.metadata.get("busy_servers", 0))
            self.queue_utilization[center] = float(event.metadata["utilization"])
        elif event_type == "SIMULATION_END":
            self.metadata["ended"] = True
            self.metadata["event_log_digest_before_end"] = event.metadata.get(
                "event_log_digest_before_end"
            )

    def _increment(self, name: str, amount: float = 1.0) -> None:
        self.counters[name] = self.counters.get(name, 0.0) + amount

    def to_dict(self) -> dict[str, Any]:
        return {
            "agents": {
                agent_id: {
                    **asdict(state),
                    "health": state.health.value,
                }
                for agent_id, state in sorted(self.agents.items())
            },
            "simulation_time": self.simulation_time,
            "logical_time": self.logical_time,
            "queues": dict(sorted(self.queues.items())),
            "busy_servers": dict(sorted(self.busy_servers.items())),
            "queue_utilization": dict(sorted(self.queue_utilization.items())),
            "counters": dict(sorted(self.counters.items())),
            "timing_denial_active": self.timing_denial_active,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FleetState":
        agents = {
            agent_id: AgentRuntimeState(
                health=AgentHealth(agent_data["health"]),
                current_task_id=agent_data.get("current_task_id"),
                credential_epoch=int(agent_data.get("credential_epoch", 0)),
                timing_uncertainty_s=float(agent_data.get("timing_uncertainty_s", 0.0)),
                informed=bool(agent_data.get("informed", False)),
                partition=int(agent_data.get("partition", 0)),
                supervisor_id=agent_data.get("supervisor_id"),
            )
            for agent_id, agent_data in data["agents"].items()
        }
        return cls(
            agents=agents,
            simulation_time=float(data.get("simulation_time", 0.0)),
            logical_time=int(data.get("logical_time", 0)),
            queues={k: int(v) for k, v in data.get("queues", {}).items()},
            busy_servers={k: int(v) for k, v in data.get("busy_servers", {}).items()},
            queue_utilization={k: float(v) for k, v in data.get("queue_utilization", {}).items()},
            counters={k: float(v) for k, v in data.get("counters", {}).items()},
            timing_denial_active=bool(data.get("timing_denial_active", False)),
            metadata=dict(data.get("metadata", {})),
        )

    def state_hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
