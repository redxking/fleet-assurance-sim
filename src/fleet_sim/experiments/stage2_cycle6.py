"""Stage 2 Cycle 6 confirmatory experiments.

All model parameters are notional. Outputs are model-conditioned and do not
establish security or stability of any physical deployment.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from math import exp, log
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import lsq_linear
from scipy.stats import spearmanr

from fleet_sim.analysis.admission_stability import (
    AssuranceResource,
    build_resource_regime,
    fluid_admission_metrics,
    make_admission_trajectory,
    simulate_stochastic_admission_batch,
)
from fleet_sim.experiments.stage2_research import (
    HypothesisAssessment,
    _build_directed_layers,
    _directed_adjacency_radius,
    _roc_auc,
)
from fleet_sim.security.attack_operator import (
    build_hazard_operators,
    dynamic_operator_metrics,
    next_generation_matrix,
    nonnegative_spectral_radius,
    simulate_directed_sir_batch,
    weighted_nonbacktracking_radius,
)


@dataclass(frozen=True)
class Cycle6Result:
    hypothesis: str
    supported_in_model: bool
    decision: str
    evidence_level: str
    primary_result: str
    limitations: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _constrained_continuous_fit(
    train: pd.DataFrame,
    test: pd.DataFrame,
    score: str,
    outcome: str,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Fit a score-monotone linear model with a common log-N adjustment."""
    x_train = np.log1p(np.maximum(0.0, train[score].to_numpy(float)))
    n_train = np.log(np.maximum(1.0, train.n_agents.to_numpy(float)))
    design = np.column_stack([np.ones(len(train)), x_train, n_train])
    lower = np.array([-np.inf, 0.0, -np.inf])
    upper = np.array([np.inf, np.inf, np.inf])
    result = lsq_linear(design, train[outcome].to_numpy(float), bounds=(lower, upper))
    x_test = np.log1p(np.maximum(0.0, test[score].to_numpy(float)))
    n_test = np.log(np.maximum(1.0, test.n_agents.to_numpy(float)))
    test_design = np.column_stack([np.ones(len(test)), x_test, n_test])
    prediction = np.clip(test_design @ result.x, 0.0, 1.0)
    train_prediction = np.clip(design @ result.x, 0.0, 1.0)
    train_mae = float(np.mean(np.abs(train_prediction - train[outcome].to_numpy(float))))
    return prediction, np.asarray(result.x, dtype=float), train_mae


