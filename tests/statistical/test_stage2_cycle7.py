import numpy as np
import pandas as pd

from fleet_sim.experiments.stage2_cycle7 import _hierarchical_bootstrap


def test_cycle7_hierarchical_bootstrap_is_deterministic_and_paired():
    rows = []
    for block in range(3):
        for scenario in range(10):
            rows.append(
                {
                    "block": block,
                    "candidate_absolute_error": 0.02 + scenario * 0.001,
                    "baseline_absolute_error": 0.04 + scenario * 0.001,
                }
            )
    frame = pd.DataFrame(rows)
    first = _hierarchical_bootstrap(frame, seed=77, draws=100)
    second = _hierarchical_bootstrap(frame, seed=77, draws=100)
    assert first == second
    assert first["absolute_mae_reduction"][0] > 0.0
    assert np.isfinite(first["fractional_mae_improvement"]).all()
