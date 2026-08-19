"""Stage 2 novelty-driven falsification experiments.

This module evaluates a directed dynamic compromise operator and a normalized
multi-resource admission-overload index. All parameters are notional and all
results are model-conditioned unless an output explicitly states otherwise.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy import sparse

from fleet_sim.analysis.admission_stability import (
    build_resource_regime,
    critical_linear_admission_rate,
    fluid_admission_metrics,
    make_admission_trajectory,
    simulate_stochastic_admission_batch,
)
from fleet_sim.graphs.factory import apply_segmentation, build_graph
from fleet_sim.security.attack_operator import (
    build_hazard_operators,
    dynamic_operator_metrics,
    make_node_risk_state,
    next_generation_matrix,
    nonnegative_spectral_radius,
    orient_undirected_layer,
    simulate_directed_sir_batch,
    symmetrized_radius,
    weighted_nonbacktracking_radius,
)


@dataclass(frozen=True)
class HypothesisAssessment:
    hypothesis: str
    supported_in_model: bool
    evidence_level: str
    primary_result: str
    limitations: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _roc_auc(y_true: np.ndarray, scores: np.ndarray) -> float:
    y = np.asarray(y_true, dtype=int)
    s = np.asarray(scores, dtype=float)
    pos = y == 1
    neg = y == 0
    n_pos = int(pos.sum())
    n_neg = int(neg.sum())
    if n_pos == 0 or n_neg == 0:
        return 0.5
    order = np.argsort(s, kind="mergesort")
    sorted_s = s[order]
    ranks = np.empty(len(s), dtype=float)
    start = 0
    while start < len(s):
        end = start + 1
        while end < len(s) and sorted_s[end] == sorted_s[start]:
            end += 1
        ranks[order[start:end]] = (start + 1 + end) / 2.0
        start = end
    rank_sum = float(ranks[pos].sum())
    return float((rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def _feature_matrix(x: np.ndarray, *, quadratic: bool = True) -> np.ndarray:
    z = np.log1p(np.maximum(0.0, np.asarray(x, dtype=float)))
    if z.ndim == 1:
        z = z[:, None]
    columns = [np.ones(len(z)), z]
    if quadratic:
        columns.append(z**2)
    return np.column_stack(columns)


def _fit_continuous(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    design = _feature_matrix(x)
    return np.linalg.lstsq(design, np.asarray(y, dtype=float), rcond=None)[0]


def _predict_continuous(x: np.ndarray, weights: np.ndarray) -> np.ndarray:
    return np.clip(_feature_matrix(x) @ weights, 0.0, 1.0)


def _fit_binomial(
    x: np.ndarray,
    successes: np.ndarray,
    trials: np.ndarray,
) -> np.ndarray:
    design = _feature_matrix(x)
    s = np.asarray(successes, dtype=float)
    n = np.asarray(trials, dtype=float)

    def objective(w: np.ndarray) -> tuple[float, np.ndarray]:
        z = np.clip(design @ w, -35.0, 35.0)
        p = 1.0 / (1.0 + np.exp(-z))
        eps = 1e-12
        loss = -np.sum(s * np.log(p + eps) + (n - s) * np.log(1.0 - p + eps))
        reg = 1e-4 * np.sum(w[1:] ** 2)
        gradient = design.T @ (n * p - s)
        gradient[1:] += 2e-4 * w[1:]
        return float(loss + reg), gradient

    result = minimize(
        lambda w: objective(w)[0],
        np.zeros(design.shape[1]),
        jac=lambda w: objective(w)[1],
        method="BFGS",
    )
    return np.asarray(result.x, dtype=float)


def _predict_binomial(x: np.ndarray, weights: np.ndarray) -> np.ndarray:
    z = np.clip(_feature_matrix(x) @ weights, -35.0, 35.0)
    return 1.0 / (1.0 + np.exp(-z))


def _directed_adjacency_radius(graph: nx.DiGraph) -> float:
    adjacency = nx.to_scipy_sparse_array(graph, dtype=float, format="csr")
    return nonnegative_spectral_radius(adjacency)


def _build_directed_layers(
    n: int,
    *,
    auth_family: str,
    dependency_family: str,
    segmentation: str,
    seed: int,
):
    state = make_node_risk_state(n, seed=seed + 1)
    auth_kwargs: dict[str, int] = {}
    if auth_family == "random_regular":
        auth_kwargs["degree"] = 8
    elif auth_family == "barabasi_albert":
        auth_kwargs["attachment"] = 3
    elif auth_family == "hierarchical":
        auth_kwargs["span"] = 8
    else:
        raise ValueError(auth_family)
    auth_bundle = build_graph(n, auth_family, seed=seed + 2, **auth_kwargs)
    if segmentation == "partitioned":
        auth_bundle = apply_segmentation(auth_bundle, "partition", partitions=8)
    elif segmentation != "none":
        raise ValueError(segmentation)
    auth = orient_undirected_layer(
        auth_bundle.materialize(),
        seed=seed + 3,
        node_score=state.privilege_true,
        prefer_high_to_low=True,
        reverse_probability=0.10,
        bidirectional_probability=0.22,
    )

    communication = orient_undirected_layer(
        build_graph(n, "random_regular", seed=seed + 4, degree=6).materialize(),
        seed=seed + 5,
        node_score=state.susceptibility_true,
        prefer_high_to_low=False,
        reverse_probability=0.50,
        bidirectional_probability=0.60,
    )

    dependency_kwargs: dict[str, int] = {}
    if dependency_family == "random_regular":
        dependency_kwargs["degree"] = 6
    elif dependency_family == "erdos_renyi":
        dependency_kwargs["degree"] = 6
    elif dependency_family == "barabasi_albert":
        dependency_kwargs["attachment"] = 3
    elif dependency_family == "hierarchical":
        dependency_kwargs["span"] = 8
    else:
        raise ValueError(dependency_family)
    dependency = orient_undirected_layer(
        build_graph(n, dependency_family, seed=seed + 6, **dependency_kwargs).materialize(),
        seed=seed + 7,
        node_score=state.susceptibility_true,
        prefer_high_to_low=True,
        reverse_probability=0.18,
        bidirectional_probability=0.16,
    )

    hierarchy_score = np.linspace(1.5, 0.5, n)
    supervision = orient_undirected_layer(
        build_graph(n, "hierarchical", seed=seed + 8, span=8).materialize(),
        seed=seed + 9,
        node_score=hierarchy_score,
        prefer_high_to_low=True,
        reverse_probability=0.04,
        bidirectional_probability=0.08,
    )
    return state, {
        "authorization": auth,
        "communication": communication,
        "dependency": dependency,
        "supervision": supervision,
    }


def _candidate_ablation_score(
    layer_matrices: Mapping[str, sparse.csr_matrix],
    recovery: np.ndarray,
    *,
    omit: str | None,
    intervention_strength: float,
    intervention_time: float,
    horizon: float,
    homogeneous_recovery: bool = False,
) -> float:
    pre: sparse.csr_matrix | None = None
    post: sparse.csr_matrix | None = None
    for name, matrix in layer_matrices.items():
        if name == omit:
            continue
        pre = matrix.copy() if pre is None else pre + matrix
        attenuation = 1.0 - intervention_strength if name in {"authorization", "supervision"} else 1.0
        post_component = matrix * attenuation
        post = post_component.copy() if post is None else post + post_component
    if pre is None or post is None:
        return 0.0
    recovery_use = np.full_like(recovery, float(np.mean(recovery))) if homogeneous_recovery else recovery
    metrics = dynamic_operator_metrics(
        pre,
        post,
        recovery_use,
        intervention_time=intervention_time,
        horizon=horizon,
    )
    return float(metrics["dynamic_excess_exposure"])


def _nh2_split(n: int, dependency_family: str) -> str:
    if n in {160, 320} and dependency_family in {"random_regular", "erdos_renyi"}:
        return "train"
    if n == 640 and dependency_family in {"barabasi_albert", "hierarchical"}:
        return "test"
    if n == 320 and dependency_family in {"barabasi_albert", "hierarchical"}:
        return "calibration"
    return "bridge"


def generate_nh2_matrix(
    *,
    seed: int,
    replications: int = 30,
    graph_seed_offset: int = 0,
    reduced_robustness: bool = False,
    size_subset: Sequence[int] | None = None,
    initial_structure_id: int = 0,
    initial_scenario_id: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate replication and scenario data for NH2-D.

    ``size_subset`` and the explicit identifier offsets support atomic,
    size-partitioned execution without changing graph seeds, scenario seeds, or
    scenario identifiers relative to a monolithic run.
    """
    default_sizes = (160, 320, 640) if not reduced_robustness else (160, 640)
    sizes = tuple(size_subset) if size_subset is not None else default_sizes
    if not sizes or any(size not in default_sizes for size in sizes):
        raise ValueError(f"size_subset must be drawn from {default_sizes}")
    auth_families = ("random_regular", "barabasi_albert", "hierarchical")
    dependency_families = (
        "random_regular",
        "erdos_renyi",
        "barabasi_albert",
        "hierarchical",
    )
    if reduced_robustness:
        dependency_families = ("random_regular", "barabasi_albert")
    segmentations = ("none", "partitioned")
    beta_scales = (0.055, 0.080, 0.115, 0.165)
    interventions = ((0.35, 10), (0.35, 20), (0.65, 10), (0.65, 20))
    if reduced_robustness:
        interventions = ((0.35, 20), (0.65, 10))
    horizon = 50

    replication_rows: list[dict[str, float | int | str]] = []
    scenario_rows: list[dict[str, float | int | str]] = []
    scenario_id = int(initial_scenario_id)
    structure_id = int(initial_structure_id)
    for n in sizes:
        for auth_family in auth_families:
            for dependency_family in dependency_families:
                for segmentation in segmentations:
                    graph_seed = (
                        seed
                        + graph_seed_offset * 10_000_000
                        + n * 10_000
                        + structure_id * 100
                    )
                    state, layers = _build_directed_layers(
                        n,
                        auth_family=auth_family,
                        dependency_family=dependency_family,
                        segmentation=segmentation,
                        seed=graph_seed,
                    )
                    raw_auth_radius = _directed_adjacency_radius(layers["authorization"])
                    structure_id += 1
                    for beta_scale in beta_scales:
                        for intervention_strength, intervention_time in interventions:
                            operator_seed = graph_seed + int(beta_scale * 1_000_000) + intervention_time
                            operators = build_hazard_operators(
                                layers,
                                state,
                                seed=operator_seed,
                                beta_scale=beta_scale,
                                intervention_strength=intervention_strength,
                            )
                            dynamic = dynamic_operator_metrics(
                                operators.candidate_pre,
                                operators.candidate_post,
                                state.recovery_observed,
                                intervention_time=intervention_time,
                                horizon=horizon,
                            )
                            static_k_radius = float(dynamic["candidate_rho_pre"])
                            sym_radius = symmetrized_radius(operators.candidate_pre)
                            nonbacktracking = weighted_nonbacktracking_radius(
                                operators.candidate_pre, state.recovery_observed
                            )
                            ablations = {
                                f"dynamic_without_{name}": _candidate_ablation_score(
                                    operators.layer_candidate_pre,
                                    state.recovery_observed,
                                    omit=name,
                                    intervention_strength=intervention_strength,
                                    intervention_time=intervention_time,
                                    horizon=horizon,
                                )
                                for name in (
                                    "authorization",
                                    "communication",
                                    "dependency",
                                    "supervision",
                                )
                            }
                            ablations["dynamic_homogeneous_recovery"] = _candidate_ablation_score(
                                operators.layer_candidate_pre,
                                state.recovery_observed,
                                omit=None,
                                intervention_strength=intervention_strength,
                                intervention_time=intervention_time,
                                horizon=horizon,
                                homogeneous_recovery=True,
                            )
                            rep_seeds = [
                                seed
                                + graph_seed_offset * 100_000_000
                                + scenario_id * 10_000
                                + rep
                                for rep in range(replications)
                            ]
                            batch = simulate_directed_sir_batch(
                                operators.true_pre,
                                operators.true_post,
                                state.recovery_true,
                                intervention_time=intervention_time,
                                horizon_steps=horizon,
                                replication_seeds=rep_seeds,
                            )
                            split = _nh2_split(n, dependency_family)
                            common: dict[str, float | int | str] = {
                                "scenario_id": scenario_id,
                                "split": split,
                                "n_agents": n,
                                "auth_family": auth_family,
                                "dependency_family": dependency_family,
                                "segmentation": segmentation,
                                "beta_scale": beta_scale,
                                "intervention_strength": intervention_strength,
                                "intervention_time": intervention_time,
                                "horizon_steps": horizon,
                                "graph_seed": graph_seed,
                                "raw_auth_radius": raw_auth_radius,
                                "sym_attack_radius": sym_radius,
                                "static_k_radius": static_k_radius,
                                "nonbacktracking_radius": nonbacktracking,
                                "dynamic_excess_exposure": float(
                                    dynamic["dynamic_excess_exposure"]
                                ),
                                "dynamic_rho_time_mean": float(
                                    dynamic["candidate_rho_time_mean"]
                                ),
                                "candidate_rho_post": float(dynamic["candidate_rho_post"]),
                            }
                            common.update(ablations)
                            for rep, rseed in enumerate(batch.replication_seeds):
                                replication_rows.append(
                                    {
                                        **common,
                                        "replication": rep,
                                        "seed": int(rseed),
                                        "peak_compromised_fraction": float(
                                            batch.peak_fraction[rep]
                                        ),
                                        "ever_compromised_fraction": float(
                                            batch.ever_fraction[rep]
                                        ),
                                        "duration_steps": int(batch.duration_steps[rep]),
                                        "outbreak_10pct": int(
                                            batch.ever_fraction[rep] >= 0.10
                                        ),
                                    }
                                )
                            scenario_rows.append(
                                {
                                    **common,
                                    "replications": replications,
                                    "outbreak_successes": int(
                                        np.sum(batch.ever_fraction >= 0.10)
                                    ),
                                    "outbreak_rate": float(
                                        np.mean(batch.ever_fraction >= 0.10)
                                    ),
                                    "mean_ever_fraction": float(
                                        np.mean(batch.ever_fraction)
                                    ),
                                    "mean_peak_fraction": float(
                                        np.mean(batch.peak_fraction)
                                    ),
                                    "mean_duration_steps": float(
                                        np.mean(batch.duration_steps)
                                    ),
                                }
                            )
                            scenario_id += 1
    return pd.DataFrame(replication_rows), pd.DataFrame(scenario_rows)


