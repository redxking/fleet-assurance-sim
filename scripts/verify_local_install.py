#!/usr/bin/env python3
"""Verify a local Fleet Assurance Simulation installation."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

MINIMUM_PYTHON = (3, 11)
REQUIRED_PACKAGES = (
    "numpy",
    "scipy",
    "networkx",
    "pandas",
    "matplotlib",
    "plotly",
    "bokeh",
    "yaml",
    "pydantic",
)
DISTRIBUTION_NAMES = {
    "yaml": "PyYAML",
}


def run_command(command: list[str], cwd: Path) -> dict[str, object]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests", action="store_true", help="run the complete pytest suite")
    parser.add_argument("--demo", action="store_true", help="run a deterministic visual smoke scenario")
    parser.add_argument("--json-output", type=Path, default=None)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    checks: dict[str, object] = {
        "root": str(root),
        "python": sys.version,
        "platform": platform.platform(),
        "python_supported": sys.version_info >= MINIMUM_PYTHON,
        "imports": {},
        "files": {},
        "commands": [],
    }

    for module_name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(module_name)
            distribution = DISTRIBUTION_NAMES.get(module_name, module_name)
            version = importlib.metadata.version(distribution)
            checks["imports"][module_name] = {"ok": True, "version": version}
        except Exception as exc:  # noqa: BLE001
            checks["imports"][module_name] = {"ok": False, "error": str(exc)}

    try:
        fleet_module = importlib.import_module("fleet_sim")
        metadata_source = "installed-distribution"
        try:
            version = importlib.metadata.version("fleet-assurance-sim")
        except importlib.metadata.PackageNotFoundError:
            import tomllib

            project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
            version = str(project["project"]["version"])
            metadata_source = "source-tree-pyproject"
        checks["imports"]["fleet_sim"] = {
            "ok": True,
            "version": version,
            "metadata_source": metadata_source,
            "path": str(Path(fleet_module.__file__).resolve()),
        }
    except Exception as exc:  # noqa: BLE001
        checks["imports"]["fleet_sim"] = {"ok": False, "error": str(exc)}

    required_files = (
        "pyproject.toml",
        "configs/baselines/mixed_100_visual.yaml",
        "configs/parameters/registry.yaml",
        "docs/stage2_cycle7_preregistered_protocol.md",
        "manifests/stage2_cycle7_preregistration_manifest.json",
    )
    for relative in required_files:
        checks["files"][relative] = (root / relative).is_file()

    validate = run_command(
        [
            sys.executable,
            "-m",
            "fleet_sim",
            "validate",
            "--config",
            "configs/baselines/mixed_100_visual.yaml",
            "--registry",
            "configs/parameters/registry.yaml",
        ],
        root,
    )
    checks["commands"].append(validate)

    if args.tests:
        test_result = run_command([sys.executable, "-m", "pytest", "-q"], root)
        checks["commands"].append(test_result)

    if args.demo:
        with tempfile.TemporaryDirectory(prefix="fleet-assurance-smoke-") as directory:
            output = Path(directory)
            demo_result = run_command(
                [
                    sys.executable,
                    "-m",
                    "fleet_sim",
                    "run",
                    "--config",
                    "configs/baselines/mixed_100_visual.yaml",
                    "--output",
                    str(output),
                    "--visualize",
                ],
                root,
            )
            checks["commands"].append(demo_result)
            bundles = list((output / "replay_bundles").glob("*"))
            checks["demo_bundle_count"] = len(bundles)
            checks["demo_console_present"] = any(
                (bundle / "virtual_fleet_assurance_console.html").is_file()
                for bundle in bundles
            )

    imports_ok = all(row.get("ok", False) for row in checks["imports"].values())
    files_ok = all(checks["files"].values())
    commands_ok = all(row["returncode"] == 0 for row in checks["commands"])
    demo_ok = (not args.demo) or (
        checks.get("demo_bundle_count", 0) >= 1 and checks.get("demo_console_present", False)
    )
    checks["passed"] = bool(checks["python_supported"] and imports_ok and files_ok and commands_ok and demo_ok)

    print(json.dumps(checks, indent=2, sort_keys=True, default=str))
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(checks, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if checks["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
