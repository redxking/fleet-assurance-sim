"""Credential issuance and revocation economics."""

from __future__ import annotations

import math


def pairwise_key_count(n: int) -> int:
    if n < 0:
        raise ValueError("n must be nonnegative")
    return math.comb(n, 2)


def steady_state_certificate_rate(n: int, ttl_s: float) -> float:
    if n < 0 or ttl_s <= 0.0:
        raise ValueError("invalid n or ttl")
    return n / ttl_s


def credential_capacity_required(
    n: int,
    ttl_s: float,
    renewal_burst_factor: float = 1.0,
    retry_factor: float = 1.0,
    headroom_factor: float = 1.25,
) -> float:
    factors = [renewal_burst_factor, retry_factor, headroom_factor]
    if any(value < 1.0 for value in factors):
        raise ValueError("capacity factors must be at least one")
    return steady_state_certificate_rate(n, ttl_s) * math.prod(factors)


def revocation_recovery_time(revoked_agents: int, issuance_capacity_per_s: float) -> float:
    if revoked_agents < 0 or issuance_capacity_per_s <= 0.0:
        raise ValueError("invalid revocation parameters")
    return revoked_agents / issuance_capacity_per_s
