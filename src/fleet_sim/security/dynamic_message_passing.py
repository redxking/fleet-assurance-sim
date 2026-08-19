"""Sparse directed dynamic message passing for Stage 3B predictors.

This module consumes only ``ObservedSystemView``.  It preserves node response
compartments and edge no-transmission messages instead of reducing the system
to a spectral scalar.  The approximation assumes conditional independence of
incoming edge messages and must be calibrated before operational use.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import ceil
from types import MappingProxyType

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import ArpackError, ArpackNoConvergence, eigs
from scipy.special import ndtr

from fleet_sim.security.attack_trace import LAYER_NAMES, ObservedSystemView


@dataclass(frozen=True)
class DMPConfig:
    """Predictor assumptions, intentionally independent of attack generation."""

    horizon_steps: int | None = None
    base_transmission_intensity: float = 0.16
    common_cause_scale: float = 1.0
    outbreak_fraction: float = 0.10
    layer_weights: Mapping[str, float] = field(
        default_factory=lambda: {
            "authorization": 0.34,
            "communication": 0.18,
            "dependency": 0.20,
            "credential": 0.20,
            "supervision": 0.08,
        }
    )
    capture_steps: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.horizon_steps is not None and self.horizon_steps < 1:
            raise ValueError("horizon_steps must be positive")
        if self.base_transmission_intensity < 0.0:
            raise ValueError("base_transmission_intensity must be nonnegative")
        if self.common_cause_scale < 0.0:
            raise ValueError("common_cause_scale must be nonnegative")
        if not 0.0 < self.outbreak_fraction <= 1.0:
            raise ValueError("outbreak_fraction must be in (0, 1]")
        if set(self.layer_weights) != set(LAYER_NAMES):
            raise ValueError(f"layer_weights must be exactly {list(LAYER_NAMES)}")
        if any(not np.isfinite(value) or value < 0.0 for value in self.layer_weights.values()):
            raise ValueError("layer weights must be finite and nonnegative")
        if any(step < 0 for step in self.capture_steps):
            raise ValueError("capture_steps must be nonnegative")
        object.__setattr__(self, "layer_weights", MappingProxyType(dict(self.layer_weights)))


@dataclass(frozen=True)
class DirectedTransmissionOperator:
    """Sparse edge representation retaining direction and layer composition."""

    n: int
    sources: np.ndarray
    targets: np.ndarray
    base_probability: np.ndarray
    credential_fraction: np.ndarray
    cross_segment: np.ndarray
    matrix: sparse.csr_matrix


@dataclass(frozen=True)
class DMPState:
    """Node and edge messages at one retained step."""

    step: int
    node_susceptible: np.ndarray
    node_compromised_undetected: np.ndarray
    node_detected: np.ndarray
    node_quarantined: np.ndarray
    node_revoked: np.ndarray
    node_recovered: np.ndarray
    edge_no_transmission: np.ndarray
    edge_source_active: np.ndarray
    common_cause_survival: np.ndarray


@dataclass(frozen=True)
class DMPResult:
    """Dynamic prediction and retained node/edge state."""

    operator: DirectedTransmissionOperator
    states: tuple[DMPState, ...]
    final_ever_compromised_probability: np.ndarray
    expected_final_fraction: float
    outbreak_probability: float


@dataclass(frozen=True)
class StaticBaselineScores:
    """Scalar comparators retained separately from node-resolved DMP output."""

    adjacency_radius: float
    nonbacktracking_radius: float
    authorization_radius: float
    communication_radius: float
    simple_reproduction_number: float
    combined_propagation_scalar: float

    def as_features(self) -> dict[str, float]:
        return {
            "static_adjacency": self.adjacency_radius,
            "static_nonbacktracking": self.nonbacktracking_radius,
            "authorization_only": self.authorization_radius,
            "communication_only": self.communication_radius,
            "simple_reproduction": self.simple_reproduction_number,
            "combined_scalar": self.combined_propagation_scalar,
        }


def _freeze(values: np.ndarray, dtype: np.dtype | type = float) -> np.ndarray:
    result = np.asarray(values, dtype=dtype).copy()
    result.setflags(write=False)
    return result


def _spectral_radius(matrix: sparse.spmatrix) -> float:
    mat = sparse.csr_matrix(matrix, dtype=float)
    n = mat.shape[0]
    if n == 0 or mat.nnz == 0:
        return 0.0
    if n <= 64:
        return float(np.max(np.abs(np.linalg.eigvals(mat.toarray()))))
    try:
        value = eigs(
            mat,
            k=1,
            which="LM",
            v0=np.full(n, 1.0 / np.sqrt(n)),
            return_eigenvectors=False,
            tol=1e-7,
            maxiter=600,
        )[0]
        return float(abs(value))
    except (ArpackError, ArpackNoConvergence, ValueError):
        vector = np.full(n, 1.0 / n)
        estimate = 0.0
        for _ in range(300):
            candidate = np.asarray(mat @ vector).reshape(-1)
            norm = float(np.linalg.norm(candidate, ord=1))
            if norm <= 0.0:
                return 0.0
            vector = candidate / norm
            if abs(norm - estimate) <= 1e-8 * max(1.0, norm):
                break
            estimate = norm
        return float(estimate)


def build_transmission_operator(
    view: ObservedSystemView,
    config: DMPConfig | None = None,
) -> DirectedTransmissionOperator:
    """Build a directed weighted operator from observation-safe inputs."""
    assumptions = config or DMPConfig()
    aggregate = sparse.csr_matrix((view.n, view.n), dtype=float)
    credential = sparse.csr_matrix((view.n, view.n), dtype=float)
    for name in LAYER_NAMES:
        contribution = view.layers[name].astype(float) * float(assumptions.layer_weights[name])
        aggregate = aggregate + contribution
        if name == "credential":
            credential = contribution
    aggregate.sum_duplicates()
    aggregate.eliminate_zeros()
    aggregate.sort_indices()
    credential = credential.tocsr()

    rows = np.repeat(np.arange(view.n, dtype=np.int64), np.diff(aggregate.indptr))
    targets = aggregate.indices.astype(np.int64, copy=True)
    source_score = view.exploitability[rows]
    target_score = view.susceptibility[targets]
    intensity = (
        assumptions.base_transmission_intensity
        * aggregate.data
        * np.sqrt(np.maximum(0.0, source_score * target_score))
    )
    probability = np.clip(1.0 - np.exp(-intensity), 0.0, 1.0)

    credential_on_edges = (
        np.asarray(credential[rows, targets], dtype=float).reshape(-1)
        if len(rows)
        else np.zeros(0, dtype=float)
    )
    credential_fraction = np.divide(
        credential_on_edges,
        aggregate.data,
        out=np.zeros_like(aggregate.data),
        where=aggregate.data > 0.0,
    )
    weighted = sparse.csr_matrix((probability, targets, aggregate.indptr.copy()), shape=aggregate.shape)
    weighted.sort_indices()
    cross = view.segment_ids[rows] != view.segment_ids[targets]
    return DirectedTransmissionOperator(
        n=view.n,
        sources=_freeze(rows, np.int64),
        targets=_freeze(targets, np.int64),
        base_probability=_freeze(probability),
        credential_fraction=_freeze(credential_fraction),
        cross_segment=_freeze(cross, bool),
        matrix=weighted,
    )


def _state(
    step: int,
    susceptible: np.ndarray,
    compromised: np.ndarray,
    detected: np.ndarray,
    quarantined: np.ndarray,
    revoked: np.ndarray,
    recovered: np.ndarray,
    theta: np.ndarray,
    edge_active: np.ndarray,
    common_survival: np.ndarray,
) -> DMPState:
    return DMPState(
        step=step,
        node_susceptible=_freeze(susceptible),
        node_compromised_undetected=_freeze(compromised),
        node_detected=_freeze(detected),
        node_quarantined=_freeze(quarantined),
        node_revoked=_freeze(revoked),
        node_recovered=_freeze(recovered),
        edge_no_transmission=_freeze(theta),
        edge_source_active=_freeze(edge_active),
        common_cause_survival=_freeze(common_survival),
    )


def dynamic_message_passing(
    view: ObservedSystemView,
    config: DMPConfig | None = None,
) -> DMPResult:
    """Run sparse directed DMP with explicit common-cause and response states."""
    assumptions = config or DMPConfig()
    horizon = assumptions.horizon_steps or view.horizon_steps
    if horizon > view.horizon_steps:
        raise ValueError("DMP horizon exceeds the observed time profiles")
    operator = build_transmission_operator(view, assumptions)
    sources, targets = operator.sources, operator.targets
    seed = np.clip(view.initial_compromise_probability, 0.0, 1.0)
    susceptible = 1.0 - seed
    compromised = seed.copy()
    detected = np.zeros(view.n)
    quarantined = np.zeros(view.n)
    revoked = np.zeros(view.n)
    recovered = np.zeros(view.n)
    theta = np.ones(len(sources))
    common_survival = np.ones(view.n)
    edge_active = compromised[sources] if len(sources) else np.zeros(0)
    capture = set(assumptions.capture_steps)
    capture.add(0)
    capture.add(horizon)
    states: list[DMPState] = []
    if 0 in capture:
        states.append(
            _state(
                0,
                susceptible,
                compromised,
                detected,
                quarantined,
                revoked,
                recovered,
                theta,
                edge_active,
                common_survival,
            )
        )

    common_per_step = 1.0 - np.power(
        np.clip(1.0 - assumptions.common_cause_scale * view.common_cause_vector, 0.0, 1.0),
        1.0 / horizon,
    )
    for step in range(horizon):
        direct_source = np.clip(compromised + detected, 0.0, 1.0)
        credential_source = np.clip(direct_source + quarantined, 0.0, 1.0)
        edge_active = (
            (1.0 - operator.credential_fraction) * direct_source[sources]
            + operator.credential_fraction * credential_source[sources]
            if len(sources)
            else np.zeros(0)
        )
        multiplier = np.full(len(sources), view.defense_profile[step], dtype=float)
        if len(sources):
            multiplier[operator.cross_segment] *= (
                view.cross_segment_availability[step] * view.boundary_multiplier[step]
            )
        edge_probability = np.clip(operator.base_probability * multiplier, 0.0, 1.0)
        theta = np.clip(theta * (1.0 - edge_probability * edge_active), 1e-15, 1.0)
        common_survival = np.clip(common_survival * (1.0 - common_per_step), 0.0, 1.0)
        log_safe = np.zeros(view.n)
        if len(targets):
            np.add.at(log_safe, targets, np.log(theta))
        susceptible_new = np.clip((1.0 - seed) * common_survival * np.exp(log_safe), 0.0, 1.0)
        newly_compromised = np.maximum(0.0, susceptible - susceptible_new)

        detect_rate = np.clip(
            view.detection_rate * view.detection_profile[step], 0.0, 1.0
        )
        detected_flow = compromised * detect_rate
        quarantine_flow = detected * view.quarantine_rate
        revocation_flow = quarantined * view.revocation_rate
        recovery_flow = revoked * view.recovery_rate
        compromised = np.maximum(0.0, compromised + newly_compromised - detected_flow)
        detected = np.maximum(0.0, detected + detected_flow - quarantine_flow)
        quarantined = np.maximum(0.0, quarantined + quarantine_flow - revocation_flow)
        revoked = np.maximum(0.0, revoked + revocation_flow - recovery_flow)
        recovered = np.clip(recovered + recovery_flow, 0.0, 1.0)
        susceptible = susceptible_new

        total = susceptible + compromised + detected + quarantined + revoked + recovered
        correction = np.maximum(total, 1.0)
        compromised /= correction
        detected /= correction
        quarantined /= correction
        revoked /= correction
        recovered /= correction
        susceptible /= correction
        if step + 1 in capture:
            states.append(
                _state(
                    step + 1,
                    susceptible,
                    compromised,
                    detected,
                    quarantined,
                    revoked,
                    recovered,
                    theta,
                    edge_active,
                    common_survival,
                )
            )

    ever = np.clip(1.0 - susceptible, 0.0, 1.0)
    mean = float(np.sum(ever))
    variance = float(np.sum(ever * (1.0 - ever)))
    threshold = ceil(assumptions.outbreak_fraction * view.n)
    if variance <= 1e-14:
        outbreak_probability = float(mean >= threshold)
    else:
        z = (threshold - 0.5 - mean) / np.sqrt(variance)
        outbreak_probability = float(np.clip(1.0 - ndtr(z), 0.0, 1.0))
    return DMPResult(
        operator=operator,
        states=tuple(states),
        final_ever_compromised_probability=_freeze(ever),
        expected_final_fraction=float(mean / view.n),
        outbreak_probability=outbreak_probability,
    )


def _weighted_nonbacktracking_radius(operator: DirectedTransmissionOperator) -> float:
    sources, targets, weight = (
        operator.sources,
        operator.targets,
        operator.base_probability,
    )
    edge_count = len(sources)
    if edge_count == 0:
        return 0.0
    reverse_lookup = {(int(u), int(v)): index for index, (u, v) in enumerate(zip(sources, targets))}
    reverse = np.array(
        [reverse_lookup.get((int(v), int(u)), -1) for u, v in zip(sources, targets)],
        dtype=np.int64,
    )
    vector = np.full(edge_count, 1.0 / edge_count)
    estimate = 0.0
    for _ in range(300):
        incoming = np.bincount(targets, weights=vector, minlength=operator.n)
        candidate = incoming[sources]
        mask = reverse >= 0
        candidate[mask] -= vector[reverse[mask]]
        candidate = np.maximum(0.0, candidate) * weight
        norm = float(np.linalg.norm(candidate, ord=1))
        if norm <= 0.0:
            return 0.0
        candidate /= norm
        if abs(norm - estimate) <= 1e-8 * max(1.0, norm):
            estimate = norm
            break
        vector = candidate
        estimate = norm
    return float(estimate)


def static_baseline_scores(
    view: ObservedSystemView,
    config: DMPConfig | None = None,
) -> StaticBaselineScores:
    """Compute Stage 3B static scalar comparators without changing DMP state."""
    assumptions = config or DMPConfig()
    operator = build_transmission_operator(view, assumptions)
    authorization = view.layers["authorization"].multiply(
        assumptions.base_transmission_intensity * assumptions.layer_weights["authorization"]
    )
    communication = view.layers["communication"].multiply(
        assumptions.base_transmission_intensity * assumptions.layer_weights["communication"]
    )
    adjacency = _spectral_radius(operator.matrix)
    nonbacktracking = _weighted_nonbacktracking_radius(operator)
    mean_response = float(
        np.mean(
            view.detection_rate
            * view.quarantine_rate
            * view.revocation_rate
            + view.recovery_rate
        )
    )
    mean_outgoing = float(np.mean(np.asarray(operator.matrix.sum(axis=1)).reshape(-1)))
    simple_r = mean_outgoing / max(mean_response, 1e-12)
    combined = adjacency / max(mean_response, 1e-12)
    return StaticBaselineScores(
        adjacency_radius=adjacency,
        nonbacktracking_radius=nonbacktracking,
        authorization_radius=_spectral_radius(authorization),
        communication_radius=_spectral_radius(communication),
        simple_reproduction_number=simple_r,
        combined_propagation_scalar=combined,
    )


__all__ = [
    "DMPConfig",
    "DMPResult",
    "DMPState",
    "DirectedTransmissionOperator",
    "StaticBaselineScores",
    "build_transmission_operator",
    "dynamic_message_passing",
    "static_baseline_scores",
]
