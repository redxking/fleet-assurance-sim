from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fleet_sim.calibration.admission import (
    calibrate_admission_resources,
    write_calibration_bundle,
)
from fleet_sim.calibration.measurements import (
    read_assurance_measurements,
    validate_assurance_measurements,
    write_canonical_measurements,
)
from fleet_sim.control_plane.resource_network import ResourceType

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "examples" / "assurance_resource_measurements_template.csv"
SCHEMA = ROOT / "schemas" / "assurance_resource_measurements.schema.json"


def test_template_covers_ten_resources_and_is_interface_only() -> None:
    dataset = read_assurance_measurements(TEMPLATE, schema_path=SCHEMA)
    assert dataset.row_count == 20
    assert set(dataset.frame.resource_type) == {item.value for item in ResourceType}
    assert dataset.evidence_scope == "interface_verification_only"


def test_csv_and_parquet_round_trip(tmp_path: Path) -> None:
    source = read_assurance_measurements(TEMPLATE, schema_path=SCHEMA)
    normalized = write_canonical_measurements(source, tmp_path / "normalized")
    restored = read_assurance_measurements(
        normalized / "measurements.parquet",
        schema_path=SCHEMA,
    )
    assert restored.row_count == source.row_count
    assert set(restored.frame.resource_id) == set(source.frame.resource_id)
    with pytest.raises(FileExistsError, match="overwrite"):
        write_canonical_measurements(source, normalized)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("queue_depth", -1.0, "nonnegative"),
        ("capacity_units_per_second", 0.0, "positive"),
        ("arrival_count", np.nan, "nonfinite"),
        ("measurement_provenance", " ", "empty"),
    ],
)
def test_invalid_measurements_are_rejected(column: str, value: object, message: str) -> None:
    frame = pd.read_csv(TEMPLATE)
    frame.loc[0, column] = value
    with pytest.raises(ValueError, match=message):
        validate_assurance_measurements(frame)


def test_uncontracted_measurement_columns_are_rejected() -> None:
    frame = pd.read_csv(TEMPLATE)
    frame["unregistered_metric"] = 1.0
    with pytest.raises(ValueError, match="unsupported columns"):
        validate_assurance_measurements(frame)


def test_calibration_is_provenance_bounded_and_no_overwrite(tmp_path: Path) -> None:
    dataset = read_assurance_measurements(TEMPLATE, schema_path=SCHEMA)
    bundle = calibrate_admission_resources(dataset)
    assert len(bundle.resources) == len(ResourceType)
    assert bundle.evidence_scope == "interface_verification_only"
    assert bundle.external_validation is False
    assert all(resource.parameter_class == "notional" for resource in bundle.resources)
    output = write_calibration_bundle(bundle, tmp_path / "calibration.json")
    assert output.exists()
    with pytest.raises(FileExistsError, match="overwrite"):
        write_calibration_bundle(bundle, output)
