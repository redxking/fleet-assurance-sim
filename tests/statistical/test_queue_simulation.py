from __future__ import annotations

from fleet_sim.control_plane.queueing import mm1_metrics, simulate_mm_c


def test_mm1_simulation_matches_closed_form() -> None:
    analytic = mm1_metrics(4.0, 5.0)
    simulated = simulate_mm_c(
        arrival_rate=4.0,
        service_rate_per_server=5.0,
        servers=1,
        jobs=80_000,
        warmup_jobs=10_000,
        seed=20260819,
    )
    assert abs(simulated.mean_time_system_s - analytic.mean_time_system_s) / analytic.mean_time_system_s < 0.08
    assert abs(simulated.time_average_number_system - analytic.mean_number_system) / analytic.mean_number_system < 0.10
    assert abs(simulated.little_law_residual) < 0.08
