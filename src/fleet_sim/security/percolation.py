"""Bond-percolation blast-radius experiments."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from fleet_sim.graphs import GraphBundle


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.size = [1] * n

    def find(self, node: int) -> int:
        while self.parent[node] != node:
            self.parent[node] = self.parent[self.parent[node]]
            node = self.parent[node]
        return node

    def union(self, left: int, right: int) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return
        if self.size[root_left] < self.size[root_right]:
            root_left, root_right = root_right, root_left
        self.parent[root_right] = root_left
        self.size[root_left] += self.size[root_right]

    def largest(self) -> int:
        return max(self.size[self.find(node)] for node in range(len(self.parent)))


@dataclass(frozen=True, slots=True)
class PercolationResult:
    q: float
    largest_component_fractions: tuple[float, ...]

    @property
    def mean(self) -> float:
        return float(np.mean(self.largest_component_fractions))

    def quantile(self, probability: float) -> float:
        return float(np.quantile(self.largest_component_fractions, probability))


def bond_percolation_trial(bundle: GraphBundle, q: float, rng: np.random.Generator) -> float:
    if not 0 <= q <= 1:
        raise ValueError("q must be in [0, 1]")
    graph = bundle.materialize()
    union_find = _UnionFind(bundle.n)
    for left, right in graph.edges:
        if rng.random() < q:
            union_find.union(int(left), int(right))
    return union_find.largest() / bundle.n


def percolation_distribution(
    bundle: GraphBundle,
    *,
    q: float,
    replications: int,
    seed: int,
) -> PercolationResult:
    if replications < 1:
        raise ValueError("replications must be positive")
    sequence = np.random.SeedSequence(seed)
    children = sequence.spawn(replications)
    fractions = []
    for child in children:
        rng = np.random.Generator(np.random.PCG64DXSM(child))
        fractions.append(bond_percolation_trial(bundle, q, rng))
    return PercolationResult(q, tuple(fractions))


def approximate_critical_q(bundle: GraphBundle) -> float:
    if bundle.n <= 1:
        return float("inf")
    if bundle.topology == "complete" or bundle.topology.startswith("complete+"):
        return 1.0 / (bundle.n - 1)
    graph = bundle.materialize()
    degrees = np.fromiter((degree for _, degree in graph.degree()), dtype=float)
    mean = float(np.mean(degrees)) if len(degrees) else 0.0
    denominator = float(np.mean(degrees**2) - mean) if len(degrees) else 0.0
    return mean / denominator if denominator > 0 else float("inf")
