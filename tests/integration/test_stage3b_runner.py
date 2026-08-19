from fleet_sim.experiments.stage3b import (
    Stage3BScenarioSpec,
    build_stage3b_records,
    materialize_stage3b_console_trace,
)
from fleet_sim.security.attack_trace import AttackTraceConfig
from fleet_sim.security.dynamic_message_passing import DMPConfig


def test_stage3b_record_builder_is_deterministic_and_retains_defense_case():
    spec = Stage3BScenarioSpec(
        scenario_id="engineering-hierarchical-shift",
        split="heldout",
        block=4,
        n_agents=36,
        topology="hierarchical",
        segmentation_policy="partitioned_8_way",
        attack_class="shared_image",
        graph_seed=401,
        process_seed=402,
        observation_seed=403,
        replication_seed=404,
        replications=2,
        defense_case="low-detection-slow-response",
        detection_probability=0.25,
        quarantine_delay_steps=4,
        revocation_delay_steps=5,
        partition_probability=0.05,
    )
    attack = AttackTraceConfig(
        horizon_steps=8,
        mean_out_degree=2,
        supply_chain_step=1,
        identity_provider_step=None,
        common_cause_probability=0.8,
        boundary_failure_step=4,
        partition_start_step=2,
        partition_end_step=5,
    )
    dmp = DMPConfig(horizon_steps=8)
    first = build_stage3b_records([spec], attack_config=attack, dmp_config=dmp)
    second = build_stage3b_records([spec], attack_config=attack, dmp_config=dmp)
    assert first == second
    assert len(first) == 2
    assert len({record.replication_seed for record in first}) == 2
    assert all(record.topology == "hierarchical" for record in first)
    assert all(record.defense_case == "low-detection-slow-response" for record in first)
    assert all(record.detection_probability == 0.25 for record in first)
    assert all(record.quarantine_delay_steps == 4 for record in first)
    assert all(record.revocation_delay_steps == 5 for record in first)
    assert all(record.partition_probability == 0.05 for record in first)
    assert all(record.graph_seed == 401 for record in first)
    assert all(record.process_seed == 402 for record in first)
    assert all(record.observation_seed == 403 for record in first)
    assert all(record.attack_horizon_steps == 8 for record in first)
    assert all(
        record.outbreak_onset_step is None
        or 0 <= record.outbreak_onset_step < record.attack_horizon_steps
        for record in first
    )
    assert all(
        record.attack_peak_active_fraction is not None
        and 0.0 <= record.attack_peak_active_fraction <= 1.0
        for record in first
    )
    assert all(
        record.attack_trace_digest is not None
        and len(record.attack_trace_digest) == 64
        for record in first
    )
    assert all(
        sum(record.attack_event_type_counts.values()) == record.attack_event_count
        for record in first
    )
    assert all(
        set(record.attack_event_first_step)
        == set(record.attack_event_last_step)
        == set(record.attack_event_type_counts)
        for record in first
    )
    assert all(
        record.attack_event_first_step[event_type]
        <= record.attack_event_last_step[event_type]
        for record in first
        for event_type in record.attack_event_type_counts
    )

    console_trace = materialize_stage3b_console_trace(
        spec,
        1,
        attack_config=attack,
        dmp_config=dmp,
        maximum_graph_nodes=10,
        maximum_graph_edges=12,
    )
    repeated = materialize_stage3b_console_trace(
        spec,
        1,
        attack_config=attack,
        dmp_config=dmp,
        maximum_graph_nodes=10,
        maximum_graph_edges=12,
    )
    assert console_trace == repeated
    assert console_trace.evidence_scope == "visualization_only_not_scientific_metric_input"
    assert console_trace.replication_seed == first[1].replication_seed
    assert console_trace.attack_trace_digest == first[1].attack_trace_digest
    assert len(console_trace.lifecycle) == 9
    assert len(console_trace.dmp_state_summary) == 9
    assert console_trace.graph.representation == "sampled"
    assert len(console_trace.graph.nodes) == 10
    assert len(console_trace.graph.edges) <= 12
    assert all(
        point.dmp_expected_fraction == point.predicted_ever_compromised_fraction
        for point in console_trace.lifecycle
    )
    assert all(
        0.0 <= value <= 1.0
        for point in console_trace.lifecycle
        for value in (
            point.observed_ever_compromised_fraction,
            point.observed_detected_fraction,
            point.observed_quarantined_fraction,
            point.observed_revoked_fraction,
            point.observed_recovered_fraction,
            point.dmp_expected_fraction,
        )
    )

    exact_graph = materialize_stage3b_console_trace(
        spec,
        1,
        attack_config=attack,
        dmp_config=dmp,
        maximum_graph_nodes=spec.n_agents,
        maximum_graph_edges=100_000,
    ).graph
    assert exact_graph.representation == "exact"
    assert len(exact_graph.nodes) == exact_graph.source_node_count
    assert len(exact_graph.edges) == exact_graph.source_edge_count
