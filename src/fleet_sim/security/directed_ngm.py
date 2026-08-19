"""Directed multilayer compromise model for Stage 2 Cycle 3.

All rates and graph parameters in this module are notional. The module is
intended to test predictive transfer of candidate compromise operators. It is
not a deployment security assessment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import networkx as nx
import numpy as np
from scipy import sparse

from fleet_sim.graphs.factory import build_graph
from fleet_sim.security.attack_operator import (
    nonnegative_spectral_radius,
    orient_undirected_layer,
    weighted_nonbacktracking_radius,
)

LAYER_NAMES = ("authorization", "communication", "dependency", "supervision")


@dataclass(frozen=True)
class DirectedNodeState:
    exploitability_true: np.ndarray
    susceptibility_true: np.ndarray
    detection_true: np.ndarray
    remediation_true: np.ndarray
    exploitability_observed: np.ndarray
    susceptibility_observed: np.ndarray
    detection_observed: np.ndarray
    remediation_observed: np.ndarray
    communication_duty_true: np.ndarray
    communication_duty_observed: np.ndarray
    dependency_delay_true_s: np.ndarray
    dependency_delay_observed_s: np.ndarray
    image_family: np.ndarray


@dataclass(frozen=True)
class DirectedAttackScenario:
    scenario_id: int
    split: str
    n: int
    seed: int
    auth_topology: str
    dependency_topology: str
    hazard_scale: float
    seed_mode: str
    true_layers: Mapping[str, sparse.csr_matrix]
    observed_layers: Mapping[str, sparse.csr_matrix]
    node_state: DirectedNodeState
    cutoff_delays_true_s: Mapping[str, float]
    cutoff_delays_observed_s: Mapping[str, float]
    expected_initial_seed_fraction: float
    correlated_seed_fraction: float
    horizon_s: float = 45.0
    dt_s: float = 0.25
    response_degradation: float = 2.5


@dataclass(frozen=True)
class DirectedOperatorSet:
    raw_auth_radius: float
    static_aggregate_radius: float
    nonbacktracking_radius: float
    operational_ngm_radius: float
    oracle_ngm_radius: float
    ablation_radii: Mapping[str, float]

    def as_dict(self) -> dict[str, float]:
        values = {
            "raw_auth_radius": self.raw_auth_radius,
            "static_aggregate_radius": self.static_aggregate_radius,
            "nonbacktracking_radius": self.nonbacktracking_radius,
            "operational_ngm_radius": self.operational_ngm_radius,
            "oracle_ngm_radius": self.oracle_ngm_radius,
        }
        values.update({f"operational_without_{name}": value for name, value in self.ablation_radii.items()})
        return values


def _lognormal_observation(true: np.ndarray, rng: np.random.Generator, sigma: float) -> np.ndarray:
    return np.asarray(true, dtype=float) * rng.lognormal(-0.5 * sigma**2, sigma, size=len(true))


def _make_node_state(n: int, seed: int) -> DirectedNodeState:
    rng = np.random.default_rng(seed)
    image_families = max(6, int(round(np.sqrt(n))))
    image_family = rng.integers(0, image_families, size=n, dtype=np.int64)
    family_multiplier = np.clip(rng.lognormal(-0.02, 0.22, size=image_families), 0.55, 1.75)

    exploitability_true = np.clip(rng.lognormal(-0.04, 0.28, size=n), 0.45, 2.10)
    susceptibility_true = np.clip(
        rng.lognormal(-0.06, 0.26, size=n) * family_multiplier[image_family],
        0.40,
        2.40,
    )
    detection_true = np.clip(rng.lognormal(np.log(0.18), 0.28, size=n), 0.055, 0.48)
    remediation_true = np.clip(rng.lognormal(np.log(0.14), 0.24, size=n), 0.045, 0.36)
    communication_duty_true = np.clip(rng.beta(7.0, 3.0, size=n), 0.25, 0.98)
    dependency_delay_true_s = np.clip(rng.lognormal(np.log(1.8), 0.30, size=n), 0.55, 5.0)

    exploitability_observed = np.clip(_lognormal_observation(exploitability_true, rng, 0.14), 0.35, 2.40)
    susceptibility_observed = np.clip(_lognormal_observation(susceptibility_true, rng, 0.17), 0.30, 2.70)
    detection_observed = np.clip(_lognormal_observation(detection_true, rng, 0.20), 0.035, 0.60)
    remediation_observed = np.clip(_lognormal_observation(remediation_true, rng, 0.18), 0.030, 0.45)
    communication_duty_observed = np.clip(
        communication_duty_true + rng.normal(0.0, 0.08, size=n), 0.15, 1.0
    )
    dependency_delay_observed_s = np.clip(
        dependency_delay_true_s * rng.lognormal(-0.5 * 0.20**2, 0.20, size=n), 0.35, 6.0
    )
    return DirectedNodeState(
        exploitability_true=exploitability_true,
        susceptibility_true=susceptibility_true,
        detection_true=detection_true,
        remediation_true=remediation_true,
        exploitability_observed=exploitability_observed,
        susceptibility_observed=susceptibility_observed,
        detection_observed=detection_observed,
        remediation_observed=remediation_observed,
        communication_duty_true=communication_duty_true,
        communication_duty_observed=communication_duty_observed,
        dependency_delay_true_s=dependency_delay_true_s,
        dependency_delay_observed_s=dependency_delay_observed_s,
        image_family=image_family,
    )


def _undirected_layer(n: int, family: str, kwargs: Mapping[str, int | float], seed: int) -> nx.Graph:
    return build_graph(n, family, seed=seed, **dict(kwargs)).materialize()


def _direct_layer(
    graph: nx.Graph,
    *,
    seed: int,
    score: np.ndarray,
    prefer_high_to_low: bool,
    reverse_probability: float,
    bidirectional_probability: float,
) -> nx.DiGraph:
    return orient_undirected_layer(
        graph,
        seed=seed,
        node_score=score,
        prefer_high_to_low=prefer_high_to_low,
        reverse_probability=reverse_probability,
        bidirectional_probability=bidirectional_probability,
    )


def _observe_graph(
    graph: nx.DiGraph,
    *,
    seed: int,
    missed_edge_probability: float,
    spurious_edge_probability: float,
) -> nx.DiGraph:
    rng = np.random.default_rng(seed)
    observed = nx.DiGraph()
    observed.add_nodes_from(graph.nodes())
    for source, target in sorted(graph.edges()):
        if rng.random() >= missed_edge_probability:
            observed.add_edge(int(source), int(target))
    n = graph.number_of_nodes()
    target_spurious = int(round(spurious_edge_probability * max(1, graph.number_of_edges())))
    attempts = 0
    while target_spurious > 0 and attempts < max(100, 20 * target_spurious):
        source = int(rng.integers(0, n))
        target = int(rng.integers(0, n))
        attempts += 1
        if source == target or observed.has_edge(source, target):
            continue
        observed.add_edge(source, target)
        target_spurious -= 1
    return observed


def _matrix_from_graph(
    graph: nx.DiGraph,
    *,
    source_score: np.ndarray,
    target_score: np.ndarray,
    base_rate: float,
    rng: np.random.Generator,
    latent_sigma: float,
    source_multiplier: np.ndarray | None = None,
) -> sparse.csr_matrix:
    n = graph.number_of_nodes()
    rows: list[int] = []
    cols: list[int] = []
    values: list[float] = []
    for source, target in sorted(graph.edges()):
        multiplier = 1.0 if source_multiplier is None else float(source_multiplier[int(source)])
        latent = 1.0
        if latent_sigma > 0.0:
            latent = float(rng.lognormal(-0.5 * latent_sigma**2, latent_sigma))
        value = (
            base_rate
            * float(source_score[int(source)])
            * float(target_score[int(target)])
            * multiplier
            * latent
        )
        rows.append(int(source))
        cols.append(int(target))
        values.append(max(0.0, value))
    return sparse.csr_matrix((values, (rows, cols)), shape=(n, n), dtype=float)


def build_directed_attack_scenario(
    *,
    scenario_id: int,
    split: str,
    n: int,
    seed: int,
    auth_topology: str,
    dependency_topology: str,
    auth_kwargs: Mapping[str, int | float] | None = None,
    dependency_kwargs: Mapping[str, int | float] | None = None,
    hazard_scale: float | None = None,
    intensity_scale: float | None = None,
    seed_mode: str = "single",
    correlated_seed_fraction: float = 0.025,
    revocation_time_s: float | None = None,
    revocation_effectiveness: float | None = None,
    supply_chain_fraction: float | None = None,
    idp_shock_fraction: float | None = None,
) -> DirectedAttackScenario:
    """Build one directed multilayer scenario.

    Compatibility arguments from the earlier Stage 2 harness are accepted but
    are translated into the Cycle 3 model. They do not alter the confirmatory
    parameter matrix unless explicitly passed by a caller.
    """
    if n < 2:
        raise ValueError("n must be at least 2")
    scale = float(hazard_scale if hazard_scale is not None else (intensity_scale or 1.0))
    if scale <= 0.0:
        raise ValueError("hazard scale must be positive")
    if seed_mode not in {"single", "correlated"}:
        if supply_chain_fraction and supply_chain_fraction > 0.0:
            seed_mode = "correlated"
        else:
            raise ValueError(f"unsupported seed mode: {seed_mode}")
    if supply_chain_fraction is not None and supply_chain_fraction > 0.0:
        correlated_seed_fraction = max(correlated_seed_fraction, float(supply_chain_fraction))

    state = _make_node_state(n, seed + 11)
    auth_graph = _direct_layer(
        _undirected_layer(n, auth_topology, auth_kwargs or {}, seed + 21),
        seed=seed + 22,
        score=state.exploitability_true,
        prefer_high_to_low=True,
        reverse_probability=0.12,
        bidirectional_probability=0.18,
    )
    dependency_graph = _direct_layer(
        _undirected_layer(n, dependency_topology, dependency_kwargs or {}, seed + 31),
        seed=seed + 32,
        score=state.susceptibility_true,
        prefer_high_to_low=True,
        reverse_probability=0.20,
        bidirectional_probability=0.14,
    )
    communication_graph = _direct_layer(
        _undirected_layer(n, "random_regular", {"degree": 6}, seed + 41),
        seed=seed + 42,
        score=state.susceptibility_true,
        prefer_high_to_low=False,
        reverse_probability=0.50,
        bidirectional_probability=0.52,
    )
    supervision_graph = _direct_layer(
        _undirected_layer(n, "hierarchical", {"span": 8}, seed + 51),
        seed=seed + 52,
        score=np.linspace(1.7, 0.4, n),
        prefer_high_to_low=True,
        reverse_probability=0.04,
        bidirectional_probability=0.06,
    )
    true_graphs = {
        "authorization": auth_graph,
        "communication": communication_graph,
        "dependency": dependency_graph,
        "supervision": supervision_graph,
    }
    observation = {
        "authorization": (0.035, 0.010),
        "communication": (0.140, 0.025),
        "dependency": (0.100, 0.018),
        "supervision": (0.055, 0.010),
    }
    observed_graphs = {
        name: _observe_graph(
            graph,
            seed=seed + 70 + index,
            missed_edge_probability=observation[name][0],
            spurious_edge_probability=observation[name][1],
        )
        for index, (name, graph) in enumerate(true_graphs.items())
    }

    true_base = {
        "authorization": 0.0460,
        "communication": 0.0140,
        "dependency": 0.0275,
        "supervision": 0.0175,
    }
    observed_base = {
        "authorization": 0.0440,
        "communication": 0.0150,
        "dependency": 0.0255,
        "supervision": 0.0185,
    }
    true_layers: dict[str, sparse.csr_matrix] = {}
    observed_layers: dict[str, sparse.csr_matrix] = {}
    true_rng = np.random.default_rng(seed + 101)
    observed_rng = np.random.default_rng(seed + 102)
    for name in LAYER_NAMES:
        true_source_multiplier = (
            state.communication_duty_true if name == "communication" else None
        )
        observed_source_multiplier = (
            state.communication_duty_observed if name == "communication" else None
        )
        true_layers[name] = _matrix_from_graph(
            true_graphs[name],
            source_score=state.exploitability_true,
            target_score=state.susceptibility_true,
            base_rate=scale * true_base[name],
            rng=true_rng,
            latent_sigma=0.24,
            source_multiplier=true_source_multiplier,
        )
        observed_layers[name] = _matrix_from_graph(
            observed_graphs[name],
            source_score=state.exploitability_observed,
            target_score=state.susceptibility_observed,
            base_rate=scale * observed_base[name],
            rng=observed_rng,
            latent_sigma=0.0,
            source_multiplier=observed_source_multiplier,
        )

    # A real system can have mechanism interactions that are not represented in
    # an additive operational model. The true simulator includes a modest
    # authorization and dependency overlap effect.
    overlap = true_layers["authorization"].multiply(true_layers["dependency"] > 0.0)
    true_layers["authorization"] = true_layers["authorization"] + 0.20 * overlap
    true_layers["dependency"] = true_layers["dependency"] + 0.12 * overlap

    if revocation_time_s is None:
        cutoff_true = {"authorization": 2.4, "supervision": 3.8}
    else:
        cutoff_true = {
            "authorization": max(0.2, 0.18 * float(revocation_time_s)),
            "supervision": max(0.3, 0.26 * float(revocation_time_s)),
        }
    cutoff_observed = {
        "authorization": cutoff_true["authorization"] * 1.10,
        "supervision": cutoff_true["supervision"] * 0.92,
    }
    correlated_fraction = float(np.clip(correlated_seed_fraction, 2.0 / n, 0.12))
    expected_seed_fraction = 1.0 / n if seed_mode == "single" else correlated_fraction
    if idp_shock_fraction:
        expected_seed_fraction = min(0.20, expected_seed_fraction + float(idp_shock_fraction))
    return DirectedAttackScenario(
        scenario_id=scenario_id,
        split=split,
        n=n,
        seed=seed,
        auth_topology=auth_topology,
        dependency_topology=dependency_topology,
        hazard_scale=scale,
        seed_mode=seed_mode,
        true_layers=true_layers,
        observed_layers=observed_layers,
        node_state=state,
        cutoff_delays_true_s=cutoff_true,
        cutoff_delays_observed_s=cutoff_observed,
        expected_initial_seed_fraction=expected_seed_fraction,
        correlated_seed_fraction=correlated_fraction,
    )


def _cutoff_residence_time(
    remediation_rate: np.ndarray,
    detection_rate: np.ndarray,
    delay_s: float,
) -> np.ndarray:
    gamma = np.asarray(remediation_rate, dtype=float)
    delta = np.asarray(detection_rate, dtype=float)
    if np.any(gamma <= 0.0) or np.any(delta < 0.0):
        raise ValueError("invalid remediation or detection rate")
    return (1.0 - np.exp(-gamma * delay_s)) / gamma + np.exp(-gamma * delay_s) / (
        gamma + delta
    )


def _layer_ngm(
    matrix: sparse.csr_matrix,
    *,
    name: str,
    remediation: np.ndarray,
    detection: np.ndarray,
    cutoff_delays: Mapping[str, float],
    dependency_delay: np.ndarray,
) -> sparse.csr_matrix:
    effective = sparse.csr_matrix(matrix, dtype=float)
    if name == "dependency":
        survival = np.exp(-np.asarray(remediation, dtype=float) * dependency_delay)
        effective = sparse.diags(survival) @ effective
    if name in cutoff_delays:
        residence = _cutoff_residence_time(
            remediation,
            detection,
            float(cutoff_delays[name]),
        )
    else:
        residence = 1.0 / np.asarray(remediation, dtype=float)
    return sparse.diags(residence) @ effective


def _ngm_from_layers(
    layers: Mapping[str, sparse.csr_matrix],
    *,
    remediation: np.ndarray,
    detection: np.ndarray,
    cutoff_delays: Mapping[str, float],
    dependency_delay: np.ndarray,
    omit: str | None = None,
) -> sparse.csr_matrix:
    total: sparse.csr_matrix | None = None
    for name in LAYER_NAMES:
        if name == omit:
            continue
        component = _layer_ngm(
            layers[name],
            name=name,
            remediation=remediation,
            detection=detection,
            cutoff_delays=cutoff_delays,
            dependency_delay=dependency_delay,
        )
        total = component.copy() if total is None else total + component
    if total is None:
        n = len(remediation)
        return sparse.csr_matrix((n, n), dtype=float)
    return sparse.csr_matrix(total)


def attack_operator_predictors(scenario: DirectedAttackScenario) -> DirectedOperatorSet:
    state = scenario.node_state
    observed_sum = sum(
        (scenario.observed_layers[name] for name in LAYER_NAMES),
        start=sparse.csr_matrix((scenario.n, scenario.n), dtype=float),
    )
    raw_auth_radius = nonnegative_spectral_radius(scenario.observed_layers["authorization"])
    mean_residence = 1.0 / float(np.mean(state.remediation_observed))
    static_aggregate_radius = nonnegative_spectral_radius(observed_sum * mean_residence)
    nonbacktracking = weighted_nonbacktracking_radius(
        observed_sum,
        state.remediation_observed,
        max_iterations=160,
    )
    operational = _ngm_from_layers(
        scenario.observed_layers,
        remediation=state.remediation_observed,
        detection=state.detection_observed,
        cutoff_delays=scenario.cutoff_delays_observed_s,
        dependency_delay=state.dependency_delay_observed_s,
    )
    oracle = _ngm_from_layers(
        scenario.true_layers,
        remediation=state.remediation_true,
        detection=state.detection_true,
        cutoff_delays=scenario.cutoff_delays_true_s,
        dependency_delay=state.dependency_delay_true_s,
    )
    ablations = {
        name: nonnegative_spectral_radius(
            _ngm_from_layers(
                scenario.observed_layers,
                remediation=state.remediation_observed,
                detection=state.detection_observed,
                cutoff_delays=scenario.cutoff_delays_observed_s,
                dependency_delay=state.dependency_delay_observed_s,
                omit=name,
            )
        )
        for name in LAYER_NAMES
    }
    return DirectedOperatorSet(
        raw_auth_radius=raw_auth_radius,
        static_aggregate_radius=static_aggregate_radius,
        nonbacktracking_radius=nonbacktracking,
        operational_ngm_radius=nonnegative_spectral_radius(operational),
        oracle_ngm_radius=nonnegative_spectral_radius(oracle),
        ablation_radii=ablations,
    )


def _initial_nodes(scenario: DirectedAttackScenario, rng: np.random.Generator) -> np.ndarray:
    if scenario.seed_mode == "single":
        return np.asarray([int(rng.integers(0, scenario.n))], dtype=np.int64)
    count = max(2, int(round(scenario.correlated_seed_fraction * scenario.n)))
    families = scenario.node_state.image_family
    unique, counts = np.unique(families, return_counts=True)
    eligible = unique[counts >= min(count, max(2, count // 2))]
    family = int(rng.choice(eligible if len(eligible) else unique))
    candidates = np.flatnonzero(families == family)
    selected = rng.choice(candidates, size=min(count, len(candidates)), replace=False)
    if len(selected) < count:
        remaining = np.setdiff1d(np.arange(scenario.n), selected, assume_unique=False)
        supplement = rng.choice(remaining, size=count - len(selected), replace=False)
        selected = np.concatenate([selected, supplement])
    return np.asarray(selected, dtype=np.int64)


def simulate_latent_compromise(
    scenario: DirectedAttackScenario,
    *,
    seed: int,
) -> dict[str, float | int]:
    """Run one stochastic directed multilayer compromise replication."""
    rng = np.random.default_rng(seed)
    n = scenario.n
    state = scenario.node_state
    dt = scenario.dt_s
    steps = int(round(scenario.horizon_s / dt))
    infected = np.zeros(n, dtype=bool)
    recovered = np.zeros(n, dtype=bool)
    detected = np.zeros(n, dtype=bool)
    age_s = np.zeros(n, dtype=float)
    detection_age_s = np.zeros(n, dtype=float)
    initial = _initial_nodes(scenario, rng)
    infected[initial] = True
    ever = infected.copy()
    peak = int(infected.sum())
    first_detection_time = float("nan")
    transmissions_after_detection = 0
    duration_s = scenario.horizon_s

    for step in range(steps):
        now = step * dt
        active = infected & ~recovered
        if not active.any():
            duration_s = now
            break
        prevalence = float(active.mean())
        degradation = 1.0 + scenario.response_degradation * prevalence

        auth_cutoff = detected & (
            detection_age_s >= float(scenario.cutoff_delays_true_s["authorization"])
        )
        supervision_cutoff = detected & (
            detection_age_s >= float(scenario.cutoff_delays_true_s["supervision"])
        )
        auth_source = (active & ~auth_cutoff).astype(float)
        supervision_source = (active & ~supervision_cutoff).astype(float)
        communication_gate = rng.random(n) < state.communication_duty_true
        communication_source = (active & communication_gate).astype(float)
        dependency_source = (active & (age_s >= state.dependency_delay_true_s)).astype(float)

        pressure = np.zeros(n, dtype=float)
        pressure += np.asarray(auth_source @ scenario.true_layers["authorization"]).ravel()
        pressure += np.asarray(communication_source @ scenario.true_layers["communication"]).ravel()
        pressure += np.asarray(dependency_source @ scenario.true_layers["dependency"]).ravel()
        pressure += np.asarray(supervision_source @ scenario.true_layers["supervision"]).ravel()
        infection_probability = 1.0 - np.exp(-np.maximum(0.0, pressure) * dt)
        susceptible = ~infected & ~recovered
        new_infections = susceptible & (rng.random(n) < infection_probability)
        if np.isfinite(first_detection_time):
            transmissions_after_detection += int(new_infections.sum())

        detection_probability = 1.0 - np.exp(-state.detection_true * dt / degradation)
        newly_detected = active & ~detected & (rng.random(n) < detection_probability)
        if newly_detected.any() and not np.isfinite(first_detection_time):
            first_detection_time = now
        detected |= newly_detected

        remediation_probability = 1.0 - np.exp(-state.remediation_true * dt / degradation)
        newly_recovered = active & (rng.random(n) < remediation_probability)
        infected[newly_recovered] = False
        recovered[newly_recovered] = True
        infected[new_infections] = True
        ever |= new_infections

        age_s[active] += dt
        age_s[new_infections] = 0.0
        detection_age_s[detected & infected] += dt
        peak = max(peak, int(infected.sum()))

    ever_fraction = float(ever.mean())
    peak_fraction = float(peak / n)
    threshold = max(0.10, float(len(initial) / n) + 0.06)
    return {
        "replication_seed": int(seed),
        "initial_seed_count": int(len(initial)),
        "initial_seed_fraction": float(len(initial) / n),
        "ever_fraction": ever_fraction,
        "peak_fraction": peak_fraction,
        "duration_s": float(duration_s),
        "time_to_first_detection_s": float(first_detection_time),
        "transmissions_after_first_detection": int(transmissions_after_detection),
        "major_outbreak": int(ever_fraction >= threshold),
    }
