#!/usr/bin/env python3
"""Create a target-free successor prediction workflow commitment."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fleet_sim.empirical.assurance_campaign import verify_empirical_campaign_package
from fleet_sim.empirical.calibration_gate import verify_empirical_calibration_package
from fleet_sim.empirical.prediction_lock import (
    build_successor_prediction_lock,
    successor_prediction_lock_schema,
    successor_prediction_parameter_draws_schema,
    successor_prediction_rows_schema,
    verify_successor_prediction_lock_package,
    write_successor_prediction_lock_package,
)
from fleet_sim.empirical.resource_adapter import verify_adapted_resource_bundle
from fleet_sim.empirical.successor_protocol import verify_successor_registration_package


def _digest(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise argparse.ArgumentTypeError("digest must be a lowercase SHA-256 value")
    return value


def _verify_public_schemas() -> None:
    expected = (
        (
            ROOT / "schemas" / "successor_prediction_lock.schema.json",
            successor_prediction_lock_schema(),
        ),
        (
            ROOT / "schemas" / "successor_prediction_rows.schema.json",
            successor_prediction_rows_schema(),
        ),
        (
            ROOT / "schemas" / "successor_prediction_parameter_draws.schema.json",
            successor_prediction_parameter_draws_schema(),
        ),
    )
    for path, live in expected:
        if json.loads(path.read_text(encoding="utf-8")) != live:
            raise RuntimeError(f"public schema differs from the live prediction lock: {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_campaign", type=Path)
    parser.add_argument("fit_package", type=Path)
    parser.add_argument("adapter_package", type=Path)
    parser.add_argument("registration_package", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--expected-source-campaign-manifest-sha256", required=True, type=_digest)
    parser.add_argument("--expected-fit-manifest-sha256", required=True, type=_digest)
    parser.add_argument("--expected-adapter-policy-sha256", required=True, type=_digest)
    parser.add_argument("--expected-adapter-manifest-sha256", required=True, type=_digest)
    parser.add_argument("--expected-registration-manifest-sha256", required=True, type=_digest)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    _verify_public_schemas()
    source = verify_empirical_campaign_package(
        args.source_campaign,
        expected_evidence_manifest_sha256=args.expected_source_campaign_manifest_sha256,
    )
    fit = verify_empirical_calibration_package(
        args.fit_package,
        source_campaign_package=args.source_campaign,
        expected_source_evidence_manifest_sha256=(args.expected_source_campaign_manifest_sha256),
        expected_fit_evidence_manifest_sha256=args.expected_fit_manifest_sha256,
    )
    adapter = verify_adapted_resource_bundle(
        args.adapter_package,
        fit_package=fit,
        expected_policy_sha256=args.expected_adapter_policy_sha256,
        expected_adapter_manifest_sha256=args.expected_adapter_manifest_sha256,
    )
    registration = verify_successor_registration_package(
        args.registration_package,
        source_campaign=source,
        fit_package=fit,
        adapter_package=adapter,
        expected_registration_manifest_sha256=args.expected_registration_manifest_sha256,
    )
    run = build_successor_prediction_lock(
        registration,
        source_campaign=source,
        fit_package=fit,
        adapter_package=adapter,
    )
    destination = write_successor_prediction_lock_package(
        run,
        args.output_dir,
        registration_package=registration,
        source_campaign=source,
        fit_package=fit,
        adapter_package=adapter,
    )
    digest = hashlib.sha256(
        (destination / "prediction_lock_manifest.json").read_bytes()
    ).hexdigest()
    checked = verify_successor_prediction_lock_package(
        destination,
        registration_package=registration,
        source_campaign=source,
        fit_package=fit,
        adapter_package=adapter,
        expected_prediction_lock_manifest_sha256=digest,
    )
    print(
        json.dumps(
            {
                "execution_chain_ready": False,
                "external_validation": False,
                "future_evaluation_campaign_not_supplied": True,
                "local_lock_chronology_consistent": True,
                "output_dir": str(destination),
                "prediction_lock_manifest_sha256": digest,
                "prediction_lock_time_externally_attested": False,
                "prediction_row_count": checked.lock.prediction_row_count,
                "prediction_rows_preoutcome_locked": False,
                "prediction_rows_target_free": True,
                "runner_authorized": False,
                "scientific_use_authorized": False,
                "workflow_prediction_commitment": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
