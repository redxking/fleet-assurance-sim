#!/usr/bin/env python3
"""Validate and normalize Stage 3A assurance measurements."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fleet_sim.calibration.measurements import (
    read_assurance_measurements,
    write_canonical_measurements,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="CSV or Parquet measurement file")
    parser.add_argument("output_dir", type=Path, help="New immutable normalized dataset directory")
    parser.add_argument(
        "--schema",
        type=Path,
        default=ROOT / "schemas" / "assurance_resource_measurements.schema.json",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    dataset = read_assurance_measurements(args.input, schema_path=args.schema)
    destination = write_canonical_measurements(dataset, args.output_dir)
    print(
        json.dumps(
            {
                "dataset_id": dataset.dataset_id,
                "row_count": dataset.row_count,
                "evidence_scope": dataset.evidence_scope,
                "external_validation": False,
                "output_dir": str(destination),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
