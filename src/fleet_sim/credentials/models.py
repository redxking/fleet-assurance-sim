"""Credential and key-management economics."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IssuerSizing:
    steady_state_rate_per_s: float
    burst_rate_per_s: float
    required_capacity_per_s: int
    headroom_factor: float


def pairwise_key_count(n: int) -> int:
    if n < 0:
        raise ValueError("n must be nonnegative")
    return n * (n - 1) // 2


def certificate_issuance_rate(n: int, ttl_s: float) -> float:
    if n < 0 or ttl_s <= 0:
        raise ValueError("invalid certificate parameters")
    return n / ttl_s


def logical_key_hierarchy_rekey_operations(n: int, span: int = 2) -> int:
    if n < 1 or span < 2:
        raise ValueError("invalid logical key hierarchy parameters")
    return 0 if n == 1 else math.ceil(math.log(n, span))


def size_issuer(
    n: int,
    ttl_s: float,
    *,
    burst_factor: float = 3.0,
    retry_factor: float = 1.10,
    headroom_factor: float = 1.30,
) -> IssuerSizing:
    if min(burst_factor, retry_factor, headroom_factor) < 1.0:
        raise ValueError("factors must be at least 1")
    steady = certificate_issuance_rate(n, ttl_s)
    burst = steady * burst_factor * retry_factor
    required = math.ceil(burst * headroom_factor)
    return IssuerSizing(steady, burst, required, headroom_factor)


def mass_revocation_recovery_time(
    revoked_agents: int,
    issuer_capacity_per_s: float,
    propagation_latency_s: float,
    relying_party_updates: int = 1,
) -> float:
    if revoked_agents < 0 or issuer_capacity_per_s <= 0 or propagation_latency_s < 0:
        raise ValueError("invalid revocation parameters")
    return revoked_agents * max(1, relying_party_updates) / issuer_capacity_per_s + propagation_latency_s
