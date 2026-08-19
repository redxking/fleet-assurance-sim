from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class TaskStatus(StrEnum):
    ARRIVED = "arrived"
    AUTH_QUEUED = "auth_queued"
    AUTHORIZED = "authorized"
    DENIED = "denied"
    EXECUTING = "executing"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(slots=True)
class Task:
    task_id: str
    arrival_time: float
    deadline_s: float
    assigned_agent: str
    required_capabilities: tuple[str, ...] = ("task.execute",)
    coalition_id: str | None = None
    criticality_weight: float = 1.0
    status: TaskStatus = TaskStatus.ARRIVED
    authorization_time: float | None = None
    completion_time: float | None = None
    audit_evidence_present: bool = True
    duplicate_irreversible_effect: bool = False
    compromised_result: bool = False
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def latency(self) -> float | None:
        if self.completion_time is None:
            return None
        return self.completion_time - self.arrival_time

    @property
    def useful(self) -> bool:
        latency = self.latency
        return bool(
            self.status == TaskStatus.COMPLETE
            and latency is not None
            and latency <= self.deadline_s
            and self.audit_evidence_present
            and not self.duplicate_irreversible_effect
            and not self.compromised_result
        )
