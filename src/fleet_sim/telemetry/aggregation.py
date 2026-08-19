"""Telemetry aggregation and model-specific rate-distortion calculations."""

from __future__ import annotations

import math


def supervisory_depth(n_agents: int, span: int) -> int:
    if n_agents < 1 or span < 2:
        raise ValueError("invalid hierarchy parameters")
    return math.ceil(math.log(n_agents, span)) if n_agents > 1 else 0


def apex_ingest_rate(
    n_agents: int,
    per_agent_rate_bits_per_second: float,
    span: int,
    compression_ratio_per_layer: float,
) -> float:
    if n_agents < 1 or per_agent_rate_bits_per_second < 0 or span < 2:
        raise ValueError("invalid ingest parameters")
    if not 0 < compression_ratio_per_layer <= 1:
        raise ValueError("compression ratio must be in (0, 1]")
    depth = supervisory_depth(n_agents, span)
    return n_agents * per_agent_rate_bits_per_second * compression_ratio_per_layer**depth


def gaussian_rate_distortion_bits_per_sample(variance: float, distortion: float) -> float:
    """Gaussian squared-error rate-distortion function.

    This result applies only to a memoryless Gaussian source under mean-squared
    error distortion. It is not a universal telemetry model.
    """

    if variance <= 0 or distortion < 0:
        raise ValueError("invalid rate-distortion parameters")
    if distortion >= variance:
        return 0.0
    if distortion == 0:
        return float("inf")
    return 0.5 * math.log2(variance / distortion)


def flat_observability_ceiling(channel_capacity_bits_per_second: float, rate_per_agent: float) -> int:
    if channel_capacity_bits_per_second < 0 or rate_per_agent <= 0:
        raise ValueError("invalid observability parameters")
    return int(channel_capacity_bits_per_second // rate_per_agent)
