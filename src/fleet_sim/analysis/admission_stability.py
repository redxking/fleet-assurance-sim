"""Multi-resource admission stability models for autonomous fleets.

The fluid backlog construction is an application of standard reflected workload
and network-calculus reasoning. The fleet-level assurance interpretation is a
candidate study construct and remains model-conditioned.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable, Mapping

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class AssuranceResource:
    name: str
    capacity_per_s: float
    background_per_agent_hz: float
    admission_work_ops: float
    max_wait_s: float

    def as_dict(self) -> dict[str, float | str]:
        return asdict(self)


@dataclass(frozen=True)
class AdmissionPredictors:
    final_n: float
    max_admission_rate: float
    peak_lambda: float
    omega: float
    final_max_utilization: float
    binding_lambda_resource: str
    binding_omega_resource: str

    def as_dict(self) -> dict[str, float | str]:
        return asdict(self)


def normalized_admission_curve(profile: str, x: np.ndarray) -> np.ndarray:
    """Return a monotone normalized population curve on x in [0, 1]."""
    z = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    if profile == "step":
        return (z > 0.0).astype(float)
    if profile == "linear":
        return z
    if profile in {"smooth", "staged"}:
        return 3.0 * z**2 - 2.0 * z**3
    if profile == "front_loaded":
        return 1.0 - (1.0 - z) ** 3
    if profile == "back_loaded":
        return z**3
    if profile == "pulse_train":
        # Five equal admission tranches with dwell intervals.
        return np.minimum(1.0, np.floor(z * 5.0 + 1e-12) / 5.0)
    raise ValueError(f"unsupported admission profile: {profile}")


def make_admission_trajectory(
    profile: str,
    *,
    n0: int,
    nf: int,
    ramp_duration_s: float,
    recovery_window_s: float = 120.0,
    dt: float = 0.5,
) -> pd.DataFrame:
    if nf < n0:
        raise ValueError("nf must be greater than or equal to n0")
    if ramp_duration_s <= 0.0 or dt <= 0.0:
        raise ValueError("ramp duration and dt must be positive")
    horizon = ramp_duration_s + recovery_window_s
    t = np.arange(0.0, horizon + 1e-12, dt)
    x = t / ramp_duration_s
    curve = normalized_admission_curve(profile, x)
    n = n0 + (nf - n0) * curve
    n[t >= ramp_duration_s] = float(nf)
    dn = np.diff(n, prepend=n[0]) / dt
    dn = np.maximum(0.0, dn)
    return pd.DataFrame(
        {
            "time_s": t,
            "n_agents": n,
            "admission_rate_agents_s": dn,
            "profile": profile,
        }
    )


def build_resource_regime(
    nf: int,
    regime: str,
    *,
    capacity_multiplier: float = 1.0,
) -> tuple[AssuranceResource, ...]:
    """Construct a notional four-resource assurance service regime.

    Capacities are sized from the declared final background utilization. This
    keeps final N below steady-state saturation while allowing admission
    transients to cross finite queue budgets.
    """
    if nf < 1 or capacity_multiplier <= 0.0:
        raise ValueError("invalid nf or capacity multiplier")
    names = ("control_plane", "credential_authority", "telemetry_control", "supervision")
    background = {
        "control_plane": 0.0080,
        "credential_authority": 1.0 / 300.0,
        "telemetry_control": 0.0045,
        "supervision": 0.00085,
    }
    admission_work = {
        "control_plane": 2.10,
        "credential_authority": 1.25,
        "telemetry_control": 1.70,
        "supervision": 0.28,
    }
    max_wait = {
        "control_plane": 2.0,
        "credential_authority": 4.0,
        "telemetry_control": 3.0,
        "supervision": 8.0,
    }
    utilization = {name: 0.44 for name in names}
    if regime == "balanced":
        pass
    elif regime == "control_constrained":
        utilization["control_plane"] = 0.64
    elif regime == "supervision_constrained":
        utilization["supervision"] = 0.64
    elif regime == "credential_constrained":
        utilization["credential_authority"] = 0.64
    else:
        raise ValueError(f"unsupported capacity regime: {regime}")

    resources: list[AssuranceResource] = []
    for name in names:
        capacity = (
            background[name] * float(nf) / utilization[name] * capacity_multiplier
        )
        resources.append(
            AssuranceResource(
                name=name,
                capacity_per_s=capacity,
                background_per_agent_hz=background[name],
                admission_work_ops=admission_work[name],
                max_wait_s=max_wait[name],
            )
        )
    return tuple(resources)


def critical_linear_admission_rate(resources: Iterable[AssuranceResource], nf: int) -> float:
    """Return the smallest final-state spare-capacity admission rate across resources."""
    rates: list[float] = []
    for resource in resources:
        spare = resource.capacity_per_s - resource.background_per_agent_hz * nf
        rates.append(spare / resource.admission_work_ops)
    return float(min(rates))


def fluid_admission_metrics(
    trajectory: pd.DataFrame,
    resources: Iterable[AssuranceResource],
) -> tuple[AdmissionPredictors, pd.DataFrame]:
    """Compute peak admission load and reflected fluid backlog for each resource."""
    required = {"time_s", "n_agents", "admission_rate_agents_s"}
    if not required.issubset(trajectory.columns):
        raise ValueError(f"trajectory must contain {sorted(required)}")
    t = trajectory.time_s.to_numpy(float)
    n = trajectory.n_agents.to_numpy(float)
    dn = trajectory.admission_rate_agents_s.to_numpy(float)
    if len(t) < 2:
        raise ValueError("trajectory must contain at least two samples")
    dt = float(np.median(np.diff(t)))
    rows: list[dict[str, float | str]] = []
    lambda_values: dict[str, float] = {}
    omega_values: dict[str, float] = {}
    final_utils: list[float] = []

    for resource in resources:
        arrival = resource.background_per_agent_hz * n + resource.admission_work_ops * dn
        spare = resource.capacity_per_s - resource.background_per_agent_hz * n
        with np.errstate(divide="ignore", invalid="ignore"):
            instant = np.where(
                spare > 0.0,
                resource.admission_work_ops * dn / spare,
                np.inf,
            )
        q = np.zeros_like(arrival)
        for idx in range(1, len(arrival)):
            q[idx] = max(0.0, q[idx - 1] + (arrival[idx] - resource.capacity_per_s) * dt)
        queue_budget = resource.capacity_per_s * resource.max_wait_s
        omega_series = q / max(queue_budget, 1e-12)
        lambda_values[resource.name] = float(np.max(instant))
        omega_values[resource.name] = float(np.max(omega_series))
        final_util = float(
            resource.background_per_agent_hz * n[-1] / resource.capacity_per_s
        )
        final_utils.append(final_util)
        for idx in range(len(t)):
            rows.append(
                {
                    "resource": resource.name,
                    "time_s": t[idx],
                    "arrival_rate": arrival[idx],
                    "capacity": resource.capacity_per_s,
                    "spare_capacity": spare[idx],
                    "instantaneous_lambda": instant[idx],
                    "fluid_queue": q[idx],
                    "normalized_fluid_backlog": omega_series[idx],
                    "fluid_wait_s": q[idx] / resource.capacity_per_s,
                }
            )

    binding_lambda = max(lambda_values, key=lambda_values.get)
    binding_omega = max(omega_values, key=omega_values.get)
    predictors = AdmissionPredictors(
        final_n=float(n[-1]),
        max_admission_rate=float(np.max(dn)),
        peak_lambda=float(lambda_values[binding_lambda]),
        omega=float(omega_values[binding_omega]),
        final_max_utilization=float(max(final_utils)),
        binding_lambda_resource=binding_lambda,
        binding_omega_resource=binding_omega,
    )
    return predictors, pd.DataFrame(rows)


def simulate_stochastic_admission(
    trajectory: pd.DataFrame,
    resources: Iterable[AssuranceResource],
    *,
    seed: int,
) -> tuple[dict[str, float | int | str], pd.DataFrame]:
    """Simulate Poisson arrivals and service for each assurance resource pool."""
    rng = np.random.default_rng(seed)
    t = trajectory.time_s.to_numpy(float)
    n = trajectory.n_agents.to_numpy(float)
    dn = trajectory.admission_rate_agents_s.to_numpy(float)
    dt = float(np.median(np.diff(t)))
    rows: list[dict[str, float | str | int]] = []
    crossed = False
    first_crossing = float("nan")
    maximum_wait = 0.0
    maximum_queue_ratio = 0.0
    binding_resource = "none"
    recovery_time = float("nan")
    resource_states: dict[str, float] = {resource.name: 0.0 for resource in resources}
    resource_list = tuple(resources)

    for idx, now in enumerate(t):
        all_recovered = True
        for resource in resource_list:
            arrival_rate = (
                resource.background_per_agent_hz * n[idx]
                + resource.admission_work_ops * dn[idx]
            )
            arrivals = float(rng.poisson(max(0.0, arrival_rate * dt)))
            offered = resource_states[resource.name] + arrivals
            service = float(rng.poisson(max(0.0, resource.capacity_per_s * dt)))
            completed = min(offered, service)
            queue = max(0.0, offered - completed)
            resource_states[resource.name] = queue
            wait = queue / resource.capacity_per_s
            ratio = wait / resource.max_wait_s
            if wait > maximum_wait:
                maximum_wait = wait
            if ratio > maximum_queue_ratio:
                maximum_queue_ratio = ratio
                binding_resource = resource.name
            if ratio >= 1.0 and not crossed:
                crossed = True
                first_crossing = float(now)
            if queue > 0.1 * resource.capacity_per_s * resource.max_wait_s:
                all_recovered = False
            rows.append(
                {
                    "seed": seed,
                    "time_s": now,
                    "resource": resource.name,
                    "n_agents": n[idx],
                    "admission_rate_agents_s": dn[idx],
                    "arrival_rate": arrival_rate,
                    "queue": queue,
                    "wait_s": wait,
                    "normalized_queue": ratio,
                    "boundary_crossed": int(ratio >= 1.0),
                }
            )
        if crossed and np.isnan(recovery_time) and all_recovered:
            recovery_time = float(now)

    summary: dict[str, float | int | str] = {
        "seed": int(seed),
        "boundary_crossed": int(crossed),
        "first_crossing_time_s": first_crossing,
        "recovery_time_s": recovery_time,
        "maximum_wait_s": float(maximum_wait),
        "maximum_normalized_queue": float(maximum_queue_ratio),
        "binding_resource": binding_resource,
        "final_n": float(n[-1]),
    }
    return summary, pd.DataFrame(rows)


def simulate_stochastic_admission_batch(
    trajectory: pd.DataFrame,
    resources: Iterable[AssuranceResource],
    *,
    replication_seeds: Iterable[int],
) -> pd.DataFrame:
    """Vectorized multi-replication stochastic admission simulation.

    Each replication has its own explicitly recorded NumPy seed. Random arrays
    are generated per replication, then queue evolution is vectorized across the
    replication dimension.
    """
    seeds = np.asarray(list(replication_seeds), dtype=np.int64)
    if len(seeds) == 0:
        raise ValueError("at least one replication seed is required")
    resource_list = tuple(resources)
    t = trajectory.time_s.to_numpy(float)
    n = trajectory.n_agents.to_numpy(float)
    dn = trajectory.admission_rate_agents_s.to_numpy(float)
    dt = float(np.median(np.diff(t)))
    steps = len(t)
    reps = len(seeds)
    r_count = len(resource_list)

    arrivals = np.empty((steps, reps, r_count), dtype=np.float64)
    services = np.empty((steps, reps, r_count), dtype=np.float64)
    arrival_rates = np.empty((steps, r_count), dtype=np.float64)
    capacities = np.empty(r_count, dtype=np.float64)
    wait_limits = np.empty(r_count, dtype=np.float64)
    for j, resource in enumerate(resource_list):
        arrival_rates[:, j] = (
            resource.background_per_agent_hz * n
            + resource.admission_work_ops * dn
        )
        capacities[j] = resource.capacity_per_s
        wait_limits[j] = resource.max_wait_s
    for rep, seed in enumerate(seeds):
        rng = np.random.default_rng(int(seed))
        arrivals[:, rep, :] = rng.poisson(np.maximum(0.0, arrival_rates * dt))
        services[:, rep, :] = rng.poisson(np.maximum(0.0, capacities[None, :] * dt), size=(steps, r_count))

    queue = np.zeros((reps, r_count), dtype=float)
    maximum_ratio = np.zeros(reps, dtype=float)
    maximum_wait = np.zeros(reps, dtype=float)
    first_crossing = np.full(reps, np.nan, dtype=float)
    crossed = np.zeros(reps, dtype=bool)
    recovery_time = np.full(reps, np.nan, dtype=float)
    binding_index = np.zeros(reps, dtype=np.int64)

    budgets = capacities * wait_limits
    for idx, now in enumerate(t):
        offered = queue + arrivals[idx]
        completed = np.minimum(offered, services[idx])
        queue = np.maximum(0.0, offered - completed)
        wait = queue / capacities[None, :]
        ratio = wait / wait_limits[None, :]
        local_idx = np.argmax(ratio, axis=1)
        local_max = ratio[np.arange(reps), local_idx]
        improved = local_max > maximum_ratio
        maximum_ratio[improved] = local_max[improved]
        binding_index[improved] = local_idx[improved]
        maximum_wait = np.maximum(maximum_wait, np.max(wait, axis=1))
        newly_crossed = (~crossed) & (local_max >= 1.0)
        first_crossing[newly_crossed] = float(now)
        crossed |= newly_crossed
        recovered_now = crossed & np.isnan(recovery_time) & np.all(queue <= 0.1 * budgets[None, :], axis=1)
        recovery_time[recovered_now] = float(now)

    return pd.DataFrame(
        {
            "seed": seeds,
            "boundary_crossed": crossed.astype(int),
            "first_crossing_time_s": first_crossing,
            "recovery_time_s": recovery_time,
            "maximum_wait_s": maximum_wait,
            "maximum_normalized_queue": maximum_ratio,
            "binding_resource": [resource_list[int(i)].name for i in binding_index],
            "final_n": float(n[-1]),
        }
    )
