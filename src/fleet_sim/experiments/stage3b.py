"""Stage 3B phase-separated compromise experiment orchestration.

The runner keeps three boundaries explicit:

* ``AttackTraceGenerator`` owns latent truth and produces outcomes.
* Predictors consume only ``ObservedSystemView``.
* Model fitting uses exploratory and calibration partitions; evaluation accepts
  held-out records only.

This module does not write evidence artifacts or adjudicate confirmatory
acceptance.  Those actions belong to the protocol-gated Stage 3 runner.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from math import cos, pi, sin
from time import perf_counter
from types import MappingProxyType
from typing import Literal

import numpy as np
from scipy import sparse

from fleet_sim.analysis.phase_separated import (
    PhaseSeparatedModel,
    PhaseSeparatedPrediction,
    PhaseSeparatedRecord,
    ResearchSplit,
    fit_phase_separated,
    predict_phase_separated,
    predict_phase_separated_crossfit,
)
from fleet_sim.analysis.predictive_metrics import (
    BinaryPredictiveMetrics,
    ContinuousPredictiveMetrics,
    binary_predictive_metrics,
    continuous_predictive_metrics,
)
from fleet_sim.security.attack_trace import (
    LAYER_NAMES,
    AttackEvent,
    AttackTraceConfig,
    AttackTraceGenerator,
    ObservedSystemView,
)
from fleet_sim.security.dynamic_message_passing import (
    DMPConfig,
    DMPResult,
    StaticBaselineScores,
    dynamic_message_passing,
    static_baseline_scores,
)

_CANDIDATE_INITIATION_FEATURES = ("dmp_outbreak_probability",)
_CANDIDATE_SEVERITY_FEATURES = ("dmp_expected_fraction",)
_STATIC_BASELINES = (
    "static_adjacency",
    "static_nonbacktracking",
    "combined_scalar",
    "authorization_only",
    "communication_only",
    "simple_reproduction",
)
_INTERPRETABLE_NON_DMP_FEATURES = (
    "node_hazard_aggregation",
    "reachable_component_fraction",
    "directed_percolation_fraction",
    *_STATIC_BASELINES,
)


@dataclass(frozen=True)
class Stage3BComparatorSpec:
    """One preregisterable comparator with explicit feature boundaries."""

    name: str
    initiation_features: tuple[str, ...]
    severity_features: tuple[str, ...]
    nonoutbreak_features: tuple[str, ...]
    model_class: str


def stage3b_comparator_specs() -> tuple[Stage3BComparatorSpec, ...]:
    """Return temporal, node-hazard, static, and multivariate comparators."""
    univariate = ("temporal_propagator", "node_hazard_aggregation", *_STATIC_BASELINES)
    specs = [
        Stage3BComparatorSpec(
            name=feature,
            initiation_features=(feature,),
            severity_features=(feature,),
            nonoutbreak_features=(feature,),
            model_class="univariate",
        )
        for feature in univariate
    ]
    specs.append(
        Stage3BComparatorSpec(
            name="interpretable_multivariate_non_dmp",
            initiation_features=_INTERPRETABLE_NON_DMP_FEATURES,
            severity_features=_INTERPRETABLE_NON_DMP_FEATURES,
            nonoutbreak_features=_INTERPRETABLE_NON_DMP_FEATURES,
            model_class="multivariate_non_dmp_interpretable",
        )
    )
    return tuple(specs)


@dataclass(frozen=True)
class Stage3BScenarioSpec:
    """One graph, observation, and attack-replication block."""

    scenario_id: str
    split: ResearchSplit
    block: int
    n_agents: int
    topology: str
    segmentation_policy: str
    attack_class: str
    graph_seed: int
    process_seed: int
    observation_seed: int
    replication_seed: int
    replications: int
    defense_case: str = "nominal"
    detection_probability: float | None = None
    quarantine_delay_steps: int | None = None
    revocation_delay_steps: int | None = None
    partition_probability: float | None = None

    def __post_init__(self) -> None:
        if not self.scenario_id:
            raise ValueError("scenario_id must be nonempty")
        if self.split not in {"exploratory", "calibration", "heldout"}:
            raise ValueError("split must be exploratory, calibration, or heldout")
        if self.n_agents < 2:
            raise ValueError("n_agents must be at least 2")
        if self.replications < 1:
            raise ValueError("replications must be positive")
        if not self.defense_case:
            raise ValueError("defense_case must be nonempty")
        for name in ("detection_probability", "partition_probability"):
            value = getattr(self, name)
            if value is not None and not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        for name in ("quarantine_delay_steps", "revocation_delay_steps"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be nonnegative")
        if self.segmentation_policy not in {"none", "partitioned_8_way", "partitioned"}:
            raise ValueError("unsupported segmentation policy")
        if self.attack_class not in {
            "direct_exploit",
            "credential_replay",
            "delegated_authority",
            "shared_dependency",
            "shared_image",
            "identity_provider",
            "mixed",
        }:
            raise ValueError("unsupported attack class")


@dataclass(frozen=True)
class Stage3BLifecyclePoint:
    """One exact synthetic-trace and estimated DMP lifecycle projection."""

    record_id: str
    scenario_id: str
    split: ResearchSplit
    block: int
    step: int
    observed_ever_compromised_fraction: float
    observed_detected_fraction: float
    observed_quarantined_fraction: float
    observed_revoked_fraction: float
    observed_recovered_fraction: float
    predicted_ever_compromised_fraction: float
    predicted_detected_fraction: float
    predicted_quarantined_fraction: float
    predicted_revoked_fraction: float
    predicted_recovered_fraction: float
    dmp_expected_fraction: float
    representation: str = "exact_synthetic_trace_and_estimated_dmp"


@dataclass(frozen=True)
class Stage3BDMPStateSummary:
    """Bounded scalar summary of one retained DMP state."""

    step: int
    susceptible_fraction: float
    compromised_undetected_fraction: float
    detected_fraction: float
    quarantined_fraction: float
    revoked_fraction: float
    recovered_fraction: float
    mean_edge_no_transmission: float
    mean_edge_source_active: float
    mean_common_cause_survival: float
    representation: str = "estimated_dmp_aggregate"


@dataclass(frozen=True)
class Stage3BGraphNode:
    """One node retained from the observed graph projection."""

    id: int
    x: float
    y: float
    segment: int
    initial_probability: float


@dataclass(frozen=True)
class Stage3BGraphEdge:
    """One directed observed edge retained for visualization."""

    source: int
    target: int
    layer: str
    weight: float


@dataclass(frozen=True)
class Stage3BObservedGraphEvidence:
    """Deterministically bounded projection of the predictor-visible graph."""

    nodes: tuple[Stage3BGraphNode, ...]
    edges: tuple[Stage3BGraphEdge, ...]
    source_node_count: int
    source_edge_count: int
    eligible_edge_count: int
    representation: Literal["exact", "sampled"]
    orientation: str = "row_source_column_target"


@dataclass(frozen=True)
class Stage3BConsoleTrace:
    """Visualization-only replay projection for one selected replication."""

    schema_version: str
    evidence_scope: str
    record_id: str
    scenario_id: str
    split: ResearchSplit
    block: int
    replication: int
    replication_seed: int
    graph_seed: int
    process_seed: int
    observation_seed: int
    attack_trace_digest: str
    attack_horizon_steps: int
    dmp_horizon_steps: int
    dmp_outbreak_probability: float
    dmp_expected_final_fraction: float
    lifecycle: tuple[Stage3BLifecyclePoint, ...]
    dmp_state_summary: tuple[Stage3BDMPStateSummary, ...]
    graph: Stage3BObservedGraphEvidence


@dataclass(frozen=True)
class Stage3BModelEvaluation:
    """Held-out predictive metrics for both phases and required error strata."""

    name: str
    initiation: BinaryPredictiveMetrics
    conditional_severity: ContinuousPredictiveMetrics
    conditional_nonoutbreak_severity: ContinuousPredictiveMetrics
    final_size: ContinuousPredictiveMetrics
    final_size_mae_by_topology: Mapping[str, float]
    final_size_mae_by_fleet_size: Mapping[int, float]
    final_size_mae_by_attack_class: Mapping[str, float]
    final_size_mae_by_segmentation: Mapping[str, float]
    final_size_mae_by_defense_case: Mapping[str, float]
    final_size_mae_by_block: Mapping[int, float]


@dataclass(frozen=True)
class Stage3BBaselineSelectionScore:
    """Out-of-fold calibration score used to select a comparator."""

    name: str
    calibration_final_size_mae: float
    calibration_outbreak_brier: float
    selection_method: str = "leave_one_block_out_calibration_crossfit"
    validation_blocks: tuple[int, ...] = ()


@dataclass(frozen=True)
class Stage3BExperimentResult:
    """In-memory engineering result.  It is not confirmatory adjudication."""

    records: tuple[PhaseSeparatedRecord, ...]
    candidate_model: PhaseSeparatedModel
    candidate_prediction: PhaseSeparatedPrediction
    candidate_evaluation: Stage3BModelEvaluation
    baseline_selection_scores: Mapping[str, Stage3BBaselineSelectionScore]
    comparator_specs: Mapping[str, Stage3BComparatorSpec]
    baseline_models: Mapping[str, PhaseSeparatedModel]
    baseline_predictions: Mapping[str, PhaseSeparatedPrediction]
    baseline_evaluations: Mapping[str, Stage3BModelEvaluation]
    strongest_final_size_baseline: str
    strongest_initiation_baseline: str
    final_size_mae_improvement_fraction: float
    outbreak_brier_improvement_fraction: float
    positive_final_size_blocks: int
    positive_outbreak_brier_blocks: int
    heldout_binary_support_by_block: Mapping[int, bool]
    valid_binary_support_blocks: int
    selection_partition: str
    selection_method: str
    elapsed_seconds: float


def _case_config(base: AttackTraceConfig, spec: Stage3BScenarioSpec) -> AttackTraceConfig:
    if spec.segmentation_policy == "none":
        segment_count, segmentation_strength = 1, 0.0
    elif spec.segmentation_policy == "partitioned_8_way":
        segment_count, segmentation_strength = min(8, spec.n_agents), 0.94
    else:
        segment_count, segmentation_strength = min(4, spec.n_agents), 0.86

    enabled_layers = {
        "direct_exploit": ("communication",),
        "credential_replay": ("credential",),
        "delegated_authority": ("authorization",),
        "shared_dependency": ("dependency",),
        "shared_image": (),
        "identity_provider": ("credential",),
        "mixed": LAYER_NAMES,
    }[spec.attack_class]
    supply_chain = base.supply_chain_step if spec.attack_class in {"shared_image", "mixed"} else None
    identity_provider = (
        base.identity_provider_step
        if spec.attack_class in {"identity_provider", "mixed"}
        else None
    )
    quarantine = (
        (spec.quarantine_delay_steps, spec.quarantine_delay_steps)
        if spec.quarantine_delay_steps is not None
        else base.quarantine_delay_range
    )
    revocation = (
        (spec.revocation_delay_steps, spec.revocation_delay_steps)
        if spec.revocation_delay_steps is not None
        else base.revocation_delay_range
    )
    partition_probability = (
        spec.partition_probability
        if spec.partition_probability is not None
        else base.partition_cross_segment_drop
    )
    if partition_probability == 0.0:
        partition_start, partition_end = None, None
    else:
        partition_start, partition_end = (
            base.partition_start_step,
            base.partition_end_step,
        )
    return replace(
        base,
        segment_count=segment_count,
        segmentation_strength=segmentation_strength,
        enabled_layers=tuple(enabled_layers),
        detection_probability=(
            spec.detection_probability
            if spec.detection_probability is not None
            else base.detection_probability
        ),
        quarantine_delay_range=quarantine,
        revocation_delay_range=revocation,
        supply_chain_step=supply_chain,
        identity_provider_step=identity_provider,
        partition_start_step=partition_start,
        partition_end_step=partition_end,
        partition_cross_segment_drop=partition_probability,
    )


def _reachable_component_fraction(view: ObservedSystemView) -> float:
    aggregate = sparse.csr_matrix((view.n, view.n), dtype=np.int8)
    for layer in view.layers.values():
        aggregate = aggregate + layer.astype(np.int8)
    aggregate.data[:] = 1
    aggregate.eliminate_zeros()
    seed_count = max(1, round(float(np.sum(view.initial_compromise_probability))))
    seeds = np.argsort(view.initial_compromise_probability, kind="mergesort")[-seed_count:]
    visited = np.zeros(view.n, dtype=bool)
    visited[seeds] = True
    frontier = [int(value) for value in seeds]
    while frontier:
        source = frontier.pop()
        begin, end = aggregate.indptr[source], aggregate.indptr[source + 1]
        for target_value in aggregate.indices[begin:end]:
            target = int(target_value)
            if not visited[target]:
                visited[target] = True
                frontier.append(target)
    return float(np.mean(visited))


def _temporal_propagator_score(view: ObservedSystemView, dmp: DMPResult) -> float:
    vector = np.maximum(view.initial_compromise_probability, 1e-15)
    vector /= float(vector.sum())
    log_growth = 0.0
    response = np.clip(view.detection_rate * view.quarantine_rate, 0.0, 1.0)
    for step in range(view.horizon_steps):
        transmitted = np.asarray(dmp.operator.matrix.T @ vector).reshape(-1)
        candidate = (1.0 - response) * vector + view.defense_profile[step] * transmitted
        norm = float(np.linalg.norm(candidate, ord=1))
        if norm <= 1e-15:
            return 0.0
        vector = candidate / norm
        log_growth += np.log(norm)
    return float(np.exp(log_growth / view.horizon_steps))


def scenario_predictor_features(
    view: ObservedSystemView,
    *,
    dmp_config: DMPConfig | None = None,
) -> tuple[dict[str, float], DMPResult, StaticBaselineScores]:
    """Compute observation-only node-resolved and static scenario features."""
    dmp = dynamic_message_passing(view, dmp_config)
    baselines = static_baseline_scores(view, dmp_config)
    incoming = np.asarray(dmp.operator.matrix.T @ view.initial_compromise_probability).reshape(-1)
    node_hazard = float(np.mean(1.0 - np.exp(-incoming - view.common_cause_vector)))
    incoming_strength = np.asarray(dmp.operator.matrix.sum(axis=0)).reshape(-1)
    percolation = float(np.mean(1.0 - np.exp(-incoming_strength)))
    features = baselines.as_features()
    features.update(
        {
            "dmp_outbreak_probability": dmp.outbreak_probability,
            "dmp_expected_fraction": dmp.expected_final_fraction,
            "node_hazard_aggregation": node_hazard,
            "temporal_propagator": _temporal_propagator_score(view, dmp),
            "reachable_component_fraction": _reachable_component_fraction(view),
            "directed_percolation_fraction": percolation,
        }
    )
    return features, dmp, baselines


def _replication_seed(base_seed: int, replication: int) -> int:
    sequence = np.random.SeedSequence([int(base_seed), int(replication)])
    return int(sequence.generate_state(1, dtype=np.uint64)[0])


def _attack_event_summary(
    events: Sequence[AttackEvent],
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    counts = dict(sorted(Counter(event.event_type for event in events).items()))
    first_step: dict[str, int] = {}
    last_step: dict[str, int] = {}
    for event in events:
        first_step.setdefault(event.event_type, int(event.step))
        last_step[event.event_type] = int(event.step)
    return counts, first_step, last_step


def _mean_or(values: np.ndarray, empty: float) -> float:
    return float(np.mean(values)) if len(values) else float(empty)


def _observed_graph_evidence(
    view: ObservedSystemView,
    *,
    maximum_nodes: int,
    maximum_edges: int,
) -> Stage3BObservedGraphEvidence:
    if maximum_nodes < 1 or maximum_edges < 1:
        raise ValueError("graph evidence bounds must be positive")
    if view.n <= maximum_nodes:
        selected: np.ndarray = np.arange(view.n, dtype=np.int64)
    else:
        risk_order = np.argsort(-view.initial_compromise_probability, kind="mergesort")
        selected = np.sort(risk_order[:maximum_nodes])
    selected_mask = np.zeros(view.n, dtype=bool)
    selected_mask[selected] = True
    nodes = tuple(
        Stage3BGraphNode(
            id=int(node),
            x=float(cos(2.0 * pi * rank / len(selected))),
            y=float(sin(2.0 * pi * rank / len(selected))),
            segment=int(view.segment_ids[node]),
            initial_probability=float(view.initial_compromise_probability[node]),
        )
        for rank, node in enumerate(selected)
    )

    eligible_edge_count = 0
    for name in LAYER_NAMES:
        matrix = view.layers[name]
        sources: np.ndarray = np.repeat(
            np.arange(view.n, dtype=np.int64), np.diff(matrix.indptr)
        )
        eligible_edge_count += int(
            np.count_nonzero(selected_mask[sources] & selected_mask[matrix.indices])
        )
    retained_indices = {
        int(value)
        for value in np.linspace(
            0,
            eligible_edge_count - 1,
            min(maximum_edges, eligible_edge_count),
            dtype=np.int64,
        )
    }
    edges: list[Stage3BGraphEdge] = []
    eligible_index = 0
    for name in LAYER_NAMES:
        matrix = view.layers[name]
        sources = np.repeat(np.arange(view.n, dtype=np.int64), np.diff(matrix.indptr))
        for source, target, weight in zip(sources, matrix.indices, matrix.data):
            if not (selected_mask[source] and selected_mask[target]):
                continue
            if eligible_index in retained_indices:
                edges.append(
                    Stage3BGraphEdge(
                        source=int(source),
                        target=int(target),
                        layer=name,
                        weight=float(weight),
                    )
                )
            eligible_index += 1
    source_edge_count = int(sum(matrix.nnz for matrix in view.layers.values()))
    representation: Literal["exact", "sampled"] = (
        "exact"
        if len(selected) == view.n and len(edges) == source_edge_count
        else "sampled"
    )
    return Stage3BObservedGraphEvidence(
        nodes=nodes,
        edges=tuple(edges),
        source_node_count=view.n,
        source_edge_count=source_edge_count,
        eligible_edge_count=eligible_edge_count,
        representation=representation,
    )


def materialize_stage3b_console_trace(
    spec: Stage3BScenarioSpec,
    replication: int,
    *,
    attack_config: AttackTraceConfig | None = None,
    dmp_config: DMPConfig | None = None,
    maximum_graph_nodes: int = 500,
    maximum_graph_edges: int = 2_500,
) -> Stage3BConsoleTrace:
    """Replay one selected trace into bounded, visualization-only evidence.

    The helper uses the same scenario, effective configuration, and derived
    replication seed as ``build_stage3b_records``. DMP capture is expanded to
    every modeled step without changing any numerical DMP parameter. Returned
    values are a presentation projection and must never be used to recompute
    or select scientific metrics.
    """
    if not 0 <= replication < spec.replications:
        raise ValueError("replication must identify one replication in the scenario spec")
    case_config = _case_config(attack_config or AttackTraceConfig(), spec)
    generator = AttackTraceGenerator(
        spec.n_agents,
        topology_seed=spec.graph_seed,
        process_seed=spec.process_seed,
        observation_seed=spec.observation_seed,
        topology=spec.topology,
        config=case_config,
    )
    seed = _replication_seed(spec.replication_seed, replication)
    trace = generator.simulate(seed)
    assumptions = dmp_config or DMPConfig()
    dmp_horizon = assumptions.horizon_steps or generator.observed_view.horizon_steps
    capture_config = replace(
        assumptions,
        capture_steps=tuple(range(dmp_horizon + 1)),
    )
    dmp = dynamic_message_passing(generator.observed_view, capture_config)
    state_by_step = {state.step: state for state in dmp.states}
    if set(state_by_step) != set(range(dmp_horizon + 1)):
        raise RuntimeError("console trace requires one retained DMP state per modeled step")

    record_id = f"{spec.scenario_id}:r{replication}"
    lifecycle: list[Stage3BLifecyclePoint] = []
    state_summary: list[Stage3BDMPStateSummary] = []
    last_attack_step = case_config.horizon_steps - 1
    for step in range(dmp_horizon + 1):
        state = state_by_step[step]
        observed_step = min(step, last_attack_step)
        compromised = (trace.compromise_step >= 0) & (
            trace.compromise_step <= observed_step
        )
        detected = (trace.detection_step <= observed_step) & (
            trace.detection_step <= last_attack_step
        )
        quarantined = (trace.quarantine_step <= observed_step) & (
            trace.quarantine_step <= last_attack_step
        )
        revoked = (trace.revocation_step <= observed_step) & (
            trace.revocation_step <= last_attack_step
        )
        recovered = (trace.recovery_step <= observed_step) & (
            trace.recovery_step <= last_attack_step
        )
        predicted_ever = float(np.mean(1.0 - state.node_susceptible))
        lifecycle.append(
            Stage3BLifecyclePoint(
                record_id=record_id,
                scenario_id=spec.scenario_id,
                split=spec.split,
                block=spec.block,
                step=step,
                observed_ever_compromised_fraction=float(np.mean(compromised)),
                observed_detected_fraction=float(np.mean(detected)),
                observed_quarantined_fraction=float(np.mean(quarantined)),
                observed_revoked_fraction=float(np.mean(revoked)),
                observed_recovered_fraction=float(np.mean(recovered)),
                predicted_ever_compromised_fraction=predicted_ever,
                predicted_detected_fraction=float(np.mean(state.node_detected)),
                predicted_quarantined_fraction=float(np.mean(state.node_quarantined)),
                predicted_revoked_fraction=float(np.mean(state.node_revoked)),
                predicted_recovered_fraction=float(np.mean(state.node_recovered)),
                dmp_expected_fraction=predicted_ever,
            )
        )
        state_summary.append(
            Stage3BDMPStateSummary(
                step=step,
                susceptible_fraction=float(np.mean(state.node_susceptible)),
                compromised_undetected_fraction=float(
                    np.mean(state.node_compromised_undetected)
                ),
                detected_fraction=float(np.mean(state.node_detected)),
                quarantined_fraction=float(np.mean(state.node_quarantined)),
                revoked_fraction=float(np.mean(state.node_revoked)),
                recovered_fraction=float(np.mean(state.node_recovered)),
                mean_edge_no_transmission=_mean_or(state.edge_no_transmission, 1.0),
                mean_edge_source_active=_mean_or(state.edge_source_active, 0.0),
                mean_common_cause_survival=float(
                    np.mean(state.common_cause_survival)
                ),
            )
        )
    return Stage3BConsoleTrace(
        schema_version="stage3b-console-trace-v1",
        evidence_scope="visualization_only_not_scientific_metric_input",
        record_id=record_id,
        scenario_id=spec.scenario_id,
        split=spec.split,
        block=spec.block,
        replication=replication,
        replication_seed=seed,
        graph_seed=spec.graph_seed,
        process_seed=spec.process_seed,
        observation_seed=spec.observation_seed,
        attack_trace_digest=trace.digest,
        attack_horizon_steps=case_config.horizon_steps,
        dmp_horizon_steps=dmp_horizon,
        dmp_outbreak_probability=dmp.outbreak_probability,
        dmp_expected_final_fraction=dmp.expected_final_fraction,
        lifecycle=tuple(lifecycle),
        dmp_state_summary=tuple(state_summary),
        graph=_observed_graph_evidence(
            generator.observed_view,
            maximum_nodes=maximum_graph_nodes,
            maximum_edges=maximum_graph_edges,
        ),
    )


def build_stage3b_records(
    specs: Sequence[Stage3BScenarioSpec],
    *,
    attack_config: AttackTraceConfig | None = None,
    dmp_config: DMPConfig | None = None,
) -> tuple[PhaseSeparatedRecord, ...]:
    """Generate replication records while preserving the observation boundary."""
    if not specs:
        raise ValueError("at least one Stage 3B scenario is required")
    if len({spec.scenario_id for spec in specs}) != len(specs):
        raise ValueError("scenario_id values must be unique")
    base = attack_config or AttackTraceConfig()
    records: list[PhaseSeparatedRecord] = []
    for spec in specs:
        case_config = _case_config(base, spec)
        generator = AttackTraceGenerator(
            spec.n_agents,
            topology_seed=spec.graph_seed,
            process_seed=spec.process_seed,
            observation_seed=spec.observation_seed,
            topology=spec.topology,
            config=case_config,
        )
        features, _dmp, _baselines = scenario_predictor_features(
            generator.observed_view, dmp_config=dmp_config
        )
        for replication in range(spec.replications):
            seed = _replication_seed(spec.replication_seed, replication)
            trace = generator.simulate(seed)
            event_counts, event_first_step, event_last_step = _attack_event_summary(
                trace.events
            )
            outbreak_count = max(
                1,
                int(np.ceil(case_config.outbreak_fraction * spec.n_agents)),
            )
            compromise_steps = np.sort(
                trace.compromise_step[trace.compromise_step >= 0]
            )
            outbreak_onset_step = (
                int(compromise_steps[outbreak_count - 1])
                if len(compromise_steps) >= outbreak_count
                else None
            )
            records.append(
                PhaseSeparatedRecord(
                    record_id=f"{spec.scenario_id}:r{replication}",
                    scenario_id=spec.scenario_id,
                    split=spec.split,
                    block=spec.block,
                    n_agents=spec.n_agents,
                    topology=spec.topology,
                    attack_class=spec.attack_class,
                    segmentation_policy=spec.segmentation_policy,
                    features=features,
                    outbreak=int(trace.outbreak),
                    final_compromise_fraction=trace.final_compromise_fraction,
                    replication_seed=seed,
                    base_replication_seed=spec.replication_seed,
                    defense_case=spec.defense_case,
                    detection_probability=case_config.detection_probability,
                    quarantine_delay_steps=round(np.mean(case_config.quarantine_delay_range)),
                    revocation_delay_steps=round(np.mean(case_config.revocation_delay_range)),
                    partition_probability=case_config.partition_cross_segment_drop,
                    graph_seed=spec.graph_seed,
                    process_seed=spec.process_seed,
                    observation_seed=spec.observation_seed,
                    attack_trace_digest=trace.digest,
                    attack_horizon_steps=case_config.horizon_steps,
                    outbreak_onset_step=outbreak_onset_step,
                    attack_peak_active_fraction=trace.peak_active_fraction,
                    attack_event_count=len(trace.events),
                    attack_event_type_counts=event_counts,
                    attack_event_first_step=event_first_step,
                    attack_event_last_step=event_last_step,
                )
            )
    return tuple(records)


def _group_mae(
    records: Sequence[PhaseSeparatedRecord],
    prediction: np.ndarray,
    attribute: str,
) -> Mapping[str | int, float]:
    observed = np.asarray([row.final_compromise_fraction for row in records], dtype=float)
    groups: dict[str | int, list[int]] = {}
    for index, row in enumerate(records):
        group = getattr(row, attribute)
        if not isinstance(group, (str, int)):
            raise TypeError(f"unsupported grouping value for {attribute}")
        groups.setdefault(group, []).append(index)
    return MappingProxyType(
        {
            group: float(np.mean(np.abs(prediction[indices] - observed[indices])))
            for group, indices in sorted(groups.items(), key=lambda item: str(item[0]))
        }
    )


def _group_mae_text(
    records: Sequence[PhaseSeparatedRecord],
    prediction: np.ndarray,
    attribute: str,
) -> Mapping[str, float]:
    return MappingProxyType(
        {str(key): value for key, value in _group_mae(records, prediction, attribute).items()}
    )


def _group_mae_integer(
    records: Sequence[PhaseSeparatedRecord],
    prediction: np.ndarray,
    attribute: str,
) -> Mapping[int, float]:
    return MappingProxyType(
        {int(key): value for key, value in _group_mae(records, prediction, attribute).items()}
    )


def evaluate_phase_model(
    name: str,
    model: PhaseSeparatedModel,
    heldout: Sequence[PhaseSeparatedRecord],
) -> tuple[PhaseSeparatedPrediction, Stage3BModelEvaluation]:
    """Evaluate one already-fitted model on held-out records only."""
    prediction = predict_phase_separated(model, heldout)
    outcome = np.asarray([row.outbreak for row in heldout], dtype=int)
    final = np.asarray([row.final_compromise_fraction for row in heldout], dtype=float)
    if set(np.unique(outcome)) != {0, 1}:
        raise ValueError("held-out evaluation requires both outbreak outcome classes")
    outbreak_indices = np.flatnonzero(outcome == 1)
    nonoutbreak_indices = np.flatnonzero(outcome == 0)
    evaluation = Stage3BModelEvaluation(
        name=name,
        initiation=binary_predictive_metrics(outcome, prediction.outbreak_probability),
        conditional_severity=continuous_predictive_metrics(
            final[outbreak_indices],
            prediction.conditional_severity[outbreak_indices],
            lower=prediction.conditional_severity_lower[outbreak_indices],
            upper=prediction.conditional_severity_upper[outbreak_indices],
        ),
        conditional_nonoutbreak_severity=continuous_predictive_metrics(
            final[nonoutbreak_indices],
            prediction.conditional_nonoutbreak_severity[nonoutbreak_indices],
            lower=prediction.conditional_nonoutbreak_severity_lower[nonoutbreak_indices],
            upper=prediction.conditional_nonoutbreak_severity_upper[nonoutbreak_indices],
        ),
        final_size=continuous_predictive_metrics(
            final,
            prediction.expected_final_fraction,
            lower=prediction.expected_final_fraction_lower,
            upper=prediction.expected_final_fraction_upper,
        ),
        final_size_mae_by_topology=_group_mae_text(
            heldout, prediction.expected_final_fraction, "topology"
        ),
        final_size_mae_by_fleet_size=_group_mae_integer(
            heldout, prediction.expected_final_fraction, "n_agents"
        ),
        final_size_mae_by_attack_class=_group_mae_text(
            heldout, prediction.expected_final_fraction, "attack_class"
        ),
        final_size_mae_by_segmentation=_group_mae_text(
            heldout, prediction.expected_final_fraction, "segmentation_policy"
        ),
        final_size_mae_by_defense_case=_group_mae_text(
            heldout, prediction.expected_final_fraction, "defense_case"
        ),
        final_size_mae_by_block=_group_mae_integer(
            heldout, prediction.expected_final_fraction, "block"
        ),
    )
    return prediction, evaluation


def _fit_comparator(
    spec: Stage3BComparatorSpec,
    exploratory: Sequence[PhaseSeparatedRecord],
    calibration: Sequence[PhaseSeparatedRecord],
) -> PhaseSeparatedModel:
    return fit_phase_separated(
        exploratory,
        calibration,
        initiation_features=spec.initiation_features,
        severity_features=spec.severity_features,
        nonoutbreak_features=spec.nonoutbreak_features,
    )


def _crossfit_comparator_score(
    spec: Stage3BComparatorSpec,
    exploratory: tuple[PhaseSeparatedRecord, ...],
    calibration: tuple[PhaseSeparatedRecord, ...],
) -> Stage3BBaselineSelectionScore:
    blocks = tuple(sorted({row.block for row in calibration}))
    if len(blocks) < 2:
        raise ValueError("comparator selection requires at least two calibration blocks")
    final_by_id: dict[str, float] = {}
    outbreak_by_id: dict[str, float] = {}
    for validation_block in blocks:
        fit_rows = tuple(row for row in calibration if row.block != validation_block)
        validation_rows = tuple(row for row in calibration if row.block == validation_block)
        try:
            model = _fit_comparator(spec, exploratory, fit_rows)
        except ValueError as exc:
            raise ValueError(
                f"comparator {spec.name} cannot fit calibration fold {validation_block}: {exc}"
            ) from exc
        prediction = predict_phase_separated_crossfit(model, validation_rows)
        for index, record in enumerate(validation_rows):
            final_by_id[record.record_id] = float(prediction.expected_final_fraction[index])
            outbreak_by_id[record.record_id] = float(prediction.outbreak_probability[index])
    if set(final_by_id) != {record.record_id for record in calibration}:
        raise RuntimeError(f"comparator {spec.name} did not score every calibration record")
    predicted_final = np.asarray(
        [final_by_id[record.record_id] for record in calibration], dtype=float
    )
    predicted_outbreak = np.asarray(
        [outbreak_by_id[record.record_id] for record in calibration], dtype=float
    )
    observed_final = np.asarray(
        [record.final_compromise_fraction for record in calibration], dtype=float
    )
    observed_outbreak = np.asarray([record.outbreak for record in calibration], dtype=float)
    return Stage3BBaselineSelectionScore(
        name=spec.name,
        calibration_final_size_mae=float(np.mean(np.abs(predicted_final - observed_final))),
        calibration_outbreak_brier=float(
            np.mean((predicted_outbreak - observed_outbreak) ** 2)
        ),
        validation_blocks=blocks,
    )


def fit_and_evaluate_stage3b(
    records: Sequence[PhaseSeparatedRecord],
) -> Stage3BExperimentResult:
    """Cross-fit comparators on calibration, then score held-out once."""
    started = perf_counter()
    exploratory = tuple(row for row in records if row.split == "exploratory")
    calibration = tuple(row for row in records if row.split == "calibration")
    heldout = tuple(row for row in records if row.split == "heldout")
    if not exploratory or not calibration or not heldout:
        raise ValueError("records must include exploratory, calibration, and heldout partitions")
    all_ids = [row.record_id for row in records]
    if len(set(all_ids)) != len(all_ids):
        raise ValueError("record IDs must be globally unique")

    candidate_model = fit_phase_separated(
        exploratory,
        calibration,
        initiation_features=_CANDIDATE_INITIATION_FEATURES,
        severity_features=_CANDIDATE_SEVERITY_FEATURES,
        nonoutbreak_features=_CANDIDATE_SEVERITY_FEATURES,
    )

    comparator_specs = {spec.name: spec for spec in stage3b_comparator_specs()}
    selection_scores = {
        name: _crossfit_comparator_score(spec, exploratory, calibration)
        for name, spec in comparator_specs.items()
    }
    strongest_final = min(
        selection_scores,
        key=lambda key: selection_scores[key].calibration_final_size_mae,
    )
    strongest_initiation = min(
        selection_scores,
        key=lambda key: selection_scores[key].calibration_outbreak_brier,
    )
    baseline_models = {
        name: _fit_comparator(comparator_specs[name], exploratory, calibration)
        for name in sorted({strongest_final, strongest_initiation})
    }

    # Held-out outcomes are first accessed only after comparator choices and
    # full-calibration refits have been fixed.
    candidate_prediction, candidate_evaluation = evaluate_phase_model(
        "phase_separated_dmp", candidate_model, heldout
    )
    baseline_evaluations: dict[str, Stage3BModelEvaluation] = {}
    baseline_predictions: dict[str, PhaseSeparatedPrediction] = {}
    for feature in sorted({strongest_final, strongest_initiation}):
        prediction, evaluation = evaluate_phase_model(
            feature, baseline_models[feature], heldout
        )
        baseline_predictions[feature] = prediction
        baseline_evaluations[feature] = evaluation
    final_baseline = baseline_evaluations[strongest_final].final_size.mean_absolute_error
    initiation_baseline = baseline_evaluations[strongest_initiation].initiation.brier_score
    final_improvement = (
        final_baseline - candidate_evaluation.final_size.mean_absolute_error
    ) / max(final_baseline, 1e-12)
    brier_improvement = (
        initiation_baseline - candidate_evaluation.initiation.brier_score
    ) / max(initiation_baseline, 1e-12)
    heldout_outcome = np.asarray([row.outbreak for row in heldout], dtype=float)
    heldout_final = np.asarray(
        [row.final_compromise_fraction for row in heldout], dtype=float
    )
    block_indices: dict[int, list[int]] = {}
    for index, row in enumerate(heldout):
        block_indices.setdefault(row.block, []).append(index)
    binary_support_by_block = MappingProxyType(
        {
            block: set(np.unique(heldout_outcome[indices])) == {0.0, 1.0}
            for block, indices in sorted(block_indices.items())
        }
    )
    final_baseline_prediction = baseline_predictions[
        strongest_final
    ].expected_final_fraction
    initiation_baseline_prediction = baseline_predictions[
        strongest_initiation
    ].outbreak_probability
    positive_final_blocks = 0
    positive_brier_blocks = 0
    for indices in block_indices.values():
        candidate_final_mae = float(
            np.mean(
                np.abs(
                    candidate_prediction.expected_final_fraction[indices]
                    - heldout_final[indices]
                )
            )
        )
        baseline_final_mae = float(
            np.mean(np.abs(final_baseline_prediction[indices] - heldout_final[indices]))
        )
        positive_final_blocks += int(candidate_final_mae < baseline_final_mae)
        candidate_brier = float(
            np.mean(
                (
                    candidate_prediction.outbreak_probability[indices]
                    - heldout_outcome[indices]
                )
                ** 2
            )
        )
        baseline_brier = float(
            np.mean(
                (
                    initiation_baseline_prediction[indices]
                    - heldout_outcome[indices]
                )
                ** 2
            )
        )
        positive_brier_blocks += int(candidate_brier < baseline_brier)
    return Stage3BExperimentResult(
        records=tuple(records),
        candidate_model=candidate_model,
        candidate_prediction=candidate_prediction,
        candidate_evaluation=candidate_evaluation,
        baseline_selection_scores=MappingProxyType(selection_scores),
        comparator_specs=MappingProxyType(comparator_specs),
        baseline_models=MappingProxyType(baseline_models),
        baseline_predictions=MappingProxyType(baseline_predictions),
        baseline_evaluations=MappingProxyType(baseline_evaluations),
        strongest_final_size_baseline=strongest_final,
        strongest_initiation_baseline=strongest_initiation,
        final_size_mae_improvement_fraction=float(final_improvement),
        outbreak_brier_improvement_fraction=float(brier_improvement),
        positive_final_size_blocks=int(positive_final_blocks),
        positive_outbreak_brier_blocks=int(positive_brier_blocks),
        heldout_binary_support_by_block=binary_support_by_block,
        valid_binary_support_blocks=sum(binary_support_by_block.values()),
        selection_partition="calibration",
        selection_method="leave_one_block_out_calibration_crossfit",
        elapsed_seconds=float(perf_counter() - started),
    )


def run_stage3b_experiment(
    specs: Sequence[Stage3BScenarioSpec],
    *,
    attack_config: AttackTraceConfig | None = None,
    dmp_config: DMPConfig | None = None,
) -> Stage3BExperimentResult:
    """Generate, fit, calibrate, and evaluate an in-memory Stage 3B study."""
    records = build_stage3b_records(
        specs, attack_config=attack_config, dmp_config=dmp_config
    )
    return fit_and_evaluate_stage3b(records)


__all__ = [
    "Stage3BBaselineSelectionScore",
    "Stage3BComparatorSpec",
    "Stage3BConsoleTrace",
    "Stage3BDMPStateSummary",
    "Stage3BExperimentResult",
    "Stage3BGraphEdge",
    "Stage3BGraphNode",
    "Stage3BLifecyclePoint",
    "Stage3BModelEvaluation",
    "Stage3BObservedGraphEvidence",
    "Stage3BScenarioSpec",
    "build_stage3b_records",
    "evaluate_phase_model",
    "fit_and_evaluate_stage3b",
    "materialize_stage3b_console_trace",
    "run_stage3b_experiment",
    "scenario_predictor_features",
    "stage3b_comparator_specs",
]
