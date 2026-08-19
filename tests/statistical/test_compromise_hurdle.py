import numpy as np
import pandas as pd

from fleet_sim.analysis.compromise_hurdle import (
    add_replication_conditionals,
    fit_compromise_hurdle,
    predict_compromise_hurdle,
)


def _fixture():
    scenarios = pd.DataFrame(
        {
            "scenario_id": range(6),
            "n_agents": [100, 100, 200, 200, 400, 400],
            "temporal_nb": [0.4, 0.7, 0.9, 1.2, 1.5, 1.9],
            "nb_pre": [0.5, 0.8, 1.0, 1.4, 1.7, 2.2],
            "outbreak_rate": [0.0, 0.1, 0.2, 0.4, 0.7, 0.9],
            "replications": [10] * 6,
            "mean_ever_fraction": [0.01, 0.03, 0.06, 0.15, 0.35, 0.55],
        }
    )
    rows = []
    for row in scenarios.itertuples(index=False):
        outbreaks = int(round(10 * row.outbreak_rate))
        for replication in range(10):
            is_outbreak = replication < outbreaks
            rows.append(
                {
                    "scenario_id": row.scenario_id,
                    "n_agents": row.n_agents,
                    "ever_compromised_fraction": 0.2 + 0.04 * row.nb_pre if is_outbreak else 1 / row.n_agents,
                    "outbreak_10pct": int(is_outbreak),
                }
            )
    return scenarios, pd.DataFrame(rows)


def test_hurdle_predictions_are_bounded_and_monotone_in_probability():
    scenarios, replications = _fixture()
    enriched = add_replication_conditionals(scenarios, replications)
    model = fit_compromise_hurdle(enriched)
    prediction = predict_compromise_hurdle(model, enriched)
    assert np.all((prediction.expected_final_fraction >= 0.0) & (prediction.expected_final_fraction <= 1.0))
    assert np.all(np.diff(prediction.outbreak_probability) >= -1e-12)
    assert np.all(prediction.conditional_outbreak_severity >= 0.10)


def test_conditionals_preserve_replication_counts():
    scenarios, replications = _fixture()
    enriched = add_replication_conditionals(scenarios, replications)
    assert np.all(enriched.outbreak_replication_count + enriched.nonoutbreak_replication_count == 10)