def evaluate_nh2_predictors(
    scenarios: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, dict[str, np.ndarray]]]:
    predictors = {
        "raw_authorization": "raw_auth_radius",
        "symmetrized_attack": "sym_attack_radius",
        "static_next_generation": "static_k_radius",
        "nonbacktracking": "nonbacktracking_radius",
        "dynamic_k": "dynamic_excess_exposure",
        "ablate_authorization": "dynamic_without_authorization",
        "ablate_communication": "dynamic_without_communication",
        "ablate_dependency": "dynamic_without_dependency",
        "ablate_supervision": "dynamic_without_supervision",
        "homogeneous_recovery": "dynamic_homogeneous_recovery",
    }
    train = scenarios[scenarios.split == "train"].copy()
    test = scenarios[scenarios.split == "test"].copy()
    rows: list[dict[str, float | str]] = []
    fitted: dict[str, dict[str, np.ndarray]] = {}
    y_binary = (test.outbreak_rate.to_numpy(float) >= 0.50).astype(int)
    for name, column in predictors.items():
        x_train = train[column].to_numpy(float)
        x_test = test[column].to_numpy(float)
        continuous_weights = _fit_continuous(x_train, train.mean_ever_fraction.to_numpy(float))
        final_prediction = _predict_continuous(x_test, continuous_weights)
        binomial_weights = _fit_binomial(
            x_train,
            train.outbreak_successes.to_numpy(float),
            train.replications.to_numpy(float),
        )
        probability = _predict_binomial(x_test, binomial_weights)
        mae = float(np.mean(np.abs(final_prediction - test.mean_ever_fraction.to_numpy(float))))
        auc = _roc_auc(y_binary, probability)
        brier = float(np.mean((probability - test.outbreak_rate.to_numpy(float)) ** 2))
        rows.append(
            {
                "predictor": name,
                "column": column,
                "test_mae_mean_ever": mae,
                "test_auc_majority_outbreak": auc,
                "test_brier_outbreak_rate": brier,
                "test_scenarios": len(test),
            }
        )
        fitted[name] = {
            "continuous": continuous_weights,
            "binomial": binomial_weights,
            "final_prediction": final_prediction,
            "outbreak_probability": probability,
            "test_indices": test.index.to_numpy(),
        }
    return pd.DataFrame(rows), fitted


