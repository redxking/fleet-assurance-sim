#!/usr/bin/env python3
"""Calibrate Stage 3A resource parameters from validated measurements."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fleet_sim.calibration.admission import (
    calibrate_admission_resources,
    write_calibration_bundle,
)
from fleet_sim.calibration.measurements import read_assurance_measurements


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Validated CSV or Parquet measurement file")
    parser.add_argument("output", type=Path, help="New calibration JSON path")
    parser.add_argument(
        "--schema",
        type=Path,
        default=ROOT / "schemas" / "assurance_resource_measurements.schema.json",
    )
    parser.add_argument(
        "--allow-partial-resources",
        action="store_true",
        help="Permit calibration data that does not contain all ten required resource types",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    dataset = read_assurance_measurements(args.input, schema_path=args.schema)
    bundle = calibrate_admission_resources(
        dataset,
        require_all_resources=not args.allow_partial_resources,
    )
    destination = write_calibration_bundle(bundle, args.output)
    print(
        json.dumps(
            {
                "dataset_id": bundle.dataset_id,
                "resource_count": len(bundle.resources),
                "evidence_scope": bundle.evidence_scope,
                "external_validation": bundle.external_validation,
                "output": str(destination),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
