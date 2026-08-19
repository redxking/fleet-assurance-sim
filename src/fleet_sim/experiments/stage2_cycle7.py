"""Stage 2 Cycle 7 preregistered two-stage compromise experiment."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from fleet_sim.analysis.compromise_hurdle import (
    add_replication_conditionals,
    fit_compromise_hurdle,
    predict_compromise_hurdle,
)
from fleet_sim.experiments.stage2_cycle6 import (
    _constrained_continuous_fit,
    _generate_nh2_cycle6,
    _pava_fit,
    _pava_predict,
    _roc_auc,
)


@dataclass(frozen=True)
class Cycle7BlockResult:
    block: int
    seed: int
    valid: bool
    positive_test_scenarios: int
    negative_test_scenarios: int
    training_scenarios_with_outbreak_fraction: float
    hurdle_mae: float
    nb_direct_mae: float
    temporal_nb_direct_mae: float
    best_baseline: str
    best_baseline_mae: float
    mae_improvement_fraction: float
    hurdle_brier: float
    nb_isotonic_brier: float
    brier_improvement_fraction: float
    hurdle_auc: float
    nb_auc: float
    auc_delta: float
    severity_coefficients: list[float]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _evaluate_block(
    block: int,
    seed: int,
    *,
    replications: int = 30,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Cycle7BlockResult]:
    runs, scenarios = _generate_nh2_cycle6(seed=seed, replications=replications, reduced=False)
    enriched = add_replication_conditionals(scenarios, runs)
    train = enriched[enriched.split == "train"].copy()
    test = enriched[enriched.split == "test"].copy()

    model = fit_compromise_hurdle(
        train,
        initiation_score="temporal_nb",
        severity_score="nb_pre",
        minimum_outbreak_fraction=0.10,
    )
    hurdle = predict_compromise_hurdle(model, test)
    nb_direct, _, _ = _constrained_continuous_fit(train, test, "nb_pre", "mean_ever_fraction")
    temporal_direct, _, _ = _constrained_continuous_fit(train, test, "temporal_nb", "mean_ever_fraction")
    nb_x, nb_y = _pava_fit(
        train.nb_pre.to_numpy(float),
        train.outbreak_rate.to_numpy(float),
        train.replications.to_numpy(float),
    )
    nb_probability = _pava_predict(test.nb_pre.to_numpy(float), nb_x, nb_y)

    observed = test.mean_ever_fraction.to_numpy(float)
    label = (test.outbreak_rate.to_numpy(float) >= 0.10).astype(int)
    hurdle_mae = float(np.mean(np.abs(hurdle.expected_final_fraction - observed)))
    nb_mae = float(np.mean(np.abs(nb_direct - observed)))
    temporal_mae = float(np.mean(np.abs(temporal_direct - observed)))
    if nb_mae <= temporal_mae:
        best_name, best_mae, best_prediction = "nb_pre", nb_mae, nb_direct
    else:
        best_name, best_mae, best_prediction = "temporal_nb", temporal_mae, temporal_direct

    positive = int(label.sum())
    negative = int(len(label) - positive)
    training_outbreak_fraction = float(np.mean(train.outbreak_replication_count.to_numpy(int) > 0))
    finite = bool(
        np.isfinite(hurdle.expected_final_fraction).all()
        and np.isfinite(hurdle.outbreak_probability).all()
        and np.isfinite(model.severity_coefficients).all()
    )
    exact_replications = bool((scenarios.replications.to_numpy(int) == replications).all())
    valid = positive >= 20 and negative >= 20 and training_outbreak_fraction >= 0.20 and finite and exact_replications

    block_result = Cycle7BlockResult(
        block=block,
        seed=seed,
        valid=valid,
        positive_test_scenarios=positive,
        negative_test_scenarios=negative,
        training_scenarios_with_outbreak_fraction=training_outbreak_fraction,
        hurdle_mae=hurdle_mae,
        nb_direct_mae=nb_mae,
        temporal_nb_direct_mae=temporal_mae,
        best_baseline=best_name,
        best_baseline_mae=best_mae,
        mae_improvement_fraction=float((best_mae - hurdle_mae) / max(best_mae, 1e-12)),
        hurdle_brier=float(np.mean((hurdle.outbreak_probability - test.outbreak_rate.to_numpy(float)) ** 2)),
        nb_isotonic_brier=float(np.mean((nb_probability - test.outbreak_rate.to_numpy(float)) ** 2)),
        brier_improvement_fraction=float(
            (np.mean((nb_probability - test.outbreak_rate.to_numpy(float)) ** 2)
             - np.mean((hurdle.outbreak_probability - test.outbreak_rate.to_numpy(float)) ** 2))
            / max(np.mean((nb_probability - test.outbreak_rate.to_numpy(float)) ** 2), 1e-12)
        ),
        hurdle_auc=_roc_auc(label, hurdle.outbreak_probability),
        nb_auc=_roc_auc(label, test.nb_pre.to_numpy(float)),
        auc_delta=float(_roc_auc(label, hurdle.outbreak_probability) - _roc_auc(label, test.nb_pre.to_numpy(float))),
        severity_coefficients=model.severity_coefficients.tolist(),
    )

    runs = runs.copy()
    scenarios = scenarios.copy()
    runs.insert(0, "block", block)
    scenarios.insert(0, "block", block)
    prediction = test[[
        "scenario_id", "split", "n_agents", "auth_family", "dependency_family",
        "segmentation", "mean_ever_fraction", "outbreak_rate", "nb_pre", "temporal_nb",
    ]].copy()
    prediction.insert(0, "block", block)
    prediction["hurdle_outbreak_probability"] = hurdle.outbreak_probability
    prediction["hurdle_conditional_severity"] = hurdle.conditional_outbreak_severity
    prediction["hurdle_expected_fraction"] = hurdle.expected_final_fraction
    prediction["nb_direct_prediction"] = nb_direct
    prediction["temporal_nb_direct_prediction"] = temporal_direct
    prediction["best_baseline_prediction"] = best_prediction
    prediction["candidate_absolute_error"] = np.abs(hurdle.expected_final_fraction - observed)
    prediction["baseline_absolute_error"] = np.abs(best_prediction - observed)
    return runs, scenarios, prediction, block_result


def _hierarchical_bootstrap(
    predictions: pd.DataFrame,
    *,
    seed: int,
    draws: int = 5000,
) -> dict[str, list[float]]:
    rng = np.random.default_rng(seed)
    blocks = sorted(predictions.block.unique().tolist())
    absolute: list[float] = []
    fractional: list[float] = []
    for _ in range(draws):
        candidate_errors: list[float] = []
        baseline_errors: list[float] = []
        for sampled_block in rng.choice(blocks, size=len(blocks), replace=True):
            frame = predictions[predictions.block == sampled_block]
            indices = rng.integers(0, len(frame), size=len(frame))
            candidate_errors.extend(frame.candidate_absolute_error.to_numpy(float)[indices].tolist())
            baseline_errors.extend(frame.baseline_absolute_error.to_numpy(float)[indices].tolist())
        candidate_mae = float(np.mean(candidate_errors))
        baseline_mae = float(np.mean(baseline_errors))
        absolute.append(baseline_mae - candidate_mae)
        fractional.append((baseline_mae - candidate_mae) / max(baseline_mae, 1e-12))
    return {
        "absolute_mae_reduction": np.quantile(absolute, [0.025, 0.975]).tolist(),
        "fractional_mae_improvement": np.quantile(fractional, [0.025, 0.975]).tolist(),
    }


def _write_figures(predictions: pd.DataFrame, block_results: pd.DataFrame, output: Path) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    fig, ax = plt.subplots(figsize=(8.2, 5.5))
    x = np.arange(len(block_results))
    width = 0.34
    ax.bar(x - width / 2, block_results.best_baseline_mae, width, label="Best direct baseline")
    ax.bar(x + width / 2, block_results.hurdle_mae, width, label="Two-stage hurdle")
    ax.set_xticks(x, [f"Block {int(v)}" for v in block_results.block])
    ax.set_ylabel("Held-out MAE")
    ax.set_title("Cycle 7 block-level held-out error")
    ax.legend()
    fig.tight_layout()
    path = output / "cycle7_block_mae.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)

    fig, ax = plt.subplots(figsize=(7.2, 5.6))
    ax.scatter(predictions.mean_ever_fraction, predictions.best_baseline_prediction, alpha=0.40, label="Best direct baseline")
    ax.scatter(predictions.mean_ever_fraction, predictions.hurdle_expected_fraction, alpha=0.40, label="Two-stage hurdle")
    upper = float(max(predictions.mean_ever_fraction.max(), predictions.best_baseline_prediction.max(), predictions.hurdle_expected_fraction.max()))
    ax.plot([0, upper], [0, upper], linestyle="--", linewidth=1, label="Ideal")
    ax.set_xlabel("Observed mean compromised fraction")
    ax.set_ylabel("Predicted mean compromised fraction")
    ax.set_title("Cycle 7 pooled held-out predictions")
    ax.legend()
    fig.tight_layout()
    path = output / "cycle7_pooled_prediction.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)

    fig, ax = plt.subplots(figsize=(7.2, 5.6))
    for block, frame in predictions.groupby("block"):
        order = np.argsort(frame.temporal_nb.to_numpy(float))
        ax.plot(frame.temporal_nb.to_numpy(float)[order], frame.hurdle_outbreak_probability.to_numpy(float)[order], linewidth=1.5, label=f"Block {int(block)}")
    ax.set_xlabel("Temporal non-backtracking score")
    ax.set_ylabel("Estimated outbreak probability")
    ax.set_title("Cycle 7 initiation calibrations")
    ax.legend()
    fig.tight_layout()
    path = output / "cycle7_initiation_probability.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)
    return paths


def run_stage2_cycle7(
    repository_root: str | Path,
    *,
    block_seeds: Sequence[int] = (20260823, 120260823, 220260823),
    replications: int = 30,
    bootstrap_draws: int = 5000,
) -> dict[str, object]:
    root = Path(repository_root)
    results_dir = root / "results" / "stage2_cycle7"
    figures_dir = root / "figures" / "stage2_cycle7"
    results_dir.mkdir(parents=True, exist_ok=True)

    all_runs: list[pd.DataFrame] = []
    all_scenarios: list[pd.DataFrame] = []
    all_predictions: list[pd.DataFrame] = []
    results: list[Cycle7BlockResult] = []
    for block, seed in enumerate(block_seeds):
        runs, scenarios, prediction, result = _evaluate_block(block, int(seed), replications=replications)
        all_runs.append(runs)
        all_scenarios.append(scenarios)
        all_predictions.append(prediction)
        results.append(result)

    runs = pd.concat(all_runs, ignore_index=True)
    scenarios = pd.concat(all_scenarios, ignore_index=True)
    predictions = pd.concat(all_predictions, ignore_index=True)
    block_frame = pd.DataFrame([row.as_dict() for row in results])
    runs.to_csv(results_dir / "nh2_hurdle_replications.csv", index=False)
    scenarios.to_csv(results_dir / "nh2_hurdle_scenarios.csv", index=False)
    predictions.to_csv(results_dir / "nh2_hurdle_predictions.csv", index=False)
    block_frame.to_csv(results_dir / "nh2_hurdle_blocks.csv", index=False)

    pooled_hurdle_mae = float(predictions.candidate_absolute_error.mean())
    pooled_baseline_mae = float(predictions.baseline_absolute_error.mean())
    pooled_improvement = float((pooled_baseline_mae - pooled_hurdle_mae) / max(pooled_baseline_mae, 1e-12))
    bootstrap = _hierarchical_bootstrap(predictions, seed=920260823, draws=bootstrap_draws)
    criteria = {
        "all_three_blocks_valid": bool(block_frame.valid.all()),
        "pooled_mae_improvement_at_least_15pct": pooled_improvement >= 0.15,
        "all_blocks_positive_mae_improvement": bool((block_frame.mae_improvement_fraction > 0).all()),
        "at_least_two_blocks_improve_15pct": int((block_frame.mae_improvement_fraction >= 0.15).sum()) >= 2,
        "bootstrap_absolute_mae_lower_bound_positive": float(bootstrap["absolute_mae_reduction"][0]) > 0.0,
        "brier_noninferior_in_two_of_three_blocks": int((block_frame.hurdle_brier <= block_frame.nb_isotonic_brier).sum()) >= 2,
        "auc_not_degraded_more_than_0_01": bool((block_frame.auc_delta >= -0.01).all()),
    }
    supported = bool(all(criteria.values()))
    figures = _write_figures(predictions, block_frame, figures_dir)
    summary = {
        "study": "Stage 2 Cycle 7 preregistered two-stage compromise experiment",
        "protocol_id": "FAS-S2-C7-2026-08-19",
        "evidence_scope": "model-conditioned; notional parameters; no external validation",
        "block_seeds": [int(value) for value in block_seeds],
        "replications_per_scenario": int(replications),
        "dataset_counts": {
            "replications": int(len(runs)),
            "scenarios": int(len(scenarios)),
            "heldout_predictions": int(len(predictions)),
        },
        "block_results": [row.as_dict() for row in results],
        "pooled_hurdle_mae": pooled_hurdle_mae,
        "pooled_best_baseline_mae": pooled_baseline_mae,
        "pooled_mae_improvement_fraction": pooled_improvement,
        "bootstrap_95pct": bootstrap,
        "criteria": criteria,
        "supported_in_model": supported,
        "decision": "supported in the declared model" if supported else "not supported under the preregistered rule",
        "figures": [str(path.relative_to(root)) for path in figures],
        "limitations": "All mechanisms and parameters are synthetic. Support does not establish operational prediction or implementation security.",
    }
    (results_dir / "stage2_cycle7_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
