"""Read-only Stage 3 evidence loading and self-contained console export.

The console has no scientific authority. Replay and comparison modes consume
completed execution directories without modifying them. Live mode first creates
a bounded, immutable synthetic demonstration run, then animates its captured
evidence. It never streams or mutates a simulation while it is executing.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from plotly.offline.offline import get_plotlyjs

ConsoleMode = Literal["live", "replay", "comparison"]

ADMISSION_PATTERNS = (
    "step",
    "linear",
    "staged",
    "exponential",
    "bursty",
    "periodic",
    "closed_loop",
    "sybil",
    "mass_restart",
    "mass_renewal",
)
TOPOLOGIES = (
    "random_regular",
    "erdos_renyi",
    "barabasi_albert",
    "hierarchical",
)
ATTACK_CLASSES = (
    "direct_exploit",
    "credential_replay",
    "delegated_authority",
    "shared_dependency",
    "shared_image",
    "identity_provider",
    "mixed",
)
INJECTIONS = (
    "none",
    "sybil",
    "mass_restart",
    "mass_renewal",
    "common_cause",
    "boundary_failure",
    "network_partition",
)


@dataclass(frozen=True, slots=True)
class ConsoleLimits:
    """Resource limits for one portable evidence payload."""

    max_table_rows: int = 12_000
    max_trace_rows: int = 50_000
    max_graph_nodes: int = 500
    max_graph_edges: int = 2_000
    max_hash_bytes: int = 256 * 1024 * 1024

    def __post_init__(self) -> None:
        values = (
            self.max_table_rows,
            self.max_trace_rows,
            self.max_graph_nodes,
            self.max_graph_edges,
            self.max_hash_bytes,
        )
        if any(value < 1 for value in values):
            raise ValueError("console limits must be positive")


@dataclass(frozen=True, slots=True)
class Stage3ScenarioConfig:
    """Bounded configuration for a synthetic visual demonstration run."""

    fleet_size: int = 100
    admission_pattern: str = "staged"
    capacity_multiplier: float = 1.0
    topology: str = "random_regular"
    attack_class: str = "credential_replay"
    injection: str = "none"
    injection_fraction: float = 0.0
    detection_delay_steps: int = 3
    quarantine_delay_steps: int = 2
    revocation_delay_steps: int = 2
    admission_duration_s: float = 30.0
    recovery_window_s: float = 15.0
    horizon_steps: int = 20
    seed: int = 320260819

    def __post_init__(self) -> None:
        if not 10 <= self.fleet_size <= 2_000:
            raise ValueError("visual live fleet_size must be between 10 and 2000")
        if self.admission_pattern not in ADMISSION_PATTERNS:
            raise ValueError(f"unsupported admission_pattern: {self.admission_pattern}")
        if self.topology not in TOPOLOGIES:
            raise ValueError(f"unsupported topology: {self.topology}")
        if self.attack_class not in ATTACK_CLASSES:
            raise ValueError(f"unsupported attack_class: {self.attack_class}")
        if self.injection not in INJECTIONS:
            raise ValueError(f"unsupported injection: {self.injection}")
        if not math.isfinite(self.capacity_multiplier) or not 0.50 <= self.capacity_multiplier <= 1.50:
            raise ValueError("capacity_multiplier must be within [0.50, 1.50]")
        if not math.isfinite(self.injection_fraction) or not 0.0 <= self.injection_fraction <= 0.25:
            raise ValueError("injection_fraction must be within [0.0, 0.25]")
        for name in (
            "detection_delay_steps",
            "quarantine_delay_steps",
            "revocation_delay_steps",
        ):
            value = int(getattr(self, name))
            if not 0 <= value <= 20:
                raise ValueError(f"{name} must be within [0, 20]")
        if not 5.0 <= self.admission_duration_s <= 300.0:
            raise ValueError("admission_duration_s must be within [5, 300]")
        if not 0.0 <= self.recovery_window_s <= 300.0:
            raise ValueError("recovery_window_s must be within [0, 300]")
        if not 3 <= self.horizon_steps <= 120:
            raise ValueError("horizon_steps must be within [3, 120]")
        if not 0 <= self.seed < 2**63:
            raise ValueError("seed must be a nonnegative signed 64-bit integer")
        if self.injection == "none" and self.injection_fraction != 0.0:
            raise ValueError("injection_fraction must be zero when injection is none")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> Stage3ScenarioConfig:
        allowed = set(cls.__dataclass_fields__)
        unknown = set(value).difference(allowed)
        if unknown:
            raise ValueError(f"unknown scenario fields: {sorted(unknown)}")
        return cls(**dict(value))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Stage3ConsoleBundle:
    """Portable, JSON-safe projection of one immutable execution."""

    execution_dir: Path
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _BoundedFrame:
    frame: pd.DataFrame
    source_rows: int
    representation: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _safe_json(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return [_safe_json(item) for item in value.tolist()]
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_safe_json(item) for item in value]
    if pd.isna(value):
        return None
    return str(value)


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [_safe_json(row) for row in frame.to_dict(orient="records")]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON root must be an object: {path}")
    return value


def _sample_frame(frame: pd.DataFrame, maximum_rows: int) -> pd.DataFrame:
    if len(frame) <= maximum_rows:
        return frame.reset_index(drop=True)
    working = frame.reset_index(drop=True)
    retained: set[int] = {0, len(working) - 1}
    if "scenario_id" in working:
        groups = ["scenario_id"]
        if "resource_id" in working:
            groups.append("resource_id")
        if "replication" in working:
            groups.append("replication")
        for _, group in working.groupby(groups, sort=False, dropna=False):
            retained.add(int(group.index[0]))
            retained.add(int(group.index[-1]))
            for column in (
                "maximum_observed_omega",
                "projected_maximum_omega",
                "omega_observed",
                "projected_omega",
            ):
                if column in group and group[column].notna().any():
                    retained.add(int(group[column].astype(float).idxmax()))
                    crossing = group.index[group[column].astype(float) >= 1.0]
                    if len(crossing):
                        retained.add(int(crossing[0]))
    if len(retained) > maximum_rows:
        retained = set(
            np.asarray(sorted(retained))[np.linspace(0, len(retained) - 1, maximum_rows, dtype=int)]
        )
    remaining_budget = maximum_rows - len(retained)
    if remaining_budget > 0:
        candidates = np.asarray(sorted(set(range(len(working))).difference(retained)), dtype=int)
        if len(candidates):
            positions = np.linspace(
                0,
                len(candidates) - 1,
                min(remaining_budget, len(candidates)),
                dtype=int,
            )
            retained.update(int(candidates[position]) for position in positions)
    return working.iloc[sorted(retained)[:maximum_rows]].reset_index(drop=True)


def _read_parquet_bounded(path: Path, maximum_rows: int) -> _BoundedFrame:
    try:
        from pyarrow import parquet
    except ImportError:
        frame = pd.read_parquet(path)
        source_rows = len(frame)
        sampled = _sample_frame(frame, maximum_rows)
        return _BoundedFrame(
            sampled,
            source_rows,
            "exact" if source_rows <= maximum_rows else "sampled",
        )

    parquet_file = parquet.ParquetFile(path)
    source_rows = int(parquet_file.metadata.num_rows)
    if source_rows <= maximum_rows:
        frame = parquet_file.read().to_pandas()
        return _BoundedFrame(frame.reset_index(drop=True), source_rows, "exact")

    row_groups = parquet_file.num_row_groups
    mean_group_rows = max(1, math.ceil(source_rows / max(1, row_groups)))
    group_budget = max(1, math.ceil(maximum_rows / mean_group_rows))
    selected = np.unique(
        np.linspace(0, row_groups - 1, min(row_groups, group_budget), dtype=int)
    ).tolist()
    frame = parquet_file.read_row_groups(selected).to_pandas()
    return _BoundedFrame(_sample_frame(frame, maximum_rows), source_rows, "sampled")


def _first_existing(root: Path, names: Sequence[str]) -> Path | None:
    for name in names:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def _merge_parquet_files(
    paths: Sequence[Path],
    *,
    maximum_rows: int,
) -> tuple[pd.DataFrame, str, int]:
    if not paths:
        return pd.DataFrame(), "not_retained", 0
    per_file = max(100, maximum_rows // len(paths))
    frames: list[pd.DataFrame] = []
    source_rows = 0
    sampled = False
    for path in paths:
        bounded = _read_parquet_bounded(path, per_file)
        source_rows += bounded.source_rows
        sampled |= bounded.representation == "sampled"
        frame = bounded.frame.copy()
        frame["console_source"] = path.name
        frames.append(frame)
    merged = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if len(merged) > maximum_rows:
        merged = _sample_frame(merged, maximum_rows)
        sampled = True
    if "representation" in merged and (merged["representation"] == "sampled").any():
        sampled = True
    return merged, ("sampled" if sampled else "exact"), source_rows


def _manifest_expected_digest(manifest: Mapping[str, Any], relative: Path) -> str | None:
    artifacts = manifest.get("artifacts", [])
    if not isinstance(artifacts, list):
        return None
    relative_parts = relative.parts
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            continue
        raw_path = artifact.get("path")
        expected = artifact.get("sha256")
        if not isinstance(raw_path, str) or not isinstance(expected, str):
            continue
        parts = Path(raw_path).parts
        if len(parts) >= len(relative_parts) and parts[-len(relative_parts) :] == relative_parts:
            return expected
    return None


def _integrity_checks(
    execution: Path,
    manifest: Mapping[str, Any] | None,
    loaded_paths: Sequence[Path],
    limits: ConsoleLimits,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    if manifest is None:
        return "manifest_missing", [], [
            "Execution manifest is absent. Evidence is displayed but integrity is unverified."
        ]
    checks: list[dict[str, Any]] = []
    for path in sorted(set(loaded_paths)):
        relative = path.relative_to(execution)
        expected = _manifest_expected_digest(manifest, relative)
        if expected is None:
            status = "not_listed"
            actual = None
        elif path.stat().st_size > limits.max_hash_bytes:
            status = "not_checked_size_limit"
            actual = None
        else:
            actual = _sha256(path)
            status = "match" if actual == expected else "mismatch"
        checks.append(
            {
                "path": relative.as_posix(),
                "bytes": path.stat().st_size,
                "expected_sha256": expected,
                "actual_sha256": actual,
                "status": status,
            }
        )
    statuses = {str(check["status"]) for check in checks}
    if "mismatch" in statuses:
        warnings.append("At least one loaded artifact digest does not match the manifest.")
        return "mismatch", checks, warnings
    if statuses and statuses == {"match"}:
        return "verified_loaded_artifacts", checks, warnings
    if "not_checked_size_limit" in statuses:
        warnings.append("Large loaded artifacts were not hashed by the console size policy.")
    if "not_listed" in statuses:
        warnings.append("At least one loaded artifact is not listed in the execution manifest.")
    return "partially_verified", checks, warnings


def _derive_wait_budgets(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    result = frame.copy()
    observed = np.full(len(result), np.nan)
    predicted = np.full(len(result), np.nan)
    if {"wait_s", "omega_observed"}.issubset(result.columns):
        wait = result["wait_s"].to_numpy(float)
        omega = result["omega_observed"].to_numpy(float)
        np.divide(wait, omega, out=observed, where=omega > 1e-12)
    if {"projected_wait_s", "projected_omega"}.issubset(result.columns):
        wait = result["projected_wait_s"].to_numpy(float)
        omega = result["projected_omega"].to_numpy(float)
        np.divide(wait, omega, out=predicted, where=omega > 1e-12)
    result["observed_wait_budget_s_derived"] = observed
    result["predicted_wait_budget_s_derived"] = predicted
    return result


_DMP_STATE_FRACTION_COLUMNS = (
    "susceptible_fraction",
    "compromised_undetected_fraction",
    "detected_fraction",
    "quarantined_fraction",
    "revoked_fraction",
    "recovered_fraction",
    "mean_edge_no_transmission",
    "mean_edge_source_active",
    "mean_common_cause_survival",
)


def _validate_dmp_state_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate retained DMP aggregates without filling or reconstructing values."""

    if frame.empty:
        return frame
    required = {
        "scenario_id",
        "step",
        "representation",
        *_DMP_STATE_FRACTION_COLUMNS,
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    scenario_ids = frame["scenario_id"].astype(str)
    if (scenario_ids.str.strip() == "").any():
        raise ValueError("scenario_id must be nonempty")
    steps = pd.to_numeric(frame["step"], errors="raise").to_numpy(float)
    if not np.isfinite(steps).all() or (steps < 0.0).any() or not np.equal(steps, np.floor(steps)).all():
        raise ValueError("step must contain finite nonnegative integers")
    values = frame[list(_DMP_STATE_FRACTION_COLUMNS)].apply(
        pd.to_numeric, errors="raise"
    ).to_numpy(float)
    if not np.isfinite(values).all() or (values < 0.0).any() or (values > 1.0).any():
        raise ValueError("DMP state fractions and means must be finite values in [0, 1]")
    representations = set(frame["representation"].astype(str))
    if representations != {"estimated_dmp_aggregate"}:
        raise ValueError(
            "DMP state summary representation must be estimated_dmp_aggregate"
        )
    return frame


def _visual_dmp_state_summary(dmp: Any, scenario_id: str) -> pd.DataFrame:
    """Materialize display-only DMP aggregates for one completed visual run."""

    def mean_or(values: np.ndarray, fallback: float) -> float:
        array = np.asarray(values, dtype=float)
        return float(np.mean(array)) if array.size else fallback

    rows: list[dict[str, Any]] = []
    for state in dmp.states:
        rows.append(
            {
                "record_id": f"{scenario_id}:r0",
                "scenario_id": scenario_id,
                "block": 0,
                "replication": 0,
                "step": int(state.step),
                "susceptible_fraction": float(np.mean(state.node_susceptible)),
                "compromised_undetected_fraction": float(
                    np.mean(state.node_compromised_undetected)
                ),
                "detected_fraction": float(np.mean(state.node_detected)),
                "quarantined_fraction": float(np.mean(state.node_quarantined)),
                "revoked_fraction": float(np.mean(state.node_revoked)),
                "recovered_fraction": float(np.mean(state.node_recovered)),
                "mean_edge_no_transmission": mean_or(
                    state.edge_no_transmission, 1.0
                ),
                "mean_edge_source_active": mean_or(state.edge_source_active, 0.0),
                "mean_common_cause_survival": float(
                    np.mean(state.common_cause_survival)
                ),
                "representation": "estimated_dmp_aggregate",
            }
        )
    return _validate_dmp_state_summary(pd.DataFrame(rows))


def _load_optional_graph(path: Path, limits: ConsoleLimits) -> tuple[dict[str, Any], str]:
    graph = _read_json(path)
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise TypeError(f"graph evidence must contain node and edge lists: {path}")
    representation = str(graph.get("representation", "exact"))
    if len(nodes) > limits.max_graph_nodes:
        positions = np.linspace(0, len(nodes) - 1, limits.max_graph_nodes, dtype=int)
        nodes = [nodes[int(position)] for position in positions]
        allowed = {str(node.get("id")) for node in nodes if isinstance(node, Mapping)}
        edges = [
            edge
            for edge in edges
            if isinstance(edge, Mapping)
            and str(edge.get("source")) in allowed
            and str(edge.get("target")) in allowed
        ]
        representation = "sampled"
    if len(edges) > limits.max_graph_edges:
        positions = np.linspace(0, len(edges) - 1, limits.max_graph_edges, dtype=int)
        edges = [edges[int(position)] for position in positions]
        representation = "sampled"
    output = dict(graph)
    output["nodes"] = nodes
    output["edges"] = edges
    output["representation"] = representation
    return _safe_json(output), representation


def load_stage3_execution(
    execution_dir: str | Path,
    *,
    limits: ConsoleLimits | None = None,
) -> Stage3ConsoleBundle:
    """Load one execution without writing to it and build a bounded payload."""

    policy = limits or ConsoleLimits()
    execution = Path(execution_dir).resolve()
    if not execution.is_dir():
        raise FileNotFoundError(execution)
    evidence_path = execution / "stage3_evidence.json"
    if not evidence_path.is_file():
        raise FileNotFoundError(f"Stage 3 evidence is missing: {evidence_path}")
    evidence = _read_json(evidence_path)
    manifest_path = execution / "execution_manifest.json"
    manifest = _read_json(manifest_path) if manifest_path.is_file() else None
    warnings: list[str] = []
    loaded_paths: list[Path] = [evidence_path]

    table_specs = {
        "stage3a_replications": (
            "raw/stage3a_replications.parquet",
            "stage3a/raw/stage3a_replications.parquet",
        ),
        "stage3a_predictions": ("derived/stage3a_heldout_predictions.parquet",),
        "stage3b_records": ("raw/stage3b_replications.parquet",),
        "stage3b_predictions": ("derived/stage3b_heldout_predictions.parquet",),
    }
    tables: dict[str, list[dict[str, Any]]] = {}
    table_meta: dict[str, dict[str, Any]] = {}
    for key, candidates in table_specs.items():
        path = _first_existing(execution, candidates)
        if path is None:
            tables[key] = []
            table_meta[key] = {"representation": "not_retained", "source_rows": 0}
            warnings.append(f"Optional table not retained: {candidates[0]}")
            continue
        try:
            bounded = _read_parquet_bounded(path, policy.max_table_rows)
        except Exception as exc:  # noqa: BLE001 - optional evidence must degrade explicitly.
            tables[key] = []
            table_meta[key] = {"representation": "unavailable", "source_rows": None}
            warnings.append(f"Could not read {path.name}: {type(exc).__name__}: {exc}")
            continue
        loaded_paths.append(path)
        tables[key] = _records(bounded.frame)
        table_meta[key] = {
            "path": path.relative_to(execution).as_posix(),
            "representation": bounded.representation,
            "source_rows": bounded.source_rows,
            "retained_rows": len(bounded.frame),
        }

    admission_paths = sorted(
        set(execution.rglob("stage3a_admission_timeseries.parquet"))
    )
    resource_paths = sorted(
        set(execution.rglob("stage3a_resource_timeseries.parquet"))
    )
    try:
        admission, admission_representation, admission_source_rows = _merge_parquet_files(
            admission_paths, maximum_rows=policy.max_trace_rows
        )
    except Exception as exc:  # noqa: BLE001 - optional evidence must degrade explicitly.
        admission = pd.DataFrame()
        admission_representation = "unavailable"
        admission_source_rows = 0
        warnings.append(f"Stage 3A admission traces could not be read: {type(exc).__name__}: {exc}")
    try:
        resource, resource_representation, resource_source_rows = _merge_parquet_files(
            resource_paths, maximum_rows=policy.max_trace_rows
        )
        resource = _derive_wait_budgets(resource)
    except Exception as exc:  # noqa: BLE001 - optional evidence must degrade explicitly.
        resource = pd.DataFrame()
        resource_representation = "unavailable"
        resource_source_rows = 0
        warnings.append(f"Stage 3A resource traces could not be read: {type(exc).__name__}: {exc}")
    loaded_paths.extend(admission_paths)
    loaded_paths.extend(resource_paths)
    if admission.empty:
        warnings.append(
            "Stage 3A admission time trace was not retained; admission and fleet animation is unavailable."
        )
    if resource.empty:
        warnings.append(
            "Stage 3A resource time trace was not retained; queue, wait-budget, and Omega animation is unavailable."
        )

    lifecycle_candidates = sorted(
        {
            *execution.rglob("stage3b_lifecycle_timeseries.parquet"),
            *execution.rglob("stage3b_attack_lifecycle.parquet"),
        }
    )
    try:
        lifecycle, lifecycle_representation, lifecycle_source_rows = _merge_parquet_files(
            lifecycle_candidates,
            maximum_rows=policy.max_trace_rows,
        )
    except Exception as exc:  # noqa: BLE001 - optional evidence must degrade explicitly.
        lifecycle = pd.DataFrame()
        lifecycle_representation = "unavailable"
        lifecycle_source_rows = 0
        warnings.append(f"Stage 3B lifecycle traces could not be read: {type(exc).__name__}: {exc}")
    loaded_paths.extend(lifecycle_candidates)
    if lifecycle.empty:
        warnings.append(
            "Stage 3B lifecycle trace was not retained; detection, quarantine, revocation, and event animation is unavailable."
        )

    dmp_state_paths = sorted(
        set(execution.rglob("stage3b_dmp_state_summary.parquet"))
    )
    try:
        dmp_state, dmp_state_retention, dmp_state_source_rows = _merge_parquet_files(
            dmp_state_paths,
            maximum_rows=policy.max_trace_rows,
        )
        dmp_state = _validate_dmp_state_summary(dmp_state)
    except Exception as exc:  # noqa: BLE001 - optional evidence must degrade explicitly.
        dmp_state = pd.DataFrame()
        dmp_state_retention = "unavailable"
        dmp_state_source_rows = 0
        warnings.append(
            f"Stage 3B DMP state summaries could not be read: {type(exc).__name__}: {exc}"
        )
    loaded_paths.extend(dmp_state_paths)
    if dmp_state.empty:
        warnings.append(
            "Stage 3B DMP state summary was not retained; node-state, edge-message, and common-cause views are unavailable and are not inferred."
        )

    graph_path = _first_existing(
        execution,
        (
            "stage3b/traces/stage3b_graph_evidence.json",
            "stage3b_graph_evidence.json",
        ),
    )
    graph: dict[str, Any] | None = None
    graph_representation = "not_retained"
    if graph_path is not None:
        try:
            graph, graph_representation = _load_optional_graph(graph_path, policy)
            loaded_paths.append(graph_path)
        except Exception as exc:  # noqa: BLE001 - optional evidence must degrade explicitly.
            warnings.append(f"Stage 3B graph evidence could not be read: {type(exc).__name__}: {exc}")
    if graph is None:
        warnings.append(
            "Stage 3B graph state was not retained; scalar graph and DMP features are shown when available."
        )

    trace_scenario_ids = sorted(
        {
            str(value)
            for frame in (lifecycle, dmp_state)
            if "scenario_id" in frame
            for value in frame["scenario_id"].dropna()
            if str(value).strip()
        }
    )
    trace_scenario_set = set(trace_scenario_ids)
    summary_scenario_ids = sorted(
        {
            str(row["scenario_id"])
            for key in ("stage3b_records", "stage3b_predictions")
            for row in tables[key]
            if row.get("scenario_id") is not None
            and str(row["scenario_id"]).strip()
            and str(row["scenario_id"]) not in trace_scenario_set
        }
    )
    selector_scenario_ids = [*trace_scenario_ids, *summary_scenario_ids]

    integrity, checks, integrity_warnings = _integrity_checks(
        execution, manifest, loaded_paths, policy
    )
    warnings.extend(integrity_warnings)
    execution_meta = evidence.get("execution", {})
    protocol_meta = evidence.get("protocol", {})
    payload = {
        "schema_version": "stage3-console-bundle-v1",
        "execution": {
            "execution_id": execution_meta.get("execution_id", execution.name),
            "mode": execution_meta.get("mode", "unknown"),
            "completed_utc": execution_meta.get("completed_utc"),
            "protocol_id": protocol_meta.get("protocol_id"),
            "protocol_hash": protocol_meta.get("protocol_hash"),
            "evidence_scope": evidence.get("evidence_scope", "unknown"),
            "integrity": integrity,
            "source_directory_name": execution.name,
        },
        "evidence": _safe_json(evidence),
        "manifest": _safe_json(manifest) if manifest is not None else None,
        "integrity_checks": checks,
        "warnings": sorted(set(warnings)),
        "availability": {
            "stage3a_admission_trace": not admission.empty,
            "stage3a_resource_trace": not resource.empty,
            "stage3b_lifecycle_trace": not lifecycle.empty,
            "stage3b_dmp_state_summary": not dmp_state.empty,
            "stage3b_graph": graph is not None,
        },
        "stage3a": {
            "replications": tables["stage3a_replications"],
            "predictions": tables["stage3a_predictions"],
            "admission_trace": _records(admission),
            "resource_trace": _records(resource),
            "representations": {
                "replications": table_meta["stage3a_replications"],
                "predictions": table_meta["stage3a_predictions"],
                "admission_trace": {
                    "representation": admission_representation,
                    "source_rows": admission_source_rows,
                    "retained_rows": len(admission),
                },
                "resource_trace": {
                    "representation": resource_representation,
                    "source_rows": resource_source_rows,
                    "retained_rows": len(resource),
                    "wait_budget": "derived_from_retained_wait_and_omega",
                },
            },
        },
        "stage3b": {
            "records": tables["stage3b_records"],
            "predictions": tables["stage3b_predictions"],
            "lifecycle_trace": _records(lifecycle),
            "dmp_state_summary": _records(dmp_state),
            "trace_scenario_ids": trace_scenario_ids,
            "selector_scenario_ids": selector_scenario_ids,
            "graph_scenario_id": (
                str(graph.get("scenario_id"))
                if graph is not None and graph.get("scenario_id") is not None
                else None
            ),
            "graph": graph,
            "representations": {
                "records": table_meta["stage3b_records"],
                "predictions": table_meta["stage3b_predictions"],
                "lifecycle_trace": {
                    "representation": lifecycle_representation,
                    "source_rows": lifecycle_source_rows,
                    "retained_rows": len(lifecycle),
                },
                "dmp_state_summary": {
                    "representation": (
                        "estimated" if not dmp_state.empty else dmp_state_retention
                    ),
                    "retention": dmp_state_retention,
                    "source_rows": dmp_state_source_rows,
                    "retained_rows": len(dmp_state),
                    "source_representation": (
                        "estimated_dmp_aggregate" if not dmp_state.empty else None
                    ),
                },
                "graph": graph_representation,
                "dmp": "estimated",
                "outcomes": "observed_within_simulation",
            },
        },
    }
    return Stage3ConsoleBundle(execution, _safe_json(payload))


def discover_stage3_executions(root: str | Path) -> list[Path]:
    """Return completed or partial Stage 3 evidence directories, newest first."""

    base = Path(root)
    if not base.exists():
        return []
    candidates = {
        path.parent.resolve() for path in base.rglob("stage3_evidence.json") if path.is_file()
    }
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)


