"""Sparse graph generation, segmentation, and metrics for fleet graph layers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Iterator

import networkx as nx
import numpy as np
from scipy.sparse.linalg import eigsh


@dataclass(slots=True)
class GraphBundle:
    n: int
    topology: str
    parameters: dict[str, float | int | str]
    seed: int
    graph: nx.Graph | None
    representation: str = "exact"

    def nodes(self) -> range | nx.classes.reportviews.NodeView:
        return self.graph.nodes if self.graph is not None else range(self.n)

    def neighbors(self, node: int) -> Iterable[int]:
        if not 0 <= node < self.n:
            raise IndexError(node)
        if self.graph is not None:
            return self.graph.neighbors(node)
        if self.topology == "complete":
            return (candidate for candidate in range(self.n) if candidate != node)
        raise RuntimeError("implicit neighbors are not implemented for this topology")

    @property
    def number_of_edges(self) -> int:
        if self.graph is not None:
            return self.graph.number_of_edges()
        if self.topology == "complete":
            return self.n * (self.n - 1) // 2
        raise RuntimeError("implicit edge count is not implemented")

    def materialize(self, max_nodes: int = 2_000) -> nx.Graph:
        if self.graph is not None:
            return self.graph
        if self.topology == "complete" and self.n <= max_nodes:
            self.graph = nx.complete_graph(self.n)
            self.representation = "exact"
            return self.graph
        raise MemoryError(
            f"refusing to materialize {self.topology} graph with N={self.n}; use analytic metrics or aggregation"
        )


def _hierarchical_tree(n: int, span: int) -> nx.Graph:
    graph = nx.Graph()
    graph.add_nodes_from(range(n))
    for child in range(1, n):
        graph.add_edge((child - 1) // span, child)
    return graph


def build_graph(
    n: int,
    topology: str,
    *,
    seed: int,
    degree: int = 4,
    probability: float | None = None,
    attachment: int = 2,
    span: int = 8,
    complete_materialization_limit: int = 2_000,
) -> GraphBundle:
    if n < 1:
        raise ValueError("n must be at least 1")
    topology = topology.replace("hierarchical_tree", "hierarchical")
    parameters: dict[str, float | int | str] = {}

    if topology == "complete":
        graph = nx.complete_graph(n) if n <= complete_materialization_limit else None
        representation = "exact" if graph is not None else "implicit-exact"
    elif topology == "random_regular":
        if n == 1:
            graph = nx.empty_graph(1)
            effective_degree = 0
        else:
            effective_degree = min(max(1, degree), n - 1)
            if (n * effective_degree) % 2:
                effective_degree -= 1
            if effective_degree <= 0:
                graph = nx.empty_graph(n)
            else:
                graph = nx.random_regular_graph(effective_degree, n, seed=seed)
        parameters["degree"] = effective_degree
        representation = "exact"
    elif topology == "erdos_renyi":
        p = probability if probability is not None else min(1.0, degree / max(1, n - 1))
        if not 0 <= p <= 1:
            raise ValueError("Erdos-Renyi probability must be in [0, 1]")
        graph = nx.fast_gnp_random_graph(n, p, seed=seed)
        parameters["probability"] = p
        representation = "exact"
    elif topology == "barabasi_albert":
        if n <= 1:
            graph = nx.empty_graph(n)
            effective_attachment = 0
        else:
            effective_attachment = min(max(1, attachment), n - 1)
            graph = nx.barabasi_albert_graph(n, effective_attachment, seed=seed)
        parameters["attachment"] = effective_attachment
        representation = "exact"
    elif topology == "hierarchical":
        if span < 2:
            raise ValueError("hierarchy span must be at least 2")
        graph = _hierarchical_tree(n, span)
        parameters["span"] = span
        representation = "exact"
    else:
        raise ValueError(f"unsupported topology: {topology}")

    return GraphBundle(n, topology, parameters, seed, graph, representation)


def _sample_effective_diameter(graph: nx.Graph, seed: int, samples: int = 32) -> float:
    if graph.number_of_nodes() <= 1:
        return 0.0
    components = list(nx.connected_components(graph))
    largest = graph.subgraph(max(components, key=len))
    if largest.number_of_nodes() <= 2_000:
        return float(nx.diameter(largest))
    rng = np.random.default_rng(seed)
    nodes = np.array(list(largest.nodes()))
    selected = rng.choice(nodes, size=min(samples, len(nodes)), replace=False)
    distances: list[int] = []
    for source in selected:
        distances.extend(nx.single_source_shortest_path_length(largest, int(source)).values())
    return float(np.quantile(distances, 0.90)) if distances else math.inf


def spectral_radius(bundle: GraphBundle) -> float:
    if bundle.n <= 1:
        return 0.0
    if bundle.graph is None and bundle.topology == "complete":
        return float(bundle.n - 1)
    graph = bundle.materialize()
    if graph.number_of_edges() == 0:
        return 0.0
    adjacency = nx.to_scipy_sparse_array(graph, dtype=float, format="csr")
    if bundle.n <= 4:
        return float(max(np.linalg.eigvalsh(adjacency.toarray())))
    value = eigsh(adjacency, k=1, which="LA", return_eigenvectors=False, tol=1e-7)[0]
    return float(value)


def graph_metrics(bundle: GraphBundle) -> dict[str, float | int | str | None]:
    n = bundle.n
    if bundle.graph is None and bundle.topology == "complete":
        return {
            "n": n,
            "edges": bundle.number_of_edges,
            "mean_degree": float(n - 1),
            "degree_second_moment": float((n - 1) ** 2),
            "clustering": 1.0 if n >= 3 else 0.0,
            "components": 1,
            "diameter_or_effective_diameter": 1.0 if n > 1 else 0.0,
            "spectral_radius": float(n - 1),
            "algebraic_connectivity": float(n) if n > 1 else 0.0,
            "representation": bundle.representation,
        }

    graph = bundle.materialize()
    degrees = np.fromiter((degree for _, degree in graph.degree()), dtype=float, count=n)
    components = nx.number_connected_components(graph)
    if n <= 5_000:
        clustering = float(nx.average_clustering(graph))
    else:
        clustering = float(nx.algorithms.approximation.average_clustering(graph, trials=1_000, seed=bundle.seed))
    algebraic: float | None = None
    if n > 1 and components == 1 and n <= 500:
        laplacian = nx.laplacian_matrix(graph).toarray().astype(float)
        eigenvalues = np.linalg.eigvalsh(laplacian)
        algebraic = float(max(0.0, eigenvalues[1]))
    return {
        "n": n,
        "edges": graph.number_of_edges(),
        "mean_degree": float(degrees.mean()) if len(degrees) else 0.0,
        "degree_second_moment": float(np.mean(degrees**2)) if len(degrees) else 0.0,
        "clustering": clustering,
        "components": components,
        "diameter_or_effective_diameter": _sample_effective_diameter(graph, bundle.seed),
        "spectral_radius": spectral_radius(bundle),
        "algebraic_connectivity": algebraic,
        "representation": bundle.representation,
    }


def apply_segmentation(
    bundle: GraphBundle,
    policy: str,
    *,
    partitions: int = 8,
    degree_cap: int = 8,
) -> GraphBundle:
    if policy == "none":
        graph = bundle.graph.copy() if bundle.graph is not None else None
        return GraphBundle(bundle.n, bundle.topology, dict(bundle.parameters), bundle.seed, graph, bundle.representation)
    graph = bundle.materialize().copy()
    partitions = max(1, min(partitions, bundle.n))

    if policy in {"flat_tenancy", "partition"}:
        graph.remove_edges_from(
            [(u, v) for u, v in graph.edges() if (u % partitions) != (v % partitions)]
        )
    elif policy == "dynamic_microsegmentation":
        graph.remove_edges_from(
            [(u, v) for u, v in graph.edges() if (u % partitions) != (v % partitions)]
        )
        representatives = [partition for partition in range(partitions) if partition < bundle.n]
        for left, right in zip(representatives, representatives[1:]):
            graph.add_edge(left, right, assurance_boundary="gateway")
    elif policy == "degree_cap":
        removals: set[tuple[int, int]] = set()
        for node in sorted(graph.nodes()):
            neighbors = sorted(graph.neighbors(node))
            for neighbor in neighbors[degree_cap:]:
                removals.add(tuple(sorted((node, neighbor))))
        graph.remove_edges_from(removals)
    else:
        raise ValueError(f"unsupported segmentation policy: {policy}")

    parameters = dict(bundle.parameters)
    parameters.update({"segmentation_policy": policy, "partitions": partitions, "degree_cap": degree_cap})
    return GraphBundle(bundle.n, f"{bundle.topology}+{policy}", parameters, bundle.seed, graph, "exact")
