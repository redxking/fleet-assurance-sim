"""Protocol-gated orchestration and adjudication for Stage 3 research."""

from __future__ import annotations

import json
import math
import resource as system_resource
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time
from typing import Any, Literal

import numpy as np
import pandas as pd
import yaml

from fleet_sim.analysis.phase_separated import PhaseSeparatedRecord
from fleet_sim.analysis.predictive_metrics import binary_predictive_metrics
from fleet_sim.control_plane.resource_network import (
    AdmissionPattern,
    AssuranceResourceSpec,
    ResourceType,
    ServiceTimeDistribution,
    default_assurance_resources,
)
from fleet_sim.experiments.stage3_protocol import (
    artifact_inventory,
    checks_as_dicts,
    environment_snapshot,
    load_preexecution_manifest,
    require_frozen_environment,
    require_frozen_inputs,
    reserve_execution_directory,
    sha256_file,
    write_new_json,
)
from fleet_sim.experiments.stage3a import Stage3AScenario, run_stage3a
from fleet_sim.experiments.stage3b import (
    Stage3BExperimentResult,
    Stage3BScenarioSpec,
    build_stage3b_records,
    fit_and_evaluate_stage3b,
    materialize_stage3b_console_trace,
)
from fleet_sim.security.attack_trace import AttackTraceConfig
from fleet_sim.security.dynamic_message_passing import DMPConfig

RunMode = Literal["pilot", "confirmatory"]

_STAGE3A_SIMPLE_PREDICTORS = (
    "final_fleet_size",
    "peak_dndt",
    "mean_dndt",
    "peak_resource_utilization",
    "maximum_projected_queue_depth",
    "total_admitted_agents",
    "cumulative_backlog_area",
    "maximum_projected_deadline_miss_fraction",
)


@dataclass(frozen=True)
class Stage3ExecutionArtifacts:
    execution_dir: Path
    evidence_path: Path
    execution_manifest_path: Path
    stage3a_predictions_path: Path
    stage3b_records_path: Path
    stage3b_predictions_path: Path


@dataclass(frozen=True)
class _RuntimeBudget:
    wall_clock_seconds: float
    peak_rss_mb: float
    maximum_output_mb: float


def _runtime_budget(payload: Mapping[str, Any]) -> _RuntimeBudget:
    return _RuntimeBudget(
        wall_clock_seconds=float(payload["wall_clock_seconds"]),
        peak_rss_mb=float(payload["peak_rss_mb"]),
        maximum_output_mb=float(payload["maximum_output_mb"]),
    )


def _peak_rss_mb() -> float:
    value = float(
        system_resource.getrusage(system_resource.RUSAGE_SELF).ru_maxrss
    )
    return value / (1024.0 * 1024.0) if sys.platform == "darwin" else value / 1024.0


def _directory_size_mb(path: Path) -> float:
    total = sum(candidate.stat().st_size for candidate in path.rglob("*") if candidate.is_file())
    return total / (1024.0 * 1024.0)


def _enforce_runtime_budget(
    execution_dir: Path,
    *,
    started_wall: float,
    budget: _RuntimeBudget,
    checkpoint: str,
    inspect_output: bool = False,
) -> None:
    wall_seconds = perf_counter() - started_wall
    peak_rss_mb = _peak_rss_mb()
    output_mb = _directory_size_mb(execution_dir) if inspect_output else 0.0
    failures: list[str] = []
    if wall_seconds > budget.wall_clock_seconds:
        failures.append(
            f"wall time {wall_seconds:.3f}s exceeds {budget.wall_clock_seconds:.3f}s"
        )
    if peak_rss_mb > budget.peak_rss_mb:
        failures.append(
            f"peak RSS {peak_rss_mb:.3f}MB exceeds {budget.peak_rss_mb:.3f}MB"
        )
    if inspect_output and output_mb > budget.maximum_output_mb:
        failures.append(f"output {output_mb:.3f}MB exceeds {budget.maximum_output_mb:.3f}MB")
    if failures:
        detail = "; ".join(failures)
        raise RuntimeError(f"Stage 3 runtime budget exceeded at {checkpoint}: {detail}")


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"configuration must be a mapping: {path}")
    return payload


def _load_boundary_audit(root: Path) -> dict[str, Any]:
    path = root / "docs/stage3_generator_predictor_independence_audit.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("generator-predictor audit must be a JSON object")
    reviewed = payload.get("reviewed_files")
    if not isinstance(reviewed, list) or not all(isinstance(value, str) for value in reviewed):
        raise TypeError("generator-predictor audit reviewed_files must be a path list")
    required = {
        "src/fleet_sim/security/attack_trace.py",
        "src/fleet_sim/security/dynamic_message_passing.py",
        "src/fleet_sim/analysis/phase_separated.py",
        "src/fleet_sim/experiments/stage3b.py",
    }
    if set(reviewed) != required or not all((root / value).is_file() for value in reviewed):
        raise ValueError("generator-predictor audit source scope is incomplete")
    reviewed_hashes = payload.get("reviewed_file_sha256")
    if not isinstance(reviewed_hashes, dict) or set(reviewed_hashes) != required:
        raise ValueError("generator-predictor audit source hashes are incomplete")
    mismatches = [
        value
        for value in reviewed
        if reviewed_hashes.get(value) != sha256((root / value).read_bytes()).hexdigest()
    ]
    if mismatches:
        raise ValueError(
            "generator-predictor audit source hashes do not match: "
            + ", ".join(sorted(mismatches))
        )
    return payload


def _domain_seed(seed: int, domain: str) -> int:
    if not domain:
        raise ValueError("seed domain must be nonempty")
    digest = sha256(f"{domain}:{int(seed)}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


def _expanded_frozen_files(root: Path, protocol: Mapping[str, Any]) -> set[str]:
    explicit = protocol.get("frozen_files")
    patterns = protocol.get("frozen_globs", [])
    if not isinstance(explicit, list) or not all(isinstance(value, str) for value in explicit):
        raise TypeError("protocol frozen_files must be a list of paths")
    if not isinstance(patterns, list) or not all(isinstance(value, str) for value in patterns):
        raise TypeError("protocol frozen_globs must be a list of patterns")
    files = set(explicit)
    for pattern in patterns:
        matches = {
            path.relative_to(root).as_posix()
            for path in root.glob(pattern)
            if path.is_file()
        }
        if not matches:
            raise FileNotFoundError(f"frozen glob matched no files: {pattern}")
        files.update(matches)
    return files


def _resolved_command(root: Path, command: Sequence[str]) -> tuple[str, ...]:
    if len(command) < 2:
        raise ValueError("execution command must include interpreter and script")
    resolved = list(command)
    for index in (0, 1):
        path = Path(resolved[index])
        if not path.is_absolute():
            path = root / path
        resolved[index] = str(path.resolve())
    return tuple(resolved)


def _finite_float(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"nonfinite value cannot enter evidence: {value!r}")
    return number


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, np.ndarray):
        return [_json_value(item) for item in value.tolist()]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return _finite_float(value)
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, float):
        return _finite_float(value)
    return value


