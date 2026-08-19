"""Finite stochastic SIS and SIR compromise propagation models."""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import numpy as np

from fleet_sim.graphs import GraphBundle, spectral_radius


@dataclass(frozen=True, slots=True)
class EpidemicResult:
    model: str
    times: tuple[float, ...]
    infected_fraction: tuple[float, ...]
    recovered_fraction: tuple[float, ...]
    peak_infected_fraction: float
    final_infected_fraction: float
    final_recovered_fraction: float
    extinct: bool


def epidemic_stability_product(bundle: GraphBundle, beta: float, gamma: float) -> float:
    if beta < 0 or gamma <= 0:
        raise ValueError("beta must be nonnegative and gamma positive")
    return (beta / gamma) * spectral_radius(bundle)


def heterogeneous_mean_field_sis_threshold(bundle: GraphBundle) -> float:
    graph = bundle.materialize()
    degrees = np.fromiter((degree for _, degree in graph.degree()), dtype=float)
    if len(degrees) == 0 or np.mean(degrees**2) == 0:
        return float("inf")
    return float(np.mean(degrees) / np.mean(degrees**2))


def heterogeneous_mean_field_sir_threshold(bundle: GraphBundle) -> float:
    graph = bundle.materialize()
    degrees = np.fromiter((degree for _, degree in graph.degree()), dtype=float)
    first = np.mean(degrees) if len(degrees) else 0.0
    denominator = np.mean(degrees**2) - first if len(degrees) else 0.0
    return float(first / denominator) if denominator > 0 else float("inf")


def simulate_sis(
    bundle: GraphBundle,
    *,
    beta: float,
    gamma: float,
    seed: int,
    initial_infected: tuple[int, ...] = (0,),
    duration: float = 50.0,
    dt: float = 0.05,
) -> EpidemicResult:
    if beta < 0 or gamma <= 0 or duration <= 0 or dt <= 0:
        raise ValueError("invalid SIS parameters")
    graph = bundle.materialize()
    rng = np.random.Generator(np.random.PCG64DXSM(seed))
    infected = {node for node in initial_infected if node in graph}
    times = [0.0]
    fractions = [len(infected) / bundle.n]
    recovered_fraction = [0.0]
    steps = int(np.ceil(duration / dt))

    for step in range(1, steps + 1):
        old = set(infected)
        next_infected = set(old)
        p_recovery = 1.0 - np.exp(-gamma * dt)
        for node in sorted(old):
            if rng.random() < p_recovery:
                next_infected.discard(node)
        for node in graph.nodes:
            if node in old:
                continue
            infected_neighbors = sum(neighbor in old for neighbor in graph.neighbors(node))
            if infected_neighbors == 0:
                continue
            p_infection = 1.0 - np.exp(-beta * infected_neighbors * dt)
            if rng.random() < p_infection:
                next_infected.add(node)
        infected = next_infected
        times.append(min(step * dt, duration))
        fractions.append(len(infected) / bundle.n)
        recovered_fraction.append(0.0)
        if not infected:
            break

    return EpidemicResult(
        "SIS",
        tuple(times),
        tuple(fractions),
        tuple(recovered_fraction),
        max(fractions),
        fractions[-1],
        0.0,
        len(infected) == 0,
    )


def simulate_sir(
    bundle: GraphBundle,
    *,
    beta: float,
    gamma: float,
    seed: int,
    initial_infected: tuple[int, ...] = (0,),
    duration: float = 50.0,
    dt: float = 0.05,
) -> EpidemicResult:
    if beta < 0 or gamma <= 0 or duration <= 0 or dt <= 0:
        raise ValueError("invalid SIR parameters")
    graph = bundle.materialize()
    rng = np.random.Generator(np.random.PCG64DXSM(seed))
    infected = {node for node in initial_infected if node in graph}
    recovered: set[int] = set()
    times = [0.0]
    infected_fractions = [len(infected) / bundle.n]
    recovered_fractions = [0.0]
    steps = int(np.ceil(duration / dt))

    for step in range(1, steps + 1):
        old_infected = set(infected)
        new_infected = set(old_infected)
        new_recovered = set(recovered)
        p_recovery = 1.0 - np.exp(-gamma * dt)
        for node in sorted(old_infected):
            if rng.random() < p_recovery:
                new_infected.discard(node)
                new_recovered.add(node)
        for node in graph.nodes:
            if node in old_infected or node in recovered:
                continue
            infected_neighbors = sum(neighbor in old_infected for neighbor in graph.neighbors(node))
            if infected_neighbors == 0:
                continue
            p_infection = 1.0 - np.exp(-beta * infected_neighbors * dt)
            if rng.random() < p_infection:
                new_infected.add(node)
        infected = new_infected - new_recovered
        recovered = new_recovered
        times.append(min(step * dt, duration))
        infected_fractions.append(len(infected) / bundle.n)
        recovered_fractions.append(len(recovered) / bundle.n)
        if not infected:
            break

    return EpidemicResult(
        "SIR",
        tuple(times),
        tuple(infected_fractions),
        tuple(recovered_fractions),
        max(infected_fractions),
        infected_fractions[-1],
        recovered_fractions[-1],
        len(infected) == 0,
    )
