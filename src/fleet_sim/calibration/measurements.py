"""Strict CSV and Parquet ingestion for assurance-resource measurements."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from fleet_sim.control_plane.resource_network import ResourceType

REQUIRED_COLUMNS = (
    "timestamp",
    "resource_id",
    "resource_type",
    "fleet_size",
    "agents_admitted",
    "arrival_count",
    "service_count",
    "queue_depth",
    "service_time_ms",
    "wait_time_ms",
    "capacity_units_per_second",
    "deadline_ms",
    "dropped_work",
    "deferred_work",
    "error_count",
    "source_type",
    "measurement_provenance",
)
INTEGER_COLUMNS = (
    "fleet_size",
    "agents_admitted",
    "arrival_count",
    "service_count",
    "error_count",
)
NONNEGATIVE_COLUMNS = (
    *INTEGER_COLUMNS,
    "queue_depth",
    "service_time_ms",
    "wait_time_ms",
    "dropped_work",
    "deferred_work",
)
POSITIVE_COLUMNS = ("capacity_units_per_second", "deadline_ms")
SOURCE_TYPES = {"measured", "replayed", "synthetic"}
OPTIONAL_COLUMNS = {"window_duration_ms"}


@dataclass(frozen=True, slots=True)
class MeasurementDataset:
    frame: pd.DataFrame
    source_path: Path
    source_sha256: str
    dataset_id: str
    evidence_scope: str

    @property
    def row_count(self) -> int:
        return len(self.frame)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_schema_contract(schema_path: Path) -> None:
    schema: dict[str, Any] = json.loads(schema_path.read_text(encoding="utf-8"))
    required = set(schema.get("required", []))
    missing = set(REQUIRED_COLUMNS).difference(required)
    if missing:
        raise ValueError(f"measurement schema is missing required fields: {sorted(missing)}")
    resource_values = set(schema.get("properties", {}).get("resource_type", {}).get("enum", []))
    if resource_values != {item.value for item in ResourceType}:
        raise ValueError("measurement schema resource types differ from the software model")


def _numeric(frame: pd.DataFrame, column: str) -> np.ndarray:
    converted = pd.to_numeric(frame[column], errors="coerce").to_numpy(float)
    if not np.isfinite(converted).all():
        indexes = np.flatnonzero(~np.isfinite(converted)).tolist()
        raise ValueError(f"{column} contains nonfinite or nonnumeric values at rows {indexes[:10]}")
    return converted


def validate_assurance_measurements(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a canonical validated copy or raise a precise ValueError."""
    missing = set(REQUIRED_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"measurement data is missing columns: {sorted(missing)}")
    unexpected = set(frame.columns).difference(REQUIRED_COLUMNS).difference(OPTIONAL_COLUMNS)
    if unexpected:
        raise ValueError(f"measurement data has unsupported columns: {sorted(unexpected)}")
    if len(frame) == 0:
        raise ValueError("measurement data cannot be empty")
    validated = frame.copy()

    parsed_time = pd.to_datetime(validated["timestamp"], utc=True, errors="coerce")
    if parsed_time.isna().any():
        indexes = parsed_time.index[parsed_time.isna()].tolist()
        raise ValueError(f"timestamp contains invalid values at rows {indexes[:10]}")
    validated["timestamp"] = parsed_time

    for column in ("resource_id", "resource_type", "source_type", "measurement_provenance"):
        if validated[column].isna().any():
            raise ValueError(f"{column} cannot contain null values")
        values = validated[column].astype(str).str.strip()
        if values.eq("").any():
            indexes = values.index[values.eq("")].tolist()
            raise ValueError(f"{column} cannot be empty at rows {indexes[:10]}")
        validated[column] = values

    unsupported_resources = sorted(
        set(validated["resource_type"]).difference(item.value for item in ResourceType)
    )
    if unsupported_resources:
        raise ValueError(f"unsupported resource_type values: {unsupported_resources}")
    unsupported_sources = sorted(set(validated["source_type"]).difference(SOURCE_TYPES))
    if unsupported_sources:
        raise ValueError(f"unsupported source_type values: {unsupported_sources}")

    for column in NONNEGATIVE_COLUMNS:
        values = _numeric(validated, column)
        if (values < 0.0).any():
            indexes = np.flatnonzero(values < 0.0).tolist()
            raise ValueError(f"{column} must be nonnegative at rows {indexes[:10]}")
        validated[column] = values
    for column in POSITIVE_COLUMNS:
        values = _numeric(validated, column)
        if (values <= 0.0).any():
            indexes = np.flatnonzero(values <= 0.0).tolist()
            raise ValueError(f"{column} must be positive at rows {indexes[:10]}")
        validated[column] = values
    if "window_duration_ms" in validated.columns:
        values = _numeric(validated, "window_duration_ms")
        if (values <= 0.0).any():
            indexes = np.flatnonzero(values <= 0.0).tolist()
            raise ValueError(f"window_duration_ms must be positive at rows {indexes[:10]}")
        validated["window_duration_ms"] = values

    for column in INTEGER_COLUMNS:
        values = validated[column].to_numpy(float)
        if not np.equal(values, np.floor(values)).all():
            indexes = np.flatnonzero(values != np.floor(values)).tolist()
            raise ValueError(f"{column} must contain integer values at rows {indexes[:10]}")
        validated[column] = values.astype(np.int64)

    duplicate = validated.duplicated(["timestamp", "resource_id"], keep=False)
    if duplicate.any():
        records = validated.loc[duplicate, ["timestamp", "resource_id"]].head(10).to_dict("records")
        raise ValueError(f"duplicate timestamp and resource_id observations: {records}")
    type_counts = validated.groupby("resource_id")["resource_type"].nunique()
    inconsistent = type_counts[type_counts != 1]
    if len(inconsistent):
        raise ValueError(
            f"resource_id maps to multiple resource types: {sorted(inconsistent.index)}"
        )

    return validated.sort_values(["resource_id", "timestamp"], kind="mergesort").reset_index(
        drop=True
    )


