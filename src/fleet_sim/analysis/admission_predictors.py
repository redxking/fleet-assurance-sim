"""Ex-ante Stage 3A admission predictors.

These predictors are calculated before stochastic resource execution. They do
not read realized queue, deadline, shedding, or operational-failure outcomes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil

import numpy as np
import pandas as pd

from fleet_sim.control_plane.resource_network import (
    AdmissionPattern,
    AdmissionTrajectory,
    AssuranceResourceSpec,
    ResourceType,
    admission_work_for_step,
)


@dataclass(frozen=True, slots=True)
class AdmissionPredictors:
    final_fleet_size: int
    projected_achieved_fleet_size: int
    peak_dndt: float
    mean_dndt: float
    peak_resource_utilization: float
    maximum_projected_queue_depth: float
    total_admitted_agents: int
    cumulative_backlog_area: float
    maximum_projected_deadline_miss_fraction: float
    omega_a: float
    binding_resource: str

    def to_dict(self) -> dict[str, float | int | str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AdmissionProjection:
    predictors: AdmissionPredictors
    resource_trace: pd.DataFrame
    admission_trace: pd.DataFrame


def project_admission_predictors(
    trajectory: AdmissionTrajectory,
    resources: tuple[AssuranceResourceSpec, ...],
) -> AdmissionProjection:
    """Project admission load using only scenario inputs and resource specifications."""
    if len(resources) != len(ResourceType) or {item.resource_type for item in resources} != set(
        ResourceType
    ):
        raise ValueError("resources must contain each assurance resource type exactly once")
    queue = {resource.resource_id: 0.0 for resource in resources}
    pending_agents = 0
    actual_fleet = trajectory.initial_n
    previous_ratio = 0.0
    base_closed_loop_cap = max(
        1,
        ceil(
            (trajectory.target_final_n - trajectory.initial_n)
            / max(1, ceil(trajectory.admission_duration_s / trajectory.dt_s))
        ),
    )
    maximum_queue = 0.0
    maximum_utilization = 0.0
    maximum_omega = 0.0
    cumulative_backlog_area = 0.0
    total_arrivals = {resource.resource_id: 0.0 for resource in resources}
    deadline_arrivals = {resource.resource_id: 0.0 for resource in resources}
    maximum_deadline_fraction = 0.0
    binding_resource = resources[0].resource_id
    admitted_series: list[int] = []
    resource_rows: list[dict[str, float | int | str]] = []
    admission_rows: list[dict[str, float | int | str]] = []

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
        admitted_series.append(admitted)
        step_max_ratio = 0.0

        for resource in resources:
            external = (
                resource.background_work_per_agent_s * actual_fleet * trajectory.dt_s
                + admission_work_for_step(
                    resource,
                    admitted_agents=admitted,
                    sybil_attempts=int(trajectory.sybil_attempts[index]),
                    restart_agents=int(trajectory.restart_agents[index]),
                    renewal_agents=int(trajectory.renewal_agents[index]),
                )
            )
            service_capacity = resource.capacity_units_per_second * trajectory.dt_s
            queue[resource.resource_id] = max(
                0.0,
                queue[resource.resource_id] + external - service_capacity,
            )
            wait_s = queue[resource.resource_id] / resource.capacity_units_per_second
            omega = wait_s / resource.max_wait_s
            utilization = external / max(service_capacity, 1e-12)
            total_arrivals[resource.resource_id] += external
            if wait_s > resource.max_wait_s:
                deadline_arrivals[resource.resource_id] += external
            deadline_fraction = deadline_arrivals[resource.resource_id] / max(
                total_arrivals[resource.resource_id], 1e-12
            )
            maximum_deadline_fraction = max(maximum_deadline_fraction, deadline_fraction)
            maximum_queue = max(maximum_queue, queue[resource.resource_id])
            maximum_utilization = max(maximum_utilization, utilization)
            cumulative_backlog_area += queue[resource.resource_id] * trajectory.dt_s
            if omega > maximum_omega:
                maximum_omega = omega
                binding_resource = resource.resource_id
            step_max_ratio = max(step_max_ratio, omega)
            resource_rows.append(
                {
                    "time_s": float(now),
                    "resource_id": resource.resource_id,
                    "resource_type": resource.resource_type.value,
                    "fleet_size": int(actual_fleet),
                    "planned_admissions": int(admitted),
                    "projected_arrival_work": float(external),
                    "capacity_work": float(service_capacity),
                    "projected_utilization": float(utilization),
                    "projected_queue_depth": float(queue[resource.resource_id]),
                    "projected_wait_s": float(wait_s),
                    "projected_omega": float(omega),
                    "projected_deadline_miss_fraction": float(deadline_fraction),
                }
            )
        previous_ratio = step_max_ratio
        admission_rows.append(
            {
                "time_s": float(now),
                "pattern": trajectory.pattern.value,
                "requested_admissions": int(trajectory.requested_admissions[index]),
                "planned_admissions": int(admitted),
                "pending_admissions": int(pending_agents),
                "projected_fleet_size": int(actual_fleet),
                "projected_maximum_omega": float(step_max_ratio),
            }
        )

    rates = np.asarray(admitted_series, dtype=float) / trajectory.dt_s
    active = trajectory.time_s < trajectory.admission_duration_s
    active_rates = rates[active] if active.any() else rates
    predictors = AdmissionPredictors(
        final_fleet_size=int(trajectory.target_final_n),
        projected_achieved_fleet_size=int(actual_fleet),
        peak_dndt=float(np.max(rates, initial=0.0)),
        mean_dndt=float(np.mean(active_rates)) if len(active_rates) else 0.0,
        peak_resource_utilization=float(maximum_utilization),
        maximum_projected_queue_depth=float(maximum_queue),
        total_admitted_agents=int(actual_fleet - trajectory.initial_n),
        cumulative_backlog_area=float(cumulative_backlog_area),
        maximum_projected_deadline_miss_fraction=float(maximum_deadline_fraction),
        omega_a=float(maximum_omega),
        binding_resource=binding_resource,
    )
    return AdmissionProjection(
        predictors=predictors,
        resource_trace=pd.DataFrame(resource_rows),
        admission_trace=pd.DataFrame(admission_rows),
    )
