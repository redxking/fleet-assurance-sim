"""Provenance-bound intake for empirical assurance-resource campaigns.

This module is intentionally separate from the completed Stage 3 execution.
It validates candidate evidence for a successor study, but it never promotes an
imported dataset to external validation and it does not execute a scientific run.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
import platform
import re
import shutil
import stat
import tempfile
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

import numpy as np
import pandas as pd

from fleet_sim.calibration.measurements import (
    INTEGER_COLUMNS,
    NONNEGATIVE_COLUMNS,
    OPTIONAL_COLUMNS,
    POSITIVE_COLUMNS,
    REQUIRED_COLUMNS,
    validate_assurance_measurements,
)
from fleet_sim.control_plane.resource_network import ResourceType

CAMPAIGN_SCHEMA_VERSION = "1.0"
CAMPAIGN_SOURCE_TYPES = {"measured", "replayed", "synthetic", "mixed"}
PARTITIONS = {"calibration", "heldout"}
ALLOWED_USES = {"research_calibration", "research_validation", "reproducibility"}
DATA_CLASSIFICATIONS = {"public", "synthetic"}
WINDOW_SEMANTICS = {"fixed_nonoverlapping", "fixed_overlapping", "event_bounded"}
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

EXTENSION_COLUMNS = (
    "campaign_id",
    "time_block_id",
    "partition",
    "is_censored",
    "missing_fraction",
)
CAMPAIGN_FIELDS = {
    "schema_version",
    "campaign_id",
    "source_type",
    "site_alias",
    "system_alias",
    "collection_start",
    "collection_end",
    "authority",
    "instrumentation",
    "units",
}
EMPIRICAL_MEASUREMENT_COLUMNS = {
    *REQUIRED_COLUMNS,
    *OPTIONAL_COLUMNS,
    *EXTENSION_COLUMNS,
}

UNIT_CONTRACT = {
    "fleet_size": "agent_count",
    "agents_admitted": "agent_count",
    "arrival_count": "work_unit_count",
    "service_count": "work_unit_count",
    "queue_depth": "work_unit",
    "service_time_ms": "millisecond",
    "wait_time_ms": "millisecond",
    "capacity_units_per_second": "work_unit/second",
    "deadline_ms": "millisecond",
    "dropped_work": "work_unit",
    "deferred_work": "work_unit",
    "error_count": "event_count",
    "window_duration_ms": "millisecond",
}

PACKAGE_FILES = {
    "campaign_manifest.json",
    "campaign_schema.json",
    "calibration_measurements.parquet",
    "heldout_measurements.parquet",
    "measurement_schema.json",
    "quality_report.json",
    "evidence_manifest.json",
}
TRUSTED_SCHEMA_SHA256 = {
    "Empirical assurance campaign": (
        "b899a1f9809d7b071766129cb1f782b17c5db34d90304c65e6001df2ea3be43d"
    ),
    "Empirical assurance resource measurement": (
        "4692233b9cac4bef5e041fcededf55b28e6fda1d9dfdfcf6ceec4eacd2331f4e"
    ),
}
MAX_PACKAGE_BYTES = 512 * 1024 * 1024
MAX_PACKAGE_ROWS = 5_000_000
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class EmpiricalCampaignInput:
    """Validated in-memory campaign before immutable packaging."""

    _frame: pd.DataFrame
    _campaign_manifest: dict[str, object]
    dataset_id: str
    evidence_scope: str
    measurement_source_path: Path
    measurement_source_sha256: str
    campaign_source_path: Path
    campaign_source_sha256: str
    campaign_schema_path: Path
    campaign_schema_sha256: str
    _campaign_schema_bytes: bytes
    measurement_schema_path: Path
    measurement_schema_sha256: str
    _measurement_schema_bytes: bytes

    @property
    def frame(self) -> pd.DataFrame:
        return self._frame.copy(deep=True)

    @property
    def campaign_manifest(self) -> dict[str, object]:
        return deepcopy(self._campaign_manifest)

    @property
    def calibration(self) -> pd.DataFrame:
        return self._frame[self._frame["partition"] == "calibration"].copy(deep=True).reset_index(
            drop=True
        )

    @property
    def heldout(self) -> pd.DataFrame:
        return self._frame[self._frame["partition"] == "heldout"].copy(deep=True).reset_index(
            drop=True
        )


@dataclass(frozen=True, slots=True)
class CampaignPackageVerification:
    """Integrity-checked package view for later engineering review."""

    package_dir: Path
    dataset_id: str
    evidence_scope: str
    external_validation: bool
    scientific_use_authorized: bool
    evidence_manifest_sha256: str
    externally_digest_bound: bool
    _calibration: pd.DataFrame
    _heldout: pd.DataFrame
    _evidence_manifest: dict[str, object]

    @property
    def calibration(self) -> pd.DataFrame:
        return self._calibration.copy(deep=True)

    @property
    def heldout(self) -> pd.DataFrame:
        return self._heldout.copy(deep=True)

    @property
    def evidence_manifest(self) -> dict[str, object]:
        return deepcopy(self._evidence_manifest)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"nonfinite JSON value is not allowed: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key is not allowed: {key}")
        result[key] = value
    return result


def _read_json_bytes(data: bytes, display_name: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            data.decode("utf-8"),
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON in {display_name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise TypeError(f"{display_name} must contain one JSON object")
    return payload


def _read_json(path: Path) -> dict[str, Any]:
    return _read_json_bytes(path.read_bytes(), path.name)


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _exact_keys(value: object, expected: set[str], context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{context} must be an object")
    actual = set(value)
    missing = expected.difference(actual)
    unexpected = actual.difference(expected)
    if missing:
        raise ValueError(f"{context} is missing fields: {sorted(missing)}")
    if unexpected:
        raise ValueError(f"{context} has unsupported fields: {sorted(unexpected)}")
    return value


def _nonempty(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} must be a nonempty string")
    return value.strip()


def _safe_identifier(value: object, context: str) -> str:
    selected = _nonempty(value, context)
    if not SAFE_IDENTIFIER.fullmatch(selected):
        raise ValueError(f"{context} must be a safe portable identifier")
    return selected


def _portable_reference(value: object, context: str) -> str:
    selected = _nonempty(value, context)
    if (
        selected.startswith(("/", "~", "file:"))
        or re.match(r"^[A-Za-z]:[\\/]", selected)
        or "\x00" in selected
        or any(part == ".." for part in re.split(r"[\\/]", selected))
    ):
        raise ValueError(f"{context} must not contain a local or traversing path")
    return selected


def _strict_bool(value: object, context: str) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    raise ValueError(f"{context} must be Boolean")


def _measurement_bool(value: object, context: str) -> bool:
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return _strict_bool(value, context)


def _positive_number(value: object, context: str) -> float:
    if isinstance(value, bool) or not isinstance(
        value, (int, float, np.integer, np.floating)
    ):
        raise TypeError(f"{context} must be numeric")
    selected = float(value)
    if not np.isfinite(selected) or selected <= 0.0:
        raise ValueError(f"{context} must be finite and positive")
    return selected


def _canonical_timestamp(value: object, context: str) -> str:
    selected = _nonempty(value, context)
    try:
        parsed = pd.Timestamp(selected)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} must be a timezone-aware date-time") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{context} must be a timezone-aware date-time")
    return parsed.tz_convert("UTC").isoformat().replace("+00:00", "Z")


def _nonnegative_integer(value: object, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise TypeError(f"{context} must be an integer")
    selected = int(value)
    if selected < 0:
        raise ValueError(f"{context} must be nonnegative")
    return selected


def _sha256_string(value: object, context: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{context} must be a lowercase SHA-256 digest")
    return value


def _validate_schema_bytes(
    schema_bytes: bytes,
    display_name: str,
    expected_title: str,
    expected_fields: set[str],
) -> str:
    schema = _read_json_bytes(schema_bytes, display_name)
    if schema.get("title") != expected_title:
        raise ValueError(f"{display_name} does not match the expected schema title")
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise ValueError(f"{display_name} must define a closed object schema")
    required = schema.get("required")
    properties = schema.get("properties")
    if not isinstance(required, list) or set(required) != expected_fields:
        raise ValueError(f"{display_name} required fields differ from the runtime contract")
    if not isinstance(properties, Mapping) or set(properties) != expected_fields:
        raise ValueError(f"{display_name} properties differ from the runtime contract")
    if expected_title == "Empirical assurance resource measurement":
        resource_property = properties.get("resource_type")
        if not isinstance(resource_property, Mapping) or set(
            resource_property.get("enum", [])
        ) != {item.value for item in ResourceType}:
            raise ValueError(f"{display_name} resource types differ from the software model")
    digest = _sha256_bytes(schema_bytes)
    if digest != TRUSTED_SCHEMA_SHA256[expected_title]:
        raise ValueError(f"{display_name} is not the trusted {expected_title} schema")
    return digest


def _validate_schema_file(
    path: Path,
    expected_title: str,
    expected_fields: set[str],
) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    return _validate_schema_bytes(
        path.read_bytes(), path.name, expected_title, expected_fields
    )


def _open_regular_file_for_read(path: Path) -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ValueError(f"input must be a regular local file: {path.name}")
    return descriptor


def _snapshot_file(source: Path, destination: Path, *, maximum_bytes: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_count = 0
    descriptor = _open_regular_file_for_read(source)
    before = os.fstat(descriptor)
    with os.fdopen(descriptor, "rb") as input_stream, destination.open("xb") as output_stream:
        for chunk in iter(lambda: input_stream.read(1024 * 1024), b""):
            byte_count += len(chunk)
            if byte_count > maximum_bytes:
                raise ValueError(f"input exceeds the {maximum_bytes}-byte intake limit")
            digest.update(chunk)
            output_stream.write(chunk)
        after = os.fstat(input_stream.fileno())
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ValueError(f"input changed while it was being snapshotted: {source.name}")
    return digest.hexdigest(), byte_count


def _read_regular_file(path: Path, *, maximum_bytes: int) -> bytes:
    descriptor = _open_regular_file_for_read(path)
    before = os.fstat(descriptor)
    chunks: list[bytes] = []
    byte_count = 0
    with os.fdopen(descriptor, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            byte_count += len(chunk)
            if byte_count > maximum_bytes:
                raise ValueError(f"file exceeds the {maximum_bytes}-byte verification limit")
            chunks.append(chunk)
        after = os.fstat(stream.fileno())
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ValueError(f"file changed while it was being verified: {path.name}")
    return b"".join(chunks)


def validate_campaign_manifest(payload: Mapping[str, object]) -> dict[str, object]:
    """Return a canonical campaign manifest or fail closed."""

    top = _exact_keys(
        payload,
        CAMPAIGN_FIELDS,
        "campaign manifest",
    )
    if top["schema_version"] != CAMPAIGN_SCHEMA_VERSION:
        raise ValueError(
            f"campaign schema_version must be {CAMPAIGN_SCHEMA_VERSION}"
        )
    source_type = _nonempty(top["source_type"], "campaign source_type")
    if source_type not in CAMPAIGN_SOURCE_TYPES:
        raise ValueError(f"unsupported campaign source_type: {source_type}")
    campaign_id = _safe_identifier(top["campaign_id"], "campaign_id")
    site_alias = _safe_identifier(top["site_alias"], "site_alias")
    system_alias = _safe_identifier(top["system_alias"], "system_alias")
    collection_start = _canonical_timestamp(top["collection_start"], "collection_start")
    collection_end = _canonical_timestamp(top["collection_end"], "collection_end")
    if pd.Timestamp(collection_end) <= pd.Timestamp(collection_start):
        raise ValueError("collection_end must be later than collection_start")

    authority = _exact_keys(
        top["authority"],
        {
            "collection_authorized",
            "authorization_reference",
            "data_rights_confirmed",
            "data_rights_reference",
            "data_classification",
            "allowed_uses",
        },
        "authority",
    )
    collection_authorized = _strict_bool(
        authority["collection_authorized"], "authority.collection_authorized"
    )
    data_rights_confirmed = _strict_bool(
        authority["data_rights_confirmed"], "authority.data_rights_confirmed"
    )
    authorization_reference = _portable_reference(
        authority["authorization_reference"], "authority.authorization_reference"
    )
    data_rights_reference = _portable_reference(
        authority["data_rights_reference"], "authority.data_rights_reference"
    )
    classification = _nonempty(
        authority["data_classification"], "authority.data_classification"
    )
    if classification not in DATA_CLASSIFICATIONS:
        raise ValueError(f"unsupported data classification: {classification}")
    allowed_uses_raw = authority["allowed_uses"]
    if not isinstance(allowed_uses_raw, list) or not allowed_uses_raw:
        raise ValueError("authority.allowed_uses must be a nonempty array")
    selected_uses = [
        _nonempty(item, "authority.allowed_uses item") for item in allowed_uses_raw
    ]
    if len(selected_uses) != len(set(selected_uses)):
        raise ValueError("authority.allowed_uses cannot contain duplicates")
    allowed_uses = sorted(selected_uses)
    unsupported_uses = set(allowed_uses).difference(ALLOWED_USES)
    if unsupported_uses:
        raise ValueError(f"unsupported allowed uses: {sorted(unsupported_uses)}")
    required_uses = {"research_calibration", "research_validation"}
    if not required_uses.issubset(allowed_uses):
        raise ValueError(
            "allowed_uses must include research_calibration and research_validation"
        )
    if not data_rights_confirmed:
        raise ValueError("data rights must be confirmed before campaign intake")

    instrumentation = _exact_keys(
        top["instrumentation"],
        {
            "environment_description",
            "collector_name",
            "collector_version",
            "clock_source",
            "sampling_interval_ms",
            "window_semantics",
            "known_gaps",
            "missingness_handling",
            "censoring_handling",
            "quality_reviewed",
            "quality_review_reference",
            "transformation_description",
        },
        "instrumentation",
    )
    canonical_instrumentation = {
        "environment_description": _nonempty(
            instrumentation["environment_description"],
            "instrumentation.environment_description",
        ),
        "collector_name": _nonempty(
            instrumentation["collector_name"], "instrumentation.collector_name"
        ),
        "collector_version": _nonempty(
            instrumentation["collector_version"], "instrumentation.collector_version"
        ),
        "clock_source": _nonempty(
            instrumentation["clock_source"], "instrumentation.clock_source"
        ),
        "sampling_interval_ms": _positive_number(
            instrumentation["sampling_interval_ms"],
            "instrumentation.sampling_interval_ms",
        ),
        "window_semantics": _nonempty(
            instrumentation["window_semantics"], "instrumentation.window_semantics"
        ),
        "known_gaps": _nonempty(
            instrumentation["known_gaps"], "instrumentation.known_gaps"
        ),
        "missingness_handling": _nonempty(
            instrumentation["missingness_handling"],
            "instrumentation.missingness_handling",
        ),
        "censoring_handling": _nonempty(
            instrumentation["censoring_handling"],
            "instrumentation.censoring_handling",
        ),
        "quality_reviewed": _strict_bool(
            instrumentation["quality_reviewed"], "instrumentation.quality_reviewed"
        ),
        "quality_review_reference": _portable_reference(
            instrumentation["quality_review_reference"],
            "instrumentation.quality_review_reference",
        ),
        "transformation_description": _nonempty(
            instrumentation["transformation_description"],
            "instrumentation.transformation_description",
        ),
    }
    if canonical_instrumentation["window_semantics"] not in WINDOW_SEMANTICS:
        raise ValueError(
            "instrumentation.window_semantics is not supported"
        )

    if source_type != "synthetic":
        if not collection_authorized:
            raise ValueError("nonsynthetic collection must be explicitly authorized")
        if not canonical_instrumentation["quality_reviewed"]:
            raise ValueError("nonsynthetic instrumentation quality must be reviewed")
        if classification == "synthetic":
            raise ValueError("nonsynthetic input cannot use synthetic classification")
    elif classification != "synthetic":
        raise ValueError("synthetic input must use synthetic classification")

    units = _exact_keys(top["units"], set(UNIT_CONTRACT), "units")
    canonical_units = {
        key: _nonempty(units[key], f"units.{key}") for key in sorted(UNIT_CONTRACT)
    }
    mismatched_units = {
        key: (canonical_units[key], expected)
        for key, expected in UNIT_CONTRACT.items()
        if canonical_units[key] != expected
    }
    if mismatched_units:
        raise ValueError(f"measurement units do not match the contract: {mismatched_units}")

    return {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "source_type": source_type,
        "site_alias": site_alias,
        "system_alias": system_alias,
        "collection_start": collection_start,
        "collection_end": collection_end,
        "authority": {
            "collection_authorized": collection_authorized,
            "authorization_reference": authorization_reference,
            "data_rights_confirmed": data_rights_confirmed,
            "data_rights_reference": data_rights_reference,
            "data_classification": classification,
            "allowed_uses": allowed_uses,
        },
        "instrumentation": canonical_instrumentation,
        "units": canonical_units,
    }


def _read_measurement_frame(
    path: Path,
    *,
    maximum_rows: int,
    maximum_uncompressed_bytes: int,
) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        string_columns = {
            "timestamp",
            "resource_id",
            "resource_type",
            "source_type",
            "measurement_provenance",
            "campaign_id",
            "time_block_id",
            "partition",
            "is_censored",
        }
        frame = pd.read_csv(
            path,
            dtype={column: "string" for column in string_columns},
            keep_default_na=False,
            nrows=maximum_rows + 1,
        )
        if len(frame) > maximum_rows:
            raise ValueError(f"measurement source exceeds the {maximum_rows}-row limit")
        return frame
    if suffix in {".parquet", ".pq"}:
        try:
            import pyarrow.parquet
        except ImportError as exc:
            raise RuntimeError("Parquet input requires the optional pyarrow dependency") from exc
        metadata = pyarrow.parquet.ParquetFile(path).metadata
        if metadata.num_rows > maximum_rows:
            raise ValueError(f"measurement source exceeds the {maximum_rows}-row limit")
        uncompressed_bytes = sum(
            metadata.row_group(index).total_byte_size
            for index in range(metadata.num_row_groups)
        )
        if uncompressed_bytes > maximum_uncompressed_bytes:
            raise ValueError(
                "measurement source exceeds the uncompressed-byte verification limit"
            )
        return pd.read_parquet(path)
    raise ValueError(f"unsupported empirical measurement format: {path.suffix}")


def _validated_extensions(frame: pd.DataFrame) -> pd.DataFrame:
    extension = frame[["timestamp", "resource_id", *EXTENSION_COLUMNS]].copy()
    extension["timestamp"] = pd.to_datetime(extension["timestamp"], utc=True, errors="coerce")
    if extension["timestamp"].isna().any():
        raise ValueError("empirical extension contains invalid timestamps")
    for column in ("campaign_id", "time_block_id", "partition"):
        if extension[column].isna().any():
            raise ValueError(f"{column} cannot contain null values")
        extension[column] = [
            _safe_identifier(value, f"{column} row {index}")
            for index, value in enumerate(extension[column])
        ]
    extension["is_censored"] = [
        _measurement_bool(value, f"is_censored row {index}")
        for index, value in enumerate(extension["is_censored"])
    ]
    missing = pd.to_numeric(extension["missing_fraction"], errors="coerce").to_numpy(float)
    if not np.isfinite(missing).all() or ((missing < 0.0) | (missing > 1.0)).any():
        indexes = np.flatnonzero(~np.isfinite(missing) | (missing < 0.0) | (missing > 1.0))
        raise ValueError(
            f"missing_fraction must be finite and within [0, 1] at rows {indexes[:10].tolist()}"
        )
    extension["missing_fraction"] = missing
    return extension


def _explicit_utc_timestamps(values: pd.Series) -> pd.Series:
    normalized: list[pd.Timestamp] = []
    for index, value in enumerate(values):
        try:
            parsed = pd.Timestamp(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"timestamp is invalid at row {index}") from exc
        if parsed.tzinfo is None:
            raise ValueError(f"timestamp must include an explicit UTC offset at row {index}")
        normalized.append(parsed.tz_convert("UTC"))
    return pd.Series(normalized, index=values.index, dtype="datetime64[ns, UTC]")


def _exact_integer_columns(frame: pd.DataFrame) -> pd.DataFrame:
    exact = frame.copy()
    maximum = int(np.iinfo(np.int64).max)
    for column in INTEGER_COLUMNS:
        converted: list[int] = []
        for index, value in enumerate(frame[column]):
            if isinstance(value, bool):
                raise TypeError(f"{column} must contain integers, not Boolean values")
            if isinstance(value, (int, np.integer)) or (
                isinstance(value, str) and re.fullmatch(r"[0-9]+", value)
            ):
                selected = int(value)
            else:
                raise ValueError(f"{column} must contain exact integers at row {index}")
            if selected < 0 or selected > maximum:
                raise ValueError(
                    f"{column} must be within the nonnegative int64 range at row {index}"
                )
            converted.append(selected)
        exact[column] = pd.Series(
            np.asarray(converted, dtype=np.int64), index=frame.index
        )
    return exact


def validate_campaign_measurements(
    frame: pd.DataFrame,
    campaign_manifest: Mapping[str, object],
) -> pd.DataFrame:
    """Validate the extended empirical table and preserve partition discipline."""

    canonical_manifest = validate_campaign_manifest(campaign_manifest)
    required = EMPIRICAL_MEASUREMENT_COLUMNS
    missing_columns = required.difference(frame.columns)
    if missing_columns:
        raise ValueError(
            f"empirical measurement data is missing columns: {sorted(missing_columns)}"
        )
    unexpected = set(frame.columns).difference(required)
    if unexpected:
        raise ValueError(
            f"empirical measurement data has unsupported columns: {sorted(unexpected)}"
        )
    for column in (
        "resource_id",
        "resource_type",
        "source_type",
        "measurement_provenance",
        "campaign_id",
        "time_block_id",
        "partition",
    ):
        if not frame[column].map(lambda value: isinstance(value, str)).all():
            raise ValueError(f"{column} values must be strings")
    numeric_columns = {
        *NONNEGATIVE_COLUMNS,
        *POSITIVE_COLUMNS,
        *OPTIONAL_COLUMNS,
        "missing_fraction",
    }
    for column in numeric_columns:
        if frame[column].map(lambda value: isinstance(value, (bool, np.bool_))).any():
            raise TypeError(f"{column} cannot contain Boolean values")
    prepared = _exact_integer_columns(frame)
    prepared["timestamp"] = _explicit_utc_timestamps(prepared["timestamp"])
    base_columns = [*REQUIRED_COLUMNS, *sorted(OPTIONAL_COLUMNS)]
    legacy_safe = prepared[base_columns].copy()
    for column in INTEGER_COLUMNS:
        legacy_safe[column] = np.int64(0)
    base = validate_assurance_measurements(legacy_safe)
    exact_counts = prepared[["timestamp", "resource_id", *INTEGER_COLUMNS]]
    base = base.drop(columns=list(INTEGER_COLUMNS)).merge(
        exact_counts,
        on=["timestamp", "resource_id"],
        how="left",
        validate="one_to_one",
    )
    extension = _validated_extensions(prepared)
    validated = base.merge(
        extension,
        on=["timestamp", "resource_id"],
        how="left",
        validate="one_to_one",
    )
    if validated[list(EXTENSION_COLUMNS)].isna().any().any():
        raise ValueError("empirical extension rows do not match validated measurements")

    campaign_id = str(canonical_manifest["campaign_id"])
    if set(validated["campaign_id"]) != {campaign_id}:
        raise ValueError("measurement campaign_id does not match the campaign manifest")
    unsupported_partitions = set(validated["partition"]).difference(PARTITIONS)
    if unsupported_partitions:
        raise ValueError(f"unsupported partition values: {sorted(unsupported_partitions)}")
    if set(validated["partition"]) != PARTITIONS:
        raise ValueError("campaign must contain both calibration and heldout partitions")

    manifest_source = str(canonical_manifest["source_type"])
    row_sources = set(validated["source_type"])
    if manifest_source == "mixed":
        if len(row_sources) < 2:
            raise ValueError("mixed campaign must contain at least two row source types")
    elif row_sources != {manifest_source}:
        raise ValueError(
            "measurement source_type values do not match the campaign manifest"
        )

    start = pd.Timestamp(str(canonical_manifest["collection_start"]))
    end = pd.Timestamp(str(canonical_manifest["collection_end"]))
    window_ends = validated["timestamp"] + pd.to_timedelta(
        validated["window_duration_ms"], unit="ms"
    )
    outside = (validated["timestamp"] < start) | (window_ends > end)
    if outside.any():
        indexes = validated.index[outside].tolist()
        raise ValueError(
            "measurement windows fall outside the declared collection window: "
            f"{indexes[:10]}"
        )

    block_partitions = validated.groupby("time_block_id")["partition"].nunique()
    overlapping = block_partitions[block_partitions != 1]
    if len(overlapping):
        raise ValueError(
            "time_block_id values cannot cross calibration and heldout partitions: "
            f"{sorted(overlapping.index)}"
        )

    calibration_end = window_ends[validated["partition"] == "calibration"].max()
    heldout_start = validated.loc[
        validated["partition"] == "heldout", "timestamp"
    ].min()
    if calibration_end > heldout_start:
        raise ValueError(
            "calibration windows must end before the prospective heldout partition begins"
        )

    instrumentation = _exact_keys(
        canonical_manifest["instrumentation"],
        {
            "environment_description",
            "collector_name",
            "collector_version",
            "clock_source",
            "sampling_interval_ms",
            "window_semantics",
            "known_gaps",
            "missingness_handling",
            "censoring_handling",
            "quality_reviewed",
            "quality_review_reference",
            "transformation_description",
        },
        "canonical campaign instrumentation",
    )
    if instrumentation["window_semantics"] == "fixed_nonoverlapping":
        sampling_interval_ms = float(str(instrumentation["sampling_interval_ms"]))
        if (validated["window_duration_ms"] > sampling_interval_ms).any():
            raise ValueError(
                "fixed_nonoverlapping window duration cannot exceed the sampling interval"
            )
        for resource_id, group in validated.groupby("resource_id", sort=True):
            ordered = group.sort_values("timestamp")
            starts = ordered["timestamp"].reset_index(drop=True)
            ends = (
                ordered["timestamp"]
                + pd.to_timedelta(ordered["window_duration_ms"], unit="ms")
            ).reset_index(drop=True)
            if len(ordered) > 1 and (ends.iloc[:-1].to_numpy() > starts.iloc[1:].to_numpy()).any():
                raise ValueError(
                    "fixed_nonoverlapping windows overlap for resource_id "
                    f"{resource_id}"
                )

    expected_types = {item.value for item in ResourceType}
    for block, group in validated.groupby("time_block_id", sort=True):
        present = set(group["resource_type"])
        if present != expected_types or len(group) != len(expected_types):
            missing = sorted(expected_types.difference(present))
            extra = sorted(present.difference(expected_types))
            raise ValueError(
                f"time block {block} must contain exactly one observation for all ten "
                f"resource types; missing={missing}, extra={extra}"
            )
        if group["timestamp"].nunique() != 1 or group["window_duration_ms"].nunique() != 1:
            raise ValueError(
                f"time block {block} must use one aligned timestamp and window duration"
            )
        if group["fleet_size"].nunique() != 1 or group["agents_admitted"].nunique() != 1:
            raise ValueError(
                f"time block {block} must use one fleet size and admitted-agent count"
            )
    for partition, group in validated.groupby("partition", sort=True):
        present = set(group["resource_type"])
        if present != expected_types:
            missing = sorted(expected_types.difference(present))
            extra = sorted(present.difference(expected_types))
            raise ValueError(
                f"{partition} must contain all ten resource types; missing={missing}, extra={extra}"
            )
        identifiers_per_type = group.groupby("resource_type")["resource_id"].nunique()
        ambiguous = identifiers_per_type[identifiers_per_type != 1]
        if len(ambiguous):
            raise ValueError(
                f"{partition} has ambiguous resource mappings without a pooling rule: "
                f"{sorted(ambiguous.index)}"
            )

    resource_map = validated.groupby("resource_type")["resource_id"].nunique()
    inconsistent = resource_map[resource_map != 1]
    if len(inconsistent):
        raise ValueError(
            "resource identifiers must remain stable across partitions: "
            f"{sorted(inconsistent.index)}"
        )

    return validated.sort_values(
        ["partition", "time_block_id", "resource_id", "timestamp"],
        kind="mergesort",
    ).reset_index(drop=True)


def _canonical_frame_bytes(frame: pd.DataFrame) -> bytes:
    columns = [*REQUIRED_COLUMNS, *sorted(OPTIONAL_COLUMNS), *EXTENSION_COLUMNS]
    canonical = frame[columns].sort_values(
        ["partition", "time_block_id", "resource_id", "timestamp"],
        kind="mergesort",
    ).reset_index(drop=True)
    canonical["timestamp"] = canonical["timestamp"].map(
        lambda value: value.tz_convert("UTC").isoformat().replace("+00:00", "Z")
    )
    canonical["is_censored"] = canonical["is_censored"].astype(np.int8)
    return canonical.to_csv(index=False, lineterminator="\n").encode("utf-8")


def _dataset_id(
    manifest: Mapping[str, object],
    frame: pd.DataFrame,
    *,
    campaign_schema_sha256: str,
    measurement_schema_sha256: str,
) -> str:
    digest = hashlib.sha256()
    digest.update(_canonical_json_bytes(manifest))
    digest.update(b"\n")
    digest.update(_canonical_frame_bytes(frame))
    digest.update(b"\n")
    digest.update(campaign_schema_sha256.encode("ascii"))
    digest.update(b"\n")
    digest.update(measurement_schema_sha256.encode("ascii"))
    return f"assurance-campaign-{digest.hexdigest()[:20]}"


def _evidence_scope(frame: pd.DataFrame) -> str:
    source_types = set(frame["source_type"])
    if "synthetic" in source_types:
        return "synthetic_or_mixed_interface_only"
    if source_types == {"measured"}:
        return "measured_input_unreviewed"
    if source_types == {"replayed"}:
        return "replayed_input_unreviewed"
    return "mixed_nonsynthetic_input_unreviewed"


def read_empirical_campaign(
    measurement_path: str | Path,
    campaign_manifest_path: str | Path,
    *,
    campaign_schema_path: str | Path,
    measurement_schema_path: str | Path,
    maximum_source_bytes: int = MAX_PACKAGE_BYTES,
    maximum_rows: int = MAX_PACKAGE_ROWS,
    maximum_uncompressed_bytes: int = MAX_UNCOMPRESSED_BYTES,
) -> EmpiricalCampaignInput:
    """Read, validate, and canonically identify an empirical campaign candidate."""

    measurements = Path(measurement_path)
    campaign_source = Path(campaign_manifest_path)
    campaign_schema = Path(campaign_schema_path)
    measurement_schema = Path(measurement_schema_path)
    if not measurements.is_file():
        raise FileNotFoundError(measurements)
    if not campaign_source.is_file():
        raise FileNotFoundError(campaign_source)
    if (
        maximum_source_bytes <= 0
        or maximum_rows <= 0
        or maximum_uncompressed_bytes <= 0
    ):
        raise ValueError("campaign intake limits must be positive")
    combined_source_bytes = measurements.stat().st_size + campaign_source.stat().st_size
    if combined_source_bytes > maximum_source_bytes:
        raise ValueError(
            f"campaign sources exceed the {maximum_source_bytes}-byte intake limit"
        )
    campaign_schema_bytes = campaign_schema.read_bytes()
    measurement_schema_bytes = measurement_schema.read_bytes()
    campaign_schema_sha256 = _validate_schema_bytes(
        campaign_schema_bytes,
        campaign_schema.name,
        "Empirical assurance campaign",
        CAMPAIGN_FIELDS,
    )
    measurement_schema_sha256 = _validate_schema_bytes(
        measurement_schema_bytes,
        measurement_schema.name,
        "Empirical assurance resource measurement",
        EMPIRICAL_MEASUREMENT_COLUMNS,
    )
    with tempfile.TemporaryDirectory(prefix=".assurance-campaign-intake-") as temporary:
        snapshot_dir = Path(temporary)
        measurement_snapshot = snapshot_dir / f"measurements{measurements.suffix.lower()}"
        campaign_snapshot = snapshot_dir / "campaign.json"
        measurement_source_sha256, measurement_bytes = _snapshot_file(
            measurements,
            measurement_snapshot,
            maximum_bytes=maximum_source_bytes,
        )
        campaign_source_sha256, _ = _snapshot_file(
            campaign_source,
            campaign_snapshot,
            maximum_bytes=maximum_source_bytes - measurement_bytes,
        )
        manifest = validate_campaign_manifest(_read_json(campaign_snapshot))
        frame = validate_campaign_measurements(
            _read_measurement_frame(
                measurement_snapshot,
                maximum_rows=maximum_rows,
                maximum_uncompressed_bytes=maximum_uncompressed_bytes,
            ),
            manifest,
        )
    return EmpiricalCampaignInput(
        _frame=frame.copy(deep=True),
        _campaign_manifest=deepcopy(manifest),
        dataset_id=_dataset_id(
            manifest,
            frame,
            campaign_schema_sha256=campaign_schema_sha256,
            measurement_schema_sha256=measurement_schema_sha256,
        ),
        evidence_scope=_evidence_scope(frame),
        measurement_source_path=measurements.resolve(),
        measurement_source_sha256=measurement_source_sha256,
        campaign_source_path=campaign_source.resolve(),
        campaign_source_sha256=campaign_source_sha256,
        campaign_schema_path=campaign_schema.resolve(),
        campaign_schema_sha256=campaign_schema_sha256,
        _campaign_schema_bytes=bytes(campaign_schema_bytes),
        measurement_schema_path=measurement_schema.resolve(),
        measurement_schema_sha256=measurement_schema_sha256,
        _measurement_schema_bytes=bytes(measurement_schema_bytes),
    )


def _quality_report(frame: pd.DataFrame) -> dict[str, object]:
    partition_rows = {
        str(name): len(group) for name, group in frame.groupby("partition", sort=True)
    }
    partition_blocks = {
        str(name): int(group["time_block_id"].nunique())
        for name, group in frame.groupby("partition", sort=True)
    }
    resource_rows = {
        str(name): len(group)
        for name, group in frame.groupby("resource_type", sort=True)
    }
    quality_actions: list[str] = []
    if bool(frame["is_censored"].any()):
        quality_actions.append("define_and_validate_a_censoring_policy")
    if bool((frame["missing_fraction"] > 0.0).any()):
        quality_actions.append("define_and_validate_a_missingness_policy")
    return {
        "row_count": len(frame),
        "resource_type_count": int(frame["resource_type"].nunique()),
        "partition_rows": partition_rows,
        "partition_time_blocks": partition_blocks,
        "resource_rows": resource_rows,
        "source_types": sorted(set(frame["source_type"])),
        "timestamp_min": frame["timestamp"].min().isoformat().replace("+00:00", "Z"),
        "timestamp_max": frame["timestamp"].max().isoformat().replace("+00:00", "Z"),
        "fleet_size_min": int(frame["fleet_size"].min()),
        "fleet_size_max": int(frame["fleet_size"].max()),
        "censored_row_count": int(frame["is_censored"].sum()),
        "missing_fraction_mean": float(frame["missing_fraction"].mean()),
        "missing_fraction_max": float(frame["missing_fraction"].max()),
        "data_quality_disposition": (
            "requires_missingness_or_censoring_policy"
            if quality_actions
            else "complete_uncensored"
        ),
        "quality_actions_required": quality_actions,
        "scientific_fit_status": "blocked_pending_successor_protocol_and_fit_review",
        "time_block_partition_disjoint": True,
        "all_ten_resources_per_time_block": True,
        "all_ten_resources_per_partition": True,
        "finite_numeric_values": True,
    }


def _artifact_record(path: Path) -> dict[str, object]:
    return {
        "path": path.name,
        "bytes": path.stat().st_size,
        "sha256": _sha256_path(path),
    }


def _implementation_record() -> dict[str, object]:
    package_root = Path(__file__).resolve().parents[1]
    implementation_files = (
        Path(__file__).resolve(),
        package_root / "calibration" / "measurements.py",
        package_root / "control_plane" / "resource_network.py",
    )
    return {
        "files": [
            {
                "path": (Path("fleet_sim") / path.relative_to(package_root)).as_posix(),
                "sha256": _sha256_path(path),
            }
            for path in implementation_files
        ],
        "runtime": {
            "python": platform.python_version(),
            "numpy": importlib.metadata.version("numpy"),
            "pandas": importlib.metadata.version("pandas"),
            "pyarrow": importlib.metadata.version("pyarrow"),
        },
    }


def write_empirical_campaign_package(
    campaign: EmpiricalCampaignInput,
    output_dir: str | Path,
) -> Path:
    """Write a cooperatively locked, no-overwrite, checksum-bound package."""

    destination = Path(output_dir)
    if os.path.lexists(destination):
        raise FileExistsError(f"refusing to overwrite existing campaign package: {destination}")
    if importlib.util.find_spec("pyarrow") is None:
        raise RuntimeError("empirical campaign packaging requires pyarrow")
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock_path = destination.parent / f".{destination.name}.intake.lock"
    try:
        lock_descriptor = os.open(
            lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError as exc:
        raise FileExistsError(
            f"campaign package destination is locked: {destination}"
        ) from exc
    temporary: Path | None = None
    try:
        if os.path.lexists(destination):
            raise FileExistsError(
                f"refusing to overwrite existing campaign package: {destination}"
            )
        temporary = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=str(destination.parent))
        )
        campaign_manifest_path = temporary / "campaign_manifest.json"
        campaign_schema_path = temporary / "campaign_schema.json"
        calibration_path = temporary / "calibration_measurements.parquet"
        heldout_path = temporary / "heldout_measurements.parquet"
        measurement_schema_path = temporary / "measurement_schema.json"
        quality_path = temporary / "quality_report.json"
        evidence_path = temporary / "evidence_manifest.json"

        _write_json(campaign_manifest_path, campaign.campaign_manifest)
        campaign_schema_path.write_bytes(campaign._campaign_schema_bytes)
        campaign.calibration.to_parquet(calibration_path, index=False)
        campaign.heldout.to_parquet(heldout_path, index=False)
        measurement_schema_path.write_bytes(campaign._measurement_schema_bytes)
        quality = _quality_report(campaign.frame)
        _write_json(quality_path, quality)

        instrumentation = _exact_keys(
            campaign.campaign_manifest["instrumentation"],
            {
                "environment_description",
                "collector_name",
                "collector_version",
                "clock_source",
                "sampling_interval_ms",
                "window_semantics",
                "known_gaps",
                "missingness_handling",
                "censoring_handling",
                "quality_reviewed",
                "quality_review_reference",
                "transformation_description",
            },
            "canonical campaign instrumentation",
        )
        transformation = {
            "canonicalization_version": "1.0",
            "row_order": ["partition", "time_block_id", "resource_id", "timestamp"],
            "timestamp_representation": "UTC ISO-8601 with nanosecond precision preserved",
            "partition_rule": "time_block_id is disjoint between calibration and heldout",
            "description": instrumentation["transformation_description"],
        }
        implementation = _implementation_record()
        artifacts = [
            _artifact_record(campaign_manifest_path),
            _artifact_record(campaign_schema_path),
            _artifact_record(calibration_path),
            _artifact_record(heldout_path),
            _artifact_record(measurement_schema_path),
            _artifact_record(quality_path),
        ]
        evidence: dict[str, object] = {
            "schema_version": CAMPAIGN_SCHEMA_VERSION,
            "dataset_id": campaign.dataset_id,
            "campaign_id": campaign.campaign_manifest["campaign_id"],
            "evidence_scope": campaign.evidence_scope,
            "external_validation": False,
            "intake_status": "accepted_for_engineering_review",
            "scientific_use_authorized": False,
            "source_artifacts": {
                "measurement_file_name": campaign.measurement_source_path.name,
                "measurement_sha256": campaign.measurement_source_sha256,
                "campaign_file_name": campaign.campaign_source_path.name,
                "campaign_sha256": campaign.campaign_source_sha256,
            },
            "schemas": {
                "campaign_schema_artifact": campaign_schema_path.name,
                "campaign_schema_sha256": campaign.campaign_schema_sha256,
                "measurement_schema_artifact": measurement_schema_path.name,
                "measurement_schema_sha256": campaign.measurement_schema_sha256,
            },
            "implementation": implementation,
            "implementation_sha256": _sha256_bytes(
                _canonical_json_bytes(implementation)
            ),
            "transformation": transformation,
            "transformation_sha256": _sha256_bytes(_canonical_json_bytes(transformation)),
            "partitions": {
                "calibration": {
                    "artifact": calibration_path.name,
                    "row_count": len(campaign.calibration),
                    "time_block_count": int(campaign.calibration["time_block_id"].nunique()),
                    "content_sha256": _sha256_bytes(
                        _canonical_frame_bytes(campaign.calibration)
                    ),
                },
                "heldout": {
                    "artifact": heldout_path.name,
                    "row_count": len(campaign.heldout),
                    "time_block_count": int(campaign.heldout["time_block_id"].nunique()),
                    "content_sha256": _sha256_bytes(_canonical_frame_bytes(campaign.heldout)),
                },
            },
            "quality_report": quality,
            "artifacts": artifacts,
        }
        evidence["self_integrity_sha256"] = _sha256_bytes(
            _canonical_json_bytes(evidence)
        )
        _write_json(evidence_path, evidence)
        verify_empirical_campaign_package(
            temporary,
        )
        if os.path.lexists(destination):
            raise FileExistsError(
                f"refusing to overwrite existing campaign package: {destination}"
            )
        os.rename(temporary, destination)
        temporary = None
        return destination
    except Exception:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)
        raise
    finally:
        os.close(lock_descriptor)
        lock_path.unlink(missing_ok=True)


def verify_empirical_campaign_package(
    package_dir: str | Path,
    *,
    campaign_schema_path: str | Path | None = None,
    measurement_schema_path: str | Path | None = None,
    expected_evidence_manifest_sha256: str | None = None,
    maximum_package_bytes: int = MAX_PACKAGE_BYTES,
    maximum_rows: int = MAX_PACKAGE_ROWS,
    maximum_uncompressed_bytes: int = MAX_UNCOMPRESSED_BYTES,
) -> CampaignPackageVerification:
    """Verify every retained artifact and reconstruct the validated partitions."""

    package = Path(package_dir)
    if package.is_symlink():
        raise ValueError("campaign package directory cannot be a symlink")
    if not package.is_dir():
        raise FileNotFoundError(package)
    entries = list(package.iterdir())
    actual_entries = {path.name for path in entries}
    if actual_entries != PACKAGE_FILES:
        raise ValueError(
            "campaign package file set mismatch: "
            f"missing={sorted(PACKAGE_FILES - actual_entries)}, "
            f"unexpected={sorted(actual_entries - PACKAGE_FILES)}"
        )
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            raise ValueError(f"campaign package entries must be regular local files: {entry.name}")
    if maximum_package_bytes <= 0 or maximum_rows <= 0 or maximum_uncompressed_bytes <= 0:
        raise ValueError("package verification limits must be positive")
    evidence_bytes = _read_regular_file(
        package / "evidence_manifest.json",
        maximum_bytes=maximum_package_bytes,
    )
    evidence_manifest_sha256 = _sha256_bytes(evidence_bytes)
    if expected_evidence_manifest_sha256 is not None:
        expected_digest = _sha256_string(
            expected_evidence_manifest_sha256,
            "expected evidence manifest hash",
        )
        if evidence_manifest_sha256 != expected_digest:
            raise ValueError("evidence manifest does not match the externally supplied digest")
    package_bytes = {"evidence_manifest.json": evidence_bytes}
    remaining_bytes = maximum_package_bytes - len(evidence_bytes)
    for name in sorted(PACKAGE_FILES.difference({"evidence_manifest.json"})):
        retained = _read_regular_file(
            package / name,
            maximum_bytes=remaining_bytes,
        )
        package_bytes[name] = retained
        remaining_bytes -= len(retained)
    evidence = _read_json_bytes(
        package_bytes["evidence_manifest.json"], "evidence_manifest.json"
    )
    _exact_keys(
        evidence,
        {
            "schema_version",
            "dataset_id",
            "campaign_id",
            "evidence_scope",
            "external_validation",
            "intake_status",
            "scientific_use_authorized",
            "source_artifacts",
            "schemas",
            "implementation",
            "implementation_sha256",
            "transformation",
            "transformation_sha256",
            "partitions",
            "quality_report",
            "artifacts",
            "self_integrity_sha256",
        },
        "campaign evidence manifest",
    )
    if evidence.get("schema_version") != CAMPAIGN_SCHEMA_VERSION:
        raise ValueError("campaign evidence manifest schema version mismatch")
    recorded_manifest_hash = evidence.pop("self_integrity_sha256", None)
    recorded_manifest_hash = _sha256_string(
        recorded_manifest_hash, "campaign evidence manifest self hash"
    )
    actual_manifest_hash = _sha256_bytes(_canonical_json_bytes(evidence))
    if actual_manifest_hash != recorded_manifest_hash:
        raise ValueError("campaign evidence manifest self hash mismatch")
    evidence["self_integrity_sha256"] = recorded_manifest_hash
    if evidence.get("external_validation") is not False:
        raise ValueError("campaign intake cannot assert external validation")
    if evidence.get("intake_status") != "accepted_for_engineering_review":
        raise ValueError("campaign intake status mismatch")
    if evidence.get("scientific_use_authorized") is not False:
        raise ValueError("campaign intake cannot authorize scientific use")

    source_record = _exact_keys(
        evidence.get("source_artifacts"),
        {
            "measurement_file_name",
            "measurement_sha256",
            "campaign_file_name",
            "campaign_sha256",
        },
        "source artifact record",
    )
    for key in ("measurement_file_name", "campaign_file_name"):
        name = _nonempty(source_record[key], f"source artifact {key}")
        if name != Path(name).name:
            raise ValueError("source artifact names must not contain paths")
    _sha256_string(source_record["measurement_sha256"], "measurement source hash")
    _sha256_string(source_record["campaign_sha256"], "campaign source hash")

    implementation_record = _exact_keys(
        evidence.get("implementation"), {"files", "runtime"}, "implementation record"
    )
    implementation_hash = _sha256_string(
        evidence.get("implementation_sha256"), "implementation record hash"
    )
    if implementation_hash != _sha256_bytes(_canonical_json_bytes(implementation_record)):
        raise ValueError("campaign implementation record hash mismatch")
    if implementation_record != _implementation_record():
        raise ValueError("campaign implementation boundary mismatch")

    transformation_record = _exact_keys(
        evidence.get("transformation"),
        {
            "canonicalization_version",
            "row_order",
            "timestamp_representation",
            "partition_rule",
            "description",
        },
        "transformation record",
    )
    recorded_transformation_hash = _sha256_string(
        evidence.get("transformation_sha256"), "transformation hash"
    )
    if recorded_transformation_hash != _sha256_bytes(
        _canonical_json_bytes(transformation_record)
    ):
        raise ValueError("campaign transformation hash mismatch")

    artifact_records = evidence.get("artifacts")
    if not isinstance(artifact_records, list) or len(artifact_records) != len(
        PACKAGE_FILES.difference({"evidence_manifest.json"})
    ):
        raise ValueError("campaign evidence manifest artifact inventory is incomplete")
    expected_inventory = PACKAGE_FILES.difference({"evidence_manifest.json"})
    inventory_names: set[str] = set()
    for record in artifact_records:
        values = _exact_keys(record, {"path", "bytes", "sha256"}, "artifact record")
        name = _nonempty(values["path"], "artifact path")
        if name != Path(name).name or name in inventory_names:
            raise ValueError("artifact paths must be unique file names")
        if name not in expected_inventory:
            raise ValueError(f"campaign artifact inventory has an invalid role: {name}")
        inventory_names.add(name)
        if _nonnegative_integer(values["bytes"], f"artifact bytes for {name}") != (
            len(package_bytes[name])
        ):
            raise ValueError(f"campaign artifact size mismatch: {name}")
        digest = _sha256_string(values["sha256"], f"artifact hash for {name}")
        if digest != _sha256_bytes(package_bytes[name]):
            raise ValueError(f"campaign artifact hash mismatch: {name}")
    if inventory_names != expected_inventory:
        raise ValueError("campaign artifact inventory does not cover the package")

    schema_record = _exact_keys(
        evidence.get("schemas"),
        {
            "campaign_schema_artifact",
            "campaign_schema_sha256",
            "measurement_schema_artifact",
            "measurement_schema_sha256",
        },
        "schema record",
    )
    if schema_record["campaign_schema_artifact"] != "campaign_schema.json":
        raise ValueError("campaign schema artifact role mismatch")
    if schema_record["measurement_schema_artifact"] != "measurement_schema.json":
        raise ValueError("measurement schema artifact role mismatch")
    retained_campaign_schema_sha256 = _validate_schema_bytes(
        package_bytes["campaign_schema.json"],
        "campaign_schema.json",
        "Empirical assurance campaign",
        CAMPAIGN_FIELDS,
    )
    retained_measurement_schema_sha256 = _validate_schema_bytes(
        package_bytes["measurement_schema.json"],
        "measurement_schema.json",
        "Empirical assurance resource measurement",
        EMPIRICAL_MEASUREMENT_COLUMNS,
    )
    if _sha256_string(
        schema_record["campaign_schema_sha256"], "campaign schema hash"
    ) != retained_campaign_schema_sha256:
        raise ValueError("campaign schema hash mismatch")
    if _sha256_string(
        schema_record["measurement_schema_sha256"], "measurement schema hash"
    ) != retained_measurement_schema_sha256:
        raise ValueError("measurement schema hash mismatch")
    if campaign_schema_path is not None and _validate_schema_file(
        Path(campaign_schema_path), "Empirical assurance campaign", CAMPAIGN_FIELDS
    ) != retained_campaign_schema_sha256:
        raise ValueError("external campaign schema differs from the retained schema")
    if measurement_schema_path is not None and _validate_schema_file(
        Path(measurement_schema_path),
        "Empirical assurance resource measurement",
        EMPIRICAL_MEASUREMENT_COLUMNS,
    ) != retained_measurement_schema_sha256:
        raise ValueError("external measurement schema differs from the retained schema")

    campaign_manifest = validate_campaign_manifest(
        _read_json_bytes(package_bytes["campaign_manifest.json"], "campaign_manifest.json")
    )
    campaign_instrumentation = _exact_keys(
        campaign_manifest["instrumentation"],
        {
            "environment_description",
            "collector_name",
            "collector_version",
            "clock_source",
            "sampling_interval_ms",
            "window_semantics",
            "known_gaps",
            "missingness_handling",
            "censoring_handling",
            "quality_reviewed",
            "quality_review_reference",
            "transformation_description",
        },
        "retained campaign instrumentation",
    )
    if transformation_record["canonicalization_version"] != "1.0":
        raise ValueError("campaign canonicalization version mismatch")
    if transformation_record["row_order"] != [
        "partition",
        "time_block_id",
        "resource_id",
        "timestamp",
    ]:
        raise ValueError("campaign canonical row order mismatch")
    if (
        transformation_record["timestamp_representation"]
        != "UTC ISO-8601 with nanosecond precision preserved"
    ):
        raise ValueError("campaign timestamp representation mismatch")
    if (
        transformation_record["partition_rule"]
        != "time_block_id is disjoint between calibration and heldout"
    ):
        raise ValueError("campaign partition rule mismatch")
    if (
        transformation_record["description"]
        != campaign_instrumentation["transformation_description"]
    ):
        raise ValueError("campaign transformation description mismatch")
    try:
        import pyarrow.parquet
    except ImportError as exc:
        raise RuntimeError("campaign package verification requires pyarrow") from exc
    calibration_metadata = pyarrow.parquet.ParquetFile(
        io.BytesIO(package_bytes["calibration_measurements.parquet"])
    ).metadata
    heldout_metadata = pyarrow.parquet.ParquetFile(
        io.BytesIO(package_bytes["heldout_measurements.parquet"])
    ).metadata
    retained_rows = calibration_metadata.num_rows + heldout_metadata.num_rows
    if retained_rows > maximum_rows:
        raise ValueError(
            f"campaign package exceeds the {maximum_rows}-row verification limit"
        )
    retained_uncompressed_bytes = sum(
        metadata.row_group(index).total_byte_size
        for metadata in (calibration_metadata, heldout_metadata)
        for index in range(metadata.num_row_groups)
    )
    if retained_uncompressed_bytes > maximum_uncompressed_bytes:
        raise ValueError(
            "campaign package exceeds the uncompressed-byte verification limit"
        )
    calibration = pd.read_parquet(
        io.BytesIO(package_bytes["calibration_measurements.parquet"])
    )
    heldout = pd.read_parquet(io.BytesIO(package_bytes["heldout_measurements.parquet"]))
    if set(calibration.get("partition", [])) != {"calibration"}:
        raise ValueError("calibration artifact contains a non-calibration partition")
    if set(heldout.get("partition", [])) != {"heldout"}:
        raise ValueError("heldout artifact contains a non-heldout partition")
    combined = validate_campaign_measurements(
        pd.concat([calibration, heldout], ignore_index=True),
        campaign_manifest,
    )
    campaign_schema_sha256 = _sha256_string(
        schema_record["campaign_schema_sha256"], "campaign schema hash"
    )
    measurement_schema_sha256 = _sha256_string(
        schema_record["measurement_schema_sha256"], "measurement schema hash"
    )
    dataset_id = _dataset_id(
        campaign_manifest,
        combined,
        campaign_schema_sha256=campaign_schema_sha256,
        measurement_schema_sha256=measurement_schema_sha256,
    )
    if evidence.get("dataset_id") != dataset_id:
        raise ValueError("campaign dataset identifier mismatch")
    if evidence.get("campaign_id") != campaign_manifest["campaign_id"]:
        raise ValueError("campaign identifier mismatch")
    scope = _evidence_scope(combined)
    if evidence.get("evidence_scope") != scope:
        raise ValueError("campaign evidence scope mismatch")

    partitions = _exact_keys(
        evidence.get("partitions"), {"calibration", "heldout"}, "partitions"
    )
    for name, selected in (("calibration", calibration), ("heldout", heldout)):
        record = _exact_keys(
            partitions[name],
            {"artifact", "row_count", "time_block_count", "content_sha256"},
            f"partition {name}",
        )
        expected_artifact = f"{name}_measurements.parquet"
        if record["artifact"] != expected_artifact:
            raise ValueError(f"{name} artifact role mismatch")
        if _nonnegative_integer(record["row_count"], f"{name} row count") != len(
            selected
        ):
            raise ValueError(f"{name} row count mismatch")
        if _nonnegative_integer(
            record["time_block_count"], f"{name} time-block count"
        ) != selected["time_block_id"].nunique():
            raise ValueError(f"{name} time-block count mismatch")
        if _sha256_string(
            record["content_sha256"], f"{name} canonical content hash"
        ) != _sha256_bytes(_canonical_frame_bytes(selected)):
            raise ValueError(f"{name} canonical content hash mismatch")

    quality = _quality_report(combined)
    if evidence.get("quality_report") != quality:
        raise ValueError("campaign quality report does not match the retained data")
    if _read_json_bytes(package_bytes["quality_report.json"], "quality_report.json") != quality:
        raise ValueError("retained quality report does not match the campaign data")

    canonical_calibration = combined[
        combined["partition"] == "calibration"
    ].reset_index(drop=True)
    canonical_heldout = combined[combined["partition"] == "heldout"].reset_index(
        drop=True
    )

    return CampaignPackageVerification(
        package_dir=package.resolve(),
        dataset_id=dataset_id,
        evidence_scope=scope,
        external_validation=False,
        scientific_use_authorized=False,
        evidence_manifest_sha256=evidence_manifest_sha256,
        externally_digest_bound=expected_evidence_manifest_sha256 is not None,
        _calibration=canonical_calibration.copy(deep=True),
        _heldout=canonical_heldout.copy(deep=True),
        _evidence_manifest=deepcopy(evidence),
    )
