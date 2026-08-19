from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import Mapping


@dataclass(frozen=True)
class ConstraintMargin:
    """Normalized margin for one assurance constraint.

    margin > 0: admissible with headroom
    margin = 0: on the declared boundary
    margin < 0: inadmissible

    Normalization is intentionally dimensionless so heterogeneous constraints can be
    compared without pretending their physical units are interchangeable.
    """

    name: str
    observed: float
    limit: float
    margin: float
    direction: str
    evidence_class: str = "model-derived"


@dataclass(frozen=True)
class FleetAssuranceEnvelope:
    admissible: bool
    binding_constraint: str | None
    minimum_margin: float
    constraints: tuple[ConstraintMargin, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "admissible": self.admissible,
            "binding_constraint": self.binding_constraint,
            "minimum_margin": self.minimum_margin,
            "constraints": [c.__dict__ for c in self.constraints],
        }


def upper_bound_margin(
    name: str,
    observed: float,
    limit: float,
    *,
    evidence_class: str = "model-derived",
) -> ConstraintMargin:
    """Return normalized headroom where lower observed values are better."""
    if limit <= 0:
        raise ValueError("upper-bound limit must be positive")
    return ConstraintMargin(
        name=name,
        observed=float(observed),
        limit=float(limit),
        margin=(float(limit) - float(observed)) / float(limit),
        direction="upper",
        evidence_class=evidence_class,
    )


def lower_bound_margin(
    name: str,
    observed: float,
    limit: float,
    *,
    evidence_class: str = "model-derived",
) -> ConstraintMargin:
    """Return normalized headroom where higher observed values are better."""
    if limit <= 0:
        raise ValueError("lower-bound limit must be positive")
    return ConstraintMargin(
        name=name,
        observed=float(observed),
        limit=float(limit),
        margin=(float(observed) - float(limit)) / float(limit),
        direction="lower",
        evidence_class=evidence_class,
    )


def evaluate_envelope(constraints: list[ConstraintMargin] | tuple[ConstraintMargin, ...]) -> FleetAssuranceEnvelope:
    if not constraints:
        return FleetAssuranceEnvelope(True, None, inf, ())
    ordered = tuple(constraints)
    binding = min(ordered, key=lambda c: c.margin)
    return FleetAssuranceEnvelope(
        admissible=all(c.margin >= 0.0 for c in ordered),
        binding_constraint=binding.name,
        minimum_margin=binding.margin,
        constraints=ordered,
    )


def containment_race_ratio(time_to_contain_s: float, time_to_spread_s: float) -> float:
    """Dimensionless containment race ratio chi = T_contain / T_spread.

    chi < 1 means containment completes faster than the modeled spread timescale.
    The ratio is a study construct, not a universal security theorem.
    """
    if time_to_contain_s < 0:
        raise ValueError("time_to_contain_s must be non-negative")
    if time_to_spread_s <= 0:
        raise ValueError("time_to_spread_s must be positive")
    return float(time_to_contain_s) / float(time_to_spread_s)


def safe_population_growth_rate(
    *,
    supervisory_service_capacity_per_s: float,
    baseline_alert_rate_per_agent_hz: float,
    hazard_alert_rate_per_new_agent_hz: float,
    settling_time_s: float,
    current_agents: int,
    utilization_target: float = 0.70,
) -> float:
    """A falsifiable Stage-1 population-velocity bound.

    The model reserves a fraction of supervisory capacity for the current population
    and converts remaining capacity into a rate at which new agents can be absorbed
    without exceeding the target utilization during one settling interval.

    This is deliberately a candidate model to be tested, not asserted as a law.
    """
    if supervisory_service_capacity_per_s <= 0:
        raise ValueError("supervisory capacity must be positive")
    if baseline_alert_rate_per_agent_hz < 0 or hazard_alert_rate_per_new_agent_hz <= 0:
        raise ValueError("alert rates are invalid")
    if settling_time_s <= 0:
        raise ValueError("settling_time_s must be positive")
    if current_agents < 0:
        raise ValueError("current_agents must be non-negative")
    if not 0 < utilization_target < 1:
        raise ValueError("utilization_target must be in (0,1)")

    usable = utilization_target * supervisory_service_capacity_per_s
    baseline = current_agents * baseline_alert_rate_per_agent_hz
    spare = max(0.0, usable - baseline)

    # Each new agent creates hazard-review demand over the controller settling window.
    per_new_agent_work = hazard_alert_rate_per_new_agent_hz * settling_time_s
    if per_new_agent_work <= 0:
        return inf
    agents_per_settling_interval = spare * settling_time_s / per_new_agent_work
    return agents_per_settling_interval / settling_time_s


def build_candidate_envelope(
    *,
    control_plane_utilization: float,
    max_control_plane_utilization: float,
    epidemic_gain: float,
    max_epidemic_gain: float,
    observability_demand_bps: float,
    observability_capacity_bps: float,
    supervisory_utilization: float,
    max_supervisory_utilization: float,
    revocation_latency_s: float,
    max_revocation_latency_s: float,
    timing_uncertainty_s: float,
    max_timing_uncertainty_s: float,
    useful_throughput_per_s: float,
    min_useful_throughput_per_s: float,
    evidence_classes: Mapping[str, str] | None = None,
) -> FleetAssuranceEnvelope:
    """Construct the candidate coupled assurance operating region.

    The coupling is currently conjunctive: all declared constraints must be satisfied.
    Stage 1/2 experiments are expected to test whether interaction terms are required.
    """
    ec = evidence_classes or {}
    c = [
        upper_bound_margin("control_plane", control_plane_utilization, max_control_plane_utilization, evidence_class=ec.get("control_plane", "model-derived")),
        upper_bound_margin("containment", epidemic_gain, max_epidemic_gain, evidence_class=ec.get("containment", "model-derived")),
        upper_bound_margin("observability", observability_demand_bps, observability_capacity_bps, evidence_class=ec.get("observability", "model-derived")),
        upper_bound_margin("supervision", supervisory_utilization, max_supervisory_utilization, evidence_class=ec.get("supervision", "model-derived")),
        upper_bound_margin("revocation", revocation_latency_s, max_revocation_latency_s, evidence_class=ec.get("revocation", "model-derived")),
        upper_bound_margin("timing", timing_uncertainty_s, max_timing_uncertainty_s, evidence_class=ec.get("timing", "model-derived")),
        lower_bound_margin("mission_throughput", useful_throughput_per_s, min_useful_throughput_per_s, evidence_class=ec.get("mission_throughput", "model-derived")),
    ]
    return evaluate_envelope(c)
