"""Fit and package calibration-only assurance-resource evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fleet_sim.empirical.calibration_gate import (
    calibration_fit_schema,
    calibration_policy_schema,
    fit_empirical_calibration,
    load_fit_gate_policy,
    prepare_calibration_fit_input,
    verify_empirical_calibration_package,
    write_empirical_calibration_package,
)


def _sha256_argument(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise argparse.ArgumentTypeError("digest must be a lowercase SHA-256 value")
    return value


def _read_schema(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"schema must contain one JSON object: {path}")
    return payload


def _verify_public_schema_contracts() -> None:
    contracts = (
        (
            ROOT / "schemas" / "empirical_calibration_policy.schema.json",
            calibration_policy_schema(),
        ),
        (
            ROOT / "schemas" / "empirical_calibration_fit.schema.json",
            calibration_fit_schema(),
        ),
    )
    for path, expected in contracts:
        if _read_schema(path) != expected:
            raise RuntimeError(f"public schema differs from the live calibration contract: {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "campaign_package",
        type=Path,
        help="Verified empirical campaign package containing the calibration partition",
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        help="New immutable calibration-fit evidence package directory",
    )
    parser.add_argument(
        "--expected-campaign-evidence-manifest-sha256",
        required=True,
        type=_sha256_argument,
        help="Externally recorded SHA-256 of the campaign evidence manifest",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=ROOT / "configs" / "successor" / "empirical_calibration_policy.json",
        help="Closed fit-gate policy JSON; defaults to the engineering-draft successor policy",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    _verify_public_schema_contracts()
    policy = load_fit_gate_policy(args.policy)
    fit_input = prepare_calibration_fit_input(
        args.campaign_package,
        expected_evidence_manifest_sha256=(args.expected_campaign_evidence_manifest_sha256),
    )
    run = fit_empirical_calibration(fit_input, policy)
    destination = write_empirical_calibration_package(run, fit_input, args.output_dir)
    fit_evidence_manifest_sha256 = hashlib.sha256(
        (destination / "fit_evidence_manifest.json").read_bytes()
    ).hexdigest()
    checked = verify_empirical_calibration_package(
        destination,
        source_campaign_package=args.campaign_package,
        expected_source_evidence_manifest_sha256=(args.expected_campaign_evidence_manifest_sha256),
    )
    status_counts = Counter(resource.gate_status for resource in checked.fit.resources)
    print(
        json.dumps(
            {
                "blocking_reasons": list(checked.fit.blocking_reasons),
                "calibration_fit_id": checked.fit.calibration_fit_id,
                "eligible_for_adapter": checked.fit.eligible_for_adapter,
                "external_validation": False,
                "fit_evidence_manifest_sha256": fit_evidence_manifest_sha256,
                "fit_evidence_manifest_externally_digest_bound": (checked.externally_digest_bound),
                "gate_status": checked.fit.gate_status,
                "interface_verification_ready": (checked.fit.interface_verification_ready),
                "output_dir": str(destination),
                "policy_id": policy.policy_id,
                "policy_sha256": policy.policy_sha256,
                "resource_count": len(checked.fit.resources),
                "resource_gate_status_counts": {
                    state: status_counts.get(state, 0)
                    for state in ("passed", "failed", "not_evaluable")
                },
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
