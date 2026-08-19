from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fleet_sim.experiments.stage2_research import run_stage2_cycle4


if __name__ == "__main__":
    result = run_stage2_cycle4(ROOT)
    print(json.dumps(result, indent=2))