def write_scenario_request(
    config: Stage3ScenarioConfig,
    destination: str | Path,
) -> Path:
    """Write a bounded run request without executing or mutating any run."""

    path = Path(destination)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite scenario request: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "stage3-visual-scenario-request-v1",
        "action": "create_new_immutable_visual_demonstration",
        "evidence_scope": "synthetic_model_demonstration_only",
        "configuration": config.to_dict(),
        "limits": {
            "maximum_fleet_size": 2_000,
            "maximum_injection_fraction": 0.25,
            "maximum_horizon_steps": 120,
        },
        "limitations": [
            "This request is not a confirmatory protocol input.",
            "The console cannot modify an existing or active execution.",
        ],
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def _graph_projection(view: Any, limits: ConsoleLimits) -> dict[str, Any]:
    n = int(view.n)
    node_count = min(n, limits.max_graph_nodes)
    selected = np.unique(np.linspace(0, n - 1, node_count, dtype=int))
    selected_set = {int(value) for value in selected}
    angles = np.linspace(0.0, 2.0 * math.pi, len(selected), endpoint=False)
    nodes = [
        {
            "id": int(node),
            "x": float(math.cos(float(angle))),
            "y": float(math.sin(float(angle))),
            "segment": int(view.segment_ids[node]),
            "initial_probability": float(view.initial_compromise_probability[node]),
        }
        for node, angle in zip(selected, angles)
    ]
    edges: list[dict[str, Any]] = []
    for layer_name, matrix in view.layers.items():
        layer_rows: np.ndarray = np.repeat(
            np.arange(n, dtype=np.int64), np.diff(matrix.indptr)
        )
        for source, target in zip(layer_rows, matrix.indices):
            if int(source) in selected_set and int(target) in selected_set:
                edges.append(
                    {
                        "source": int(source),
                        "target": int(target),
                        "layer": str(layer_name),
                    }
                )
    representation = "exact"
    if n > len(selected) or len(edges) > limits.max_graph_edges:
        representation = "sampled"
    if len(edges) > limits.max_graph_edges:
        positions = np.linspace(0, len(edges) - 1, limits.max_graph_edges, dtype=int)
        edges = [edges[int(position)] for position in positions]
    return {
        "nodes": nodes,
        "edges": edges,
        "source_node_count": n,
        "source_edge_count": int(sum(matrix.nnz for matrix in view.layers.values())),
        "representation": representation,
        "orientation": "row_source_column_target",
    }


