from __future__ import annotations

import math

import numpy as np

from fleet_sim.graphs import build_graph
from fleet_sim.security import approximate_critical_q, percolation_distribution, simulate_gossip, simulate_sis


def test_gossip_complete_graph_has_logarithmic_round_growth() -> None:
    sizes = [32, 128, 512]
    means = []
    for n in sizes:
        bundle = build_graph(n, "complete", seed=n)
        rounds = []
        for seed in range(12):
            result = simulate_gossip(bundle, seed=1000 + seed, fanout=2, protocol="push_pull")
            value = result.rounds_to_coverage(0.99)
            assert value is not None
            rounds.append(value)
        means.append(float(np.mean(rounds)))
    slope = np.polyfit(np.log2(sizes), means, 1)[0]
    assert 0.0 < slope < 3.0
    assert means[-1] < 4.0 * math.log2(sizes[-1])


def test_random_regular_percolation_transition() -> None:
    bundle = build_graph(400, "random_regular", seed=8, degree=4)
    critical = approximate_critical_q(bundle)
    assert math.isclose(critical, 1 / 3, rel_tol=0.05)
    below = percolation_distribution(bundle, q=0.15, replications=60, seed=9)
    above = percolation_distribution(bundle, q=0.70, replications=60, seed=10)
    assert below.mean < 0.10
    assert above.mean > 0.80


def test_sis_subcritical_extinction_exceeds_supercritical_extinction() -> None:
    bundle = build_graph(120, "random_regular", seed=12, degree=4)
    subcritical = []
    supercritical = []
    for seed in range(20):
        subcritical.append(simulate_sis(bundle, beta=0.03, gamma=0.5, seed=seed, duration=30.0, dt=0.1).extinct)
        supercritical.append(simulate_sis(bundle, beta=0.6, gamma=0.1, seed=100 + seed, duration=30.0, dt=0.1).extinct)
    assert sum(subcritical) > sum(supercritical)
    assert sum(subcritical) >= 15
