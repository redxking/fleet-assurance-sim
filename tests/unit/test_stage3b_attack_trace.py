import numpy as np

from fleet_sim.security.attack_trace import LAYER_NAMES, AttackTraceConfig, AttackTraceGenerator


def _response_config() -> AttackTraceConfig:
    return AttackTraceConfig(
        horizon_steps=12,
        mean_out_degree=2,
        enabled_layers=(),
        detection_delay_range=(0, 0),
        quarantine_delay_range=(1, 1),
        revocation_delay_range=(1, 1),
        recovery_delay_range=(1, 1),
        supply_chain_step=1,
        identity_provider_step=None,
        common_cause_probability=1.0,
        boundary_failure_step=3,
        partition_start_step=4,
        partition_end_step=6,
    )


def test_attack_trace_is_deterministic_and_preserves_response_order():
    generator = AttackTraceGenerator(
        48,
        topology_seed=101,
        process_seed=102,
        observation_seed=103,
        topology="random_regular",
        config=_response_config(),
    )
    first = generator.simulate(104)
    second = generator.simulate(104)
    assert first.digest == second.digest
    assert np.array_equal(first.ever_compromised, second.ever_compromised)
    assert any(event.mechanism == "supply_chain_common_cause" for event in first.events)
    event_types = {event.event_type for event in first.events}
    assert {
        "detected",
        "quarantined",
        "credentials_revoked",
        "recovered",
        "boundary_failed",
        "network_partition_started",
        "network_partition_ended",
    }.issubset(event_types)
    recovered = np.flatnonzero(first.recovery_step < _response_config().horizon_steps)
    assert len(recovered) > 0
    assert np.all(first.compromise_step[recovered] < first.detection_step[recovered])
    assert np.all(first.detection_step[recovered] <= first.quarantine_step[recovered])
    assert np.all(first.quarantine_step[recovered] <= first.revocation_step[recovered])
    assert np.all(first.revocation_step[recovered] <= first.recovery_step[recovered])


def test_observed_view_exposes_no_latent_truth_and_has_explicit_common_cause_vector():
    generator = AttackTraceGenerator(
        32,
        topology_seed=201,
        process_seed=202,
        observation_seed=203,
        topology="erdos_renyi",
        config=_response_config(),
    )
    view = generator.observed_view
    assert set(view.layers) == set(LAYER_NAMES)
    assert view.common_cause_vector.shape == (32,)
    assert np.any(view.common_cause_vector > 0.0)
    assert not any("true" in name or "latent" in name for name in vars(view))
    assert all(matrix.shape == (32, 32) for matrix in view.layers.values())
    assert all(not matrix.data.flags.writeable for matrix in view.layers.values())


def test_protocol_topologies_are_distinct_and_declared_name_is_retained():
    fingerprints = {}
    config = AttackTraceConfig(
        horizon_steps=3,
        mean_out_degree=2,
        supply_chain_step=None,
        identity_provider_step=None,
        boundary_failure_step=None,
        partition_start_step=None,
        partition_end_step=None,
    )
    for topology in (
        "random_regular",
        "erdos_renyi",
        "barabasi_albert",
        "hierarchical",
    ):
        generator = AttackTraceGenerator(
            40,
            topology_seed=301,
            process_seed=302,
            observation_seed=303,
            topology=topology,
            config=config,
        )
        matrix = generator.observed_view.layers["authorization"]
        fingerprints[topology] = (matrix.indptr.tobytes(), matrix.indices.tobytes())
        assert generator.topology == topology
    assert len(set(fingerprints.values())) == 4
