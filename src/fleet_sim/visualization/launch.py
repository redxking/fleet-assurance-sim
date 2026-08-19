"""Local launcher for the offline Bokeh assurance console."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch the Virtual Fleet Assurance Console")
    parser.add_argument("--port", type=int, default=5006)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--address",
        default=os.environ.get("FLEET_CONSOLE_ADDRESS", "127.0.0.1"),
        help="address on which the Bokeh server listens",
    )
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args()

    app_path = Path(__file__).resolve().with_name("app.py")
    repository_root = args.root or Path(__file__).resolve().parents[3]
    environment = os.environ.copy()
    environment["FLEET_SIM_ROOT"] = str(repository_root)
    src_path = repository_root / "src"
    environment["PYTHONPATH"] = str(src_path) + os.pathsep + environment.get("PYTHONPATH", "")

    command = [
        sys.executable,
        "-m",
        "bokeh",
        "serve",
        str(app_path),
        "--port",
        str(args.port),
        "--address",
        str(args.address),
    ]
    if not args.no_browser:
        command.append("--show")
    return subprocess.run(command, env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
