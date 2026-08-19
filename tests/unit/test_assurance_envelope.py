from __future__ import annotations

import math

from fleet_sim.analysis.assurance_envelope import (
    build_candidate_envelope,
    containment_race_ratio,
    safe_population_growth_rate,
)


def test_candidate_envelope_identifies_binding_constraint() -> None:
    result = build_candidate_envelope(
        control_plane_utilization=0.50,
        max_control_plane_utilization=0.70,
        epidemic_gain=0.40,
        max_epidemic_gain=1.0,
        observability_demand_bps=80.0,
        observability_capacity_bps=100.0,
        supervisory_utilization=0.60,
        max_supervisory_utilization=0.70,
        revocation_latency_s=8.0,
        max_revocation_latency_s=10.0,
        timing_uncertainty_s=0.2,
        max_timing_uncertainty_s=1.0,
        useful_throughput_per_s=101.0,
        min_useful_throughput_per_s=100.0,
    )
    assert result.admissible
    assert result.binding_constraint == "mission_throughput"
    assert math.isclose(result.minimum_margin, 0.01)


def test_candidate_envelope_fails_when_one_constraint_crosses_boundary() -> None:
    result = build_candidate_envelope(
        control_plane_utilization=0.71,
        max_control_plane_utilization=0.70,
        epidemic_gain=0.40,
        max_epidemic_gain=1.0,
        observability_demand_bps=80.0,
        observability_capacity_bps=100.0,
        supervisory_utilization=0.60,
        max_supervisory_utilization=0.70,
        revocation_latency_s=8.0,
        max_revocation_latency_s=10.0,
        timing_uncertainty_s=0.2,
        max_timing_uncertainty_s=1.0,
        useful_throughput_per_s=110.0,
        min_useful_throughput_per_s=100.0,
    )
    assert not result.admissible
    assert result.binding_constraint == "control_plane"
    assert result.minimum_margin < 0


def test_containment_race_and_population_velocity_constructs() -> None:
    assert containment_race_ratio(3.0, 6.0) == 0.5
    rate = safe_population_growth_rate(
        supervisory_service_capacity_per_s=100.0,
        baseline_alert_rate_per_agent_hz=0.01,
        hazard_alert_rate_per_new_agent_hz=0.10,
        settling_time_s=10.0,
        current_agents=2_000,
        utilization_target=0.70,
    )
    assert math.isclose(rate, 50.0)
