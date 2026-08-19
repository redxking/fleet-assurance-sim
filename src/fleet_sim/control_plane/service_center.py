"""Deterministic queue-backed service center for integrated scenarios."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from fleet_sim.model.engine import DeterministicEventEngine


@dataclass(slots=True)
class ServiceRequest:
    request_id: str
    submitted_at: float
    on_complete: Callable[[float], None]


class ServiceCenter:
    def __init__(
        self,
        name: str,
        engine: DeterministicEventEngine,
        servers: int,
        service_rate: float,
        rng: np.random.Generator,
        on_queue_change: Callable[[str, int, int, int], None],
    ) -> None:
        if servers < 1 or service_rate <= 0.0:
            raise ValueError("invalid service center parameters")
        self.name = name
        self.engine = engine
        self.servers = servers
        self.service_rate = service_rate
        self.rng = rng
        self.on_queue_change = on_queue_change
        self.busy = 0
        self.queue: deque[ServiceRequest] = deque()
        self.max_queue = 0
        self.completed = 0
        self.wait_samples: list[float] = []

    def submit(self, request: ServiceRequest) -> None:
        self.queue.append(request)
        self.max_queue = max(self.max_queue, len(self.queue))
        self._notify()
        self._start_available()

    def _start_available(self) -> None:
        while self.queue and self.busy < self.servers:
            request = self.queue.popleft()
            self.busy += 1
            wait = self.engine.now - request.submitted_at
            self.wait_samples.append(wait)
            self._notify()
            service_time = float(self.rng.exponential(1.0 / self.service_rate))

            def finish(req: ServiceRequest = request, elapsed: float = service_time) -> None:
                self.busy -= 1
                self.completed += 1
                req.on_complete(elapsed)
                self._notify()
                self._start_available()

            self.engine.schedule_after(service_time, finish, label=f"{self.name}:complete")

    def _notify(self) -> None:
        self.on_queue_change(self.name, len(self.queue), self.busy, self.servers)
