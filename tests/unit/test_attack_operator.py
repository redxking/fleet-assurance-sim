import networkx as nx
import numpy as np
from scipy import sparse

from fleet_sim.security.attack_operator import (
    dynamic_operator_metrics,
    next_generation_matrix,
    nonnegative_spectral_radius,
    simulate_directed_sir_batch,
    weighted_nonbacktracking_radius,
)


def test_directed_chain_next_generation_radius_is_zero():
    h = sparse.csr_matrix(np.array([[0.0, 0.2, 0.0], [0.0, 0.0, 0.2], [0.0, 0.0, 0.0]]))
    k = next_generation_matrix(h, np.array([0.2, 0.2, 0.2]))
    assert nonnegative_spectral_radius(k) == 0.0


def test_directed_cycle_next_generation_radius_matches_ratio():
    h = sparse.csr_matrix(np.array([[0.0, 0.2], [0.2, 0.0]]))
    k = next_generation_matrix(h, np.array([0.4, 0.4]))
    assert np.isclose(nonnegative_spectral_radius(k), 0.5, rtol=1e-6)


def test_dynamic_intervention_reduces_operator_metrics():
    pre = sparse.csr_matrix(np.array([[0.0, 0.4], [0.4, 0.0]]))
    post = pre * 0.25
    metrics = dynamic_operator_metrics(
        pre,
        post,
        np.array([0.2, 0.2]),
        intervention_time=5,
        horizon=20,
    )
    assert metrics["candidate_rho_pre"] > metrics["candidate_rho_post"]
    assert metrics["dynamic_excess_exposure"] > 0.0


def test_batched_sir_is_seed_reproducible():
    h = sparse.csr_matrix(np.array([[0.0, 0.3], [0.3, 0.0]]))
    kwargs = dict(
        true_pre=h,
        true_post=h * 0.5,
        recovery_true=np.array([0.2, 0.2]),
        intervention_time=4,
        horizon_steps=12,
        replication_seeds=[11, 12, 13],
    )
    first = simulate_directed_sir_batch(**kwargs)
    second = simulate_directed_sir_batch(**kwargs)
    assert np.array_equal(first.ever_fraction, second.ever_fraction)
    assert np.array_equal(first.duration_steps, second.duration_steps)


def test_nonbacktracking_radius_zero_without_nonbacktracking_walk():
    h = sparse.csr_matrix(np.array([[0.0, 0.2], [0.2, 0.0]]))
    assert weighted_nonbacktracking_radius(h, np.array([0.2, 0.2])) == 0.0


def test_sparse_power_radius_matches_dense_reference() -> None:
    rng = np.random.default_rng(812)
    dense = rng.random((90, 90))
    dense[dense < 0.94] = 0.0
    matrix = sparse.csr_matrix(dense)
    observed = nonnegative_spectral_radius(matrix)
    expected = float(np.max(np.abs(np.linalg.eigvals(dense))))
    assert np.isclose(observed, expected, rtol=2e-5, atol=2e-7)


def test_operator_cache_does_not_change_radius() -> None:
    from fleet_sim.security.attack_operator import clear_operator_caches

    matrix = sparse.csr_matrix(np.array([[0.0, 0.4], [0.2, 0.0]]))
    clear_operator_caches()
    first = nonnegative_spectral_radius(matrix)
    second = nonnegative_spectral_radius(matrix.copy())
    assert first == second
