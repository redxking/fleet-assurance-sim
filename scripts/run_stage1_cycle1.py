from pathlib import Path
import json

from fleet_sim.experiments.stage1_research import run_stage1_cycle

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    result = run_stage1_cycle(root)
    print(json.dumps(result, indent=2))