def _pava_fit(
    x: np.ndarray,
    y: np.ndarray,
    weights: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Fit a nondecreasing weighted isotonic calibration using PAVA."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    w = np.ones_like(y) if weights is None else np.asarray(weights, dtype=float)
    order = np.argsort(x, kind="mergesort")
    xs = x[order]
    ys = y[order]
    ws = w[order]

    unique_x: list[float] = []
    unique_y: list[float] = []
    unique_w: list[float] = []
    start = 0
    while start < len(xs):
        end = start + 1
        while end < len(xs) and xs[end] == xs[start]:
            end += 1
        total_w = float(ws[start:end].sum())
        unique_x.append(float(xs[start]))
        unique_y.append(float(np.sum(ys[start:end] * ws[start:end]) / max(total_w, 1e-12)))
        unique_w.append(total_w)
        start = end

    blocks: list[dict[str, float | int]] = []
    for index, (xi, yi, wi) in enumerate(zip(unique_x, unique_y, unique_w)):
        blocks.append({"start": index, "end": index, "weight": wi, "value": yi})
        while len(blocks) >= 2 and float(blocks[-2]["value"]) > float(blocks[-1]["value"]):
            right = blocks.pop()
            left = blocks.pop()
            weight = float(left["weight"]) + float(right["weight"])
            value = (
                float(left["value"]) * float(left["weight"])
                + float(right["value"]) * float(right["weight"])
            ) / max(weight, 1e-12)
            blocks.append(
                {
                    "start": int(left["start"]),
                    "end": int(right["end"]),
                    "weight": weight,
                    "value": value,
                }
            )

    fit_x: list[float] = []
    fit_y: list[float] = []
    for block in blocks:
        lo = int(block["start"])
        hi = int(block["end"])
        fit_x.append(float(np.average(unique_x[lo : hi + 1], weights=unique_w[lo : hi + 1])))
        fit_y.append(float(block["value"]))
    return np.asarray(fit_x), np.asarray(fit_y)


def _pava_predict(x: np.ndarray, fit_x: np.ndarray, fit_y: np.ndarray) -> np.ndarray:
    if len(fit_x) == 0:
        return np.zeros(len(x), dtype=float)
    if len(fit_x) == 1:
        return np.full(len(x), float(fit_y[0]), dtype=float)
    return np.clip(
        np.interp(np.asarray(x, dtype=float), fit_x, fit_y, left=fit_y[0], right=fit_y[-1]),
        0.0,
        1.0,
    )


def temporal_geometric_radius(
    pre_radius: float,
    post_radius: float,
    intervention_time: int,
    horizon: int,
    *,
    epsilon: float = 1e-12,
) -> float:
    fraction = float(intervention_time) / float(horizon)
    return float(
        np.exp(
            fraction * np.log(max(epsilon, pre_radius))
            + (1.0 - fraction) * np.log(max(epsilon, post_radius))
        )
    )


def temporal_linear_propagator_growth(
    candidate_pre: sparse.spmatrix,
    candidate_post: sparse.spmatrix,
    recovery: np.ndarray,
    *,
    intervention_time: int,
    horizon: int,
    max_iterations: int = 45,
    tolerance: float = 1e-7,
) -> float:
    """Estimate rho(Psi)^(1/T) by normalized sparse power iteration."""
    pre_t = sparse.csr_matrix(candidate_pre, dtype=float).transpose().tocsr()
    post_t = sparse.csr_matrix(candidate_post, dtype=float).transpose().tocsr()
    survival = np.exp(-np.asarray(recovery, dtype=float))
    n = pre_t.shape[0]
    vector = np.full(n, 1.0 / np.sqrt(n), dtype=float)
    previous = 0.0
    growth = 0.0
    for _ in range(max_iterations):
        state = vector.copy()
        log_scale = 0.0
        for step in range(horizon):
            hazard = pre_t if step < intervention_time else post_t
            state = survival * state + hazard @ state
            norm = float(np.linalg.norm(state))
            if norm <= 0.0 or not np.isfinite(norm):
                return 0.0
            state /= norm
            log_scale += log(norm)
        growth = exp(log_scale / max(1, horizon))
        vector = state
        if abs(growth - previous) <= tolerance * max(1.0, growth):
            break
        previous = growth
    return float(growth)


def _nh2_structures(
    *,
    training: bool,
) -> Iterable[tuple[int, str, str, str]]:
    if training:
        for n in (128, 256):
            for dependency in ("random_regular", "erdos_renyi"):
                for segmentation in ("none", "partitioned"):
                    yield n, "random_regular", dependency, segmentation
    else:
        for authorization in ("barabasi_albert", "hierarchical"):
            for dependency in ("barabasi_albert", "hierarchical"):
                for segmentation in ("none", "partitioned"):
                    yield 512, authorization, dependency, segmentation


def _generate_nh2_cycle6(
    *,
    seed: int,
    replications: int,
    reduced: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    targets = (0.60, 0.85, 1.10, 1.40, 1.80, 2.30)
    interventions = ((0.35, 10), (0.35, 25), (0.65, 10), (0.65, 25))
    structures = list(_nh2_structures(training=True)) + list(_nh2_structures(training=False))
    if reduced:
        targets = (0.70, 1.10, 1.60, 2.20)
        interventions = ((0.35, 25), (0.65, 10))
        structures = [
            (128, "random_regular", "random_regular", "none"),
            (128, "random_regular", "random_regular", "partitioned"),
            (512, "hierarchical", "barabasi_albert", "none"),
            (512, "hierarchical", "barabasi_albert", "partitioned"),
        ]
    horizon = 50
    run_rows: list[dict[str, float | int | str]] = []
    scenario_rows: list[dict[str, float | int | str]] = []
    scenario_id = 0
    for structure_index, (n, auth, dependency, segmentation) in enumerate(structures):
        split = "train" if n in {128, 256} and auth == "random_regular" and dependency in {"random_regular", "erdos_renyi"} else "test"
        graph_seed = seed + structure_index * 1_000_000 + n * 101
        state, layers = _build_directed_layers(
            n,
            auth_family=auth,
            dependency_family=dependency,
            segmentation=segmentation,
            seed=graph_seed,
        )
        raw_auth = _directed_adjacency_radius(layers["authorization"])
        operator_seed = graph_seed + 77_777
        unit = build_hazard_operators(
            layers,
            state,
            seed=operator_seed,
            beta_scale=1.0,
            intervention_strength=0.35,
        )
        unit_k = next_generation_matrix(unit.candidate_pre, state.recovery_observed)
        base_radius = max(nonnegative_spectral_radius(unit_k), 1e-12)
        for target in targets:
            beta_scale = float(target / base_radius)
            for strength, intervention_time in interventions:
                operators = build_hazard_operators(
                    layers,
                    state,
                    seed=operator_seed,
                    beta_scale=beta_scale,
                    intervention_strength=strength,
                )
                dynamic = dynamic_operator_metrics(
                    operators.candidate_pre,
                    operators.candidate_post,
                    state.recovery_observed,
                    intervention_time=intervention_time,
                    horizon=horizon,
                )
                nb_pre = weighted_nonbacktracking_radius(
                    operators.candidate_pre, state.recovery_observed
                )
                nb_post = weighted_nonbacktracking_radius(
                    operators.candidate_post, state.recovery_observed
                )
                tnb = temporal_geometric_radius(
                    nb_pre, nb_post, intervention_time, horizon
                )
                k_geo = temporal_geometric_radius(
                    float(dynamic["candidate_rho_pre"]),
                    float(dynamic["candidate_rho_post"]),
                    intervention_time,
                    horizon,
                )
                propagator = temporal_linear_propagator_growth(
                    operators.candidate_pre,
                    operators.candidate_post,
                    state.recovery_observed,
                    intervention_time=intervention_time,
                    horizon=horizon,
                )
                rep_seeds = [seed + 500_000_000 + scenario_id * 10_000 + r for r in range(replications)]
                batch = simulate_directed_sir_batch(
                    operators.true_pre,
                    operators.true_post,
                    state.recovery_true,
                    intervention_time=intervention_time,
                    horizon_steps=horizon,
                    replication_seeds=rep_seeds,
                )
                common: dict[str, float | int | str] = {
                    "scenario_id": scenario_id,
                    "split": split,
                    "n_agents": n,
                    "auth_family": auth,
                    "dependency_family": dependency,
                    "segmentation": segmentation,
                    "graph_seed": graph_seed,
                    "operator_seed": operator_seed,
                    "target_pre_k_radius": target,
                    "beta_scale": beta_scale,
                    "intervention_strength": strength,
                    "intervention_time": intervention_time,
                    "horizon_steps": horizon,
                    "raw_auth_radius": raw_auth,
                    "static_k_pre": float(dynamic["candidate_rho_pre"]),
                    "static_k_post": float(dynamic["candidate_rho_post"]),
                    "k_geometric": k_geo,
                    "nb_pre": nb_pre,
                    "nb_post": nb_post,
                    "temporal_nb": tnb,
                    "propagator_growth": propagator,
                }
                for r, rseed in enumerate(batch.replication_seeds):
                    run_rows.append(
                        {
                            **common,
                            "replication": r,
                            "seed": int(rseed),
                            "ever_compromised_fraction": float(batch.ever_fraction[r]),
                            "peak_compromised_fraction": float(batch.peak_fraction[r]),
                            "duration_steps": int(batch.duration_steps[r]),
                            "outbreak_10pct": int(batch.ever_fraction[r] >= 0.10),
                        }
                    )
                scenario_rows.append(
                    {
                        **common,
                        "replications": replications,
                        "mean_ever_fraction": float(np.mean(batch.ever_fraction)),
                        "mean_peak_fraction": float(np.mean(batch.peak_fraction)),
                        "mean_duration_steps": float(np.mean(batch.duration_steps)),
                        "outbreak_successes": int(np.sum(batch.ever_fraction >= 0.10)),
                        "outbreak_rate": float(np.mean(batch.ever_fraction >= 0.10)),
                    }
                )
                scenario_id += 1
    return pd.DataFrame(run_rows), pd.DataFrame(scenario_rows)


def _nh2_metrics(scenarios: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, np.ndarray], str]:
    train = scenarios[scenarios.split == "train"].copy()
    test = scenarios[scenarios.split == "test"].copy()
    predictors = (
        "raw_auth_radius",
        "static_k_pre",
        "nb_pre",
        "k_geometric",
        "temporal_nb",
        "propagator_growth",
    )
    y_binary = (test.outbreak_rate.to_numpy(float) >= 0.10).astype(int)
    rows: list[dict[str, float | str | int]] = []
    predictions: dict[str, np.ndarray] = {}
    training_mae: dict[str, float] = {}
    for predictor in predictors:
        prediction, weights, train_mae = _constrained_continuous_fit(
            train, test, predictor, "mean_ever_fraction"
        )
        predictions[predictor] = prediction
        training_mae[predictor] = train_mae
        observed = test.mean_ever_fraction.to_numpy(float)
        rows.append(
            {
                "predictor": predictor,
                "train_mae": train_mae,
                "test_mae": float(np.mean(np.abs(prediction - observed))),
                "test_rmse": float(np.sqrt(np.mean((prediction - observed) ** 2))),
                "test_raw_auc": _roc_auc(y_binary, test[predictor].to_numpy(float)),
                "test_spearman_mean_ever": float(
                    spearmanr(test[predictor].to_numpy(float), observed).statistic
                ),
                "positive_test_scenarios": int(y_binary.sum()),
                "negative_test_scenarios": int(len(y_binary) - y_binary.sum()),
                "coefficient_score": float(weights[1]),
                "coefficient_log_n": float(weights[2]),
            }
        )
    selected = min(("temporal_nb", "propagator_growth"), key=lambda p: training_mae[p])
    return pd.DataFrame(rows), predictions, selected


def _nh2_bootstrap(
    scenarios: pd.DataFrame,
    predictions: Mapping[str, np.ndarray],
    selected: str,
    *,
    seed: int,
    draws: int = 1000,
) -> dict[str, list[float]]:
    test = scenarios[scenarios.split == "test"].reset_index(drop=True)
    observed = test.mean_ever_fraction.to_numpy(float)
    y_binary = (test.outbreak_rate.to_numpy(float) >= 0.10).astype(int)
    rng = np.random.default_rng(seed)
    mae_improvements: list[float] = []
    absolute_differences: list[float] = []
    auc_deltas: list[float] = []
    for _ in range(draws):
        sample = rng.integers(0, len(test), size=len(test))
        base_mae = float(np.mean(np.abs(predictions["nb_pre"][sample] - observed[sample])))
        candidate_mae = float(np.mean(np.abs(predictions[selected][sample] - observed[sample])))
        mae_improvements.append((base_mae - candidate_mae) / max(base_mae, 1e-12))
        absolute_differences.append(base_mae - candidate_mae)
        auc_deltas.append(
            _roc_auc(y_binary[sample], test[selected].to_numpy(float)[sample])
            - _roc_auc(y_binary[sample], test.nb_pre.to_numpy(float)[sample])
        )
    return {
        "mae_improvement_fraction": [
            float(np.quantile(mae_improvements, 0.025)),
            float(np.quantile(mae_improvements, 0.975)),
        ],
        "absolute_mae_reduction": [
            float(np.quantile(absolute_differences, 0.025)),
            float(np.quantile(absolute_differences, 0.975)),
        ],
        "auc_delta": [
            float(np.quantile(auc_deltas, 0.025)),
            float(np.quantile(auc_deltas, 0.975)),
        ],
    }


def _nh2_robustness(*, seed: int, selected: str, blocks: int = 5) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    for block in range(blocks):
        _, scenarios = _generate_nh2_cycle6(
            seed=seed + block * 10_000_000,
            replications=30,
            reduced=True,
        )
        metrics, _, block_selected = _nh2_metrics(scenarios)
        candidate = metrics[metrics.predictor == selected].iloc[0]
        baseline = metrics[metrics.predictor == "nb_pre"].iloc[0]
        rows.append(
            {
                "block": block,
                "selected_primary_candidate": selected,
                "training_selected_candidate_in_block": block_selected,
                "candidate_mae": float(candidate.test_mae),
                "baseline_mae": float(baseline.test_mae),
                "mae_improvement_fraction": float(
                    (baseline.test_mae - candidate.test_mae) / max(baseline.test_mae, 1e-12)
                ),
                "candidate_auc": float(candidate.test_raw_auc),
                "baseline_auc": float(baseline.test_raw_auc),
                "auc_delta": float(candidate.test_raw_auc - baseline.test_raw_auc),
            }
        )
    return pd.DataFrame(rows)


def run_nh2_cycle6(*, seed: int = 20260821) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    runs, scenarios = _generate_nh2_cycle6(seed=seed, replications=30)
    metrics, predictions, selected = _nh2_metrics(scenarios)
    robustness = _nh2_robustness(seed=seed + 810_000_000, selected=selected)
    bootstrap = _nh2_bootstrap(
        scenarios, predictions, selected, seed=seed + 820_000_000
    )
    candidate = metrics[metrics.predictor == selected].iloc[0]
    baseline = metrics[metrics.predictor == "nb_pre"].iloc[0]
    mae_improvement = float(
        (baseline.test_mae - candidate.test_mae) / max(baseline.test_mae, 1e-12)
    )
    auc_delta = float(candidate.test_raw_auc - baseline.test_raw_auc)
    spearman_delta = float(
        candidate.test_spearman_mean_ever - baseline.test_spearman_mean_ever
    )
    positive_blocks = int((robustness.mae_improvement_fraction > 0.0).sum())
    criteria = {
        "mae_improvement_at_least_5pct": mae_improvement >= 0.05,
        "auc_delta_at_least_0_01": auc_delta >= 0.01,
        "spearman_non_decreasing": spearman_delta >= 0.0,
        "bootstrap_absolute_mae_lower_bound_positive": bootstrap["absolute_mae_reduction"][0] > 0.0,
        "four_of_five_positive_robustness_blocks": positive_blocks >= 4,
    }
    test_index = scenarios[scenarios.split == "test"].index
    prediction_rows: list[pd.DataFrame] = []
    for predictor, values in predictions.items():
        frame = scenarios.loc[test_index, ["scenario_id", "split", "mean_ever_fraction", "outbreak_rate"]].copy()
        frame["predictor"] = predictor
        frame["prediction"] = values
        frame["raw_score"] = scenarios.loc[test_index, predictor].to_numpy(float)
        prediction_rows.append(frame)
    summary = {
        "selected_temporal_candidate": selected,
        "candidate_test_mae": float(candidate.test_mae),
        "baseline_test_mae": float(baseline.test_mae),
        "mae_improvement_fraction": mae_improvement,
        "candidate_raw_auc": float(candidate.test_raw_auc),
        "baseline_raw_auc": float(baseline.test_raw_auc),
        "auc_delta": auc_delta,
        "candidate_spearman": float(candidate.test_spearman_mean_ever),
        "baseline_spearman": float(baseline.test_spearman_mean_ever),
        "spearman_delta": spearman_delta,
        "positive_robustness_blocks": positive_blocks,
        "bootstrap_95pct": bootstrap,
        "criteria": criteria,
        "supported_in_model": bool(all(criteria.values())),
        "test_class_counts": {
            "positive": int(candidate.positive_test_scenarios),
            "negative": int(candidate.negative_test_scenarios),
        },
    }
    return runs, scenarios, metrics, pd.concat(prediction_rows, ignore_index=True), {**summary, "robustness": robustness.to_dict(orient="records")}


def _make_exponential_trajectory(
    *,
    n0: int,
    nf: int,
    ramp_duration_s: float,
    recovery_window_s: float = 120.0,
    dt: float = 0.5,
) -> pd.DataFrame:
    horizon = ramp_duration_s + recovery_window_s
    t = np.arange(0.0, horizon + 1e-12, dt)
    z = np.clip(t / ramp_duration_s, 0.0, 1.0)
    curve = (np.exp(3.0 * z) - 1.0) / (np.exp(3.0) - 1.0)
    n = n0 + (nf - n0) * curve
    n[t >= ramp_duration_s] = float(nf)
    dn = np.maximum(0.0, np.diff(n, prepend=n[0]) / dt)
    return pd.DataFrame(
        {
            "time_s": t,
            "n_agents": n,
            "admission_rate_agents_s": dn,
            "profile": "exponential",
        }
    )


def _admission_trajectory(
    profile: str,
    *,
    n0: int,
    nf: int,
    duration: float,
) -> pd.DataFrame:
    if profile == "exponential":
        return _make_exponential_trajectory(
            n0=n0, nf=nf, ramp_duration_s=duration
        )
    return make_admission_trajectory(
        profile,
        n0=n0,
        nf=nf,
        ramp_duration_s=duration,
        recovery_window_s=120.0,
        dt=0.5,
    )


def _fast_fluid_scores(
    *,
    profile: str,
    n0: int,
    nf: int,
    duration: float,
    resources: Sequence[AssuranceResource],
    dt: float = 0.5,
) -> tuple[float, float]:
    """Return peak Lambda and Omega without constructing a long-form frame."""
    t = np.arange(0.0, duration + 1e-12, dt)
    z = np.clip(t / duration, 0.0, 1.0)
    if profile == "linear":
        curve = z
    elif profile in {"smooth", "staged"}:
        curve = 3.0 * z**2 - 2.0 * z**3
    elif profile == "front_loaded":
        curve = 1.0 - (1.0 - z) ** 3
    elif profile == "back_loaded":
        curve = z**3
    elif profile == "exponential":
        curve = (np.exp(3.0 * z) - 1.0) / (np.exp(3.0) - 1.0)
    else:
        raise ValueError(profile)
    n = n0 + (nf - n0) * curve
    n[-1] = float(nf)
    dn = np.maximum(0.0, np.diff(n, prepend=n[0]) / dt)
    peak_lambda = 0.0
    peak_omega = 0.0
    for resource in resources:
        arrival = resource.background_per_agent_hz * n + resource.admission_work_ops * dn
        spare = resource.capacity_per_s - resource.background_per_agent_hz * n
        instant = np.where(
            spare > 0.0,
            resource.admission_work_ops * dn / spare,
            np.inf,
        )
        increments = (arrival - resource.capacity_per_s) * dt
        cumulative = np.cumsum(increments)
        prefix_min = np.minimum.accumulate(np.concatenate(([0.0], cumulative)))
        queue = cumulative - prefix_min[1:]
        omega = np.max(queue) / max(resource.capacity_per_s * resource.max_wait_s, 1e-12)
        peak_lambda = max(peak_lambda, float(np.max(instant)))
        peak_omega = max(peak_omega, float(omega))
    return peak_lambda, peak_omega


def _solve_duration_for_omega(
    *,
    profile: str,
    n0: int,
    nf: int,
    resources: Sequence[AssuranceResource],
    target_omega: float,
) -> tuple[float, float]:
    low = 0.5
    high = 5_000.0

    def omega_at(duration: float) -> float:
        return _fast_fluid_scores(
            profile=profile,
            n0=n0,
            nf=nf,
            duration=duration,
            resources=resources,
        )[1]

    omega_low = omega_at(low)
    omega_high = omega_at(high)
    if target_omega >= omega_low:
        return low, omega_low
    if target_omega <= omega_high:
        return high, omega_high
    for _ in range(32):
        middle = float(np.sqrt(low * high))
        omega_middle = omega_at(middle)
        if omega_middle > target_omega:
            low = middle
        else:
            high = middle
    candidates = [(low, omega_at(low)), (high, omega_at(high))]
    return min(candidates, key=lambda item: abs(item[1] - target_omega))


def _nh4_specs() -> list[dict[str, float | int | str]]:
    targets = (0.30, 0.55, 0.80, 1.00, 1.25, 1.60, 2.20)
    regimes = (
        "balanced",
        "control_constrained",
        "supervision_constrained",
        "credential_constrained",
    )
    profile_groups = (
        ("train", (2_000, 5_000), ("linear", "smooth", "front_loaded")),
        ("test", (10_000, 20_000), ("back_loaded", "exponential")),
    )

    # With n0/nf fixed and capacities proportional to nf, nominal Omega is
    # scale invariant. Solve each profile-regime-target duration once.
    duration_cache: dict[tuple[str, str, float], tuple[float, float]] = {}
    reference_nf = 10_000
    reference_n0 = 500
    for _, _, profiles in profile_groups:
        for profile in profiles:
            for regime in regimes:
                reference_resources = build_resource_regime(reference_nf, regime)
                for target in targets:
                    duration_cache[(profile, regime, target)] = _solve_duration_for_omega(
                        profile=profile,
                        n0=reference_n0,
                        nf=reference_nf,
                        resources=reference_resources,
                        target_omega=target,
                    )

    rows: list[dict[str, float | int | str]] = []
    scenario_id = 0
    for split, sizes, profiles in profile_groups:
        for nf in sizes:
            n0 = max(100, int(round(0.05 * nf)))
            for profile in profiles:
                for regime in regimes:
                    resources = build_resource_regime(nf, regime)
                    for target in targets:
                        duration, nominal_reference = duration_cache[(profile, regime, target)]
                        trajectory = _admission_trajectory(
                            profile, n0=n0, nf=nf, duration=duration
                        )
                        predictors, _ = fluid_admission_metrics(trajectory, resources)
                        rows.append(
                            {
                                "scenario_id": scenario_id,
                                "split": split,
                                "nf": nf,
                                "n0": n0,
                                "profile": profile,
                                "capacity_regime": regime,
                                "target_omega": target,
                                "reference_achieved_omega": nominal_reference,
                                "achieved_target_omega": float(predictors.omega),
                                "ramp_duration_s": duration,
                                **predictors.as_dict(),
                            }
                        )
                        scenario_id += 1
    return rows


def _execute_nh4_specs(
    specs: Sequence[Mapping[str, float | int | str]],
    *,
    seed: int,
    replications: int,
    retain_runs: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    run_rows: list[dict[str, float | int | str]] = []
    scenario_rows: list[dict[str, float | int | str]] = []
    for spec in specs:
        nf = int(spec["nf"])
        n0 = int(spec["n0"])
        profile = str(spec["profile"])
        regime = str(spec["capacity_regime"])
        scenario_id = int(spec["scenario_id"])
        duration = float(spec["ramp_duration_s"])
        resources = build_resource_regime(nf, regime)
        trajectory = _admission_trajectory(
            profile, n0=n0, nf=nf, duration=duration
        )
        rep_seeds = [seed + scenario_id * 10_000 + r for r in range(replications)]
        outcomes = simulate_stochastic_admission_batch(
            trajectory, resources, replication_seeds=rep_seeds
        )
        if retain_runs:
            for replication, (_, outcome) in enumerate(outcomes.iterrows()):
                run_rows.append(
                    {
                        **dict(spec),
                        "replication": replication,
                        **outcome.to_dict(),
                    }
                )
        scenario_rows.append(
            {
                **dict(spec),
                "replications": replications,
                "failure_successes": int(outcomes.boundary_crossed.sum()),
                "failure_rate": float(outcomes.boundary_crossed.mean()),
                "mean_maximum_normalized_queue": float(
                    outcomes.maximum_normalized_queue.mean()
                ),
                "p95_maximum_normalized_queue": float(
                    outcomes.maximum_normalized_queue.quantile(0.95)
                ),
            }
        )
    return pd.DataFrame(run_rows), pd.DataFrame(scenario_rows)


def _balanced_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y = np.asarray(y_true, dtype=int)
    p = np.asarray(y_pred, dtype=int)
    positive = y == 1
    negative = y == 0
    if not positive.any() or not negative.any():
        return 0.5
    return 0.5 * (
        float(np.mean(p[positive] == 1)) + float(np.mean(p[negative] == 0))
    )


def _interpolate_half_threshold(group: pd.DataFrame) -> float:
    ordered = group.groupby("omega", as_index=False).failure_rate.mean().sort_values("omega")
    x = ordered.omega.to_numpy(float)
    y = ordered.failure_rate.to_numpy(float)
    for idx in range(1, len(x)):
        if y[idx - 1] < 0.5 <= y[idx]:
            if y[idx] == y[idx - 1]:
                return float((x[idx - 1] + x[idx]) / 2.0)
            fraction = (0.5 - y[idx - 1]) / (y[idx] - y[idx - 1])
            return float(x[idx - 1] + fraction * (x[idx] - x[idx - 1]))
    return float("nan")


def _nh4_evaluate(
    scenarios: pd.DataFrame,
) -> tuple[dict[str, object], dict[str, np.ndarray]]:
    train = scenarios[scenarios.split == "train"].copy()
    test = scenarios[scenarios.split == "test"].copy()
    y_binary = (test.failure_rate.to_numpy(float) >= 0.5).astype(int)
    predictions: dict[str, np.ndarray] = {}
    metrics: dict[str, dict[str, float]] = {}
    for predictor in ("peak_lambda", "omega"):
        fit_x, fit_y = _pava_fit(
            train[predictor].to_numpy(float),
            train.failure_rate.to_numpy(float),
            train.replications.to_numpy(float),
        )
        probability = _pava_predict(test[predictor].to_numpy(float), fit_x, fit_y)
        predictions[predictor] = probability
        metrics[predictor] = {
            "raw_auc": _roc_auc(y_binary, test[predictor].to_numpy(float)),
            "brier": float(np.mean((probability - test.failure_rate.to_numpy(float)) ** 2)),
        }
    omega_auc = metrics["omega"]["raw_auc"]
    lambda_auc = metrics["peak_lambda"]["raw_auc"]
    omega_brier = metrics["omega"]["brier"]
    lambda_brier = metrics["peak_lambda"]["brier"]
    threshold_ba = _balanced_accuracy(y_binary, (test.omega.to_numpy(float) >= 1.0).astype(int))
    positives = int(y_binary.sum())
    negatives = int(len(y_binary) - positives)
    valid_gate = positives >= int(np.ceil(0.20 * len(test))) and negatives >= int(np.ceil(0.20 * len(test)))
    thresholds: list[float] = []
    for _, group in test.groupby(["nf", "profile"]):
        threshold = _interpolate_half_threshold(group)
        if np.isfinite(threshold):
            thresholds.append(threshold)
    threshold_cv = (
        float(np.std(thresholds, ddof=1) / np.mean(thresholds))
        if len(thresholds) > 1 and np.mean(thresholds) != 0.0
        else float("nan")
    )
    brier_improvement = (lambda_brier - omega_brier) / max(lambda_brier, 1e-12)
    summary = {
        "test_scenarios": len(test),
        "positive_test_scenarios": positives,
        "negative_test_scenarios": negatives,
        "validity_gate": valid_gate,
        "omega_auc": omega_auc,
        "lambda_auc": lambda_auc,
        "auc_delta": omega_auc - lambda_auc,
        "omega_brier": omega_brier,
        "lambda_brier": lambda_brier,
        "brier_improvement_fraction": brier_improvement,
        "omega_one_balanced_accuracy": threshold_ba,
        "threshold_cv": threshold_cv,
        "valid_threshold_groups": len(thresholds),
        "thresholds": thresholds,
        "predictor_metrics": metrics,
    }
    return summary, predictions


def _nh4_robustness(
    specs: Sequence[Mapping[str, float | int | str]],
    *,
    seed: int,
    blocks: int = 5,
) -> pd.DataFrame:
    rows: list[dict[str, float | int | bool]] = []
    for block in range(blocks):
        _, scenarios = _execute_nh4_specs(
            specs,
            seed=seed + block * 100_000_000,
            replications=30,
            retain_runs=False,
        )
        summary, _ = _nh4_evaluate(scenarios)
        block_pass = bool(
            summary["validity_gate"]
            and float(summary["omega_auc"]) >= 0.90
            and float(summary["auc_delta"]) >= 0.08
            and float(summary["omega_one_balanced_accuracy"]) >= 0.80
            and float(summary["brier_improvement_fraction"]) >= 0.15
        )
        rows.append(
            {
                "block": block,
                "validity_gate": bool(summary["validity_gate"]),
                "omega_auc": float(summary["omega_auc"]),
                "lambda_auc": float(summary["lambda_auc"]),
                "auc_delta": float(summary["auc_delta"]),
                "omega_one_balanced_accuracy": float(summary["omega_one_balanced_accuracy"]),
                "brier_improvement_fraction": float(summary["brier_improvement_fraction"]),
                "block_pass": block_pass,
            }
        )
    return pd.DataFrame(rows)


def _nh4_bootstrap(
    scenarios: pd.DataFrame,
    predictions: Mapping[str, np.ndarray],
    *,
    seed: int,
    draws: int = 1000,
) -> dict[str, list[float]]:
    test = scenarios[scenarios.split == "test"].reset_index(drop=True)
    y_rate = test.failure_rate.to_numpy(float)
    y_binary = (y_rate >= 0.5).astype(int)
    rng = np.random.default_rng(seed)
    auc_delta: list[float] = []
    brier_improvement: list[float] = []
    balanced_accuracy: list[float] = []
    for _ in range(draws):
        sample = rng.integers(0, len(test), size=len(test))
        auc_delta.append(
            _roc_auc(y_binary[sample], test.omega.to_numpy(float)[sample])
            - _roc_auc(y_binary[sample], test.peak_lambda.to_numpy(float)[sample])
        )
        bo = float(np.mean((predictions["omega"][sample] - y_rate[sample]) ** 2))
        bl = float(np.mean((predictions["peak_lambda"][sample] - y_rate[sample]) ** 2))
        brier_improvement.append((bl - bo) / max(bl, 1e-12))
        balanced_accuracy.append(
            _balanced_accuracy(
                y_binary[sample],
                (test.omega.to_numpy(float)[sample] >= 1.0).astype(int),
            )
        )
    return {
        "auc_delta": [float(np.quantile(auc_delta, 0.025)), float(np.quantile(auc_delta, 0.975))],
        "brier_improvement_fraction": [
            float(np.quantile(brier_improvement, 0.025)),
            float(np.quantile(brier_improvement, 0.975)),
        ],
        "omega_one_balanced_accuracy": [
            float(np.quantile(balanced_accuracy, 0.025)),
            float(np.quantile(balanced_accuracy, 0.975)),
        ],
    }


def run_nh4_cycle6(*, seed: int = 20260821) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    specs = _nh4_specs()
    runs, scenarios = _execute_nh4_specs(
        specs, seed=seed + 900_000_000, replications=30, retain_runs=True
    )
    summary, predictions = _nh4_evaluate(scenarios)
    robustness = _nh4_robustness(specs, seed=seed + 910_000_000)
    bootstrap = _nh4_bootstrap(
        scenarios, predictions, seed=seed + 920_000_000
    )
    positive_blocks = int(robustness.block_pass.sum())
    criteria = {
        "validity_gate": bool(summary["validity_gate"]),
        "omega_auc_at_least_0_90": float(summary["omega_auc"]) >= 0.90,
        "auc_delta_at_least_0_08": float(summary["auc_delta"]) >= 0.08,
        "omega_one_balanced_accuracy_at_least_0_80": float(summary["omega_one_balanced_accuracy"]) >= 0.80,
        "brier_reduction_at_least_15pct": float(summary["brier_improvement_fraction"]) >= 0.15,
        "threshold_cv_no_more_than_0_20": bool(
            np.isfinite(float(summary["threshold_cv"])) and float(summary["threshold_cv"]) <= 0.20
        ),
        "four_of_five_robustness_blocks": positive_blocks >= 4,
    }
    test = scenarios[scenarios.split == "test"].copy().reset_index(drop=True)
    prediction_frame = test[["scenario_id", "nf", "profile", "capacity_regime", "target_omega", "omega", "peak_lambda", "failure_rate"]].copy()
    prediction_frame["omega_probability"] = predictions["omega"]
    prediction_frame["lambda_probability"] = predictions["peak_lambda"]
    return runs, scenarios, prediction_frame, {
        **summary,
        "positive_robustness_blocks": positive_blocks,
        "robustness": robustness.to_dict(orient="records"),
        "bootstrap_95pct": bootstrap,
        "criteria": criteria,
        "supported_in_model": bool(all(criteria.values())),
    }


def write_cycle6_figures(
    nh2_scenarios: pd.DataFrame,
    nh2_metrics: pd.DataFrame,
    nh2_predictions: pd.DataFrame,
    nh2_summary: Mapping[str, object],
    nh4_scenarios: pd.DataFrame,
    nh4_predictions: pd.DataFrame,
    nh4_summary: Mapping[str, object],
    output_dir: str | Path,
) -> list[Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    selected = str(nh2_summary["selected_temporal_candidate"])
    test2 = nh2_scenarios[nh2_scenarios.split == "test"]
    fig, ax = plt.subplots(figsize=(7.8, 5.4))
    ax.scatter(test2.nb_pre, test2.mean_ever_fraction, alpha=0.55, label="Static non-backtracking")
    ax.scatter(test2[selected], test2.mean_ever_fraction, marker="x", alpha=0.75, label=selected)
    ax.set_xlabel("Predictor score")
    ax.set_ylabel("Mean ever-compromised fraction")
    ax.set_title("NH2-T held-out response-adjusted predictor")
    ax.legend()
    ax.grid(alpha=0.2)
    path = output / "nh2_temporal_predictor_scatter.png"
    fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig); paths.append(path)

    fig, ax = plt.subplots(figsize=(8.4, 5.4))
    ordered = nh2_metrics.sort_values("test_mae")
    ax.bar(ordered.predictor, ordered.test_mae)
    ax.set_ylabel("Held-out MAE")
    ax.set_title("NH2-T predictor comparison")
    ax.tick_params(axis="x", rotation=35)
    ax.grid(axis="y", alpha=0.2)
    path = output / "nh2_predictor_mae.png"
    fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig); paths.append(path)

    test4 = nh4_scenarios[nh4_scenarios.split == "test"]
    fig, ax = plt.subplots(figsize=(7.8, 5.4))
    for profile, group in test4.groupby("profile"):
        ax.scatter(group.omega, group.failure_rate, label=profile, alpha=0.72)
    ax.axvline(1.0, linestyle="--", linewidth=1)
    ax.set_xlabel("Overload index Omega_A")
    ax.set_ylabel("Boundary-crossing probability")
    ax.set_title("NH4-O boundary-spanning held-out test")
    ax.legend()
    ax.grid(alpha=0.2)
    path = output / "nh4_omega_transition.png"
    fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig); paths.append(path)

    fig, ax = plt.subplots(figsize=(7.8, 5.4))
    ax.scatter(test4.peak_lambda, test4.failure_rate, alpha=0.65, label="Lambda_A")
    ax.scatter(test4.omega, test4.failure_rate, marker="x", alpha=0.75, label="Omega_A")
    ax.set_xscale("log")
    ax.set_xlabel("Predictor score")
    ax.set_ylabel("Boundary-crossing probability")
    ax.set_title("NH4-O instantaneous versus accumulated overload")
    ax.legend()
    ax.grid(alpha=0.2)
    path = output / "nh4_lambda_vs_omega.png"
    fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig); paths.append(path)

    fig, ax = plt.subplots(figsize=(7.8, 5.2))
    grouped = test4.groupby("target_omega", as_index=False).agg(
        achieved=("omega", "mean"), failure=("failure_rate", "mean")
    )
    ax.plot(grouped.achieved, grouped.failure, marker="o")
    ax.axvline(1.0, linestyle="--", linewidth=1)
    ax.set_xlabel("Mean achieved Omega_A")
    ax.set_ylabel("Mean boundary-crossing probability")
    ax.set_title("NH4-O targeted assurance boundary")
    ax.grid(alpha=0.2)
    path = output / "nh4_targeted_boundary_curve.png"
    fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig); paths.append(path)
    return paths


