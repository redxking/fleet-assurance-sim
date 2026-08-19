"""Leakage-resistant phase-separated compromise estimator for Stage 3B.

Outbreak initiation, outbreak severity, and non-outbreak severity are fitted
separately. Exploratory rows fit coefficients, calibration rows fit monotone
calibration maps and interval widths, and held-out rows are accepted only for
prediction.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

import numpy as np

ResearchSplit = Literal["exploratory", "calibration", "heldout"]


@dataclass(frozen=True)
class PhaseSeparatedRecord:
    """One replication with predictor features and generator outcomes."""

    record_id: str
    scenario_id: str
    split: ResearchSplit
    block: int
    n_agents: int
    topology: str
    attack_class: str
    segmentation_policy: str
    features: Mapping[str, float]
    outbreak: int
    final_compromise_fraction: float
    replication_seed: int
    base_replication_seed: int | None = None
    defense_case: str = "nominal"
    detection_probability: float | None = None
    quarantine_delay_steps: int | None = None
    revocation_delay_steps: int | None = None
    partition_probability: float | None = None
    graph_seed: int | None = None
    process_seed: int | None = None
    observation_seed: int | None = None
    attack_trace_digest: str | None = None
    attack_horizon_steps: int | None = None
    outbreak_onset_step: int | None = None
    attack_peak_active_fraction: float | None = None
    attack_event_count: int = 0
    attack_event_type_counts: Mapping[str, int] = field(default_factory=dict)
    attack_event_first_step: Mapping[str, int] = field(default_factory=dict)
    attack_event_last_step: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.record_id or not self.scenario_id:
            raise ValueError("record_id and scenario_id must be nonempty")
        if self.split not in {"exploratory", "calibration", "heldout"}:
            raise ValueError("invalid research split")
        if self.n_agents < 2:
            raise ValueError("n_agents must be at least 2")
        if self.outbreak not in {0, 1}:
            raise ValueError("outbreak must be 0 or 1")
        if not 0.0 <= self.final_compromise_fraction <= 1.0:
            raise ValueError("final_compromise_fraction must be in [0, 1]")
        if not self.defense_case:
            raise ValueError("defense_case must be nonempty")
        for name in ("detection_probability", "partition_probability"):
            value = getattr(self, name)
            if value is not None and not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        for name in ("quarantine_delay_steps", "revocation_delay_steps"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be nonnegative")
        for name in (
            "base_replication_seed",
            "graph_seed",
            "process_seed",
            "observation_seed",
        ):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be nonnegative")
        if self.attack_trace_digest is not None:
            digest = self.attack_trace_digest
            if len(digest) != 64:
                raise ValueError("attack_trace_digest must be a 64-character hexadecimal digest")
            try:
                int(digest, 16)
            except ValueError as exc:
                raise ValueError(
                    "attack_trace_digest must be a 64-character hexadecimal digest"
                ) from exc
        if self.attack_horizon_steps is not None and self.attack_horizon_steps < 1:
            raise ValueError("attack_horizon_steps must be positive")
        if self.outbreak_onset_step is not None:
            if self.outbreak_onset_step < 0:
                raise ValueError("outbreak_onset_step must be nonnegative")
            if (
                self.attack_horizon_steps is not None
                and self.outbreak_onset_step >= self.attack_horizon_steps
            ):
                raise ValueError("outbreak_onset_step must be within the attack horizon")
        if self.attack_peak_active_fraction is not None and not (
            0.0 <= self.attack_peak_active_fraction <= 1.0
        ):
            raise ValueError("attack_peak_active_fraction must be in [0, 1]")
        if self.attack_event_count < 0:
            raise ValueError("attack_event_count must be nonnegative")
        event_counts = {str(name): int(value) for name, value in self.attack_event_type_counts.items()}
        first_steps = {str(name): int(value) for name, value in self.attack_event_first_step.items()}
        last_steps = {str(name): int(value) for name, value in self.attack_event_last_step.items()}
        if any(not name or value < 0 for name, value in event_counts.items()):
            raise ValueError("attack event types must be nonempty and counts nonnegative")
        if sum(event_counts.values()) != self.attack_event_count:
            raise ValueError("attack event counts must sum to attack_event_count")
        if set(first_steps) != set(event_counts) or set(last_steps) != set(event_counts):
            raise ValueError("attack event timing summaries must cover every counted event type")
        if any(
            first_steps[name] < 0 or last_steps[name] < first_steps[name]
            for name in event_counts
        ):
            raise ValueError("attack event timing summaries contain invalid steps")
        clean = {str(name): float(value) for name, value in self.features.items()}
        if not clean or not np.isfinite(list(clean.values())).all():
            raise ValueError("features must be nonempty and finite")
        object.__setattr__(self, "features", MappingProxyType(clean))
        object.__setattr__(self, "attack_event_type_counts", MappingProxyType(event_counts))
        object.__setattr__(self, "attack_event_first_step", MappingProxyType(first_steps))
        object.__setattr__(self, "attack_event_last_step", MappingProxyType(last_steps))


@dataclass(frozen=True)
class CalibratedInitiationModel:
    feature_names: tuple[str, ...]
    feature_mean: np.ndarray
    feature_scale: np.ndarray
    coefficients: np.ndarray
    calibration_x: np.ndarray
    calibration_y: np.ndarray


@dataclass(frozen=True)
class CalibratedSeverityModel:
    feature_names: tuple[str, ...]
    feature_mean: np.ndarray
    feature_scale: np.ndarray
    coefficients: np.ndarray
    calibration_x: np.ndarray
    calibration_y: np.ndarray
    interval_half_width: float


@dataclass(frozen=True)
class PhaseSeparatedModel:
    initiation: CalibratedInitiationModel
    severity: CalibratedSeverityModel
    nonoutbreak_severity: CalibratedSeverityModel
    fit_record_ids: frozenset[str]
    interval_level: float


@dataclass(frozen=True)
class PhaseSeparatedPrediction:
    record_ids: tuple[str, ...]
    outbreak_probability: np.ndarray
    conditional_severity: np.ndarray
    conditional_severity_lower: np.ndarray
    conditional_severity_upper: np.ndarray
    conditional_nonoutbreak_severity: np.ndarray
    conditional_nonoutbreak_severity_lower: np.ndarray
    conditional_nonoutbreak_severity_upper: np.ndarray
    expected_final_fraction: np.ndarray
    expected_final_fraction_lower: np.ndarray
    expected_final_fraction_upper: np.ndarray


def _freeze(values: np.ndarray) -> np.ndarray:
    result = np.asarray(values, dtype=float).copy()
    result.setflags(write=False)
    return result


def _matrix(records: Sequence[PhaseSeparatedRecord], names: Sequence[str]) -> np.ndarray:
    missing = sorted(
        {
            name
            for record in records
            for name in names
            if name not in record.features
        }
    )
    if missing:
        raise ValueError(f"records missing features: {missing}")
    return np.asarray([[record.features[name] for name in names] for record in records], dtype=float)


def _standardize_fit(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = np.mean(matrix, axis=0)
    scale = np.std(matrix, axis=0)
    scale = np.where(scale > 1e-12, scale, 1.0)
    return (matrix - mean) / scale, mean, scale


def _design(matrix: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(matrix)), matrix])


def _sigmoid(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(values, dtype=float), -35.0, 35.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _fit_logistic(design: np.ndarray, target: np.ndarray, ridge: float) -> np.ndarray:
    if ridge < 0.0:
        raise ValueError("ridge must be nonnegative")
    average = float(np.clip(np.mean(target), 1e-5, 1.0 - 1e-5))
    coefficients = np.zeros(design.shape[1])
    coefficients[0] = np.log(average / (1.0 - average))
    penalty = np.eye(design.shape[1]) * ridge
    penalty[0, 0] = 0.0
    for _ in range(100):
        fitted = _sigmoid(design @ coefficients)
        weight = np.maximum(fitted * (1.0 - fitted), 1e-7)
        working = design @ coefficients + (target - fitted) / weight
        lhs = design.T @ (weight[:, None] * design) + penalty + 1e-10 * np.eye(
            design.shape[1]
        )
        rhs = design.T @ (weight * working)
        updated = np.linalg.solve(lhs, rhs)
        if np.max(np.abs(updated - coefficients)) < 1e-9:
            coefficients = updated
            break
        coefficients = updated
    return coefficients


def _pava_fit(score: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    order = np.argsort(score, kind="mergesort")
    x, y = score[order], target[order]
    unique_x, inverse = np.unique(x, return_inverse=True)
    sums = np.bincount(inverse, weights=y)
    weights = np.bincount(inverse).astype(float)
    means = sums / weights
    blocks: list[list[float]] = []
    for value, weight in zip(means, weights):
        blocks.append([float(value), float(weight), 1.0])
        while len(blocks) >= 2 and blocks[-2][0] > blocks[-1][0]:
            right = blocks.pop()
            left = blocks.pop()
            merged_weight = left[1] + right[1]
            merged_value = (left[0] * left[1] + right[0] * right[1]) / merged_weight
            blocks.append([merged_value, merged_weight, left[2] + right[2]])
    calibrated: list[float] = []
    for value, _weight, count in blocks:
        calibrated.extend([float(value)] * int(count))
    return unique_x, np.clip(np.asarray(calibrated, dtype=float), 0.0, 1.0)


def _pava_predict(score: np.ndarray, fit_x: np.ndarray, fit_y: np.ndarray) -> np.ndarray:
    if len(fit_x) == 1:
        return np.full(len(score), fit_y[0])
    return np.asarray(
        np.clip(
            np.interp(score, fit_x, fit_y, left=fit_y[0], right=fit_y[-1]),
            0.0,
            1.0,
        ),
        dtype=float,
    )


def _validate_partition(
    records: Sequence[PhaseSeparatedRecord], expected: ResearchSplit
) -> tuple[PhaseSeparatedRecord, ...]:
    if not records:
        raise ValueError(f"{expected} records cannot be empty")
    if any(record.split != expected for record in records):
        raise ValueError(f"all records must have split={expected}")
    ids = [record.record_id for record in records]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate record_id in {expected} records")
    return tuple(records)


def _require_both_outcome_classes(
    records: Sequence[PhaseSeparatedRecord],
    partition_name: str,
) -> None:
    if {record.outbreak for record in records} != {0, 1}:
        raise ValueError(f"{partition_name} partition requires both outbreak outcome classes")


def _fit_conditional_severity(
    exploratory: Sequence[PhaseSeparatedRecord],
    calibration: Sequence[PhaseSeparatedRecord],
    *,
    feature_names: tuple[str, ...],
    ridge: float,
    interval_level: float,
    condition_name: str,
) -> CalibratedSeverityModel:
    if not exploratory or not calibration:
        raise ValueError(
            f"both exploratory and calibration partitions require {condition_name} rows"
        )
    severity_x, severity_mean, severity_scale = _standardize_fit(
        _matrix(exploratory, feature_names)
    )
    severity_target = np.asarray(
        [row.final_compromise_fraction for row in exploratory], dtype=float
    )
    severity_logit = np.log(
        np.clip(severity_target, 1e-5, 1.0 - 1e-5)
        / np.clip(1.0 - severity_target, 1e-5, 1.0)
    )
    severity_design = _design(severity_x)
    penalty = np.eye(severity_design.shape[1]) * ridge
    penalty[0, 0] = 0.0
    severity_coefficients = np.linalg.solve(
        severity_design.T @ severity_design
        + penalty
        + 1e-10 * np.eye(severity_design.shape[1]),
        severity_design.T @ severity_logit,
    )
    severity_calibration_x = (
        _matrix(calibration, feature_names) - severity_mean
    ) / severity_scale
    raw_severity = _sigmoid(_design(severity_calibration_x) @ severity_coefficients)
    observed_severity = np.asarray(
        [row.final_compromise_fraction for row in calibration], dtype=float
    )
    severity_cal_x, severity_cal_y = _pava_fit(raw_severity, observed_severity)
    calibrated_severity = _pava_predict(raw_severity, severity_cal_x, severity_cal_y)
    interval_half_width = float(
        np.quantile(np.abs(observed_severity - calibrated_severity), interval_level)
    )
    return CalibratedSeverityModel(
        feature_names=feature_names,
        feature_mean=_freeze(severity_mean),
        feature_scale=_freeze(severity_scale),
        coefficients=_freeze(severity_coefficients),
        calibration_x=_freeze(severity_cal_x),
        calibration_y=_freeze(severity_cal_y),
        interval_half_width=interval_half_width,
    )


def fit_phase_separated(
    exploratory: Sequence[PhaseSeparatedRecord],
    calibration: Sequence[PhaseSeparatedRecord],
    *,
    initiation_features: Sequence[str],
    severity_features: Sequence[str],
    nonoutbreak_features: Sequence[str] | None = None,
    ridge: float = 1e-3,
    interval_level: float = 0.90,
) -> PhaseSeparatedModel:
    """Fit coefficients on exploration and calibration maps on calibration only."""
    exploration = _validate_partition(exploratory, "exploratory")
    calibration_rows = _validate_partition(calibration, "calibration")
    overlap = {row.record_id for row in exploration}.intersection(
        row.record_id for row in calibration_rows
    )
    if overlap:
        raise ValueError("exploratory and calibration record IDs must be disjoint")
    if not initiation_features or not severity_features:
        raise ValueError("initiation_features and severity_features cannot be empty")
    if not 0.5 < interval_level < 1.0:
        raise ValueError("interval_level must be in (0.5, 1)")
    _require_both_outcome_classes(exploration, "exploratory")
    _require_both_outcome_classes(calibration_rows, "calibration")

    initiation_names = tuple(str(value) for value in initiation_features)
    severity_names = tuple(str(value) for value in severity_features)
    nonoutbreak_names = (
        severity_names
        if nonoutbreak_features is None
        else tuple(str(value) for value in nonoutbreak_features)
    )
    if not nonoutbreak_names:
        raise ValueError("nonoutbreak_features cannot be empty")
    initiation_x, initiation_mean, initiation_scale = _standardize_fit(
        _matrix(exploration, initiation_names)
    )
    initiation_target = np.asarray([row.outbreak for row in exploration], dtype=float)
    initiation_coefficients = _fit_logistic(
        _design(initiation_x), initiation_target, ridge
    )
    calibration_x = (
        _matrix(calibration_rows, initiation_names) - initiation_mean
    ) / initiation_scale
    raw_calibration_probability = _sigmoid(_design(calibration_x) @ initiation_coefficients)
    initiation_cal_x, initiation_cal_y = _pava_fit(
        raw_calibration_probability,
        np.asarray([row.outbreak for row in calibration_rows], dtype=float),
    )

    exploration_outbreak = tuple(row for row in exploration if row.outbreak == 1)
    calibration_outbreak = tuple(row for row in calibration_rows if row.outbreak == 1)
    exploration_nonoutbreak = tuple(row for row in exploration if row.outbreak == 0)
    calibration_nonoutbreak = tuple(row for row in calibration_rows if row.outbreak == 0)
    severity = _fit_conditional_severity(
        exploration_outbreak,
        calibration_outbreak,
        feature_names=severity_names,
        ridge=ridge,
        interval_level=interval_level,
        condition_name="outbreak",
    )
    nonoutbreak_severity = _fit_conditional_severity(
        exploration_nonoutbreak,
        calibration_nonoutbreak,
        feature_names=nonoutbreak_names,
        ridge=ridge,
        interval_level=interval_level,
        condition_name="non-outbreak",
    )

    return PhaseSeparatedModel(
        initiation=CalibratedInitiationModel(
            feature_names=initiation_names,
            feature_mean=_freeze(initiation_mean),
            feature_scale=_freeze(initiation_scale),
            coefficients=_freeze(initiation_coefficients),
            calibration_x=_freeze(initiation_cal_x),
            calibration_y=_freeze(initiation_cal_y),
        ),
        severity=severity,
        nonoutbreak_severity=nonoutbreak_severity,
        fit_record_ids=frozenset(
            row.record_id for row in (*exploration, *calibration_rows)
        ),
        interval_level=float(interval_level),
    )


def _predict_records(
    model: PhaseSeparatedModel,
    rows: Sequence[PhaseSeparatedRecord],
) -> PhaseSeparatedPrediction:
    identifiers = tuple(row.record_id for row in rows)
    initiation = model.initiation
    initiation_x = (
        _matrix(rows, initiation.feature_names) - initiation.feature_mean
    ) / initiation.feature_scale
    raw_probability = _sigmoid(_design(initiation_x) @ initiation.coefficients)
    probability = _pava_predict(
        raw_probability, initiation.calibration_x, initiation.calibration_y
    )

    def severity_projection(
        fitted: CalibratedSeverityModel,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        severity_x = (
            _matrix(rows, fitted.feature_names) - fitted.feature_mean
        ) / fitted.feature_scale
        raw_severity = _sigmoid(_design(severity_x) @ fitted.coefficients)
        conditional = _pava_predict(
            raw_severity, fitted.calibration_x, fitted.calibration_y
        )
        lower = np.clip(conditional - fitted.interval_half_width, 0.0, 1.0)
        upper = np.clip(conditional + fitted.interval_half_width, 0.0, 1.0)
        return conditional, lower, upper

    conditional, lower, upper = severity_projection(model.severity)
    nonoutbreak, nonoutbreak_lower, nonoutbreak_upper = severity_projection(
        model.nonoutbreak_severity
    )
    expected = np.clip(
        probability * conditional + (1.0 - probability) * nonoutbreak,
        0.0,
        1.0,
    )
    expected_lower = np.clip(
        probability * lower + (1.0 - probability) * nonoutbreak_lower,
        0.0,
        1.0,
    )
    expected_upper = np.clip(
        probability * upper + (1.0 - probability) * nonoutbreak_upper,
        0.0,
        1.0,
    )
    return PhaseSeparatedPrediction(
        record_ids=identifiers,
        outbreak_probability=_freeze(probability),
        conditional_severity=_freeze(conditional),
        conditional_severity_lower=_freeze(lower),
        conditional_severity_upper=_freeze(upper),
        conditional_nonoutbreak_severity=_freeze(nonoutbreak),
        conditional_nonoutbreak_severity_lower=_freeze(nonoutbreak_lower),
        conditional_nonoutbreak_severity_upper=_freeze(nonoutbreak_upper),
        expected_final_fraction=_freeze(expected),
        expected_final_fraction_lower=_freeze(expected_lower),
        expected_final_fraction_upper=_freeze(expected_upper),
    )


def predict_phase_separated_calibration(
    model: PhaseSeparatedModel,
    calibration: Sequence[PhaseSeparatedRecord],
) -> PhaseSeparatedPrediction:
    """Predict the declared calibration partition for model selection only."""
    rows = _validate_partition(calibration, "calibration")
    identifiers = {row.record_id for row in rows}
    if not identifiers.issubset(model.fit_record_ids):
        raise ValueError("calibration records were not part of model fitting")
    return _predict_records(model, rows)


def predict_phase_separated_crossfit(
    model: PhaseSeparatedModel,
    calibration: Sequence[PhaseSeparatedRecord],
) -> PhaseSeparatedPrediction:
    """Predict a calibration fold excluded from this model's calibration map."""
    rows = _validate_partition(calibration, "calibration")
    identifiers = {row.record_id for row in rows}
    if model.fit_record_ids.intersection(identifiers):
        raise ValueError("cross-fit calibration record IDs overlap model fitting IDs")
    return _predict_records(model, rows)


def predict_phase_separated(
    model: PhaseSeparatedModel,
    heldout: Sequence[PhaseSeparatedRecord],
) -> PhaseSeparatedPrediction:
    """Predict held-out records and reject partition or identifier leakage."""
    rows = _validate_partition(heldout, "heldout")
    identifiers = tuple(row.record_id for row in rows)
    overlap = model.fit_record_ids.intersection(identifiers)
    if overlap:
        raise ValueError("held-out record IDs overlap model fitting IDs")
    return _predict_records(model, rows)


__all__ = [
    "CalibratedInitiationModel",
    "CalibratedSeverityModel",
    "PhaseSeparatedModel",
    "PhaseSeparatedPrediction",
    "PhaseSeparatedRecord",
    "ResearchSplit",
    "fit_phase_separated",
    "predict_phase_separated",
    "predict_phase_separated_calibration",
    "predict_phase_separated_crossfit",
]
