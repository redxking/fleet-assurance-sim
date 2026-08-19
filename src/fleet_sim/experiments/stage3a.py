"""Lean, deterministic Stage 3A experiment runner."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from fleet_sim.analysis.admission_predictors import project_admission_predictors
from fleet_sim.control_plane.resource_network import (
    AdmissionPattern,
    AssuranceResourceSpec,
    OperationalFailureCriteria,
    ResourceType,
    default_assurance_resources,
    make_admission_trajectory,
    simulate_resource_network,
)

ResourceFactory = Callable[["Stage3AScenario"], tuple[AssuranceResourceSpec, ...]]


@dataclass(frozen=True, slots=True)
class Stage3AScenario:
    scenario_id: str
    pattern: AdmissionPattern
    initial_n: int
    final_n: int
    admission_duration_s: float
    recovery_window_s: float = 120.0
    dt_s: float = 1.0
    disturbance_fraction: float = 0.25
    capacity_multiplier: float = 1.0
    partition: Literal["training", "calibration", "held_out", "robustness"] = "training"
    block_id: int = 0
    architecture: str = "centralized"
    workload: str = "nominal"
    shift_label: str = "nominal"
    randomization_pair_id: str | None = None
    capacity_scale_exponent: float = 0.0
    capacity_reference_n: int = 1_000

    def __post_init__(self) -> None:
        if not self.scenario_id.strip():
            raise ValueError("scenario_id cannot be empty")
        if not isinstance(self.pattern, AdmissionPattern):
            raise TypeError("pattern must be an AdmissionPattern")
        if self.initial_n < 0 or self.final_n < self.initial_n:
            raise ValueError("invalid initial or final fleet size")
        timing = (self.admission_duration_s, self.dt_s, self.capacity_multiplier)
        if not all(np.isfinite(value) and value > 0.0 for value in timing):
            raise ValueError("duration, time step, and capacity multiplier must be positive")
        if not np.isfinite(self.recovery_window_s) or self.recovery_window_s < 0.0:
            raise ValueError("recovery_window_s must be finite and nonnegative")
        if not np.isfinite(self.disturbance_fraction) or self.disturbance_fraction < 0.0:
            raise ValueError("disturbance_fraction must be finite and nonnegative")
        if self.partition not in {"training", "calibration", "held_out", "robustness"}:
            raise ValueError("unsupported Stage 3A partition")
        if self.block_id < 0:
            raise ValueError("block_id must be nonnegative")
        if not np.isfinite(self.capacity_scale_exponent):
            raise ValueError("capacity_scale_exponent must be finite")
        if self.capacity_reference_n < 1:
            raise ValueError("capacity_reference_n must be positive")
        for value, name in (
            (self.architecture, "architecture"),
            (self.workload, "workload"),
            (self.shift_label, "shift_label"),
        ):
            if not value.strip():
                raise ValueError(f"{name} cannot be empty")
        if self.randomization_pair_id is not None and not self.randomization_pair_id.strip():
            raise ValueError("randomization_pair_id must be nonempty when provided")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["pattern"] = self.pattern.value
        return payload


@dataclass(frozen=True, slots=True)
class Stage3AArtifacts:
    output_dir: Path
    raw_replications_path: Path
    scenario_results_path: Path
    summary_path: Path
    execution_manifest_path: Path
    resource_trace_path: Path | None
    admission_trace_path: Path | None


def default_stage3a_scenarios(
    *,
    fleet_sizes: Sequence[int] = (100, 1_000, 10_000),
    admission_duration_s: float = 180.0,
    recovery_window_s: float = 120.0,
    dt_s: float = 1.0,
) -> tuple[Stage3AScenario, ...]:
    scenarios: list[Stage3AScenario] = []
    for final_n in fleet_sizes:
        initial_n = max(0, min(final_n, round(0.10 * final_n)))
        for pattern in AdmissionPattern:
            scenarios.append(
                Stage3AScenario(
                    scenario_id=f"stage3a-{pattern.value}-n{final_n}",
                    pattern=pattern,
                    initial_n=initial_n,
                    final_n=int(final_n),
                    admission_duration_s=admission_duration_s,
                    recovery_window_s=recovery_window_s,
                    dt_s=dt_s,
                )
            )
    return tuple(scenarios)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _experiment_id(
    scenarios: Sequence[Stage3AScenario],
    root_seed: int,
    replications: int,
) -> str:
    payload = {
        "scenarios": [scenario.to_dict() for scenario in scenarios],
        "root_seed": int(root_seed),
        "replications": int(replications),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return f"stage3a-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def _replication_seed(root_seed: int, pair_id: str, replication: int) -> int:
    payload = f"{int(root_seed)}:{pair_id}:{int(replication)}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big", signed=False)


def _default_resource_factory(scenario: Stage3AScenario) -> tuple[AssuranceResourceSpec, ...]:
    return default_assurance_resources(
        scenario.final_n,
        capacity_multiplier=scenario.capacity_multiplier,
    )


def _bounded_trace(frame: pd.DataFrame, maximum_rows: int) -> tuple[pd.DataFrame, str]:
    if maximum_rows < 1:
        raise ValueError("maximum trace rows must be positive")
    if len(frame) <= maximum_rows:
        output = frame.copy()
        output["representation"] = "exact"
        return output, "exact"
    mandatory: set[int] = set()
    group_columns = [
        name for name in ("scenario_id", "replication", "resource_id") if name in frame
    ]
    omega_columns = [
        name
        for name in (
            "omega_observed",
            "projected_omega",
            "maximum_observed_omega",
            "projected_maximum_omega",
        )
        if name in frame
    ]
    if group_columns:
        for _, group in frame.groupby(group_columns, sort=False):
            mandatory.add(int(group.index[0]))
            mandatory.add(int(group.index[-1]))
            for column in omega_columns:
                mandatory.add(int(group[column].astype(float).idxmax()))
                crossings = group.index[group[column].astype(float) >= 1.0]
                if len(crossings):
                    mandatory.add(int(crossings[0]))
    budget = max(0, maximum_rows - len(mandatory))
    remaining = np.asarray(sorted(set(frame.index).difference(mandatory)), dtype=np.int64)
    if budget and len(remaining):
        positions = np.linspace(0, len(remaining) - 1, num=min(budget, len(remaining)), dtype=int)
        mandatory.update(int(value) for value in remaining[positions])
    selected = frame.loc[sorted(mandatory)[:maximum_rows]].copy()
    selected["representation"] = "sampled"
    return selected.reset_index(drop=True), "sampled"


def run_stage3a(
    scenarios: Sequence[Stage3AScenario],
    output_dir: str | Path,
    *,
    root_seed: int,
    replications: int = 30,
    resource_factory: ResourceFactory | None = None,
    failure_criteria: OperationalFailureCriteria | None = None,
    trace_replications_per_scenario: int = 1,
    maximum_trace_rows: int = 100_000,
) -> Stage3AArtifacts:
    """Run Stage 3A and write immutable Parquet and JSON artifacts."""
    if not scenarios:
        raise ValueError("at least one Stage 3A scenario is required")
    if replications < 1:
        raise ValueError("replications must be positive")
    if trace_replications_per_scenario < 0:
        raise ValueError("trace_replications_per_scenario cannot be negative")
    identifiers = [scenario.scenario_id for scenario in scenarios]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Stage 3A scenario identifiers must be unique")
    experiment_id = _experiment_id(scenarios, root_seed, replications)
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing Stage 3A output: {destination}")
    if (
        importlib.util.find_spec("pyarrow") is None
        and importlib.util.find_spec("fastparquet") is None
    ):
        raise RuntimeError("Stage 3A Parquet output requires pyarrow or fastparquet")
    raw_dir = destination / "raw"
    derived_dir = destination / "derived"
    trace_dir = destination / "traces"
    raw_dir.mkdir(parents=True)
    derived_dir.mkdir(parents=True)
    if trace_replications_per_scenario:
        trace_dir.mkdir(parents=True)

    factory = resource_factory or _default_resource_factory
    raw_rows: list[dict[str, object]] = []
    scenario_rows: list[dict[str, object]] = []
    resource_trace_frames: list[pd.DataFrame] = []
    admission_trace_frames: list[pd.DataFrame] = []

    for scenario in scenarios:
        trajectory = make_admission_trajectory(
            scenario.pattern,
            initial_n=scenario.initial_n,
            final_n=scenario.final_n,
            admission_duration_s=scenario.admission_duration_s,
            recovery_window_s=scenario.recovery_window_s,
            dt_s=scenario.dt_s,
            disturbance_fraction=scenario.disturbance_fraction,
        )
        resources = factory(scenario)
        projection = project_admission_predictors(trajectory, resources)
        predictor_values = projection.predictors.to_dict()
        scenario_replications: list[dict[str, object]] = []
        for replication in range(replications):
            pair_id = scenario.randomization_pair_id or scenario.scenario_id
            seed = _replication_seed(root_seed, pair_id, replication)
            result = simulate_resource_network(
                trajectory,
                resources,
                seed=seed,
                failure_criteria=failure_criteria,
            )
            row = {
                "experiment_id": experiment_id,
                "scenario_id": scenario.scenario_id,
                "replication": int(replication),
                "replication_seed": seed,
                **scenario.to_dict(),
                **predictor_values,
                **result.summary,
            }
            raw_rows.append(row)
            scenario_replications.append(row)
            if replication < trace_replications_per_scenario:
                resource_trace = result.resource_trace.merge(
                    projection.resource_trace[
                        [
                            "time_s",
                            "resource_id",
                            "projected_arrival_work",
                            "projected_queue_depth",
                            "projected_wait_s",
                            "projected_omega",
                        ]
                    ],
                    on=["time_s", "resource_id"],
                    how="left",
                    validate="one_to_one",
                )
                resource_trace.insert(0, "replication", int(replication))
                resource_trace.insert(0, "scenario_id", scenario.scenario_id)
                resource_trace["partition"] = scenario.partition
                resource_trace["block_id"] = scenario.block_id
                resource_trace["architecture"] = scenario.architecture
                resource_trace["workload"] = scenario.workload
                resource_trace["shift_label"] = scenario.shift_label
                resource_trace_frames.append(resource_trace)

                admission_trace = result.admission_trace.merge(
                    projection.admission_trace[
                        [
                            "time_s",
                            "planned_admissions",
                            "projected_fleet_size",
                            "projected_maximum_omega",
                        ]
                    ],
                    on="time_s",
                    how="left",
                    validate="one_to_one",
                )
                admission_trace.insert(0, "replication", int(replication))
                admission_trace.insert(0, "scenario_id", scenario.scenario_id)
                admission_trace["partition"] = scenario.partition
                admission_trace["block_id"] = scenario.block_id
                admission_trace["architecture"] = scenario.architecture
                admission_trace["workload"] = scenario.workload
                admission_trace["shift_label"] = scenario.shift_label
                admission_trace_frames.append(admission_trace)

        frame = pd.DataFrame(scenario_replications)
        scenario_rows.append(
            {
                "experiment_id": experiment_id,
                "scenario_id": scenario.scenario_id,
                **scenario.to_dict(),
                **predictor_values,
                "replications": int(replications),
                "operational_failure_rate": float(frame["operational_failure"].mean()),
                "mean_deadline_miss_fraction": float(frame["deadline_miss_fraction"].mean()),
                "mean_shed_fraction": float(frame["shed_fraction"].mean()),
                "mean_useful_task_throughput_ratio": float(
                    frame["useful_task_throughput_ratio"].mean()
                ),
                "mean_incomplete_exposure_per_agent_s": float(
                    frame["incomplete_exposure_per_agent_s"].mean()
                ),
                "evidence_scope": str(frame["evidence_scope"].iloc[0]),
            }
        )

    raw_frame = pd.DataFrame(raw_rows)
    scenario_frame = pd.DataFrame(scenario_rows)
    raw_path = raw_dir / "stage3a_replications.parquet"
    scenario_path = derived_dir / "stage3a_scenarios.parquet"
    try:
        raw_frame.to_parquet(raw_path, index=False)
        scenario_frame.to_parquet(scenario_path, index=False)
    except ImportError as exc:
        raise RuntimeError(
            "Stage 3A Parquet output requires the optional pyarrow dependency"
        ) from exc

    resource_trace_path: Path | None = None
    admission_trace_path: Path | None = None
    trace_representation = "not_captured"
    if resource_trace_frames:
        resource_trace, resource_representation = _bounded_trace(
            pd.concat(resource_trace_frames, ignore_index=True), maximum_trace_rows
        )
        admission_trace, admission_representation = _bounded_trace(
            pd.concat(admission_trace_frames, ignore_index=True), maximum_trace_rows
        )
        trace_representation = (
            "sampled"
            if "sampled" in {resource_representation, admission_representation}
            else "exact"
        )
        resource_trace_path = trace_dir / "stage3a_resource_timeseries.parquet"
        admission_trace_path = trace_dir / "stage3a_admission_timeseries.parquet"
        resource_trace.to_parquet(resource_trace_path, index=False)
        admission_trace.to_parquet(admission_trace_path, index=False)

    summary = {
        "experiment_id": experiment_id,
        "study": "Stage 3A fleet-admission stability interface",
        "root_seed": int(root_seed),
        "scenario_count": len(scenarios),
        "replications_per_scenario": int(replications),
        "replication_count": len(raw_frame),
        "resource_types": sorted(resource.value for resource in ResourceType),
        "patterns": sorted({scenario.pattern.value for scenario in scenarios}),
        "operational_failure_definition_uses_omega": False,
        "evidence_scope": (
            "interface_verification_only"
            if "interface_verification_only" in set(raw_frame["evidence_scope"])
            else "calibrated_model_evidence"
        ),
        "external_validation": False,
        "trace_replications_per_scenario": int(trace_replications_per_scenario),
        "trace_representation": trace_representation,
        "limitations": [
            "Synthetic or calibrated simulation results are not observed operational evidence.",
            "Projected Omega_A is calculated before stochastic outcomes.",
            "Operational failure is defined without using Omega_A.",
        ],
    }
    summary_path = destination / "stage3a_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    artifact_paths = [raw_path, scenario_path, summary_path]
    if resource_trace_path is not None:
        artifact_paths.append(resource_trace_path)
    if admission_trace_path is not None:
        artifact_paths.append(admission_trace_path)
    manifest = {
        "experiment_id": experiment_id,
        "root_seed": int(root_seed),
        "artifacts": [
            {"path": str(path.relative_to(destination)), "sha256": _sha256(path)}
            for path in artifact_paths
        ],
    }
    manifest_path = destination / "execution_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return Stage3AArtifacts(
        output_dir=destination,
        raw_replications_path=raw_path,
        scenario_results_path=scenario_path,
        summary_path=summary_path,
        execution_manifest_path=manifest_path,
        resource_trace_path=resource_trace_path,
        admission_trace_path=admission_trace_path,
    )