def run_stage2_cycle6(repository_root: str | Path, *, seed: int = 20260821) -> dict[str, object]:
    root = Path(repository_root)
    results_dir = root / "results" / "stage2_cycle6"
    figures_dir = root / "figures" / "stage2_cycle6"
    results_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    nh2_runs, nh2_scenarios, nh2_metrics, nh2_predictions, nh2_summary = run_nh2_cycle6(seed=seed)
    nh2_runs.to_csv(results_dir / "nh2_replications.csv", index=False)
    nh2_scenarios.to_csv(results_dir / "nh2_scenarios.csv", index=False)
    nh2_metrics.to_csv(results_dir / "nh2_metrics.csv", index=False)
    nh2_predictions.to_csv(results_dir / "nh2_predictions.csv", index=False)
    pd.DataFrame(nh2_summary["robustness"]).to_csv(results_dir / "nh2_robustness.csv", index=False)

    nh4_runs, nh4_scenarios, nh4_predictions, nh4_summary = run_nh4_cycle6(seed=seed)
    nh4_runs.to_csv(results_dir / "nh4_replications.csv", index=False)
    nh4_scenarios.to_csv(results_dir / "nh4_scenarios.csv", index=False)
    nh4_predictions.to_csv(results_dir / "nh4_predictions.csv", index=False)
    pd.DataFrame(nh4_summary["robustness"]).to_csv(results_dir / "nh4_robustness.csv", index=False)

    figures = write_cycle6_figures(
        nh2_scenarios,
        nh2_metrics,
        nh2_predictions,
        nh2_summary,
        nh4_scenarios,
        nh4_predictions,
        nh4_summary,
        figures_dir,
    )
    summary = {
        "study": "Stage 2 Cycle 6",
        "protocol_id": "FAS-S2-C6-2026-08-19",
        "seed": seed,
        "evidence_scope": "model-conditioned; notional parameters; no external validation",
        "NH2_T": nh2_summary,
        "NH4_O": nh4_summary,
        "assessments": [
            Cycle6Result(
                hypothesis="NH2-T",
                supported_in_model=bool(nh2_summary["supported_in_model"]),
                decision="supported" if nh2_summary["supported_in_model"] else "refuted or not supported",
                evidence_level="model-conditioned",
                primary_result=(
                    f"Selected {nh2_summary['selected_temporal_candidate']}; MAE improvement "
                    f"{100*float(nh2_summary['mae_improvement_fraction']):.1f}% and AUC delta "
                    f"{float(nh2_summary['auc_delta']):.3f}."
                ),
                limitations="Synthetic directed propagation with noisy but model-derived observables.",
            ).as_dict(),
            Cycle6Result(
                hypothesis="NH4-O",
                supported_in_model=bool(nh4_summary["supported_in_model"]),
                decision="supported" if nh4_summary["supported_in_model"] else "refuted, invalid, or not supported",
                evidence_level="analytic plus model-conditioned",
                primary_result=(
                    f"Omega AUC {float(nh4_summary['omega_auc']):.3f}; AUC delta "
                    f"{float(nh4_summary['auc_delta']):.3f}; balanced accuracy "
                    f"{float(nh4_summary['omega_one_balanced_accuracy']):.3f}."
                ),
                limitations="Resource demand, capacity, and stochastic work are notional.",
            ).as_dict(),
        ],
        "dataset_counts": {
            "nh2_replications": len(nh2_runs),
            "nh2_scenarios": len(nh2_scenarios),
            "nh4_replications": len(nh4_runs),
            "nh4_scenarios": len(nh4_scenarios),
        },
        "figures": [str(path.relative_to(root)) for path in figures],
    }
    (results_dir / "stage2_cycle6_summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=True), encoding="utf-8"
    )
    return summary
