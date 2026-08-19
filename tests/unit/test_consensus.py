from __future__ import annotations

from fleet_sim.consensus import bounded_committee_cost, fault_bounds, pbft_class_cost, threshold_leader_cost


def test_pbft_message_accounting() -> None:
    cost = pbft_class_cost(4)
    assert cost.messages == 4 * 3 * 2 + 3 + 4
    assert cost.sequential_message_steps == 4
    assert fault_bounds(4) == {"max_byzantine_f": 1, "max_crash_f": 1}


def test_threshold_and_bounded_committee_scale_below_flat_pbft() -> None:
    flat = pbft_class_cost(100)
    threshold = threshold_leader_cost(100)
    bounded = bounded_committee_cost(10_000, 16)
    assert threshold.messages < flat.messages
    assert bounded.messages < pbft_class_cost(10_000).messages
