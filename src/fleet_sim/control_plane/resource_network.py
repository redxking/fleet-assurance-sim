"""Aggregate assurance-resource network for Stage 3A admission research.

The implementation is intentionally count based. Its state dimension depends
on the number of assurance resources and time steps, not the fleet population.
All default parameters are notional and do not represent an operational system.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from math import ceil
from typing import Literal

import numpy as np
import pandas as pd


class ResourceType(StrEnum):
    IDENTITY_ISSUANCE = "identity_issuance"
    CERTIFICATE_ISSUANCE_RENEWAL = "certificate_issuance_renewal"
    AUTHORIZATION_POLICY_EVALUATION = "authorization_policy_evaluation"
    TASK_DISPATCH_REGISTRATION = "task_dispatch_registration"
    TELEMETRY_SOURCE_REGISTRATION = "telemetry_source_registration"
    EVIDENCE_INGEST_INITIALIZATION = "evidence_ingest_initialization"
    SUPERVISORY_REVIEW = "supervisory_review"
    REVOCATION_READINESS = "revocation_readiness"
    CONFIGURATION_ATTESTATION = "configuration_attestation"
    DEPENDENCY_REGISTRATION = "dependency_registration"


class AdmissionPattern(StrEnum):
    STEP = "step"
    LINEAR = "linear"
    STAGED = "staged"
    EXPONENTIAL = "exponential"
    BURSTY = "bursty"
    PERIODIC = "periodic"
    CLOSED_LOOP = "closed_loop"
    SYBIL = "sybil"
    MASS_RESTART = "mass_restart"
    MASS_RENEWAL = "mass_renewal"


class ServiceTimeDistribution(StrEnum):
    DETERMINISTIC = "deterministic"
    EXPONENTIAL = "exponential"
    GAMMA = "gamma"
    EMPIRICAL = "empirical"


class OverloadBehavior(StrEnum):
    QUEUE = "queue"
    SHED = "shed"
    DEFER = "defer"


@dataclass(frozen=True, slots=True)
class AssuranceResourceSpec:
    resource_id: str
    resource_type: ResourceType
    arrival_process: Literal["poisson", "scheduled", "empirical_replay"]
    admission_work_units: float
    background_work_per_agent_s: float
    capacity_units_per_second: float
    service_time_distribution: ServiceTimeDistribution
    service_time_mean_ms: float
    max_wait_s: float
    overload_behavior: OverloadBehavior
    shedding_threshold: float
    recovery_capacity_multiplier: float
    measurement_provenance: str
    parameter_class: Literal["measured", "inferred", "notional"] = "notional"

    def __post_init__(self) -> None:
        if not self.resource_id.strip():
            raise ValueError("resource_id cannot be empty")
        positive = (
            self.admission_work_units,
            self.capacity_units_per_second,
            self.service_time_mean_ms,
            self.max_wait_s,
            self.shedding_threshold,
            self.recovery_capacity_multiplier,
        )
        if not all(np.isfinite(value) and value > 0.0 for value in positive):
            raise ValueError(
                "resource work, capacity, timing, and recovery values must be finite and positive"
            )
        if (
            not np.isfinite(self.background_work_per_agent_s)
            or self.background_work_per_agent_s < 0.0
        ):
            raise ValueError("background_work_per_agent_s must be finite and nonnegative")
        if not self.measurement_provenance.strip():
            raise ValueError("measurement_provenance cannot be empty")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["resource_type"] = self.resource_type.value
        payload["service_time_distribution"] = self.service_time_distribution.value
        payload["overload_behavior"] = self.overload_behavior.value
        return payload


@dataclass(frozen=True, slots=True)
class AdmissionTrajectory:
    pattern: AdmissionPattern
    time_s: np.ndarray
    requested_admissions: np.ndarray
    fleet_size_if_unconstrained: np.ndarray
    sybil_attempts: np.ndarray
    restart_agents: np.ndarray
    renewal_agents: np.ndarray
    initial_n: int
    target_final_n: int
    admission_duration_s: float
    recovery_window_s: float
    dt_s: float

    def __post_init__(self) -> None:
        lengths = {
            len(self.time_s),
            len(self.requested_admissions),
            len(self.fleet_size_if_unconstrained),
            len(self.sybil_attempts),
            len(self.restart_agents),
            len(self.renewal_agents),
        }
        if len(lengths) != 1 or not lengths or next(iter(lengths)) < 2:
            raise ValueError("trajectory arrays must have equal length and at least two samples")
        for values in (
            self.time_s,
            self.requested_admissions,
            self.fleet_size_if_unconstrained,
            self.sybil_attempts,
            self.restart_agents,
            self.renewal_agents,
        ):
            if not np.isfinite(values).all() or (values < 0.0).any():
                raise ValueError("trajectory arrays must be finite and nonnegative")


@dataclass(frozen=True, slots=True)
class OperationalFailureCriteria:
    maximum_deadline_miss_fraction: float = 0.05
    maximum_shed_fraction: float = 0.01
    maximum_incomplete_exposure_per_agent_s: float = 5.0
    minimum_useful_throughput_ratio: float = 0.90
    require_recovery: bool = True

    def __post_init__(self) -> None:
        fractions = (
            self.maximum_deadline_miss_fraction,
            self.maximum_shed_fraction,
            self.minimum_useful_throughput_ratio,
        )
        if not all(np.isfinite(value) and 0.0 <= value <= 1.0 for value in fractions):
            raise ValueError("failure fractions must be finite and within [0, 1]")
        if (
            not np.isfinite(self.maximum_incomplete_exposure_per_agent_s)
            or self.maximum_incomplete_exposure_per_agent_s < 0.0
        ):
            raise ValueError("maximum incomplete exposure must be finite and nonnegative")


@dataclass(frozen=True, slots=True)
class AdmissionRunResult:
    summary: dict[str, object]
    resource_trace: pd.DataFrame
    admission_trace: pd.DataFrame


def required_resource_types() -> tuple[ResourceType, ...]:
    return tuple(ResourceType)


def default_assurance_resources(
    final_n: int,
    *,
    capacity_multiplier: float = 1.0,
) -> tuple[AssuranceResourceSpec, ...]:
    """Return ten explicit notional resource specifications.

    Capacities are sized from final background work at 55 percent utilization
    plus three times the mean admission work for a 180 second nominal horizon.
    This is an engineering fixture, not measured capacity.
    """
    if final_n < 1 or not np.isfinite(capacity_multiplier) or capacity_multiplier <= 0.0:
        raise ValueError("final_n and capacity_multiplier must be positive")
    background = {
        ResourceType.IDENTITY_ISSUANCE: 0.00020,
        ResourceType.CERTIFICATE_ISSUANCE_RENEWAL: 1.0 / 300.0,
        ResourceType.AUTHORIZATION_POLICY_EVALUATION: 0.00600,
        ResourceType.TASK_DISPATCH_REGISTRATION: 0.00300,
        ResourceType.TELEMETRY_SOURCE_REGISTRATION: 0.00400,
        ResourceType.EVIDENCE_INGEST_INITIALIZATION: 0.00300,
        ResourceType.SUPERVISORY_REVIEW: 0.00080,
        ResourceType.REVOCATION_READINESS: 0.00050,
        ResourceType.CONFIGURATION_ATTESTATION: 0.00150,
        ResourceType.DEPENDENCY_REGISTRATION: 0.00100,
    }
    work = {
        ResourceType.IDENTITY_ISSUANCE: 1.00,
        ResourceType.CERTIFICATE_ISSUANCE_RENEWAL: 1.00,
        ResourceType.AUTHORIZATION_POLICY_EVALUATION: 2.00,
        ResourceType.TASK_DISPATCH_REGISTRATION: 1.00,
        ResourceType.TELEMETRY_SOURCE_REGISTRATION: 1.50,
        ResourceType.EVIDENCE_INGEST_INITIALIZATION: 1.40,
        ResourceType.SUPERVISORY_REVIEW: 0.25,
        ResourceType.REVOCATION_READINESS: 0.30,
        ResourceType.CONFIGURATION_ATTESTATION: 1.20,
        ResourceType.DEPENDENCY_REGISTRATION: 1.00,
    }
    wait = {
        ResourceType.IDENTITY_ISSUANCE: 2.0,
        ResourceType.CERTIFICATE_ISSUANCE_RENEWAL: 4.0,
        ResourceType.AUTHORIZATION_POLICY_EVALUATION: 1.5,
        ResourceType.TASK_DISPATCH_REGISTRATION: 2.0,
        ResourceType.TELEMETRY_SOURCE_REGISTRATION: 3.0,
        ResourceType.EVIDENCE_INGEST_INITIALIZATION: 3.5,
        ResourceType.SUPERVISORY_REVIEW: 8.0,
        ResourceType.REVOCATION_READINESS: 5.0,
        ResourceType.CONFIGURATION_ATTESTATION: 4.5,
        ResourceType.DEPENDENCY_REGISTRATION: 6.0,
    }
    behavior = {
        ResourceType.IDENTITY_ISSUANCE: OverloadBehavior.QUEUE,
        ResourceType.CERTIFICATE_ISSUANCE_RENEWAL: OverloadBehavior.QUEUE,
        ResourceType.AUTHORIZATION_POLICY_EVALUATION: OverloadBehavior.QUEUE,
        ResourceType.TASK_DISPATCH_REGISTRATION: OverloadBehavior.DEFER,
        ResourceType.TELEMETRY_SOURCE_REGISTRATION: OverloadBehavior.DEFER,
        ResourceType.EVIDENCE_INGEST_INITIALIZATION: OverloadBehavior.SHED,
        ResourceType.SUPERVISORY_REVIEW: OverloadBehavior.QUEUE,
        ResourceType.REVOCATION_READINESS: OverloadBehavior.QUEUE,
        ResourceType.CONFIGURATION_ATTESTATION: OverloadBehavior.DEFER,
        ResourceType.DEPENDENCY_REGISTRATION: OverloadBehavior.DEFER,
    }
    output: list[AssuranceResourceSpec] = []
    for resource_type in ResourceType:
        capacity = capacity_multiplier * max(
            0.5,
            background[resource_type] * final_n / 0.55
            + 3.0 * work[resource_type] * final_n / 180.0,
        )
        output.append(
            AssuranceResourceSpec(
                resource_id=resource_type.value,
                resource_type=resource_type,
                arrival_process="poisson",
                admission_work_units=work[resource_type],
                background_work_per_agent_s=background[resource_type],
                capacity_units_per_second=float(capacity),
                service_time_distribution=ServiceTimeDistribution.EXPONENTIAL,
                service_time_mean_ms=float(1000.0 / capacity),
                max_wait_s=wait[resource_type],
                overload_behavior=behavior[resource_type],
                shedding_threshold=1.25,
                recovery_capacity_multiplier=1.15,
                measurement_provenance="notional Stage 3A engineering fixture",
                parameter_class="notional",
            )
        )
    return tuple(output)


def _integer_allocation(total: int, weights: np.ndarray) -> np.ndarray:
    if total < 0 or len(weights) == 0:
        raise ValueError("invalid integer allocation")
    normalized = np.asarray(weights, dtype=float)
    if not np.isfinite(normalized).all() or (normalized < 0.0).any() or normalized.sum() <= 0.0:
        raise ValueError("allocation weights must be finite, nonnegative, and nonzero")
    raw = total * normalized / normalized.sum()
    cumulative = np.cumsum(raw)
    cumulative_integer = np.floor(cumulative + 0.5).astype(np.int64)
    cumulative_integer[-1] = total
    return np.diff(np.concatenate(([0], cumulative_integer))).astype(np.int64)


def make_admission_trajectory(
    pattern: AdmissionPattern | str,
    *,
    initial_n: int,
    final_n: int,
    admission_duration_s: float,
    recovery_window_s: float = 120.0,
    dt_s: float = 1.0,
    disturbance_fraction: float = 0.25,
) -> AdmissionTrajectory:
    """Create a deterministic requested-admission and disturbance schedule."""
    selected = AdmissionPattern(pattern)
    if initial_n < 0 or final_n < initial_n:
        raise ValueError("final_n must be at least initial_n and both must be nonnegative")
    if admission_duration_s <= 0.0 or recovery_window_s < 0.0 or dt_s <= 0.0:
        raise ValueError("trajectory timing must be positive and recovery nonnegative")
    if not np.isfinite(disturbance_fraction) or disturbance_fraction < 0.0:
        raise ValueError("disturbance_fraction must be finite and nonnegative")

    horizon = admission_duration_s + recovery_window_s
    time_s: np.ndarray = np.arange(0.0, horizon + 0.5 * dt_s, dt_s, dtype=float)
    ramp_steps = max(1, min(len(time_s), ceil(admission_duration_s / dt_s)))
    weights: np.ndarray = np.zeros(ramp_steps, dtype=float)
    if selected == AdmissionPattern.STEP:
        weights[0] = 1.0
    elif selected in {
        AdmissionPattern.LINEAR,
        AdmissionPattern.CLOSED_LOOP,
        AdmissionPattern.SYBIL,
        AdmissionPattern.MASS_RESTART,
        AdmissionPattern.MASS_RENEWAL,
    }:
        weights[:] = 1.0
    elif selected == AdmissionPattern.STAGED:
        weights[np.unique(np.linspace(0, ramp_steps - 1, num=min(4, ramp_steps), dtype=int))] = 1.0
    elif selected == AdmissionPattern.EXPONENTIAL:
        weights[:] = np.exp(np.linspace(0.0, 4.0, ramp_steps))
    elif selected == AdmissionPattern.BURSTY:
        weights[max(0, int(0.10 * (ramp_steps - 1)))] = 0.70
        weights[max(0, int(0.65 * (ramp_steps - 1)))] += 0.30
    elif selected == AdmissionPattern.PERIODIC:
        interval = max(1, ramp_steps // 6)
        weights[::interval] = 1.0
    else:  # pragma: no cover, StrEnum rejects unsupported values.
        raise ValueError(f"unsupported admission pattern: {selected}")

    delta = final_n - initial_n
    requested: np.ndarray = np.zeros(len(time_s), dtype=np.int64)
    requested[:ramp_steps] = _integer_allocation(delta, weights)
    fleet = initial_n + np.cumsum(requested)
    sybil: np.ndarray = np.zeros(len(time_s), dtype=np.int64)
    restart: np.ndarray = np.zeros(len(time_s), dtype=np.int64)
    renewal: np.ndarray = np.zeros(len(time_s), dtype=np.int64)
    disturbance_count = round(max(1, final_n) * disturbance_fraction)
    disturbance_index = min(len(time_s) - 1, max(0, round(0.65 * (ramp_steps - 1))))
    if selected == AdmissionPattern.SYBIL:
        sybil[disturbance_index] = disturbance_count
    elif selected == AdmissionPattern.MASS_RESTART:
        restart[disturbance_index] = min(final_n, disturbance_count)
    elif selected == AdmissionPattern.MASS_RENEWAL:
        renewal[disturbance_index] = min(final_n, disturbance_count)

    return AdmissionTrajectory(
        pattern=selected,
        time_s=time_s,
        requested_admissions=requested,
        fleet_size_if_unconstrained=fleet,
        sybil_attempts=sybil,
        restart_agents=restart,
        renewal_agents=renewal,
        initial_n=initial_n,
        target_final_n=final_n,
        admission_duration_s=float(admission_duration_s),
        recovery_window_s=float(recovery_window_s),
        dt_s=float(dt_s),
    )


_SYBIL_MULTIPLIER = {
    ResourceType.IDENTITY_ISSUANCE: 1.00,
    ResourceType.CERTIFICATE_ISSUANCE_RENEWAL: 0.20,
    ResourceType.AUTHORIZATION_POLICY_EVALUATION: 0.60,
    ResourceType.TASK_DISPATCH_REGISTRATION: 0.10,
    ResourceType.TELEMETRY_SOURCE_REGISTRATION: 0.10,
    ResourceType.EVIDENCE_INGEST_INITIALIZATION: 0.10,
    ResourceType.SUPERVISORY_REVIEW: 0.20,
    ResourceType.REVOCATION_READINESS: 0.40,
    ResourceType.CONFIGURATION_ATTESTATION: 0.15,
    ResourceType.DEPENDENCY_REGISTRATION: 0.10,
}
_RESTART_MULTIPLIER = {
    resource_type: (
        1.0
        if resource_type
        in {
            ResourceType.AUTHORIZATION_POLICY_EVALUATION,
            ResourceType.TASK_DISPATCH_REGISTRATION,
            ResourceType.TELEMETRY_SOURCE_REGISTRATION,
            ResourceType.EVIDENCE_INGEST_INITIALIZATION,
            ResourceType.CONFIGURATION_ATTESTATION,
            ResourceType.DEPENDENCY_REGISTRATION,
        }
        else 0.05
    )
    for resource_type in ResourceType
}
_RENEWAL_MULTIPLIER = {
    resource_type: (
        1.0
        if resource_type
        in {
            ResourceType.CERTIFICATE_ISSUANCE_RENEWAL,
            ResourceType.AUTHORIZATION_POLICY_EVALUATION,
            ResourceType.REVOCATION_READINESS,
        }
        else 0.02
    )
    for resource_type in ResourceType
}


def admission_work_for_step(
    resource: AssuranceResourceSpec,
    *,
    admitted_agents: int,
    sybil_attempts: int,
    restart_agents: int,
    renewal_agents: int,
) -> float:
    equivalent_agents = (
        float(admitted_agents)
        + _SYBIL_MULTIPLIER[resource.resource_type] * sybil_attempts
        + _RESTART_MULTIPLIER[resource.resource_type] * restart_agents
        + _RENEWAL_MULTIPLIER[resource.resource_type] * renewal_agents
    )
    return resource.admission_work_units * equivalent_agents


def _service_count(
    resource: AssuranceResourceSpec,
    expected: float,
    rng: np.random.Generator,
) -> float:
    if expected <= 0.0:
        return 0.0
    if resource.service_time_distribution == ServiceTimeDistribution.DETERMINISTIC:
        return float(expected)
    if resource.service_time_distribution == ServiceTimeDistribution.GAMMA:
        shape = max(1.0, expected)
        return float(rng.gamma(shape=shape, scale=expected / shape))
    return float(rng.poisson(expected))


def simulate_resource_network(
    trajectory: AdmissionTrajectory,
    resources: tuple[AssuranceResourceSpec, ...],
    *,
    seed: int,
    failure_criteria: OperationalFailureCriteria | None = None,
) -> AdmissionRunResult:
    """Execute one deterministic-seed aggregate stochastic resource run."""
    if len(resources) != len(ResourceType) or {item.resource_type for item in resources} != set(
        ResourceType
    ):
        raise ValueError(
            "resources must contain each of the ten assurance resource types exactly once"
        )
    criteria = failure_criteria or OperationalFailureCriteria()
    rng = np.random.default_rng(seed)
    queue = {resource.resource_id: 0.0 for resource in resources}
    deferred = {resource.resource_id: 0.0 for resource in resources}
    previous_ratio = 0.0
    pending_agents = 0
    actual_fleet = trajectory.initial_n
    base_closed_loop_cap = max(
        1,
        ceil(
            (trajectory.target_final_n - trajectory.initial_n)
            / max(1, ceil(trajectory.admission_duration_s / trajectory.dt_s))
        ),
    )
    resource_rows: list[dict[str, object]] = []
    admission_rows: list[dict[str, object]] = []
    total_arrival_work = 0.0
    total_deadline_missed_work = 0.0
    total_dropped_work = 0.0
    total_deferred_created = 0.0
    incomplete_exposure_agent_s = 0.0
    useful_tasks = 0.0
    nominal_tasks = 0.0
    observed_omega = 0.0
    maximum_queue_depth = 0.0
    maximum_wait_by_type = {resource_type: 0.0 for resource_type in ResourceType}
    maximum_utilization_by_type = {resource_type: 0.0 for resource_type in ResourceType}
    recovery_time_s: float | None = None
    low_queue_streak = 0

    for index, now in enumerate(trajectory.time_s):
        pending_agents += int(trajectory.requested_admissions[index])
        if trajectory.pattern == AdmissionPattern.CLOSED_LOOP:
            if previous_ratio < 0.65:
                gate = 1.0
            elif previous_ratio < 0.90:
                gate = 0.5
            else:
                gate = 0.0
            admitted = min(pending_agents, ceil(base_closed_loop_cap * gate))
        else:
            admitted = pending_agents
        pending_agents -= admitted
        actual_fleet += admitted

        step_max_ratio = 0.0
        step_incomplete = 0.0
        for resource in resources:
            expected_external = (
                resource.background_work_per_agent_s * actual_fleet * trajectory.dt_s
                + admission_work_for_step(
                    resource,
                    admitted_agents=admitted,
                    sybil_attempts=int(trajectory.sybil_attempts[index]),
                    restart_agents=int(trajectory.restart_agents[index]),
                    renewal_agents=int(trajectory.renewal_agents[index]),
                )
            )
            external = (
                float(rng.poisson(expected_external))
                if resource.arrival_process == "poisson"
                else float(expected_external)
            )
            retry = min(
                deferred[resource.resource_id],
                0.25 * resource.capacity_units_per_second * trajectory.dt_s,
            )
            deferred[resource.resource_id] -= retry
            arrivals = external + retry
            offered = queue[resource.resource_id] + arrivals
            queue_budget = resource.capacity_units_per_second * resource.max_wait_s
            dropped = 0.0
            deferred_created = 0.0
            threshold = resource.shedding_threshold * queue_budget
            if resource.overload_behavior == OverloadBehavior.SHED and offered > threshold:
                dropped = offered - threshold
                offered = threshold
            elif resource.overload_behavior == OverloadBehavior.DEFER and offered > threshold:
                deferred_created = offered - threshold
                deferred[resource.resource_id] += deferred_created
                offered = threshold

            capacity_factor = (
                resource.recovery_capacity_multiplier if previous_ratio >= 1.0 else 1.0
            )
            service = min(
                offered,
                _service_count(
                    resource,
                    resource.capacity_units_per_second * capacity_factor * trajectory.dt_s,
                    rng,
                ),
            )
            queue[resource.resource_id] = max(0.0, offered - service)
            wait_s = queue[resource.resource_id] / resource.capacity_units_per_second
            ratio = wait_s / resource.max_wait_s
            arrival_utilization = arrivals / max(
                resource.capacity_units_per_second * trajectory.dt_s,
                1e-12,
            )
            step_max_ratio = max(step_max_ratio, ratio)
            observed_omega = max(observed_omega, ratio)
            maximum_queue_depth = max(maximum_queue_depth, queue[resource.resource_id])
            maximum_wait_by_type[resource.resource_type] = max(
                maximum_wait_by_type[resource.resource_type],
                wait_s,
            )
            maximum_utilization_by_type[resource.resource_type] = max(
                maximum_utilization_by_type[resource.resource_type],
                arrival_utilization,
            )
            deadline_missed = arrivals if wait_s > resource.max_wait_s else 0.0
            total_arrival_work += arrivals
            total_deadline_missed_work += deadline_missed
            total_dropped_work += dropped
            total_deferred_created += deferred_created
            step_incomplete = max(
                step_incomplete,
                queue[resource.resource_id] / max(resource.admission_work_units, 1e-12),
            )
            resource_rows.append(
                {
                    "seed": int(seed),
                    "time_s": float(now),
                    "resource_id": resource.resource_id,
                    "resource_type": resource.resource_type.value,
                    "fleet_size": int(actual_fleet),
                    "admitted_agents": int(admitted),
                    "arrival_work": float(arrivals),
                    "arrival_utilization": float(arrival_utilization),
                    "service_work": float(service),
                    "queue_depth": float(queue[resource.resource_id]),
                    "wait_s": float(wait_s),
                    "omega_observed": float(ratio),
                    "capacity_units_per_second": resource.capacity_units_per_second,
                    "deadline_missed_work": float(deadline_missed),
                    "dropped_work": float(dropped),
                    "deferred_work_created": float(deferred_created),
                    "deferred_work_outstanding": float(deferred[resource.resource_id]),
                    "parameter_class": resource.parameter_class,
                    "measurement_provenance": resource.measurement_provenance,
                }
            )

        previous_ratio = step_max_ratio
        incomplete_agents = min(float(actual_fleet), max(0.0, step_incomplete))
        incomplete_exposure_agent_s += incomplete_agents * trajectory.dt_s
        nominal_step_tasks = actual_fleet * 0.02 * trajectory.dt_s
        nominal_tasks += nominal_step_tasks
        useful_tasks += max(0.0, actual_fleet - incomplete_agents) * 0.02 * trajectory.dt_s
        if now >= trajectory.admission_duration_s:
            outstanding_work = sum(queue.values()) + sum(deferred.values())
            if outstanding_work <= 1e-9:
                low_queue_streak += 1
            else:
                low_queue_streak = 0
            if recovery_time_s is None and low_queue_streak >= 3:
                recovery_time_s = max(0.0, float(now - trajectory.admission_duration_s))
        admission_rows.append(
            {
                "seed": int(seed),
                "time_s": float(now),
                "pattern": trajectory.pattern.value,
                "requested_admissions": int(trajectory.requested_admissions[index]),
                "admitted_agents": int(admitted),
                "pending_admissions": int(pending_agents),
                "fleet_size": int(actual_fleet),
                "sybil_attempts": int(trajectory.sybil_attempts[index]),
                "restart_agents": int(trajectory.restart_agents[index]),
                "renewal_agents": int(trajectory.renewal_agents[index]),
                "maximum_observed_omega": float(step_max_ratio),
                "incomplete_agents_estimate": float(incomplete_agents),
            }
        )

    deadline_fraction = total_deadline_missed_work / max(total_arrival_work, 1e-12)
    shed_fraction = total_dropped_work / max(total_arrival_work, 1e-12)
    exposure_per_agent_s = incomplete_exposure_agent_s / max(1, trajectory.target_final_n)
    throughput_ratio = useful_tasks / max(nominal_tasks, 1e-12)
    recovered = recovery_time_s is not None
    operational_failure = bool(
        deadline_fraction > criteria.maximum_deadline_miss_fraction
        or shed_fraction > criteria.maximum_shed_fraction
        or exposure_per_agent_s > criteria.maximum_incomplete_exposure_per_agent_s
        or throughput_ratio < criteria.minimum_useful_throughput_ratio
        or actual_fleet != trajectory.target_final_n
        or (criteria.require_recovery and not recovered)
    )
    evidence_scope = (
        "interface_verification_only"
        if any(resource.parameter_class == "notional" for resource in resources)
        else "calibrated_model_evidence"
    )
    summary: dict[str, object] = {
        "seed": int(seed),
        "pattern": trajectory.pattern.value,
        "initial_n": int(trajectory.initial_n),
        "target_final_n": int(trajectory.target_final_n),
        "achieved_final_n": int(actual_fleet),
        "observed_total_admitted_agents": int(actual_fleet - trajectory.initial_n),
        "pending_admissions": int(pending_agents),
        "observed_omega_a": float(observed_omega),
        "assurance_boundary_crossed": int(observed_omega >= 1.0),
        "maximum_queue_depth": float(maximum_queue_depth),
        "queue_unrecovered_at_horizon": int(not recovered),
        "authorization_latency_s": float(
            maximum_wait_by_type[ResourceType.AUTHORIZATION_POLICY_EVALUATION]
        ),
        "telemetry_registration_delay_s": float(
            maximum_wait_by_type[ResourceType.TELEMETRY_SOURCE_REGISTRATION]
        ),
        "credential_issuance_delay_s": float(
            max(
                maximum_wait_by_type[ResourceType.IDENTITY_ISSUANCE],
                maximum_wait_by_type[ResourceType.CERTIFICATE_ISSUANCE_RENEWAL],
            )
        ),
        "supervisory_saturation": float(
            maximum_utilization_by_type[ResourceType.SUPERVISORY_REVIEW]
        ),
        "revocation_readiness_delay_s": float(
            maximum_wait_by_type[ResourceType.REVOCATION_READINESS]
        ),
        "deadline_miss_fraction": float(deadline_fraction),
        "shed_fraction": float(shed_fraction),
        "deferred_work_created": float(total_deferred_created),
        "deferred_work_outstanding": float(sum(deferred.values())),
        "incomplete_assurance_exposure_agent_s": float(incomplete_exposure_agent_s),
        "incomplete_exposure_per_agent_s": float(exposure_per_agent_s),
        "useful_task_throughput_ratio": float(throughput_ratio),
        "recovery_time_s": recovery_time_s,
        "operational_failure": int(operational_failure),
        "operational_failure_definition_uses_omega": False,
        "evidence_scope": evidence_scope,
    }
    return AdmissionRunResult(summary, pd.DataFrame(resource_rows), pd.DataFrame(admission_rows))
