import numpy as np
from scipy import sparse

from fleet_sim.security.attack_trace import LAYER_NAMES, ObservedSystemView
from fleet_sim.security.dynamic_message_passing import DMPConfig, dynamic_message_passing


def _view(
    n: int,
    communication: sparse.csr_matrix,
    *,
    seed: np.ndarray,
    common_cause: np.ndarray | None = None,
    horizon: int = 4,
) -> ObservedSystemView:
    layers = {name: sparse.csr_matrix((n, n), dtype=float) for name in LAYER_NAMES}
    layers["communication"] = communication
    zeros = np.zeros(n)
    return ObservedSystemView(
        n=n,
        layers=layers,
        susceptibility=np.ones(n),
        exploitability=np.ones(n),
        detection_rate=zeros,
        quarantine_rate=zeros,
        revocation_rate=zeros,
        recovery_rate=zeros,
        initial_compromise_probability=seed,
        common_cause_vector=zeros if common_cause is None else common_cause,
        segment_ids=np.zeros(n, dtype=int),
        defense_profile=np.ones(horizon),
        detection_profile=np.ones(horizon),
        cross_segment_availability=np.ones(horizon),
        boundary_multiplier=np.ones(horizon),
    )


def _communication_only(horizon: int) -> DMPConfig:
    return DMPConfig(
        horizon_steps=horizon,
        base_transmission_intensity=20.0,
        layer_weights={name: float(name == "communication") for name in LAYER_NAMES},
    )


def test_dmp_respects_edge_direction_and_retains_node_and_edge_state():
    edge_forward = sparse.csr_matrix(([1.0], ([0], [1])), shape=(3, 3))
    forward = dynamic_message_passing(
        _view(3, edge_forward, seed=np.array([1.0, 0.0, 0.0]), horizon=1),
        _communication_only(1),
    )
    assert forward.final_ever_compromised_probability[1] > 0.99
    assert forward.final_ever_compromised_probability[2] == 0.0
    assert len(forward.states[-1].edge_no_transmission) == 1
    total = sum(
        getattr(forward.states[-1], name)
        for name in (
            "node_susceptible",
            "node_compromised_undetected",
            "node_detected",
            "node_quarantined",
            "node_revoked",
            "node_recovered",
        )
    )
    assert np.allclose(total, 1.0)

    edge_reverse = sparse.csr_matrix(([1.0], ([1], [0])), shape=(3, 3))
    reverse = dynamic_message_passing(
        _view(3, edge_reverse, seed=np.array([1.0, 0.0, 0.0]), horizon=1),
        _communication_only(1),
    )
    assert reverse.final_ever_compromised_probability[1] == 0.0


def test_dmp_common_cause_vector_is_exogenous_not_an_edge():
    view = _view(
        3,
        sparse.csr_matrix((3, 3), dtype=float),
        seed=np.zeros(3),
        common_cause=np.array([0.0, 0.0, 0.60]),
        horizon=4,
    )
    result = dynamic_message_passing(view, _communication_only(4))
    assert result.operator.matrix.nnz == 0
    assert np.isclose(result.final_ever_compromised_probability[2], 0.60)
    assert np.allclose(result.final_ever_compromised_probability[:2], 0.0)


def test_sparse_dmp_handles_ten_thousand_nodes_without_dense_graph_state():
    n = 10_000
    sources = np.arange(n, dtype=np.int64)
    targets = (sources + 1) % n
    ring = sparse.csr_matrix((np.ones(n), (sources, targets)), shape=(n, n))
    seed = np.zeros(n)
    seed[0] = 1.0
    result = dynamic_message_passing(
        _view(n, ring, seed=seed, horizon=2),
        _communication_only(2),
    )
    assert sparse.isspmatrix_csr(result.operator.matrix)
    assert result.operator.matrix.nnz == n
    assert result.states[-1].edge_no_transmission.shape == (n,)
    assert result.final_ever_compromised_probability.shape == (n,)