def _evidence_scope(frame: pd.DataFrame) -> str:
    source_types = set(frame["source_type"])
    if "synthetic" in source_types:
        return "interface_verification_only"
    if source_types == {"measured"}:
        return "external_measurement_calibration"
    return "replayed_measurement_calibration"


def read_assurance_measurements(
    path: str | Path,
    *,
    schema_path: str | Path | None = None,
) -> MeasurementDataset:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if schema_path is not None:
        _validate_schema_contract(Path(schema_path))
    suffix = source.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(source)
    elif suffix in {".parquet", ".pq"}:
        try:
            frame = pd.read_parquet(source)
        except ImportError as exc:
            raise RuntimeError("Parquet input requires the optional pyarrow dependency") from exc
    else:
        raise ValueError(f"unsupported measurement format: {source.suffix}")
    validated = validate_assurance_measurements(frame)
    canonical = validated.copy()
    canonical["timestamp"] = canonical["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    digest = hashlib.sha256(canonical.to_csv(index=False).encode("utf-8")).hexdigest()
    return MeasurementDataset(
        frame=validated,
        source_path=source.resolve(),
        source_sha256=_sha256(source),
        dataset_id=f"assurance-measurements-{digest[:16]}",
        evidence_scope=_evidence_scope(validated),
    )


def write_canonical_measurements(
    dataset: MeasurementDataset,
    output_dir: str | Path,
) -> Path:
    """Write an immutable normalized Parquet dataset and import manifest."""
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing output directory: {destination}")
    if (
        importlib.util.find_spec("pyarrow") is None
        and importlib.util.find_spec("fastparquet") is None
    ):
        raise RuntimeError("Parquet output requires pyarrow or fastparquet")
    destination.mkdir(parents=True)
    parquet_path = destination / "measurements.parquet"
    try:
        dataset.frame.to_parquet(parquet_path, index=False)
    except ImportError as exc:
        raise RuntimeError("Parquet output requires the optional pyarrow dependency") from exc
    manifest = {
        "dataset_id": dataset.dataset_id,
        "row_count": dataset.row_count,
        "source_path": str(dataset.source_path),
        "source_sha256": dataset.source_sha256,
        "evidence_scope": dataset.evidence_scope,
        "external_validation": False,
        "normalized_artifact": "measurements.parquet",
        "normalized_sha256": _sha256(parquet_path),
    }
    (destination / "import_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return destination
