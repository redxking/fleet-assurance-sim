"""Stage 0 verification, analytic sweeps, and artifact orchestration."""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from fleet_sim.analysis.usl import bootstrap_usl, fit_usl, usl_capacity
from fleet_sim.config import load_config
from fleet_sim.consensus.models import bounded_committee_cost, pbft_class_cost, threshold_leader_cost
from fleet_sim.control_plane.queueing import erlang_c, minimum_servers, mm1_metrics, simulate_mm_c
from fleet_sim.credentials import certificate_issuance_rate, pairwise_key_count, size_issuer
from fleet_sim.experiments.simulator import FleetSimulator
from fleet_sim.graphs import apply_segmentation, build_graph
from fleet_sim.provenance.registry import load_parameter_registry
from fleet_sim.security import (
    approximate_critical_q,
    percolation_distribution,
    simulate_complete_gossip_mean_field,
    simulate_gossip,
)
from fleet_sim.supervision import supervisory_depth
from fleet_sim.telemetry import hierarchical_telemetry
from fleet_sim.timing import fiber_propagation_delay, holdover_uncertainty, landauer_energy_per_bit
from fleet_sim.visualization.console import build_console
from fleet_sim.visualization.figures import (
    consensus_scaling_figure,
    credential_scaling_figure,
    gossip_scaling_figure,
    percolation_figure,
    queue_verification_figure,
    telemetry_scaling_figure,
    timing_sweep_figure,
    usl_verification_figure,
    write_figure_manifest,
)
from fleet_sim.visualization.static import export_final_topology


SCALE_LADDER = (1, 10, 100, 1_000, 10_000, 30_000, 100_000)


def _json_write(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path


def _confidence_interval(values: list[float], confidence: float = 0.95) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    if len(array) < 2:
        value = float(array[0]) if len(array) else math.nan
        return value, value
    mean = float(np.mean(array))
    standard_error = float(stats.sem(array))
    critical = float(stats.t.ppf((1.0 + confidence) / 2.0, len(array) - 1))
    return mean - critical * standard_error, mean + critical * standard_error


def _run_pytest(repository_root: Path) -> dict[str, Any]:
    started = time.time()
    process = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "passed": process.returncode == 0,
        "return_code": process.returncode,
        "stdout": process.stdout.strip(),
        "stderr": process.stderr.strip(),
        "wall_clock_s": time.time() - started,
    }


