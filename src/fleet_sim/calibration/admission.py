"""Calibration of aggregate Stage 3A resource parameters."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear

from fleet_sim.calibration.measurements import MeasurementDataset
from fleet_sim.control_plane.resource_network import ResourceType


@dataclass(frozen=True, slots=True)
class ResourceCalibration:
    resource_id: str
    resource_type: str
    observation_count: int
    background_work_per_agent_s: float
    admission_work_units_per_agent: float
    capacity_units_per_second: float
    service_time_mean_ms: float
    service_time_standard_deviation_ms: float
    max_wait_s: float
    fit_rmse_work_units_per_s: float
    dropped_work_fraction: float
    deferred_work_fraction: float
    measurement_provenance: tuple[str, ...]
    parameter_class: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["measurement_provenance"] = list(self.measurement_provenance)
        return payload


@dataclass(frozen=True, slots=True)
class AdmissionCalibrationBundle:
    dataset_id: str
    evidence_scope: str
    external_validation: bool
    resources: tuple[ResourceCalibration, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "evidence_scope": self.evidence_scope,
            "external_validation": self.external_validation,
            "resource_count": len(self.resources),
            "resources": [resource.to_dict() for resource in self.resources],
        }


def _window_seconds(group: pd.DataFrame) -> np.ndarray:
    if "window_duration_ms" in group.columns:
        return group["window_duration_ms"].to_numpy(float) / 1000.0
    times = group["timestamp"].astype("int64").to_numpy(float) / 1e9
    differences = np.diff(times)
    positive = differences[differences > 0.0]
    if len(positive) == 0:
        raise ValueError(
            f"resource {group.resource_id.iloc[0]} needs window_duration_ms or two distinct timestamps"
        )
    default = float(np.median(positive))
    return np.concatenate([[default], differences])


def _weighted_moments(values: np.ndarray, weights: np.ndarray) -> tuple[float, float]:
    effective = np.maximum(weights, 1.0)
    mean = float(np.average(values, weights=effective))
    variance = float(np.average((values - mean) ** 2, weights=effective))
    return mean, float(np.sqrt(max(0.0, variance)))


def calibrate_admission_resources(
    dataset: MeasurementDataset,
    *,
    require_all_resources: bool = True,
) -> AdmissionCalibrationBundle:
    frame = dataset.frame
    present = {ResourceType(value) for value in frame["resource_type"].unique()}
    missing = set(ResourceType).difference(present)
    if require_all_resources and missing:
        raise ValueError(
            f"calibration data is missing resource types: {sorted(item.value for item in missing)}"
        )

    calibrations: list[ResourceCalibration] = []
    for resource_id, group in frame.groupby("resource_id", sort=True):
        ordered = group.sort_values("timestamp", kind="mergesort")
        duration_s = _window_seconds(ordered)
        if not np.isfinite(duration_s).all() or (duration_s <= 0.0).any():
            raise ValueError(f"resource {resource_id} has invalid observation windows")
        arrival_rate = ordered["arrival_count"].to_numpy(float) / duration_s
        design = np.column_stack(
            [
                ordered["fleet_size"].to_numpy(float),
                ordered["agents_admitted"].to_numpy(float) / duration_s,
            ]
        )
        fit = lsq_linear(design, arrival_rate, bounds=(0.0, np.inf))
        if not fit.success or not np.isfinite(fit.x).all():
            raise RuntimeError(f"resource calibration failed for {resource_id}: {fit.message}")
        fitted = design @ fit.x
        rmse = float(np.sqrt(np.mean((fitted - arrival_rate) ** 2)))
        service_mean, service_std = _weighted_moments(
            ordered["service_time_ms"].to_numpy(float),
            ordered["service_count"].to_numpy(float),
        )
        arrivals = float(ordered["arrival_count"].sum())
        parameter_class = "notional" if "synthetic" in set(ordered["source_type"]) else "inferred"
        calibrations.append(
            ResourceCalibration(
                resource_id=str(resource_id),
                resource_type=str(ordered["resource_type"].iloc[0]),
                observation_count=len(ordered),
                background_work_per_agent_s=float(fit.x[0]),
                admission_work_units_per_agent=float(fit.x[1]),
                capacity_units_per_second=float(
                    np.median(ordered["capacity_units_per_second"].to_numpy(float))
                ),
                service_time_mean_ms=service_mean,
                service_time_standard_deviation_ms=service_std,
                max_wait_s=float(np.median(ordered["deadline_ms"].to_numpy(float)) / 1000.0),
                fit_rmse_work_units_per_s=rmse,
                dropped_work_fraction=float(ordered["dropped_work"].sum() / max(arrivals, 1.0)),
                deferred_work_fraction=float(ordered["deferred_work"].sum() / max(arrivals, 1.0)),
                measurement_provenance=tuple(
                    sorted(set(ordered["measurement_provenance"].astype(str)))
                ),
                parameter_class=parameter_class,
            )
        )
    return AdmissionCalibrationBundle(
        dataset_id=dataset.dataset_id,
        evidence_scope=dataset.evidence_scope,
        external_validation=False,
        resources=tuple(calibrations),
    )


def write_calibration_bundle(
    bundle: AdmissionCalibrationBundle,
    output_path: str | Path,
) -> Path:
    destination = Path(output_path)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing calibration: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = bundle.to_dict()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    payload["calibration_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return destination