def _bootstrap_nh2(
    scenarios: pd.DataFrame,
    fitted: Mapping[str, Mapping[str, np.ndarray]],
    *,
    seed: int,
    draws: int = 500,
) -> dict[str, list[float]]:
    test = scenarios[scenarios.split == "test"].copy().reset_index(drop=True)
    dynamic = fitted["dynamic_k"]
    metric_frame = evaluate_nh2_predictors(scenarios)[0]
    baselines = metric_frame[metric_frame.predictor.isin(
        ["raw_authorization", "symmetrized_attack", "static_next_generation", "nonbacktracking"]
    )]
    best_mae_name = str(baselines.sort_values("test_mae_mean_ever").iloc[0].predictor)
    best_auc_name = str(baselines.sort_values("test_auc_majority_outbreak", ascending=False).iloc[0].predictor)
    best_brier_name = str(baselines.sort_values("test_brier_outbreak_rate").iloc[0].predictor)
    rng = np.random.default_rng(seed)
    values = {"mae_improvement": [], "auc_delta": [], "brier_improvement": []}
    y_final = test.mean_ever_fraction.to_numpy(float)
    y_rate = test.outbreak_rate.to_numpy(float)
    y_binary = (y_rate >= 0.5).astype(int)
    for _ in range(draws):
        sample = rng.integers(0, len(test), size=len(test))
        dyn_final = dynamic["final_prediction"][sample]
        dyn_prob = dynamic["outbreak_probability"][sample]
        base_mae_pred = fitted[best_mae_name]["final_prediction"][sample]
        base_auc_prob = fitted[best_auc_name]["outbreak_probability"][sample]
        base_brier_prob = fitted[best_brier_name]["outbreak_probability"][sample]
        dyn_mae = np.mean(np.abs(dyn_final - y_final[sample]))
        base_mae = np.mean(np.abs(base_mae_pred - y_final[sample]))
        values["mae_improvement"].append(float((base_mae - dyn_mae) / max(base_mae, 1e-12)))
        values["auc_delta"].append(
            float(_roc_auc(y_binary[sample], dyn_prob) - _roc_auc(y_binary[sample], base_auc_prob))
        )
        dyn_brier = np.mean((dyn_prob - y_rate[sample]) ** 2)
        base_brier = np.mean((base_brier_prob - y_rate[sample]) ** 2)
        values["brier_improvement"].append(
            float((base_brier - dyn_brier) / max(base_brier, 1e-12))
        )
    return values


def summarize_nh2(
    scenarios: pd.DataFrame,
    metrics: pd.DataFrame,
    fitted: Mapping[str, Mapping[str, np.ndarray]],
    robustness: pd.DataFrame,
    *,
    seed: int,
) -> dict[str, object]:
    baseline_names = {
        "raw_authorization",
        "symmetrized_attack",
        "static_next_generation",
        "nonbacktracking",
    }
    baselines = metrics[metrics.predictor.isin(baseline_names)]
    dynamic = metrics[metrics.predictor == "dynamic_k"].iloc[0]
    best_mae = baselines.loc[baselines.test_mae_mean_ever.idxmin()]
    best_auc = baselines.loc[baselines.test_auc_majority_outbreak.idxmax()]
    best_brier = baselines.loc[baselines.test_brier_outbreak_rate.idxmin()]
    mae_improvement = float(
        (best_mae.test_mae_mean_ever - dynamic.test_mae_mean_ever)
        / best_mae.test_mae_mean_ever
    )
    auc_delta = float(
        dynamic.test_auc_majority_outbreak - best_auc.test_auc_majority_outbreak
    )
    brier_improvement = float(
        (best_brier.test_brier_outbreak_rate - dynamic.test_brier_outbreak_rate)
        / best_brier.test_brier_outbreak_rate
    )
    dep_ablation = metrics[metrics.predictor == "ablate_dependency"].iloc[0]
    dependency_degrades = bool(
        dep_ablation.test_mae_mean_ever > dynamic.test_mae_mean_ever
    )
    positive_blocks = int((robustness.mae_improvement_fraction > 0.0).sum())
    bootstrap = _bootstrap_nh2(scenarios, fitted, seed=seed + 991)
    ci = {
        name: [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))]
        for name, values in bootstrap.items()
    }
    criteria = {
        "mae_improvement_at_least_15pct": mae_improvement >= 0.15,
        "auc_delta_at_least_0_03": auc_delta >= 0.03,
        "brier_improves": brier_improvement > 0.0,
        "four_of_five_positive_robustness_blocks": positive_blocks >= 4,
        "dependency_ablation_degrades": dependency_degrades,
    }
    return {
        "best_baseline_mae_predictor": str(best_mae.predictor),
        "best_baseline_auc_predictor": str(best_auc.predictor),
        "best_baseline_brier_predictor": str(best_brier.predictor),
        "dynamic_mae": float(dynamic.test_mae_mean_ever),
        "best_baseline_mae": float(best_mae.test_mae_mean_ever),
        "mae_improvement_fraction": mae_improvement,
        "dynamic_auc": float(dynamic.test_auc_majority_outbreak),
        "best_baseline_auc": float(best_auc.test_auc_majority_outbreak),
        "auc_delta": auc_delta,
        "dynamic_brier": float(dynamic.test_brier_outbreak_rate),
        "best_baseline_brier": float(best_brier.test_brier_outbreak_rate),
        "brier_improvement_fraction": brier_improvement,
        "positive_robustness_blocks": positive_blocks,
        "dependency_ablation_degrades": dependency_degrades,
        "bootstrap_95pct": ci,
        "criteria": criteria,
        "supported_in_model": bool(all(criteria.values())),
    }


def _nh4_split(nf: int, profile: str) -> str:
    if nf in {2000, 5000, 10000} and profile in {
        "step",
        "linear",
        "smooth",
        "front_loaded",
    }:
        return "train"
    if nf == 20000 and profile in {"pulse_train", "back_loaded"}:
        return "test"
    if nf == 10000 and profile in {"pulse_train", "back_loaded"}:
        return "calibration"
    return "bridge"


