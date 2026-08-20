#!/usr/bin/env python3
"""Bind realized evaluation inputs to a frozen successor registration."""

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
from fleet_sim.empirical.resource_adapter import verify_adapted_resource_bundle
from fleet_sim.empirical.successor_protocol import (
    bind_successor_evaluation_inputs,
    successor_evaluation_inputs_schema,
    verify_successor_evaluation_inputs_package,
    verify_successor_registration_package,
    write_successor_evaluation_inputs_package,
)


def _digest(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise argparse.ArgumentTypeError("digest must be a lowercase SHA-256 value")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_campaign", type=Path)
    parser.add_argument("fit_package", type=Path)
    parser.add_argument("adapter_package", type=Path)
    parser.add_argument("registration_package", type=Path)
    parser.add_argument("evaluation_campaign", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--expected-source-campaign-manifest-sha256", required=True, type=_digest)
    parser.add_argument("--expected-fit-manifest-sha256", required=True, type=_digest)
    parser.add_argument("--expected-adapter-policy-sha256", required=True, type=_digest)
    parser.add_argument("--expected-adapter-manifest-sha256", required=True, type=_digest)
    parser.add_argument("--expected-registration-manifest-sha256", required=True, type=_digest)
    parser.add_argument(
        "--expected-evaluation-campaign-manifest-sha256", required=True, type=_digest
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    public_schema = ROOT / "schemas" / "successor_evaluation_inputs.schema.json"
    if json.loads(public_schema.read_text(encoding="utf-8")) != (
        successor_evaluation_inputs_schema()
    ):
        raise RuntimeError("public evaluation-input schema differs from the live protocol")
    source = verify_empirical_campaign_package(
        args.source_campaign,
        expected_evidence_manifest_sha256=args.expected_source_campaign_manifest_sha256,
    )
    fit = verify_empirical_calibration_package(
        args.fit_package,
        source_campaign_package=args.source_campaign,
        expected_source_evidence_manifest_sha256=args.expected_source_campaign_manifest_sha256,
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
    evaluation = verify_empirical_campaign_package(
        args.evaluation_campaign,
        expected_evidence_manifest_sha256=args.expected_evaluation_campaign_manifest_sha256,
    )
    inputs = bind_successor_evaluation_inputs(registration, evaluation)
    destination = write_successor_evaluation_inputs_package(
        inputs,
        args.output_dir,
        registration_package=registration,
        evaluation_campaign=evaluation,
    )
    digest = hashlib.sha256(
        (destination / "evaluation_inputs_manifest.json").read_bytes()
    ).hexdigest()
    checked = verify_successor_evaluation_inputs_package(
        destination,
        registration_package=registration,
        evaluation_campaign=evaluation,
        expected_evaluation_inputs_manifest_sha256=digest,
    )
    print(
        json.dumps(
            {
                "chronology_consistent": checked.inputs.chronology_consistent,
                "evaluation_inputs_manifest_sha256": digest,
                "execution_chain_ready": False,
                "external_validation": False,
                "output_dir": str(destination),
                "prediction_rows_preoutcome_locked": False,
                "runner_authorized": False,
                "scientific_use_authorized": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
