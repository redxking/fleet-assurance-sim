"""Build the offline Stage 3 evidence console."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATPLOTLIB_CACHE = Path(tempfile.gettempdir()) / "fleet-sim-matplotlib-cache"
MATPLOTLIB_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLBACKEND", "Agg")
configured_cache_value = os.environ.get("MPLCONFIGDIR")
configured_cache = Path(configured_cache_value) if configured_cache_value else None
if configured_cache is None or not configured_cache.is_dir() or not os.access(configured_cache, os.W_OK):
    os.environ["MPLCONFIGDIR"] = str(MATPLOTLIB_CACHE)
sys.path.insert(0, str(ROOT / "src"))

from fleet_sim.visualization.stage3_app import main

if __name__ == "__main__":
    raise SystemExit(main())
