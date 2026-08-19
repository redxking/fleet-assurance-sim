"""Two-stage compromise propagation estimator.

The estimator separates outbreak initiation from conditional outbreak severity.
It is a study construct, not an established epidemic law. All outputs remain
conditioned on the supplied simulation model and data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear



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
    xs, ys, ws = x[order], y[order], w[order]
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
    for index, (_, yi, wi) in enumerate(zip(unique_x, unique_y, unique_w)):
        blocks.append({"start": index, "end": index, "weight": wi, "value": yi})
        while len(blocks) >= 2 and float(blocks[-2]["value"]) > float(blocks[-1]["value"]):
            right = blocks.pop()
            left = blocks.pop()
            weight = float(left["weight"]) + float(right["weight"])
            value = (
                float(left["value"]) * float(left["weight"])
                + float(right["value"]) * float(right["weight"])
            ) / max(weight, 1e-12)
            blocks.append({
                "start": int(left["start"]),
                "end": int(right["end"]),
                "weight": weight,
                "value": value,
            })
    fit_x: list[float] = []
    fit_y: list[float] = []
    for block in blocks:
        lo, hi = int(block["start"]), int(block["end"])
        fit_x.append(float(np.average(unique_x[lo:hi + 1], weights=unique_w[lo:hi + 1])))
        fit_y.append(float(block["value"]))
    return np.asarray(fit_x), np.asarray(fit_y)


def _pava_predict(x: np.ndarray, fit_x: np.ndarray, fit_y: np.ndarray) -> np.ndarray:
    """Apply a fitted PAVA calibration with bounded endpoint extrapolation."""
    if len(fit_x) == 0:
        return np.zeros(len(x), dtype=float)
    if len(fit_x) == 1:
        return np.full(len(x), float(fit_y[0]), dtype=float)
    return np.clip(
        np.interp(np.asarray(x, dtype=float), fit_x, fit_y, left=fit_y[0], right=fit_y[-1]),
        0.0,
        1.0,
    )


@dataclass(frozen=True)
class CompromiseHurdleModel:
    """Fitted two-stage estimator parameters."""

    initiation_score: str
    severity_score: str
    initiation_x: np.ndarray
    initiation_y: np.ndarray
    severity_coefficients: np.ndarray
    minimum_outbreak_fraction: float = 0.10


@dataclass(frozen=True)
class HurdlePrediction:
    outbreak_probability: np.ndarray
    conditional_outbreak_severity: np.ndarray
    conditional_nonoutbreak_fraction: np.ndarray
    expected_final_fraction: np.ndarray


def add_replication_conditionals(
    scenarios: pd.DataFrame,
    replications: pd.DataFrame,
) -> pd.DataFrame:
    """Attach conditional outbreak and non-outbreak statistics by scenario."""
    required = {
        "scenario_id",
        "n_agents",
        "ever_compromised_fraction",
        "outbreak_10pct",
    }
    missing = required.difference(replications.columns)
    if missing:
        raise ValueError(f"replication data missing columns: {sorted(missing)}")

    rows: list[dict[str, float | int]] = []
    for scenario_id, group in replications.groupby("scenario_id", sort=True):
        outbreak = group[group["outbreak_10pct"] == 1]
        nonoutbreak = group[group["outbreak_10pct"] == 0]
        rows.append(
            {
                "scenario_id": int(scenario_id),
                "conditional_outbreak_fraction": (
                    float(outbreak["ever_compromised_fraction"].mean())
                    if len(outbreak)
                    else float("nan")
                ),
                "conditional_nonoutbreak_fraction": (
                    float(nonoutbreak["ever_compromised_fraction"].mean())
                    if len(nonoutbreak)
                    else float("nan")
                ),
                "outbreak_replication_count": int(len(outbreak)),
                "nonoutbreak_replication_count": int(len(nonoutbreak)),
            }
        )
    return scenarios.merge(pd.DataFrame(rows), on="scenario_id", how="left", validate="one_to_one")


def fit_compromise_hurdle(
    training: pd.DataFrame,
    *,
    initiation_score: str = "temporal_nb",
    severity_score: str = "nb_pre",
    minimum_outbreak_fraction: float = 0.10,
) -> CompromiseHurdleModel:
    """Fit initiation probability and conditional severity on training rows only."""
    required = {
        initiation_score,
        severity_score,
        "outbreak_rate",
        "replications",
        "n_agents",
        "conditional_outbreak_fraction",
        "outbreak_replication_count",
    }
    missing = required.difference(training.columns)
    if missing:
        raise ValueError(f"training data missing columns: {sorted(missing)}")
    if len(training) == 0:
        raise ValueError("training data cannot be empty")

    initiation_x, initiation_y = _pava_fit(
        training[initiation_score].to_numpy(float),
        training["outbreak_rate"].to_numpy(float),
        training["replications"].to_numpy(float),
    )

    severity_rows = training[training["outbreak_replication_count"] > 0].copy()
    if len(severity_rows) < 3:
        raise ValueError("at least three scenarios with outbreaks are required")
    score = np.log1p(np.maximum(0.0, severity_rows[severity_score].to_numpy(float)))
    log_n = np.log(np.maximum(1.0, severity_rows["n_agents"].to_numpy(float)))
    design = np.column_stack([np.ones(len(severity_rows)), score, log_n])
    weights = np.sqrt(severity_rows["outbreak_replication_count"].to_numpy(float))
    target = severity_rows["conditional_outbreak_fraction"].to_numpy(float)
    result = lsq_linear(
        design * weights[:, None],
        target * weights,
        bounds=(np.array([-np.inf, 0.0, -np.inf]), np.array([np.inf, np.inf, np.inf])),
    )
    if not result.success:
        raise RuntimeError(f"conditional-severity fit failed: {result.message}")

    return CompromiseHurdleModel(
        initiation_score=initiation_score,
        severity_score=severity_score,
        initiation_x=initiation_x,
        initiation_y=initiation_y,
        severity_coefficients=np.asarray(result.x, dtype=float),
        minimum_outbreak_fraction=float(minimum_outbreak_fraction),
    )


def predict_compromise_hurdle(
    model: CompromiseHurdleModel,
    frame: pd.DataFrame,
) -> HurdlePrediction:
    """Predict expected final compromise fraction for scenario rows."""
    required = {model.initiation_score, model.severity_score, "n_agents"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"prediction data missing columns: {sorted(missing)}")

    probability = _pava_predict(
        frame[model.initiation_score].to_numpy(float),
        model.initiation_x,
        model.initiation_y,
    )
    score = np.log1p(np.maximum(0.0, frame[model.severity_score].to_numpy(float)))
    log_n = np.log(np.maximum(1.0, frame["n_agents"].to_numpy(float)))
    design = np.column_stack([np.ones(len(frame)), score, log_n])
    severity = np.clip(
        design @ model.severity_coefficients,
        model.minimum_outbreak_fraction,
        1.0,
    )
    nonoutbreak = np.clip(1.0 / np.maximum(1.0, frame["n_agents"].to_numpy(float)), 0.0, model.minimum_outbreak_fraction)
    expected = np.clip(probability * severity + (1.0 - probability) * nonoutbreak, 0.0, 1.0)
    return HurdlePrediction(probability, severity, nonoutbreak, expected)


def grouped_cross_validation_mae(
    frame: pd.DataFrame,
    *,
    initiation_score: str,
    severity_score: str,
    group_columns: Sequence[str] = ("n_agents", "dependency_family", "segmentation"),
) -> float:
    """Return leave-one-structural-group-out MAE using training scenarios."""
    missing = set(group_columns).difference(frame.columns)
    if missing:
        raise ValueError(f"cross-validation columns missing: {sorted(missing)}")
    group_key = frame[list(group_columns)].astype(str).agg("|".join, axis=1)
    prediction: list[float] = []
    observed: list[float] = []
    for group in group_key.unique():
        fit_rows = frame[group_key != group]
        test_rows = frame[group_key == group]
        model = fit_compromise_hurdle(
            fit_rows,
            initiation_score=initiation_score,
            severity_score=severity_score,
        )
        estimate = predict_compromise_hurdle(model, test_rows)
        prediction.extend(estimate.expected_final_fraction.tolist())
        observed.extend(test_rows["mean_ever_fraction"].to_numpy(float).tolist())
    return float(np.mean(np.abs(np.asarray(prediction) - np.asarray(observed))))


def select_hurdle_scores(
    training: pd.DataFrame,
    *,
    initiation_candidates: Iterable[str],
    severity_candidates: Iterable[str],
) -> pd.DataFrame:
    """Rank candidate score pairs using training-only grouped cross-validation."""
    rows: list[dict[str, float | str]] = []
    for initiation in initiation_candidates:
        for severity in severity_candidates:
            rows.append(
                {
                    "initiation_score": initiation,
                    "severity_score": severity,
                    "cross_validated_mae": grouped_cross_validation_mae(
                        training,
                        initiation_score=initiation,
                        severity_score=severity,
                    ),
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["cross_validated_mae", "initiation_score", "severity_score"],
        ignore_index=True,
    )
