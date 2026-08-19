from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


DEFAULT_STREAMS = (
    "workload_arrival",
    "workload_target",
    "control_service",
    "agent_service",
    "graph_communication",
    "graph_authorization",
    "network",
    "authorization",
    "consensus",
    "compromise",
    "detection",
    "recovery",
    "credentials",
    "telemetry",
    "visualization",
)


@dataclass(slots=True)
class RandomStreams:
    """Named deterministic PCG64DXSM streams derived from one SeedSequence."""

    root_seed: int
    stream_names: tuple[str, ...] = DEFAULT_STREAMS
    _generators: dict[str, np.random.Generator] = field(init=False, repr=False)
    _spawn_keys: dict[str, tuple[int, ...]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if len(set(self.stream_names)) != len(self.stream_names):
            raise ValueError("stream names must be unique")
        seed_sequence = np.random.SeedSequence(self.root_seed)
        children = seed_sequence.spawn(len(self.stream_names))
        self._generators = {
            name: np.random.Generator(np.random.PCG64DXSM(child))
            for name, child in zip(self.stream_names, children, strict=True)
        }
        self._spawn_keys = {
            name: tuple(child.spawn_key)
            for name, child in zip(self.stream_names, children, strict=True)
        }

    def rng(self, name: str) -> np.random.Generator:
        try:
            return self._generators[name]
        except KeyError as exc:
            raise KeyError(f"unknown random stream: {name}") from exc

    def manifest(self) -> dict[str, object]:
        return {
            "generator": "NumPy PCG64DXSM",
            "root_seed": self.root_seed,
            "substreams": {name: list(key) for name, key in self._spawn_keys.items()},
        }
