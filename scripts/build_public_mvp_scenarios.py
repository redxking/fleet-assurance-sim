"""Build the deterministic synthetic data package for the public MVP."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fleet_sim.public_mvp import (
    DEFAULT_REPLICATIONS,
    DEFAULT_ROOT_SEED,
    build_public_mvp_scenario_pack,
    verify_public_mvp_scenario_pack,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "schemas" / "public_mvp_scenario_pack.schema.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a fail-no-overwrite, synthetic-only Stage 3A scenario pack for the "
            "static public explorer."
        )
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        help="New output directory; an existing path is never overwritten.",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA,
        help="Closed public scenario-pack schema to bind into the manifest.",
    )
    parser.add_argument(
        "--root-seed",
        type=int,
        default=DEFAULT_ROOT_SEED,
        help="Nonnegative deterministic root seed (default: %(default)s).",
    )
    parser.add_argument(
        "--replications",
        type=int,
        default=DEFAULT_REPLICATIONS,
        help="Positive stochastic replications per scenario (default: %(default)s).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    artifacts = build_public_mvp_scenario_pack(
        args.output_dir,
        schema_path=args.schema,
        root_seed=args.root_seed,
        replications=args.replications,
    )
    verified = verify_public_mvp_scenario_pack(
        artifacts.output_dir,
        schema_path=args.schema,
        expected_pack_sha256=artifacts.pack_sha256,
        expected_manifest_sha256=artifacts.manifest_sha256,
    )
    print(
        json.dumps(
            {
                "external_validation": False,
                "manifest_content_sha256": verified.manifest_content_sha256,
                "manifest_sha256": verified.manifest_sha256,
                "operational_use_authorized": False,
                "pack_sha256": verified.pack_sha256,
                "scenario_count": verified.scenario_count,
                "synthetic_only": True,
                "timeseries_point_count": verified.timeseries_point_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
