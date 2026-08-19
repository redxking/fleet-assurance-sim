#!/usr/bin/env python3
"""Run an engineering pilot or a hash-gated Stage 3 confirmation."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")
ROOT = Path(__file__).resolve().parents[1]
os.environ["MPLCONFIGDIR"] = str(ROOT / ".matplotlib-cache")
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
sys.path.insert(0, str(ROOT / "src"))

from fleet_sim.experiments.stage3_protocol import (
    artifact_inventory,
    environment_snapshot,
    load_preexecution_manifest,
    validate_safe_identifier,
    write_new_json,
)
from fleet_sim.experiments.stage3_runner import execute_stage3


def _record_failure(
    root: Path,
    *,
    mode: str,
    execution_id: str,
    exc: Exception,
    traceback_text: str,
) -> Path | None:
    execution_id = validate_safe_identifier(execution_id, label="execution_id")
    if mode == "pilot":
        protocol_hash = "engineering-pilots"
    else:
        manifest_path = root / "manifests/stage3_preexecution_manifest.json"
        if not manifest_path.is_file():
            return None
        protocol_hash = str(load_preexecution_manifest(manifest_path)["protocol_hash"])
    execution_dir = root / "results/stage3" / protocol_hash / execution_id
    if not execution_dir.is_dir():
        return None
    failure_path = execution_dir / "execution_failure.json"
    write_new_json(
        failure_path,
        {
            "schema_version": "1.0",
            "status": "failed",
            "mode": mode,
            "execution_id": execution_id,
            "exception_type": type(exc).__name__,
            "exception": str(exc),
            "traceback": traceback_text,
            "environment": environment_snapshot(),
            "actual_command_argv": [sys.executable, *sys.argv],
            "retained_artifacts_before_failure_record": artifact_inventory(
                execution_dir, root=root
            ),
        },
    )
    return failure_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("pilot", "confirmatory"), required=True)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--stage3a-replications", type=int, default=None)
    parser.add_argument("--stage3b-replications", type=int, default=None)
    parser.add_argument("--bootstrap-draws", type=int, default=None)
    args = parser.parse_args()
    execution_id = validate_safe_identifier(args.execution_id, label="execution_id")
    if args.mode == "pilot":
        stage3a_replications = args.stage3a_replications or 2
        stage3b_replications = args.stage3b_replications or 2
        bootstrap_draws = args.bootstrap_draws or 200
    else:
        stage3a_replications = args.stage3a_replications or 12
        stage3b_replications = args.stage3b_replications or 10
        bootstrap_draws = args.bootstrap_draws or 5000
    try:
        artifacts = execute_stage3(
            args.root,
            mode=args.mode,
            execution_id=execution_id,
            stage3a_replications=stage3a_replications,
            stage3b_replications=stage3b_replications,
            bootstrap_draws=bootstrap_draws,
        )
    except Exception as exc:  # noqa: BLE001
        traceback_text = traceback.format_exc()
        failure_path: Path | None = None
        failure_recording_error: str | None = None
        try:
            failure_path = _record_failure(
                args.root.resolve(),
                mode=args.mode,
                execution_id=execution_id,
                exc=exc,
                traceback_text=traceback_text,
            )
        except Exception as recording_exc:  # noqa: BLE001
            failure_recording_error = f"{type(recording_exc).__name__}: {recording_exc}"
        print(
            json.dumps(
                {
                    "status": "failed",
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                    "traceback": traceback_text,
                    "failure_artifact": str(failure_path) if failure_path else None,
                    "failure_recording_error": failure_recording_error,
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "status": "completed",
                "execution_dir": str(artifacts.execution_dir),
                "evidence": str(artifacts.evidence_path),
                "manifest": str(artifacts.execution_manifest_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
