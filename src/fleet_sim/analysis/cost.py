"""Transparent notional practical cost and energy model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CostRates:
    compute_per_agent_second_usd: float = 2.0e-6
    network_per_gb_usd: float = 0.02
    storage_per_gb_month_usd: float = 0.02
    crypto_operation_usd: float = 1.0e-8
    supervisor_hour_usd: float = 120.0
    compute_watts_per_agent: float = 15.0
    network_joule_per_bit: float = 1.0e-8
    provenance: str = "notional"


def practical_cost_per_useful_task(
    *,
    useful_tasks: int,
    duration_s: float,
    n_agents: int,
    bytes_transmitted: float,
    bytes_stored: float,
    crypto_operations: float,
    supervisor_seconds: float,
    rates: CostRates = CostRates(),
) -> float:
    if useful_tasks <= 0:
        return float("inf")
    compute = n_agents * duration_s * rates.compute_per_agent_second_usd
    network = bytes_transmitted / 1e9 * rates.network_per_gb_usd
    storage = bytes_stored / 1e9 * rates.storage_per_gb_month_usd * (duration_s / (30 * 86400))
    crypto = crypto_operations * rates.crypto_operation_usd
    labor = supervisor_seconds / 3600 * rates.supervisor_hour_usd
    return (compute + network + storage + crypto + labor) / useful_tasks


def practical_energy_per_useful_task(
    *,
    useful_tasks: int,
    duration_s: float,
    n_agents: int,
    bits_transmitted: float,
    rates: CostRates = CostRates(),
) -> float:
    if useful_tasks <= 0:
        return float("inf")
    compute_joules = n_agents * rates.compute_watts_per_agent * duration_s
    network_joules = bits_transmitted * rates.network_joule_per_bit
    return (compute_joules + network_joules) / useful_tasks