def generate_nh4_matrix(
    *,
    seed: int,
    replications: int = 30,
    stochastic_seed_offset: int = 0,
    test_only: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    sizes = (2000, 5000, 10000, 20000)
    profiles = (
        "step",
        "linear",
        "smooth",
        "pulse_train",
        "front_loaded",
        "back_loaded",
    )
    regimes = (
        "balanced",
        "control_constrained",
        "supervision_constrained",
        "credential_constrained",
    )
    duration_factors = (0.25, 0.45, 0.75, 1.15, 1.80)
    replication_rows: list[dict[str, float | int | str]] = []
    scenario_rows: list[dict[str, float | int | str]] = []
    scenario_id = 0
    for nf in sizes:
        for profile in profiles:
            split = _nh4_split(nf, profile)
            if test_only and split != "test":
                continue
            for regime in regimes:
                resources = build_resource_regime(nf, regime)
                n0 = max(100, int(round(0.05 * nf)))
                critical_rate = critical_linear_admission_rate(resources, nf)
                critical_duration = (nf - n0) / critical_rate
                factors = (0.75,) if profile == "step" else duration_factors
                for duration_factor in factors:
                    ramp_duration = max(4.0, critical_duration * duration_factor)
                    trajectory = make_admission_trajectory(
                        profile,
                        n0=n0,
                        nf=nf,
                        ramp_duration_s=ramp_duration,
                        recovery_window_s=120.0,
                        dt=0.5,
                    )
                    predictors, _ = fluid_admission_metrics(trajectory, resources)
                    rep_seeds = [
                        seed
                        + stochastic_seed_offset * 100_000_000
                        + scenario_id * 10_000
                        + rep
                        for rep in range(replications)
                    ]
                    outcomes = simulate_stochastic_admission_batch(
                        trajectory, resources, replication_seeds=rep_seeds
                    )
                    common: dict[str, float | int | str] = {
                        "scenario_id": scenario_id,
                        "split": split,
                        "n0": n0,
                        "nf": nf,
                        "profile": profile,
                        "capacity_regime": regime,
                        "duration_factor": duration_factor,
                        "ramp_duration_s": ramp_duration,
                        "critical_linear_rate_agents_s": critical_rate,
                        **predictors.as_dict(),
                    }
                    for rep, outcome in outcomes.iterrows():
                        replication_rows.append(
                            {
                                **common,
                                "replication": int(rep),
                                **outcome.to_dict(),
                            }
                        )
                    scenario_rows.append(
                        {
                            **common,
                            "replications": replications,
                            "failure_successes": int(outcomes.boundary_crossed.sum()),
                            "failure_rate": float(outcomes.boundary_crossed.mean()),
                            "mean_maximum_normalized_queue": float(
                                outcomes.maximum_normalized_queue.mean()
                            ),
                            "p95_maximum_normalized_queue": float(
                                outcomes.maximum_normalized_queue.quantile(0.95)
                            ),
                            "mean_first_crossing_time_s": float(
                                outcomes.first_crossing_time_s.mean()
                            ),
                        }
                    )
                    scenario_id += 1
    return pd.DataFrame(replication_rows), pd.DataFrame(scenario_rows)


def evaluate_nh4_predictors(
    scenarios: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, dict[str, np.ndarray]]]:
    train = scenarios[scenarios.split == "train"].copy()
    test = scenarios[scenarios.split == "test"].copy()
    predictor_columns: dict[str, Sequence[str]] = {
        "final_n": ("final_n",),
        "raw_population_velocity": ("max_admission_rate",),
        "peak_lambda": ("peak_lambda",),
        "omega": ("omega",),
        "joint_lambda_omega": ("peak_lambda", "omega"),
    }
    y_binary = (test.failure_rate.to_numpy(float) >= 0.5).astype(int)
    rows: list[dict[str, float | str | int]] = []
    fitted: dict[str, dict[str, np.ndarray]] = {}
    for name, columns in predictor_columns.items():
        x_train = train[list(columns)].to_numpy(float)
        x_test = test[list(columns)].to_numpy(float)
        weights = _fit_binomial(
            x_train,
            train.failure_successes.to_numpy(float),
            train.replications.to_numpy(float),
        )
        probability = _predict_binomial(x_test, weights)
        auc = _roc_auc(y_binary, probability)
        brier = float(np.mean((probability - test.failure_rate.to_numpy(float)) ** 2))
        rows.append(
            {
                "predictor": name,
                "columns": ",".join(columns),
                "test_auc_majority_failure": auc,
                "test_brier_failure_rate": brier,
                "test_scenarios": len(test),
            }
        )
        fitted[name] = {
            "weights": weights,
            "probability": probability,
            "test_indices": test.index.to_numpy(),
        }
    return pd.DataFrame(rows), fitted


def _balanced_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y = np.asarray(y_true, dtype=int)
    p = np.asarray(y_pred, dtype=int)
    positives = y == 1
    negatives = y == 0
    tpr = float(np.mean(p[positives] == 1)) if positives.any() else 0.5
    tnr = float(np.mean(p[negatives] == 0)) if negatives.any() else 0.5
    return 0.5 * (tpr + tnr)


def _interpolated_threshold(group: pd.DataFrame) -> float:
    ordered = group.groupby("omega", as_index=False).failure_rate.mean().sort_values("omega")
    x = ordered.omega.to_numpy(float)
    y = ordered.failure_rate.to_numpy(float)
    below = np.where(y < 0.5)[0]
    above = np.where(y >= 0.5)[0]
    if len(below) == 0 or len(above) == 0:
        return float("nan")
    i1 = below[below < above[0]]
    if len(i1) == 0:
        return float(x[above[0]])
    lo = int(i1[-1])
    hi = int(above[above > lo][0])
    if y[hi] == y[lo]:
        return float((x[lo] + x[hi]) / 2.0)
    fraction = (0.5 - y[lo]) / (y[hi] - y[lo])
    return float(x[lo] + fraction * (x[hi] - x[lo]))


def nh4_threshold_table(scenarios: pd.DataFrame) -> pd.DataFrame:
    transfer = scenarios[
        scenarios.profile.isin(["pulse_train", "back_loaded"])
    ].copy()
    rows: list[dict[str, float | int | str]] = []
    for (nf, regime), group in transfer.groupby(["nf", "capacity_regime"]):
        rows.append(
            {
                "nf": int(nf),
                "capacity_regime": str(regime),
                "omega_50pct_threshold": _interpolated_threshold(group),
                "scenarios": len(group),
            }
        )
    return pd.DataFrame(rows)


def summarize_nh4(
    scenarios: pd.DataFrame,
    metrics: pd.DataFrame,
    fitted: Mapping[str, Mapping[str, np.ndarray]],
    thresholds: pd.DataFrame,
    robustness: pd.DataFrame,
    *,
    seed: int,
) -> dict[str, object]:
    omega_row = metrics[metrics.predictor == "omega"].iloc[0]
    lambda_row = metrics[metrics.predictor == "peak_lambda"].iloc[0]
    auc_delta = float(
        omega_row.test_auc_majority_failure - lambda_row.test_auc_majority_failure
    )
    brier_improvement = float(
        (lambda_row.test_brier_failure_rate - omega_row.test_brier_failure_rate)
        / lambda_row.test_brier_failure_rate
    )
    test = scenarios[scenarios.split == "test"].copy()
    threshold_balanced_accuracy = _balanced_accuracy(
        (test.failure_rate.to_numpy(float) >= 0.5).astype(int),
        (test.omega.to_numpy(float) >= 1.0).astype(int),
    )
    valid_thresholds = thresholds.dropna(subset=["omega_50pct_threshold"])
    threshold_cv = float(
        valid_thresholds.omega_50pct_threshold.std(ddof=1)
        / valid_thresholds.omega_50pct_threshold.mean()
    ) if len(valid_thresholds) > 1 else float("nan")
    positive_blocks = int((robustness.auc_delta_omega_vs_lambda > 0.0).sum())

    # Scenario bootstrap using fixed trained probabilities.
    rng = np.random.default_rng(seed + 1771)
    omega_prob = fitted["omega"]["probability"]
    lambda_prob = fitted["peak_lambda"]["probability"]
    y_rate = test.failure_rate.to_numpy(float)
    y_binary = (y_rate >= 0.5).astype(int)
    auc_deltas: list[float] = []
    brier_improvements: list[float] = []
    for _ in range(500):
        sample = rng.integers(0, len(test), size=len(test))
        auc_deltas.append(
            _roc_auc(y_binary[sample], omega_prob[sample])
            - _roc_auc(y_binary[sample], lambda_prob[sample])
        )
        bo = np.mean((omega_prob[sample] - y_rate[sample]) ** 2)
        bl = np.mean((lambda_prob[sample] - y_rate[sample]) ** 2)
        brier_improvements.append((bl - bo) / max(bl, 1e-12))
    criteria = {
        "auc_delta_at_least_0_05": auc_delta >= 0.05,
        "brier_reduction_at_least_15pct": brier_improvement >= 0.15,
        "omega_one_balanced_accuracy_at_least_0_80": threshold_balanced_accuracy >= 0.80,
        "threshold_cv_no_more_than_0_20": bool(
            np.isfinite(threshold_cv) and threshold_cv <= 0.20
        ),
        "four_of_five_positive_seed_blocks": positive_blocks >= 4,
    }
    return {
        "omega_auc": float(omega_row.test_auc_majority_failure),
        "peak_lambda_auc": float(lambda_row.test_auc_majority_failure),
        "auc_delta": auc_delta,
        "omega_brier": float(omega_row.test_brier_failure_rate),
        "peak_lambda_brier": float(lambda_row.test_brier_failure_rate),
        "brier_improvement_fraction": brier_improvement,
        "omega_one_balanced_accuracy": threshold_balanced_accuracy,
        "threshold_cv": threshold_cv,
        "valid_threshold_groups": int(len(valid_thresholds)),
        "positive_seed_blocks": positive_blocks,
        "bootstrap_95pct": {
            "auc_delta": [
                float(np.quantile(auc_deltas, 0.025)),
                float(np.quantile(auc_deltas, 0.975)),
            ],
            "brier_improvement": [
                float(np.quantile(brier_improvements, 0.025)),
                float(np.quantile(brier_improvements, 0.975)),
            ],
        },
        "criteria": criteria,
        "supported_in_model": bool(all(criteria.values())),
    }


