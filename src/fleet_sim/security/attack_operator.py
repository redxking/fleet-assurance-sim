"""Directed multilayer compromise operators and stochastic propagation.

The functions in this module support model-conditioned research. They do not
claim that the layer weights or transition intensities are measured properties
of a deployed system.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp
import hashlib
from typing import Mapping, Sequence

import networkx as nx
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import eigs


_SPECTRAL_RADIUS_CACHE: dict[bytes, float] = {}
_NONBACKTRACKING_RADIUS_CACHE: dict[bytes, float] = {}
_CACHE_LIMIT = 50_000


def _sparse_fingerprint(matrix: sparse.spmatrix, *extra: bytes) -> bytes:
    mat = sparse.csr_matrix(matrix, dtype=float)
    digest = hashlib.blake2b(digest_size=20)
    digest.update(np.asarray(mat.shape, dtype=np.int64).tobytes())
    digest.update(mat.indptr.tobytes())
    digest.update(mat.indices.tobytes())
    digest.update(mat.data.tobytes())
    for item in extra:
        digest.update(item)
    return digest.digest()


def clear_operator_caches() -> None:
    """Clear deterministic spectral caches between independent study processes."""
    _SPECTRAL_RADIUS_CACHE.clear()
    _NONBACKTRACKING_RADIUS_CACHE.clear()


@dataclass(frozen=True)
class NodeRiskState:
    """True and observable node-level security attributes."""

    privilege_true: np.ndarray
    susceptibility_true: np.ndarray
    recovery_true: np.ndarray
    privilege_observed: np.ndarray
    susceptibility_observed: np.ndarray
    recovery_observed: np.ndarray
    image_family: np.ndarray
    image_risk: np.ndarray


@dataclass(frozen=True)
class HazardOperators:
    """True and candidate directed transmission operators."""

    true_pre: sparse.csr_matrix
    true_post: sparse.csr_matrix
    candidate_pre: sparse.csr_matrix
    candidate_post: sparse.csr_matrix
    layer_candidate_pre: Mapping[str, sparse.csr_matrix]
    node_state: NodeRiskState


@dataclass(frozen=True)
class PropagationBatch:
    """Replication-level outcomes for a directed SIR batch."""

    peak_fraction: np.ndarray
    ever_fraction: np.ndarray
    duration_steps: np.ndarray
    replication_seeds: np.ndarray


def nonnegative_spectral_radius(matrix: sparse.spmatrix | np.ndarray) -> float:
    """Return the Perron root of a nonnegative square matrix.

    Small matrices use dense eigendecomposition. Larger sparse matrices use
    ARPACK with a fixed positive start vector for deterministic execution in a
    fixed environment. A bounded shifted power iteration is the deterministic
    fallback for reducible or ill-conditioned operators.
    """
    if matrix.shape[0] == 0:
        return 0.0
    if sparse.issparse(matrix):
        mat = sparse.csr_matrix(matrix, dtype=float)
        if mat.nnz == 0:
            return 0.0
        key = _sparse_fingerprint(mat, b"perron-v2")
        cached = _SPECTRAL_RADIUS_CACHE.get(key)
        if cached is not None:
            return cached
        n = mat.shape[0]
        if mat.shape[1] != n:
            raise ValueError("matrix must be square")
        if n <= 64:
            vals = np.linalg.eigvals(mat.toarray())
            result = float(np.max(np.abs(vals)))
            _SPECTRAL_RADIUS_CACHE[key] = result
            return result
        v0 = np.full(n, 1.0 / np.sqrt(n), dtype=float)
        try:
            value = eigs(
                mat,
                k=1,
                which="LM",
                v0=v0,
                return_eigenvectors=False,
                tol=1e-7,
                maxiter=800,
            )[0]
            result = float(abs(value))
            if len(_SPECTRAL_RADIUS_CACHE) >= _CACHE_LIMIT:
                _SPECTRAL_RADIUS_CACHE.clear()
            _SPECTRAL_RADIUS_CACHE[key] = result
            return result
        except Exception:
            shift = max(1e-6, 0.25 * float(np.max(np.asarray(mat.sum(axis=1)).reshape(-1))))
            x = np.full(n, 1.0 / n, dtype=float)
            previous = -1.0
            radius = 0.0
            for _ in range(250):
                y = np.asarray(mat @ x).reshape(-1) + shift * x
                growth = float(np.sum(y))
                if growth <= 0.0 or not np.isfinite(growth):
                    return 0.0
                x = y / growth
                radius = max(0.0, growth - shift)
                if previous >= 0.0 and abs(radius - previous) <= 1e-8 * max(1.0, radius):
                    break
                previous = radius
            result = float(radius)
            if len(_SPECTRAL_RADIUS_CACHE) >= _CACHE_LIMIT:
                _SPECTRAL_RADIUS_CACHE.clear()
            _SPECTRAL_RADIUS_CACHE[key] = result
            return result
    dense = np.asarray(matrix, dtype=float)
    if dense.shape[0] != dense.shape[1]:
        raise ValueError("matrix must be square")
    vals = np.linalg.eigvals(dense)
    return float(np.max(np.abs(vals))) if len(vals) else 0.0


def make_node_risk_state(n: int, *, seed: int, image_families: int | None = None) -> NodeRiskState:
    """Generate correlated, notional node risk and noisy observable estimates."""
    if n < 1:
        raise ValueError("n must be positive")
    rng = np.random.default_rng(seed)
    families = image_families or max(4, int(round(np.sqrt(n) / 2)))
    image_family = rng.integers(0, families, size=n, dtype=np.int64)
    family_risk = np.clip(rng.lognormal(mean=-0.04, sigma=0.22, size=families), 0.55, 1.75)
    image_risk = family_risk[image_family]

    privilege_true = np.clip(rng.lognormal(mean=-0.04, sigma=0.28, size=n), 0.45, 1.95)
    susceptibility_true = np.clip(
        rng.lognormal(mean=-0.08, sigma=0.25, size=n) * image_risk,
        0.40,
        2.20,
    )
    recovery_true = np.clip(rng.lognormal(mean=np.log(0.30), sigma=0.24, size=n), 0.12, 0.65)

    privilege_observed = np.clip(privilege_true * rng.lognormal(0.0, 0.12, size=n), 0.35, 2.30)
    susceptibility_observed = np.clip(
        susceptibility_true * rng.lognormal(0.0, 0.14, size=n), 0.30, 2.50
    )
    recovery_observed = np.clip(recovery_true * rng.lognormal(0.0, 0.16, size=n), 0.09, 0.80)
    return NodeRiskState(
        privilege_true=privilege_true,
        susceptibility_true=susceptibility_true,
        recovery_true=recovery_true,
        privilege_observed=privilege_observed,
        susceptibility_observed=susceptibility_observed,
        recovery_observed=recovery_observed,
        image_family=image_family,
        image_risk=image_risk,
    )


def orient_undirected_layer(
    graph: nx.Graph,
    *,
    seed: int,
    node_score: np.ndarray,
    prefer_high_to_low: bool,
    reverse_probability: float,
    bidirectional_probability: float,
) -> nx.DiGraph:
    """Convert an undirected layer into a directed layer with asymmetric reachability."""
    if not 0.0 <= reverse_probability <= 1.0:
        raise ValueError("reverse_probability must be in [0, 1]")
    if not 0.0 <= bidirectional_probability <= 1.0:
        raise ValueError("bidirectional_probability must be in [0, 1]")
    rng = np.random.default_rng(seed)
    directed = nx.DiGraph()
    directed.add_nodes_from(graph.nodes())
    for u, v in graph.edges():
        su = float(node_score[int(u)])
        sv = float(node_score[int(v)])
        if su == sv:
            primary = (u, v) if rng.random() < 0.5 else (v, u)
        elif prefer_high_to_low:
            primary = (u, v) if su > sv else (v, u)
        else:
            primary = (u, v) if su < sv else (v, u)
        if rng.random() < reverse_probability:
            primary = (primary[1], primary[0])
        directed.add_edge(*primary)
        if rng.random() < bidirectional_probability:
            directed.add_edge(primary[1], primary[0])
    return directed


def _layer_edge_set(graph: nx.DiGraph) -> set[tuple[int, int]]:
    return {(int(u), int(v)) for u, v in graph.edges()}


def build_hazard_operators(
    layers: Mapping[str, nx.DiGraph],
    node_state: NodeRiskState,
    *,
    seed: int,
    beta_scale: float,
    intervention_strength: float,
    true_layer_weights: Mapping[str, float] | None = None,
    candidate_layer_weights: Mapping[str, float] | None = None,
    true_interaction_strength: float = 0.45,
    latent_edge_sigma: float = 0.22,
) -> HazardOperators:
    """Build true and candidate pre and post intervention hazard matrices.

    Matrices use the orientation row=source, column=target. The true matrices
    include latent edge variation and a multiplicative authorization-dependency
    interaction. The candidate matrices use noisy observable node state and an
    additive layer model.
    """
    if beta_scale <= 0.0:
        raise ValueError("beta_scale must be positive")
    if not 0.0 <= intervention_strength <= 1.0:
        raise ValueError("intervention_strength must be in [0, 1]")
    true_weights = dict(
        true_layer_weights
        or {"authorization": 0.54, "communication": 0.10, "dependency": 0.27, "supervision": 0.09}
    )
    candidate_weights = dict(
        candidate_layer_weights
        or {"authorization": 0.50, "communication": 0.12, "dependency": 0.28, "supervision": 0.10}
    )
    required = {"authorization", "communication", "dependency", "supervision"}
    if set(layers) != required:
        raise ValueError(f"layers must be exactly {sorted(required)}")
    n = len(node_state.privilege_true)
    rng = np.random.default_rng(seed)
    edge_sets = {name: _layer_edge_set(graph) for name, graph in layers.items()}
    all_edges = sorted(set().union(*edge_sets.values()))

    true_rows: list[int] = []
    true_cols: list[int] = []
    true_pre_data: list[float] = []
    true_post_data: list[float] = []
    cand_rows: list[int] = []
    cand_cols: list[int] = []
    cand_pre_data: list[float] = []
    cand_post_data: list[float] = []
    per_layer_rows: dict[str, list[int]] = {name: [] for name in required}
    per_layer_cols: dict[str, list[int]] = {name: [] for name in required}
    per_layer_data: dict[str, list[float]] = {name: [] for name in required}

    for source, target in all_edges:
        present = {name: (source, target) in edges for name, edges in edge_sets.items()}
        true_union = 1.0
        candidate_sum = 0.0
        for name in required:
            if present[name]:
                true_union *= 1.0 - true_weights[name]
                candidate_sum += candidate_weights[name]
        true_layer_effect = 1.0 - true_union
        if present["authorization"] and present["dependency"]:
            true_layer_effect *= 1.0 + true_interaction_strength
        latent = float(rng.lognormal(mean=-0.5 * latent_edge_sigma**2, sigma=latent_edge_sigma))
        true_hazard = (
            beta_scale
            * node_state.privilege_true[source]
            * node_state.susceptibility_true[target]
            * true_layer_effect
            * latent
        )
        candidate_hazard = (
            beta_scale
            * node_state.privilege_observed[source]
            * node_state.susceptibility_observed[target]
            * min(1.0, candidate_sum)
        )
        attenuation_true = 1.0
        attenuation_candidate = 1.0
        if present["authorization"] or present["supervision"]:
            # Response effectiveness is intentionally misspecified in the candidate.
            true_effectiveness = float(
                np.clip(intervention_strength * rng.lognormal(0.0, 0.08), 0.0, 0.95)
            )
            attenuation_true = 1.0 - true_effectiveness
            attenuation_candidate = 1.0 - intervention_strength

        true_rows.append(source)
        true_cols.append(target)
        true_pre_data.append(true_hazard)
        true_post_data.append(true_hazard * attenuation_true)
        cand_rows.append(source)
        cand_cols.append(target)
        cand_pre_data.append(candidate_hazard)
        cand_post_data.append(candidate_hazard * attenuation_candidate)
        for name in required:
            if present[name]:
                layer_hazard = (
                    beta_scale
                    * node_state.privilege_observed[source]
                    * node_state.susceptibility_observed[target]
                    * candidate_weights[name]
                )
                per_layer_rows[name].append(source)
                per_layer_cols[name].append(target)
                per_layer_data[name].append(layer_hazard)

    shape = (n, n)
    true_pre = sparse.csr_matrix((true_pre_data, (true_rows, true_cols)), shape=shape)
    true_post = sparse.csr_matrix((true_post_data, (true_rows, true_cols)), shape=shape)
    candidate_pre = sparse.csr_matrix((cand_pre_data, (cand_rows, cand_cols)), shape=shape)
    candidate_post = sparse.csr_matrix((cand_post_data, (cand_rows, cand_cols)), shape=shape)
    layer_candidate_pre = {
        name: sparse.csr_matrix(
            (per_layer_data[name], (per_layer_rows[name], per_layer_cols[name])), shape=shape
        )
        for name in sorted(required)
    }
    return HazardOperators(
        true_pre=true_pre,
        true_post=true_post,
        candidate_pre=candidate_pre,
        candidate_post=candidate_post,
        layer_candidate_pre=layer_candidate_pre,
        node_state=node_state,
    )


def next_generation_matrix(hazard: sparse.spmatrix, recovery_by_source: np.ndarray) -> sparse.csr_matrix:
    """Return K with row=source and column=target expected offspring entries."""
    recovery = np.asarray(recovery_by_source, dtype=float)
    if hazard.shape[0] != len(recovery):
        raise ValueError("recovery vector length must match hazard matrix")
    if np.any(recovery <= 0.0):
        raise ValueError("recovery rates must be positive")
    return sparse.diags(1.0 / recovery) @ sparse.csr_matrix(hazard)


def symmetrized_radius(hazard: sparse.spmatrix) -> float:
    """Return the spectral radius of the symmetric aggregate used as a Stage 1 baseline."""
    mat = sparse.csr_matrix(hazard)
    sym = 0.5 * (mat + mat.T)
    return nonnegative_spectral_radius(sym)


def weighted_nonbacktracking_radius(
    hazard: sparse.spmatrix,
    recovery_by_source: np.ndarray,
    *,
    max_iterations: int = 250,
    tolerance: float = 1e-8,
) -> float:
    """Estimate the Perron root of a weighted directed non-backtracking operator.

    Edge transmissibility is h_ij / (h_ij + gamma_i), which is the probability
    that an exponential transmission clock fires before source recovery under
    the declared two-clock approximation.
    """
    h = sparse.csr_matrix(hazard, dtype=float)
    source, target = h.nonzero()
    if len(source) == 0:
        return 0.0
    data = h.data
    gamma = np.asarray(recovery_by_source, dtype=float)
    cache_key = _sparse_fingerprint(
        h,
        gamma.tobytes(),
        np.asarray([max_iterations], dtype=np.int64).tobytes(),
        np.asarray([tolerance], dtype=float).tobytes(),
        b"nonbacktracking-v1",
    )
    cached = _NONBACKTRACKING_RADIUS_CACHE.get(cache_key)
    if cached is not None:
        return cached
    transmissibility = data / (data + gamma[source])
    edges = list(zip(source.tolist(), target.tolist()))
    index = {edge: idx for idx, edge in enumerate(edges)}
    outgoing: dict[int, list[tuple[int, int, float]]] = {}
    for idx, (u, v) in enumerate(edges):
        outgoing.setdefault(int(u), []).append((idx, int(v), float(transmissibility[idx])))

    rows: list[int] = []
    cols: list[int] = []
    values: list[float] = []
    for e_idx, (u, v) in enumerate(edges):
        for f_idx, w, weight in outgoing.get(int(v), []):
            if w == int(u):
                continue
            rows.append(f_idx)
            cols.append(e_idx)
            values.append(weight)
    if not values:
        _NONBACKTRACKING_RADIUS_CACHE[cache_key] = 0.0
        return 0.0
    b = sparse.csr_matrix((values, (rows, cols)), shape=(len(edges), len(edges)))
    x = np.full(len(edges), 1.0 / np.sqrt(len(edges)), dtype=float)
    previous = 0.0
    radius = 0.0
    for _ in range(max_iterations):
        y = b @ x
        norm = float(np.linalg.norm(y))
        if norm == 0.0:
            return 0.0
        x = y / norm
        radius = norm
        if abs(radius - previous) <= tolerance * max(1.0, radius):
            break
        previous = radius
    result = float(radius)
    if len(_NONBACKTRACKING_RADIUS_CACHE) >= _CACHE_LIMIT:
        _NONBACKTRACKING_RADIUS_CACHE.clear()
    _NONBACKTRACKING_RADIUS_CACHE[cache_key] = result
    return result


def dynamic_operator_metrics(
    candidate_pre: sparse.spmatrix,
    candidate_post: sparse.spmatrix,
    recovery_observed: np.ndarray,
    *,
    intervention_time: float,
    horizon: float,
) -> dict[str, float]:
    """Compute static and time-integrated next-generation metrics."""
    if not 0.0 <= intervention_time <= horizon:
        raise ValueError("intervention_time must be inside the horizon")
    k_pre = next_generation_matrix(candidate_pre, recovery_observed)
    k_post = next_generation_matrix(candidate_post, recovery_observed)
    rho_pre = nonnegative_spectral_radius(k_pre)
    rho_post = nonnegative_spectral_radius(k_post)
    pre_fraction = intervention_time / horizon if horizon > 0 else 0.0
    mean_rho = pre_fraction * rho_pre + (1.0 - pre_fraction) * rho_post
    excess = (
        max(0.0, rho_pre - 1.0) * intervention_time
        + max(0.0, rho_post - 1.0) * (horizon - intervention_time)
    ) / max(horizon, 1e-12)
    return {
        "candidate_rho_pre": rho_pre,
        "candidate_rho_post": rho_post,
        "candidate_rho_time_mean": mean_rho,
        "dynamic_excess_exposure": excess,
    }


def simulate_directed_sir_batch(
    true_pre: sparse.spmatrix,
    true_post: sparse.spmatrix,
    recovery_true: np.ndarray,
    *,
    intervention_time: int,
    horizon_steps: int,
    replication_seeds: Sequence[int],
    initial_seed_count: int = 1,
) -> PropagationBatch:
    """Run independent directed SIR replications using sparse batched hazards."""
    pre = sparse.csr_matrix(true_pre, dtype=float)
    post = sparse.csr_matrix(true_post, dtype=float)
    n = pre.shape[0]
    if pre.shape != post.shape or pre.shape[1] != n:
        raise ValueError("hazard matrices must be square and have equal shape")
    recovery = np.asarray(recovery_true, dtype=float)
    if len(recovery) != n:
        raise ValueError("recovery vector length mismatch")
    seeds = np.asarray(list(replication_seeds), dtype=np.int64)
    reps = len(seeds)
    if reps == 0:
        raise ValueError("at least one replication is required")
    if initial_seed_count < 1 or initial_seed_count > n:
        raise ValueError("invalid initial_seed_count")

    infection_uniform = np.empty((horizon_steps, reps, n), dtype=np.float32)
    recovery_uniform = np.empty((horizon_steps, reps, n), dtype=np.float32)
    initial_nodes = np.empty((reps, initial_seed_count), dtype=np.int64)
    for r, seed in enumerate(seeds):
        rng = np.random.default_rng(int(seed))
        initial_nodes[r] = rng.choice(n, size=initial_seed_count, replace=False)
        infection_uniform[:, r, :] = rng.random((horizon_steps, n), dtype=np.float32)
        recovery_uniform[:, r, :] = rng.random((horizon_steps, n), dtype=np.float32)

    susceptible = np.ones((reps, n), dtype=bool)
    infected = np.zeros((reps, n), dtype=bool)
    recovered = np.zeros((reps, n), dtype=bool)
    for r in range(reps):
        infected[r, initial_nodes[r]] = True
        susceptible[r, initial_nodes[r]] = False
    ever = infected.copy()
    peak = infected.sum(axis=1).astype(np.int64)
    duration = np.full(reps, horizon_steps, dtype=np.int64)
    active = np.ones(reps, dtype=bool)
    recovery_probability = 1.0 - np.exp(-recovery)

    for step in range(horizon_steps):
        hazard = pre if step < intervention_time else post
        pressure = infected.astype(float) @ hazard
        infection_probability = 1.0 - np.exp(-np.asarray(pressure))
        new_infected = susceptible & (infection_uniform[step] < infection_probability)
        new_recovered = infected & (recovery_uniform[step] < recovery_probability[None, :])
        infected = (infected | new_infected) & ~new_recovered
        recovered |= new_recovered
        susceptible &= ~new_infected
        ever |= new_infected
        peak = np.maximum(peak, infected.sum(axis=1))
        just_finished = active & (infected.sum(axis=1) == 0)
        duration[just_finished] = step + 1
        active &= ~just_finished
        if not active.any():
            break

    return PropagationBatch(
        peak_fraction=peak.astype(float) / n,
        ever_fraction=ever.sum(axis=1).astype(float) / n,
        duration_steps=duration,
        replication_seeds=seeds,
    )
