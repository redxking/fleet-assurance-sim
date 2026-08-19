"""Physical latency, timing uncertainty, and thermodynamic floors."""

from __future__ import annotations

import math

SPEED_OF_LIGHT_M_S = 299_792_458.0
BOLTZMANN_J_K = 1.380649e-23


def fiber_propagation_delay(distance_km: float, refractive_index: float = 1.47) -> float:
    if distance_km < 0 or refractive_index <= 1:
        raise ValueError("invalid distance or refractive index")
    velocity = SPEED_OF_LIGHT_M_S / refractive_index
    return distance_km * 1_000.0 / velocity


def landauer_energy_per_bit(temperature_k: float = 300.0) -> float:
    if temperature_k <= 0:
        raise ValueError("temperature must be positive")
    return BOLTZMANN_J_K * temperature_k * math.log(2.0)


def landauer_energy(bit_count: float, temperature_k: float = 300.0) -> float:
    if bit_count < 0:
        raise ValueError("bit_count must be nonnegative")
    return bit_count * landauer_energy_per_bit(temperature_k)


def holdover_uncertainty(
    elapsed_s: float,
    initial_uncertainty_s: float,
    fractional_frequency_error: float,
    *,
    temperature_error_s: float = 0.0,
    aging_error_s: float = 0.0,
    model_error_s: float = 0.0,
) -> float:
    if min(elapsed_s, initial_uncertainty_s, fractional_frequency_error) < 0:
        raise ValueError("holdover parameters must be nonnegative")
    return (
        initial_uncertainty_s
        + abs(fractional_frequency_error) * elapsed_s
        + abs(temperature_error_s)
        + abs(aging_error_s)
        + abs(model_error_s)
    )


def ordered_operation_latency(
    network_s: float,
    service_s: float,
    consensus_s: float,
    uncertainty_s: float,
    commit_wait_factor: float = 2.0,
) -> float:
    values = (network_s, service_s, consensus_s, uncertainty_s, commit_wait_factor)
    if any(value < 0 for value in values):
        raise ValueError("latency components must be nonnegative")
    return network_s + service_s + consensus_s + commit_wait_factor * uncertainty_s


def ordered_operation_throughput(
    lanes: int,
    network_s: float,
    service_s: float,
    consensus_s: float,
    uncertainty_s: float,
    commit_wait_factor: float = 2.0,
) -> float:
    if lanes < 1:
        raise ValueError("lanes must be positive")
    latency = ordered_operation_latency(
        network_s, service_s, consensus_s, uncertainty_s, commit_wait_factor
    )
    return float("inf") if latency == 0 else lanes / latency
