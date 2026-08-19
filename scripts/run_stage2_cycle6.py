from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import traceback
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fleet_sim.experiments.stage2_cycle6 import run_stage2_cycle6


PROTOCOL_MANIFEST = ROOT / "manifests" / "stage2_cycle6_preregistration_manifest.json"
EXECUTION_MANIFEST = ROOT / "manifests" / "stage2_cycle6_execution_manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_frozen_inputs(manifest: dict[str, object]) -> tuple[bool, list[dict[str, object]]]:
    checks: list[dict[str, object]] = []
    all_match = True
    files = manifest.get("files", {})
    if not isinstance(files, dict):
        raise ValueError("preregistration manifest files field must be an object")
    for relative, expected in files.items():
        path = ROOT / str(relative)
        actual = sha256(path) if path.exists() else None
        match = actual == expected
        all_match = all_match and match
        checks.append(
            {
                "path": str(relative),
                "expected_sha256": expected,
                "actual_sha256": actual,
                "match": match,
            }
        )
    return all_match, checks


def environment_manifest() -> dict[str, object]:
    packages = {}
    for name in ("numpy", "scipy", "pandas", "networkx", "matplotlib"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "packages": packages,
    }


def artifact_hashes() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for directory in (ROOT / "results" / "stage2_cycle6", ROOT / "figures" / "stage2_cycle6"):
        if not directory.exists():
            continue
        for path in sorted(p for p in directory.rglob("*") if p.is_file()):
            rows.append(
                {
                    "path": str(path.relative_to(ROOT)),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    return rows


def write_manifest(payload: dict[str, object]) -> None:
    EXECUTION_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    EXECUTION_MANIFEST.write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )


def main() -> int:
    prereg = json.loads(PROTOCOL_MANIFEST.read_text(encoding="utf-8"))
    started = datetime.now(timezone.utc).isoformat()
    all_match, checks = verify_frozen_inputs(prereg)
    base: dict[str, object] = {
        "protocol_id": prereg["protocol_id"],
        "primary_seed": prereg["primary_seed"],
        "started_utc": started,
        "frozen_input_checks": checks,
        "all_frozen_inputs_match": all_match,
        "environment": environment_manifest(),
    }
    if not all_match:
        base.update(
            {
                "status": "aborted_before_execution",
                "completed_utc": datetime.now(timezone.utc).isoformat(),
                "reason": "one or more frozen input hashes did not match",
            }
        )
        write_manifest(base)
        print(json.dumps(base, indent=2))
        return 2

    try:
        summary = run_stage2_cycle6(ROOT, seed=int(prereg["primary_seed"]))
        base.update(
            {
                "status": "completed",
                "completed_utc": datetime.now(timezone.utc).isoformat(),
                "summary_path": "results/stage2_cycle6/stage2_cycle6_summary.json",
                "summary_decisions": {
                    "NH2_T_supported_in_model": bool(summary["NH2_T"]["supported_in_model"]),
                    "NH4_O_supported_in_model": bool(summary["NH4_O"]["supported_in_model"]),
                },
                "artifacts": artifact_hashes(),
            }
        )
        write_manifest(base)
        print(json.dumps(summary, indent=2, allow_nan=True))
        return 0
    except Exception as exc:
        base.update(
            {
                "status": "failed_during_execution",
                "completed_utc": datetime.now(timezone.utc).isoformat(),
                "exception_type": type(exc).__name__,
                "exception": str(exc),
                "traceback": traceback.format_exc(),
                "partial_artifacts": artifact_hashes(),
            }
        )
        write_manifest(base)
        print(json.dumps(base, indent=2, allow_nan=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
