"""Stage 2 Cycle 3 confirmatory research harness.

The protocol is fixed in docs/stage2_cycle3_preregistered_protocol.md. All
parameters remain notional. Outputs are model-conditioned and must not be
presented as observed deployment evidence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from fleet_sim.analysis.fleet_admission_stress import (
    admission_load_predictors,
    build_admission_pools,
    make_admission_trajectory,
    simulate_admission_queue,
)
from fleet_sim.security.directed_ngm import (
    LAYER_NAMES,
    attack_operator_predictors,
    build_directed_attack_scenario,
    simulate_latent_compromise,
)


@dataclass(frozen=True)
class ResearchDecision:
    hypothesis: str
    supported_in_model: bool
    evidence_level: str
    primary_result: str
    limitations: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _roc_auc(y_true: Sequence[int] | np.ndarray, scores: Sequence[float] | np.ndarray) -> float:
    y = np.asarray(y_true, dtype=int)
    s = np.asarray(scores, dtype=float)
    positives = y == 1
    negatives = y == 0
    n_positive = int(positives.sum())
    n_negative = int(negatives.sum())
    if n_positive == 0 or n_negative == 0:
        return 0.5
    order = np.argsort(s, kind="mergesort")
    sorted_scores = s[order]
    ranks = np.empty(len(s), dtype=float)
    start = 0
    while start < len(s):
        end = start + 1
        while end < len(s) and sorted_scores[end] == sorted_scores[start]:
            end += 1
        ranks[order[start:end]] = (start + 1 + end) / 2.0
        start = end
    rank_sum = float(ranks[positives].sum())
    return float(
        (rank_sum - n_positive * (n_positive + 1) / 2.0)
        / (n_positive * n_negative)
    )


def _scalar_design(
    predictor: Sequence[float] | np.ndarray,
    initial_seed_fraction: Sequence[float] | np.ndarray,
    n_agents: Sequence[float] | np.ndarray,
) -> np.ndarray:
    x = np.log1p(np.maximum(0.0, np.asarray(predictor, dtype=float)))
    seed_fraction = np.asarray(initial_seed_fraction, dtype=float)
    log_n = np.log(np.maximum(1.0, np.asarray(n_agents, dtype=float)))
    return np.column_stack(
        [
            np.ones(len(x), dtype=float),
            x,
            x**2,
            seed_fraction,
            log_n,
        ]
    )


def _fit_ridge(design: np.ndarray, target: np.ndarray, ridge: float = 1e-5) -> np.ndarray:
    penalty = np.eye(design.shape[1], dtype=float) * ridge
    penalty[0, 0] = 0.0
    return np.linalg.solve(design.T @ design + penalty, design.T @ target)


def _fit_continuous_predictor(
    train: pd.DataFrame,
    test: pd.DataFrame,
    predictor: str,
) -> np.ndarray:
    train_design = _scalar_design(
        train[predictor], train.initial_seed_fraction, train.n_agents
    )
    weights = _fit_ridge(train_design, train.ever_fraction.to_numpy(float))
    test_design = _scalar_design(
        test[predictor], test.initial_seed_fraction, test.n_agents
    )
    return np.clip(test_design @ weights, 0.0, 1.0)


def _fit_binomial_design(
    design: np.ndarray,
    successes: np.ndarray,
    trials: np.ndarray,
) -> np.ndarray:
    successes = np.asarray(successes, dtype=float)
    trials = np.asarray(trials, dtype=float)

    def objective(weights: np.ndarray) -> tuple[float, np.ndarray]:
        linear = np.clip(design @ weights, -35.0, 35.0)
        probability = 1.0 / (1.0 + np.exp(-linear))
        eps = 1e-12
        loss = -np.sum(
            successes * np.log(probability + eps)
            + (trials - successes) * np.log(1.0 - probability + eps)
        )
        regularization = 1e-4 * np.sum(weights[1:] ** 2)
        gradient = design.T @ (trials * probability - successes)
        gradient[1:] += 2e-4 * weights[1:]
        return float(loss + regularization), gradient

    result = minimize(
        lambda weights: objective(weights)[0],
        np.zeros(design.shape[1], dtype=float),
        jac=lambda weights: objective(weights)[1],
        method="BFGS",
    )
    return np.asarray(result.x, dtype=float)


def _predict_binomial(design: np.ndarray, weights: np.ndarray) -> np.ndarray:
    linear = np.clip(design @ weights, -35.0, 35.0)
    return 1.0 / (1.0 + np.exp(-linear))


def _finite_mean(values: pd.Series) -> float:
    array = values.to_numpy(float)
    finite = array[np.isfinite(array)]
    return float(finite.mean()) if len(finite) else float("nan")


def _nh2_topology_matrix(split: str) -> tuple[list[tuple[str, dict[str, int]]], list[tuple[str, dict[str, int]]], tuple[int, ...]]:
    if split == "train":
        auth = [
            ("random_regular", {"degree": 4}),
            ("erdos_renyi", {"degree": 6}),
        ]
        dependency = [
            ("random_regular", {"degree": 3}),
            ("erdos_renyi", {"degree": 5}),
        ]
        return auth, dependency, (96, 192)
    if split == "test":
        auth = [
            ("barabasi_albert", {"attachment": 2}),
            ("hierarchical", {"span": 6}),
        ]
        dependency = [
            ("barabasi_albert", {"attachment": 3}),
            ("hierarchical", {"span": 8}),
        ]
        return auth, dependency, (384,)
    raise ValueError(split)


def run_nh2_directed_ngm(
    *,
    seed: int,
    replications: int = 12,
    bootstrap_replications: int = 1_000,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, ResearchDecision, dict[str, object]]:
    if replications < 2:
        raise ValueError("at least two replications are required")
    hazard_scales = (0.55, 0.80, 1.05, 1.35)
    seed_modes = ("single", "correlated")
    run_rows: list[dict[str, float | int | str]] = []
    scenario_rows: list[dict[str, float | int | str]] = []
    scenario_id = 0

    for split in ("train", "test"):
        auth_families, dependency_families, fleet_sizes = _nh2_topology_matrix(split)
        for n in fleet_sizes:
            for auth_family, auth_kwargs in auth_families:
                for dependency_family, dependency_kwargs in dependency_families:
                    for hazard_scale in hazard_scales:
                        for seed_mode in seed_modes:
                            scenario_seed = (
                                seed
                                + 1_000_003 * scenario_id
                                + 101 * n
                                + int(round(hazard_scale * 10_000))
                            )
                            scenario = build_directed_attack_scenario(
                                scenario_id=scenario_id,
                                split=split,
                                n=n,
                                seed=scenario_seed,
                                auth_topology=auth_family,
                                dependency_topology=dependency_family,
                                auth_kwargs=auth_kwargs,
                                dependency_kwargs=dependency_kwargs,
                                hazard_scale=hazard_scale,
                                seed_mode=seed_mode,
                                correlated_seed_fraction=0.025,
                            )
                            predictors = attack_operator_predictors(scenario).as_dict()
                            scenario_run_rows: list[dict[str, float | int | str]] = []
                            for replication in range(replications):
                                replication_seed = seed + scenario_id * 100_000 + replication
                                outcome = simulate_latent_compromise(
                                    scenario,
                                    seed=replication_seed,
                                )
                                row: dict[str, float | int | str] = {
                                    "scenario_id": scenario_id,
                                    "split": split,
                                    "replication": replication,
                                    "n_agents": n,
                                    "auth_topology": auth_family,
                                    "dependency_topology": dependency_family,
                                    "hazard_scale": hazard_scale,
                                    "seed_mode": seed_mode,
                                    "scenario_seed": scenario_seed,
                                    **predictors,
                                    **outcome,
                                }
                                run_rows.append(row)
                                scenario_run_rows.append(row)
                            frame = pd.DataFrame(scenario_run_rows)
                            scenario_rows.append(
                                {
                                    "scenario_id": scenario_id,
                                    "split": split,
                                    "n_agents": n,
                                    "auth_topology": auth_family,
                                    "dependency_topology": dependency_family,
                                    "hazard_scale": hazard_scale,
                                    "seed_mode": seed_mode,
                                    "scenario_seed": scenario_seed,
                                    "replications": replications,
                                    "initial_seed_fraction": float(frame.initial_seed_fraction.mean()),
                                    "ever_fraction": float(frame.ever_fraction.mean()),
                                    "peak_fraction": float(frame.peak_fraction.mean()),
                                    "outbreak_successes": int(frame.major_outbreak.sum()),
                                    "outbreak_probability": float(frame.major_outbreak.mean()),
                                    "mean_duration_s": float(frame.duration_s.mean()),
                                    "mean_time_to_first_detection_s": _finite_mean(
                                        frame.time_to_first_detection_s
                                    ),
                                    "mean_transmissions_after_first_detection": float(
                                        frame.transmissions_after_first_detection.mean()
                                    ),
                                    **predictors,
                                }
                            )
                            scenario_id += 1

    runs = pd.DataFrame(run_rows)
    scenarios = pd.DataFrame(scenario_rows)
    train = scenarios[scenarios.split == "train"].copy()
    test = scenarios[scenarios.split == "test"].copy()
    predictor_names = [
        "raw_auth_radius",
        "static_aggregate_radius",
        "nonbacktracking_radius",
        "operational_ngm_radius",
        "oracle_ngm_radius",
        *[f"operational_without_{name}" for name in LAYER_NAMES],
    ]
    predictions = test[
        ["scenario_id", "ever_fraction", "outbreak_probability"]
    ].copy()
    predictor_metrics: dict[str, dict[str, float]] = {}
    majority_outbreak = (test.outbreak_probability.to_numpy(float) >= 0.5).astype(int)
    for predictor in predictor_names:
        continuous_prediction = _fit_continuous_predictor(train, test, predictor)
        predictions[f"{predictor}_ever_prediction"] = continuous_prediction
        mae = float(np.mean(np.abs(continuous_prediction - test.ever_fraction.to_numpy(float))))

        train_design = _scalar_design(
            train[predictor], train.initial_seed_fraction, train.n_agents
        )
        test_design = _scalar_design(
            test[predictor], test.initial_seed_fraction, test.n_agents
        )
        weights = _fit_binomial_design(
            train_design,
            train.outbreak_successes.to_numpy(float),
            train.replications.to_numpy(float),
        )
        outbreak_prediction = _predict_binomial(test_design, weights)
        predictions[f"{predictor}_outbreak_prediction"] = outbreak_prediction
        predictor_metrics[predictor] = {
            "heldout_mae_ever_fraction": mae,
            "heldout_outbreak_auc": _roc_auc(majority_outbreak, outbreak_prediction),
            "heldout_outbreak_brier": float(
                np.mean(
                    (outbreak_prediction - test.outbreak_probability.to_numpy(float)) ** 2
                )
            ),
        }

    raw_mae = predictor_metrics["raw_auth_radius"]["heldout_mae_ever_fraction"]
    static_mae = predictor_metrics["static_aggregate_radius"]["heldout_mae_ever_fraction"]
    operational_mae = predictor_metrics["operational_ngm_radius"]["heldout_mae_ever_fraction"]
    raw_reduction_fraction = (raw_mae - operational_mae) / max(raw_mae, 1e-12)
    static_reduction_fraction = (static_mae - operational_mae) / max(static_mae, 1e-12)

    rng = np.random.default_rng(seed + 8_888_881)
    observed = test.ever_fraction.to_numpy(float)
    raw_prediction = predictions.raw_auth_radius_ever_prediction.to_numpy(float)
    static_prediction = predictions.static_aggregate_radius_ever_prediction.to_numpy(float)
    operational_prediction = predictions.operational_ngm_radius_ever_prediction.to_numpy(float)
    bootstrap_raw_reduction: list[float] = []
    bootstrap_static_reduction: list[float] = []
    for _ in range(bootstrap_replications):
        sample = rng.integers(0, len(test), size=len(test))
        op_error = float(np.mean(np.abs(operational_prediction[sample] - observed[sample])))
        raw_error = float(np.mean(np.abs(raw_prediction[sample] - observed[sample])))
        static_error = float(np.mean(np.abs(static_prediction[sample] - observed[sample])))
        bootstrap_raw_reduction.append(raw_error - op_error)
        bootstrap_static_reduction.append(static_error - op_error)

    ablation_penalties = {
        name: (
            predictor_metrics[f"operational_without_{name}"]["heldout_mae_ever_fraction"]
            - operational_mae
        )
        for name in LAYER_NAMES
    }
    meaningful_ablations = sum(value >= 0.003 for value in ablation_penalties.values())
    raw_interval = [
        float(np.quantile(bootstrap_raw_reduction, 0.025)),
        float(np.quantile(bootstrap_raw_reduction, 0.975)),
    ]
    static_interval = [
        float(np.quantile(bootstrap_static_reduction, 0.025)),
        float(np.quantile(bootstrap_static_reduction, 0.975)),
    ]
    criteria = {
        "operational_mae_reduction_vs_raw_at_least_15pct": raw_reduction_fraction >= 0.15,
        "operational_mae_reduction_vs_static_at_least_5pct": static_reduction_fraction >= 0.05,
        "bootstrap_lower_bounds_positive": raw_interval[0] > 0.0 and static_interval[0] > 0.0,
        "at_least_two_layer_ablations_worsen_mae_by_0_003": meaningful_ablations >= 2,
    }
    supported = bool(all(criteria.values()))
    summary: dict[str, object] = {
        "train_scenarios": int(len(train)),
        "heldout_scenarios": int(len(test)),
        "replications_per_scenario": replications,
        "predictor_metrics": predictor_metrics,
        "operational_mae_reduction_vs_raw_fraction": float(raw_reduction_fraction),
        "operational_mae_reduction_vs_static_fraction": float(static_reduction_fraction),
        "bootstrap_95pct_absolute_mae_reduction": {
            "versus_raw_authorization": raw_interval,
            "versus_static_aggregate": static_interval,
        },
        "ablation_mae_penalties": ablation_penalties,
        "meaningful_ablation_count": int(meaningful_ablations),
        "criteria": criteria,
        "supported_in_model": supported,
    }
    decision = ResearchDecision(
        hypothesis="NH2-D",
        supported_in_model=supported,
        evidence_level="model-conditioned",
        primary_result=(
            f"Operational K held-out MAE reduction was {100.0 * raw_reduction_fraction:.1f}% "
            f"versus raw authorization and {100.0 * static_reduction_fraction:.1f}% versus "
            "the static aggregate."
        ),
        limitations=(
            "The propagation substrate, transition intensities, observation errors, and response "
            "mechanisms are synthetic. Transfer is internal to the declared model family."
        ),
    )
    return runs, scenarios, predictions, decision, summary


def _admission_design(score: Sequence[float] | np.ndarray) -> np.ndarray:
    x = np.log1p(np.maximum(0.0, np.asarray(score, dtype=float)))
    return np.column_stack([np.ones(len(x)), x, x**2])


def _balanced_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y = np.asarray(y_true, dtype=int)
    prediction = np.asarray(y_pred, dtype=int)
    positive = y == 1
    negative = y == 0
    sensitivity = float(np.mean(prediction[positive] == 1)) if positive.any() else 0.5
    specificity = float(np.mean(prediction[negative] == 0)) if negative.any() else 0.5
    return 0.5 * (sensitivity + specificity)


def _calibrate_threshold(scores: np.ndarray, labels: np.ndarray) -> tuple[float, float]:
    unique = np.unique(np.asarray(scores, dtype=float))
    if len(unique) == 1:
        return float(unique[0]), 0.5
    candidates = np.concatenate(
        [
            [unique[0] - 1e-9],
            0.5 * (unique[:-1] + unique[1:]),
            [unique[-1] + 1e-9],
        ]
    )
    best_threshold = float(candidates[0])
    best_score = -1.0
    for threshold in candidates:
        score = _balanced_accuracy(labels, (scores >= threshold).astype(int))
        if score > best_score + 1e-12:
            best_threshold = float(threshold)
            best_score = float(score)
    return best_threshold, best_score


def run_nh4_admission_load(
    *,
    seed: int,
    replications: int = 12,
    bootstrap_replications: int = 1_000,
) -> tuple[pd.DataFrame, pd.DataFrame, ResearchDecision, dict[str, object]]:
    if replications < 2:
        raise ValueError("at least two replications are required")
    regions = {
        "train": {
            "profiles": ("linear", "staged", "burst"),
            "fleet_sizes": (1_500, 3_000, 5_000),
        },
        "test": {
            "profiles": ("logistic", "exponential", "step"),
            "fleet_sizes": (2_200, 4_200, 8_000),
        },
    }
    durations = (35.0, 75.0, 140.0, 230.0)
    coupling_scales = (0.65, 1.00, 1.35)
    run_rows: list[dict[str, float | int | str]] = []
    scenario_rows: list[dict[str, float | int | str]] = []
    selected_trace_rows: list[pd.DataFrame] = []
    scenario_id = 0

    for split, region in regions.items():
        for profile in region["profiles"]:
            for final_n in region["fleet_sizes"]:
                for duration_s in durations:
                    for coupling_scale in coupling_scales:
                        scenario_seed = (
                            seed
                            + scenario_id * 1_000_003
                            + int(final_n)
                            + int(duration_s * 100)
                            + int(coupling_scale * 10_000)
                        )
                        system = build_admission_pools(
                            final_n=int(final_n),
                            final_baseline_fraction=0.55,
                            coupling_scale=float(coupling_scale),
                            seed=scenario_seed,
                        )
                        trajectory = make_admission_trajectory(
                            str(profile),
                            final_n=int(final_n),
                            duration_s=float(duration_s),
                            initial_fraction=0.20,
                            recovery_window_s=150.0,
                            dt_s=0.5,
                        )
                        predictors = admission_load_predictors(
                            trajectory.n_agents,
                            trajectory.admission_rate_agents_s,
                            system,
                            dt_s=0.5,
                        )
                        if (
                            split == "test"
                            and int(final_n) == max(regions["test"]["fleet_sizes"])
                            and float(duration_s) in {75.0, 230.0}
                            and abs(float(coupling_scale) - 1.0) < 1e-12
                        ):
                            trace = predictors["coupled_trace"].copy()
                            trace["scenario_id"] = scenario_id
                            trace["split"] = split
                            trace["profile"] = profile
                            trace["final_n"] = int(final_n)
                            trace["duration_s"] = float(duration_s)
                            selected_trace_rows.append(trace)

                        scenario_outcomes: list[dict[str, float | int | str]] = []
                        for replication in range(replications):
                            replication_seed = seed + 50_000_000 + scenario_id * 100_000 + replication
                            outcome = simulate_admission_queue(
                                trajectory,
                                system,
                                seed=replication_seed,
                            )
                            common: dict[str, float | int | str] = {
                                "scenario_id": scenario_id,
                                "split": split,
                                "replication": replication,
                                "profile": profile,
                                "final_n": int(final_n),
                                "duration_s": float(duration_s),
                                "coupling_scale": float(coupling_scale),
                                "scenario_seed": scenario_seed,
                                "peak_population_velocity": float(
                                    predictors["peak_population_velocity"]
                                ),
                                "peak_work_headroom_ratio": float(
                                    predictors["peak_work_headroom_ratio"]
                                ),
                                "independent_stress": float(predictors["independent_stress"]),
                                "coupled_stress": float(predictors["coupled_stress"]),
                                "binding_independent_resource": str(
                                    predictors["binding_independent_resource"]
                                ),
                                "binding_coupled_resource": str(
                                    predictors["binding_coupled_resource"]
                                ),
                            }
                            row = {**common, **outcome}
                            run_rows.append(row)
                            scenario_outcomes.append(row)
                        frame = pd.DataFrame(scenario_outcomes)
                        scenario_rows.append(
                            {
                                "scenario_id": scenario_id,
                                "split": split,
                                "profile": profile,
                                "final_n": int(final_n),
                                "duration_s": float(duration_s),
                                "coupling_scale": float(coupling_scale),
                                "scenario_seed": scenario_seed,
                                "replications": replications,
                                "inadmissible_successes": int(frame.boundary_crossed.sum()),
                                "inadmissible_probability": float(frame.boundary_crossed.mean()),
                                "mean_minimum_assurance_margin": float(
                                    frame.minimum_assurance_margin.mean()
                                ),
                                "mean_fraction_time_outside_boundary": float(
                                    frame.fraction_time_outside_boundary.mean()
                                ),
                                "mean_first_boundary_crossing_time_s": _finite_mean(
                                    frame.first_boundary_crossing_time_s
                                ),
                                "mean_recovery_time_after_admission_s": _finite_mean(
                                    frame.recovery_time_after_admission_s
                                ),
                                "mean_maximum_wait_ratio": float(frame.maximum_wait_ratio.mean()),
                                "peak_population_velocity": float(
                                    predictors["peak_population_velocity"]
                                ),
                                "peak_work_headroom_ratio": float(
                                    predictors["peak_work_headroom_ratio"]
                                ),
                                "independent_stress": float(predictors["independent_stress"]),
                                "coupled_stress": float(predictors["coupled_stress"]),
                                "binding_independent_resource": str(
                                    predictors["binding_independent_resource"]
                                ),
                                "binding_coupled_resource": str(
                                    predictors["binding_coupled_resource"]
                                ),
                            }
                        )
                        scenario_id += 1

    runs = pd.DataFrame(run_rows)
    scenarios = pd.DataFrame(scenario_rows)
    train = scenarios[scenarios.split == "train"].copy()
    test = scenarios[scenarios.split == "test"].copy()
    predictor_columns = {
        "final_n": "final_n",
        "peak_population_velocity": "peak_population_velocity",
        "peak_work_headroom_ratio": "peak_work_headroom_ratio",
        "independent_stress": "independent_stress",
        "coupled_stress": "coupled_stress",
    }
    test_output = test.copy()
    predictor_metrics: dict[str, dict[str, float]] = {}
    test_labels = (test.inadmissible_probability.to_numpy(float) >= 0.5).astype(int)
    for name, column in predictor_columns.items():
        train_design = _admission_design(train[column].to_numpy(float))
        test_design = _admission_design(test[column].to_numpy(float))
        weights = _fit_binomial_design(
            train_design,
            train.inadmissible_successes.to_numpy(float),
            train.replications.to_numpy(float),
        )
        probability = _predict_binomial(test_design, weights)
        test_output[f"{name}_prediction"] = probability
        predictor_metrics[name] = {
            "auc": _roc_auc(test_labels, probability),
            "brier": float(
                np.mean(
                    (probability - test.inadmissible_probability.to_numpy(float)) ** 2
                )
            ),
        }

    train_labels = (train.inadmissible_probability.to_numpy(float) >= 0.5).astype(int)
    critical_threshold, train_balanced_accuracy = _calibrate_threshold(
        train.coupled_stress.to_numpy(float), train_labels
    )
    heldout_balanced_accuracy = _balanced_accuracy(
        test_labels,
        (test.coupled_stress.to_numpy(float) >= critical_threshold).astype(int),
    )
    size_thresholds: list[float] = []
    for final_n, group in train.groupby("final_n"):
        labels = (group.inadmissible_probability.to_numpy(float) >= 0.5).astype(int)
        if labels.min() == labels.max():
            continue
        threshold, _ = _calibrate_threshold(group.coupled_stress.to_numpy(float), labels)
        size_thresholds.append(float(threshold))
    threshold_cv = (
        float(np.std(size_thresholds, ddof=1) / np.mean(size_thresholds))
        if len(size_thresholds) >= 2 and np.mean(size_thresholds) > 0.0
        else float("nan")
    )

    coupled_auc = predictor_metrics["coupled_stress"]["auc"]
    independent_auc = predictor_metrics["independent_stress"]["auc"]
    velocity_auc = predictor_metrics["peak_population_velocity"]["auc"]
    coupled_brier = predictor_metrics["coupled_stress"]["brier"]
    independent_brier = predictor_metrics["independent_stress"]["brier"]

    rng = np.random.default_rng(seed + 71_717_171)
    coupled_probability = test_output.coupled_stress_prediction.to_numpy(float)
    independent_probability = test_output.independent_stress_prediction.to_numpy(float)
    velocity_probability = test_output.peak_population_velocity_prediction.to_numpy(float)
    observed_probability = test.inadmissible_probability.to_numpy(float)
    auc_delta_independent: list[float] = []
    auc_delta_velocity: list[float] = []
    brier_delta: list[float] = []
    for _ in range(bootstrap_replications):
        sample = rng.integers(0, len(test), size=len(test))
        labels = test_labels[sample]
        auc_delta_independent.append(
            _roc_auc(labels, coupled_probability[sample])
            - _roc_auc(labels, independent_probability[sample])
        )
        auc_delta_velocity.append(
            _roc_auc(labels, coupled_probability[sample])
            - _roc_auc(labels, velocity_probability[sample])
        )
        brier_delta.append(
            float(
                np.mean((independent_probability[sample] - observed_probability[sample]) ** 2)
                - np.mean((coupled_probability[sample] - observed_probability[sample]) ** 2)
            )
        )

    criteria = {
        "coupled_auc_exceeds_independent_by_0_03": coupled_auc - independent_auc >= 0.03,
        "coupled_auc_exceeds_velocity_by_0_10": coupled_auc - velocity_auc >= 0.10,
        "coupled_brier_lower_than_independent": coupled_brier < independent_brier,
        "heldout_balanced_accuracy_at_least_0_75": heldout_balanced_accuracy >= 0.75,
        "training_size_threshold_cv_no_more_than_0_25": bool(
            np.isfinite(threshold_cv) and threshold_cv <= 0.25
        ),
    }
    supported = bool(all(criteria.values()))
    selected_trajectories = (
        pd.concat(selected_trace_rows, ignore_index=True)
        if selected_trace_rows
        else pd.DataFrame()
    )
    summary: dict[str, object] = {
        "train_scenarios": int(len(train)),
        "heldout_scenarios": int(len(test)),
        "replications_per_scenario": replications,
        "predictor_metrics": predictor_metrics,
        "train_critical_threshold": float(critical_threshold),
        "train_threshold_balanced_accuracy": float(train_balanced_accuracy),
        "heldout_threshold_balanced_accuracy": float(heldout_balanced_accuracy),
        "training_size_thresholds": size_thresholds,
        "training_size_threshold_cv": threshold_cv,
        "bootstrap_95pct": {
            "auc_delta_coupled_minus_independent": [
                float(np.quantile(auc_delta_independent, 0.025)),
                float(np.quantile(auc_delta_independent, 0.975)),
            ],
            "auc_delta_coupled_minus_velocity": [
                float(np.quantile(auc_delta_velocity, 0.025)),
                float(np.quantile(auc_delta_velocity, 0.975)),
            ],
            "brier_improvement_independent_minus_coupled": [
                float(np.quantile(brier_delta, 0.025)),
                float(np.quantile(brier_delta, 0.975)),
            ],
        },
        "criteria": criteria,
        "supported_in_model": supported,
        "selected_trajectories": selected_trajectories,
    }
    decision = ResearchDecision(
        hypothesis="NH4-L",
        supported_in_model=supported,
        evidence_level="analytic plus model-conditioned",
        primary_result=(
            f"Coupled stress held-out AUC was {coupled_auc:.3f}, compared with "
            f"{independent_auc:.3f} for independent stress and {velocity_auc:.3f} for peak dN/dt."
        ),
        limitations=(
            "The resource work rates, routing, queue budgets, service disturbances, and escalation "
            "mechanisms are notional. The critical threshold is not an operational deployment limit."
        ),
    )
    return runs, test_output, decision, summary
