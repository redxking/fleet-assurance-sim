"""Dimensionless Fleet Admission Stress model for Stage 2 Cycle 3.

The resource rates, queue budgets, routing probabilities, and disturbance
parameters are notional. The implementation tests whether a normalized load
construct transfers across fleet size and admission profile within the model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

RESOURCE_NAMES = ("identity", "policy", "telemetry", "supervision")


@dataclass(frozen=True)
class AdmissionResource:
    name: str
    capacity_per_s: float
    assurance_utilization_target: float
    max_wait_s: float
    background_work_per_agent_s: float
    admission_work_per_agent: float


@dataclass(frozen=True)
class AdmissionSystem:
    resources: tuple[AdmissionResource, ...]
    true_routing: np.ndarray
    observed_routing: np.ndarray

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(resource.name for resource in self.resources)


@dataclass(frozen=True)
class AdmissionPredictors:
    final_n: float
    peak_population_velocity: float
    peak_work_headroom_ratio: float
    independent_stress: float
    coupled_stress: float
    binding_independent_resource: str
    binding_coupled_resource: str

    def as_dict(self) -> dict[str, float | str]:
        return {
            "final_n": self.final_n,
            "peak_population_velocity": self.peak_population_velocity,
            "peak_work_headroom_ratio": self.peak_work_headroom_ratio,
            "independent_stress": self.independent_stress,
            "coupled_stress": self.coupled_stress,
            "binding_independent_resource": self.binding_independent_resource,
            "binding_coupled_resource": self.binding_coupled_resource,
        }


def build_admission_pools(
    *,
    final_n: int,
    final_baseline_fraction: float = 0.55,
    coupling_scale: float = 1.0,
    seed: int = 0,
) -> AdmissionSystem:
    if final_n < 1:
        raise ValueError("final_n must be positive")
    if not 0.20 <= final_baseline_fraction < 0.90:
        raise ValueError("final_baseline_fraction must be in [0.20, 0.90)")
    if coupling_scale <= 0.0:
        raise ValueError("coupling_scale must be positive")

    work_quantum = 50.0
    background = work_quantum * np.asarray([0.0018, 0.0065, 0.0105, 0.00125], dtype=float)
    admission = work_quantum * np.asarray([0.050, 0.150, 0.250, 0.025], dtype=float)
    eta = np.asarray([0.72, 0.70, 0.74, 0.68], dtype=float)
    max_wait = np.asarray([3.5, 1.8, 3.0, 9.0], dtype=float)

    base_routing = np.asarray(
        [
            [0.000, 0.110, 0.025, 0.015],
            [0.050, 0.000, 0.095, 0.030],
            [0.015, 0.025, 0.000, 0.120],
            [0.020, 0.035, 0.018, 0.000],
        ],
        dtype=float,
    )
    true_routing = np.clip(base_routing * coupling_scale, 0.0, 0.35)
    row_sums = true_routing.sum(axis=1)
    for index, total in enumerate(row_sums):
        if total >= 0.72:
            true_routing[index] *= 0.72 / total

    rng = np.random.default_rng(seed)
    observed_routing = np.clip(
        true_routing * rng.lognormal(-0.5 * 0.14**2, 0.14, size=true_routing.shape),
        0.0,
        0.40,
    )
    observed_routing[true_routing == 0.0] = 0.0
    observed_row_sums = observed_routing.sum(axis=1)
    for index, total in enumerate(observed_row_sums):
        if total >= 0.75:
            observed_routing[index] *= 0.75 / total

    # Size each pool from coupled steady-state background work, not from raw
    # exogenous work. This prevents the routing network from being unstable at
    # the declared final population before any admission transient occurs.
    effective_background = background @ np.linalg.inv(np.eye(len(background)) - true_routing)
    capacities = effective_background * float(final_n) / final_baseline_fraction
    resources = tuple(
        AdmissionResource(
            name=name,
            capacity_per_s=float(capacities[index]),
            assurance_utilization_target=float(eta[index]),
            max_wait_s=float(max_wait[index]),
            background_work_per_agent_s=float(background[index]),
            admission_work_per_agent=float(admission[index]),
        )
        for index, name in enumerate(RESOURCE_NAMES)
    )
    return AdmissionSystem(
        resources=resources,
        true_routing=true_routing,
        observed_routing=observed_routing,
    )


def normalized_population_curve(profile: str, x: np.ndarray) -> np.ndarray:
    z = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    if profile == "linear":
        return z
    if profile == "staged":
        # Four admission tranches with short dwell intervals.
        return np.minimum(1.0, np.floor(4.0 * z + 1e-12) / 4.0)
    if profile == "burst":
        return np.minimum(1.0, 0.62 * (z > 0.05) + 0.38 * np.clip((z - 0.55) / 0.15, 0.0, 1.0))
    if profile == "logistic":
        raw = 1.0 / (1.0 + np.exp(-10.0 * (z - 0.50)))
        lo = 1.0 / (1.0 + np.exp(5.0))
        hi = 1.0 / (1.0 + np.exp(-5.0))
        return (raw - lo) / (hi - lo)
    if profile == "exponential":
        return np.expm1(4.0 * z) / np.expm1(4.0)
    if profile == "step":
        return (z > 0.0).astype(float)
    raise ValueError(f"unsupported admission profile: {profile}")


def make_admission_trajectory(
    profile: str,
    *,
    final_n: int,
    duration_s: float,
    initial_fraction: float = 0.20,
    recovery_window_s: float = 150.0,
    dt_s: float = 0.5,
) -> pd.DataFrame:
    if final_n < 1 or duration_s <= 0.0 or dt_s <= 0.0:
        raise ValueError("invalid trajectory arguments")
    if not 0.0 <= initial_fraction < 1.0:
        raise ValueError("initial_fraction must be in [0, 1)")
    initial_n = float(final_n) * initial_fraction
    horizon = duration_s + recovery_window_s
    time_s = np.arange(0.0, horizon + 1e-12, dt_s)
    normalized_time = time_s / duration_s
    curve = normalized_population_curve(profile, normalized_time)
    population = initial_n + (float(final_n) - initial_n) * curve
    population[time_s >= duration_s] = float(final_n)
    admission_rate = np.diff(population, prepend=population[0]) / dt_s
    admission_rate = np.maximum(0.0, admission_rate)
    return pd.DataFrame(
        {
            "time_s": time_s,
            "n_agents": population,
            "admission_rate_agents_s": admission_rate,
            "profile": profile,
            "final_n": int(final_n),
            "duration_s": float(duration_s),
        }
    )


def _effective_work(external: np.ndarray, routing: np.ndarray) -> np.ndarray:
    identity = np.eye(routing.shape[0], dtype=float)
    inverse = np.linalg.inv(identity - routing)
    return external @ inverse


def _stress_from_routing(
    n_agents: np.ndarray,
    admission_rate: np.ndarray,
    system: AdmissionSystem,
    routing: np.ndarray,
    *,
    dt_s: float,
) -> tuple[float, str, pd.DataFrame]:
    resources = system.resources
    background = np.asarray([r.background_work_per_agent_s for r in resources], dtype=float)
    admission_work = np.asarray([r.admission_work_per_agent for r in resources], dtype=float)
    capacity = np.asarray([r.capacity_per_s for r in resources], dtype=float)
    eta = np.asarray([r.assurance_utilization_target for r in resources], dtype=float)
    wait_budget = np.asarray([r.max_wait_s for r in resources], dtype=float)

    external = n_agents[:, None] * background[None, :] + admission_rate[:, None] * admission_work[None, :]
    effective = _effective_work(external, routing)
    queues = np.zeros_like(effective)
    for index in range(1, len(effective)):
        queues[index] = np.maximum(
            0.0,
            queues[index - 1] + (effective[index] - capacity) * dt_s,
        )
    offered_ratio = effective / np.maximum(eta * capacity, 1e-12)
    queue_ratio = queues / np.maximum(capacity * wait_budget, 1e-12)
    combined = np.maximum(offered_ratio, queue_ratio)
    max_index = np.unravel_index(int(np.argmax(combined)), combined.shape)
    stress = float(combined[max_index])
    binding = resources[max_index[1]].name

    rows: list[dict[str, float | str]] = []
    for time_index in range(len(n_agents)):
        for resource_index, resource in enumerate(resources):
            rows.append(
                {
                    "time_index": float(time_index),
                    "resource": resource.name,
                    "external_work_rate": float(external[time_index, resource_index]),
                    "effective_work_rate": float(effective[time_index, resource_index]),
                    "capacity_per_s": float(capacity[resource_index]),
                    "offered_target_ratio": float(offered_ratio[time_index, resource_index]),
                    "fluid_queue": float(queues[time_index, resource_index]),
                    "queue_budget_ratio": float(queue_ratio[time_index, resource_index]),
                }
            )
    return stress, binding, pd.DataFrame(rows)


def admission_load_predictors(
    n_agents: Sequence[float] | np.ndarray,
    admission_rate_agents_s: Sequence[float] | np.ndarray,
    system: AdmissionSystem,
    *,
    dt_s: float,
) -> dict[str, float | str | pd.DataFrame]:
    n = np.asarray(n_agents, dtype=float)
    rate = np.asarray(admission_rate_agents_s, dtype=float)
    if n.shape != rate.shape or n.ndim != 1 or len(n) < 2:
        raise ValueError("population and admission-rate arrays must be equal one-dimensional arrays")
    resources = system.resources
    capacity = np.asarray([r.capacity_per_s for r in resources], dtype=float)
    eta = np.asarray([r.assurance_utilization_target for r in resources], dtype=float)
    background = np.asarray([r.background_work_per_agent_s for r in resources], dtype=float)
    work = np.asarray([r.admission_work_per_agent for r in resources], dtype=float)
    remaining_headroom = eta[None, :] * capacity[None, :] - n[:, None] * background[None, :]
    headroom_ratio = rate[:, None] * work[None, :] / np.maximum(remaining_headroom, 1e-12)
    peak_headroom = float(np.max(headroom_ratio))

    independent, independent_binding, independent_trace = _stress_from_routing(
        n,
        rate,
        system,
        np.zeros_like(system.observed_routing),
        dt_s=dt_s,
    )
    coupled, coupled_binding, coupled_trace = _stress_from_routing(
        n,
        rate,
        system,
        system.observed_routing,
        dt_s=dt_s,
    )
    return {
        "final_n": float(n[-1]),
        "peak_population_velocity": float(np.max(rate)),
        "peak_work_headroom_ratio": peak_headroom,
        "independent_stress": independent,
        "coupled_stress": coupled,
        "peak_lambda_a": coupled,
        "binding_independent_resource": independent_binding,
        "binding_coupled_resource": coupled_binding,
        "independent_trace": independent_trace,
        "coupled_trace": coupled_trace,
    }


def _dynamic_routing(base: np.ndarray, queue_ratio: np.ndarray) -> np.ndarray:
    routing = base.copy()
    routing *= (1.0 + 0.38 * np.clip(queue_ratio[:, None], 0.0, 3.0))
    for index, total in enumerate(routing.sum(axis=1)):
        if total > 0.82:
            routing[index] *= 0.82 / total
    return routing


def simulate_admission_queue(
    trajectory: pd.DataFrame,
    system: AdmissionSystem,
    *,
    seed: int,
) -> dict[str, float | int | str]:
    rng = np.random.default_rng(seed)
    n = trajectory.n_agents.to_numpy(float)
    rate = trajectory.admission_rate_agents_s.to_numpy(float)
    time_s = trajectory.time_s.to_numpy(float)
    dt_s = float(np.median(np.diff(time_s)))
    resources = system.resources
    count = len(resources)
    capacity = np.asarray([r.capacity_per_s for r in resources], dtype=float)
    eta = np.asarray([r.assurance_utilization_target for r in resources], dtype=float)
    wait_budget = np.asarray([r.max_wait_s for r in resources], dtype=float)
    background = np.asarray([r.background_work_per_agent_s for r in resources], dtype=float)
    work = np.asarray([r.admission_work_per_agent for r in resources], dtype=float)

    queue = np.zeros(count, dtype=float)
    routed_next = np.zeros(count, dtype=float)
    utilization_ewma = np.full(count, 0.0, dtype=float)
    persistence = np.zeros(count, dtype=int)
    crossed = False
    first_crossing = float("nan")
    recovery_time = float("nan")
    maximum_wait_ratio = 0.0
    maximum_utilization_ratio = 0.0
    minimum_margin = 1.0
    binding_resource = "none"
    outside_steps = 0
    admission_end = float(trajectory.duration_s.iloc[0])

    for index, now in enumerate(time_s):
        external_rate = n[index] * background + rate[index] * work
        external = rng.poisson(np.maximum(0.0, external_rate * dt_s)).astype(float)

        telemetry_index = RESOURCE_NAMES.index("telemetry")
        supervision_index = RESOURCE_NAMES.index("supervision")
        telemetry_queue_ratio = queue[telemetry_index] / max(
            capacity[telemetry_index] * wait_budget[telemetry_index], 1e-12
        )
        evidence_escalation_rate = (
            0.065
            * max(0.0, telemetry_queue_ratio)
            * max(1.0, external_rate[telemetry_index])
        )
        external[supervision_index] += float(rng.poisson(evidence_escalation_rate * dt_s))

        arrivals = external + routed_next
        offered_ratio = arrivals / np.maximum(capacity * dt_s, 1e-12)
        utilization_ewma = 0.88 * utilization_ewma + 0.12 * offered_ratio

        capacity_factor = rng.lognormal(-0.5 * 0.055**2, 0.055, size=count)
        shared_degradation = 1.0 / (1.0 + 0.035 * float(np.sum(queue / np.maximum(capacity, 1e-12))))
        service = rng.poisson(np.maximum(0.0, capacity * capacity_factor * shared_degradation * dt_s)).astype(float)
        available = queue + arrivals
        completed = np.minimum(available, service)
        queue = np.maximum(0.0, available - completed)

        queue_ratio = queue / np.maximum(capacity * wait_budget, 1e-12)
        dynamic_routing = _dynamic_routing(system.true_routing, queue_ratio)
        routed_next = np.zeros(count, dtype=float)
        for source in range(count):
            for target in range(count):
                probability = float(dynamic_routing[source, target])
                if probability <= 0.0 or completed[source] <= 0.0:
                    continue
                routed_next[target] += float(rng.binomial(int(round(completed[source])), probability))

        utilization_ratio = utilization_ewma / np.maximum(eta, 1e-12)
        combined = np.maximum(queue_ratio, utilization_ratio)
        violating = combined >= 1.0
        persistence[violating] += 1
        persistence[~violating] = 0
        persistent_violation = persistence >= 4
        if persistent_violation.any():
            outside_steps += 1
            if not crossed:
                crossed = True
                first_crossing = float(now)
        margin = float(1.0 - np.max(combined))
        if margin < minimum_margin:
            minimum_margin = margin
            binding_resource = resources[int(np.argmax(combined))].name
        maximum_wait_ratio = max(maximum_wait_ratio, float(np.max(queue_ratio)))
        maximum_utilization_ratio = max(maximum_utilization_ratio, float(np.max(utilization_ratio)))

        if (
            crossed
            and np.isnan(recovery_time)
            and now >= admission_end
            and np.all(combined < 0.80)
            and not routed_next.any()
        ):
            recovery_time = float(now - admission_end)

    return {
        "replication_seed": int(seed),
        "boundary_crossed": int(crossed),
        "minimum_assurance_margin": float(minimum_margin),
        "fraction_time_outside_boundary": float(outside_steps / len(time_s)),
        "first_boundary_crossing_time_s": float(first_crossing),
        "recovery_time_after_admission_s": float(recovery_time),
        "maximum_wait_ratio": float(maximum_wait_ratio),
        "maximum_utilization_ratio": float(maximum_utilization_ratio),
        "binding_resource": binding_resource,
    }
