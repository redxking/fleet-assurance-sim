#!/usr/bin/env python3
"""Freeze the Stage 3 protocol after engineering pilots and before confirmation."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
sys.path.insert(0, str(ROOT / "src"))

from fleet_sim.experiments.stage3_protocol import (
    build_preexecution_manifest,
    validate_safe_identifier,
    write_new_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/stage3/protocol.yaml"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("manifests/stage3_preexecution_manifest.json"),
    )
    parser.add_argument("--execution-id", required=True)
    args = parser.parse_args()
    execution_id = validate_safe_identifier(args.execution_id, label="execution_id")

    root = args.root.resolve()
    config_path = args.config if args.config.is_absolute() else root / args.config
    output_path = args.output if args.output.is_absolute() else root / args.output
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise TypeError("Stage 3 protocol configuration must be a mapping")
    if config.get("status_before_freeze") != "frozen_for_confirmatory_execution":
        raise ValueError(
            "protocol status must be frozen_for_confirmatory_execution before manifest creation"
        )
    frozen_files = config.get("frozen_files")
    if not isinstance(frozen_files, list) or not all(isinstance(v, str) for v in frozen_files):
        raise ValueError("frozen_files must be a list of repository-relative paths")
    frozen_globs = config.get("frozen_globs", [])
    if not isinstance(frozen_globs, list) or not all(isinstance(v, str) for v in frozen_globs):
        raise ValueError("frozen_globs must be a list of repository-relative patterns")
    expanded_files = list(frozen_files)
    for pattern in frozen_globs:
        matches = sorted(
            path.relative_to(root).as_posix()
            for path in root.glob(pattern)
            if path.is_file()
        )
        if not matches:
            raise FileNotFoundError(f"frozen glob matched no files: {pattern}")
        expanded_files.extend(matches)

    admission = yaml.safe_load(
        (root / "configs/stage3/admission_matrix.yaml").read_text(encoding="utf-8")
    )
    compromise = yaml.safe_load(
        (root / "configs/stage3/compromise_matrix.yaml").read_text(encoding="utf-8")
    )
    budget = yaml.safe_load(
        (root / "configs/stage3/compute_budget.yaml").read_text(encoding="utf-8")
    )
    stage3a_replications = int(admission["replications"]["confirmatory"])
    stage3b_replications = int(compromise["replications"]["confirmatory"])
    bootstrap_draws = int(budget["confirmatory"]["bootstrap_draws"])
    command = [
        ".venv-stage3-verify/bin/python",
        "scripts/run_stage3.py",
        "--mode",
        "confirmatory",
        "--execution-id",
        execution_id,
        "--stage3a-replications",
        str(stage3a_replications),
        "--stage3b-replications",
        str(stage3b_replications),
        "--bootstrap-draws",
        str(bootstrap_draws),
    ]
    execution_contract = {
        "execution_id": execution_id,
        "command_argv": command,
        "stage3a_replications_per_scenario": stage3a_replications,
        "stage3b_replications_per_scenario": stage3b_replications,
        "bootstrap_draws": bootstrap_draws,
        "stopping_rules": budget["confirmatory"],
        "seed_manifest": "manifests/stage3_seed_manifest.csv",
        "seed_domains": config["seed_domains"]["confirmatory"],
        "bootstrap_seed_bases": config["bootstrap_seed_bases"],
        "network_access": "prohibited",
        "overwrite_existing_execution": False,
    }

    payload = build_preexecution_manifest(
        root,
        protocol_id=str(config["protocol_id"]),
        frozen_files=expanded_files,
        evidence_scope=str(config["evidence_scope"]),
        execution_contract=execution_contract,
    )
    write_new_json(output_path, payload)
    frozen_payload_files = payload["files"]
    if not isinstance(frozen_payload_files, dict):
        raise TypeError("generated manifest files must be an object")
    print(f"Frozen {len(frozen_payload_files)} inputs")
    print(f"Protocol hash: {payload['protocol_hash']}")
    print(f"Manifest: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
