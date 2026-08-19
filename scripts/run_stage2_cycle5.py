from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fleet_sim.experiments.stage2_cycle5 import run_stage2_cycle5

MANIFEST = ROOT / "manifests" / "stage2_cycle5_preregistration_manifest.json"
EXECUTION_MANIFEST = ROOT / "manifests" / "stage2_cycle5_execution_manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_frozen_inputs() -> dict[str, bool]:
    prereg = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {
        relative: sha256(ROOT / relative) == expected
        for relative, expected in prereg["files"].items()
    }


def main() -> None:
    checks = verify_frozen_inputs()
    if not all(checks.values()):
        EXECUTION_MANIFEST.write_text(
            json.dumps(
                {
                    "protocol_id": "FAS-S2-C5-2026-08-19",
                    "execution_exit_code": 2,
                    "frozen_input_hashes_verified": checks,
                    "all_frozen_inputs_match": False,
                    "result": "aborted before simulation",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        raise SystemExit(2)

    start = time.perf_counter()
    summary = run_stage2_cycle5(ROOT, seed=20260820)
    runtime = time.perf_counter() - start

    artifact_paths = sorted(
        [
            *list((ROOT / "results" / "stage2_cycle5").glob("*")),
            *list((ROOT / "figures" / "stage2_cycle5").glob("*")),
        ]
    )
    artifacts = {
        str(path.relative_to(ROOT)): {
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in artifact_paths
        if path.is_file()
    }
    EXECUTION_MANIFEST.write_text(
        json.dumps(
            {
                "protocol_id": "FAS-S2-C5-2026-08-19",
                "primary_seed": 20260820,
                "execution_exit_code": 0,
                "frozen_input_hashes_verified": checks,
                "all_frozen_inputs_match": True,
                "runtime_seconds": runtime,
                "environment": {
                    "python": sys.version,
                    "platform": platform.platform(),
                },
                "artifacts": artifacts,
                "summary": summary,
            },
            indent=2,
            allow_nan=True,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, allow_nan=True))


if __name__ == "__main__":
    main()
