from __future__ import annotations

import math

from fleet_sim.control_plane.queueing import erlang_c, minimum_servers, mm1_metrics


def test_mm1_closed_form() -> None:
    metrics = mm1_metrics(4.0, 5.0)
    assert math.isclose(metrics.utilization, 0.8)
    assert math.isclose(metrics.mean_number_system, 4.0)
    assert math.isclose(metrics.mean_time_system_s, 1.0)
    assert math.isclose(metrics.mean_number_system, 4.0 * metrics.mean_time_system_s)


def test_erlang_c_reduces_to_mm1() -> None:
    mm1 = mm1_metrics(4.0, 5.0)
    mmc = erlang_c(4.0, 5.0, 1)
    assert math.isclose(mmc.probability_wait, mm1.probability_wait, rel_tol=1e-12)
    assert math.isclose(mmc.mean_time_system_s, mm1.mean_time_system_s, rel_tol=1e-12)
    assert math.isclose(mmc.mean_number_system, mm1.mean_number_system, rel_tol=1e-12)


def test_minimum_servers_for_target_utilization() -> None:
    assert minimum_servers(70.0, 10.0, 0.70) == 10
    assert minimum_servers(70.1, 10.0, 0.70) == 11
