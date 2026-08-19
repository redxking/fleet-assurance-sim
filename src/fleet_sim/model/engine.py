"""Deterministic callback-based discrete-event simulation kernel."""

from __future__ import annotations

import heapq
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


Callback = Callable[[], None]


@dataclass(order=True, slots=True)
class _ScheduledCallback:
    time: float
    priority: int
    sequence: int
    callback: Callback = field(compare=False)
    label: str = field(compare=False, default="event")


class DeterministicEventEngine:
    """Minimal explicit event queue with deterministic tie breaking.

    Callbacks scheduled for the same simulation time and priority execute in
    insertion order. Given the same configuration, seed streams, and callback
    schedule, execution is deterministic.
    """

    def __init__(self) -> None:
        self.now = 0.0
        self.executed_events = 0
        self._sequence = 0
        self._queue: list[_ScheduledCallback] = []
        self._current_label: str | None = None

    @property
    def pending_events(self) -> int:
        return len(self._queue)

    @property
    def current_label(self) -> str | None:
        return self._current_label

    def schedule_at(
        self,
        when: float,
        callback: Callback,
        *,
        priority: int = 100,
        label: str = "event",
    ) -> int:
        if when < self.now:
            raise ValueError("cannot schedule an event in the past")
        if not callable(callback):
            raise TypeError("callback must be callable")
        sequence = self._sequence
        self._sequence += 1
        heapq.heappush(
            self._queue,
            _ScheduledCallback(float(when), int(priority), sequence, callback, label),
        )
        return sequence

    def schedule_after(
        self,
        delay: float,
        callback: Callback,
        *,
        priority: int = 100,
        label: str = "event",
    ) -> int:
        if delay < 0:
            raise ValueError("delay cannot be negative")
        return self.schedule_at(self.now + float(delay), callback, priority=priority, label=label)

    def run(self, *, until: float | None = None, max_events: int | None = None) -> int:
        if until is not None and until < self.now:
            raise ValueError("until cannot precede current simulation time")
        if max_events is not None and max_events < 1:
            raise ValueError("max_events must be positive")

        executed_at_start = self.executed_events
        while self._queue:
            if max_events is not None and self.executed_events - executed_at_start >= max_events:
                break
            scheduled = heapq.heappop(self._queue)
            if until is not None and scheduled.time > until:
                heapq.heappush(self._queue, scheduled)
                self.now = float(until)
                break
            self.now = scheduled.time
            self._current_label = scheduled.label
            scheduled.callback()
            self.executed_events += 1
        self._current_label = None
        if until is not None and not self._queue and self.now < until:
            self.now = float(until)
        return self.executed_events - executed_at_start

    def clear(self) -> None:
        self._queue.clear()
        self._current_label = None

    def queue_manifest(self) -> list[dict[str, Any]]:
        return [
            {
                "time": item.time,
                "priority": item.priority,
                "sequence": item.sequence,
                "label": item.label,
            }
            for item in sorted(self._queue)
        ]
