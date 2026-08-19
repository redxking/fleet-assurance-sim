"""Credential issuance and revocation capacity models."""

from __future__ import annotations

import math


def pairwise_key_count(n_agents: int) -> int:
    if n_agents < 0:
        raise ValueError("n_agents cannot be negative")
    return n_agents * (n_agents - 1) // 2


def steady_state_certificate_issuance_rate(n_agents: int, ttl_seconds: float) -> float:
    if n_agents < 0 or ttl_seconds <= 0:
        raise ValueError("invalid credential parameters")
    return n_agents / ttl_seconds


def mass_revocation_recovery_time(
    revoked_agents: int,
    replacement_credentials_per_second: float,
    baseline_issuance_per_second: float = 0.0,
) -> float:
    if revoked_agents < 0 or replacement_credentials_per_second <= baseline_issuance_per_second:
        raise ValueError("issuer must have positive headroom")
    return revoked_agents / (replacement_credentials_per_second - baseline_issuance_per_second)


def logical_key_hierarchy_rekey_operations(n_agents: int, branch_factor: int = 2) -> int:
    if n_agents < 1 or branch_factor < 2:
        raise ValueError("invalid logical key hierarchy parameters")
    return math.ceil(math.log(n_agents, branch_factor))
