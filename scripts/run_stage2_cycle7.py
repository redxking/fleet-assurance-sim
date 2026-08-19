#!/usr/bin/env python3
"""Hash-gated runner for Stage 2 Cycle 7."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
from datetime import datetime, timezone

from fleet_sim.experiments.stage2_cycle7 import run_stage2_cycle7


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact(path: Path, root: Path) -> dict[str, object]:
    return {"path": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": digest(path)}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    prereg_path = root / "manifests/stage2_cycle7_preregistration_manifest.json"
    prereg = json.loads(prereg_path.read_text())
    checks = []
    for relative, expected in prereg["files"].items():
        path = root / relative
        actual = digest(path) if path.exists() else None
        checks.append({"path": relative, "expected_sha256": expected, "actual_sha256": actual, "match": actual == expected})
    if not all(row["match"] for row in checks):
        print(json.dumps({"status": "aborted", "frozen_input_checks": checks}, indent=2))
        return 2

    started = datetime.now(timezone.utc).isoformat()
    summary = run_stage2_cycle7(root)
    outputs = sorted((root / "results/stage2_cycle7").glob("*")) + sorted((root / "figures/stage2_cycle7").glob("*"))
    manifest = {
        "protocol_id": prereg["protocol_id"],
        "started_utc": started,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "all_frozen_inputs_match": True,
        "frozen_input_checks": checks,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "packages": {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "pandas", "networkx", "matplotlib")},
        },
        "summary_decision": summary["decision"],
        "artifacts": [artifact(path, root) for path in outputs if path.is_file()],
    }
    (root / "manifests/stage2_cycle7_execution_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
