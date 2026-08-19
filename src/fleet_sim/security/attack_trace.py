"""Independent, event-driven attack traces for Stage 3B.

The generator in this module is intentionally separate from the predictive
models.  It uses a discrete attacker campaign with bounded attempt budgets,
hidden edge resistance, response delays, and explicit common-cause actions.
Predictors receive only :class:`ObservedSystemView`; they never receive the
latent system used to generate outcomes.

All matrices use row=source and column=target orientation.  Inputs and
parameters are synthetic research constructs, not measurements of an
operational fleet.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from math import exp
from types import MappingProxyType

import networkx as nx
import numpy as np
from scipy import sparse

LAYER_NAMES = (
    "authorization",
    "communication",
    "dependency",
    "credential",
    "supervision",
)

_LAYER_MECHANISM = {
    "authorization": "delegated_authority",
    "communication": "direct_exploit",
    "dependency": "shared_dependency",
    "credential": "credential_replay",
    "supervision": "supervisory_relationship",
}


def _read_only_vector(values: np.ndarray, *, dtype: np.dtype | type = float) -> np.ndarray:
    vector = np.asarray(values, dtype=dtype).copy()
    vector.setflags(write=False)
    return vector


def _read_only_csr(matrix: sparse.spmatrix, n: int) -> sparse.csr_matrix:
    result = sparse.csr_matrix(matrix, dtype=float, shape=(n, n)).copy()
    result.sum_duplicates()
    result.eliminate_zeros()
    result.sort_indices()
    if result.nnz and (not np.isfinite(result.data).all() or np.any(result.data < 0.0)):
        raise ValueError("layer weights must be finite and nonnegative")
    result.data.setflags(write=False)
    result.indices.setflags(write=False)
    result.indptr.setflags(write=False)
    return result


@dataclass(frozen=True)
class DefensePhase:
    """Observable defense effectiveness beginning at ``start_step``."""

    start_step: int
    transmission_multiplier: float
    detection_multiplier: float = 1.0

    def __post_init__(self) -> None:
        if self.start_step < 0:
            raise ValueError("defense phase start_step must be nonnegative")
        if not 0.0 <= self.transmission_multiplier <= 2.0:
            raise ValueError("transmission multiplier must be in [0, 2]")
        if not 0.0 <= self.detection_multiplier <= 2.0:
            raise ValueError("detection multiplier must be in [0, 2]")


@dataclass(frozen=True)
class AttackTraceConfig:
    """Frozen controls for one synthetic attack-system family."""

    horizon_steps: int = 30
    mean_out_degree: int = 3
    segment_count: int = 4
    segmentation_strength: float = 0.82
    initial_compromises: int = 1
    attempts_per_active_node: int = 2
    enabled_layers: tuple[str, ...] = LAYER_NAMES
    outbreak_fraction: float = 0.10
    detection_probability: float | None = None
    detection_delay_range: tuple[int, int] = (2, 6)
    quarantine_delay_range: tuple[int, int] = (1, 3)
    revocation_delay_range: tuple[int, int] = (1, 4)
    recovery_delay_range: tuple[int, int] = (2, 6)
    supply_chain_step: int | None = 4
    identity_provider_step: int | None = 8
    common_cause_probability: float = 0.08
    boundary_failure_step: int | None = 12
    boundary_failure_multiplier: float = 1.45
    partition_start_step: int | None = 10
    partition_end_step: int | None = 15
    partition_cross_segment_drop: float = 0.70
    observation_edge_miss_probability: float = 0.05
    observation_spurious_edge_fraction: float = 0.01
    observation_noise_sigma: float = 0.15
    defense_phases: tuple[DefensePhase, ...] = field(
        default_factory=lambda: (
            DefensePhase(0, 1.00, 1.00),
            DefensePhase(16, 0.62, 1.30),
        )
    )

    def __post_init__(self) -> None:
        if self.horizon_steps < 1:
            raise ValueError("horizon_steps must be positive")
        if self.mean_out_degree < 1:
            raise ValueError("mean_out_degree must be positive")
        if self.segment_count < 1:
            raise ValueError("segment_count must be positive")
        if not 0.0 <= self.segmentation_strength <= 1.0:
            raise ValueError("segmentation_strength must be in [0, 1]")
        if self.initial_compromises < 1:
            raise ValueError("initial_compromises must be positive")
        if self.attempts_per_active_node < 1:
            raise ValueError("attempts_per_active_node must be positive")
        if len(set(self.enabled_layers)) != len(self.enabled_layers):
            raise ValueError("enabled_layers cannot contain duplicates")
        if not set(self.enabled_layers).issubset(LAYER_NAMES):
            raise ValueError(f"enabled_layers must be drawn from {list(LAYER_NAMES)}")
        for name in (
            "outbreak_fraction",
            "common_cause_probability",
            "partition_cross_segment_drop",
            "observation_edge_miss_probability",
            "observation_spurious_edge_fraction",
        ):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        if (
            self.detection_probability is not None
            and not 0.0 <= self.detection_probability <= 1.0
        ):
            raise ValueError("detection_probability must be in [0, 1]")
        if self.boundary_failure_multiplier < 1.0:
            raise ValueError("boundary_failure_multiplier must be at least 1")
        if self.observation_noise_sigma < 0.0:
            raise ValueError("observation_noise_sigma must be nonnegative")
        for name in (
            "detection_delay_range",
            "quarantine_delay_range",
            "revocation_delay_range",
            "recovery_delay_range",
        ):
            low, high = getattr(self, name)
            if low < 0 or high < low:
                raise ValueError(f"invalid {name}")
        if self.partition_start_step is None and self.partition_end_step is not None:
            raise ValueError("partition_end_step requires partition_start_step")
        if self.partition_start_step is not None and (
            self.partition_end_step is None
            or self.partition_end_step <= self.partition_start_step
        ):
            raise ValueError("partition_end_step must follow partition_start_step")
        starts = [phase.start_step for phase in self.defense_phases]
        if not starts or starts[0] != 0 or starts != sorted(set(starts)):
            raise ValueError("defense phases must start at zero and have unique sorted starts")


@dataclass(frozen=True)
class ObservedSystemView:
    """The complete information boundary available to Stage 3B predictors.

    Layer matrices are directed and follow row=source, column=target.  The
    common-cause vector is an exogenous node probability, not a synthetic edge.
    """

    n: int
    layers: Mapping[str, sparse.csr_matrix]
    susceptibility: np.ndarray
    exploitability: np.ndarray
    detection_rate: np.ndarray
    quarantine_rate: np.ndarray
    revocation_rate: np.ndarray
    recovery_rate: np.ndarray
    initial_compromise_probability: np.ndarray
    common_cause_vector: np.ndarray
    segment_ids: np.ndarray
    defense_profile: np.ndarray
    detection_profile: np.ndarray
    cross_segment_availability: np.ndarray
    boundary_multiplier: np.ndarray
    schema_version: str = "stage3b-observed-view-v1"

    def __post_init__(self) -> None:
        if self.n < 2:
            raise ValueError("n must be at least 2")
        if set(self.layers) != set(LAYER_NAMES):
            raise ValueError(f"layers must be exactly {list(LAYER_NAMES)}")
        matrices = {
            name: _read_only_csr(self.layers[name], self.n) for name in LAYER_NAMES
        }
        object.__setattr__(self, "layers", MappingProxyType(matrices))
        probability_fields = (
            "susceptibility",
            "exploitability",
            "detection_rate",
            "quarantine_rate",
            "revocation_rate",
            "recovery_rate",
            "initial_compromise_probability",
            "common_cause_vector",
        )
        for name in probability_fields:
            value = np.asarray(getattr(self, name), dtype=float)
            if value.shape != (self.n,) or not np.isfinite(value).all():
                raise ValueError(f"{name} must be a finite vector of length n")
            if np.any(value < 0.0):
                raise ValueError(f"{name} must be nonnegative")
            if name not in {"susceptibility", "exploitability"} and np.any(value > 1.0):
                raise ValueError(f"{name} must be in [0, 1]")
            object.__setattr__(self, name, _read_only_vector(value))
        segments = np.asarray(self.segment_ids, dtype=np.int64)
        if segments.shape != (self.n,) or np.any(segments < 0):
            raise ValueError("segment_ids must be a nonnegative vector of length n")
        object.__setattr__(self, "segment_ids", _read_only_vector(segments, dtype=np.int64))
        profile_names = (
            "defense_profile",
            "detection_profile",
            "cross_segment_availability",
            "boundary_multiplier",
        )
        profile_length: int | None = None
        for name in profile_names:
            value = np.asarray(getattr(self, name), dtype=float)
            if value.ndim != 1 or len(value) < 1 or not np.isfinite(value).all():
                raise ValueError(f"{name} must be a nonempty finite vector")
            if np.any(value < 0.0):
                raise ValueError(f"{name} must be nonnegative")
            if profile_length is None:
                profile_length = len(value)
            elif len(value) != profile_length:
                raise ValueError("all time profiles must have the same length")
            object.__setattr__(self, name, _read_only_vector(value))

    @property
    def horizon_steps(self) -> int:
        return len(self.defense_profile)


@dataclass(frozen=True)
class AttackEvent:
    """One causal or response transition in a generated attack trace."""

    step: int
    event_type: str
    node: int | None = None
    source: int | None = None
    mechanism: str | None = None


@dataclass(frozen=True)
class AttackTrace:
    """Outcome of one stochastic attack campaign."""

    seed: int
    events: tuple[AttackEvent, ...]
    ever_compromised: np.ndarray
    compromise_step: np.ndarray
    detection_step: np.ndarray
    quarantine_step: np.ndarray
    revocation_step: np.ndarray
    recovery_step: np.ndarray
    peak_active_fraction: float
    final_compromise_fraction: float
    outbreak: bool
    digest: str


@dataclass(frozen=True)
class _LatentSystem:
    layers: Mapping[str, sparse.csr_matrix]
    edge_resistance: Mapping[str, sparse.csr_matrix]
    edge_delay: Mapping[str, sparse.csr_matrix]
    susceptibility: np.ndarray
    exploitability: np.ndarray
    detection_propensity: np.ndarray
    common_cause: np.ndarray
    idp_exposure: np.ndarray
    segments: np.ndarray


def _directed_layer(
    n: int,
    degree: int,
    *,
    topology: str,
    segments: np.ndarray,
    segmentation_strength: float,
    rng: np.random.Generator,
) -> sparse.csr_matrix:
    degree = max(1, int(degree))
    if topology in {"random_regular", "random"}:
        source_parts: list[np.ndarray] = []
        target_parts: list[np.ndarray] = []
        actual_degree = min(degree, n - 1)
        candidates = np.arange(n - 1, dtype=np.int64)
        for source in range(n):
            selected = rng.choice(candidates, size=actual_degree, replace=False)
            selected = selected + (selected >= source)
            source_parts.append(np.full(actual_degree, source, dtype=np.int64))
            target_parts.append(selected)
        sources = np.concatenate(source_parts)
        targets = np.concatenate(target_parts)
    elif topology == "erdos_renyi":
        probability = min(1.0, degree / max(1, n - 1))
        counts = rng.binomial(n - 1, probability, size=n)
        source_parts = []
        target_parts = []
        candidates = np.arange(n - 1, dtype=np.int64)
        for source, count_value in enumerate(counts):
            count = int(count_value)
            if not count:
                continue
            selected = rng.choice(candidates, size=count, replace=False)
            selected = selected + (selected >= source)
            source_parts.append(np.full(count, source, dtype=np.int64))
            target_parts.append(selected)
        sources = np.concatenate(source_parts) if source_parts else np.zeros(0, dtype=np.int64)
        targets = np.concatenate(target_parts) if target_parts else np.zeros(0, dtype=np.int64)
    elif topology in {"barabasi_albert", "hub"}:
        attachment = min(max(1, degree), n - 1)
        graph = nx.barabasi_albert_graph(
            n,
            attachment,
            seed=int(rng.integers(0, np.iinfo(np.int32).max)),
        )
        undirected_edges = np.asarray(list(graph.edges()), dtype=np.int64)
        orientation = rng.random(len(undirected_edges)) < 0.5
        sources = np.where(orientation, undirected_edges[:, 0], undirected_edges[:, 1])
        targets = np.where(orientation, undirected_edges[:, 1], undirected_edges[:, 0])
        reverse = rng.random(len(sources)) < 0.08
        sources = np.concatenate([sources, targets[reverse]])
        targets = np.concatenate([targets, sources[: len(orientation)][reverse]])
    elif topology == "hierarchical":
        branch = max(2, degree)
        children = np.arange(1, n, dtype=np.int64)
        parents = (children - 1) // branch
        sources = parents.copy()
        targets = children.copy()
        local_sources = np.arange(n, dtype=np.int64)
        segment_members = [
            np.flatnonzero(segments == segment) for segment in np.unique(segments)
        ]
        local_targets = np.empty(n, dtype=np.int64)
        for source in range(n):
            members = segment_members[int(segments[source])]
            candidates = members[members != source]
            if len(candidates):
                local_targets[source] = int(rng.choice(candidates))
            else:
                local_targets[source] = (source + 1) % n
        sources = np.concatenate([sources, local_sources])
        targets = np.concatenate([targets, local_targets])
    elif topology == "segmented":
        sources = np.repeat(np.arange(n, dtype=np.int64), degree)
        targets = rng.integers(0, n, size=len(sources), dtype=np.int64)
        local = rng.random(len(sources)) < segmentation_strength
        segment_members = [
            np.flatnonzero(segments == segment) for segment in np.unique(segments)
        ]
        for segment, members in enumerate(segment_members):
            mask = local & (segments[sources] == segment)
            count = int(mask.sum())
            if count:
                targets[mask] = members[rng.integers(0, len(members), size=count)]
    elif topology == "zipf_hub":
        sources = np.repeat(np.arange(n, dtype=np.int64), degree)
        order = rng.permutation(n)
        ranks = np.minimum(rng.zipf(2.0, size=len(sources)), n) - 1
        targets = order[ranks]
    else:
        raise ValueError(
            "topology must be random_regular, erdos_renyi, barabasi_albert, "
            "hierarchical, random, segmented, hub, or zipf_hub"
        )
    keep = sources != targets
    sources, targets = sources[keep], targets[keep]
    matrix = sparse.csr_matrix(
        (np.ones(len(sources), dtype=float), (sources, targets)), shape=(n, n)
    )
    matrix.sum_duplicates()
    matrix.data[:] = 1.0
    matrix.eliminate_zeros()
    matrix.sort_indices()
    return matrix


def _observe_layer(
    matrix: sparse.csr_matrix,
    *,
    miss_probability: float,
    spurious_fraction: float,
    rng: np.random.Generator,
) -> sparse.csr_matrix:
    coo = matrix.tocoo()
    keep = rng.random(matrix.nnz) >= miss_probability
    rows = coo.row[keep].astype(np.int64, copy=False)
    cols = coo.col[keep].astype(np.int64, copy=False)
    target_spurious = round(spurious_fraction * max(1, matrix.nnz))
    if target_spurious:
        extra_rows = rng.integers(0, matrix.shape[0], size=target_spurious, dtype=np.int64)
        extra_cols = rng.integers(0, matrix.shape[0], size=target_spurious, dtype=np.int64)
        valid = extra_rows != extra_cols
        rows = np.concatenate([rows, extra_rows[valid]])
        cols = np.concatenate([cols, extra_cols[valid]])
    observed = sparse.csr_matrix(
        (np.ones(len(rows), dtype=float), (rows, cols)), shape=matrix.shape
    )
    observed.sum_duplicates()
    observed.data[:] = 1.0
    observed.eliminate_zeros()
    observed.sort_indices()
    return observed


def _time_profiles(config: AttackTraceConfig) -> tuple[np.ndarray, ...]:
    defense = np.ones(config.horizon_steps, dtype=float)
    detection = np.ones(config.horizon_steps, dtype=float)
    for phase in config.defense_phases:
        defense[phase.start_step :] = phase.transmission_multiplier
        detection[phase.start_step :] = phase.detection_multiplier
    availability = np.ones(config.horizon_steps, dtype=float)
    if config.partition_start_step is not None and config.partition_end_step is not None:
        availability[config.partition_start_step : config.partition_end_step] = (
            1.0 - config.partition_cross_segment_drop
        )
    boundary = np.ones(config.horizon_steps, dtype=float)
    if config.boundary_failure_step is not None:
        boundary[config.boundary_failure_step :] = config.boundary_failure_multiplier
    return defense, detection, availability, boundary


class AttackTraceGenerator:
    """Own latent attack state and expose only an observation-safe view."""

    def __init__(
        self,
        n: int,
        *,
        topology_seed: int,
        process_seed: int | None = None,
        observation_seed: int | None = None,
        topology: str = "random",
        config: AttackTraceConfig | None = None,
    ) -> None:
        self.config = config or AttackTraceConfig()
        if n < 2:
            raise ValueError("n must be at least 2")
        if self.config.initial_compromises >= n:
            raise ValueError("initial_compromises must be smaller than n")
        self.n = int(n)
        self.topology_seed = int(topology_seed)
        self.process_seed = int(process_seed if process_seed is not None else topology_seed + 1)
        self.observation_seed = int(
            observation_seed if observation_seed is not None else topology_seed + 2
        )
        self.topology = str(topology)
        self._latent, self._observed_view = self._build_system()

    @property
    def observed_view(self) -> ObservedSystemView:
        """Return the sole predictor-facing representation."""
        return self._observed_view

    def _build_system(self) -> tuple[_LatentSystem, ObservedSystemView]:
        graph_rng = np.random.default_rng(self.topology_seed)
        process_rng = np.random.default_rng(self.process_seed)
        n = self.n
        config = self.config
        segment_count = min(config.segment_count, n)
        segments = np.arange(n, dtype=np.int64) % segment_count
        graph_rng.shuffle(segments)
        family_count = max(2, round(np.sqrt(n)))
        image_family = process_rng.integers(0, family_count, size=n)
        family_risk = np.clip(
            process_rng.beta(2.2, 5.0, size=family_count), 0.03, 0.85
        )
        susceptibility = np.clip(
            process_rng.lognormal(-0.10, 0.38, size=n)
            * (0.75 + family_risk[image_family]),
            0.20,
            2.80,
        )
        exploitability = np.clip(
            process_rng.lognormal(-0.05, 0.34, size=n), 0.25, 2.60
        )
        if config.detection_probability is None:
            detection_propensity = np.clip(
                process_rng.beta(4.0, 3.0, size=n), 0.08, 0.98
            )
        else:
            detection_propensity = np.clip(
                config.detection_probability
                * process_rng.lognormal(-0.5 * 0.12**2, 0.12, size=n),
                0.01,
                0.99,
            )
        idp_exposure = np.clip(process_rng.beta(1.8, 5.2, size=n), 0.0, 1.0)
        common_cause = np.clip(
            0.62 * family_risk[image_family] + 0.38 * idp_exposure,
            0.0,
            1.0,
        )

        degree = config.mean_out_degree
        layer_degree = {
            "authorization": degree,
            "communication": degree,
            "dependency": max(1, degree // 2),
            "credential": max(1, degree // 2),
            "supervision": 1,
        }
        graph_sequences = np.random.SeedSequence(self.topology_seed).spawn(len(LAYER_NAMES))
        process_sequences = np.random.SeedSequence(self.process_seed).spawn(len(LAYER_NAMES))
        observation_sequences = np.random.SeedSequence(self.observation_seed).spawn(
            len(LAYER_NAMES) + 1
        )
        layers: dict[str, sparse.csr_matrix] = {}
        resistance: dict[str, sparse.csr_matrix] = {}
        delay: dict[str, sparse.csr_matrix] = {}
        observed_layers: dict[str, sparse.csr_matrix] = {}
        for index, name in enumerate(LAYER_NAMES):
            layer_rng = np.random.default_rng(graph_sequences[index])
            latent_rng = np.random.default_rng(process_sequences[index])
            observed_rng = np.random.default_rng(observation_sequences[index])
            matrix = _directed_layer(
                n,
                layer_degree[name],
                topology=self.topology,
                segments=segments,
                segmentation_strength=config.segmentation_strength,
                rng=layer_rng,
            )
            layers[name] = matrix
            edge_resistance = matrix.copy()
            edge_resistance.data = latent_rng.beta(3.0, 2.2, size=matrix.nnz)
            resistance[name] = edge_resistance
            edge_delay = matrix.copy()
            edge_delay.data = latent_rng.integers(0, 3, size=matrix.nnz).astype(float)
            delay[name] = edge_delay
            observed_layers[name] = _observe_layer(
                matrix,
                miss_probability=config.observation_edge_miss_probability,
                spurious_fraction=config.observation_spurious_edge_fraction,
                rng=observed_rng,
            )

        observation_rng = np.random.default_rng(observation_sequences[-1])
        sigma = config.observation_noise_sigma
        noise = lambda: observation_rng.lognormal(-0.5 * sigma**2, sigma, size=n)
        susceptibility_observed = np.clip(susceptibility * noise(), 0.10, 3.20)
        exploitability_observed = np.clip(exploitability * noise(), 0.10, 3.00)
        detection_delay_mean = 0.5 * sum(config.detection_delay_range)
        quarantine_delay_mean = 0.5 * sum(config.quarantine_delay_range)
        revocation_delay_mean = 0.5 * sum(config.revocation_delay_range)
        recovery_delay_mean = 0.5 * sum(config.recovery_delay_range)
        detection_rate = np.clip(
            detection_propensity / max(1.0, detection_delay_mean),
            0.01,
            1.0,
        )
        detection_rate = np.clip(detection_rate * noise(), 0.01, 1.0)
        quarantine_rate = np.full(n, 1.0 / max(1.0, quarantine_delay_mean))
        revocation_rate = np.full(n, 1.0 / max(1.0, revocation_delay_mean))
        recovery_rate = np.full(n, 1.0 / max(1.0, recovery_delay_mean))
        seed_weight = exploitability_observed / float(exploitability_observed.sum())
        seed_probability = np.clip(config.initial_compromises * seed_weight, 0.0, 1.0)
        common_observed = np.clip(config.common_cause_probability * common_cause * noise(), 0.0, 0.80)
        defense, detection_profile, availability, boundary = _time_profiles(config)
        latent = _LatentSystem(
            layers=MappingProxyType(layers),
            edge_resistance=MappingProxyType(resistance),
            edge_delay=MappingProxyType(delay),
            susceptibility=susceptibility,
            exploitability=exploitability,
            detection_propensity=detection_propensity,
            common_cause=common_cause,
            idp_exposure=idp_exposure,
            segments=segments,
        )
        observed = ObservedSystemView(
            n=n,
            layers=observed_layers,
            susceptibility=susceptibility_observed,
            exploitability=exploitability_observed,
            detection_rate=detection_rate,
            quarantine_rate=quarantine_rate,
            revocation_rate=revocation_rate,
            recovery_rate=recovery_rate,
            initial_compromise_probability=seed_probability,
            common_cause_vector=common_observed,
            segment_ids=segments,
            defense_profile=defense,
            detection_profile=detection_profile,
            cross_segment_availability=availability,
            boundary_multiplier=boundary,
        )
        return latent, observed

    @staticmethod
    def _sample_delay(rng: np.random.Generator, bounds: tuple[int, int]) -> int:
        return int(rng.integers(bounds[0], bounds[1] + 1))

    def simulate(self, attack_seed: int) -> AttackTrace:
        """Generate one deterministic-given-seed discrete attack trace."""
        rng = np.random.default_rng(int(attack_seed))
        config = self.config
        latent = self._latent
        n = self.n
        susceptible, compromised, detected, quarantined, revoked, recovered = range(6)
        state = np.full(n, susceptible, dtype=np.int8)
        ever = np.zeros(n, dtype=bool)
        unset = config.horizon_steps + max(config.recovery_delay_range) + 1
        compromise_step = np.full(n, -1, dtype=np.int64)
        detection_step = np.full(n, unset, dtype=np.int64)
        quarantine_step = np.full(n, unset, dtype=np.int64)
        revocation_step = np.full(n, unset, dtype=np.int64)
        recovery_step = np.full(n, unset, dtype=np.int64)
        events: list[AttackEvent] = []
        pending: dict[int, list[tuple[int, int, str, float]]] = {}

        seed_weight = latent.exploitability / float(latent.exploitability.sum())
        seeds = rng.choice(n, size=config.initial_compromises, replace=False, p=seed_weight)

        def compromise(node: int, step: int, source: int | None, mechanism: str) -> None:
            if state[node] != susceptible:
                return
            state[node] = compromised
            ever[node] = True
            compromise_step[node] = step
            detection_delay = self._sample_delay(rng, config.detection_delay_range)
            phase = max(
                (phase for phase in config.defense_phases if phase.start_step <= step),
                key=lambda candidate: candidate.start_step,
            )
            detection_delay = max(
                1,
                round(
                    detection_delay
                    / max(
                        0.1,
                        latent.detection_propensity[node] * phase.detection_multiplier,
                    )
                ),
            )
            detection_step[node] = step + detection_delay
            quarantine_step[node] = detection_step[node] + self._sample_delay(
                rng, config.quarantine_delay_range
            )
            revocation_step[node] = quarantine_step[node] + self._sample_delay(
                rng, config.revocation_delay_range
            )
            recovery_step[node] = revocation_step[node] + self._sample_delay(
                rng, config.recovery_delay_range
            )
            events.append(AttackEvent(step, "compromised", node, source, mechanism))

        for node in sorted(int(value) for value in np.atleast_1d(seeds)):
            compromise(node, 0, None, "initial_access")

        tactic_bias = {
            "authorization": 0.15,
            "communication": 0.00,
            "dependency": 0.25,
            "credential": 0.45,
            "supervision": 0.20,
        }
        peak_active = float(config.initial_compromises)

        for step in range(config.horizon_steps):
            if config.boundary_failure_step == step:
                events.append(AttackEvent(step, "boundary_failed"))
            if config.partition_start_step == step:
                events.append(AttackEvent(step, "network_partition_started"))
            if config.partition_end_step == step:
                events.append(AttackEvent(step, "network_partition_ended"))

            for node in np.flatnonzero((state == compromised) & (detection_step <= step)):
                state[node] = detected
                events.append(AttackEvent(step, "detected", int(node)))
            for node in np.flatnonzero((state == detected) & (quarantine_step <= step)):
                state[node] = quarantined
                events.append(AttackEvent(step, "quarantined", int(node)))
            for node in np.flatnonzero((state == quarantined) & (revocation_step <= step)):
                state[node] = revoked
                events.append(AttackEvent(step, "credentials_revoked", int(node)))
            for node in np.flatnonzero((state == revoked) & (recovery_step <= step)):
                state[node] = recovered
                events.append(AttackEvent(step, "recovered", int(node)))

            for source, target, mechanism, pending_probability in pending.pop(step, []):
                if state[target] == susceptible and rng.random() < pending_probability:
                    compromise(target, step, source, mechanism)

            if config.supply_chain_step == step:
                phase = max(
                    (phase for phase in config.defense_phases if phase.start_step <= step),
                    key=lambda candidate: candidate.start_step,
                )
                common_probability = np.clip(
                    config.common_cause_probability
                    * latent.common_cause
                    * phase.transmission_multiplier,
                    0.0,
                    0.95,
                )
                selected = np.flatnonzero(
                    (state == susceptible) & (rng.random(n) < common_probability)
                )
                for node in selected:
                    compromise(int(node), step, None, "supply_chain_common_cause")
            if config.identity_provider_step == step:
                common_probability = np.clip(
                    0.65 * config.common_cause_probability * latent.idp_exposure,
                    0.0,
                    0.90,
                )
                selected = np.flatnonzero(
                    (state == susceptible) & (rng.random(n) < common_probability)
                )
                for node in selected:
                    compromise(int(node), step, None, "identity_provider_common_cause")

            active_direct = np.flatnonzero((state == compromised) | (state == detected))
            active_credentials = np.flatnonzero(
                (state == compromised) | (state == detected) | (state == quarantined)
            )
            layer_order = list(config.enabled_layers)
            rng.shuffle(layer_order)
            for name in layer_order:
                matrix = latent.layers[name]
                resistance = latent.edge_resistance[name]
                delay = latent.edge_delay[name]
                active = active_credentials if name == "credential" else active_direct
                for source_value in active:
                    source = int(source_value)
                    begin, end = int(matrix.indptr[source]), int(matrix.indptr[source + 1])
                    if begin == end:
                        continue
                    choice_count = min(config.attempts_per_active_node, end - begin)
                    choices = rng.choice(np.arange(begin, end), size=choice_count, replace=False)
                    for edge_index_value in np.atleast_1d(choices):
                        edge_index = int(edge_index_value)
                        target = int(matrix.indices[edge_index])
                        if state[target] != susceptible:
                            continue
                        cross_segment = latent.segments[source] != latent.segments[target]
                        if cross_segment and config.partition_start_step is not None:
                            if config.partition_end_step is None:
                                raise RuntimeError("validated partition end step is missing")
                            in_partition = (
                                config.partition_start_step
                                <= step
                                < config.partition_end_step
                            )
                            if in_partition and rng.random() < config.partition_cross_segment_drop:
                                continue
                        boundary = (
                            config.boundary_failure_multiplier
                            if cross_segment
                            and config.boundary_failure_step is not None
                            and step >= config.boundary_failure_step
                            else 1.0
                        )
                        phase = max(
                            (
                                phase
                                for phase in config.defense_phases
                                if phase.start_step <= step
                            ),
                            key=lambda candidate: candidate.start_step,
                        )
                        hidden_margin = (
                            -2.75
                            + tactic_bias[name]
                            + 0.72 * np.log1p(latent.exploitability[source])
                            + 0.95 * np.sqrt(latent.susceptibility[target])
                            - 1.65 * float(resistance.data[edge_index])
                            + np.log(boundary)
                            + np.log(max(phase.transmission_multiplier, 1e-9))
                        )
                        success_probability = min(0.88, 0.72 / (1.0 + exp(-hidden_margin)))
                        due = step + max(1, int(delay.data[edge_index]))
                        if due < config.horizon_steps:
                            pending.setdefault(due, []).append(
                                (
                                    source,
                                    target,
                                    _LAYER_MECHANISM[name],
                                    success_probability,
                                )
                            )

            active_count = int(np.count_nonzero((state >= compromised) & (state < recovered)))
            peak_active = max(peak_active, float(active_count))

        final_fraction = float(np.mean(ever))
        event_payload = [
            [event.step, event.event_type, event.node, event.source, event.mechanism]
            for event in events
        ]
        digest = hashlib.sha256(
            json.dumps(event_payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            + ever.tobytes()
        ).hexdigest()
        trace = AttackTrace(
            seed=int(attack_seed),
            events=tuple(events),
            ever_compromised=_read_only_vector(ever, dtype=bool),
            compromise_step=_read_only_vector(compromise_step, dtype=np.int64),
            detection_step=_read_only_vector(detection_step, dtype=np.int64),
            quarantine_step=_read_only_vector(quarantine_step, dtype=np.int64),
            revocation_step=_read_only_vector(revocation_step, dtype=np.int64),
            recovery_step=_read_only_vector(recovery_step, dtype=np.int64),
            peak_active_fraction=float(peak_active / n),
            final_compromise_fraction=final_fraction,
            outbreak=bool(final_fraction >= config.outbreak_fraction),
            digest=digest,
        )
        return trace


__all__ = [
    "LAYER_NAMES",
    "AttackEvent",
    "AttackTrace",
    "AttackTraceConfig",
    "AttackTraceGenerator",
    "DefensePhase",
    "ObservedSystemView",
]
