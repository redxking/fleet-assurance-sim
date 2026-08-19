"""Publication-oriented Stage 0 figures.

Every figure produced here is labeled as analytic, software verification, or
numerically demonstrated under notional parameters. None is operational data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _destination(path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def _save(figure: plt.Figure, path: str | Path) -> Path:
    destination = _destination(path)
    figure.tight_layout()
    figure.savefig(destination, dpi=200, bbox_inches="tight")
    plt.close(figure)
    return destination


def queue_verification_figure(frame: pd.DataFrame, path: str | Path) -> Path:
    grouped = frame.groupby("rho", sort=True)
    rho = np.array(sorted(grouped.groups), dtype=float)
    analytic_l = np.array([grouped.get_group(value)["analytic_mean_number_system"].iloc[0] for value in rho])
    simulated_l = np.array([grouped.get_group(value)["simulated_mean_number_system"].mean() for value in rho])
    low = np.array([grouped.get_group(value)["simulated_mean_number_system"].quantile(0.025) for value in rho])
    high = np.array([grouped.get_group(value)["simulated_mean_number_system"].quantile(0.975) for value in rho])

    figure, axis = plt.subplots(figsize=(9, 5.5))
    axis.plot(rho, analytic_l, marker="o", label="Analytic M/M/1")
    axis.plot(rho, simulated_l, marker="s", label="Simulation mean")
    axis.fill_between(rho, low, high, alpha=0.2, label="Replication 2.5 to 97.5 percent range")
    axis.set_xlabel("Utilization, rho")
    axis.set_ylabel("Mean number in system, L")
    axis.set_title("Stage 0 queue verification and utilization cliff")
    axis.grid(True, alpha=0.25)
    axis.legend()
    axis.text(
        0.01,
        0.01,
        "Software verification only. Poisson arrivals and exponential service.",
        transform=axis.transAxes,
        fontsize=8,
    )
    return _save(figure, path)


def gossip_scaling_figure(frame: pd.DataFrame, path: str | Path) -> Path:
    grouped = frame.groupby("n_agents", sort=True)["rounds_to_99_percent"]
    summary = grouped.agg(["mean", "std", "count"]).reset_index()
    ci = 1.96 * summary["std"].fillna(0.0) / np.sqrt(summary["count"])

    figure, axis = plt.subplots(figsize=(9, 5.5))
    axis.errorbar(
        summary["n_agents"],
        summary["mean"],
        yerr=ci,
        marker="o",
        capsize=4,
        label="Push-pull gossip simulation, mean and approximate 95 percent CI",
    )
    n = summary["n_agents"].to_numpy(dtype=float)
    coefficient = np.polyfit(np.log2(n), summary["mean"].to_numpy(dtype=float), 1)
    axis.plot(n, np.polyval(coefficient, np.log2(n)), linestyle="--", label="Linear fit versus log2(N)")
    axis.set_xscale("log")
    axis.set_xlabel("Fleet size, N")
    axis.set_ylabel("Rounds to at least 99 percent coverage")
    axis.set_title("Stage 0 dissemination verification")
    axis.grid(True, which="both", alpha=0.25)
    axis.legend()
    axis.text(
        0.01,
        0.01,
        "Complete communication graph, fanout 2, notional zero-loss verification case.",
        transform=axis.transAxes,
        fontsize=8,
    )
    return _save(figure, path)


def percolation_figure(frame: pd.DataFrame, path: str | Path) -> Path:
    figure, axis = plt.subplots(figsize=(9, 5.5))
    for architecture, group in frame.groupby("architecture", sort=True):
        summary = group.groupby("q")["largest_component_fraction"].agg(
            mean="mean",
            low=lambda values: values.quantile(0.025),
            high=lambda values: values.quantile(0.975),
        ).reset_index()
        axis.plot(summary["q"], summary["mean"], marker="o", label=f"{architecture} mean")
        axis.fill_between(summary["q"], summary["low"], summary["high"], alpha=0.18)
    axis.set_xlabel("Authorization-boundary traversal probability, q")
    axis.set_ylabel("Largest reachable component as fleet fraction")
    axis.set_title("Stage 0 bond-percolation blast-radius comparison")
    axis.grid(True, alpha=0.25)
    axis.legend()
    axis.text(
        0.01,
        0.01,
        "Notional graph experiment. Shaded regions are replication quantiles, not deployment confidence.",
        transform=axis.transAxes,
        fontsize=8,
    )
    return _save(figure, path)


def consensus_scaling_figure(frame: pd.DataFrame, path: str | Path) -> Path:
    figure, axis = plt.subplots(figsize=(9, 5.5))
    for protocol, group in frame.groupby("protocol", sort=True):
        ordered = group.sort_values("n_agents")
        axis.plot(ordered["n_agents"], ordered["messages"], marker="o", label=protocol)
    axis.set_xscale("log")
    axis.set_yscale("log")
    axis.set_xlabel("Fleet size or participating committee size, N")
    axis.set_ylabel("Messages per ordered operation")
    axis.set_title("Analytic consensus message-growth comparison")
    axis.grid(True, which="both", alpha=0.25)
    axis.legend()
    axis.text(
        0.01,
        0.01,
        "Analytic accounting. Bounded committee uses a fixed 31-member committee plus dissemination.",
        transform=axis.transAxes,
        fontsize=8,
    )
    return _save(figure, path)


def telemetry_scaling_figure(frame: pd.DataFrame, path: str | Path) -> Path:
    figure, axis = plt.subplots(figsize=(9, 5.5))
    flat = frame[frame["architecture"] == "flat"].sort_values("n_agents")
    axis.plot(flat["n_agents"], flat["apex_rate_bps"], marker="o", linewidth=2, label="Flat ingest")
    for architecture, group in frame[frame["architecture"] != "flat"].groupby("architecture", sort=True):
        ordered = group.sort_values("n_agents")
        axis.plot(ordered["n_agents"], ordered["apex_rate_bps"], marker="o", label=architecture)
    axis.set_xscale("log")
    axis.set_yscale("log")
    axis.set_xlabel("Fleet size, N")
    axis.set_ylabel("Apex ingest rate, bits per second")
    axis.set_title("Analytic observability transport scaling")
    axis.grid(True, which="both", alpha=0.25)
    axis.legend()
    axis.text(
        0.01,
        0.01,
        "Notional 2,000 bit/s per agent and 0.35 per-layer compression ratio.",
        transform=axis.transAxes,
        fontsize=8,
    )
    return _save(figure, path)


def timing_sweep_figure(frame: pd.DataFrame, path: str | Path) -> Path:
    ordered = frame.sort_values("clock_uncertainty_s")
    figure, axis = plt.subplots(figsize=(9, 5.5))
    axis.plot(ordered["clock_uncertainty_s"], ordered["commit_wait_only_ceiling_tps"], marker="o")
    axis.set_xscale("log")
    axis.set_yscale("log")
    axis.set_xlabel("Clock uncertainty epsilon, seconds")
    axis.set_ylabel("Single-lane commit-wait-only ceiling, transactions per second")
    axis.set_title("Analytic timing-assurance sensitivity")
    axis.grid(True, which="both", alpha=0.25)
    axis.text(
        0.01,
        0.01,
        "This ceiling is a special unpipelined case, not a universal fleet throughput law.",
        transform=axis.transAxes,
        fontsize=8,
    )
    return _save(figure, path)


def credential_scaling_figure(frame: pd.DataFrame, path: str | Path) -> Path:
    ordered = frame.sort_values("n_agents")
    figure, axis = plt.subplots(figsize=(9, 5.5))
    axis.plot(ordered["n_agents"], ordered["pairwise_keys"], marker="o", label="Pairwise symmetric keys")
    axis.plot(ordered["n_agents"], ordered["certificate_issuance_rate_hz"], marker="s", label="Certificates per second, TTL 300 s")
    axis.set_xscale("log")
    axis.set_yscale("log")
    axis.set_xlabel("Fleet size, N")
    axis.set_ylabel("Count or operations per second")
    axis.set_title("Analytic credential and key-management scaling")
    axis.grid(True, which="both", alpha=0.25)
    axis.legend()
    return _save(figure, path)


def usl_verification_figure(
    observations: pd.DataFrame,
    fitted_curve: pd.DataFrame,
    path: str | Path,
) -> Path:
    summary = observations.groupby("n_agents")["throughput_hz"].agg(["mean", "std", "count"]).reset_index()
    ci = 1.96 * summary["std"].fillna(0.0) / np.sqrt(summary["count"])
    figure, axis = plt.subplots(figsize=(9, 5.5))
    axis.errorbar(summary["n_agents"], summary["mean"], yerr=ci, marker="o", capsize=4, label="Poisson-counting simulation")
    axis.plot(fitted_curve["n_agents"], fitted_curve["fitted_throughput_hz"], label="Fitted USL")
    axis.set_xscale("log")
    axis.set_xlabel("Concurrency, N")
    axis.set_ylabel("Useful completions per second")
    axis.set_title("USL fitting-pipeline software verification")
    axis.grid(True, which="both", alpha=0.25)
    axis.legend()
    axis.text(
        0.01,
        0.01,
        "Generated from a known USL counting process. This verifies recovery, not an architecture claim.",
        transform=axis.transAxes,
        fontsize=8,
    )
    return _save(figure, path)


def write_figure_manifest(paths: Iterable[Path], output_path: str | Path) -> Path:
    destination = _destination(output_path)
    rows = [{"figure": path.name, "path": str(path), "exists": path.exists()} for path in paths]
    pd.DataFrame(rows).to_csv(destination, index=False)
    return destination