def _attack_lifecycle(trace: Any, dmp: Any, scenario_id: str, n: int) -> pd.DataFrame:
    state_by_step = {int(state.step): state for state in dmp.states}
    rows: list[dict[str, Any]] = []
    horizon = max(state_by_step)
    for step in range(horizon + 1):
        state = state_by_step.get(step)
        if state is None:
            preceding = max(value for value in state_by_step if value <= step)
            state = state_by_step[preceding]
        compromise = np.asarray(trace.compromise_step)
        detection = np.asarray(trace.detection_step)
        quarantine = np.asarray(trace.quarantine_step)
        revocation = np.asarray(trace.revocation_step)
        recovery = np.asarray(trace.recovery_step)
        rows.append(
            {
                "scenario_id": scenario_id,
                "step": step,
                "observed_ever_compromised_fraction": float(np.mean((compromise >= 0) & (compromise <= step))),
                "observed_detected_fraction": float(np.mean(detection <= step)),
                "observed_quarantined_fraction": float(np.mean(quarantine <= step)),
                "observed_revoked_fraction": float(np.mean(revocation <= step)),
                "observed_recovered_fraction": float(np.mean(recovery <= step)),
                "predicted_ever_compromised_fraction": float(
                    np.mean(1.0 - np.asarray(state.node_susceptible))
                ),
                "predicted_detected_fraction": float(np.mean(state.node_detected)),
                "predicted_quarantined_fraction": float(np.mean(state.node_quarantined)),
                "predicted_revoked_fraction": float(np.mean(state.node_revoked)),
                "predicted_recovered_fraction": float(np.mean(state.node_recovered)),
                "representation": "exact_observed_and_estimated_dmp",
                "n_agents": n,
            }
        )
    return pd.DataFrame(rows)


