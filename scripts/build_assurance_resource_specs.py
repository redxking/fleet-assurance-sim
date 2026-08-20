"""Build checksum-bound assurance-resource specifications from an accepted fit."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fleet_sim.empirical.calibration_gate import verify_empirical_calibration_package
from fleet_sim.empirical.resource_adapter import (
    adapt_accepted_fit_to_resource_specs,
    assurance_resource_specs_schema,
    load_resource_adapter_policy,
    resource_adapter_policy_schema,
    verify_adapted_resource_bundle,
    write_adapted_resource_bundle,
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
            ROOT / "schemas" / "assurance_resource_adapter_policy.schema.json",
            resource_adapter_policy_schema(),
        ),
        (
            ROOT / "schemas" / "assurance_resource_specs.schema.json",
            assurance_resource_specs_schema(),
        ),
    )
    for path, expected in contracts:
        if _read_schema(path) != expected:
            raise RuntimeError(f"public schema differs from the live adapter contract: {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "campaign_package",
        type=Path,
        help="Source empirical campaign package used to verify the accepted fit",
    )
    parser.add_argument(
        "fit_package",
        type=Path,
        help="Calibration-fit package accepted for interface or adapter review",
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        help="New immutable adapter evidence package directory",
    )
    parser.add_argument(
        "--expected-campaign-evidence-manifest-sha256",
        required=True,
        type=_sha256_argument,
        help="Externally recorded SHA-256 of the source campaign evidence manifest",
    )
    parser.add_argument(
        "--expected-fit-evidence-manifest-sha256",
        required=True,
        type=_sha256_argument,
        help="Externally recorded SHA-256 of the calibration fit evidence manifest",
    )
    parser.add_argument(
        "--adapter-policy",
        type=Path,
        default=(ROOT / "configs" / "successor" / "assurance_resource_adapter_policy.example.json"),
        help="Closed adapter policy JSON; defaults to the interface-only example",
    )
    parser.add_argument(
        "--expected-adapter-policy-sha256",
        required=True,
        type=_sha256_argument,
        help="Externally recorded semantic SHA-256 of the adapter policy",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    _verify_public_schema_contracts()
    fit_package = verify_empirical_calibration_package(
        args.fit_package,
        source_campaign_package=args.campaign_package,
        expected_source_evidence_manifest_sha256=(args.expected_campaign_evidence_manifest_sha256),
        expected_fit_evidence_manifest_sha256=(args.expected_fit_evidence_manifest_sha256),
    )
    policy = load_resource_adapter_policy(
        args.adapter_policy,
        expected_policy_sha256=args.expected_adapter_policy_sha256,
    )
    bundle = adapt_accepted_fit_to_resource_specs(fit_package, policy)
    destination = write_adapted_resource_bundle(
        bundle,
        policy,
        args.output_dir,
        fit_package=fit_package,
    )
    adapter_manifest_sha256 = hashlib.sha256(
        (destination / "adapter_manifest.json").read_bytes()
    ).hexdigest()
    checked = verify_adapted_resource_bundle(
        destination,
        fit_package=fit_package,
        expected_policy_sha256=args.expected_adapter_policy_sha256,
    )
    print(
        json.dumps(
            {
                "adapter_bundle_id": checked.bundle.adapter_bundle_id,
                "adapter_manifest_externally_digest_bound": (checked.externally_digest_bound),
                "adapter_manifest_sha256": adapter_manifest_sha256,
                "adapter_mode": checked.bundle.adapter_mode,
                "adapter_policy_id": checked.bundle.adapter_policy_id,
                "adapter_policy_sha256": checked.bundle.adapter_policy_sha256,
                "calibration_fit_id": checked.bundle.calibration_fit_id,
                "evidence_scope": checked.bundle.evidence_scope,
                "external_validation": False,
                "fit_evidence_manifest_externally_digest_bound": (
                    fit_package.externally_digest_bound
                ),
                "source_package_heldout_verified": True,
                "heldout_used_for_adapter": False,
                "no_fallback": True,
                "output_dir": str(destination),
                "resource_count": len(checked.bundle.resources),
                "runner_authorized": False,
                "scientific_use": checked.bundle.scientific_use,
                "scientific_use_authorized": False,
                "simulator_semantics_sha256": (checked.bundle.simulator_semantics_sha256),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