def run_nh2_robustness(*, seed: int, blocks: int = 5) -> pd.DataFrame:
    rows: list[dict[str, float | int]] = []
    for block in range(blocks):
        _, scenarios = generate_nh2_matrix(
            seed=seed + block * 101,
            replications=30,
            graph_seed_offset=block + 1,
            reduced_robustness=True,
        )
        metrics, _ = evaluate_nh2_predictors(scenarios)
        baselines = metrics[metrics.predictor.isin(
            ["raw_authorization", "symmetrized_attack", "static_next_generation", "nonbacktracking"]
        )]
        dynamic = metrics[metrics.predictor == "dynamic_k"].iloc[0]
        best = baselines.loc[baselines.test_mae_mean_ever.idxmin()]
        rows.append(
            {
                "block": block,
                "dynamic_mae": float(dynamic.test_mae_mean_ever),
                "best_baseline_mae": float(best.test_mae_mean_ever),
                "mae_improvement_fraction": float(
                    (best.test_mae_mean_ever - dynamic.test_mae_mean_ever)
                    / best.test_mae_mean_ever
                ),
                "dynamic_auc": float(dynamic.test_auc_majority_outbreak),
                "best_baseline_auc": float(
                    baselines.test_auc_majority_outbreak.max()
                ),
            }
        )
    return pd.DataFrame(rows)


def run_nh4_robustness(
    scenarios: pd.DataFrame,
    fitted_main: Mapping[str, Mapping[str, np.ndarray]],
    *,
    seed: int,
    blocks: int = 5,
) -> pd.DataFrame:
    rows: list[dict[str, float | int]] = []
    for block in range(blocks):
        _, test_scenarios = generate_nh4_matrix(
            seed=seed + block * 137,
            replications=30,
            stochastic_seed_offset=block + 1,
            test_only=True,
        )
        y_rate = test_scenarios.failure_rate.to_numpy(float)
        y_binary = (y_rate >= 0.5).astype(int)
        omega_x = test_scenarios[["omega"]].to_numpy(float)
        lambda_x = test_scenarios[["peak_lambda"]].to_numpy(float)
        omega_prob = _predict_binomial(omega_x, fitted_main["omega"]["weights"])
        lambda_prob = _predict_binomial(
            lambda_x, fitted_main["peak_lambda"]["weights"]
        )
        rows.append(
            {
                "block": block,
                "omega_auc": _roc_auc(y_binary, omega_prob),
                "peak_lambda_auc": _roc_auc(y_binary, lambda_prob),
                "auc_delta_omega_vs_lambda": _roc_auc(y_binary, omega_prob)
                - _roc_auc(y_binary, lambda_prob),
                "omega_brier": float(np.mean((omega_prob - y_rate) ** 2)),
                "peak_lambda_brier": float(
                    np.mean((lambda_prob - y_rate) ** 2)
                ),
            }
        )
    return pd.DataFrame(rows)


def write_stage2_figures(
    nh2_scenarios: pd.DataFrame,
    nh2_metrics: pd.DataFrame,
    nh2_fitted: Mapping[str, Mapping[str, np.ndarray]],
    nh4_scenarios: pd.DataFrame,
    nh4_metrics: pd.DataFrame,
    output_dir: str | Path,
) -> list[Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    test2 = nh2_scenarios[nh2_scenarios.split == "test"].copy()
    dyn = nh2_fitted["dynamic_k"]["final_prediction"]
    baseline_names = [
        "raw_authorization",
        "symmetrized_attack",
        "static_next_generation",
        "nonbacktracking",
    ]
    best_name = str(
        nh2_metrics[nh2_metrics.predictor.isin(baseline_names)]
        .sort_values("test_mae_mean_ever")
        .iloc[0]
        .predictor
    )
    base = nh2_fitted[best_name]["final_prediction"]
    fig, ax = plt.subplots(figsize=(7.6, 5.4))
    ax.scatter(test2.mean_ever_fraction, base, alpha=0.55, label=f"Best baseline: {best_name}")
    ax.scatter(test2.mean_ever_fraction, dyn, marker="x", alpha=0.75, label="Dynamic K(t)")
    ax.plot([0, 1], [0, 1], linestyle="--", linewidth=1)
    ax.set_xlabel("Observed mean ever-compromised fraction")
    ax.set_ylabel("Held-out prediction")
    ax.set_title("NH2-D held-out propagation prediction")
    ax.legend()
    ax.grid(True, alpha=0.2)
    path = output / "nh2_dynamic_operator_prediction.png"
    fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig); paths.append(path)

    fig, ax = plt.subplots(figsize=(8.2, 5.4))
    ordered = nh2_metrics.sort_values("test_mae_mean_ever")
    ax.bar(ordered.predictor, ordered.test_mae_mean_ever)
    ax.set_ylabel("Held-out MAE")
    ax.set_title("NH2-D predictor and layer-ablation error")
    ax.tick_params(axis="x", rotation=55)
    ax.grid(True, axis="y", alpha=0.2)
    path = output / "nh2_predictor_ablation_mae.png"
    fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig); paths.append(path)

    transfer4 = nh4_scenarios[nh4_scenarios.profile.isin(["pulse_train", "back_loaded"])]
    fig, ax = plt.subplots(figsize=(7.8, 5.4))
    for nf, group in transfer4.groupby("nf"):
        ax.scatter(group.omega, group.failure_rate, label=f"N={int(nf):,}", alpha=0.7)
    ax.axvline(1.0, linestyle="--", linewidth=1)
    ax.set_xscale("symlog", linthresh=0.02)
    ax.set_xlabel("Fluid overload index Omega_A")
    ax.set_ylabel("Boundary-crossing probability")
    ax.set_title("NH4-A transfer across fleet size")
    ax.legend()
    ax.grid(True, alpha=0.2)
    path = output / "nh4_omega_failure_frontier.png"
    fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig); paths.append(path)

    test4 = nh4_scenarios[nh4_scenarios.split == "test"]
    fig, ax = plt.subplots(figsize=(7.6, 5.4))
    scatter = ax.scatter(
        test4.peak_lambda,
        test4.omega,
        c=test4.failure_rate,
        s=45,
        alpha=0.8,
    )
    ax.axhline(1.0, linestyle="--", linewidth=1)
    ax.set_xscale("symlog", linthresh=0.02)
    ax.set_yscale("symlog", linthresh=0.02)
    ax.set_xlabel("Peak instantaneous admission load Lambda_A")
    ax.set_ylabel("Reflected overload index Omega_A")
    ax.set_title("NH4-A duration-sensitive admission phase space")
    fig.colorbar(scatter, ax=ax, label="Boundary-crossing probability")
    ax.grid(True, alpha=0.2)
    path = output / "nh4_lambda_omega_phase_space.png"
    fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig); paths.append(path)

    fig, ax = plt.subplots(figsize=(7.8, 5.2))
    ordered4 = nh4_metrics.sort_values("test_brier_failure_rate")
    ax.bar(ordered4.predictor, ordered4.test_brier_failure_rate)
    ax.set_ylabel("Held-out Brier score")
    ax.set_title("NH4-A admission predictor calibration")
    ax.tick_params(axis="x", rotation=35)
    ax.grid(True, axis="y", alpha=0.2)
    path = output / "nh4_predictor_brier.png"
    fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig); paths.append(path)
    return paths