def run_visual_scenario(
    config: Stage3ScenarioConfig,
    output_dir: str | Path,
    *,
    limits: ConsoleLimits | None = None,
) -> Path:
    """Create one immutable synthetic demonstration, then return its directory."""

    from fleet_sim.control_plane.resource_network import AdmissionPattern
    from fleet_sim.experiments.stage3a import Stage3AScenario, run_stage3a
    from fleet_sim.experiments.stage3b import scenario_predictor_features
    from fleet_sim.security.attack_trace import LAYER_NAMES, AttackTraceConfig, AttackTraceGenerator
    from fleet_sim.security.dynamic_message_passing import DMPConfig

    policy = limits or ConsoleLimits()
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite visual run: {destination}")
    destination.mkdir(parents=True)
    try:
        scenario_id = f"visual-{config.seed}-{config.fleet_size}"
        admission_pattern = config.admission_pattern
        if config.injection in {"sybil", "mass_restart", "mass_renewal"}:
            admission_pattern = config.injection
        stage3a_dir = destination / "stage3a" / "block-0" / "held_out"
        stage3a = run_stage3a(
            [
                Stage3AScenario(
                    scenario_id=scenario_id,
                    pattern=AdmissionPattern(admission_pattern),
                    initial_n=max(1, round(0.10 * config.fleet_size)),
                    final_n=config.fleet_size,
                    admission_duration_s=config.admission_duration_s,
                    recovery_window_s=config.recovery_window_s,
                    disturbance_fraction=config.injection_fraction,
                    capacity_multiplier=config.capacity_multiplier,
                    partition="held_out",
                    architecture="visual_demo_notional",
                    workload="poisson",
                    shift_label=f"injection_{config.injection}",
                )
            ],
            stage3a_dir,
            root_seed=config.seed,
            replications=1,
            trace_replications_per_scenario=1,
            maximum_trace_rows=policy.max_trace_rows,
        )

        sequence = np.random.SeedSequence(config.seed).spawn(4)
        seeds = [int(item.generate_state(1, dtype=np.uint64)[0]) for item in sequence]
        enabled_layers = {
            "direct_exploit": ("communication",),
            "credential_replay": ("credential",),
            "delegated_authority": ("authorization",),
            "shared_dependency": ("dependency",),
            "shared_image": (),
            "identity_provider": ("credential",),
            "mixed": LAYER_NAMES,
        }[config.attack_class]
        common_probability = (
            config.injection_fraction
            if config.injection == "common_cause"
            else min(0.08, max(0.01, config.injection_fraction))
        )
        attack_config = AttackTraceConfig(
            horizon_steps=config.horizon_steps,
            mean_out_degree=3,
            enabled_layers=tuple(enabled_layers),
            detection_delay_range=(config.detection_delay_steps, config.detection_delay_steps),
            quarantine_delay_range=(
                config.quarantine_delay_steps,
                config.quarantine_delay_steps,
            ),
            revocation_delay_range=(
                config.revocation_delay_steps,
                config.revocation_delay_steps,
            ),
            supply_chain_step=(
                max(1, config.horizon_steps // 4)
                if config.attack_class in {"shared_image", "mixed"}
                else None
            ),
            identity_provider_step=(
                max(1, config.horizon_steps // 3)
                if config.attack_class in {"identity_provider", "mixed"}
                else None
            ),
            common_cause_probability=common_probability,
            boundary_failure_step=(
                config.horizon_steps // 2 if config.injection == "boundary_failure" else None
            ),
            boundary_failure_multiplier=1.0 + 2.0 * config.injection_fraction,
            partition_start_step=(
                config.horizon_steps // 3 if config.injection == "network_partition" else None
            ),
            partition_end_step=(
                2 * config.horizon_steps // 3
                if config.injection == "network_partition"
                else None
            ),
            partition_cross_segment_drop=config.injection_fraction,
        )
        generator = AttackTraceGenerator(
            config.fleet_size,
            topology_seed=seeds[0],
            process_seed=seeds[1],
            observation_seed=seeds[2],
            topology=config.topology,
            config=attack_config,
        )
        dmp_config = DMPConfig(
            horizon_steps=config.horizon_steps,
            capture_steps=tuple(range(config.horizon_steps + 1)),
        )
        features, dmp, _ = scenario_predictor_features(
            generator.observed_view,
            dmp_config=dmp_config,
        )
        trace = generator.simulate(seeds[3])
        lifecycle = _attack_lifecycle(trace, dmp, scenario_id, config.fleet_size)
        dmp_state_summary = _visual_dmp_state_summary(dmp, scenario_id)
        graph = {
            "record_id": f"{scenario_id}:r0",
            "scenario_id": scenario_id,
            "block": 0,
            "replication": 0,
            **_graph_projection(generator.observed_view, policy),
        }

        raw_dir = destination / "raw"
        derived_dir = destination / "derived"
        stage3b_trace_dir = destination / "stage3b" / "traces"
        raw_dir.mkdir()
        derived_dir.mkdir()
        stage3b_trace_dir.mkdir(parents=True)
        stage3a_raw = pd.read_parquet(stage3a.raw_replications_path)
        stage3a_raw.to_parquet(raw_dir / "stage3a_replications.parquet", index=False)
        record = {
            "record_id": f"{scenario_id}:r0",
            "scenario_id": scenario_id,
            "split": "heldout",
            "block": 0,
            "n_agents": config.fleet_size,
            "topology": config.topology,
            "attack_class": config.attack_class,
            "segmentation_policy": "partitioned",
            "defense_case": f"visual_{config.injection}",
            "outbreak": int(trace.outbreak),
            "final_compromise_fraction": trace.final_compromise_fraction,
            "replication_seed": seeds[3],
            **features,
        }
        pd.DataFrame([record]).to_parquet(
            raw_dir / "stage3b_replications.parquet", index=False
        )
        prediction = {
            **{key: record[key] for key in (
                "record_id",
                "scenario_id",
                "block",
                "n_agents",
                "topology",
                "attack_class",
                "segmentation_policy",
                "defense_case",
                "outbreak",
                "final_compromise_fraction",
            )},
            "candidate_outbreak_probability": dmp.outbreak_probability,
            "candidate_conditional_severity": dmp.expected_final_fraction,
            "candidate_conditional_severity_lower": max(0.0, dmp.expected_final_fraction - 0.10),
            "candidate_conditional_severity_upper": min(1.0, dmp.expected_final_fraction + 0.10),
            "candidate_expected_final_fraction": dmp.expected_final_fraction,
            "baseline_final_fraction": min(
                1.0, max(0.0, features.get("static_nonbacktracking", 0.0))
            ),
            "baseline_outbreak_probability": min(
                1.0, max(0.0, features.get("simple_reproduction", 0.0))
            ),
        }
        pd.DataFrame([prediction]).to_parquet(
            derived_dir / "stage3b_heldout_predictions.parquet", index=False
        )
        lifecycle.to_parquet(
            stage3b_trace_dir / "stage3b_lifecycle_timeseries.parquet", index=False
        )
        dmp_state_summary.to_parquet(
            stage3b_trace_dir / "stage3b_dmp_state_summary.parquet", index=False
        )
        graph_path = stage3b_trace_dir / "stage3b_graph_evidence.json"
        graph_path.write_text(
            json.dumps(graph, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )

        stage3a_summary = _read_json(stage3a.summary_path)
        evidence = {
            "schema_version": "1.0",
            "protocol": {
                "protocol_id": "FAS-S3-VISUAL-DEMO",
                "protocol_hash": "not_applicable_visual_demonstration",
                "frozen_input_checks": [],
            },
            "execution": {
                "execution_id": destination.name,
                "mode": "visual_live_demonstration",
                "completed_utc": datetime.now(UTC).isoformat(),
                "configuration": config.to_dict(),
                "seeds": {
                    "topology": seeds[0],
                    "process": seeds[1],
                    "observation": seeds[2],
                    "replication": seeds[3],
                },
            },
            "evidence_scope": "synthetic_model_demonstration_only",
            "negative_results_preserved": {},
            "stage3a": {
                "disposition": "engineering_visualization_only",
                "external_validation": False,
                "summary": stage3a_summary,
            },
            "stage3b": {
                "disposition": "engineering_visualization_only",
                "external_validation": False,
                "outbreak_probability": dmp.outbreak_probability,
                "predicted_final_fraction": dmp.expected_final_fraction,
                "observed_final_fraction": trace.final_compromise_fraction,
                "observed_outbreak": trace.outbreak,
                "attack_trace_digest": trace.digest,
            },
            "limitations": [
                "This is a bounded visual demonstration, not a protocol-gated confirmatory execution.",
                "All inputs and outcomes are synthetic and model-conditioned.",
                "Displayed DMP values are estimated; generated attack outcomes are observed within simulation only.",
            ],
        }
        evidence_path = destination / "stage3_evidence.json"
        evidence_path.write_text(
            json.dumps(_safe_json(evidence), indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        artifacts = []
        for path in sorted(candidate for candidate in destination.rglob("*") if candidate.is_file()):
            artifacts.append(
                {
                    "path": path.relative_to(destination).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
        manifest = {
            "schema_version": "1.0",
            "protocol_id": "FAS-S3-VISUAL-DEMO",
            "protocol_hash": "not_applicable_visual_demonstration",
            "execution_id": destination.name,
            "mode": "visual_live_demonstration",
            "status": "completed",
            "artifacts": artifacts,
        }
        (destination / "execution_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    except Exception:
        failure = {
            "status": "failed",
            "completed": False,
            "evidence_scope": "synthetic_model_demonstration_only",
            "configuration": config.to_dict(),
        }
        failure_path = destination / "visual_run_failure.json"
        if not failure_path.exists():
            failure_path.write_text(
                json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        raise
    return destination


def _script_json(value: Any) -> str:
    encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return (
        encoded.replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def build_stage3_console(
    primary_execution: str | Path,
    output_path: str | Path,
    *,
    comparison_execution: str | Path | None = None,
    initial_mode: ConsoleMode = "replay",
    limits: ConsoleLimits | None = None,
    overwrite: bool = False,
) -> Path:
    """Build one offline HTML console without modifying source executions."""

    if initial_mode not in {"live", "replay", "comparison"}:
        raise ValueError(f"unsupported console mode: {initial_mode}")
    if initial_mode == "comparison" and comparison_execution is None:
        raise ValueError("comparison mode requires comparison_execution")
    primary = load_stage3_execution(primary_execution, limits=limits)
    comparison = (
        load_stage3_execution(comparison_execution, limits=limits)
        if comparison_execution is not None
        else None
    )
    target = Path(output_path).resolve()
    source_roots = [primary.execution_dir]
    if comparison is not None:
        source_roots.append(comparison.execution_dir)
    if any(target == root or root in target.parents for root in source_roots):
        raise ValueError("console output must be outside immutable source execution directories")
    if target.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite console output: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "stage3-evidence-console-v1",
        "generated_utc": datetime.now(UTC).isoformat(),
        "initial_mode": initial_mode,
        "primary": primary.payload,
        "comparison": comparison.payload if comparison is not None else None,
        "scenario_bounds": {
            "fleet_size": [10, 2_000],
            "capacity_multiplier": [0.50, 1.50],
            "injection_fraction": [0.0, 0.25],
            "horizon_steps": [3, 120],
            "admission_patterns": list(ADMISSION_PATTERNS),
            "topologies": list(TOPOLOGIES),
            "attack_classes": list(ATTACK_CLASSES),
            "injections": list(INJECTIONS),
        },
    }
    html = (
        _HTML_TEMPLATE.replace("__PLOTLY_JS__", get_plotlyjs())
        .replace("__CONSOLE_PAYLOAD__", _script_json(payload))
    )
    if "\u2014" in html:
        raise RuntimeError("em dash detected in generated Stage 3 console")
    target.write_text(html, encoding="utf-8")
    return target


def export_stage3_console_json(
    primary_execution: str | Path,
    output_path: str | Path,
    *,
    comparison_execution: str | Path | None = None,
    limits: ConsoleLimits | None = None,
    overwrite: bool = False,
) -> Path:
    """Export the bounded console evidence projection as strict JSON."""

    primary = load_stage3_execution(primary_execution, limits=limits)
    comparison = (
        load_stage3_execution(comparison_execution, limits=limits)
        if comparison_execution is not None
        else None
    )
    target = Path(output_path).resolve()
    source_roots = [primary.execution_dir]
    if comparison is not None:
        source_roots.append(comparison.execution_dir)
    if any(target == root or root in target.parents for root in source_roots):
        raise ValueError("JSON export must be outside immutable source execution directories")
    if target.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite console JSON export: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "stage3-console-export-v1",
        "primary": primary.payload,
        "comparison": comparison.payload if comparison is not None else None,
    }
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return target


_HTML_TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stage 3 Fleet Assurance Evidence Console</title>
<style>
:root {
  --bg:#07111c; --panel:#0d1b2a; --panel2:#13283b; --line:#29445c;
  --text:#edf6ff; --muted:#9bb0c3; --cyan:#55c7dd; --blue:#6fa8ff;
  --green:#69d39d; --amber:#f4c266; --red:#ff7e86; --purple:#b694f6;
}
* { box-sizing:border-box; }
body { margin:0; color:var(--text); background:var(--bg); font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif; }
header { padding:24px clamp(16px,4vw,52px); border-bottom:1px solid var(--line); background:radial-gradient(circle at 15% 0,#153958 0,var(--bg) 52%); }
h1 { margin:0; font-size:clamp(25px,3vw,42px); letter-spacing:-.02em; }
.subtitle { color:var(--muted); max-width:1150px; margin-top:8px; line-height:1.5; }
.bar { margin-top:16px; display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
.badge { display:inline-flex; align-items:center; border:1px solid var(--line); border-radius:999px; padding:5px 10px; font-size:12px; color:var(--muted); }
.badge.exact { border-color:var(--green); color:var(--green); }
.badge.sampled { border-color:var(--amber); color:var(--amber); }
.badge.estimated,.badge.predicted { border-color:var(--purple); color:var(--purple); }
.badge.observed { border-color:var(--cyan); color:var(--cyan); }
.banner { margin-top:14px; padding:11px 14px; border-left:4px solid var(--amber); background:rgba(244,194,102,.08); border-radius:7px; }
nav { position:sticky; top:0; z-index:20; display:flex; gap:7px; overflow-x:auto; padding:10px clamp(12px,4vw,52px); background:rgba(7,17,28,.96); border-bottom:1px solid var(--line); }
button,select,input { background:#12263a; color:var(--text); border:1px solid #3b5872; border-radius:7px; padding:7px 9px; }
button { cursor:pointer; }
button:hover { border-color:var(--cyan); }
nav button.active { border-color:var(--cyan); background:rgba(85,199,221,.12); }
main { max-width:1680px; margin:auto; padding:18px clamp(12px,3vw,42px) 60px; }
.tab { display:none; }
.tab.active { display:block; }
.controls { display:grid; grid-template-columns:repeat(auto-fit,minmax(185px,1fr)); gap:10px; padding:13px; background:var(--panel); border:1px solid var(--line); border-radius:12px; margin-bottom:14px; }
.field { display:grid; gap:5px; }
label,.small { color:var(--muted); font-size:12px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin:14px 0; }
.card,.panel { background:var(--panel); border:1px solid var(--line); border-radius:12px; }
.card { padding:14px; min-height:100px; }
.card .label { color:var(--muted); text-transform:uppercase; letter-spacing:.08em; font-size:11px; }
.card .value { font-size:24px; font-weight:720; margin-top:7px; overflow-wrap:anywhere; }
.card .detail { color:var(--muted); margin-top:5px; font-size:12px; }
.panel { margin:13px 0; overflow:hidden; }
.panel h2,.panel h3 { margin:0; padding:11px 14px; background:var(--panel2); border-bottom:1px solid var(--line); font-size:15px; }
.plot { height:410px; }
.plot.tall { height:560px; }
.empty { padding:25px; color:var(--amber); min-height:120px; }
.two { display:grid; grid-template-columns:1fr 1fr; gap:13px; }
.warnings { padding:10px 14px; margin:0; }
.warnings li { margin:6px 0; color:var(--amber); }
.timeline { display:grid; grid-template-columns:auto auto 1fr auto; gap:8px; align-items:center; margin:13px 0; }
.timeline input { width:100%; }
.scenario-form { display:grid; grid-template-columns:repeat(auto-fit,minmax(155px,1fr)); gap:9px; padding:14px; }
.scenario-note { padding:0 14px 14px; color:var(--muted); font-size:12px; }
table { width:100%; border-collapse:collapse; font-size:12px; }
th,td { padding:8px 10px; text-align:left; border-bottom:1px solid var(--line); vertical-align:top; }
th { color:var(--muted); background:var(--panel2); }
pre { margin:0; padding:13px; max-height:420px; overflow:auto; font:11px ui-monospace,SFMono-Regular,Menlo,monospace; }
@media (max-width:900px) { .two { grid-template-columns:1fr; } .timeline { grid-template-columns:auto auto; } }
</style>
<script>__PLOTLY_JS__</script>
</head>
<body>
<header>
  <h1>Stage 3 Fleet Assurance Evidence Console</h1>
  <div class="subtitle">Read-only review of immutable Stage 3 evidence. Live mode completes a bounded synthetic demonstration run before animation. It is not simulation streaming and does not modify scientific evidence.</div>
  <div class="bar" id="headerBadges"></div>
  <div class="banner" id="evidenceBoundary"></div>
</header>
<nav>
  <button class="active" data-tab="overview">Overview</button>
  <button data-tab="stage3a">Stage 3A admission</button>
  <button data-tab="stage3b">Stage 3B compromise</button>
  <button data-tab="scenario">Scenario request</button>
  <button data-tab="provenance">Provenance</button>
</nav>
<main>
<div class="controls">
  <div class="field"><label for="modeSelect">Mode</label><select id="modeSelect"><option value="live">Live, completed-run animation</option><option value="replay">Replay</option><option value="comparison">Comparison</option></select></div>
  <div class="field"><label for="aScenario">Stage 3A scenario</label><select id="aScenario"></select></div>
  <div class="field"><label for="aResource">Assurance resource</label><select id="aResource"></select></div>
  <div class="field"><label for="bScenario">Stage 3B scenario</label><select id="bScenario"></select></div>
  <div class="field"><label>Exports</label><div><button id="downloadEvidence">Evidence JSON</button> <button id="downloadRequest">Run request JSON</button></div></div>
</div>
<div class="timeline"><button id="play">Play evidence</button><button id="pause">Pause</button><input id="timeSlider" type="range" min="0" max="0" value="0" step="1"><span id="timeLabel">t=0</span></div>

<section id="overview" class="tab active">
  <div class="grid" id="summaryCards"></div>
  <section class="panel"><h2>Evidence availability and limitations</h2><ul class="warnings" id="warnings"></ul></section>
  <section class="panel"><h2>Disposition comparison</h2><div id="dispositionPlot" class="plot"></div></section>
</section>

<section id="stage3a" class="tab">
  <div class="grid" id="aCards"></div>
  <div class="two">
    <section class="panel"><h2>Admission and fleet trajectory</h2><div id="admissionPlot" class="plot"></div></section>
    <section class="panel"><h2>Omega(t) and boundary crossing at 1.0</h2><div id="omegaPlot" class="plot"></div></section>
  </div>
  <div class="two">
    <section class="panel"><h2>Queue depth</h2><div id="queuePlot" class="plot"></div></section>
    <section class="panel"><h2>Wait and derived wait budget</h2><div id="waitPlot" class="plot"></div></section>
  </div>
</section>

<section id="stage3b" class="tab">
  <div class="grid" id="bCards"></div>
  <div class="two">
    <section class="panel"><h2>Outbreak probability versus observed outcome</h2><div id="outbreakPlot" class="plot"></div></section>
    <section class="panel"><h2>Predicted versus observed compromise with conditional-severity intervals</h2><div id="severityPlot" class="plot"></div></section>
  </div>
  <div class="two">
    <section class="panel"><h2>Detection, quarantine, revocation, and recovery</h2><div id="lifecyclePlot" class="plot"></div></section>
    <section class="panel"><h2>Retained DMP node-state fractions, estimated</h2><div id="dmpStatePlot" class="plot"></div></section>
  </div>
  <div class="two">
    <section class="panel"><h2>Retained DMP edge and common-cause summaries, estimated</h2><div id="dmpMechanismPlot" class="plot"></div></section>
    <section class="panel"><h2>Scenario predictor features, estimated</h2><div id="dmpFeaturePlot" class="plot"></div></section>
  </div>
  <section class="panel"><h2>Observed graph view, when retained</h2><div id="graphPlot" class="plot tall"></div></section>
</section>

<section id="scenario" class="tab">
  <section class="panel"><h2>Bounded synthetic scenario request</h2>
    <div class="scenario-form">
      <div class="field"><label>Fleet size, 10 to 2000</label><input id="cfgFleet" type="number" min="10" max="2000" value="100"></div>
      <div class="field"><label>Admission pattern</label><select id="cfgAdmission"></select></div>
      <div class="field"><label>Capacity multiplier</label><input id="cfgCapacity" type="number" min="0.5" max="1.5" step="0.05" value="1"></div>
      <div class="field"><label>Topology</label><select id="cfgTopology"></select></div>
      <div class="field"><label>Attack class</label><select id="cfgAttack"></select></div>
      <div class="field"><label>Fault or adversary injection</label><select id="cfgInjection"></select></div>
      <div class="field"><label>Injection fraction, 0 to 0.25</label><input id="cfgFraction" type="number" min="0" max="0.25" step="0.01" value="0"></div>
      <div class="field"><label>Horizon steps, 3 to 120</label><input id="cfgHorizon" type="number" min="3" max="120" value="20"></div>
      <div class="field"><label>Seed</label><input id="cfgSeed" type="number" min="0" value="320260819"></div>
    </div>
    <div class="scenario-note">The offline browser can export this request but cannot execute it. Use the local builder in live mode to create a new immutable visual run. Existing runs are never mutated. Injection bounds are enforced again in Python.</div>
  </section>
  <section class="panel"><h2>Current request</h2><pre id="requestPreview"></pre></section>
</section>

<section id="provenance" class="tab">
  <section class="panel"><h2>Loaded artifact integrity</h2><div style="overflow:auto"><table><thead><tr><th>Artifact</th><th>Bytes</th><th>Status</th><th>Expected SHA-256</th><th>Actual SHA-256</th></tr></thead><tbody id="integrityRows"></tbody></table></div></section>
  <section class="panel"><h2>Embedded evidence</h2><pre id="rawEvidence"></pre></section>
</section>
</main>
<script>
const CONSOLE = __CONSOLE_PAYLOAD__;
const PRIMARY = CONSOLE.primary;
const COMPARISON = CONSOLE.comparison;
const COLORS = {observed:'#55c7dd',predicted:'#b694f6',sampled:'#f4c266',failure:'#ff7e86',ok:'#69d39d',comparison:'#6fa8ff',amber:'#f4c266',blue:'#6fa8ff',purple:'#b694f6'};
const layoutBase = {paper_bgcolor:'#0d1b2a',plot_bgcolor:'#0d1b2a',font:{color:'#edf6ff'},margin:{l:58,r:26,t:30,b:50},legend:{orientation:'h',y:-.22},hovermode:'closest'};
let timer = null;
let currentTime = 0;

function unique(values) { return [...new Set(values.filter(v => v !== null && v !== undefined).map(String))].sort(); }
function rows(run, track, name) { return run && run[track] && Array.isArray(run[track][name]) ? run[track][name] : []; }
function num(value, fallback=0) { const parsed=Number(value); return Number.isFinite(parsed)?parsed:fallback; }
function pct(value) { return value===null||value===undefined?'not available':(100*num(value)).toFixed(1)+'%'; }
function text(value) { return value===null||value===undefined?'not available':String(value); }
function hasFiniteFields(row,names) { return names.every(name=>row[name]!==null&&row[name]!==undefined&&Number.isFinite(Number(row[name]))); }
function selected(id) { return document.getElementById(id).value; }
function byScenario(data, scenario) { return data.filter(row => String(row.scenario_id) === String(scenario)); }
function firstReplication(data) { if (!data.length) return data; const reps=unique(data.map(row=>row.replication)); return data.filter(row=>String(row.replication)===String(reps[0])); }
function sorted(data, field) { return [...data].sort((a,b)=>num(a[field])-num(b[field])); }
function emptyPlot(id,message) { Plotly.purge(id); document.getElementById(id).innerHTML='<div class="empty"></div>'; document.getElementById(id).firstChild.textContent=message; }
function plot(id,traces,layout={}) { Plotly.newPlot(id,traces,{...layoutBase,...layout},{responsive:true,displaylogo:false}); }
function addOptions(id,values) { const select=document.getElementById(id); const old=select.value; select.innerHTML=''; values.forEach(value=>{const option=document.createElement('option');option.value=value;option.textContent=value;select.appendChild(option);}); if(values.includes(old))select.value=old; }
function badge(label,kind='') { const span=document.createElement('span');span.className='badge '+kind;span.textContent=label;return span; }

function initializeHeader() {
  const holder=document.getElementById('headerBadges');
  holder.appendChild(badge('Execution '+text(PRIMARY.execution.execution_id)));
  holder.appendChild(badge('Integrity '+text(PRIMARY.execution.integrity),PRIMARY.execution.integrity.startsWith('verified')?'exact':'sampled'));
  holder.appendChild(badge('Observed outcomes','observed'));
  holder.appendChild(badge('Predictions and DMP','predicted'));
  const aRep=PRIMARY.stage3a.representations.admission_trace.representation;
  holder.appendChild(badge('A traces '+aRep,aRep==='exact'?'exact':'sampled'));
  const lifecycleRep=PRIMARY.stage3b.representations.lifecycle_trace.representation;
  holder.appendChild(badge('B lifecycle retention '+lifecycleRep,lifecycleRep==='exact'?'exact':'sampled'));
  const dmpMeta=PRIMARY.stage3b.representations.dmp_state_summary;
  holder.appendChild(badge('DMP state '+text(dmpMeta.representation)+', retention '+text(dmpMeta.retention),dmpMeta.representation==='estimated'?'predicted':'sampled'));
  if(COMPARISON)holder.appendChild(badge('Comparison '+text(COMPARISON.execution.execution_id),'predicted'));
  document.getElementById('evidenceBoundary').textContent='Evidence scope: '+text(PRIMARY.execution.evidence_scope)+'. Representation labels describe retained data, not operational accuracy. No console action changes a run, metric, or manifest.';
}

function initializeSelectors() {
  const aRows=[...rows(PRIMARY,'stage3a','admission_trace'),...rows(PRIMARY,'stage3a','replications')];
  const aScenarios=unique(aRows.map(row=>row.scenario_id));
  addOptions('aScenario',aScenarios.length?aScenarios:['not retained']);
  const resources=unique(rows(PRIMARY,'stage3a','resource_trace').map(row=>row.resource_id));
  addOptions('aResource',resources.length?resources:['not retained']);
  const bRows=[...rows(PRIMARY,'stage3b','predictions'),...rows(PRIMARY,'stage3b','records'),...rows(PRIMARY,'stage3b','lifecycle_trace'),...rows(PRIMARY,'stage3b','dmp_state_summary')];
  const bScenarios=Array.isArray(PRIMARY.stage3b.selector_scenario_ids)?PRIMARY.stage3b.selector_scenario_ids.map(String):unique(bRows.map(row=>row.scenario_id));
  addOptions('bScenario',bScenarios.length?bScenarios:['not retained']);
  const bounds=CONSOLE.scenario_bounds;
  addOptions('cfgAdmission',bounds.admission_patterns);
  addOptions('cfgTopology',bounds.topologies);
  addOptions('cfgAttack',bounds.attack_classes);
  addOptions('cfgInjection',bounds.injections);
  document.getElementById('modeSelect').value=CONSOLE.initial_mode;
  if(!COMPARISON)document.querySelector('#modeSelect option[value="comparison"]').disabled=true;
}

function stageSummary(run,track) { return run.evidence && run.evidence[track] ? run.evidence[track] : {}; }
function initializeOverview() {
  const a=stageSummary(PRIMARY,'stage3a'), b=stageSummary(PRIMARY,'stage3b'), exe=PRIMARY.execution;
  const cards=[
    ['Mode',text(exe.mode),'Run completed before animation'],
    ['Stage 3A disposition',text(a.disposition),'Synthetic, model-conditioned'],
    ['Stage 3B disposition',text(b.disposition),'Separate generator with bounded observed view'],
    ['Integrity',text(exe.integrity),'Loaded artifacts only'],
    ['A trace representation',text(PRIMARY.stage3a.representations.admission_trace.representation),'Exact or sampled retention'],
    ['B lifecycle retention',text(PRIMARY.stage3b.representations.lifecycle_trace.representation),'Exact or sampled retained rows'],
    ['B DMP state',text(PRIMARY.stage3b.representations.dmp_state_summary.representation)+', retention '+text(PRIMARY.stage3b.representations.dmp_state_summary.retention),'Estimated aggregate; no inferred state when absent'],
    ['B graph retention',text(PRIMARY.stage3b.representations.graph),'One scenario-bound observed-view projection'],
  ];
  const holder=document.getElementById('summaryCards');holder.innerHTML='';
  cards.forEach(([label,value,detail])=>{const div=document.createElement('div');div.className='card';div.innerHTML='<div class="label"></div><div class="value"></div><div class="detail"></div>';div.children[0].textContent=label;div.children[1].textContent=value;div.children[2].textContent=detail;holder.appendChild(div);});
  const warnings=document.getElementById('warnings');warnings.innerHTML='';
  PRIMARY.warnings.forEach(value=>{const li=document.createElement('li');li.textContent=value;warnings.appendChild(li);});
  const runs=[PRIMARY,...(COMPARISON?[COMPARISON]:[])];
  const labels=runs.map(run=>run.execution.execution_id);
  const aValues=runs.map(run=>num(stageSummary(run,'stage3a').brier_improvement_fraction,0));
  const bValues=runs.map(run=>num(stageSummary(run,'stage3b').final_size_mae_improvement_fraction,0));
  plot('dispositionPlot',[{type:'bar',x:labels,y:aValues,name:'Stage 3A Brier improvement, predicted comparison',marker:{color:COLORS.predicted}},{type:'bar',x:labels,y:bValues,name:'Stage 3B final-size MAE improvement, predicted comparison',marker:{color:COLORS.comparison}}],{barmode:'group',yaxis:{title:'Fractional improvement'},title:'Evidence summary comparison. Missing metrics render as zero and remain labeled unavailable in cards.'});
}

function timelineShape(x) { return {type:'line',x0:x,x1:x,y0:0,y1:1,yref:'paper',line:{color:'#f4c266',width:2,dash:'dot'}}; }
function renderStage3A() {
  const scenario=selected('aScenario'), resource=selected('aResource');
  let admission=sorted(firstReplication(byScenario(rows(PRIMARY,'stage3a','admission_trace'),scenario)),'time_s');
  let resources=sorted(firstReplication(byScenario(rows(PRIMARY,'stage3a','resource_trace'),scenario).filter(row=>String(row.resource_id)===resource)),'time_s');
  const compareMode=selected('modeSelect')==='comparison'&&COMPARISON;
  const comparisonAdmission=compareMode?sorted(firstReplication(byScenario(rows(COMPARISON,'stage3a','admission_trace'),scenario)),'time_s'):[];
  const comparisonResources=compareMode?sorted(firstReplication(byScenario(rows(COMPARISON,'stage3a','resource_trace'),scenario).filter(row=>String(row.resource_id)===resource)),'time_s'):[];
  if(!admission.length)emptyPlot('admissionPlot','Admission and fleet trace not retained for this scenario.');
  else {
    const admissionTraces=[
      {type:'bar',x:admission.map(r=>r.time_s),y:admission.map(r=>r.planned_admissions),name:'Planned admissions, predicted',marker:{color:COLORS.predicted},opacity:.45},
      {type:'bar',x:admission.map(r=>r.time_s),y:admission.map(r=>r.admitted_agents),name:'Admitted agents, observed',marker:{color:COLORS.observed},opacity:.65},
      {type:'scatter',mode:'lines',x:admission.map(r=>r.time_s),y:admission.map(r=>r.fleet_size),name:'Fleet size, observed',yaxis:'y2',line:{color:COLORS.observed,width:3}},
      {type:'scatter',mode:'lines',x:admission.map(r=>r.time_s),y:admission.map(r=>r.projected_fleet_size),name:'Fleet size, predicted',yaxis:'y2',line:{color:COLORS.predicted,dash:'dash'}}
    ];
    if(comparisonAdmission.length)admissionTraces.push({type:'scatter',mode:'lines',x:comparisonAdmission.map(r=>r.time_s),y:comparisonAdmission.map(r=>r.fleet_size),name:'Comparison fleet, observed',yaxis:'y2',line:{color:COLORS.comparison,dash:'dot'}});
    plot('admissionPlot',admissionTraces,{barmode:'overlay',xaxis:{title:'Time, s'},yaxis:{title:'Admissions per step'},yaxis2:{title:'Fleet size',overlaying:'y',side:'right'},shapes:[timelineShape(currentTime)]});
  }
  if(!admission.length)emptyPlot('omegaPlot','Omega(t) trace not retained for this scenario.');
  else {
    const observed=admission.map(r=>num(r.maximum_observed_omega,NaN));
    const predicted=admission.map(r=>num(r.projected_maximum_omega,NaN));
    const crossings=admission.filter(r=>num(r.maximum_observed_omega)<Infinity&&num(r.maximum_observed_omega)>=1);
    const omegaTraces=[
      {type:'scatter',mode:'lines',x:admission.map(r=>r.time_s),y:observed,name:'Omega observed',line:{color:COLORS.observed,width:3}},
      {type:'scatter',mode:'lines',x:admission.map(r=>r.time_s),y:predicted,name:'Omega predicted ex ante',line:{color:COLORS.predicted,dash:'dash'}},
      {type:'scatter',mode:'markers',x:crossings.map(r=>r.time_s),y:crossings.map(r=>r.maximum_observed_omega),name:'Observed boundary crossing',marker:{color:COLORS.failure,size:8}}
    ];
    if(comparisonAdmission.length)omegaTraces.push({type:'scatter',mode:'lines',x:comparisonAdmission.map(r=>r.time_s),y:comparisonAdmission.map(r=>r.maximum_observed_omega),name:'Comparison Omega observed',line:{color:COLORS.comparison,dash:'dot'}});
    plot('omegaPlot',omegaTraces,{xaxis:{title:'Time, s'},yaxis:{title:'Omega ratio'},shapes:[timelineShape(currentTime),{type:'line',x0:admission[0].time_s,x1:admission[admission.length-1].time_s,y0:1,y1:1,line:{color:COLORS.failure,dash:'dash'}}]});
  }
  if(!resources.length){emptyPlot('queuePlot','Resource trace not retained for this scenario and resource.');emptyPlot('waitPlot','Wait trace not retained for this scenario and resource.');}
  else {
    const queueTraces=[
      {type:'scatter',mode:'lines',x:resources.map(r=>r.time_s),y:resources.map(r=>r.queue_depth),name:'Queue observed',line:{color:COLORS.observed,width:3}},
      {type:'scatter',mode:'lines',x:resources.map(r=>r.time_s),y:resources.map(r=>r.projected_queue_depth),name:'Queue predicted',line:{color:COLORS.predicted,dash:'dash'}}
    ];
    if(comparisonResources.length)queueTraces.push({type:'scatter',mode:'lines',x:comparisonResources.map(r=>r.time_s),y:comparisonResources.map(r=>r.queue_depth),name:'Comparison queue observed',line:{color:COLORS.comparison,dash:'dot'}});
    plot('queuePlot',queueTraces,{xaxis:{title:'Time, s'},yaxis:{title:'Work units'},shapes:[timelineShape(currentTime)]});
    const waitTraces=[
      {type:'scatter',mode:'lines',x:resources.map(r=>r.time_s),y:resources.map(r=>r.wait_s),name:'Wait observed',line:{color:COLORS.observed,width:3}},
      {type:'scatter',mode:'lines',x:resources.map(r=>r.time_s),y:resources.map(r=>r.projected_wait_s),name:'Wait predicted',line:{color:COLORS.predicted,dash:'dash'}},
      {type:'scatter',mode:'lines',x:resources.map(r=>r.time_s),y:resources.map(r=>r.observed_wait_budget_s_derived),name:'Wait budget, derived from retained ratio',line:{color:COLORS.failure,dash:'dot'}}
    ];
    if(comparisonResources.length)waitTraces.push({type:'scatter',mode:'lines',x:comparisonResources.map(r=>r.time_s),y:comparisonResources.map(r=>r.wait_s),name:'Comparison wait observed',line:{color:COLORS.comparison,dash:'dot'}});
    plot('waitPlot',waitTraces,{xaxis:{title:'Time, s'},yaxis:{title:'Seconds'},shapes:[timelineShape(currentTime)]});
  }
  const outcomes=byScenario(rows(PRIMARY,'stage3a','replications'),scenario);
  const row=outcomes[0]||{};
  const crossings=admission.filter(r=>num(r.maximum_observed_omega,0)>=1);
  const cards=[
    ['Operational failure',text(row.operational_failure),'Observed within simulation'],
    ['First Omega crossing',crossings.length?num(crossings[0].time_s).toFixed(1)+' s':'none retained','Boundary at 1.0'],
    ['Deadline-miss fraction',row.deadline_miss_fraction===undefined?'not available':pct(row.deadline_miss_fraction),'Observed outcome'],
    ['Useful throughput ratio',row.useful_task_throughput_ratio===undefined?'not available':pct(row.useful_task_throughput_ratio),'Observed outcome']
  ];
  fillCards('aCards',cards);
  updateTimeRange(admission.map(r=>num(r.time_s,0)));
}

function fillCards(id,cards) { const holder=document.getElementById(id);holder.innerHTML='';cards.forEach(([label,value,detail])=>{const div=document.createElement('div');div.className='card';div.innerHTML='<div class="label"></div><div class="value"></div><div class="detail"></div>';div.children[0].textContent=label;div.children[1].textContent=value;div.children[2].textContent=detail;holder.appendChild(div);}); }

function renderStage3B() {
  const scenario=selected('bScenario');
  const predictions=rows(PRIMARY,'stage3b','predictions');
  const compareMode=selected('modeSelect')==='comparison'&&COMPARISON;
  const comparisonPredictions=compareMode?rows(COMPARISON,'stage3b','predictions'):[];
  if(!predictions.length){emptyPlot('outbreakPlot','Held-out Stage 3B predictions were not retained.');emptyPlot('severityPlot','Held-out Stage 3B predictions were not retained.');}
  else {
    const outbreakTraces=[{type:'scatter',mode:'markers',x:predictions.map(r=>r.candidate_outbreak_probability),y:predictions.map(r=>r.outbreak),name:'Primary observed outcome by predicted probability',marker:{color:COLORS.observed,opacity:.55,size:7}},{type:'scatter',mode:'lines',x:[0,1],y:[0,1],name:'Reference only',line:{color:COLORS.predicted,dash:'dash'}}];
    if(comparisonPredictions.length)outbreakTraces.push({type:'scatter',mode:'markers',x:comparisonPredictions.map(r=>r.candidate_outbreak_probability),y:comparisonPredictions.map(r=>r.outbreak),name:'Comparison observed outcome by predicted probability',marker:{color:COLORS.comparison,opacity:.45,size:6,symbol:'diamond'}});
    plot('outbreakPlot',outbreakTraces,{xaxis:{title:'Outbreak probability, predicted',range:[0,1]},yaxis:{title:'Outbreak outcome, observed',range:[-.1,1.1]}});
    const outbreaks=predictions.filter(r=>num(r.outbreak)===1);
    const lower=outbreaks.map(r=>num(r.candidate_conditional_severity)-num(r.candidate_conditional_severity_lower));
    const upper=outbreaks.map(r=>num(r.candidate_conditional_severity_upper)-num(r.candidate_conditional_severity));
    const severityTraces=[
      {type:'scatter',mode:'markers',x:outbreaks.map(r=>r.final_compromise_fraction),y:outbreaks.map(r=>r.candidate_conditional_severity),name:'Conditional severity predicted with interval',marker:{color:COLORS.predicted,size:7},error_y:{type:'data',symmetric:false,array:upper,arrayminus:lower,visible:true}},
      {type:'scatter',mode:'lines',x:[0,1],y:[0,1],name:'Perfect prediction',line:{color:COLORS.failure,dash:'dash'}}
    ];
    const expectedIntervalFields=['candidate_expected_final_fraction_lower','candidate_expected_final_fraction_upper'];
    const expectedPointFields=['candidate_expected_final_fraction','final_compromise_fraction'];
    const expectedWithInterval=predictions.filter(r=>hasFiniteFields(r,[...expectedPointFields,...expectedIntervalFields]));
    const expectedWithoutInterval=predictions.filter(r=>hasFiniteFields(r,expectedPointFields)&&!hasFiniteFields(r,expectedIntervalFields));
    if(expectedWithInterval.length)severityTraces.push({type:'scatter',mode:'markers',x:expectedWithInterval.map(r=>r.final_compromise_fraction),y:expectedWithInterval.map(r=>r.candidate_expected_final_fraction),name:'Expected final fraction, estimated with calibration-fitted interval',marker:{color:COLORS.observed,opacity:.55,size:6},error_y:{type:'data',symmetric:false,array:expectedWithInterval.map(r=>num(r.candidate_expected_final_fraction_upper)-num(r.candidate_expected_final_fraction)),arrayminus:expectedWithInterval.map(r=>num(r.candidate_expected_final_fraction)-num(r.candidate_expected_final_fraction_lower)),visible:true}});
    if(expectedWithoutInterval.length)severityTraces.push({type:'scatter',mode:'markers',x:expectedWithoutInterval.map(r=>r.final_compromise_fraction),y:expectedWithoutInterval.map(r=>r.candidate_expected_final_fraction),name:'Expected final fraction, estimated; interval not retained',marker:{color:COLORS.observed,opacity:.45,size:6,symbol:'circle-open'}});
    const comparisonWithInterval=comparisonPredictions.filter(r=>hasFiniteFields(r,[...expectedPointFields,...expectedIntervalFields]));
    const comparisonWithoutInterval=comparisonPredictions.filter(r=>hasFiniteFields(r,expectedPointFields)&&!hasFiniteFields(r,expectedIntervalFields));
    if(comparisonWithInterval.length)severityTraces.push({type:'scatter',mode:'markers',x:comparisonWithInterval.map(r=>r.final_compromise_fraction),y:comparisonWithInterval.map(r=>r.candidate_expected_final_fraction),name:'Comparison expected final fraction, estimated with calibration-fitted interval',marker:{color:COLORS.comparison,opacity:.5,size:6,symbol:'diamond'},error_y:{type:'data',symmetric:false,array:comparisonWithInterval.map(r=>num(r.candidate_expected_final_fraction_upper)-num(r.candidate_expected_final_fraction)),arrayminus:comparisonWithInterval.map(r=>num(r.candidate_expected_final_fraction)-num(r.candidate_expected_final_fraction_lower)),visible:true}});
    if(comparisonWithoutInterval.length)severityTraces.push({type:'scatter',mode:'markers',x:comparisonWithoutInterval.map(r=>r.final_compromise_fraction),y:comparisonWithoutInterval.map(r=>r.candidate_expected_final_fraction),name:'Comparison expected final fraction, estimated; interval not retained',marker:{color:COLORS.comparison,opacity:.4,size:6,symbol:'diamond-open'}});
    plot('severityPlot',severityTraces,{xaxis:{title:'Final compromise fraction, observed',range:[0,1]},yaxis:{title:'Compromise fraction, predicted',range:[0,1]}});
  }
  let lifecycle=sorted(byScenario(rows(PRIMARY,'stage3b','lifecycle_trace'),scenario),'step');
  if(!lifecycle.length)emptyPlot('lifecyclePlot','Lifecycle events were not retained. Detection, quarantine, revocation, and recovery overlays are unavailable, not estimated.');
  else plot('lifecyclePlot',[
    {type:'scatter',mode:'lines',x:lifecycle.map(r=>r.step),y:lifecycle.map(r=>r.observed_ever_compromised_fraction),name:'Ever compromised, observed',line:{color:COLORS.failure,width:3}},
    {type:'scatter',mode:'lines',x:lifecycle.map(r=>r.step),y:lifecycle.map(r=>r.observed_detected_fraction),name:'Detected, observed',line:{color:COLORS.amber}},
    {type:'scatter',mode:'lines',x:lifecycle.map(r=>r.step),y:lifecycle.map(r=>r.observed_quarantined_fraction),name:'Quarantined, observed',line:{color:COLORS.blue}},
    {type:'scatter',mode:'lines',x:lifecycle.map(r=>r.step),y:lifecycle.map(r=>r.observed_revoked_fraction),name:'Revoked, observed',line:{color:COLORS.purple}},
    {type:'scatter',mode:'lines',x:lifecycle.map(r=>r.step),y:lifecycle.map(r=>r.observed_recovered_fraction),name:'Recovered, observed',line:{color:COLORS.ok}},
    {type:'scatter',mode:'lines',x:lifecycle.map(r=>r.step),y:lifecycle.map(r=>r.predicted_ever_compromised_fraction),name:'Ever compromised, DMP estimated',line:{color:COLORS.predicted,dash:'dash'}}
  ],{xaxis:{title:'Step'},yaxis:{title:'Fleet fraction',range:[0,1]},shapes:[timelineShape(currentTime)]});
  let dmpState=sorted(firstReplication(byScenario(rows(PRIMARY,'stage3b','dmp_state_summary'),scenario)),'step');
  if(!dmpState.length){
    emptyPlot('dmpStatePlot','DMP node-state summaries were not retained. Values are unavailable and are not inferred.');
    emptyPlot('dmpMechanismPlot','DMP edge-message and common-cause summaries were not retained. Values are unavailable and are not inferred.');
  } else {
    plot('dmpStatePlot',[
      {type:'scatter',mode:'lines',x:dmpState.map(r=>r.step),y:dmpState.map(r=>r.susceptible_fraction),name:'Susceptible fraction, DMP estimated',line:{color:COLORS.ok}},
      {type:'scatter',mode:'lines',x:dmpState.map(r=>r.step),y:dmpState.map(r=>r.compromised_undetected_fraction),name:'Compromised undetected, DMP estimated',line:{color:COLORS.failure,width:3}},
      {type:'scatter',mode:'lines',x:dmpState.map(r=>r.step),y:dmpState.map(r=>r.detected_fraction),name:'Detected fraction, DMP estimated',line:{color:COLORS.amber}},
      {type:'scatter',mode:'lines',x:dmpState.map(r=>r.step),y:dmpState.map(r=>r.quarantined_fraction),name:'Quarantined fraction, DMP estimated',line:{color:COLORS.blue}},
      {type:'scatter',mode:'lines',x:dmpState.map(r=>r.step),y:dmpState.map(r=>r.revoked_fraction),name:'Revoked fraction, DMP estimated',line:{color:COLORS.purple}},
      {type:'scatter',mode:'lines',x:dmpState.map(r=>r.step),y:dmpState.map(r=>r.recovered_fraction),name:'Recovered fraction, DMP estimated',line:{color:COLORS.observed}}
    ],{xaxis:{title:'Step'},yaxis:{title:'Estimated node fraction',range:[0,1]},shapes:[timelineShape(currentTime)]});
    plot('dmpMechanismPlot',[
      {type:'scatter',mode:'lines',x:dmpState.map(r=>r.step),y:dmpState.map(r=>r.mean_edge_no_transmission),name:'Mean edge no-transmission, DMP estimated',line:{color:COLORS.predicted,width:3}},
      {type:'scatter',mode:'lines',x:dmpState.map(r=>r.step),y:dmpState.map(r=>r.mean_edge_source_active),name:'Mean edge source-active, DMP estimated',line:{color:COLORS.failure}},
      {type:'scatter',mode:'lines',x:dmpState.map(r=>r.step),y:dmpState.map(r=>r.mean_common_cause_survival),name:'Mean common-cause survival, DMP estimated',line:{color:COLORS.comparison,dash:'dash'}}
    ],{xaxis:{title:'Step'},yaxis:{title:'Estimated aggregate',range:[0,1]},shapes:[timelineShape(currentTime)]});
  }
  const record=byScenario(rows(PRIMARY,'stage3b','records'),scenario)[0]||{};
  const featureNames=['dmp_outbreak_probability','dmp_expected_fraction','node_hazard_aggregation','temporal_propagator','reachable_component_fraction','directed_percolation_fraction','static_adjacency','static_nonbacktracking','simple_reproduction','combined_scalar'];
  const available=featureNames.filter(name=>record[name]!==undefined&&record[name]!==null);
  if(!available.length)emptyPlot('dmpFeaturePlot','Scenario predictor features were not retained. Values are unavailable and are not inferred.');
  else plot('dmpFeaturePlot',[{type:'bar',x:available,y:available.map(name=>record[name]),name:'Estimated predictor feature',marker:{color:available.map(name=>name.startsWith('dmp')?COLORS.predicted:COLORS.comparison)}}],{xaxis:{tickangle:-28},yaxis:{title:'Feature value'},margin:{...layoutBase.margin,b:135}});
  renderGraph(scenario);
  const selectedPrediction=byScenario(predictions,scenario)[0]||{};
  const expectedIntervalRetained=hasFiniteFields(selectedPrediction,['candidate_expected_final_fraction_lower','candidate_expected_final_fraction_upper']);
  fillCards('bCards',[
    ['Outbreak probability',selectedPrediction.candidate_outbreak_probability===undefined?'not available':pct(selectedPrediction.candidate_outbreak_probability),'Predicted'],
    ['Outbreak outcome',text(selectedPrediction.outbreak),'Observed within simulation'],
    ['Expected final fraction',selectedPrediction.candidate_expected_final_fraction===undefined?'not available':pct(selectedPrediction.candidate_expected_final_fraction),expectedIntervalRetained?'Estimated; calibration-fitted interval retained':'Estimated; interval not retained'],
    ['Final compromise',selectedPrediction.final_compromise_fraction===undefined?'not available':pct(selectedPrediction.final_compromise_fraction),'Observed within simulation']
  ]);
  updateTimeRange([...lifecycle,...dmpState].map(r=>num(r.step,0)));
}

function renderGraph(scenario) {
  const graph=PRIMARY.stage3b.graph;
  if(!graph||!Array.isArray(graph.nodes)){emptyPlot('graphPlot','Observed graph evidence was not retained. No topology is reconstructed from scalar predictors.');return;}
  const graphScenario=PRIMARY.stage3b.graph_scenario_id;
  if(!graphScenario){emptyPlot('graphPlot','Retained graph evidence has no scenario identity. Display is unavailable because the console will not infer a match.');return;}
  if(String(graphScenario)!==String(scenario)){emptyPlot('graphPlot','The one retained graph belongs to scenario '+String(graphScenario)+'. It is unavailable for selected scenario '+String(scenario)+', and no graph is reconstructed.');return;}
  const nodeMap=Object.fromEntries(graph.nodes.map(node=>[String(node.id),node]));
  const x=[],y=[];
  (graph.edges||[]).forEach(edge=>{const a=nodeMap[String(edge.source)],b=nodeMap[String(edge.target)];if(a&&b){x.push(a.x,b.x,null);y.push(a.y,b.y,null);}});
  plot('graphPlot',[{type:'scattergl',mode:'lines',x,y,name:'Observed directed edges, arrowheads omitted',line:{color:'rgba(155,176,195,.24)',width:1},hoverinfo:'skip'},{type:'scattergl',mode:'markers',x:graph.nodes.map(n=>n.x),y:graph.nodes.map(n=>n.y),text:graph.nodes.map(n=>'node '+n.id+'<br>segment '+n.segment+'<br>initial p '+num(n.initial_probability).toFixed(4)),hoverinfo:'text',name:'Observed nodes',marker:{size:7,color:graph.nodes.map(n=>num(n.initial_probability)),colorscale:'Viridis',showscale:true}}],{xaxis:{visible:false},yaxis:{visible:false,scaleanchor:'x'},title:'Observed-view graph for '+String(graphScenario)+', retention '+text(graph.representation)});
}

function updateTimeRange(values) { if(!values.length)return; const slider=document.getElementById('timeSlider');const maximum=Math.max(...values);slider.max=String(Math.ceil(maximum));if(currentTime>maximum){currentTime=0;slider.value='0';}document.getElementById('timeLabel').textContent='t='+currentTime; }
function updateTimeline() { currentTime=num(document.getElementById('timeSlider').value);document.getElementById('timeLabel').textContent='t='+currentTime;['admissionPlot','omegaPlot','queuePlot','waitPlot','lifecyclePlot','dmpStatePlot','dmpMechanismPlot'].forEach(id=>{const element=document.getElementById(id);if(element&&element.data)Plotly.relayout(id,{'shapes[0].x0':currentTime,'shapes[0].x1':currentTime}).catch(()=>{});}); }

function currentRequest() {
  const injection=selected('cfgInjection');
  const fraction=injection==='none'?0:num(document.getElementById('cfgFraction').value);
  return {schema_version:'stage3-visual-scenario-request-v1',action:'create_new_immutable_visual_demonstration',evidence_scope:'synthetic_model_demonstration_only',configuration:{fleet_size:Math.round(num(document.getElementById('cfgFleet').value)),admission_pattern:selected('cfgAdmission'),capacity_multiplier:num(document.getElementById('cfgCapacity').value),topology:selected('cfgTopology'),attack_class:selected('cfgAttack'),injection,injection_fraction:fraction,detection_delay_steps:3,quarantine_delay_steps:2,revocation_delay_steps:2,admission_duration_s:30,recovery_window_s:15,horizon_steps:Math.round(num(document.getElementById('cfgHorizon').value)),seed:Math.round(num(document.getElementById('cfgSeed').value))},limitations:['This request is not a confirmatory protocol input.','The console cannot modify an existing or active execution.']};
}
function validateRequest(request) { const c=request.configuration,b=CONSOLE.scenario_bounds;const errors=[];if(c.fleet_size<b.fleet_size[0]||c.fleet_size>b.fleet_size[1])errors.push('fleet_size outside bounds');if(c.capacity_multiplier<b.capacity_multiplier[0]||c.capacity_multiplier>b.capacity_multiplier[1])errors.push('capacity_multiplier outside bounds');if(c.injection_fraction<b.injection_fraction[0]||c.injection_fraction>b.injection_fraction[1])errors.push('injection_fraction outside bounds');if(c.horizon_steps<b.horizon_steps[0]||c.horizon_steps>b.horizon_steps[1])errors.push('horizon_steps outside bounds');return errors; }
function updateRequest() { const request=currentRequest();const errors=validateRequest(request);document.getElementById('requestPreview').textContent=JSON.stringify({...request,validation:errors.length?{status:'rejected',errors}:{status:'bounded_and_ready_for_local_builder'}},null,2); }
function download(name,value) { const blob=new Blob([JSON.stringify(value,null,2)],{type:'application/json'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=name;link.click();URL.revokeObjectURL(link.href); }

function renderProvenance() { const body=document.getElementById('integrityRows');body.innerHTML='';PRIMARY.integrity_checks.forEach(check=>{const tr=document.createElement('tr');[check.path,check.bytes,check.status,check.expected_sha256||'not listed',check.actual_sha256||'not checked'].forEach(value=>{const td=document.createElement('td');td.textContent=String(value);tr.appendChild(td);});body.appendChild(tr);});document.getElementById('rawEvidence').textContent=JSON.stringify(PRIMARY.evidence,null,2); }
function renderAll() { initializeOverview();renderStage3A();renderStage3B();renderProvenance();updateRequest(); }

document.querySelectorAll('nav button').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('nav button').forEach(item=>item.classList.remove('active'));document.querySelectorAll('.tab').forEach(item=>item.classList.remove('active'));button.classList.add('active');document.getElementById(button.dataset.tab).classList.add('active');}));
['aScenario','aResource'].forEach(id=>document.getElementById(id).addEventListener('change',renderStage3A));
document.getElementById('bScenario').addEventListener('change',renderStage3B);
document.getElementById('timeSlider').addEventListener('input',updateTimeline);
document.getElementById('play').addEventListener('click',()=>{if(timer)return;timer=setInterval(()=>{const slider=document.getElementById('timeSlider');if(num(slider.value)>=num(slider.max)){clearInterval(timer);timer=null;return;}slider.value=String(num(slider.value)+1);updateTimeline();},180);});
document.getElementById('pause').addEventListener('click',()=>{if(timer){clearInterval(timer);timer=null;}});
document.getElementById('downloadEvidence').addEventListener('click',()=>download('stage3_console_evidence.json',CONSOLE));
document.getElementById('downloadRequest').addEventListener('click',()=>{const request=currentRequest(),errors=validateRequest(request);if(errors.length){alert(errors.join('\n'));return;}download('stage3_visual_run_request.json',request);});
['cfgFleet','cfgAdmission','cfgCapacity','cfgTopology','cfgAttack','cfgInjection','cfgFraction','cfgHorizon','cfgSeed'].forEach(id=>document.getElementById(id).addEventListener('input',updateRequest));
document.getElementById('modeSelect').addEventListener('change',event=>{const mode=event.target.value;if(mode==='comparison'&&!COMPARISON){alert('No comparison execution is embedded.');event.target.value='replay';return;}document.getElementById('evidenceBoundary').textContent=(mode==='live'?'Live mode animates a completed immutable demonstration. It does not stream or mutate simulation state. ':mode==='comparison'?'Comparison mode overlays two immutable execution projections. ':'Replay mode reads one immutable execution projection. ')+'Evidence scope: '+text(PRIMARY.execution.evidence_scope)+'.';renderAll();});
initializeHeader();initializeSelectors();renderAll();
</script>
</body>
</html>
'''


__all__ = [
    "ADMISSION_PATTERNS",
    "ATTACK_CLASSES",
    "INJECTIONS",
    "TOPOLOGIES",
    "ConsoleLimits",
    "Stage3ConsoleBundle",
    "Stage3ScenarioConfig",
    "build_stage3_console",
    "discover_stage3_executions",
    "export_stage3_console_json",
    "load_stage3_execution",
    "run_visual_scenario",
    "write_scenario_request",
]
