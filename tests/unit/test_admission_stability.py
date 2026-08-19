import numpy as np

from fleet_sim.analysis.admission_stability import (
    build_resource_regime,
    critical_linear_admission_rate,
    fluid_admission_metrics,
    make_admission_trajectory,
    simulate_stochastic_admission_batch,
)


def test_fluid_backlog_zero_at_critical_or_slower_linear_rate():
    nf = 5000
    n0 = 100
    resources = build_resource_regime(nf, "balanced")
    rate = critical_linear_admission_rate(resources, nf)
    duration = (nf - n0) / rate * 1.05
    trajectory = make_admission_trajectory(
        "linear", n0=n0, nf=nf, ramp_duration_s=duration, dt=0.5
    )
    predictors, _ = fluid_admission_metrics(trajectory, resources)
    assert predictors.peak_lambda <= 1.01
    assert predictors.omega < 1e-9


def test_fast_linear_admission_creates_positive_overload_index():
    nf = 5000
    n0 = 100
    resources = build_resource_regime(nf, "control_constrained")
    rate = critical_linear_admission_rate(resources, nf)
    duration = (nf - n0) / rate * 0.25
    trajectory = make_admission_trajectory(
        "linear", n0=n0, nf=nf, ramp_duration_s=duration, dt=0.5
    )
    predictors, _ = fluid_admission_metrics(trajectory, resources)
    assert predictors.peak_lambda > 1.0
    assert predictors.omega > 0.0


def test_admission_batch_is_seed_reproducible():
    resources = build_resource_regime(2000, "balanced")
    trajectory = make_admission_trajectory(
        "smooth", n0=100, nf=2000, ramp_duration_s=80.0, dt=1.0
    )
    first = simulate_stochastic_admission_batch(
        trajectory, resources, replication_seeds=[21, 22, 23]
    )
    second = simulate_stochastic_admission_batch(
        trajectory, resources, replication_seeds=[21, 22, 23]
    )
    assert np.array_equal(first.boundary_crossed, second.boundary_crossed)
    assert np.allclose(first.maximum_normalized_queue, second.maximum_normalized_queue)