def _reported_value(value: Any) -> Any:
    """Convert metrics to JSON values while representing non-evaluability as null."""

    if isinstance(value, Mapping):
        return {str(key): _reported_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_reported_value(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _reported_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, np.ndarray):
        return [_reported_value(item) for item in value.tolist()]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _criterion(
    passed: bool | None,
    *,
    observed: Any,
    rule: str,
) -> dict[str, Any]:
    status = "not_evaluable" if passed is None else "passed" if passed else "failed"
    return {
        "status": status,
        "observed": _reported_value(observed),
        "rule": rule,
    }


def _all_criteria_pass(criteria: Mapping[str, Mapping[str, Any]]) -> bool:
    return all(value.get("status") == "passed" for value in criteria.values())


def _seed_table(
    root: Path,
    protocol: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    path = root / "manifests" / "stage3_seed_manifest.csv"
    frame = pd.read_csv(path)
    required = {
        "protocol_id",
        "block",
        "partition",
        "graph_seed",
        "process_seed",
        "observation_seed",
        "replication_seed",
        "use",
    }
    if set(frame.columns) != required:
        raise ValueError("Stage 3 seed manifest columns do not match the frozen contract")
    if frame.duplicated(["block", "partition"]).any():
        raise ValueError("Stage 3 seed manifest contains duplicate block and partition rows")
    seed_columns = ["graph_seed", "process_seed", "observation_seed", "replication_seed"]
    values = frame[seed_columns].to_numpy(np.int64)
    if (values < 0).any() or len(set(values.reshape(-1).tolist())) != values.size:
        raise ValueError("Stage 3 seeds must be nonnegative and globally distinct")
    active_protocol = protocol or _load_yaml(root / "configs/stage3/protocol.yaml")
    protocol_id = str(active_protocol["protocol_id"])
    block_count = int(active_protocol["partitions"]["independent_blocks"])
    expected_uses = {
        "training": "fit_only",
        "calibration": "select_and_calibrate_only",
        "held_out": "adjudication_only",
    }
    expected_rows = {
        (block, partition)
        for block in range(block_count)
        for partition in expected_uses
    }
    actual_rows = {
        (int(row.block), str(row.partition))
        for row in frame.itertuples(index=False)
    }
    if actual_rows != expected_rows:
        raise ValueError("Stage 3 seed manifest block and partition rows are incomplete")
    if set(frame.protocol_id.astype(str)) != {protocol_id}:
        raise ValueError("Stage 3 seed manifest protocol_id does not match the protocol")
    invalid_uses = frame[
        frame.apply(
            lambda row: str(row["use"]) != expected_uses.get(str(row["partition"])),
            axis=1,
        )
    ]
    if not invalid_uses.empty:
        raise ValueError("Stage 3 seed manifest use labels do not match the protocol")
    return frame.sort_values(["block", "partition"], kind="mergesort").reset_index(drop=True)


def _seed_row(seeds: pd.DataFrame, block: int, partition: str) -> pd.Series:
    selected = seeds[(seeds.block == block) & (seeds.partition == partition)]
    if len(selected) != 1:
        raise ValueError(f"missing unique seed row for block={block}, partition={partition}")
    return selected.iloc[0]


def _partition_sizes(protocol: Mapping[str, Any], partition: str) -> tuple[int, ...]:
    values = protocol["partitions"][partition]["fleet_sizes"]
    return tuple(int(value) for value in values)


def build_stage3a_scenarios(
    protocol: Mapping[str, Any],
    admission_config: Mapping[str, Any],
    *,
    block: int,
    partition: Literal["training", "calibration", "held_out"],
) -> tuple[Stage3AScenario, ...]:
    """Build the fixed Stage 3A matrix with explicit shift labels."""

    sizes = _partition_sizes(protocol, partition)
    patterns = tuple(AdmissionPattern(value) for value in admission_config["admission_profiles"])
    multipliers = tuple(float(value) for value in admission_config["resource_capacity_multipliers"])
    horizon = float(admission_config["horizon_seconds"])
    recovery = float(admission_config["recovery_window_seconds"])
    dt_s = float(admission_config["timestep_seconds"])
    admission_duration = horizon - recovery
    if admission_duration <= 0.0:
        raise ValueError("Stage 3A horizon must exceed its recovery window")

    architecture_options = tuple(str(value) for value in admission_config["architectures"][partition])
    capacity_scale_exponents = {
        str(key): float(value)
        for key, value in admission_config["capacity_scale_exponents"].items()
    }
    capacity_reference_n = int(admission_config["capacity_reference_fleet_size"])
    if not architecture_options:
        raise ValueError(f"Stage 3A has no architecture for {partition}")
    scenarios: list[Stage3AScenario] = []
    for n_agents in sizes:
        for index, pattern in enumerate(patterns):
            design_points: Iterable[tuple[str, float, str]]
            if partition == "held_out":
                design_points = (
                    (architecture, capacity, workload)
                    for architecture in architecture_options
                    for capacity in multipliers
                    for workload in ("poisson", "gamma")
                )
            elif partition == "calibration":
                design_points = (
                    (architecture_options[index % len(architecture_options)], capacity, "poisson")
                    for capacity in multipliers
                )
            else:
                design_points = iter(
                    (
                        (
                            architecture_options[index % len(architecture_options)],
                            multipliers[(index + block) % len(multipliers)],
                            "deterministic" if index % 2 == 0 else "poisson",
                        ),
                    )
                )
            for architecture, capacity, workload in design_points:
                shift_components = []
                if architecture != "centralized_balanced":
                    shift_components.append("architecture")
                if capacity != 1.0:
                    shift_components.append("capacity")
                if workload == "gamma":
                    shift_components.append("workload")
                shift = "+".join(shift_components) if shift_components else "reference"
                scenario_id = (
                    f"s3a-b{block}-{partition}-n{n_agents}-{pattern.value}-"
                    f"{architecture}-c{capacity:.2f}-{workload}"
                )
                scenarios.append(
                    Stage3AScenario(
                        scenario_id=scenario_id,
                        pattern=pattern,
                        initial_n=max(0, round(0.10 * n_agents)),
                        final_n=n_agents,
                        admission_duration_s=admission_duration,
                        recovery_window_s=recovery,
                        dt_s=dt_s,
                        disturbance_fraction=0.25,
                        capacity_multiplier=capacity,
                        partition=partition,
                        block_id=block,
                        architecture=architecture,
                        workload=workload,
                        shift_label=shift,
                        randomization_pair_id=(
                            f"s3a-pair-b{block}-{partition}-n{n_agents}-{pattern.value}"
                        ),
                        capacity_scale_exponent=capacity_scale_exponents[architecture],
                        capacity_reference_n=capacity_reference_n,
                    )
                )
    return tuple(scenarios)


def _stage3a_resource_factory(scenario: Stage3AScenario) -> tuple[AssuranceResourceSpec, ...]:
    resources = default_assurance_resources(
        scenario.final_n,
        capacity_multiplier=scenario.capacity_multiplier,
    )
    constrained = {
        ResourceType.IDENTITY_ISSUANCE,
        ResourceType.CERTIFICATE_ISSUANCE_RENEWAL,
        ResourceType.AUTHORIZATION_POLICY_EVALUATION,
        ResourceType.SUPERVISORY_REVIEW,
        ResourceType.REVOCATION_READINESS,
    }
    output: list[AssuranceResourceSpec] = []
    scale_factor = (
        max(scenario.final_n, scenario.capacity_reference_n)
        / scenario.capacity_reference_n
    ) ** scenario.capacity_scale_exponent
    for resource in resources:
        architecture_factor = 1.0
        if scenario.architecture == "centralized_control_constrained" and resource.resource_type in constrained:
            architecture_factor = 0.72
        elif scenario.architecture == "sharded_balanced":
            architecture_factor = 1.10
        elif scenario.architecture == "pipelined_proportional":
            architecture_factor = (
                1.18
                if resource.resource_type
                in {
                    ResourceType.IDENTITY_ISSUANCE,
                    ResourceType.CERTIFICATE_ISSUANCE_RENEWAL,
                    ResourceType.TELEMETRY_SOURCE_REGISTRATION,
                    ResourceType.EVIDENCE_INGEST_INITIALIZATION,
                }
                else 0.96
            )
        elif scenario.architecture == "sharded_sublinear_capacity":
            architecture_factor = 0.96
        arrival_process: Literal["scheduled", "poisson"] = (
            "scheduled" if scenario.workload == "deterministic" else "poisson"
        )
        service_distribution = {
            "deterministic": ServiceTimeDistribution.DETERMINISTIC,
            "poisson": ServiceTimeDistribution.EXPONENTIAL,
            "gamma": ServiceTimeDistribution.GAMMA,
        }[scenario.workload]
        capacity = (
            resource.capacity_units_per_second * architecture_factor * scale_factor
        )
        background_factor = 1.18 if scenario.workload == "gamma" else 1.0
        output.append(
            replace(
                resource,
                arrival_process=arrival_process,
                service_time_distribution=service_distribution,
                capacity_units_per_second=capacity,
                service_time_mean_ms=1000.0 / capacity,
                background_work_per_agent_s=(
                    resource.background_work_per_agent_s * background_factor
                ),
                measurement_provenance=(
                    f"notional Stage 3A fixture; architecture={scenario.architecture}; "
                    f"workload={scenario.workload}"
                ),
            )
        )
    return tuple(output)


def _pava_fit(score: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(score, dtype=float)
    y = np.asarray(target, dtype=float)
    if x.shape != y.shape or x.ndim != 1 or len(x) == 0:
        raise ValueError("PAVA score and target must be nonempty equal vectors")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("PAVA inputs must be finite")
    order = np.argsort(x, kind="mergesort")
    unique_x, inverse = np.unique(x[order], return_inverse=True)
    weights = np.bincount(inverse).astype(float)
    means = np.bincount(inverse, weights=y[order]) / weights
    blocks: list[list[float]] = []
    for value, weight in zip(means, weights):
        blocks.append([float(value), float(weight), 1.0])
        while len(blocks) >= 2 and blocks[-2][0] > blocks[-1][0]:
            right = blocks.pop()
            left = blocks.pop()
            combined = left[1] + right[1]
            blocks.append(
                [
                    (left[0] * left[1] + right[0] * right[1]) / combined,
                    combined,
                    left[2] + right[2],
                ]
            )
    calibrated: list[float] = []
    for value, _weight, count in blocks:
        calibrated.extend([value] * int(count))
    return unique_x, np.clip(np.asarray(calibrated), 0.0, 1.0)


def _pava_predict(score: np.ndarray, fit_x: np.ndarray, fit_y: np.ndarray) -> np.ndarray:
    values = np.asarray(score, dtype=float)
    if len(fit_x) == 1:
        return np.full(len(values), fit_y[0])
    return np.asarray(
        np.clip(
            np.interp(values, fit_x, fit_y, left=fit_y[0], right=fit_y[-1]),
            0.0,
            1.0,
        ),
        dtype=float,
    )


def _cross_fitted_pava_mse(
    score: np.ndarray,
    target: np.ndarray,
    groups: Sequence[str],
) -> float:
    values = np.asarray(score, dtype=float)
    labels = np.asarray(target, dtype=float)
    group_values = np.asarray(groups, dtype=str)
    if values.shape != labels.shape or values.shape != group_values.shape:
        raise ValueError("cross-fitted PAVA inputs must have equal shape")
    predicted: np.ndarray = np.empty(len(values), dtype=float)
    for group in np.unique(group_values):
        validation = group_values == group
        fitting = ~validation
        if not fitting.any():
            raise ValueError("cross-fitted PAVA requires at least two groups")
        fit_x, fit_y = _pava_fit(values[fitting], labels[fitting])
        predicted[validation] = _pava_predict(values[validation], fit_x, fit_y)
    return float(np.mean((predicted - labels) ** 2))


def _fit_logistic(matrix: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = np.mean(matrix, axis=0)
    scale = np.std(matrix, axis=0)
    scale = np.where(scale > 1e-12, scale, 1.0)
    design = np.column_stack([np.ones(len(matrix)), (matrix - mean) / scale])
    y = np.asarray(target, dtype=float)
    coefficients = np.zeros(design.shape[1])
    average = float(np.clip(np.mean(y), 1e-5, 1.0 - 1e-5))
    coefficients[0] = np.log(average / (1.0 - average))
    penalty = np.eye(design.shape[1]) * 1e-3
    penalty[0, 0] = 0.0
    for _ in range(100):
        probability = 1.0 / (1.0 + np.exp(-np.clip(design @ coefficients, -35.0, 35.0)))
        weight = np.maximum(probability * (1.0 - probability), 1e-7)
        working = design @ coefficients + (y - probability) / weight
        lhs = design.T @ (weight[:, None] * design) + penalty
        rhs = design.T @ (weight * working)
        updated = np.linalg.solve(lhs, rhs)
        if np.max(np.abs(updated - coefficients)) < 1e-9:
            coefficients = updated
            break
        coefficients = updated
    return coefficients, mean, scale


def _logistic_predict(
    matrix: np.ndarray,
    coefficients: np.ndarray,
    mean: np.ndarray,
    scale: np.ndarray,
) -> np.ndarray:
    design = np.column_stack([np.ones(len(matrix)), (matrix - mean) / scale])
    return 1.0 / (1.0 + np.exp(-np.clip(design @ coefficients, -35.0, 35.0)))


def _balanced_accuracy(labels: np.ndarray, predicted: np.ndarray) -> float:
    positive = labels == 1
    negative = labels == 0
    if not positive.any() or not negative.any():
        return float("nan")
    sensitivity = float(np.mean(predicted[positive] == 1))
    specificity = float(np.mean(predicted[negative] == 0))
    return 0.5 * (sensitivity + specificity)


def _select_threshold(score: np.ndarray, labels: np.ndarray) -> tuple[float, float]:
    candidates = np.unique(np.quantile(score, np.linspace(0.0, 1.0, 101)))
    best_threshold = float(candidates[0])
    best_accuracy = -1.0
    for threshold in candidates:
        accuracy = _balanced_accuracy(labels, (score >= threshold).astype(int))
        if math.isfinite(accuracy) and accuracy > best_accuracy:
            best_accuracy = accuracy
            best_threshold = float(threshold)
    return best_threshold, float(best_accuracy)


def _hierarchical_bootstrap(
    frame: pd.DataFrame,
    *,
    candidate_error: str,
    baseline_error: str,
    seed: int,
    draws: int,
    cluster_column: str = "scenario_id",
    replication_unit_column: str | None = None,
) -> dict[str, list[float]]:
    if draws < 1:
        raise ValueError("bootstrap draws must be positive")
    required = {"block_id", cluster_column, candidate_error, baseline_error}
    if replication_unit_column is not None:
        required.add(replication_unit_column)
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"bootstrap frame is missing columns: {sorted(missing)}")

    # Pre-group once, then resample paired candidate/baseline arrays in bounded
    # batches. Each replication unit retains every factor or defense row that
    # shares its random stream, so common-random-number dependence is preserved.
    grouped_blocks: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
    for block_id in sorted(frame.block_id.unique()):
        block = frame[frame.block_id == block_id]
        cluster_candidate: list[np.ndarray] = []
        cluster_baseline: list[np.ndarray] = []
        cluster_counts: list[np.ndarray] = []
        for cluster_id in block[cluster_column].unique():
            cluster = block[block[cluster_column] == cluster_id]
            if replication_unit_column is None:
                unit_values = tuple(range(len(cluster)))
                unit_series = pd.Series(np.arange(len(cluster)), index=cluster.index)
            else:
                unit_values = tuple(cluster[replication_unit_column].unique())
                unit_series = cluster[replication_unit_column]
            candidate_units: list[float] = []
            baseline_units: list[float] = []
            unit_row_counts: list[int] = []
            for unit in unit_values:
                rows = cluster[unit_series == unit]
                pair = rows[[candidate_error, baseline_error]].to_numpy(float)
                if not np.isfinite(pair).all() or len(pair) == 0:
                    raise ValueError("bootstrap errors must be finite and nonempty")
                candidate_units.append(float(pair[:, 0].sum()))
                baseline_units.append(float(pair[:, 1].sum()))
                unit_row_counts.append(len(pair))
            cluster_candidate.append(np.asarray(candidate_units, dtype=float))
            cluster_baseline.append(np.asarray(baseline_units, dtype=float))
            cluster_counts.append(np.asarray(unit_row_counts, dtype=np.int64))
        if not cluster_candidate:
            raise ValueError("every bootstrap block must contain a resampling cluster")
        replication_counts = {len(values) for values in cluster_candidate}
        if len(replication_counts) != 1 or next(iter(replication_counts)) < 1:
            raise ValueError(
                "hierarchical bootstrap requires equal replication-unit counts "
                "within a block"
            )
        grouped_blocks.append(
            (
                np.stack(cluster_candidate, axis=0),
                np.stack(cluster_baseline, axis=0),
                np.stack(cluster_counts, axis=0),
            )
        )

    if not grouped_blocks:
        raise ValueError("hierarchical bootstrap requires at least one block")
    rng = np.random.default_rng(seed)
    block_count = len(grouped_blocks)
    absolute: np.ndarray = np.empty(draws, dtype=float)
    fractional: np.ndarray = np.empty(draws, dtype=float)
    batch_size = 64
    for start in range(0, draws, batch_size):
        stop = min(start + batch_size, draws)
        size = stop - start
        sampled_blocks = rng.integers(0, block_count, size=(size, block_count))
        candidate_sum: np.ndarray = np.zeros(size, dtype=float)
        baseline_sum: np.ndarray = np.zeros(size, dtype=float)
        sampled_count: np.ndarray = np.zeros(size, dtype=np.int64)
        for position in range(block_count):
            for source_index, (candidate, baseline, retained_row_counts) in enumerate(
                grouped_blocks
            ):
                selected_draws = np.flatnonzero(sampled_blocks[:, position] == source_index)
                if selected_draws.size == 0:
                    continue
                cluster_count, replication_count = candidate.shape
                sampled_clusters = rng.integers(
                    0,
                    cluster_count,
                    size=(selected_draws.size, cluster_count),
                )
                sampled_replications = rng.integers(
                    0,
                    replication_count,
                    size=(selected_draws.size, cluster_count, replication_count),
                )
                expanded_clusters = sampled_clusters[:, :, None]
                candidate_values = candidate[
                    expanded_clusters, sampled_replications
                ]
                baseline_values = baseline[
                    expanded_clusters, sampled_replications
                ]
                retained_counts = retained_row_counts[
                    expanded_clusters, sampled_replications
                ]
                candidate_sum[selected_draws] += candidate_values.sum(axis=(1, 2))
                baseline_sum[selected_draws] += baseline_values.sum(axis=(1, 2))
                sampled_count[selected_draws] += retained_counts.sum(axis=(1, 2))
        candidate_mean = candidate_sum / sampled_count
        baseline_mean = baseline_sum / sampled_count
        improvement = baseline_mean - candidate_mean
        absolute[start:stop] = improvement
        fractional[start:stop] = improvement / np.maximum(baseline_mean, 1e-12)
    absolute_interval: np.ndarray = np.asarray(
        np.quantile(absolute, [0.025, 0.975]), dtype=float
    )
    fractional_interval: np.ndarray = np.asarray(
        np.quantile(fractional, [0.025, 0.975]), dtype=float
    )
    return {
        "absolute_improvement": [
            float(absolute_interval[0]),
            float(absolute_interval[1]),
        ],
        "fractional_improvement": [
            float(fractional_interval[0]),
            float(fractional_interval[1]),
        ],
    }


def analyze_stage3a(
    raw: pd.DataFrame,
    *,
    acceptance: Mapping[str, Any],
    bootstrap_seed: int,
    bootstrap_draws: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fit on training, select on calibration, and adjudicate held-out Stage 3A."""

    required = {
        "partition",
        "block_id",
        "scenario_id",
        "operational_failure",
        "omega_a",
        "final_n",
        "architecture",
        "workload",
        "capacity_multiplier",
        "randomization_pair_id",
        "replication",
        *_STAGE3A_SIMPLE_PREDICTORS,
    }
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(f"Stage 3A analysis is missing columns: {sorted(missing)}")
    prediction_frames: list[pd.DataFrame] = []
    block_rows: list[dict[str, Any]] = []
    for block_id in sorted(raw.block_id.unique()):
        block = raw[raw.block_id == block_id]
        training = block[block.partition == "training"]
        calibration = block[block.partition == "calibration"]
        heldout = block[block.partition == "held_out"].copy()
        if training.empty or calibration.empty or heldout.empty:
            raise ValueError(f"Stage 3A block {block_id} lacks a required partition")
        train_y = training.operational_failure.to_numpy(int)
        calibration_y = calibration.operational_failure.to_numpy(int)
        heldout_y = heldout.operational_failure.to_numpy(int)
        class_support = {
            "training": set(np.unique(train_y)) == {0, 1},
            "calibration": set(np.unique(calibration_y)) == {0, 1},
            "held_out": set(np.unique(heldout_y)) == {0, 1},
        }

        omega_x, omega_y = _pava_fit(
            calibration.omega_a.to_numpy(float), calibration_y
        )
        heldout["candidate_probability"] = _pava_predict(
            heldout.omega_a.to_numpy(float), omega_x, omega_y
        )
        calibration_scores: dict[str, float] = {}
        scalar_models: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for predictor in _STAGE3A_SIMPLE_PREDICTORS:
            fit_x, fit_y = _pava_fit(
                calibration[predictor].to_numpy(float), calibration_y
            )
            scalar_models[predictor] = (fit_x, fit_y)
            calibration_scores[predictor] = _cross_fitted_pava_mse(
                calibration[predictor].to_numpy(float),
                calibration_y,
                calibration.scenario_id.astype(str).to_numpy(),
            )
        strongest_simple = min(
            calibration_scores, key=lambda name: calibration_scores[name]
        )
        simple_x, simple_y = scalar_models[strongest_simple]
        heldout["baseline_probability"] = _pava_predict(
            heldout[strongest_simple].to_numpy(float), simple_x, simple_y
        )

        feature_matrix = training[list(_STAGE3A_SIMPLE_PREDICTORS)].to_numpy(float)
        coefficients, feature_mean, feature_scale = _fit_logistic(feature_matrix, train_y)
        calibration_logistic = _logistic_predict(
            calibration[list(_STAGE3A_SIMPLE_PREDICTORS)].to_numpy(float),
            coefficients,
            feature_mean,
            feature_scale,
        )
        calibration_x, calibration_y_map = _pava_fit(calibration_logistic, calibration_y)
        raw_logistic = _logistic_predict(
            heldout[list(_STAGE3A_SIMPLE_PREDICTORS)].to_numpy(float),
            coefficients,
            feature_mean,
            feature_scale,
        )
        heldout["multivariate_probability"] = _pava_predict(
            raw_logistic, calibration_x, calibration_y_map
        )

        threshold, calibration_balanced_accuracy = _select_threshold(
            calibration.omega_a.to_numpy(float), calibration_y
        )
        transfer = heldout[heldout.final_n == 10_000]
        transfer_accuracy = _balanced_accuracy(
            transfer.operational_failure.to_numpy(int),
            (transfer.omega_a.to_numpy(float) >= threshold).astype(int),
        )
        sublinear_transfer = transfer[
            transfer.architecture == "sharded_sublinear_capacity"
        ]
        sublinear_transfer_accuracy = _balanced_accuracy(
            sublinear_transfer.operational_failure.to_numpy(int),
            (sublinear_transfer.omega_a.to_numpy(float) >= threshold).astype(int),
        )
        candidate_metrics = binary_predictive_metrics(
            heldout_y, heldout.candidate_probability.to_numpy(float)
        )
        baseline_metrics = binary_predictive_metrics(
            heldout_y, heldout.baseline_probability.to_numpy(float)
        )
        multivariate_metrics = binary_predictive_metrics(
            heldout_y, heldout.multivariate_probability.to_numpy(float)
        )
        heldout["candidate_squared_error"] = (
            heldout.candidate_probability - heldout.operational_failure
        ) ** 2
        heldout["baseline_squared_error"] = (
            heldout.baseline_probability - heldout.operational_failure
        ) ** 2
        improvement = (
            baseline_metrics.brier_score - candidate_metrics.brier_score
        ) / max(baseline_metrics.brier_score, 1e-12)
        block_rows.append(
            {
                "block": int(block_id),
                "strongest_simple_baseline": strongest_simple,
                "baseline_selection_partition": "calibration",
                "probability_mapping_partition": "calibration",
                "baseline_selection_method": "leave_one_scenario_out_crossfit",
                "binary_class_support": class_support,
                "candidate_brier": candidate_metrics.brier_score,
                "baseline_brier": baseline_metrics.brier_score,
                "multivariate_brier": multivariate_metrics.brier_score,
                "brier_improvement_fraction": float(improvement),
                "candidate_auc": candidate_metrics.roc_auc,
                "calibration_intercept": candidate_metrics.calibration_intercept,
                "calibration_slope": candidate_metrics.calibration_slope,
                "calibration_threshold": threshold,
                "calibration_threshold_balanced_accuracy": calibration_balanced_accuracy,
                "n10000_transfer_balanced_accuracy": transfer_accuracy,
                "n10000_sublinear_capacity_transfer_balanced_accuracy": (
                    sublinear_transfer_accuracy
                ),
            }
        )
        prediction_frames.append(heldout)

    predictions = pd.concat(prediction_frames, ignore_index=True)
    blocks = pd.DataFrame(block_rows)
    observed = predictions.operational_failure.to_numpy(int)
    candidate_metrics = binary_predictive_metrics(
        observed, predictions.candidate_probability.to_numpy(float)
    )
    baseline_metrics = binary_predictive_metrics(
        observed, predictions.baseline_probability.to_numpy(float)
    )
    multivariate_metrics = binary_predictive_metrics(
        observed, predictions.multivariate_probability.to_numpy(float)
    )
    improvement = (
        baseline_metrics.brier_score - candidate_metrics.brier_score
    ) / max(baseline_metrics.brier_score, 1e-12)
    bootstrap = _hierarchical_bootstrap(
        predictions,
        candidate_error="candidate_squared_error",
        baseline_error="baseline_squared_error",
        seed=bootstrap_seed,
        draws=bootstrap_draws,
        cluster_column="randomization_pair_id",
        replication_unit_column="replication",
    )

    def shifted_improvement(mask: pd.Series) -> float:
        selected = predictions[mask]
        if selected.empty:
            return float("nan")
        candidate = float(selected.candidate_squared_error.mean())
        baseline = float(selected.baseline_squared_error.mean())
        return (baseline - candidate) / max(baseline, 1e-12)

    architecture_shift_results = {
        str(value): shifted_improvement(predictions.architecture == value)
        for value in sorted(set(predictions.architecture) - {"centralized_balanced"})
    }
    capacity_shift_results = {
        f"{float(value):.2f}": shifted_improvement(
            predictions.capacity_multiplier == value
        )
        for value in sorted(set(predictions.capacity_multiplier) - {1.0})
    }
    workload_shift_value = shifted_improvement(predictions.workload == "gamma")
    combined_shift_value = shifted_improvement(
        (predictions.architecture != "centralized_balanced")
        & (predictions.capacity_multiplier != 1.0)
        & (predictions.workload == "gamma")
    )
    shift_results = {
        "architecture_improvement_by_unseen_architecture": architecture_shift_results,
        "capacity_improvement_by_shift": capacity_shift_results,
        "workload_gamma_improvement": workload_shift_value,
        "combined_shift_improvement": combined_shift_value,
    }
    slope_low, slope_high = map(float, acceptance["calibration_slope_range"])
    minimum_transfer = float(acceptance["minimum_transfer_balanced_accuracy"])
    transfer_values = blocks.n10000_transfer_balanced_accuracy.to_numpy(float)
    sublinear_transfer_values = (
        blocks.n10000_sublinear_capacity_transfer_balanced_accuracy.to_numpy(float)
    )
    architecture_shift_evaluable = bool(
        architecture_shift_results
        and all(math.isfinite(value) for value in architecture_shift_results.values())
    )
    capacity_shift_evaluable = bool(
        capacity_shift_results
        and all(math.isfinite(value) for value in capacity_shift_results.values())
    )
    criteria = {
        "all_blocks_have_binary_class_support": _criterion(
            all(
                all(bool(value) for value in row["binary_class_support"].values())
                for row in block_rows
            ),
            observed={str(row["block"]): row["binary_class_support"] for row in block_rows},
            rule="both outcome classes present in training, calibration, and held-out",
        ),
        "brier_improvement_at_least_15pct": _criterion(
            improvement >= float(acceptance["minimum_brier_improvement_fraction"]),
            observed=improvement,
            rule=(
                f">= {float(acceptance['minimum_brier_improvement_fraction']):.6g}"
            ),
        ),
        "bootstrap_fractional_lower_bound_positive": _criterion(
            float(bootstrap["fractional_improvement"][0])
            > float(acceptance["bootstrap_improvement_lower_bound_greater_than"]),
            observed=float(bootstrap["fractional_improvement"][0]),
            rule=(
                "> "
                f"{float(acceptance['bootstrap_improvement_lower_bound_greater_than']):.6g}"
            ),
        ),
        "auc_at_least_0_90": _criterion(
            (
                candidate_metrics.roc_auc >= float(acceptance["minimum_auc"])
                if math.isfinite(candidate_metrics.roc_auc)
                else None
            ),
            observed=candidate_metrics.roc_auc,
            rule=f">= {float(acceptance['minimum_auc']):.6g}",
        ),
        "calibration_slope_in_range": _criterion(
            (
                slope_low <= candidate_metrics.calibration_slope <= slope_high
                if math.isfinite(candidate_metrics.calibration_slope)
                else None
            ),
            observed=candidate_metrics.calibration_slope,
            rule=f"in [{slope_low:.6g}, {slope_high:.6g}]",
        ),
        "positive_improvement_in_four_of_five_blocks": _criterion(
            int((blocks.brier_improvement_fraction > 0.0).sum())
            >= int(acceptance["minimum_positive_blocks"]),
            observed=int((blocks.brier_improvement_fraction > 0.0).sum()),
            rule=f">= {int(acceptance['minimum_positive_blocks'])} blocks",
        ),
        "threshold_transfers_to_n10000": _criterion(
            (
                bool((transfer_values >= minimum_transfer).all())
                if np.isfinite(transfer_values).all()
                else None
            ),
            observed={
                str(int(row.block)): row.n10000_transfer_balanced_accuracy
                for row in blocks.itertuples()
            },
            rule=f">= {minimum_transfer:.6g} in every block",
        ),
        "threshold_transfers_to_n10000_sublinear_capacity": _criterion(
            (
                bool((sublinear_transfer_values >= minimum_transfer).all())
                if np.isfinite(sublinear_transfer_values).all()
                else None
            ),
            observed={
                str(int(row.block)): (
                    row.n10000_sublinear_capacity_transfer_balanced_accuracy
                )
                for row in blocks.itertuples()
            },
            rule=f">= {minimum_transfer:.6g} in every block",
        ),
        "architecture_shift_survives": _criterion(
            (
                all(value > 0.0 for value in architecture_shift_results.values())
                if architecture_shift_evaluable
                else None
            ),
            observed=architecture_shift_results,
            rule="> 0 for every unseen architecture",
        ),
        "capacity_shift_survives": _criterion(
            (
                all(value > 0.0 for value in capacity_shift_results.values())
                if capacity_shift_evaluable
                else None
            ),
            observed=capacity_shift_results,
            rule="> 0 for every non-reference capacity",
        ),
        "workload_shift_survives": _criterion(
            workload_shift_value > 0.0 if math.isfinite(workload_shift_value) else None,
            observed=workload_shift_value,
            rule="> 0 for gamma workload",
        ),
        "combined_shift_survives": _criterion(
            combined_shift_value > 0.0 if math.isfinite(combined_shift_value) else None,
            observed=combined_shift_value,
            rule="> 0 for combined architecture, capacity, and workload shift",
        ),
    }
    summary = {
        "disposition": (
            "supported_within_declared_model"
            if _all_criteria_pass(criteria)
            else "not_supported_under_preregistered_rule"
        ),
        "evidence_scope": "synthetic_model_conditioned; calibration_interface_only",
        "external_validation": False,
        "candidate": "projected_omega_a",
        "candidate_metrics": _reported_value(candidate_metrics),
        "strongest_simple_baseline_metrics": _reported_value(baseline_metrics),
        "multivariate_baseline_metrics": _reported_value(multivariate_metrics),
        "pooled_brier_improvement_fraction": float(improvement),
        "bootstrap_95pct": _reported_value(bootstrap),
        "block_results": _reported_value(block_rows),
        "shift_results": _reported_value(shift_results),
        "criteria": criteria,
    }
    return predictions, summary


def build_stage3b_specs(
    protocol: Mapping[str, Any],
    compromise_config: Mapping[str, Any],
    seeds: pd.DataFrame,
    *,
    replications: int,
    seed_domain: str = "confirmatory-stage3b",
) -> tuple[Stage3BScenarioSpec, ...]:
    """Build the fixed cross-scale Stage 3B scenario matrix."""

    topologies = compromise_config["topologies"]
    attack_classes = tuple(str(value) for value in compromise_config["attack_classes"])
    segmentations = tuple(str(value) for value in compromise_config["segmentation_policies"])
    partitions: tuple[
        tuple[
            Literal["training", "calibration", "held_out"],
            Literal["exploratory", "calibration", "heldout"],
        ],
        ...,
    ] = (
        ("training", "exploratory"),
        ("calibration", "calibration"),
        ("held_out", "heldout"),
    )
    block_count = int(protocol["partitions"]["independent_blocks"])
    specs: list[Stage3BScenarioSpec] = []
    for block in range(block_count):
        for manifest_partition, model_split in partitions:
            sizes = _partition_sizes(protocol, manifest_partition)
            row = _seed_row(seeds, block, manifest_partition)
            topology_choices = tuple(str(value) for value in topologies[manifest_partition])
            scenario_index = 0
            for n_agents in sizes:
                for attack_index, attack_class in enumerate(attack_classes):
                    topology = topology_choices[(attack_index + block) % len(topology_choices)]
                    segmentation = segmentations[
                        ((attack_index // len(topology_choices)) + block)
                        % len(segmentations)
                    ]
                    defense_cases = (
                        ("nominal", "detection_response_shift")
                        if model_split == "heldout"
                        else ("nominal",)
                    )
                    offset = scenario_index * 101
                    pair_id = (
                        f"s3b-b{block}-{model_split}-n{n_agents}-{topology}-"
                        f"{attack_class}-{segmentation}"
                    )
                    seeds_for_pair = {
                        "graph_seed": _domain_seed(int(row.graph_seed) + offset, seed_domain),
                        "process_seed": _domain_seed(int(row.process_seed) + offset, seed_domain),
                        "observation_seed": _domain_seed(
                            int(row.observation_seed) + offset, seed_domain
                        ),
                        "replication_seed": _domain_seed(
                            int(row.replication_seed) + offset, seed_domain
                        ),
                    }
                    for defense_case in defense_cases:
                        defense = compromise_config["defense_shifts"]
                        if defense_case == "nominal":
                            detection_probability = float(
                                defense["detection_probability"][1]
                            )
                            quarantine_delay = int(defense["quarantine_delay_steps"][1])
                            revocation_delay = int(defense["revocation_delay_steps"][1])
                            partition_probability = float(
                                defense["partition_probability"][0]
                            )
                        else:
                            detection_probability = float(
                                defense["detection_probability"][0]
                            )
                            quarantine_delay = int(defense["quarantine_delay_steps"][-1])
                            revocation_delay = int(defense["revocation_delay_steps"][-1])
                            partition_probability = float(
                                defense["partition_probability"][-1]
                            )
                        specs.append(
                            Stage3BScenarioSpec(
                                scenario_id=f"{pair_id}-{defense_case}",
                                split=model_split,
                                block=block,
                                n_agents=n_agents,
                                topology=topology,
                                segmentation_policy=segmentation,
                                attack_class=attack_class,
                                **seeds_for_pair,
                                replications=replications,
                                defense_case=defense_case,
                                detection_probability=detection_probability,
                                quarantine_delay_steps=quarantine_delay,
                                revocation_delay_steps=revocation_delay,
                                partition_probability=partition_probability,
                            )
                        )
                    scenario_index += 1
    return tuple(specs)


def _stage3b_records_frame(
    result: Stage3BExperimentResult | Sequence[Any],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    records = result.records if isinstance(result, Stage3BExperimentResult) else result
    for record in records:
        payload = {
            "record_id": record.record_id,
            "scenario_id": record.scenario_id,
            "split": record.split,
            "block": record.block,
            "n_agents": record.n_agents,
            "topology": record.topology,
            "attack_class": record.attack_class,
            "segmentation_policy": record.segmentation_policy,
            "defense_case": record.defense_case,
            "defense_pair_id": record.scenario_id.rsplit("-", 1)[0],
            "outbreak": record.outbreak,
            "final_compromise_fraction": record.final_compromise_fraction,
            "replication_seed": record.replication_seed,
            "base_replication_seed": record.base_replication_seed,
            "graph_seed": record.graph_seed,
            "process_seed": record.process_seed,
            "observation_seed": record.observation_seed,
            "detection_probability": record.detection_probability,
            "quarantine_delay_steps": record.quarantine_delay_steps,
            "revocation_delay_steps": record.revocation_delay_steps,
            "partition_probability": record.partition_probability,
            "attack_trace_digest": record.attack_trace_digest,
            "attack_horizon_steps": record.attack_horizon_steps,
            "outbreak_onset_step": record.outbreak_onset_step,
            "attack_peak_active_fraction": record.attack_peak_active_fraction,
            "attack_event_count": record.attack_event_count,
            "attack_event_type_counts_json": json.dumps(
                dict(record.attack_event_type_counts), sort_keys=True, separators=(",", ":")
            ),
            "attack_event_first_step_json": json.dumps(
                dict(record.attack_event_first_step), sort_keys=True, separators=(",", ":")
            ),
            "attack_event_last_step_json": json.dumps(
                dict(record.attack_event_last_step), sort_keys=True, separators=(",", ":")
            ),
        }
        payload.update(record.features)
        rows.append(payload)
    return pd.DataFrame(rows)


def _stage3b_predictions_frame(result: Stage3BExperimentResult) -> pd.DataFrame:
    heldout = tuple(record for record in result.records if record.split == "heldout")
    frame = pd.DataFrame(
        {
            "record_id": [record.record_id for record in heldout],
            "scenario_id": [record.scenario_id for record in heldout],
            "block": [record.block for record in heldout],
            "n_agents": [record.n_agents for record in heldout],
            "topology": [record.topology for record in heldout],
            "attack_class": [record.attack_class for record in heldout],
            "segmentation_policy": [record.segmentation_policy for record in heldout],
            "defense_case": [record.defense_case for record in heldout],
            "defense_pair_id": [
                record.scenario_id.rsplit("-", 1)[0] for record in heldout
            ],
            "defense_pair_record_id": [
                f"{record.scenario_id.rsplit('-', 1)[0]}:{record.record_id.rsplit(':', 1)[1]}"
                for record in heldout
            ],
            "replication_seed": [record.replication_seed for record in heldout],
            "base_replication_seed": [record.base_replication_seed for record in heldout],
            "graph_seed": [record.graph_seed for record in heldout],
            "process_seed": [record.process_seed for record in heldout],
            "observation_seed": [record.observation_seed for record in heldout],
            "outbreak": [record.outbreak for record in heldout],
            "final_compromise_fraction": [record.final_compromise_fraction for record in heldout],
            "candidate_outbreak_probability": result.candidate_prediction.outbreak_probability,
            "candidate_conditional_severity": result.candidate_prediction.conditional_severity,
            "candidate_conditional_severity_lower": result.candidate_prediction.conditional_severity_lower,
            "candidate_conditional_nonoutbreak_severity": (
                result.candidate_prediction.conditional_nonoutbreak_severity
            ),
            "candidate_conditional_nonoutbreak_severity_lower": (
                result.candidate_prediction.conditional_nonoutbreak_severity_lower
            ),
            "candidate_conditional_nonoutbreak_severity_upper": (
                result.candidate_prediction.conditional_nonoutbreak_severity_upper
            ),
            "candidate_expected_final_fraction": result.candidate_prediction.expected_final_fraction,
            "candidate_expected_final_fraction_lower": (
                result.candidate_prediction.expected_final_fraction_lower
            ),
            "candidate_expected_final_fraction_upper": (
                result.candidate_prediction.expected_final_fraction_upper
            ),
        }
    )
    final_prediction = result.baseline_predictions[
        result.strongest_final_size_baseline
    ].expected_final_fraction
    initiation_prediction = result.baseline_predictions[
        result.strongest_initiation_baseline
    ].outbreak_probability
    frame["baseline_final_fraction"] = final_prediction
    frame["baseline_outbreak_probability"] = initiation_prediction
    frame["candidate_final_absolute_error"] = np.abs(
        frame.candidate_expected_final_fraction - frame.final_compromise_fraction
    )
    frame["baseline_final_absolute_error"] = np.abs(
        frame.baseline_final_fraction - frame.final_compromise_fraction
    )
    frame["candidate_brier_component"] = (
        frame.candidate_outbreak_probability - frame.outbreak
    ) ** 2
    frame["baseline_brier_component"] = (
        frame.baseline_outbreak_probability - frame.outbreak
    ) ** 2
    return frame


def analyze_stage3b(
    result: Stage3BExperimentResult,
    predictions: pd.DataFrame,
    *,
    acceptance: Mapping[str, Any],
    bootstrap_seed: int,
    bootstrap_draws: int,
    boundary_audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    final_bootstrap = _hierarchical_bootstrap(
        predictions.rename(columns={"block": "block_id"}),
        candidate_error="candidate_final_absolute_error",
        baseline_error="baseline_final_absolute_error",
        seed=bootstrap_seed,
        draws=bootstrap_draws,
        cluster_column="defense_pair_id",
        replication_unit_column="defense_pair_record_id",
    )
    brier_bootstrap = _hierarchical_bootstrap(
        predictions.rename(columns={"block": "block_id"}),
        candidate_error="candidate_brier_component",
        baseline_error="baseline_brier_component",
        seed=bootstrap_seed + 1,
        draws=bootstrap_draws,
        cluster_column="defense_pair_id",
        replication_unit_column="defense_pair_record_id",
    )
    candidate = result.candidate_evaluation
    defense_nominal = predictions[predictions.defense_case == "nominal"]
    defense_shift = predictions[predictions.defense_case != "nominal"]

    def grouped_transfer_improvement(column: str, values: Sequence[Any]) -> dict[str, float]:
        output: dict[str, float] = {}
        for value in values:
            selected = predictions[predictions[column] == value]
            if selected.empty:
                output[str(value)] = float("nan")
                continue
            candidate_mae = float(selected.candidate_final_absolute_error.mean())
            baseline_mae = float(selected.baseline_final_absolute_error.mean())
            output[str(value)] = (baseline_mae - candidate_mae) / max(
                baseline_mae, 1e-12
            )
        return output

    topology_transfer = grouped_transfer_improvement(
        "topology", ("barabasi_albert", "hierarchical")
    )
    scale_transfer = grouped_transfer_improvement("n_agents", (1_000, 10_000))
    minimum_transfer_improvement = float(
        acceptance["minimum_transfer_mae_improvement_fraction"]
    )

    def calibration_slope(frame: pd.DataFrame) -> float | None:
        if frame.empty or frame.outbreak.nunique() != 2:
            return None
        slope = binary_predictive_metrics(
            frame.outbreak.to_numpy(int),
            frame.candidate_outbreak_probability.to_numpy(float),
        ).calibration_slope
        return float(slope) if math.isfinite(slope) else None

    nominal_slope = calibration_slope(defense_nominal)
    shifted_slope = calibration_slope(defense_shift)
    unsegmented_slope = calibration_slope(
        predictions[predictions.segmentation_policy == "none"]
    )
    segmented_slope = calibration_slope(
        predictions[predictions.segmentation_policy != "none"]
    )
    defense_slope_change = (
        abs(shifted_slope - nominal_slope)
        if shifted_slope is not None and nominal_slope is not None
        else None
    )
    segmentation_slope_change = (
        abs(segmented_slope - unsegmented_slope)
        if segmented_slope is not None and unsegmented_slope is not None
        else None
    )
    pair_columns = {
        "defense_pair_record_id",
        "defense_case",
        "graph_seed",
        "process_seed",
        "observation_seed",
        "base_replication_seed",
        "replication_seed",
    }
    pair_completeness = False
    if pair_columns.issubset(predictions.columns) and not predictions.empty:
        pair_completeness = all(
            set(group.defense_case.astype(str))
            == {"nominal", "detection_response_shift"}
            and len(group) == 2
            and all(
                group[column].nunique(dropna=False) == 1
                for column in (
                    "graph_seed",
                    "process_seed",
                    "observation_seed",
                    "base_replication_seed",
                    "replication_seed",
                )
            )
            for _, group in predictions.groupby("defense_pair_record_id", sort=False)
        )
    expected_heldout_blocks = {int(value) for value in predictions.block.unique()}
    binary_support_by_block = {
        int(key): bool(value)
        for key, value in result.heldout_binary_support_by_block.items()
    }
    all_blocks_have_binary_support = bool(expected_heldout_blocks) and (
        set(binary_support_by_block) == expected_heldout_blocks
        and all(binary_support_by_block.values())
    )
    boundary_passed = (
        bool(
            boundary_audit.get("status") == "passed_structural_review"
            and boundary_audit.get("identical_latent_equation_reuse_detected") is False
        )
        if boundary_audit is not None
        else None
    )
    criteria = {
        "final_size_mae_improvement_at_least_15pct": _criterion(
            result.final_size_mae_improvement_fraction
            >= float(acceptance["minimum_final_size_mae_improvement_fraction"]),
            observed=result.final_size_mae_improvement_fraction,
            rule=(
                f">= {float(acceptance['minimum_final_size_mae_improvement_fraction']):.6g}"
            ),
        ),
        "outbreak_brier_improvement_at_least_10pct": _criterion(
            result.outbreak_brier_improvement_fraction
            >= float(acceptance["minimum_outbreak_brier_improvement_fraction"]),
            observed=result.outbreak_brier_improvement_fraction,
            rule=(
                f">= {float(acceptance['minimum_outbreak_brier_improvement_fraction']):.6g}"
            ),
        ),
        "final_size_positive_in_four_of_five_blocks": _criterion(
            result.positive_final_size_blocks
            >= int(acceptance["minimum_positive_blocks"]),
            observed=result.positive_final_size_blocks,
            rule=f">= {int(acceptance['minimum_positive_blocks'])} blocks",
        ),
        "outbreak_brier_positive_in_four_of_five_blocks": _criterion(
            result.positive_outbreak_brier_blocks
            >= int(acceptance["minimum_positive_blocks"]),
            observed=result.positive_outbreak_brier_blocks,
            rule=f">= {int(acceptance['minimum_positive_blocks'])} blocks",
        ),
        "final_size_bootstrap_lower_bound_positive": _criterion(
            float(final_bootstrap["absolute_improvement"][0])
            > float(acceptance["bootstrap_improvement_lower_bound_greater_than"]),
            observed=float(final_bootstrap["absolute_improvement"][0]),
            rule=(
                "> "
                f"{float(acceptance['bootstrap_improvement_lower_bound_greater_than']):.6g}"
            ),
        ),
        "outbreak_brier_bootstrap_lower_bound_positive": _criterion(
            float(brier_bootstrap["absolute_improvement"][0])
            > float(acceptance["bootstrap_improvement_lower_bound_greater_than"]),
            observed=float(brier_bootstrap["absolute_improvement"][0]),
            rule=(
                "> "
                f"{float(acceptance['bootstrap_improvement_lower_bound_greater_than']):.6g}"
            ),
        ),
        "unseen_topology_transfer_succeeds": _criterion(
            (
                all(value > minimum_transfer_improvement for value in topology_transfer.values())
                if all(math.isfinite(value) for value in topology_transfer.values())
                else None
            ),
            observed=topology_transfer,
            rule=f"> {minimum_transfer_improvement:.6g} for every unseen topology",
        ),
        "unseen_scale_transfer_succeeds": _criterion(
            (
                all(value > minimum_transfer_improvement for value in scale_transfer.values())
                if all(math.isfinite(value) for value in scale_transfer.values())
                else None
            ),
            observed=scale_transfer,
            rule=f"> {minimum_transfer_improvement:.6g} at N=1000 and N=10000",
        ),
        "paired_defense_scenarios_complete": _criterion(
            pair_completeness,
            observed=pair_completeness,
            rule=(
                "every defense_pair_record_id has exactly both declared defense cases "
                "with shared graph, process, observation, base-replication, and "
                "derived-replication seeds"
            ),
        ),
        "all_heldout_blocks_have_binary_class_support": _criterion(
            all_blocks_have_binary_support,
            observed=binary_support_by_block,
            rule="both outbreak classes are present in every held-out block",
        ),
        "detection_response_calibration_shift_within_limit": _criterion(
            (
                defense_slope_change
                <= float(acceptance["maximum_calibration_slope_shift"])
                if defense_slope_change is not None
                else None
            ),
            observed=defense_slope_change,
            rule=f"<= {float(acceptance['maximum_calibration_slope_shift']):.6g}",
        ),
        "segmentation_calibration_shift_within_limit": _criterion(
            (
                segmentation_slope_change
                <= float(acceptance["maximum_calibration_slope_shift"])
                if segmentation_slope_change is not None
                else None
            ),
            observed=segmentation_slope_change,
            rule=f"<= {float(acceptance['maximum_calibration_slope_shift']):.6g}",
        ),
        "generator_predictor_structural_boundary_audit": _criterion(
            boundary_passed,
            observed=(boundary_audit.get("status") if boundary_audit else None),
            rule=(
                "frozen structural review passed and identical latent-equation reuse "
                "was not detected"
            ),
        ),
    }
    return {
        "disposition": (
            "supported_within_declared_model"
            if _all_criteria_pass(criteria)
            else "not_supported_under_preregistered_rule"
        ),
        "evidence_scope": (
            "synthetic_model_conditioned; separate_generator_implementation_with_"
            "bounded_observed_view"
        ),
        "external_validation": False,
        "candidate": "phase_separated_dynamic_message_passing",
        "selection_partition": result.selection_partition,
        "selection_method": result.selection_method,
        "comparator_specs": _reported_value(result.comparator_specs),
        "strongest_final_size_baseline": result.strongest_final_size_baseline,
        "strongest_initiation_baseline": result.strongest_initiation_baseline,
        "baseline_selection_scores": _reported_value(result.baseline_selection_scores),
        "candidate_evaluation": _reported_value(candidate),
        "selected_baseline_evaluations": _reported_value(result.baseline_evaluations),
        "final_size_mae_improvement_fraction": result.final_size_mae_improvement_fraction,
        "outbreak_brier_improvement_fraction": result.outbreak_brier_improvement_fraction,
        "positive_final_size_blocks": result.positive_final_size_blocks,
        "positive_outbreak_brier_blocks": result.positive_outbreak_brier_blocks,
        "heldout_binary_support_by_block": _reported_value(binary_support_by_block),
        "valid_binary_support_blocks": result.valid_binary_support_blocks,
        "final_size_bootstrap_95pct": _reported_value(final_bootstrap),
        "outbreak_brier_bootstrap_95pct": _reported_value(brier_bootstrap),
        "nominal_calibration_slope": nominal_slope,
        "shifted_calibration_slope": shifted_slope,
        "detection_response_calibration_slope_change": defense_slope_change,
        "unsegmented_calibration_slope": unsegmented_slope,
        "segmented_calibration_slope": segmented_slope,
        "segmentation_calibration_slope_change": segmentation_slope_change,
        "unseen_topology_final_size_mae_improvement_fraction": _json_value(
            topology_transfer
        ),
        "unseen_scale_final_size_mae_improvement_fraction": _json_value(scale_transfer),
        "generator_predictor_boundary_audit": _reported_value(boundary_audit),
        "criteria": criteria,
    }


def _write_stage3b_console_traces(
    execution_dir: Path,
    specs: Sequence[Stage3BScenarioSpec],
    *,
    attack_config: AttackTraceConfig,
    dmp_config: DMPConfig,
    execution_config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Retain fixed, visualization-only traces without consulting outcomes."""

    traces_per_block = int(execution_config["capture_full_trace_scenarios_per_block"])
    preferred_n = int(execution_config["canonical_trace_fleet_size"])
    preferred_attack = str(execution_config["canonical_trace_attack_class"])
    preferred_defense = str(execution_config["canonical_trace_defense_case"])
    replication = int(execution_config["canonical_trace_replication_index"])
    maximum_nodes = int(execution_config["maximum_graph_nodes"])
    maximum_edges = int(execution_config["maximum_graph_edges"])
    if traces_per_block < 1:
        return []

    selected: list[Stage3BScenarioSpec] = []
    for block in sorted({spec.block for spec in specs if spec.split == "heldout"}):
        eligible = sorted(
            (
                spec
                for spec in specs
                if spec.split == "heldout"
                and spec.block == block
                and spec.n_agents == preferred_n
                and spec.attack_class == preferred_attack
                and spec.defense_case == preferred_defense
            ),
            key=lambda spec: spec.scenario_id,
        )
        if len(eligible) < traces_per_block:
            raise ValueError(
                "canonical Stage 3B trace selection did not find the declared "
                f"scenario count for block {block}"
            )
        selected.extend(eligible[:traces_per_block])

    trace_dir = execution_dir / "stage3b" / "traces"
    trace_dir.mkdir(parents=True)
    lifecycle_rows: list[dict[str, Any]] = []
    dmp_rows: list[dict[str, Any]] = []
    metadata: list[dict[str, Any]] = []
    canonical_graph: dict[str, Any] | None = None
    for spec in selected:
        trace = materialize_stage3b_console_trace(
            spec,
            replication,
            attack_config=attack_config,
            dmp_config=dmp_config,
            maximum_graph_nodes=maximum_nodes,
            maximum_graph_edges=maximum_edges,
        )
        trace_metadata = {
            "record_id": trace.record_id,
            "scenario_id": trace.scenario_id,
            "block": trace.block,
            "replication": trace.replication,
            "replication_seed": trace.replication_seed,
            "graph_seed": trace.graph_seed,
            "process_seed": trace.process_seed,
            "observation_seed": trace.observation_seed,
            "attack_trace_digest": trace.attack_trace_digest,
            "attack_horizon_steps": trace.attack_horizon_steps,
            "dmp_horizon_steps": trace.dmp_horizon_steps,
            "dmp_outbreak_probability": trace.dmp_outbreak_probability,
            "dmp_expected_final_fraction": trace.dmp_expected_final_fraction,
            "evidence_scope": trace.evidence_scope,
            "selection_rule": (
                "fixed heldout fleet, attack class, defense case, replication, "
                "then scenario_id lexical order; no outcome-based selection"
            ),
        }
        metadata.append(_reported_value(trace_metadata))
        for lifecycle_point in trace.lifecycle:
            row = _reported_value(lifecycle_point)
            row.update(trace_metadata)
            lifecycle_rows.append(row)
        for dmp_point in trace.dmp_state_summary:
            row = _reported_value(dmp_point)
            row.update(trace_metadata)
            dmp_rows.append(row)
        if canonical_graph is None:
            canonical_graph = {
                "schema_version": trace.schema_version,
                "evidence_scope": trace.evidence_scope,
                "record_id": trace.record_id,
                "scenario_id": trace.scenario_id,
                "block": trace.block,
                "replication": trace.replication,
                "attack_trace_digest": trace.attack_trace_digest,
                **_reported_value(trace.graph),
            }

    pd.DataFrame(lifecycle_rows).to_parquet(
        trace_dir / "stage3b_lifecycle_timeseries.parquet", index=False
    )
    pd.DataFrame(dmp_rows).to_parquet(
        trace_dir / "stage3b_dmp_state_summary.parquet", index=False
    )
    write_new_json(trace_dir / "stage3b_graph_evidence.json", canonical_graph or {})
    write_new_json(
        trace_dir / "stage3b_trace_selection.json",
        {
            "schema_version": "stage3b-trace-selection-v1",
            "evidence_scope": "visualization_only_not_scientific_metric_input",
            "traces": metadata,
        },
    )
    return metadata


def execute_stage3(
    root: Path,
    *,
    mode: RunMode,
    execution_id: str,
    stage3a_replications: int,
    stage3b_replications: int,
    bootstrap_draws: int,
) -> Stage3ExecutionArtifacts:
    """Execute a pilot or a hash-gated confirmatory Stage 3 study."""

    root = root.resolve()
    protocol = _load_yaml(root / "configs/stage3/protocol.yaml")
    admission = _load_yaml(root / "configs/stage3/admission_matrix.yaml")
    compromise = _load_yaml(root / "configs/stage3/compromise_matrix.yaml")
    compute_budget = _load_yaml(root / "configs/stage3/compute_budget.yaml")
    expected_replications = {
        "pilot": (
            int(admission["replications"]["engineering_pilot"]),
            int(compromise["replications"]["engineering_pilot"]),
            int(compute_budget["engineering_pilot"]["bootstrap_draws"]),
        ),
        "confirmatory": (
            int(admission["replications"]["confirmatory"]),
            int(compromise["replications"]["confirmatory"]),
            int(compute_budget["confirmatory"]["bootstrap_draws"]),
        ),
    }[mode]
    requested_replications = (
        int(stage3a_replications),
        int(stage3b_replications),
        int(bootstrap_draws),
    )
    if requested_replications != expected_replications:
        raise ValueError(
            f"{mode} execution counts must match the frozen protocol: "
            f"Stage3A={expected_replications[0]}, Stage3B={expected_replications[1]}, "
            f"bootstrap={expected_replications[2]}"
        )
    selected_budget = _runtime_budget(
        compute_budget["engineering_pilot" if mode == "pilot" else "confirmatory"]
    )
    seed_domains = protocol["seed_domains"][mode]
    bootstrap_seed_bases = protocol["bootstrap_seed_bases"]
    stage3a_bootstrap_seed = _domain_seed(
        int(bootstrap_seed_bases["stage3a"]), str(seed_domains["stage3a_bootstrap"])
    )
    stage3b_bootstrap_seed = _domain_seed(
        int(bootstrap_seed_bases["stage3b"]), str(seed_domains["stage3b_bootstrap"])
    )
    seeds = _seed_table(root, protocol)
    checks: list[Any] = []
    engineering_input_snapshot: dict[str, Any] | None = None
    execution_contract: dict[str, Any]
    if mode == "confirmatory":
        manifest = load_preexecution_manifest(
            root / "manifests/stage3_preexecution_manifest.json"
        )
        require_frozen_environment(manifest)
        if manifest.get("protocol_status") != "frozen_before_confirmatory_execution":
            raise ValueError("confirmatory manifest is not in the frozen protocol state")
        if manifest.get("protocol_id") != protocol["protocol_id"]:
            raise ValueError("confirmatory manifest protocol_id does not match configuration")
        if manifest.get("evidence_scope") != protocol["evidence_scope"]:
            raise ValueError("confirmatory manifest evidence_scope does not match configuration")
        raw_contract = manifest.get("execution_contract")
        if not isinstance(raw_contract, dict):
            raise ValueError("confirmatory manifest lacks an execution contract")
        execution_contract = raw_contract
        contracted_counts = (
            int(execution_contract["stage3a_replications_per_scenario"]),
            int(execution_contract["stage3b_replications_per_scenario"]),
            int(execution_contract["bootstrap_draws"]),
        )
        if execution_contract.get("execution_id") != execution_id:
            raise ValueError("execution_id does not match the frozen execution contract")
        if contracted_counts != requested_replications:
            raise ValueError("execution counts do not match the frozen execution contract")
        if execution_contract.get("seed_domains") != seed_domains:
            raise ValueError("seed domains do not match the frozen execution contract")
        if execution_contract.get("bootstrap_seed_bases") != bootstrap_seed_bases:
            raise ValueError(
                "bootstrap seed bases do not match the frozen execution contract"
            )
        manifest_files = manifest.get("files")
        if not isinstance(manifest_files, dict):
            raise TypeError("confirmatory manifest files must be an object")
        if set(manifest_files) != _expanded_frozen_files(root, protocol):
            raise ValueError("confirmatory manifest file set does not match protocol inputs")
        contracted_command = execution_contract.get("command_argv")
        if not isinstance(contracted_command, list) or not all(
            isinstance(value, str) for value in contracted_command
        ):
            raise TypeError("confirmatory command_argv must be a list of strings")
        if _resolved_command(root, contracted_command) != _resolved_command(
            root, (sys.executable, *sys.argv)
        ):
            raise ValueError("actual command does not match the frozen execution contract")
        checks = require_frozen_inputs(root, manifest)
        protocol_hash = str(manifest["protocol_hash"])
    elif mode == "pilot":
        protocol_hash = "engineering-pilots"
        engineering_input_snapshot = {
            "status": "engineering_only_nonauthoritative_input_snapshot",
            "environment": environment_snapshot(),
            "files": {
                path: sha256_file(root / path)
                for path in sorted(_expanded_frozen_files(root, protocol))
            },
        }
        execution_contract = {
            "execution_id": execution_id,
            "stage3a_replications_per_scenario": stage3a_replications,
            "stage3b_replications_per_scenario": stage3b_replications,
            "bootstrap_draws": bootstrap_draws,
            "status": "engineering_pilot_excluded_from_confirmation",
        }
    else:
        raise ValueError(f"unsupported Stage 3 mode: {mode}")
    boundary_audit = _load_boundary_audit(root)
    execution_dir = reserve_execution_directory(
        root, protocol_hash=protocol_hash, execution_id=execution_id
    )
    started_utc = datetime.now(UTC).isoformat()
    started_wall = perf_counter()
    started_cpu = process_time()
    write_new_json(
        execution_dir / "execution_started.json",
        {
            "schema_version": "1.0",
            "protocol_id": protocol["protocol_id"],
            "protocol_hash": protocol_hash,
            "execution_id": execution_id,
            "mode": mode,
            "status": "started",
            "started_utc": started_utc,
            "actual_command_argv": [sys.executable, *sys.argv],
            "environment": environment_snapshot(),
            "runtime_budget": _json_value(selected_budget),
        },
    )

    stage3a_root = execution_dir / "stage3a"
    stage3a_frames: list[pd.DataFrame] = []
    for block in range(int(protocol["partitions"]["independent_blocks"])):
        for partition in ("training", "calibration", "held_out"):
            scenarios = build_stage3a_scenarios(
                protocol, admission, block=block, partition=partition
            )
            seed = _domain_seed(
                int(_seed_row(seeds, block, partition).replication_seed),
                str(seed_domains["stage3a"]),
            )
            artifacts = run_stage3a(
                scenarios,
                stage3a_root / f"block-{block}" / partition,
                root_seed=seed,
                replications=stage3a_replications,
                resource_factory=_stage3a_resource_factory,
                trace_replications_per_scenario=1,
                maximum_trace_rows=25_000,
            )
            stage3a_frames.append(pd.read_parquet(artifacts.raw_replications_path))
            _enforce_runtime_budget(
                execution_dir,
                started_wall=started_wall,
                budget=selected_budget,
                checkpoint=f"stage3a-block-{block}-{partition}",
                inspect_output=True,
            )
    stage3a_raw = pd.concat(stage3a_frames, ignore_index=True)
    stage3a_predictions, stage3a_summary = analyze_stage3a(
        stage3a_raw,
        acceptance=admission["acceptance"],
        bootstrap_seed=stage3a_bootstrap_seed,
        bootstrap_draws=bootstrap_draws,
    )
    if mode == "pilot":
        stage3a_summary["diagnostic_disposition_if_confirmatory_rule_applied"] = (
            stage3a_summary["disposition"]
        )
        stage3a_summary["disposition"] = "not_adjudicated_engineering_pilot"
        stage3a_summary["criteria_evidence_use"] = "engineering_diagnostic_only"
    derived_dir = execution_dir / "derived"
    raw_dir = execution_dir / "raw"
    derived_dir.mkdir()
    raw_dir.mkdir()
    stage3a_raw_path = raw_dir / "stage3a_replications.parquet"
    stage3a_predictions_path = derived_dir / "stage3a_heldout_predictions.parquet"
    stage3a_raw.to_parquet(stage3a_raw_path, index=False)
    stage3a_predictions.to_parquet(stage3a_predictions_path, index=False)

    stage3b_specs = build_stage3b_specs(
        protocol,
        compromise,
        seeds,
        replications=stage3b_replications,
        seed_domain=str(seed_domains["stage3b"]),
    )
    stage3b_specifications_path = raw_dir / "stage3b_scenario_specifications.parquet"
    pd.DataFrame([_reported_value(spec) for spec in stage3b_specs]).to_parquet(
        stage3b_specifications_path, index=False
    )
    checkpoint_dir = execution_dir / "checkpoints/stage3b"
    checkpoint_dir.mkdir(parents=True)
    attack_config = AttackTraceConfig(
        horizon_steps=int(compromise["horizon_steps"]),
        mean_out_degree=int(compromise["mean_out_degree"]),
        outbreak_fraction=float(compromise["outbreak_threshold_fraction"]),
    )
    dmp_config = DMPConfig(
        horizon_steps=int(compromise["horizon_steps"]),
        outbreak_fraction=float(compromise["outbreak_threshold_fraction"]),
        capture_steps=(0, int(compromise["horizon_steps"]) // 2, int(compromise["horizon_steps"])),
    )
    stage3b_records_in_memory: list[PhaseSeparatedRecord] = []
    for spec_index, spec in enumerate(stage3b_specs, start=1):
        try:
            scenario_records = build_stage3b_records(
                (spec,),
                attack_config=attack_config,
                dmp_config=dmp_config,
            )
            stage3b_records_in_memory.extend(scenario_records)
            _stage3b_records_frame(scenario_records).to_parquet(
                checkpoint_dir / f"scenario-{spec_index:03d}.parquet",
                index=False,
            )
        except Exception as exc:
            write_new_json(
                raw_dir / f"stage3b_failed_scenario_{spec_index:03d}.json",
                {
                    "scenario_id": spec.scenario_id,
                    "specification": _json_value(spec),
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                },
            )
            raise
        _enforce_runtime_budget(
            execution_dir,
            started_wall=started_wall,
            budget=selected_budget,
            checkpoint=f"stage3b-scenario-{spec_index}-of-{len(stage3b_specs)}",
            inspect_output=True,
        )
    stage3b_result = fit_and_evaluate_stage3b(stage3b_records_in_memory)
    stage3b_records = _stage3b_records_frame(stage3b_result)
    stage3b_predictions = _stage3b_predictions_frame(stage3b_result)
    stage3b_summary = analyze_stage3b(
        stage3b_result,
        stage3b_predictions,
        acceptance=compromise["acceptance"],
        bootstrap_seed=stage3b_bootstrap_seed,
        bootstrap_draws=bootstrap_draws,
        boundary_audit=boundary_audit,
    )
    if mode == "pilot":
        stage3b_summary["diagnostic_disposition_if_confirmatory_rule_applied"] = (
            stage3b_summary["disposition"]
        )
        stage3b_summary["disposition"] = "not_adjudicated_engineering_pilot"
        stage3b_summary["criteria_evidence_use"] = "engineering_diagnostic_only"
    stage3b_records_path = raw_dir / "stage3b_replications.parquet"
    stage3b_predictions_path = derived_dir / "stage3b_heldout_predictions.parquet"
    stage3b_records.to_parquet(stage3b_records_path, index=False)
    stage3b_predictions.to_parquet(stage3b_predictions_path, index=False)
    trace_metadata = _write_stage3b_console_traces(
        execution_dir,
        stage3b_specs,
        attack_config=attack_config,
        dmp_config=dmp_config,
        execution_config=compute_budget["execution"],
    )
    stage3b_summary["visualization_trace_artifacts"] = trace_metadata
    _enforce_runtime_budget(
        execution_dir,
        started_wall=started_wall,
        budget=selected_budget,
        checkpoint="post-analysis",
        inspect_output=True,
    )

    ended_wall = perf_counter()
    ended_cpu = process_time()
    evidence = {
        "schema_version": "1.0",
        "protocol": {
            "protocol_id": protocol["protocol_id"],
            "protocol_hash": protocol_hash,
            "frozen_input_checks": checks_as_dicts(checks),
            "execution_contract": execution_contract,
            "seed_domains": _json_value(seed_domains),
            "bootstrap_seeds": {
                "stage3a": stage3a_bootstrap_seed,
                "stage3b_final_size": stage3b_bootstrap_seed,
                "stage3b_outbreak_brier": stage3b_bootstrap_seed + 1,
            },
            "declared_evidence_scope": protocol["evidence_scope"],
            "engineering_input_snapshot": engineering_input_snapshot,
        },
        "execution": {
            "execution_id": execution_id,
            "mode": mode,
            "started_utc": started_utc,
            "completed_utc": datetime.now(UTC).isoformat(),
            "wall_clock_seconds": ended_wall - started_wall,
            "cpu_seconds": ended_cpu - started_cpu,
            "peak_rss_mb": _peak_rss_mb(),
            "output_mb_before_evidence": _directory_size_mb(execution_dir),
            "runtime_budget": _json_value(selected_budget),
            "environment": environment_snapshot(),
            "actual_command_argv": [sys.executable, *sys.argv],
        },
        "evidence_scope": (
            protocol["evidence_scope"]
            if mode == "confirmatory"
            else "engineering_pilot_excluded_from_confirmation"
        ),
        "negative_results_preserved": protocol["negative_results_preserved"],
        "stage3a": stage3a_summary,
        "stage3b": stage3b_summary,
        "limitations": [
            "All outcomes in this execution are synthetic and model-conditioned.",
            "The calibration interface used only the included synthetic template.",
            "No result establishes implementation security or deployment assurance.",
            "The attack generator is a separate implementation with a bounded observed view, not external operational evidence.",
        ],
    }
    evidence_path = execution_dir / "stage3_evidence.json"
    write_new_json(evidence_path, _json_value(evidence))
    manifest_payload = {
        "schema_version": "1.0",
        "protocol_id": protocol["protocol_id"],
        "protocol_hash": protocol_hash,
        "execution_id": execution_id,
        "mode": mode,
        "status": "completed",
        "started_utc": started_utc,
        "completed_utc": datetime.now(UTC).isoformat(),
        "frozen_input_checks": checks_as_dicts(checks),
        "actual_command_argv": [sys.executable, *sys.argv],
        "artifacts": artifact_inventory(execution_dir, root=root),
    }
    execution_manifest_path = execution_dir / "execution_manifest.json"
    write_new_json(execution_manifest_path, manifest_payload)
    return Stage3ExecutionArtifacts(
        execution_dir=execution_dir,
        evidence_path=evidence_path,
        execution_manifest_path=execution_manifest_path,
        stage3a_predictions_path=stage3a_predictions_path,
        stage3b_records_path=stage3b_records_path,
        stage3b_predictions_path=stage3b_predictions_path,
    )


__all__ = [
    "Stage3ExecutionArtifacts",
    "analyze_stage3a",
    "analyze_stage3b",
    "build_stage3a_scenarios",
    "build_stage3b_specs",
    "execute_stage3",
]
