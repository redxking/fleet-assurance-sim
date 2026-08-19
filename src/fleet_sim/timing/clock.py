"""Physical latency, thermodynamic floor, and timing-uncertainty models."""

from __future__ import annotations

import math

BOLTZMANN_J_PER_K = 1.380649e-23
SPEED_OF_LIGHT_M_PER_S = 299_792_458.0


def fiber_propagation_delay(distance_m: float, refractive_index: float = 1.47) -> float:
    if distance_m < 0 or refractive_index <= 1:
        raise ValueError("invalid propagation parameters")
    return distance_m / (SPEED_OF_LIGHT_M_PER_S / refractive_index)


def landauer_energy_per_bit(temperature_kelvin: float = 300.0) -> float:
    if temperature_kelvin <= 0:
        raise ValueError("temperature must be positive")
    return BOLTZMANN_J_PER_K * temperature_kelvin * math.log(2.0)


def holdover_uncertainty(
    initial_uncertainty_seconds: float,
    fractional_frequency_error: float,
    denial_interval_seconds: float,
) -> float:
    if initial_uncertainty_seconds < 0 or denial_interval_seconds < 0:
        raise ValueError("uncertainty and denial interval cannot be negative")
    return initial_uncertainty_seconds + abs(fractional_frequency_error) * denial_interval_seconds


def commit_wait_seconds(clock_uncertainty_seconds: float) -> float:
    if clock_uncertainty_seconds < 0:
        raise ValueError("clock uncertainty cannot be negative")
    return 2.0 * clock_uncertainty_seconds


def single_lane_ordered_throughput_ceiling(clock_uncertainty_seconds: float) -> float:
    wait = commit_wait_seconds(clock_uncertainty_seconds)
    if wait == 0:
        return float("inf")
    return 1.0 / wait
