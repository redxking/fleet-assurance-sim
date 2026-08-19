from __future__ import annotations

import pandas as pd

from fleet_sim.analysis.admission_predictors import project_admission_predictors
from fleet_sim.control_plane.resource_network import (
    AdmissionPattern,
    OperationalFailureCriteria,
    ResourceType,
    default_assurance_resources,
    make_admission_trajectory,
    simulate_resource_network,
)


def test_default_resource_model_exposes_all_ten_required_resources() -> None:
    resources = default_assurance_resources(10_000)
    assert len(resources) == 10
    assert {resource.resource_type for resource in resources} == set(ResourceType)
    assert all(resource.measurement_provenance for resource in resources)


def test_every_required_profile_and_disturbance_reaches_requested_population() -> None:
    for pattern in AdmissionPattern:
        trajectory = make_admission_trajectory(
            pattern,
            initial_n=10,
            final_n=100,
            admission_duration_s=20.0,
            recovery_window_s=10.0,
            dt_s=1.0,
        )
        assert int(trajectory.requested_admissions.sum()) == 90
        assert int(trajectory.fleet_size_if_unconstrained[-1]) == 100
        if pattern == AdmissionPattern.SYBIL:
            assert trajectory.sybil_attempts.sum() > 0
        if pattern == AdmissionPattern.MASS_RESTART:
            assert trajectory.restart_agents.sum() > 0
        if pattern == AdmissionPattern.MASS_RENEWAL:
            assert trajectory.renewal_agents.sum() > 0


def test_linear_admission_does_not_front_load_integer_rounding() -> None:
    trajectory = make_admission_trajectory(
        AdmissionPattern.LINEAR,
        initial_n=10,
        final_n=100,
        admission_duration_s=180.0,
        recovery_window_s=0.0,
        dt_s=1.0,
    )
    first_half = trajectory.requested_admissions[:90]
    second_half = trajectory.requested_admissions[90:180]
    assert int(first_half.sum()) == 45
    assert int(second_half.sum()) == 45


def test_projected_omega_is_ex_ante_and_operational_failure_is_independent() -> None:
    trajectory = make_admission_trajectory(
        AdmissionPattern.BURSTY,
        initial_n=100,
        final_n=1_000,
        admission_duration_s=60.0,
        recovery_window_s=30.0,
        dt_s=1.0,
    )
    resources = default_assurance_resources(1_000)
    projection = project_admission_predictors(trajectory, resources)
    first = simulate_resource_network(trajectory, resources, seed=9001)
    second = simulate_resource_network(trajectory, resources, seed=9001)
    assert projection.predictors.omega_a >= 0.0
    assert projection.predictors.final_fleet_size == 1_000
    assert first.summary["operational_failure_definition_uses_omega"] is False
    pd.testing.assert_frame_equal(first.resource_trace, second.resource_trace)
    pd.testing.assert_frame_equal(first.admission_trace, second.admission_trace)
    assert first.summary == second.summary


def test_equal_final_population_profiles_create_distinct_projected_boundaries() -> None:
    resources = default_assurance_resources(1_000)
    linear = make_admission_trajectory(
        AdmissionPattern.LINEAR,
        initial_n=100,
        final_n=1_000,
        admission_duration_s=180.0,
        recovery_window_s=120.0,
    )
    step = make_admission_trajectory(
        AdmissionPattern.STEP,
        initial_n=100,
        final_n=1_000,
        admission_duration_s=180.0,
        recovery_window_s=120.0,
    )
    linear_omega = project_admission_predictors(linear, resources).predictors.omega_a
    step_omega = project_admission_predictors(step, resources).predictors.omega_a
    assert linear_omega < 1.0
    assert step_omega > 1.0


def test_boundary_crossing_does_not_directly_define_operational_failure() -> None:
    trajectory = make_admission_trajectory(
        AdmissionPattern.STEP,
        initial_n=10,
        final_n=100,
        admission_duration_s=180.0,
        recovery_window_s=120.0,
    )
    criteria = OperationalFailureCriteria(
        maximum_deadline_miss_fraction=1.0,
        maximum_shed_fraction=1.0,
        maximum_incomplete_exposure_per_agent_s=1e9,
        minimum_useful_throughput_ratio=0.0,
        require_recovery=False,
    )
    result = simulate_resource_network(
        trajectory,
        default_assurance_resources(100),
        seed=42,
        failure_criteria=criteria,
    )
    assert result.summary["assurance_boundary_crossed"] == 1
    assert result.summary["operational_failure"] == 0


def test_n10000_resource_state_is_population_independent_in_size() -> None:
    trajectory = make_admission_trajectory(
        AdmissionPattern.LINEAR,
        initial_n=1_000,
        final_n=10_000,
        admission_duration_s=10.0,
        recovery_window_s=5.0,
        dt_s=1.0,
    )
    result = simulate_resource_network(
        trajectory,
        default_assurance_resources(10_000),
        seed=42,
    )
    assert len(result.resource_trace) == len(trajectory.time_s) * len(ResourceType)
    assert len(result.admission_trace) == len(trajectory.time_s)
