from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Mapping, Protocol


class AgentHealth(StrEnum):
    IDLE = "idle"
    WORKING = "working"
    SUSPECTED = "suspected"
    COMPROMISED = "compromised"
    ISOLATED = "isolated"
    REVOKED = "revoked"
    TERMINATED = "terminated"
    RECOVERED = "recovered"


class ExternalPolicy(Protocol):
    def __call__(self, observation: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class Capability:
    capability_id: str
    resource_scope: str
    action: str
    criticality_weight: float = 1.0


@dataclass(slots=True)
class Agent:
    """Runtime-agnostic external representation of an agent."""

    agent_id: str
    workload_identity: str
    capabilities: tuple[Capability, ...]
    opaque_state_label: str = "opaque"
    policy: ExternalPolicy | Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None
    service_rate_hz: float = 1.0
    telemetry_rate_bps: float = 2_000.0
    kill_authority_endpoint: str = "local://revoke"
    credential_epoch: int = 0
    health: AgentHealth = AgentHealth.IDLE
    metadata: dict[str, Any] = field(default_factory=dict)

    def external_view(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "workload_identity": self.workload_identity,
            "capabilities": [cap.capability_id for cap in self.capabilities],
            "opaque_state_label": self.opaque_state_label,
            "service_rate_hz": self.service_rate_hz,
            "telemetry_rate_bps": self.telemetry_rate_bps,
            "kill_authority_endpoint": self.kill_authority_endpoint,
            "credential_epoch": self.credential_epoch,
            "health": self.health.value,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class AgentRuntimeState:
    """Replayable state visible outside an opaque agent implementation."""

    health: AgentHealth = AgentHealth.IDLE
    current_task_id: str | None = None
    credential_epoch: int = 0
    timing_uncertainty_s: float = 0.0
    informed: bool = False
    partition: int = 0
    supervisor_id: str | None = None
