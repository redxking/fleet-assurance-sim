"""Supervisory span and review-capacity models."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SupervisoryLayer:
    layer: int
    population: int
    alert_rate_hz: float
    reviewers: int
    service_rate_per_reviewer_hz: float
    utilization: float


def supervisory_depth(n: int, span: int) -> int:
    if n < 1 or span < 2:
        raise ValueError("invalid supervisory hierarchy")
    return 0 if n == 1 else math.ceil(math.log(n, span))


def supervisory_layers(
    n: int,
    *,
    span: int,
    alert_rate_per_agent_hz: float,
    suppression_ratio: float,
    reviewers_per_layer: int,
    service_rate_per_reviewer_hz: float,
) -> tuple[SupervisoryLayer, ...]:
    if not 0 <= suppression_ratio <= 1:
        raise ValueError("suppression_ratio must be in [0, 1]")
    depth = supervisory_depth(n, span)
    layers = []
    population = n
    incoming = n * alert_rate_per_agent_hz
    for layer in range(1, depth + 1):
        population = math.ceil(population / span)
        incoming *= suppression_ratio
        capacity = reviewers_per_layer * service_rate_per_reviewer_hz
        utilization = incoming / capacity if capacity > 0 else math.inf
        layers.append(
            SupervisoryLayer(
                layer,
                population,
                incoming,
                reviewers_per_layer,
                service_rate_per_reviewer_hz,
                utilization,
            )
        )
    return tuple(layers)
