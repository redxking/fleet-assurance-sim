#!/usr/bin/env python3
"""Build all Stage 0 verification artifacts from the repository root."""

from __future__ import annotations

import json
from pathlib import Path

from fleet_sim.experiments.stage0 import run_stage0


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    report = run_stage0(root, root, replications=30)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
