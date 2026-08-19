import numpy as np
from scipy import sparse

from fleet_sim.experiments.stage2_cycle6 import (
    _nh2_structures,
    _nh4_specs,
    _pava_fit,
    _pava_predict,
    temporal_geometric_radius,
    temporal_linear_propagator_growth,
)


def test_cycle6_temporal_geometric_radius_respects_endpoints():
    assert np.isclose(temporal_geometric_radius(2.0, 0.5, 50, 50), 2.0)
    assert np.isclose(temporal_geometric_radius(2.0, 0.5, 0, 50), 0.5)
    assert np.isclose(temporal_geometric_radius(4.0, 1.0, 25, 50), 2.0)


def test_cycle6_temporal_propagator_growth_decreases_after_response():
    pre = sparse.csr_matrix([[0.0, 0.8], [0.8, 0.0]])
    post = sparse.csr_matrix([[0.0, 0.1], [0.1, 0.0]])
    recovery = np.array([0.3, 0.3])
    early = temporal_linear_propagator_growth(
        pre, post, recovery, intervention_time=5, horizon=40
    )
    late = temporal_linear_propagator_growth(
        pre, post, recovery, intervention_time=35, horizon=40
    )
    assert early < late


def test_cycle6_pava_is_monotone_and_bounded():
    x = np.array([0, 1, 2, 3, 4], dtype=float)
    y = np.array([0.0, 0.8, 0.4, 1.0, 0.9])
    fit_x, fit_y = _pava_fit(x, y)
    prediction = _pava_predict(np.linspace(-1, 5, 30), fit_x, fit_y)
    assert np.all(np.diff(prediction) >= -1e-12)
    assert np.all((prediction >= 0.0) & (prediction <= 1.0))


def test_cycle6_nh2_train_and_test_structures_are_disjoint():
    train = set(_nh2_structures(training=True))
    test = set(_nh2_structures(training=False))
    assert len(train) == 8
    assert len(test) == 8
    assert train.isdisjoint(test)


def test_cycle6_nh4_matrix_is_boundary_spanning_and_disjoint():
    specs = _nh4_specs()
    train = [row for row in specs if row["split"] == "train"]
    test = [row for row in specs if row["split"] == "test"]
    assert len(train) == 168
    assert len(test) == 112
    assert {row["nf"] for row in train} == {2000, 5000}
    assert {row["nf"] for row in test} == {10000, 20000}
    assert {row["profile"] for row in train}.isdisjoint(
        {row["profile"] for row in test}
    )
    targets = {row["target_omega"] for row in specs}
    assert targets == {0.30, 0.55, 0.80, 1.00, 1.25, 1.60, 2.20}


def test_cycle6_temporal_propagator_matches_exact_dense_product():
    pre_dense = np.array([[0.0, 0.30], [0.20, 0.0]])
    post_dense = np.array([[0.0, 0.05], [0.10, 0.0]])
    recovery = np.array([0.20, 0.40])
    intervention_time = 3
    horizon = 7
    pre_step = np.diag(np.exp(-recovery)) + pre_dense.T
    post_step = np.diag(np.exp(-recovery)) + post_dense.T
    propagator = (
        np.linalg.matrix_power(post_step, horizon - intervention_time)
        @ np.linalg.matrix_power(pre_step, intervention_time)
    )
    exact = float(np.max(np.abs(np.linalg.eigvals(propagator))) ** (1.0 / horizon))
    estimated = temporal_linear_propagator_growth(
        sparse.csr_matrix(pre_dense),
        sparse.csr_matrix(post_dense),
        recovery,
        intervention_time=intervention_time,
        horizon=horizon,
        max_iterations=200,
        tolerance=1e-12,
    )
    assert np.isclose(estimated, exact, rtol=1e-10, atol=1e-12)


def test_cycle6_fast_fluid_solver_matches_full_reflected_queue():
    from fleet_sim.analysis.admission_stability import (
        build_resource_regime,
        fluid_admission_metrics,
    )
    from fleet_sim.experiments.stage2_cycle6 import (
        _admission_trajectory,
        _fast_fluid_scores,
    )

    resources = build_resource_regime(10_000, "supervision_constrained")
    trajectory = _admission_trajectory(
        "exponential", n0=500, nf=10_000, duration=137.5
    )
    full, _ = fluid_admission_metrics(trajectory, resources)
    peak_lambda, omega = _fast_fluid_scores(
        profile="exponential",
        n0=500,
        nf=10_000,
        duration=137.5,
        resources=resources,
    )
    assert np.isclose(peak_lambda, full.peak_lambda, rtol=0.0, atol=1e-12)
    assert np.isclose(omega, full.omega, rtol=0.0, atol=1e-10)


def test_cycle6_duration_solver_targets_declared_boundary_grid():
    specs = _nh4_specs()
    maximum_error = max(
        abs(float(row["omega"]) - float(row["target_omega"])) for row in specs
    )
    assert maximum_error < 0.08
