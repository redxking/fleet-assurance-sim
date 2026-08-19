"""Telemetry hierarchy and observability ceiling models."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TelemetryHierarchyResult:
    fleet_size: int
    span: int
    depth: int
    raw_rate_bps: float
    apex_rate_bps: float
    layer_rates_bps: tuple[float, ...]


def gaussian_rate_distortion(variance: float, distortion: float) -> float:
    if variance <= 0 or distortion <= 0:
        raise ValueError("variance and distortion must be positive")
    if distortion >= variance:
        return 0.0
    return 0.5 * math.log2(variance / distortion)


def flat_observability_ceiling(channel_capacity_bps: float, rate_distortion_bps: float) -> int:
    if channel_capacity_bps < 0 or rate_distortion_bps < 0:
        raise ValueError("rates must be nonnegative")
    if rate_distortion_bps == 0:
        return math.inf  # type: ignore[return-value]
    return math.floor(channel_capacity_bps / rate_distortion_bps)


def hierarchical_telemetry(
    fleet_size: int,
    rate_per_agent_bps: float,
    *,
    span: int,
    compression_ratio: float,
    metadata_rate_bps_per_aggregator: float = 64.0,
    alert_rate_bps_per_aggregator: float = 16.0,
) -> TelemetryHierarchyResult:
    if fleet_size < 1 or rate_per_agent_bps < 0 or span < 2:
        raise ValueError("invalid hierarchy parameters")
    if not 0 <= compression_ratio <= 1:
        raise ValueError("compression_ratio must be in [0, 1]")
    depth = 0 if fleet_size == 1 else math.ceil(math.log(fleet_size, span))
    rate = fleet_size * rate_per_agent_bps
    layer_rates = [rate]
    nodes_at_layer = fleet_size
    for _ in range(depth):
        aggregators = math.ceil(nodes_at_layer / span)
        rate = compression_ratio * rate + aggregators * (
            metadata_rate_bps_per_aggregator + alert_rate_bps_per_aggregator
        )
        layer_rates.append(rate)
        nodes_at_layer = aggregators
    return TelemetryHierarchyResult(
        fleet_size,
        span,
        depth,
        fleet_size * rate_per_agent_bps,
        rate,
        tuple(layer_rates),
    )
