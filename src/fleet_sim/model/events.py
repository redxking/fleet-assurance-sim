"""Canonical append-only event records and persistence helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


@dataclass(frozen=True, slots=True)
class Event:
    run_id: str
    configuration_hash: str
    seed: int
    event_id: str
    parent_event_id: str | None
    simulation_time: float
    logical_time: int
    event_type: str
    source_id: str | None = None
    destination_id: str | None = None
    resource_id: str | None = None
    graph_layer: str | None = None
    task_id: str | None = None
    coalition_id: str | None = None
    message_id: str | None = None
    message_bytes: int = 0
    capability_id: str | None = None
    authorization_decision: str | None = None
    credential_epoch: int | None = None
    state_before: str | None = None
    state_after: str | None = None
    severity: str = "info"
    policy_version: str = "v0"
    timing_uncertainty: float | None = None
    provenance_tag: str = "notional"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), default=str)


class EventLog:
    def __init__(self) -> None:
        self._events: list[Event] = []

    def append(self, event: Event) -> None:
        if self._events:
            previous = self._events[-1]
            if event.logical_time <= previous.logical_time:
                raise ValueError("logical_time must increase monotonically")
            if event.simulation_time < previous.simulation_time:
                raise ValueError("simulation_time must not decrease")
        self._events.append(event)

    @property
    def events(self) -> tuple[Event, ...]:
        return tuple(self._events)

    def __len__(self) -> int:
        return len(self._events)

    def __iter__(self):
        return iter(self._events)

    def digest(self) -> str:
        hasher = hashlib.sha256()
        for event in self._events:
            hasher.update(event.canonical_json().encode("utf-8"))
            hasher.update(b"\n")
        return hasher.hexdigest()

    def event_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in self._events:
            counts[event.event_type] = counts.get(event.event_type, 0) + 1
        return dict(sorted(counts.items()))

    def to_frame(self) -> pd.DataFrame:
        rows = []
        for event in self._events:
            row = event.to_dict()
            row["metadata"] = json.dumps(row["metadata"], sort_keys=True, separators=(",", ":"))
            rows.append(row)
        return pd.DataFrame(rows)

    def write_jsonl(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8") as handle:
            for event in self._events:
                handle.write(event.canonical_json())
                handle.write("\n")
        return destination

    def write_csv(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.to_frame().to_csv(destination, index=False)
        return destination

    def write_parquet(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.to_frame().to_parquet(destination, index=False)
        except ImportError as exc:
            raise RuntimeError(
                "Parquet output requires the optional pyarrow or fastparquet dependency"
            ) from exc
        return destination

    @classmethod
    def read_jsonl(cls, path: str | Path) -> "EventLog":
        log = cls()
        with Path(path).open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    data = json.loads(line)
                    log.append(Event(**data))
        return log

    @classmethod
    def from_events(cls, events: Iterable[Event]) -> "EventLog":
        log = cls()
        for event in events:
            log.append(event)
        return log
