"""Run manifest and environment capture."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any


CORE_PACKAGES = [
    "numpy",
    "scipy",
    "networkx",
    "pandas",
    "matplotlib",
    "plotly",
    "pydantic",
    "PyYAML",
]


def _git_value(root: Path, arguments: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None


def dependency_versions() -> dict[str, str]:
    output: dict[str, str] = {}
    for package in CORE_PACKAGES:
        try:
            output[package] = version(package)
        except PackageNotFoundError:
            output[package] = "not-installed"
    return output


def system_memory_bytes() -> int | None:
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        pages = os.sysconf("SC_PHYS_PAGES")
        return int(page_size * pages)
    except (ValueError, OSError, AttributeError):
        return None


def capture_manifest(
    root: Path,
    run_id: str,
    configuration_hash: str,
    seed: int,
    substreams: dict[str, object],
    started_unix: float,
    ended_unix: float,
    trace_level: int | str,
    approximation_mode: str = "full-agent",
) -> dict[str, Any]:
    commit = _git_value(root, ["rev-parse", "HEAD"])
    dirty = _git_value(root, ["status", "--porcelain"])
    manifest = {
        "run_id": run_id,
        "configuration_hash": configuration_hash,
        "seed": seed,
        "random_substreams": substreams,
        "source_control_commit": commit,
        "dirty_tree": bool(dirty) if dirty is not None else None,
        "python_version": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "system_memory_bytes": system_memory_bytes(),
        "dependencies": dependency_versions(),
        "start_unix": started_unix,
        "end_unix": ended_unix,
        "wall_clock_s": ended_unix - started_unix,
        "trace_level": trace_level,
        "approximation_mode": approximation_mode,
    }
    manifest_payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    manifest["manifest_hash"] = hashlib.sha256(manifest_payload.encode("utf-8")).hexdigest()
    return manifest


def write_manifest(path: str | Path, manifest: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
