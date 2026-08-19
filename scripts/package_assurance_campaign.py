#!/usr/bin/env python3
"""Validate and package a provenance-bound assurance measurement campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fleet_sim.empirical.assurance_campaign import (
    read_empirical_campaign,
    write_empirical_campaign_package,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("measurements", type=Path, help="Extended CSV or Parquet observations")
    parser.add_argument("campaign_manifest", type=Path, help="Campaign authority metadata JSON")
    parser.add_argument("output_dir", type=Path, help="New immutable campaign package directory")
    parser.add_argument(
        "--campaign-schema",
        type=Path,
        default=ROOT / "schemas" / "empirical_assurance_campaign.schema.json",
    )
    parser.add_argument(
        "--measurement-schema",
        type=Path,
        default=ROOT / "schemas" / "empirical_assurance_measurements.schema.json",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    campaign = read_empirical_campaign(
        args.measurements,
        args.campaign_manifest,
        campaign_schema_path=args.campaign_schema,
        measurement_schema_path=args.measurement_schema,
    )
    destination = write_empirical_campaign_package(campaign, args.output_dir)
    evidence_manifest_sha256 = hashlib.sha256(
        (destination / "evidence_manifest.json").read_bytes()
    ).hexdigest()
    print(
        json.dumps(
            {
                "calibration_rows": len(campaign.calibration),
                "dataset_id": campaign.dataset_id,
                "evidence_scope": campaign.evidence_scope,
                "evidence_manifest_sha256": evidence_manifest_sha256,
                "external_validation": False,
                "heldout_rows": len(campaign.heldout),
                "output_dir": str(destination),
                "scientific_use_authorized": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
