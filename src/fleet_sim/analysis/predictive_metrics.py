"""Calibration and error metrics for held-out Stage 3 predictions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import log

import numpy as np

_LOG_LOSS_PROBABILITY_CLIP = 1e-6


@dataclass(frozen=True)
class ReliabilityBin:
    lower: float
    upper: float
    count: int
    mean_prediction: float
    observed_frequency: float


@dataclass(frozen=True)
class BinaryPredictiveMetrics:
    brier_score: float
    log_loss: float
    roc_auc: float
    precision_recall_auc: float
    calibration_intercept: float
    calibration_slope: float
    expected_calibration_error: float
    reliability: tuple[ReliabilityBin, ...]


@dataclass(frozen=True)
class ContinuousPredictiveMetrics:
    mean_absolute_error: float
    root_mean_square_error: float
    quantile_loss: float
    interval_coverage: float | None


def _paired(
    observed: Sequence[float] | np.ndarray,
    predicted: Sequence[float] | np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(observed, dtype=float).reshape(-1)
    p = np.asarray(predicted, dtype=float).reshape(-1)
    if len(y) == 0 or y.shape != p.shape:
        raise ValueError("observed and predicted must be nonempty vectors of equal length")
    if not np.isfinite(y).all() or not np.isfinite(p).all():
        raise ValueError("observed and predicted must be finite")
    return y, p


def reliability_curve(
    observed: Sequence[float] | np.ndarray,
    probability: Sequence[float] | np.ndarray,
    *,
    bins: int = 10,
) -> tuple[ReliabilityBin, ...]:
    """Return equal-width reliability bins, omitting empty bins."""
    y, p = _paired(observed, probability)
    if np.any((y < 0.0) | (y > 1.0)) or np.any((p < 0.0) | (p > 1.0)):
        raise ValueError("binary observations and probabilities must be in [0, 1]")
    if bins < 2:
        raise ValueError("bins must be at least 2")
    index = np.minimum((p * bins).astype(int), bins - 1)
    result: list[ReliabilityBin] = []
    for bin_index in range(bins):
        selected = index == bin_index
        count = int(selected.sum())
        if not count:
            continue
        result.append(
            ReliabilityBin(
                lower=bin_index / bins,
                upper=(bin_index + 1) / bins,
                count=count,
                mean_prediction=float(np.mean(p[selected])),
                observed_frequency=float(np.mean(y[selected])),
            )
        )
    return tuple(result)


def _roc_auc(labels: np.ndarray, scores: np.ndarray) -> float:
    positive = int(np.sum(labels == 1.0))
    negative = int(np.sum(labels == 0.0))
    if positive == 0 or negative == 0:
        return float("nan")
    order = np.argsort(scores, kind="mergesort")
    sorted_scores = scores[order]
    ranks: np.ndarray = np.empty(len(scores), dtype=float)
    start = 0
    while start < len(scores):
        end = start + 1
        while end < len(scores) and sorted_scores[end] == sorted_scores[start]:
            end += 1
        ranks[order[start:end]] = 0.5 * (start + 1 + end)
        start = end
    rank_sum = float(np.sum(ranks[labels == 1.0]))
    return float((rank_sum - positive * (positive + 1) / 2.0) / (positive * negative))


def _precision_recall_auc(labels: np.ndarray, scores: np.ndarray) -> float:
    positives = float(np.sum(labels))
    if positives == 0.0:
        return float("nan")
    order = np.argsort(-scores, kind="mergesort")
    ordered_scores = scores[order]
    ordered_labels = labels[order]
    true_positive_all = np.cumsum(ordered_labels)
    false_positive_all = np.cumsum(1.0 - ordered_labels)
    threshold_ends = np.flatnonzero(
        np.r_[ordered_scores[:-1] != ordered_scores[1:], True]
    )
    true_positive = true_positive_all[threshold_ends]
    false_positive = false_positive_all[threshold_ends]
    recall = true_positive / positives
    precision = true_positive / np.maximum(true_positive + false_positive, 1.0)
    recall = np.concatenate([[0.0], recall])
    precision = np.concatenate([[1.0], precision])
    return float(
        np.sum((recall[1:] - recall[:-1]) * (precision[1:] + precision[:-1]) * 0.5)
    )


def _calibration_intercept_slope(labels: np.ndarray, probability: np.ndarray) -> tuple[float, float]:
    if np.all(labels == labels[0]):
        return float("nan"), float("nan")
    clipped = np.clip(probability, 1e-8, 1.0 - 1e-8)
    score = np.log(clipped / (1.0 - clipped))
    design = np.column_stack([np.ones(len(score)), score])
    coefficients = np.zeros(2)
    coefficients[0] = log((float(np.mean(labels)) + 1e-6) / (1.0 - float(np.mean(labels)) + 1e-6))
    for _ in range(80):
        linear = np.clip(design @ coefficients, -30.0, 30.0)
        fitted = 1.0 / (1.0 + np.exp(-linear))
        weight = np.maximum(fitted * (1.0 - fitted), 1e-8)
        working = linear + (labels - fitted) / weight
        lhs = design.T @ (weight[:, None] * design) + 1e-8 * np.eye(2)
        rhs = design.T @ (weight * working)
        updated = np.linalg.solve(lhs, rhs)
        if np.max(np.abs(updated - coefficients)) < 1e-9:
            coefficients = updated
            break
        coefficients = updated
    return float(coefficients[0]), float(coefficients[1])


def binary_predictive_metrics(
    observed: Sequence[int] | np.ndarray,
    probability: Sequence[float] | np.ndarray,
    *,
    bins: int = 10,
) -> BinaryPredictiveMetrics:
    """Evaluate probability accuracy, discrimination, and calibration."""
    y, p = _paired(observed, probability)
    if np.any((y != 0.0) & (y != 1.0)):
        raise ValueError("binary observed values must be 0 or 1")
    if set(np.unique(y)) != {0.0, 1.0}:
        raise ValueError("binary predictive evaluation requires both outcome classes")
    if np.any((p < 0.0) | (p > 1.0)):
        raise ValueError("probabilities must be in [0, 1]")
    clipped = np.clip(
        p,
        _LOG_LOSS_PROBABILITY_CLIP,
        1.0 - _LOG_LOSS_PROBABILITY_CLIP,
    )
    reliability = reliability_curve(y, p, bins=bins)
    expected_calibration_error = float(
        sum(
            row.count / len(y) * abs(row.mean_prediction - row.observed_frequency)
            for row in reliability
        )
    )
    intercept, slope = _calibration_intercept_slope(y, p)
    return BinaryPredictiveMetrics(
        brier_score=float(np.mean((p - y) ** 2)),
        log_loss=float(-np.mean(y * np.log(clipped) + (1.0 - y) * np.log(1.0 - clipped))),
        roc_auc=_roc_auc(y, p),
        precision_recall_auc=_precision_recall_auc(y, p),
        calibration_intercept=intercept,
        calibration_slope=slope,
        expected_calibration_error=expected_calibration_error,
        reliability=reliability,
    )


def continuous_predictive_metrics(
    observed: Sequence[float] | np.ndarray,
    predicted: Sequence[float] | np.ndarray,
    *,
    quantile: float = 0.5,
    lower: Sequence[float] | np.ndarray | None = None,
    upper: Sequence[float] | np.ndarray | None = None,
) -> ContinuousPredictiveMetrics:
    """Evaluate point and optional prediction-interval performance."""
    y, p = _paired(observed, predicted)
    if not 0.0 < quantile < 1.0:
        raise ValueError("quantile must be in (0, 1)")
    residual = y - p
    loss = np.maximum(quantile * residual, (quantile - 1.0) * residual)
    coverage: float | None = None
    if (lower is None) != (upper is None):
        raise ValueError("lower and upper intervals must be supplied together")
    if lower is not None and upper is not None:
        low, high = _paired(lower, upper)
        if low.shape != y.shape or np.any(low > high):
            raise ValueError("prediction intervals must match observations and lower <= upper")
        coverage = float(np.mean((y >= low) & (y <= high)))
    return ContinuousPredictiveMetrics(
        mean_absolute_error=float(np.mean(np.abs(residual))),
        root_mean_square_error=float(np.sqrt(np.mean(residual**2))),
        quantile_loss=float(np.mean(loss)),
        interval_coverage=coverage,
    )


__all__ = [
    "BinaryPredictiveMetrics",
    "ContinuousPredictiveMetrics",
    "ReliabilityBin",
    "binary_predictive_metrics",
    "continuous_predictive_metrics",
    "reliability_curve",
]