def _queue_verification(replications: int, seed: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    service_rate = 1.0
    rhos = (0.25, 0.50, 0.70, 0.85, 0.95)
    jobs = 16_000
    warmup_jobs = 2_000
    for replication in range(replications):
        replication_seed = seed + replication
        for rho in rhos:
            arrival_rate = rho * service_rate
            analytic = mm1_metrics(arrival_rate, service_rate)
            simulated = simulate_mm_c(
                arrival_rate=arrival_rate,
                service_rate_per_server=service_rate,
                servers=1,
                jobs=jobs,
                warmup_jobs=warmup_jobs,
                seed=replication_seed,
            )
            rows.append(
                {
                    "replication": replication,
                    "seed": replication_seed,
                    "rho": rho,
                    "jobs": jobs,
                    "warmup_jobs": warmup_jobs,
                    "analytic_mean_number_system": analytic.mean_number_system,
                    "analytic_mean_time_system_s": analytic.mean_time_system_s,
                    "simulated_mean_number_system": simulated.time_average_number_system,
                    "simulated_mean_time_system_s": simulated.mean_time_system_s,
                    "simulated_utilization": simulated.utilization,
                    "little_law_residual": simulated.little_law_residual,
                }
            )
    frame = pd.DataFrame(rows)
    checks: list[dict[str, Any]] = []
    for rho, group in frame.groupby("rho"):
        analytic_l = float(group["analytic_mean_number_system"].iloc[0])
        mean_l = float(group["simulated_mean_number_system"].mean())
        relative_error = abs(mean_l - analytic_l) / analytic_l
        low, high = _confidence_interval(group["simulated_mean_number_system"].tolist())
        tolerance = 0.10 if rho <= 0.85 else 0.25
        checks.append(
            {
                "rho": float(rho),
                "analytic_L": analytic_l,
                "simulated_mean_L": mean_l,
                "mean_95_percent_ci": [low, high],
                "relative_error": relative_error,
                "tolerance": tolerance,
                "passed": relative_error <= tolerance,
            }
        )
    return frame, {"passed": all(item["passed"] for item in checks), "checks": checks}


def _gossip_verification(replications: int, seed: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    exact_n_values = (10, 100, 1_000)
    for n_agents in exact_n_values:
        graph = build_graph(n_agents, "complete", seed=seed)
        for replication in range(replications):
            replication_seed = seed + replication
            result = simulate_gossip(
                graph,
                seed=replication_seed,
                source=0,
                fanout=2,
                protocol="push_pull",
                loss_probability=0.0,
            )
            rows.append(
                {
                    "n_agents": n_agents,
                    "replication": replication,
                    "seed": replication_seed,
                    "rounds_to_99_percent": result.rounds_to_coverage(0.99),
                    "rounds_executed": result.rounds_executed,
                    "messages_sent": result.messages_sent,
                    "reached_all": result.reached_all,
                    "model_resolution": "exact_agent_level",
                }
            )

    # Validate the complete-graph state-count approximation at N=1000 with
    # common seeds, then use it for the N=10000 scale rung.
    exact_1000 = [
        row for row in rows if row["n_agents"] == 1_000
    ]
    approximation_errors: list[float] = []
    for replication in range(replications):
        replication_seed = seed + replication
        approximate = simulate_complete_gossip_mean_field(
            1_000,
            seed=replication_seed,
            fanout=2,
            protocol="push_pull",
            loss_probability=0.0,
        )
        exact_rounds = float(exact_1000[replication]["rounds_to_99_percent"])
        approximate_rounds = float(approximate.rounds_to_coverage(0.99))
        approximation_errors.append(approximate_rounds - exact_rounds)

        large = simulate_complete_gossip_mean_field(
            10_000,
            seed=replication_seed,
            fanout=2,
            protocol="push_pull",
            loss_probability=0.0,
        )
        rows.append(
            {
                "n_agents": 10_000,
                "replication": replication,
                "seed": replication_seed,
                "rounds_to_99_percent": large.rounds_to_coverage(0.99),
                "rounds_executed": large.rounds_executed,
                "messages_sent": large.messages_sent,
                "reached_all": large.reached_all,
                "model_resolution": "validated_state_count_approximation",
            }
        )

    frame = pd.DataFrame(rows)
    grouped = frame.groupby("n_agents")["rounds_to_99_percent"].mean()
    slope, intercept, r_value, _, _ = stats.linregress(
        np.log2(grouped.index.to_numpy(dtype=float)),
        grouped.to_numpy(dtype=float),
    )
    mean_absolute_error = float(np.mean(np.abs(approximation_errors)))
    maximum_absolute_error = float(np.max(np.abs(approximation_errors)))
    approximation_passed = maximum_absolute_error <= 2.0
    return frame, {
        "passed": bool(
            frame["reached_all"].all()
            and r_value**2 >= 0.90
            and approximation_passed
        ),
        "fit_rounds_equals_a_log2_n_plus_b": {
            "a": float(slope),
            "b": float(intercept),
            "r_squared": float(r_value**2),
        },
        "large_n_approximation_validation_at_n_1000": {
            "mean_absolute_round_error": mean_absolute_error,
            "maximum_absolute_round_error": maximum_absolute_error,
            "acceptance_threshold_rounds": 2.0,
            "passed": approximation_passed,
        },
    }


def _percolation_verification(replications: int, seed: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    base = build_graph(1_000, "random_regular", seed=seed, degree=6)
    segmented = apply_segmentation(
        base,
        "dynamic_microsegmentation",
        partitions=20,
        degree_cap=6,
    )
    architectures = {"unsegmented": base, "dynamic_microsegmentation": segmented}
    rows: list[dict[str, Any]] = []
    for q in np.linspace(0.0, 1.0, 11):
        for architecture, graph in architectures.items():
            distribution = percolation_distribution(
                graph,
                q=float(q),
                replications=replications,
                seed=seed + int(round(q * 10_000)),
            )
            for replication, fraction in enumerate(distribution.largest_component_fractions):
                rows.append(
                    {
                        "architecture": architecture,
                        "q": float(q),
                        "replication": replication,
                        "seed_family": seed + int(round(q * 10_000)),
                        "largest_component_fraction": fraction,
                    }
                )
    frame = pd.DataFrame(rows)
    at_half = frame[np.isclose(frame["q"], 0.5)].groupby("architecture")["largest_component_fraction"].mean()
    reduction = float(at_half["unsegmented"] - at_half["dynamic_microsegmentation"])
    return frame, {
        "passed": reduction > 0,
        "mean_blast_radius_reduction_at_q_0_5": reduction,
        "approximate_critical_q": {
            "unsegmented": approximate_critical_q(base),
            "dynamic_microsegmentation": approximate_critical_q(segmented),
        },
        "interpretation_limit": "Finite bond-percolation verification on one notional graph realization.",
    }


def _analytic_scale_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    control_rows: list[dict[str, Any]] = []
    consensus_rows: list[dict[str, Any]] = []
    telemetry_rows: list[dict[str, Any]] = []
    credential_rows: list[dict[str, Any]] = []
    supervision_rows: list[dict[str, Any]] = []
    arrival_per_agent = 0.03
    service_per_server = 10.0
    fixed_servers = 4
    for n_agents in SCALE_LADDER:
        arrival_rate = n_agents * arrival_per_agent
        queue = erlang_c(arrival_rate, service_per_server, fixed_servers)
        control_rows.append(
            {
                "n_agents": n_agents,
                "arrival_rate_hz": arrival_rate,
                "fixed_servers": fixed_servers,
                "service_rate_per_server_hz": service_per_server,
                "rho_fixed_servers": queue.utilization,
                "erlang_c_probability_wait": queue.probability_wait,
                "mean_wait_queue_s": queue.mean_wait_queue_s,
                "servers_required_for_rho_0_70": minimum_servers(arrival_rate, service_per_server, 0.70),
                "evidence_class": "analytic_under_notional_workload",
            }
        )

        for cost in (
            pbft_class_cost(n_agents),
            threshold_leader_cost(n_agents),
            bounded_committee_cost(n_agents, min(31, n_agents)),
        ):
            consensus_rows.append(
                {
                    "n_agents": n_agents,
                    "protocol": cost.protocol,
                    "committee_size": cost.committee_size,
                    "messages": cost.messages,
                    "bytes_transmitted": cost.bytes_transmitted,
                    "signature_generations": cost.signature_generations,
                    "signature_verifications": cost.signature_verifications,
                    "sequential_message_steps": cost.sequential_message_steps,
                    "evidence_class": "analytic_message_accounting",
                }
            )

        telemetry_rows.append(
            {
                "n_agents": n_agents,
                "architecture": "flat",
                "span": 1,
                "depth": 0,
                "raw_rate_bps": n_agents * 2_000.0,
                "apex_rate_bps": n_agents * 2_000.0,
                "evidence_class": "analytic_under_notional_telemetry_rate",
            }
        )
        for span in (4, 8, 16):
            result = hierarchical_telemetry(
                n_agents,
                2_000.0,
                span=span,
                compression_ratio=0.35,
            )
            telemetry_rows.append(
                {
                    "n_agents": n_agents,
                    "architecture": f"hierarchical_span_{span}",
                    "span": span,
                    "depth": result.depth,
                    "raw_rate_bps": result.raw_rate_bps,
                    "apex_rate_bps": result.apex_rate_bps,
                    "evidence_class": "analytic_under_notional_compression",
                }
            )

        issuer = size_issuer(n_agents, 300.0)
        credential_rows.append(
            {
                "n_agents": n_agents,
                "pairwise_keys": pairwise_key_count(n_agents),
                "certificate_issuance_rate_hz": certificate_issuance_rate(n_agents, 300.0),
                "issuer_capacity_with_factors_hz": issuer.required_capacity_per_s,
                "credential_ttl_s": 300.0,
                "evidence_class": "analytic",
            }
        )
        for span in (4, 8, 16):
            supervision_rows.append(
                {
                    "n_agents": n_agents,
                    "span": span,
                    "depth": supervisory_depth(n_agents, span),
                    "evidence_class": "analytic",
                }
            )
    return (
        pd.DataFrame(control_rows),
        pd.DataFrame(consensus_rows),
        pd.DataFrame(telemetry_rows),
        pd.DataFrame(credential_rows),
        pd.DataFrame(supervision_rows),
    )


def _timing_sweep() -> pd.DataFrame:
    rows = []
    one_way = fiber_propagation_delay(4_500.0)
    for epsilon in (20e-9, 1e-6, 1e-3, 100e-3):
        rows.append(
            {
                "clock_uncertainty_s": epsilon,
                "commit_wait_s": 2.0 * epsilon,
                "commit_wait_only_ceiling_tps": 1.0 / (2.0 * epsilon),
                "continental_one_way_floor_s": one_way,
                "continental_round_trip_floor_s": 2.0 * one_way,
                "three_phase_propagation_floor_s": 6.0 * one_way,
                "holdover_after_3600_s_at_1e_9_fractional_error_s": holdover_uncertainty(
                    3_600.0, epsilon, 1e-9
                ),
                "evidence_class": "analytic_under_stated_assumptions",
            }
        )
    return pd.DataFrame(rows)


def _usl_software_verification(replications: int, seed: int) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    n_values = np.asarray((1, 10, 100, 1_000, 10_000), dtype=float)
    true_scale = 120.0
    true_alpha = 0.018
    true_beta = 1.5e-6
    duration_s = 240.0
    expected = usl_capacity(n_values, true_alpha, true_beta, true_scale)
    seed_sequence = np.random.SeedSequence(seed)
    children = seed_sequence.spawn(replications)
    matrix = np.empty((len(n_values), replications), dtype=float)
    rows: list[dict[str, Any]] = []
    for replication, child in enumerate(children):
        rng = np.random.Generator(np.random.PCG64DXSM(child))
        counts = rng.poisson(expected * duration_s)
        throughput = counts / duration_s
        matrix[:, replication] = throughput
        for n_agents, value, count in zip(n_values.astype(int), throughput, counts):
            rows.append(
                {
                    "n_agents": int(n_agents),
                    "replication": replication,
                    "seed_entropy": seed,
                    "duration_s": duration_s,
                    "completion_count": int(count),
                    "throughput_hz": float(value),
                }
            )
    observations = pd.DataFrame(rows)
    fit = fit_usl(n_values, matrix.mean(axis=1))
    bootstrap = bootstrap_usl(n_values, matrix, seed=seed + 1, replications=500)
    curve_n = np.geomspace(1, 10_000, 250)
    fitted_curve = pd.DataFrame(
        {
            "n_agents": curve_n,
            "fitted_throughput_hz": usl_capacity(curve_n, fit.alpha, fit.beta, fit.scale),
        }
    )
    result = {
        "passed": (
            abs(fit.alpha - true_alpha) / true_alpha < 0.15
            and abs(fit.beta - true_beta) / true_beta < 0.20
        ),
        "purpose": "Software verification of the USL fitting path only.",
        "true_parameters": {
            "scale": true_scale,
            "alpha": true_alpha,
            "beta": true_beta,
            "n_star": math.sqrt((1.0 - true_alpha) / true_beta),
        },
        "fitted_parameters": {
            "scale": fit.scale,
            "alpha": fit.alpha,
            "beta": fit.beta,
            "n_star": fit.n_star,
            "r_squared": fit.r_squared,
            "rmse": fit.residual_rmse,
        },
        "bootstrap_95_percent_intervals": bootstrap,
    }
    return observations, fitted_curve, result


def _measurement_rows(
    queue_frame: pd.DataFrame,
    gossip_frame: pd.DataFrame,
    percolation_frame: pd.DataFrame,
    usl_observations: pd.DataFrame,
    integrated_summary: dict[str, Any],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for record in queue_frame.to_dict(orient="records"):
        rows.append(
            {
                "experiment": "mm1_queue_verification",
                "configuration": f"rho={record['rho']}",
                "replication": int(record["replication"]),
                "seed": int(record["seed"]),
                "metric": "mean_number_system",
                "value": float(record["simulated_mean_number_system"]),
                "evidence_class": "software_verification",
                "parameter_class": "analytically_fixed_queue_family",
            }
        )
        rows.append(
            {
                "experiment": "mm1_queue_verification",
                "configuration": f"rho={record['rho']}",
                "replication": int(record["replication"]),
                "seed": int(record["seed"]),
                "metric": "little_law_residual",
                "value": float(record["little_law_residual"]),
                "evidence_class": "software_verification",
                "parameter_class": "analytically_fixed_queue_family",
            }
        )

    for record in gossip_frame.to_dict(orient="records"):
        rows.append(
            {
                "experiment": "complete_graph_gossip_verification",
                "configuration": f"N={record['n_agents']};fanout=2;push_pull",
                "replication": int(record["replication"]),
                "seed": int(record["seed"]),
                "metric": "rounds_to_99_percent",
                "value": float(record["rounds_to_99_percent"]),
                "evidence_class": "software_verification",
                "parameter_class": "notional_protocol_parameters",
            }
        )

    for record in percolation_frame.to_dict(orient="records"):
        rows.append(
            {
                "experiment": "bond_percolation_verification",
                "configuration": f"{record['architecture']};q={record['q']}",
                "replication": int(record["replication"]),
                "seed": int(record["seed_family"]),
                "metric": "largest_component_fraction",
                "value": float(record["largest_component_fraction"]),
                "evidence_class": "numerically_demonstrated",
                "parameter_class": "notional_graph_realization",
            }
        )

    for record in usl_observations.to_dict(orient="records"):
        rows.append(
            {
                "experiment": "usl_fit_pipeline_verification",
                "configuration": f"N={record['n_agents']}",
                "replication": int(record["replication"]),
                "seed": int(record["seed_entropy"]),
                "metric": "throughput_hz",
                "value": float(record["throughput_hz"]),
                "evidence_class": "software_verification",
                "parameter_class": "synthetic_known_usl_process",
            }
        )

    integrated_metrics = {
        "useful_throughput_hz": integrated_summary["tasks"]["useful_throughput_hz"],
        "raw_throughput_hz": integrated_summary["tasks"]["raw_throughput_hz"],
        "latency_p95_s": integrated_summary["tasks"]["latency_s"]["p95"],
        "control_utilization": integrated_summary["control_plane"]["observed_utilization"],
        "blast_radius_fraction": integrated_summary["security"]["blast_radius_fraction"],
        "gossip_rounds": integrated_summary["gossip"]["rounds"],
        "event_count": integrated_summary["event_count"],
    }
    for metric, value in integrated_metrics.items():
        rows.append(
            {
                "experiment": "integrated_visual_replay",
                "configuration": integrated_summary["run_id"],
                "replication": 0,
                "seed": int(integrated_summary["seed"]),
                "metric": metric,
                "value": float(value),
                "evidence_class": "numerically_demonstrated_single_trace",
                "parameter_class": integrated_summary["parameter_class"],
            }
        )
    return pd.DataFrame(rows)


def _seed_manifest(
    queue_frame: pd.DataFrame,
    gossip_frame: pd.DataFrame,
    percolation_frame: pd.DataFrame,
    usl_observations: pd.DataFrame,
    integrated_seed: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for experiment, frame, seed_column in (
        ("mm1_queue_verification", queue_frame, "seed"),
        ("complete_graph_gossip_verification", gossip_frame, "seed"),
        ("bond_percolation_verification", percolation_frame, "seed_family"),
        ("usl_fit_pipeline_verification", usl_observations, "seed_entropy"),
    ):
        for record in frame[["replication", seed_column]].drop_duplicates().to_dict(orient="records"):
            rows.append(
                {
                    "experiment": experiment,
                    "replication": int(record["replication"]),
                    "seed": int(record[seed_column]),
                }
            )
    rows.append(
        {
            "experiment": "integrated_visual_replay",
            "replication": 0,
            "seed": int(integrated_seed),
        }
    )
    return pd.DataFrame(rows).sort_values(["experiment", "replication", "seed"])


def _write_stage0_markdown(report: dict[str, Any], path: Path) -> Path:
    integrated = report["integrated_replay"]
    checks = report["checks"]
    check_lines = "\n".join(
        f"- {item['name']}: **{'PASS' if item['passed'] else 'FAIL'}**"
        for item in checks
    )
    text = f"""# Stage 0 Verification and Visual Simulation Report

## Status

This report documents the first executable increment of the secure multi-agent fleet scaling study. It establishes a deterministic simulation kernel, analytic baseline models, stochastic software-verification checks, immutable event logging, exact replay, and an offline visual console. It does not establish secure operation at any fleet size.

Overall Stage 0 status: **{'PASS' if report['overall_passed'] else 'FAIL'}**

## Acceptance summary

{check_lines}

## Integrated replay result

The integrated run used **N = {integrated['n_agents']}** agents and a notional parameter set. It emitted **{integrated['event_count']}** canonical events. The execution final-state hash was `{integrated['final_state_hash']}` and the replay hash was `{integrated['replay_state_hash']}`. The repeated execution produced the same event-log digest and final-state hash: **{'yes' if integrated['seed_determinism'] else 'no'}**.

The self-contained visual console consumes the canonical event and graph artifacts. It supports event stepping, playback, communication and authorization graph overlays, queue behavior, compromise and containment, timing degradation, credential operations, and node inspection.

## Scientific classification

The queue, gossip, percolation, and USL recovery experiments are software-verification evidence. The scale tables and physical-limit calculations are analytic results under stated assumptions. The integrated trace is numerically demonstrated only for its specific notional configuration and seed. No result in this increment is operationally measured evidence.

## Material limitations

1. The integrated scenario is one deterministic trace, not a statistically supported architecture comparison.
2. The full staged experiment matrix and the controlled tests of H1 through H7 have not been executed.
3. The current security process is a finite SIR-like abstraction. It does not yet compose communication, authorization, dependency, supervisory, and exploit-condition layers into a complete attack-reachability graph.
4. The browser application is generated from replay data, but automated browser-state equivalence and large-N frame-rate qualification remain open.
5. Sobol sensitivity analysis and Parquet output remain open until their compatible dependencies and schemas are included in the pinned environment.
6. Workload, adversary, cost, energy, detection, and credential-capacity inputs in the integrated run are notional.

## Open acceptance gates

""" + "\n".join(f"- {item}" for item in report["open_gates"]) + """

## What This Study Does Not Establish

A discrete-event simulation establishes the behavior of a model. Its findings transfer to a real deployment only to the degree that the model's assumptions hold. This study cannot establish that any particular implementation is secure. It establishes structural constraints: which architectures are ruled out by mathematics and physics, and which remain candidates. Ruling out is stronger than ruling in. An architecture that violates the epidemic threshold condition or exceeds the observability ceiling is provably unmanageable at the stated scale. An architecture that satisfies every constraint identified here is merely not yet ruled out, and still requires adversarial testing, formal verification of critical components, and operational evaluation before deployment.

The phrase "unlimited agents" should be retired in favor of the precise finding this study will produce: fleets scale without bound only along axes where required coordination is O(1) or O(log N) in fleet size, and every remaining axis has a computable ceiling.

The preceding paragraph is required scope language. In this Stage 0 increment, the epidemic threshold is a model-specific approximation and the observability ceiling is conditional on a specified source, distortion metric, and channel model. Neither has yet been used to rule out a production architecture.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run_stage0(
    repository_root: str | Path,
    output_root: str | Path,
    replications: int = 30,
) -> dict[str, Any]:
    """Execute Stage 0 checks and generate the first durable artifact set."""

    if replications < 3:
        raise ValueError("Stage 0 requires at least three replications")
    repository = Path(repository_root).resolve()
    output = Path(output_root).resolve()
    results_dir = output / "results" / "stage0"
    figures_dir = output / "figures" / "stage0"
    manifests_dir = output / "manifests"
    paper_dir = output / "paper"
    for directory in (results_dir, figures_dir, manifests_dir, paper_dir):
        directory.mkdir(parents=True, exist_ok=True)

    started = time.time()
    checks: list[dict[str, Any]] = []

    registry_path = repository / "configs" / "parameters" / "registry.yaml"
    try:
        parameter_records = load_parameter_registry(registry_path)
        registry_check = {
            "name": "parameter_registry_validation",
            "passed": True,
            "parameter_records": len(parameter_records),
            "evidence_class": "software_verification",
        }
    except Exception as exc:
        registry_check = {
            "name": "parameter_registry_validation",
            "passed": False,
            "error": str(exc),
            "evidence_class": "software_verification",
        }
    checks.append(registry_check)

    pytest_result = _run_pytest(repository)
    checks.append(
        {
            "name": "automated_pytest_suite",
            "passed": pytest_result["passed"],
            "stdout": pytest_result["stdout"],
            "stderr": pytest_result["stderr"],
            "wall_clock_s": pytest_result["wall_clock_s"],
            "evidence_class": "software_verification",
        }
    )

    queue_frame, queue_result = _queue_verification(replications, seed=73_001)
    queue_path = results_dir / "queue_verification.csv"
    queue_frame.to_csv(queue_path, index=False)
    queue_figure = queue_verification_figure(queue_frame, figures_dir / "queue_verification.png")
    queue_result.update(
        {
            "name": "mm1_and_little_law_verification",
            "evidence_class": "analytic_and_numerical_comparison",
            "replications_per_utilization": replications,
            "artifact": str(queue_figure),
        }
    )
    checks.append(queue_result)

    gossip_frame, gossip_result = _gossip_verification(replications, seed=73_101)
    gossip_path = results_dir / "gossip_verification.csv"
    gossip_frame.to_csv(gossip_path, index=False)
    gossip_figure = gossip_scaling_figure(gossip_frame, figures_dir / "gossip_scaling.png")
    gossip_result.update(
        {
            "name": "gossip_logarithmic_growth_verification",
            "evidence_class": "numerically_demonstrated",
            "replications_per_n": replications,
            "artifact": str(gossip_figure),
        }
    )
    checks.append(gossip_result)

    percolation_frame, percolation_result = _percolation_verification(replications, seed=73_201)
    percolation_path = results_dir / "percolation_verification.csv"
    percolation_frame.to_csv(percolation_path, index=False)
    percolation_plot = percolation_figure(
        percolation_frame,
        figures_dir / "percolation_blast_radius.png",
    )
    percolation_result.update(
        {
            "name": "percolation_segmentation_direction_verification",
            "evidence_class": "analytic_approximation_and_numerical_distribution",
            "replications_per_q": replications,
            "artifact": str(percolation_plot),
        }
    )
    checks.append(percolation_result)

    control_frame, consensus_frame, telemetry_frame, credential_frame, supervision_frame = _analytic_scale_tables()
    control_path = results_dir / "control_plane_scale.csv"
    consensus_path = results_dir / "consensus_scale.csv"
    telemetry_path = results_dir / "telemetry_scale.csv"
    credential_path = results_dir / "credential_scale.csv"
    supervision_path = results_dir / "supervision_scale.csv"
    control_frame.to_csv(control_path, index=False)
    consensus_frame.to_csv(consensus_path, index=False)
    telemetry_frame.to_csv(telemetry_path, index=False)
    credential_frame.to_csv(credential_path, index=False)
    supervision_frame.to_csv(supervision_path, index=False)

    timing_frame = _timing_sweep()
    timing_path = results_dir / "timing_sweep.csv"
    timing_frame.to_csv(timing_path, index=False)

    usl_observations, usl_curve, usl_result = _usl_software_verification(replications, seed=73_301)
    usl_observations_path = results_dir / "usl_verification_observations.csv"
    usl_curve_path = results_dir / "usl_verification_curve.csv"
    usl_observations.to_csv(usl_observations_path, index=False)
    usl_curve.to_csv(usl_curve_path, index=False)
    usl_plot = usl_verification_figure(
        usl_observations,
        usl_curve,
        figures_dir / "usl_fit_verification.png",
    )
    usl_result.update(
        {
            "name": "usl_fitting_pipeline_verification",
            "evidence_class": "software_verification",
            "replications_per_n": replications,
            "artifact": str(usl_plot),
        }
    )
    checks.append(usl_result)

    integrated_config = load_config(repository / "configs" / "experiments" / "stage0_demo.yaml")
    integrated_artifacts = FleetSimulator(integrated_config, repository).run(output)
    console_path = build_console(
        integrated_artifacts.bundle_dir,
        integrated_artifacts.bundle_dir / "virtual_fleet_assurance_console.html",
    )
    topology_path = export_final_topology(
        integrated_artifacts.bundle_dir,
        figures_dir / "integrated_final_topology.png",
    )
    integrated_summary = json.loads(integrated_artifacts.summary_path.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory(prefix="fleet-stage0-repeat-") as temporary:
        repeated = FleetSimulator(integrated_config, repository).run(Path(temporary))
        seed_determinism = bool(
            repeated.event_log_digest == integrated_artifacts.event_log_digest
            and repeated.final_state_hash == integrated_artifacts.final_state_hash
        )

    required_event_types = {
        "SIMULATION_START",
        "SIMULATION_END",
        "TASK_ARRIVAL",
        "AUTH_DECISION",
        "GOSSIP_ROUND",
        "COMPROMISE",
        "DETECTION",
        "QUARANTINE",
        "REVOCATION",
        "RECOVERY",
        "TIMING_UPDATE",
        "CREDENTIAL_RENEWAL",
        "CREDENTIAL_REVOCATION_STORM_START",
        "CREDENTIAL_REVOCATION_STORM_END",
    }
    observed_event_types = set(integrated_summary["event_counts_by_type"])
    missing_event_types = sorted(required_event_types - observed_event_types)
    replay_verified = bool(
        integrated_artifacts.final_state_hash == integrated_artifacts.replay_state_hash
        and integrated_summary["replay_validation"]["passed"]
    )
    integrated_check = {
        "name": "integrated_simulation_replay_and_visualization_verification",
        "passed": bool(
            replay_verified
            and seed_determinism
            and not missing_event_types
            and Path(console_path).exists()
            and Path(topology_path).exists()
        ),
        "evidence_class": "software_verification_and_numerical_demonstration",
        "run_id": integrated_artifacts.run_id,
        "n_agents": integrated_summary["n_agents"],
        "event_count": integrated_summary["event_count"],
        "event_log_digest": integrated_artifacts.event_log_digest,
        "final_state_hash": integrated_artifacts.final_state_hash,
        "replay_state_hash": integrated_artifacts.replay_state_hash,
        "replay_equivalence": replay_verified,
        "seed_determinism": seed_determinism,
        "missing_required_event_types": missing_event_types,
        "bundle_dir": str(integrated_artifacts.bundle_dir),
        "console_html": str(console_path),
        "static_topology": str(topology_path),
    }
    checks.append(integrated_check)

    figure_paths = [
        queue_figure,
        gossip_figure,
        percolation_plot,
        consensus_scaling_figure(consensus_frame, figures_dir / "consensus_message_scaling.png"),
        telemetry_scaling_figure(telemetry_frame, figures_dir / "telemetry_ingest_scaling.png"),
        timing_sweep_figure(timing_frame, figures_dir / "timing_assurance_sweep.png"),
        credential_scaling_figure(credential_frame, figures_dir / "credential_scaling.png"),
        usl_plot,
        topology_path,
    ]
    figure_manifest = write_figure_manifest(figure_paths, figures_dir / "figure_manifest.csv")

    measurements = _measurement_rows(
        queue_frame,
        gossip_frame,
        percolation_frame,
        usl_observations,
        integrated_summary,
    )
    measurements_path = results_dir / "stage0_measurements.csv"
    measurements.to_csv(measurements_path, index=False)

    seed_manifest = _seed_manifest(
        queue_frame,
        gossip_frame,
        percolation_frame,
        usl_observations,
        integrated_config.seed,
    )
    seed_manifest_path = manifests_dir / "stage0_seed_manifest.csv"
    seed_manifest.to_csv(seed_manifest_path, index=False)

    physical_limits = {
        "fiber_one_way_4500_km_s": fiber_propagation_delay(4_500.0),
        "fiber_round_trip_4500_km_s": 2.0 * fiber_propagation_delay(4_500.0),
        "landauer_energy_per_bit_at_300_k_j": landauer_energy_per_bit(300.0),
        "classification": "analytic_under_stated_assumptions",
    }

    open_gates = [
        "Full staged design of experiments",
        "Controlled architecture comparisons with at least 30 independent replications",
        "Sobol global sensitivity analysis with a compatible sampling design",
        "Parquet result output and schema validation",
        "Mean-field approximation validation before relying on N above 10,000",
        "All twelve predefined replay scenarios",
        "Dependency, supervisory, and dynamic attack-reachability graph composition",
        "Full adversary suite, including Dolev-Yao, Byzantine, insider, supply-chain, instruction-channel, and Sybil models",
        "Automated browser-state equivalence and large-N rendering qualification",
        "Technical paper, decision table, and evidence-derived candidate reference architecture",
    ]

    report: dict[str, Any] = {
        "stage": "Stage 0: analytic and software verification",
        "version": "0.1.0",
        "generated_unix": time.time(),
        "replications": replications,
        "checks": checks,
        "pytest": pytest_result,
        "queue_verification": queue_result,
        "gossip_verification": gossip_result,
        "percolation_verification": percolation_result,
        "usl_verification": usl_result,
        "physical_limits": physical_limits,
        "integrated_replay": integrated_check,
        "integrated_summary": integrated_summary,
        "datasets": {
            "measurements": str(measurements_path),
            "seed_manifest": str(seed_manifest_path),
            "queue": str(queue_path),
            "gossip": str(gossip_path),
            "percolation": str(percolation_path),
            "control_plane": str(control_path),
            "consensus": str(consensus_path),
            "telemetry": str(telemetry_path),
            "credentials": str(credential_path),
            "supervision": str(supervision_path),
            "timing": str(timing_path),
            "usl_observations": str(usl_observations_path),
            "usl_curve": str(usl_curve_path),
        },
        "figures": [str(path) for path in figure_paths],
        "figure_manifest": str(figure_manifest),
        "open_gates": open_gates,
        "limitations": [
            "The integrated scenario uses notional parameters.",
            "Stage 0 verifies implementation behavior and known baselines, not deployment assurance.",
            "The full architecture experiment matrix and sensitivity analysis have not been executed.",
            "No production reference architecture is recommended by this increment.",
        ],
    }
    report["overall_passed"] = bool(all(item["passed"] for item in checks))
    report["wall_clock_s"] = time.time() - started

    report_path = results_dir / "stage0_report.json"
    markdown_path = paper_dir / "stage0_verification_report.md"
    report["report_path"] = str(report_path)
    report["paper_path"] = str(markdown_path)
    _write_stage0_markdown(report, markdown_path)
    _json_write(report_path, report)
    return report