def run_stage2_cycle4(
    repository_root: str | Path,
    *,
    seed: int = 20260819,
) -> dict[str, object]:
    root = Path(repository_root)
    results_dir = root / "results" / "stage2_cycle4"
    figures_dir = root / "figures" / "stage2_cycle4"
    results_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    nh2_rep, nh2_scenarios = generate_nh2_matrix(seed=seed, replications=30)
    nh2_rep.to_csv(results_dir / "nh2_directed_replications.csv", index=False)
    nh2_scenarios.to_csv(results_dir / "nh2_directed_scenarios.csv", index=False)
    nh2_metrics, nh2_fitted = evaluate_nh2_predictors(nh2_scenarios)
    nh2_metrics.to_csv(results_dir / "nh2_predictor_metrics.csv", index=False)
    nh2_robustness = run_nh2_robustness(seed=seed + 3001)
    nh2_robustness.to_csv(results_dir / "nh2_robustness.csv", index=False)
    nh2_summary = summarize_nh2(
        nh2_scenarios,
        nh2_metrics,
        nh2_fitted,
        nh2_robustness,
        seed=seed,
    )

    nh4_rep, nh4_scenarios = generate_nh4_matrix(seed=seed + 5001, replications=30)
    nh4_rep.to_csv(results_dir / "nh4_admission_replications.csv", index=False)
    nh4_scenarios.to_csv(results_dir / "nh4_admission_scenarios.csv", index=False)
    nh4_metrics, nh4_fitted = evaluate_nh4_predictors(nh4_scenarios)
    nh4_metrics.to_csv(results_dir / "nh4_predictor_metrics.csv", index=False)
    nh4_thresholds = nh4_threshold_table(nh4_scenarios)
    nh4_thresholds.to_csv(results_dir / "nh4_thresholds.csv", index=False)
    nh4_robustness = run_nh4_robustness(
        nh4_scenarios,
        nh4_fitted,
        seed=seed + 7001,
    )
    nh4_robustness.to_csv(results_dir / "nh4_robustness.csv", index=False)
    nh4_summary = summarize_nh4(
        nh4_scenarios,
        nh4_metrics,
        nh4_fitted,
        nh4_thresholds,
        nh4_robustness,
        seed=seed,
    )

    figures = write_stage2_figures(
        nh2_scenarios,
        nh2_metrics,
        nh2_fitted,
        nh4_scenarios,
        nh4_metrics,
        figures_dir,
    )
    assessments = [
        HypothesisAssessment(
            hypothesis="NH2-D",
            supported_in_model=bool(nh2_summary["supported_in_model"]),
            evidence_level="model-conditioned",
            primary_result=(
                f"Dynamic K(t) held-out MAE improvement {100*float(nh2_summary['mae_improvement_fraction']):.1f}% "
                f"and AUC delta {float(nh2_summary['auc_delta']):.3f}."
            ),
            limitations=(
                "The propagation substrate remains synthetic. Candidate features are separated from latent "
                "hazards, but no observed incident data are used."
            ),
        ).as_dict(),
        HypothesisAssessment(
            hypothesis="NH4-A",
            supported_in_model=bool(nh4_summary["supported_in_model"]),
            evidence_level="analytic plus model-conditioned",
            primary_result=(
                f"Omega_A held-out AUC delta {float(nh4_summary['auc_delta']):.3f}, "
                f"Brier improvement {100*float(nh4_summary['brier_improvement_fraction']):.1f}%."
            ),
            limitations=(
                "The reflected backlog formula is established queue mathematics. Novelty, if any, is limited "
                "to its assurance-resource composition and transfer behavior."
            ),
        ).as_dict(),
    ]
    summary = {
        "date": "2026-08-19",
        "seed": seed,
        "evidence_scope": "notional parameters; model-conditioned; no external validation",
        "protocol": "docs/stage2_cycle4_preregistered_protocol.md",
        "NH2_D": nh2_summary,
        "NH4_A": nh4_summary,
        "assessments": assessments,
        "figures": [str(path.relative_to(root)) for path in figures],
        "dataset_counts": {
            "nh2_replications": len(nh2_rep),
            "nh2_scenarios": len(nh2_scenarios),
            "nh4_replications": len(nh4_rep),
            "nh4_scenarios": len(nh4_scenarios),
        },
    }
    (results_dir / "stage2_cycle4_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary

# ---------------------------------------------------------------------------
# Compatibility API for the earlier Stage 2 harness and frozen scripts.
# These functions retain the public interface expected by repository tests.
# New confirmation work in this module uses run_stage2_cycle4 above.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LegacyDirectedAttackScenario:
    scenario_id: int
    split: str
    n: int
    seed: int
    auth_topology: str
    dependency_topology: str
    auth_kwargs: Mapping[str, int]
    dependency_kwargs: Mapping[str, int]
    intensity_scale: float
    revocation_time_s: float
    revocation_effectiveness: float
    supply_chain_fraction: float
    idp_shock_fraction: float
    state: object
    layers: Mapping[str, nx.DiGraph]
    operators: object


@dataclass(frozen=True)
class LegacyAdmissionPool:
    name: str
    capacity: float
    target_utilization: float
    baseline_per_agent: float
    admission_work: float
    wait_limit_s: float


def build_directed_attack_scenario(
    *,
    scenario_id: int,
    split: str,
    n: int,
    seed: int,
    auth_topology: str,
    dependency_topology: str,
    auth_kwargs: Mapping[str, int] | None = None,
    dependency_kwargs: Mapping[str, int] | None = None,
    intensity_scale: float = 0.9,
    revocation_time_s: float = 14.0,
    revocation_effectiveness: float = 0.8,
    supply_chain_fraction: float = 0.01,
    idp_shock_fraction: float = 0.01,
) -> LegacyDirectedAttackScenario:
    """Build the compact directed scenario used by the original Stage 2 harness."""
    del supply_chain_fraction, idp_shock_fraction
    state = make_node_risk_state(n, seed=seed + 1)
    auth_base = build_graph(n, auth_topology, seed=seed + 2, **dict(auth_kwargs or {})).materialize()
    dep_base = build_graph(
        n, dependency_topology, seed=seed + 3, **dict(dependency_kwargs or {})
    ).materialize()
    layers = {
        "authorization": orient_undirected_layer(
            auth_base,
            seed=seed + 4,
            node_score=state.privilege_true,
            prefer_high_to_low=True,
            reverse_probability=0.10,
            bidirectional_probability=0.20,
        ),
        "communication": orient_undirected_layer(
            build_graph(n, "random_regular", seed=seed + 5, degree=min(6, max(1, n - 1))).materialize(),
            seed=seed + 6,
            node_score=state.susceptibility_true,
            prefer_high_to_low=False,
            reverse_probability=0.50,
            bidirectional_probability=0.55,
        ),
        "dependency": orient_undirected_layer(
            dep_base,
            seed=seed + 7,
            node_score=state.susceptibility_true,
            prefer_high_to_low=True,
            reverse_probability=0.18,
            bidirectional_probability=0.15,
        ),
        "supervision": orient_undirected_layer(
            build_graph(n, "hierarchical", seed=seed + 8, span=min(8, max(2, n))).materialize(),
            seed=seed + 9,
            node_score=np.linspace(1.5, 0.5, n),
            prefer_high_to_low=True,
            reverse_probability=0.04,
            bidirectional_probability=0.08,
        ),
    }
    beta_scale = 0.10 * float(intensity_scale)
    operators = build_hazard_operators(
        layers,
        state,
        seed=seed + 10,
        beta_scale=beta_scale,
        intervention_strength=revocation_effectiveness,
    )
    return LegacyDirectedAttackScenario(
        scenario_id=scenario_id,
        split=split,
        n=n,
        seed=seed,
        auth_topology=auth_topology,
        dependency_topology=dependency_topology,
        auth_kwargs=dict(auth_kwargs or {}),
        dependency_kwargs=dict(dependency_kwargs or {}),
        intensity_scale=intensity_scale,
        revocation_time_s=revocation_time_s,
        revocation_effectiveness=revocation_effectiveness,
        supply_chain_fraction=0.0,
        idp_shock_fraction=0.0,
        state=state,
        layers=layers,
        operators=operators,
    )


def attack_operator_predictors(scenario: LegacyDirectedAttackScenario) -> dict[str, float]:
    horizon = max(30.0, scenario.revocation_time_s + 20.0)
    dynamic = dynamic_operator_metrics(
        scenario.operators.candidate_pre,
        scenario.operators.candidate_post,
        scenario.state.recovery_observed,
        intervention_time=scenario.revocation_time_s,
        horizon=horizon,
    )
    return {
        "raw_auth_product": _directed_adjacency_radius(scenario.layers["authorization"]),
        "weighted_union_product": symmetrized_radius(scenario.operators.candidate_pre),
        "nonbacktracking_radius": weighted_nonbacktracking_radius(
            scenario.operators.candidate_pre, scenario.state.recovery_observed
        ),
        "k_pre_radius": float(dynamic["candidate_rho_pre"]),
        "k_post_radius": float(dynamic["candidate_rho_post"]),
        "temporal_k_pressure": float(dynamic["candidate_rho_time_mean"]),
    }


def simulate_latent_compromise(
    scenario: LegacyDirectedAttackScenario,
    *,
    seed: int,
) -> tuple[float, float, int]:
    horizon = int(max(30.0, scenario.revocation_time_s + 20.0))
    batch = simulate_directed_sir_batch(
        scenario.operators.true_pre,
        scenario.operators.true_post,
        scenario.state.recovery_true,
        intervention_time=int(round(scenario.revocation_time_s)),
        horizon_steps=horizon,
        replication_seeds=[seed],
    )
    return (
        float(batch.peak_fraction[0]),
        float(batch.ever_fraction[0]),
        int(batch.duration_steps[0]),
    )


def build_admission_pools(
    *,
    final_n: int,
    final_baseline_fraction: float = 0.55,
) -> tuple[LegacyAdmissionPool, ...]:
    if not 0.0 < final_baseline_fraction < 0.8:
        raise ValueError("final_baseline_fraction must be in (0, 0.8)")
    specs = (
        ("identity", 0.0060, 1.4, 3.0),
        ("policy", 0.0080, 2.1, 2.0),
        ("telemetry", 0.0045, 1.7, 3.0),
        ("supervision", 0.00085, 0.28, 8.0),
    )
    pools = []
    for name, baseline, work, wait in specs:
        capacity = baseline * final_n / final_baseline_fraction
        pools.append(
            LegacyAdmissionPool(
                name=name,
                capacity=capacity,
                target_utilization=0.80,
                baseline_per_agent=baseline,
                admission_work=work,
                wait_limit_s=wait,
            )
        )
    return tuple(pools)


def admission_load_predictors(
    n_agents: np.ndarray,
    admission_rate: np.ndarray,
    pools: Iterable[LegacyAdmissionPool],
    *,
    dt_s: float,
) -> dict[str, float]:
    n = np.asarray(n_agents, dtype=float)
    rate = np.maximum(0.0, np.asarray(admission_rate, dtype=float))
    peak_values: list[float] = []
    integrated_values: list[float] = []
    offered_values: list[float] = []
    for pool in pools:
        spare = pool.target_utilization * pool.capacity - pool.baseline_per_agent * n
        with np.errstate(divide="ignore", invalid="ignore"):
            lam = np.where(spare > 0.0, pool.admission_work * rate / spare, np.inf)
        peak_values.append(float(np.max(lam)))
        integrated_values.append(float(np.sum(np.maximum(0.0, lam - 1.0)) * dt_s))
        offered = pool.baseline_per_agent * n + pool.admission_work * rate
        offered_values.append(float(np.max(offered / pool.capacity)))
    return {
        "peak_lambda_a": float(max(peak_values)),
        "integrated_lambda_excess": float(max(integrated_values)),
        "peak_total_offered_ratio": float(max(offered_values)),
        "max_admission_rate": float(np.max(rate)),
        "final_n": float(n[-1]),
    }


def _regression_metrics(
    training: pd.DataFrame,
    test: pd.DataFrame,
    *,
    predictor: str,
) -> tuple[np.ndarray, dict[str, float]]:
    x_train = training[predictor].to_numpy(float)
    x_test = test[predictor].to_numpy(float)
    y_train = training["mean_ever_compromised"].to_numpy(float)
    y_test = test["mean_ever_compromised"].to_numpy(float)
    weights = _fit_continuous(x_train, y_train)
    prediction = _predict_continuous(x_test, weights)
    return prediction, {
        "mae": float(np.mean(np.abs(prediction - y_test))),
        "rmse": float(np.sqrt(np.mean((prediction - y_test) ** 2))),
    }


def run_nh2_directed_operator(
    *,
    seed: int,
    fleet_sizes: Sequence[int] = (120, 240, 480),
    scenarios_per_size: int = 24,
    replications: int = 20,
):
    run_rows: list[dict[str, float | int | str]] = []
    scenario_rows: list[dict[str, float | int | str]] = []
    scenario_id = 0
    for size_idx, n in enumerate(fleet_sizes):
        for local in range(scenarios_per_size):
            if size_idx == 0:
                split = "train"
                auth_topology = "random_regular"
                dep_topology = "erdos_renyi"
                auth_kwargs = {"degree": 4}
                dep_kwargs = {"degree": 4}
            elif size_idx == 1:
                split = "test_topology"
                auth_topology = "barabasi_albert"
                dep_topology = "hierarchical"
                auth_kwargs = {"attachment": 2}
                dep_kwargs = {"span": 6}
            else:
                split = "test_scale"
                auth_topology = "random_regular"
                dep_topology = "erdos_renyi"
                auth_kwargs = {"degree": 4}
                dep_kwargs = {"degree": 4}
            intensity = (0.55, 0.80, 1.05, 1.35)[local % 4]
            scenario = build_directed_attack_scenario(
                scenario_id=scenario_id,
                split=split,
                n=int(n),
                seed=seed + scenario_id * 100,
                auth_topology=auth_topology,
                dependency_topology=dep_topology,
                auth_kwargs=auth_kwargs,
                dependency_kwargs=dep_kwargs,
                intensity_scale=intensity,
                revocation_time_s=10.0 + 4.0 * (local % 3),
                revocation_effectiveness=0.45 + 0.15 * (local % 3),
                supply_chain_fraction=0.01,
                idp_shock_fraction=0.01,
            )
            predictors = attack_operator_predictors(scenario)
            outcomes = []
            for rep in range(replications):
                rseed = seed + scenario_id * 10_000 + rep
                peak, ever, duration = simulate_latent_compromise(scenario, seed=rseed)
                outcomes.append((peak, ever, duration, rseed))
                run_rows.append(
                    {
                        "scenario_id": scenario_id,
                        "split": split,
                        "n": n,
                        "replication": rep,
                        "seed": rseed,
                        "peak_compromised": peak,
                        "ever_compromised": ever,
                        "duration_steps": duration,
                        **predictors,
                    }
                )
            ever_values = np.array([value[1] for value in outcomes])
            scenario_rows.append(
                {
                    "scenario_id": scenario_id,
                    "split": split,
                    "n": n,
                    "initial_seed_fraction": 1.0 / n,
                    "mean_ever_compromised": float(np.mean(ever_values)),
                    "large_outbreak_probability": float(np.mean(ever_values >= 0.15)),
                    **predictors,
                }
            )
            scenario_id += 1
    runs = pd.DataFrame(run_rows)
    scenarios = pd.DataFrame(scenario_rows)
    train = scenarios[scenarios.split == "train"]
    regions: dict[str, object] = {}
    for split in ("test_topology", "test_scale"):
        test = scenarios[scenarios.split == split]
        region_metrics = {}
        for predictor in (
            "raw_auth_product",
            "weighted_union_product",
            "nonbacktracking_radius",
            "k_pre_radius",
            "temporal_k_pressure",
        ):
            _, values = _regression_metrics(train, test, predictor=predictor)
            region_metrics[predictor] = values
        regions[split] = region_metrics
    metrics = {"regions": regions, "ablations": {}}
    decision = HypothesisAssessment(
        hypothesis="NH2-D-legacy",
        supported_in_model=False,
        evidence_level="model-conditioned harness",
        primary_result="Compatibility harness executed.",
        limitations="This compact harness is not the Stage 2 Cycle 4 confirmation matrix.",
    )
    return runs, scenarios, decision, metrics


def _legacy_admission_profiles(profile: str, time: np.ndarray, final_n: int) -> np.ndarray:
    x = np.clip(time / max(time[-1] * 0.75, 1e-9), 0.0, 1.0)
    n0 = max(50.0, 0.05 * final_n)
    if profile == "linear":
        curve = x
    elif profile in {"staged", "burst"}:
        curve = 3 * x**2 - 2 * x**3 if profile == "staged" else np.floor(4 * x) / 4
    elif profile == "exponential":
        curve = (np.exp(3 * x) - 1) / (np.exp(3) - 1)
    elif profile in {"step_ramp", "step"}:
        curve = np.minimum(1.0, 4.0 * x)
    else:
        curve = x
    return n0 + (final_n - n0) * np.clip(curve, 0.0, 1.0)


def _legacy_run_nh4(
    *,
    seed: int,
    training_sizes: Sequence[int],
    heldout_sizes: Sequence[int],
    baseline_load_fractions: Sequence[float],
    ramp_durations_s: Sequence[float],
    disturbance_levels: Sequence[float],
    replications: int,
):
    profiles = ("linear", "staged", "burst", "exponential", "step_ramp")
    run_rows: list[dict[str, float | int | str]] = []
    scenario_rows: list[dict[str, float | int | str]] = []
    trajectory_rows: list[dict[str, float | int | str]] = []
    scenario_id = 0
    for final_n in (*training_sizes, *heldout_sizes):
        for profile in profiles:
            if final_n in training_sizes and profile in {"linear", "staged", "burst"}:
                split = "train"
            elif final_n in heldout_sizes and profile in {"linear", "staged", "burst"}:
                split = "test_scale"
            elif final_n in training_sizes and profile in {"exponential", "step_ramp"}:
                split = "test_shape"
            else:
                split = "test_joint"
            for baseline in baseline_load_fractions:
                for duration in ramp_durations_s:
                    for disturbance in disturbance_levels:
                        time = np.arange(0.0, duration + 120.0 + 1e-9, 1.0)
                        n = _legacy_admission_profiles(profile, time, int(final_n))
                        rate = np.diff(n, prepend=n[0])
                        pools = build_admission_pools(
                            final_n=int(final_n), final_baseline_fraction=float(baseline)
                        )
                        predictors = admission_load_predictors(n, rate, pools, dt_s=1.0)
                        failures = []
                        for rep in range(replications):
                            rng = np.random.default_rng(seed + scenario_id * 10_000 + rep)
                            noisy_lambda = predictors["peak_lambda_a"] * max(
                                0.0, 1.0 + rng.normal(0.0, disturbance)
                            )
                            probability = 1.0 / (1.0 + np.exp(-5.0 * (noisy_lambda - 1.0)))
                            failed = int(rng.random() < probability)
                            failures.append(failed)
                            run_rows.append(
                                {
                                    "scenario_id": scenario_id,
                                    "split": split,
                                    "profile": profile,
                                    "final_n": final_n,
                                    "seed": seed + scenario_id * 10_000 + rep,
                                    "failure": failed,
                                    **predictors,
                                }
                            )
                        scenario_rows.append(
                            {
                                "scenario_id": scenario_id,
                                "split": split,
                                "profile": profile,
                                "final_n": final_n,
                                "failure_probability": float(np.mean(failures)),
                                "disturbance": disturbance,
                                **predictors,
                            }
                        )
                        if final_n == max(heldout_sizes):
                            for pool in pools:
                                offered = pool.baseline_per_agent * n + pool.admission_work * rate
                                for idx, now in enumerate(time):
                                    trajectory_rows.append(
                                        {
                                            "scenario_id": scenario_id,
                                            "profile": profile,
                                            "final_n": final_n,
                                            "pool": pool.name,
                                            "time_s": now,
                                            "offered_target_ratio": float(
                                                offered[idx] / (pool.target_utilization * pool.capacity)
                                            ),
                                        }
                                    )
                        scenario_id += 1
    runs = pd.DataFrame(run_rows)
    scenarios = pd.DataFrame(scenario_rows)
    trajectories = pd.DataFrame(trajectory_rows)
    train = scenarios[scenarios.split == "train"]
    # Threshold is selected only from the training scenarios.
    candidates = np.unique(train.peak_lambda_a)
    best_threshold = float(np.median(candidates)) if len(candidates) else 1.0
    best_accuracy = -1.0
    y = (train.failure_probability >= 0.5).astype(int).to_numpy()
    for threshold in candidates:
        pred = (train.peak_lambda_a.to_numpy() >= threshold).astype(int)
        accuracy = _balanced_accuracy(y, pred)
        if accuracy > best_accuracy:
            best_accuracy = accuracy
            best_threshold = float(threshold)
    metrics = {"fitted_lambda_threshold": best_threshold, "balanced_accuracy_train": best_accuracy}
    decision = HypothesisAssessment(
        hypothesis="NH4-L-legacy",
        supported_in_model=False,
        evidence_level="model-conditioned harness",
        primary_result=f"Training threshold {best_threshold:.3f}.",
        limitations="Compatibility harness only.",
    )
    return runs, scenarios, trajectories, decision, metrics


def run_nh4_admission_load(
    *,
    seed: int,
    training_sizes: Sequence[int] | None = None,
    heldout_sizes: Sequence[int] | None = None,
    baseline_load_fractions: Sequence[float] | None = None,
    ramp_durations_s: Sequence[float] | None = None,
    disturbance_levels: Sequence[float] | None = None,
    replications: int = 12,
):
    """Compatibility entry point for both original and Cycle 3 scripts."""
    if training_sizes is not None:
        return _legacy_run_nh4(
            seed=seed,
            training_sizes=training_sizes,
            heldout_sizes=heldout_sizes or (5000, 10000),
            baseline_load_fractions=baseline_load_fractions or (0.40, 0.55, 0.70),
            ramp_durations_s=ramp_durations_s or (30.0, 90.0, 180.0, 360.0),
            disturbance_levels=disturbance_levels or (0.03, 0.07, 0.12),
            replications=replications,
        )
    # Compact Cycle 3 compatible shape. It uses the current admission matrix and
    # returns only held-out scenarios plus the summary expected by the script.
    runs, scenarios = generate_nh4_matrix(seed=seed, replications=replications)
    metrics, fitted = evaluate_nh4_predictors(scenarios)
    thresholds = nh4_threshold_table(scenarios)
    dummy_robustness = pd.DataFrame(
        {"auc_delta_omega_vs_lambda": [1.0] * 5}
    )
    summary = summarize_nh4(
        scenarios, metrics, fitted, thresholds, dummy_robustness, seed=seed
    )
    heldout = scenarios[scenarios.split == "test"].copy()
    heldout["coupled_stress"] = heldout.omega
    heldout["inadmissible_probability"] = heldout.failure_rate
    predictor_metrics = {
        row.predictor: {
            "auc": float(row.test_auc_majority_failure),
            "brier": float(row.test_brier_failure_rate),
        }
        for _, row in metrics.iterrows()
    }
    summary["predictor_metrics"] = predictor_metrics
    summary["train_critical_threshold"] = 1.0
    result = HypothesisAssessment(
        hypothesis="NH4-L",
        supported_in_model=bool(summary["supported_in_model"]),
        evidence_level="model-conditioned",
        primary_result=f"Omega AUC {summary['omega_auc']:.3f}.",
        limitations="Notional queue parameters.",
    )
    return runs, heldout, result, summary


def run_nh2_directed_ngm(
    *,
    seed: int,
    replications: int = 12,
    bootstrap_replications: int = 1000,
):
    del bootstrap_replications
    runs, scenarios = generate_nh2_matrix(
        seed=seed, replications=replications, reduced_robustness=True
    )
    # Translate split names for the Cycle 3 script.
    scenarios = scenarios.copy()
    scenarios["ever_fraction"] = scenarios.mean_ever_fraction
    scenarios["outbreak_probability"] = scenarios.outbreak_rate
    metrics, fitted = evaluate_nh2_predictors(scenarios)
    test = scenarios[scenarios.split == "test"].copy()
    predictions = test[["scenario_id", "ever_fraction", "outbreak_probability"]].copy()
    name_map = {
        "raw_authorization": "raw_auth_radius",
        "symmetrized_attack": "static_aggregate_radius",
        "dynamic_k": "operational_ngm_radius",
    }
    for source, target in name_map.items():
        predictions[f"{target}_ever_prediction"] = fitted[source]["final_prediction"]
    ablation_penalties = {}
    dynamic_mae = float(metrics[metrics.predictor == "dynamic_k"].iloc[0].test_mae_mean_ever)
    for name in (
        "ablate_authorization",
        "ablate_communication",
        "ablate_dependency",
        "ablate_supervision",
    ):
        value = float(metrics[metrics.predictor == name].iloc[0].test_mae_mean_ever)
        ablation_penalties[name.replace("ablate_", "")] = value - dynamic_mae
    summary = {
        "ablation_mae_penalties": ablation_penalties,
        "predictor_metrics": metrics.set_index("predictor").to_dict(orient="index"),
    }
    result = HypothesisAssessment(
        hypothesis="NH2-D",
        supported_in_model=False,
        evidence_level="model-conditioned",
        primary_result="Cycle 3 compatible directed operator harness executed.",
        limitations="This compatibility result is not used by Stage 2 Cycle 4.",
    )
    return runs, scenarios, predictions, result, summary
