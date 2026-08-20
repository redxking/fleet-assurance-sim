#!/usr/bin/env python3
"""Freeze a successor study registration without authorizing execution."""

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
    freeze_successor_registration,
    load_resource_arrival_transfer_contract,
    load_successor_registration_plan,
    successor_registration_plan_schema,
    transfer_contract_schema,
    verify_successor_registration_package,
    write_successor_registration_package,
)


def _digest(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise argparse.ArgumentTypeError("digest must be a lowercase SHA-256 value")
    return value


def _verify_public_schemas() -> None:
    expected = (
        (
            ROOT / "schemas" / "successor_registration_plan.schema.json",
            successor_registration_plan_schema(),
        ),
        (
            ROOT / "schemas" / "successor_transfer_contract.schema.json",
            transfer_contract_schema(),
        ),
    )
    for path, live in expected:
        if json.loads(path.read_text(encoding="utf-8")) != live:
            raise RuntimeError(f"public schema differs from the live protocol: {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_campaign", type=Path)
    parser.add_argument("fit_package", type=Path)
    parser.add_argument("adapter_package", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--expected-campaign-evidence-manifest-sha256", required=True, type=_digest)
    parser.add_argument("--expected-fit-evidence-manifest-sha256", required=True, type=_digest)
    parser.add_argument("--expected-adapter-policy-sha256", required=True, type=_digest)
    parser.add_argument("--expected-adapter-manifest-sha256", required=True, type=_digest)
    parser.add_argument(
        "--plan",
        type=Path,
        default=ROOT / "configs" / "successor" / "successor_registration_plan.example.json",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=(
            ROOT / "configs" / "successor" / "resource_arrival_transfer_contract.example.json"
        ),
    )
    parser.add_argument(
        "--registered-at-utc",
        help="Canonical UTC registration time. Omit to use the current local UTC clock.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    _verify_public_schemas()
    source = verify_empirical_campaign_package(
        args.source_campaign,
        expected_evidence_manifest_sha256=args.expected_campaign_evidence_manifest_sha256,
    )
    fit = verify_empirical_calibration_package(
        args.fit_package,
        source_campaign_package=args.source_campaign,
        expected_source_evidence_manifest_sha256=args.expected_campaign_evidence_manifest_sha256,
        expected_fit_evidence_manifest_sha256=args.expected_fit_evidence_manifest_sha256,
    )
    adapter = verify_adapted_resource_bundle(
        args.adapter_package,
        fit_package=fit,
        expected_policy_sha256=args.expected_adapter_policy_sha256,
        expected_adapter_manifest_sha256=args.expected_adapter_manifest_sha256,
    )
    plan = load_successor_registration_plan(args.plan)
    contract = load_resource_arrival_transfer_contract(args.contract)
    registration = freeze_successor_registration(
        source,
        fit,
        adapter,
        plan,
        contract,
        registered_at_utc=args.registered_at_utc,
    )
    destination = write_successor_registration_package(
        registration,
        plan,
        contract,
        args.output_dir,
        source_campaign=source,
        fit_package=fit,
        adapter_package=adapter,
    )
    digest = hashlib.sha256((destination / "registration_manifest.json").read_bytes()).hexdigest()
    checked = verify_successor_registration_package(
        destination,
        source_campaign=source,
        fit_package=fit,
        adapter_package=adapter,
        expected_registration_manifest_sha256=digest,
    )
    print(
        json.dumps(
            {
                "chronology_consistent": checked.registration.chronology_consistent,
                "execution_chain_ready": False,
                "external_validation": False,
                "output_dir": str(destination),
                "registration_manifest_sha256": digest,
                "registration_time_externally_attested": False,
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
