from __future__ import annotations

import math

from fleet_sim.graphs import apply_segmentation, build_graph, graph_metrics, spectral_radius


def test_complete_graph_metrics() -> None:
    bundle = build_graph(10, "complete", seed=1)
    metrics = graph_metrics(bundle)
    assert metrics["edges"] == 45
    assert math.isclose(float(metrics["mean_degree"]), 9.0)
    assert math.isclose(spectral_radius(bundle), 9.0, rel_tol=1e-12)


def test_random_regular_degree_and_spectral_radius() -> None:
    bundle = build_graph(100, "random_regular", seed=2, degree=4)
    metrics = graph_metrics(bundle)
    assert metrics["edges"] == 200
    assert math.isclose(float(metrics["mean_degree"]), 4.0, rel_tol=1e-12)
    assert math.isclose(float(metrics["spectral_radius"]), 4.0, rel_tol=1e-6)


def test_partition_segmentation_reduces_spectral_radius() -> None:
    complete = build_graph(64, "complete", seed=3)
    segmented = apply_segmentation(complete, "partition", partitions=8)
    assert spectral_radius(segmented) < spectral_radius(complete)
    assert graph_metrics(segmented)["components"] == 8
