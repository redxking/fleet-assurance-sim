"""Authorization-graph segmentation transformations."""

from __future__ import annotations

import networkx as nx


def partition_graph(graph: nx.Graph, partitions: int) -> nx.Graph:
    """Remove inter-partition edges using deterministic contiguous partitions."""

    if partitions < 1:
        raise ValueError("partitions must be positive")
    n = graph.number_of_nodes()
    segmented = nx.Graph()
    segmented.add_nodes_from(graph.nodes(data=True))
    for u, v, data in graph.edges(data=True):
        partition_u = min(partitions - 1, int(u) * partitions // max(n, 1))
        partition_v = min(partitions - 1, int(v) * partitions // max(n, 1))
        if partition_u == partition_v:
            segmented.add_edge(u, v, **data)
    segmented.graph.update(graph.graph)
    segmented.graph["segmentation"] = f"{partitions}-way"
    return segmented


def cap_degree(graph: nx.Graph, maximum_degree: int, seed: int = 0) -> nx.Graph:
    """Create a deterministic degree-capped authorization graph.

    Edges are retained in a seed-stable order while neither endpoint exceeds the
    configured degree cap. This is a policy abstraction, not an optimizer.
    """

    if maximum_degree < 0:
        raise ValueError("maximum_degree cannot be negative")
    capped = nx.Graph()
    capped.add_nodes_from(graph.nodes(data=True))
    edges = sorted(
        graph.edges(data=True),
        key=lambda item: hash((min(item[0], item[1]), max(item[0], item[1]), seed)),
    )
    for u, v, data in edges:
        if capped.degree(u) < maximum_degree and capped.degree(v) < maximum_degree:
            capped.add_edge(u, v, **data)
    capped.graph.update(graph.graph)
    capped.graph["segmentation"] = f"degree-cap-{maximum_degree}"
    return capped
