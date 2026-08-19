from __future__ import annotations

import math

from fleet_sim.credentials import certificate_issuance_rate, pairwise_key_count, size_issuer
from fleet_sim.telemetry import gaussian_rate_distortion, hierarchical_telemetry
from fleet_sim.timing import fiber_propagation_delay, holdover_uncertainty, landauer_energy_per_bit


def test_physical_limits_and_holdover() -> None:
    one_way = fiber_propagation_delay(4_500.0, 1.47)
    assert 0.021 < one_way < 0.023
    assert math.isclose(
        holdover_uncertainty(100.0, 1e-6, 1e-9),
        1.1e-6,
        rel_tol=1e-12,
    )
    assert 2.8e-21 < landauer_energy_per_bit(300.0) < 2.9e-21


def test_credential_economics() -> None:
    assert pairwise_key_count(10_000) == 49_995_000
    assert math.isclose(certificate_issuance_rate(10_000, 300.0), 10000 / 300)
    assert size_issuer(10_000, 300.0).required_capacity_per_s >= 143


def test_hierarchical_telemetry_reduces_apex_rate() -> None:
    result = hierarchical_telemetry(10_000, 2_000.0, span=8, compression_ratio=0.35)
    assert result.depth == 5
    assert result.apex_rate_bps < result.raw_rate_bps
    assert gaussian_rate_distortion(1.0, 0.25) == 1.0
