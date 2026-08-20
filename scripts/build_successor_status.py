"""Build the public-safe offline successor-study status UI."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATPLOTLIB_CACHE = Path(tempfile.gettempdir()) / "fleet-sim-matplotlib-cache"
MATPLOTLIB_CACHE.mkdir(parents=True, exist_ok=True)
FONT_CACHE = Path(tempfile.gettempdir()) / "fleet-sim-font-cache"
FONT_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("XDG_CACHE_HOME", str(FONT_CACHE))
os.environ.setdefault("MPLBACKEND", "Agg")
configured_cache_value = os.environ.get("MPLCONFIGDIR")
configured_cache = Path(configured_cache_value) if configured_cache_value else None
if (
    configured_cache is None
    or not configured_cache.is_dir()
    or not os.access(configured_cache, os.W_OK)
):
    os.environ["MPLCONFIGDIR"] = str(MATPLOTLIB_CACHE)
sys.path.insert(0, str(ROOT / "src"))

from fleet_sim.visualization.successor_status import build_successor_status


def _sha256_argument(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise argparse.ArgumentTypeError("digest must be a lowercase SHA-256 value")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_package", type=Path, help="Verified campaign package")
    parser.add_argument(
        "output_directory",
        type=Path,
        help="Directory that will receive index.html and successor-status.json",
    )
    parser.add_argument(
        "--expected-campaign-evidence-manifest-sha256",
        required=True,
        type=_sha256_argument,
        help="Externally recorded campaign evidence-manifest digest",
    )
    parser.add_argument("--fit-package", type=Path, help="Optional calibration-fit package")
    parser.add_argument(
        "--expected-fit-evidence-manifest-sha256",
        type=_sha256_argument,
        help="Externally recorded fit evidence-manifest digest",
    )
    parser.add_argument("--adapter-package", type=Path, help="Optional adapter package")
    parser.add_argument(
        "--expected-adapter-policy-sha256",
        type=_sha256_argument,
        help="Externally recorded semantic adapter-policy digest",
    )
    parser.add_argument(
        "--expected-adapter-manifest-sha256",
        type=_sha256_argument,
        help="Externally recorded adapter-manifest digest",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing status assets in the output directory",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    html_path, json_path = build_successor_status(
        args.campaign_package,
        args.output_directory,
        expected_campaign_evidence_manifest_sha256=(
            args.expected_campaign_evidence_manifest_sha256
        ),
        fit_package=args.fit_package,
        expected_fit_evidence_manifest_sha256=(args.expected_fit_evidence_manifest_sha256),
        adapter_package=args.adapter_package,
        expected_adapter_policy_sha256=args.expected_adapter_policy_sha256,
        expected_adapter_manifest_sha256=args.expected_adapter_manifest_sha256,
        overwrite=args.overwrite,
    )
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "html": str(html_path),
                "json": str(json_path),
                "overall_state": payload["overall_state"],
                "projection_sha256": payload["projection_sha256"],
                "scientific_use_authorized": False,
                "runner_authorized": False,
                "external_validation": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
