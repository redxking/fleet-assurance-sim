"""Stage 1 novelty-driven research experiments.

This module deliberately separates three evidence levels:

1. harness verification: a synthetic or model-internal experiment behaves as designed;
2. model-conditioned demonstration: a hypothesis is supported inside the declared model;
3. external validation: requires measured or independently sourced real-system evidence.

No function in this module claims external validation.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from math import exp
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import spearmanr

from fleet_sim.graphs.factory import GraphBundle, build_graph, spectral_radius


@dataclass(frozen=True)
class Stage1Result:
    hypothesis: str
    evidence_level: str
    supported_in_model: bool
    primary_metric: float
    baseline_metric: float
    notes: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _roc_auc(y_true: np.ndarray, scores: np.ndarray) -> float:
    """Compute ROC AUC from ranks without adding a machine-learning dependency."""
    y = np.asarray(y_true, dtype=int)
    s = np.asarray(scores, dtype=float)
    pos = y == 1
    neg = y == 0
    n_pos = int(pos.sum())
    n_neg = int(neg.sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    # Stable average-rank handling for ties.
    order = np.argsort(s, kind="mergesort")
    sorted_s = s[order]
    ranks = np.empty(len(s), dtype=float)
    start = 0
    while start < len(s):
        end = start + 1
        while end < len(s) and sorted_s[end] == sorted_s[start]:
            end += 1
        avg_rank = (start + 1 + end) / 2.0
        ranks[order[start:end]] = avg_rank
        start = end
    rank_sum_pos = float(ranks[pos].sum())
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def _fit_logistic(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Fit a small L2-regularized logistic model using SciPy."""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    X1 = np.column_stack([np.ones(len(X)), X])

    def objective(w: np.ndarray) -> tuple[float, np.ndarray]:
        z = np.clip(X1 @ w, -35.0, 35.0)
        p = 1.0 / (1.0 + np.exp(-z))
        eps = 1e-12
        loss = -np.sum(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))
        reg = 1e-3 * np.sum(w[1:] ** 2)
        grad = X1.T @ (p - y)
        grad[1:] += 2e-3 * w[1:]
        return float(loss + reg), grad

    result = minimize(
        lambda w: objective(w)[0],
        np.zeros(X1.shape[1]),
        jac=lambda w: objective(w)[1],
        method="BFGS",
    )
    return np.asarray(result.x, dtype=float)


def _predict_logistic(X: np.ndarray, w: np.ndarray) -> np.ndarray:
    X1 = np.column_stack([np.ones(len(X)), np.asarray(X, dtype=float)])
    z = np.clip(X1 @ w, -35.0, 35.0)
    return 1.0 / (1.0 + np.exp(-z))


def _dynamic_assurance_outcome(
    x: np.ndarray,
    *,
    n_agents: int,
    rng: np.random.Generator,
) -> tuple[int, float, dict[str, float]]:
    """Evaluate a stylized coupled assurance model.

    x order:
      control, containment, observability, supervision, revocation, timing,
      inverse mission throughput ratio.

    The exogenous ratios are perturbed by endogenous effects. These equations are
    notional and exist to verify that Stage 1 can detect and generalize coupling.
    """
    cp, contain, obs, sup, rev, timing, mission_inv = map(float, x)

    # Evidence loss slows detection. The penalty is smooth and monotone.
    evidence_penalty = max(1.0, obs)
    effective_containment = contain * evidence_penalty

    # Convert containment stress to expected active compromise pressure.
    compromise_pressure = 1.0 / (1.0 + np.exp(-5.0 * (effective_containment - 0.92)))
    # Correlated perturbation models scenario variability, not measurement noise.
    compromise_pressure = float(np.clip(compromise_pressure + rng.normal(0.0, 0.025), 0.0, 1.0))

    # Compromise generates revocation work; revocation work consumes control-plane capacity.
    rev_dynamic = rev + 0.42 * compromise_pressure
    cp_dynamic = cp + 0.34 * max(0.0, rev_dynamic - 0.55) + 0.08 * max(0.0, obs - 0.8)

    # Compromise and degraded evidence both increase supervisory demand.
    sup_dynamic = sup + 0.30 * compromise_pressure + 0.12 * max(0.0, obs - 0.75)

    # Timing degradation can increase retry/ordering overhead, reducing mission yield.
    mission_dynamic = mission_inv + 0.16 * max(0.0, timing - 0.65) + 0.10 * max(0.0, cp_dynamic - 0.75)

    # A fleet is declared failed if an operational constraint crosses 1.0 or if
    # active compromise pressure exceeds a notional mission threshold.
    failure = int(
        cp_dynamic > 1.0
        or effective_containment > 1.0
        or obs > 1.0
        or sup_dynamic > 1.0
        or rev_dynamic > 1.0
        or timing > 1.0
        or mission_dynamic > 1.0
        or compromise_pressure > 0.58
    )
    severity = max(
        cp_dynamic,
        effective_containment,
        obs,
        sup_dynamic,
        rev_dynamic,
        timing,
        mission_dynamic,
        compromise_pressure / 0.58,
    )
    details = {
        "cp_dynamic": cp_dynamic,
        "contain_dynamic": effective_containment,
        "obs": obs,
        "sup_dynamic": sup_dynamic,
        "rev_dynamic": rev_dynamic,
        "timing": timing,
        "mission_dynamic": mission_dynamic,
        "compromise_pressure": compromise_pressure,
        "n_agents": float(n_agents),
    }
    return failure, float(severity), details


def run_nh1_coupled_envelope(
    *,
    seed: int = 20260819,
    n_samples: int = 1200,
    n_agents: int = 10_000,
) -> tuple[pd.DataFrame, Stage1Result, dict[str, float]]:
    """NH1: compare independent ceilings with a learned coupled boundary.

    Parameter-space split is geometric, not random: samples with high observability
    and revocation stress are preferentially held out so generalization is harder.
    """
    rng = np.random.default_rng(seed)
    X = rng.uniform(0.35, 1.18, size=(n_samples, 7))
    rows: list[dict[str, float | int | str]] = []
    for i, x in enumerate(X):
        fail, severity, details = _dynamic_assurance_outcome(x, n_agents=n_agents, rng=rng)
        # Independent-ceiling baseline ignores endogenous interaction.
        baseline_score = float(np.max(x))
        # Geometric held-out wedge plus calibration band.
        if 0.65 < x[2] < 1.00 and 0.55 < x[4] < 0.95 and x[0] < 0.95:
            split = "test"
        elif 0.84 < np.max(x) < 1.03 and (i % 3 == 0):
            split = "calibration"
        else:
            split = "train"
        row: dict[str, float | int | str] = {
            "sample_id": i,
            "split": split,
            "failure": fail,
            "realized_severity": severity,
            "baseline_score": baseline_score,
        }
        names = ["cp", "contain", "obs", "sup", "rev", "timing", "mission_inv"]
        row.update({name: float(value) for name, value in zip(names, x)})
        row.update(details)
        rows.append(row)
    df = pd.DataFrame(rows)

    features = ["cp", "contain", "obs", "sup", "rev", "timing", "mission_inv"]
    # Candidate coupled model includes only pre-declared interactions, not arbitrary polynomial expansion.
    def matrix(frame: pd.DataFrame) -> np.ndarray:
        base = frame[features].to_numpy(float)
        interactions = np.column_stack(
            [
                frame["obs"].to_numpy() * frame["contain"].to_numpy(),
                frame["contain"].to_numpy() * frame["rev"].to_numpy(),
                frame["rev"].to_numpy() * frame["cp"].to_numpy(),
                frame["obs"].to_numpy() * frame["sup"].to_numpy(),
                frame["timing"].to_numpy() * frame["mission_inv"].to_numpy(),
            ]
        )
        return np.column_stack([base, interactions])

    train = df[df.split == "train"]
    test = df[df.split == "test"]
    w = _fit_logistic(matrix(train), train.failure.to_numpy())
    coupled_score = _predict_logistic(matrix(test), w)
    baseline_score = test.baseline_score.to_numpy()
    y = test.failure.to_numpy()
    auc_coupled = _roc_auc(y, coupled_score)
    auc_baseline = _roc_auc(y, baseline_score)
    brier_coupled = float(np.mean((coupled_score - y) ** 2))
    # Convert baseline margin to a soft probability for Brier comparison.
    p_base = 1.0 / (1.0 + np.exp(-10.0 * (baseline_score - 1.0)))
    brier_baseline = float(np.mean((p_base - y) ** 2))
    df.loc[test.index, "coupled_score"] = coupled_score
    df.loc[test.index, "baseline_probability"] = p_base

    supported = bool(auc_coupled > auc_baseline + 0.02 and brier_coupled < brier_baseline)
    result = Stage1Result(
        hypothesis="NH1",
        evidence_level="model-conditioned demonstration",
        supported_in_model=supported,
        primary_metric=float(auc_coupled),
        baseline_metric=float(auc_baseline),
        notes=(
            "Held-out geometric region. Support requires coupled AUC to exceed the independent-ceiling "
            "baseline by >0.02 and coupled Brier score to improve. Parameters are notional."
        ),
    )
    metrics = {
        "auc_coupled": float(auc_coupled),
        "auc_independent": float(auc_baseline),
        "brier_coupled": brier_coupled,
        "brier_independent": brier_baseline,
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "failure_rate_test": float(y.mean()) if len(y) else float("nan"),
    }
    return df, result, metrics


def _weighted_attack_operator(
    g_auth: nx.Graph,
    g_comm: nx.Graph,
    g_dep: nx.Graph,
    g_sup: nx.Graph,
    *,
    w_auth: float = 0.60,
    w_comm: float = 0.10,
    w_dep: float = 0.22,
    w_sup: float = 0.08,
) -> nx.Graph:
    """Build a weighted, undirected attack-reachability graph for Stage 1.

    Weights are notional exploit/authority-transfer intensities. The operator is a
    candidate construct, not a validated security metric.
    """
    nodes = sorted(set(g_auth) | set(g_comm) | set(g_dep) | set(g_sup))
    gx = nx.Graph()
    gx.add_nodes_from(nodes)
    for graph, weight in ((g_auth, w_auth), (g_comm, w_comm), (g_dep, w_dep), (g_sup, w_sup)):
        for u, v in graph.edges():
            if gx.has_edge(u, v):
                gx[u][v]["weight"] += weight
            else:
                gx.add_edge(u, v, weight=weight)
    for u, v, data in gx.edges(data=True):
        data["weight"] = min(1.0, float(data["weight"]))
    return gx


def _weighted_spectral_radius(graph: nx.Graph) -> float:
    if graph.number_of_nodes() <= 1 or graph.number_of_edges() == 0:
        return 0.0
    a = nx.to_numpy_array(graph, weight="weight", dtype=float)
    vals = np.linalg.eigvalsh(a)
    return float(np.max(vals))


def _simulate_weighted_sir(
    graph: nx.Graph,
    *,
    beta: float,
    gamma: float,
    seed: int,
    max_steps: int = 120,
) -> tuple[float, float, int]:
    rng = np.random.default_rng(seed)
    nodes = list(graph.nodes())
    if not nodes:
        return 0.0, 0.0, 0
    patient_zero = nodes[int(rng.integers(0, len(nodes)))]
    infected = {patient_zero}
    recovered: set[int] = set()
    peak = len(infected)
    ever = set(infected)
    for step in range(max_steps):
        new_inf: set[int] = set()
        new_rec: set[int] = set()
        for u in list(infected):
            for v in graph.neighbors(u):
                if v in infected or v in recovered:
                    continue
                weight = float(graph[u][v].get("weight", 1.0))
                p = 1.0 - exp(-beta * weight)
                if rng.random() < p:
                    new_inf.add(v)
            if rng.random() < 1.0 - exp(-gamma):
                new_rec.add(u)
        infected = (infected | new_inf) - new_rec
        recovered |= new_rec
        ever |= new_inf
        peak = max(peak, len(infected))
        if not infected:
            return peak / len(nodes), len(ever) / len(nodes), step + 1
    return peak / len(nodes), len(ever) / len(nodes), max_steps


def run_nh2_attack_reachability(
    *,
    seed: int = 20260819,
    n: int = 220,
    replications: int = 30,
) -> tuple[pd.DataFrame, Stage1Result, dict[str, float]]:
    """NH2: compare raw authorization spectrum with a dynamic attack operator.

    Held-out test cases are topology combinations not used for calibration.
    """
    rng = np.random.default_rng(seed)
    topology_specs = [
        ("random_regular", {"degree": 4}),
        ("random_regular", {"degree": 8}),
        ("erdos_renyi", {"degree": 4}),
        ("erdos_renyi", {"degree": 8}),
        ("barabasi_albert", {"attachment": 2}),
        ("barabasi_albert", {"attachment": 4}),
        ("hierarchical", {"span": 4}),
        ("hierarchical", {"span": 8}),
    ]
    rows: list[dict[str, float | int | str]] = []
    scenario_id = 0
    for a_idx, (a_top, a_kw) in enumerate(topology_specs):
        for d_idx, (d_top, d_kw) in enumerate(topology_specs[::2]):
            graph_seed = int(rng.integers(1, 2**31 - 1))
            auth_b = build_graph(n, a_top, seed=graph_seed, **a_kw)
            comm_b = build_graph(n, "random_regular", seed=graph_seed + 1, degree=6)
            dep_b = build_graph(n, d_top, seed=graph_seed + 2, **d_kw)
            sup_b = build_graph(n, "hierarchical", seed=graph_seed + 3, span=8)
            ga = auth_b.materialize()
            gc = comm_b.materialize()
            gd = dep_b.materialize()
            gs = sup_b.materialize()
            gx = _weighted_attack_operator(ga, gc, gd, gs)
            raw_radius = spectral_radius(auth_b)
            attack_radius = _weighted_spectral_radius(gx)
            # Recovery/infection sweep shifts the operating point around threshold.
            for ratio in (0.12, 0.20, 0.30, 0.42):
                gamma = 0.30
                beta = ratio * gamma
                split = "test" if (a_idx + d_idx) % 4 == 0 else "train"
                for rep in range(replications):
                    rseed = seed + scenario_id * 1000 + rep
                    peak, ever, duration = _simulate_weighted_sir(
                        gx, beta=beta, gamma=gamma, seed=rseed
                    )
                    rows.append(
                        {
                            "scenario_id": scenario_id,
                            "split": split,
                            "auth_topology": a_top,
                            "dependency_topology": d_top,
                            "beta_gamma_ratio": ratio,
                            "raw_auth_spectral_radius": raw_radius,
                            "attack_operator_spectral_radius": attack_radius,
                            "raw_threshold_product": ratio * raw_radius,
                            "attack_threshold_product": ratio * attack_radius,
                            "peak_compromised_fraction": peak,
                            "ever_compromised_fraction": ever,
                            "duration_steps": duration,
                            "seed": rseed,
                        }
                    )
                scenario_id += 1
    df = pd.DataFrame(rows)
    test = df[df.split == "test"].copy()
    # Scenario means prevent pseudo-replication from inflating correlation.
    means = (
        test.groupby("scenario_id", as_index=False)
        .agg(
            raw_threshold_product=("raw_threshold_product", "first"),
            attack_threshold_product=("attack_threshold_product", "first"),
            peak_compromised_fraction=("peak_compromised_fraction", "mean"),
            ever_compromised_fraction=("ever_compromised_fraction", "mean"),
        )
    )
    raw_rho = float(spearmanr(means.raw_threshold_product, means.ever_compromised_fraction).statistic)
    attack_rho = float(spearmanr(means.attack_threshold_product, means.ever_compromised_fraction).statistic)
    raw_peak_rho = float(spearmanr(means.raw_threshold_product, means.peak_compromised_fraction).statistic)
    attack_peak_rho = float(spearmanr(means.attack_threshold_product, means.peak_compromised_fraction).statistic)
    supported = bool(attack_rho > raw_rho + 0.10 and attack_peak_rho >= raw_peak_rho)
    result = Stage1Result(
        hypothesis="NH2",
        evidence_level="model-conditioned demonstration",
        supported_in_model=supported,
        primary_metric=attack_rho,
        baseline_metric=raw_rho,
        notes=(
            "Outcome is stochastic SIR on the candidate weighted attack graph. This verifies predictive "
            "utility inside the declared propagation model, not against observed incidents."
        ),
    )
    metrics = {
        "spearman_attack_vs_ever": attack_rho,
        "spearman_raw_auth_vs_ever": raw_rho,
        "spearman_attack_vs_peak": attack_peak_rho,
        "spearman_raw_auth_vs_peak": raw_peak_rho,
        "test_scenarios": int(means.scenario_id.nunique()),
        "replications_per_scenario": replications,
    }
    return df, result, metrics


def _admission_profile(kind: str, t: np.ndarray, n0: float, nf: float, duration: float) -> np.ndarray:
    if kind == "step":
        return np.where(t >= 5.0, nf, n0)
    if kind == "burst":
        # Four large admission bursts.
        levels = np.array([n0, n0 + 0.35*(nf-n0), n0 + 0.62*(nf-n0), n0 + 0.82*(nf-n0), nf])
        idx = np.minimum(4, np.floor(np.maximum(0.0, t - 5.0) / max(duration / 4.0, 1e-9)).astype(int))
        return levels[idx]
    if kind == "linear":
        return n0 + (nf - n0) * np.clip((t - 5.0) / duration, 0.0, 1.0)
    if kind == "staged":
        # Smooth operational staging with dwell intervals.
        phase = np.clip((t - 5.0) / duration, 0.0, 1.0)
        return n0 + (nf - n0) * (3 * phase**2 - 2 * phase**3)
    raise ValueError(kind)


def simulate_admission_trajectory(
    kind: str,
    *,
    seed: int,
    n0: int = 100,
    nf: int = 4000,
    horizon_s: float = 240.0,
    ramp_duration_s: float = 150.0,
    dt: float = 0.25,
    cp_capacity_ops_s: float = 92.0,
    sup_capacity_reviews_s: float = 18.0,
    cp_background_per_agent_hz: float = 0.010,
    sup_background_per_agent_hz: float = 0.0012,
) -> pd.DataFrame:
    """Fluid/stochastic admission transient with shared control resources."""
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, horizon_s + 1e-9, dt)
    n = _admission_profile(kind, t, float(n0), float(nf), ramp_duration_s)
    dn = np.diff(n, prepend=n[0]) / dt
    cp_q = 0.0
    sup_q = 0.0
    rows: list[dict[str, float | str | int]] = []
    for idx, now in enumerate(t):
        # Each admitted workload consumes identity + policy + telemetry-registration work.
        admitted_rate = max(0.0, float(dn[idx]))
        cp_arrival = n[idx] * cp_background_per_agent_hz + 2.3 * admitted_rate
        sup_arrival = n[idx] * sup_background_per_agent_hz + 0.38 * admitted_rate
        # Mild stochastic load variation with common physical interpretation.
        cp_arrival *= max(0.0, 1.0 + rng.normal(0.0, 0.025))
        sup_arrival *= max(0.0, 1.0 + rng.normal(0.0, 0.035))
        cp_q = max(0.0, cp_q + (cp_arrival - cp_capacity_ops_s) * dt)
        sup_q = max(0.0, sup_q + (sup_arrival - sup_capacity_reviews_s) * dt)
        cp_wait = cp_q / cp_capacity_ops_s
        sup_wait = sup_q / sup_capacity_reviews_s
        cp_util = cp_arrival / cp_capacity_ops_s
        sup_util = sup_arrival / sup_capacity_reviews_s
        # Transient minimum assurance margin. Queue delay is allowed some finite headroom.
        margins = {
            "cp_util": (0.80 - cp_util) / 0.80,
            "sup_util": (0.75 - sup_util) / 0.75,
            "cp_wait": (2.0 - cp_wait) / 2.0,
            "sup_wait": (5.0 - sup_wait) / 5.0,
        }
        min_margin = min(margins.values())
        rows.append(
            {
                "profile": kind,
                "seed": seed,
                "time_s": now,
                "n_agents": n[idx],
                "admission_rate_agents_s": admitted_rate,
                "cp_arrival_ops_s": cp_arrival,
                "sup_arrival_reviews_s": sup_arrival,
                "cp_queue": cp_q,
                "sup_queue": sup_q,
                "cp_wait_s": cp_wait,
                "sup_wait_s": sup_wait,
                "cp_utilization": cp_util,
                "sup_utilization": sup_util,
                "assurance_margin": min_margin,
                "admissible": int(min_margin >= 0.0),
            }
        )
    return pd.DataFrame(rows)


def run_nh4_admission_trajectory(
    *,
    seed: int = 20260819,
    replications: int = 40,
) -> tuple[pd.DataFrame, Stage1Result, dict[str, float]]:
    frames: list[pd.DataFrame] = []
    for rep in range(replications):
        common_seed = seed + rep
        for profile in ("step", "burst", "linear", "staged"):
            frames.append(simulate_admission_trajectory(profile, seed=common_seed))
    df = pd.concat(frames, ignore_index=True)
    per_run = (
        df.groupby(["profile", "seed"], as_index=False)
        .agg(
            final_n=("n_agents", "last"),
            minimum_margin=("assurance_margin", "min"),
            max_cp_queue=("cp_queue", "max"),
            max_sup_queue=("sup_queue", "max"),
            inadmissible_fraction=("admissible", lambda x: float(1.0 - np.mean(x))),
            final_cp_queue=("cp_queue", "last"),
            final_sup_queue=("sup_queue", "last"),
        )
    )
    summary = per_run.groupby("profile").agg(
        final_n=("final_n", "mean"),
        mean_minimum_margin=("minimum_margin", "mean"),
        mean_inadmissible_fraction=("inadmissible_fraction", "mean"),
        mean_max_cp_queue=("max_cp_queue", "mean"),
        mean_max_sup_queue=("max_sup_queue", "mean"),
    )
    rapid = float(summary.loc["step", "mean_minimum_margin"])
    gradual = float(summary.loc["staged", "mean_minimum_margin"])
    same_n = bool(np.allclose(summary.final_n.to_numpy(), summary.final_n.iloc[0]))
    supported = bool(same_n and rapid < 0.0 and gradual > rapid + 0.25)
    result = Stage1Result(
        hypothesis="NH4",
        evidence_level="model-conditioned demonstration",
        supported_in_model=supported,
        primary_metric=gradual - rapid,
        baseline_metric=0.0,
        notes=(
            "All profiles end at the same N. The experiment tests whether admission trajectory creates "
            "different transient assurance outcomes through identity/control/supervisory queues."
        ),
    )
    metrics = {
        "same_final_n": float(same_n),
        "step_mean_minimum_margin": rapid,
        "staged_mean_minimum_margin": gradual,
        "margin_advantage_staged_over_step": gradual - rapid,
        "step_inadmissible_fraction": float(summary.loc["step", "mean_inadmissible_fraction"]),
        "staged_inadmissible_fraction": float(summary.loc["staged", "mean_inadmissible_fraction"]),
        "replications": replications,
    }
    return df, result, metrics


def write_stage1_figures(
    nh1: pd.DataFrame,
    nh2: pd.DataFrame,
    nh4: pd.DataFrame,
    output_dir: str | Path,
) -> list[Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    # NH1 held-out predicted vs realized.
    test = nh1[nh1.split == "test"].dropna(subset=["coupled_score"])
    bins = pd.qcut(test.coupled_score, q=min(10, test.coupled_score.nunique()), duplicates="drop")
    calibration = test.assign(bin=bins).groupby("bin", observed=True).agg(
        predicted=("coupled_score", "mean"), realized=("failure", "mean"), n=("failure", "size")
    )
    fig, ax = plt.subplots(figsize=(7.4, 5.2))
    ax.plot([0, 1], [0, 1], linestyle="--", linewidth=1)
    ax.scatter(calibration.predicted, calibration.realized, s=np.maximum(20, calibration.n * 2))
    ax.set_xlabel("Predicted failure probability")
    ax.set_ylabel("Realized failure fraction")
    ax.set_title("NH1 held-out coupled-envelope calibration")
    ax.grid(True, alpha=0.2)
    p = output / "nh1_heldout_calibration.png"
    fig.tight_layout(); fig.savefig(p, dpi=170); plt.close(fig); paths.append(p)

    # NH2 predictor comparison.
    means = nh2[nh2.split == "test"].groupby("scenario_id", as_index=False).agg(
        raw=("raw_threshold_product", "first"), attack=("attack_threshold_product", "first"),
        ever=("ever_compromised_fraction", "mean")
    )
    fig, ax = plt.subplots(figsize=(7.4, 5.2))
    ax.scatter(means.raw, means.ever, marker="o", label="Raw authorization spectrum")
    ax.scatter(means.attack, means.ever, marker="x", label="Attack-reachability operator")
    ax.set_xlabel("Threshold predictor")
    ax.set_ylabel("Mean ever-compromised fraction")
    ax.set_title("NH2 held-out propagation predictor comparison")
    ax.legend()
    ax.grid(True, alpha=0.2)
    p = output / "nh2_attack_operator_comparison.png"
    fig.tight_layout(); fig.savefig(p, dpi=170); plt.close(fig); paths.append(p)

    # NH4 trajectory comparison, averaged across common-random-number replications.
    mean_t = nh4.groupby(["profile", "time_s"], as_index=False).agg(
        n_agents=("n_agents", "mean"), margin=("assurance_margin", "mean")
    )
    fig, ax = plt.subplots(figsize=(8.0, 5.2))
    for profile, group in mean_t.groupby("profile"):
        ax.plot(group.time_s, group.margin, label=profile)
    ax.axhline(0.0, linestyle="--", linewidth=1)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Minimum normalized assurance margin")
    ax.set_title("NH4 equal-final-N admission trajectories")
    ax.legend()
    ax.grid(True, alpha=0.2)
    p = output / "nh4_admission_trajectory_margin.png"
    fig.tight_layout(); fig.savefig(p, dpi=170); plt.close(fig); paths.append(p)

    return paths


def run_stage1_cycle(output_root: str | Path, *, seed: int = 20260819) -> dict[str, object]:
    root = Path(output_root)
    results_dir = root / "results" / "stage1_cycle1"
    figures_dir = root / "figures" / "stage1_cycle1"
    results_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    nh1_df, nh1_result, nh1_metrics = run_nh1_coupled_envelope(seed=seed)
    nh1_df.to_csv(results_dir / "nh1_coupled_envelope.csv", index=False)

    nh2_df, nh2_result, nh2_metrics = run_nh2_attack_reachability(seed=seed)
    nh2_df.to_csv(results_dir / "nh2_attack_reachability.csv", index=False)

    nh4_df, nh4_result, nh4_metrics = run_nh4_admission_trajectory(seed=seed)
    nh4_df.to_csv(results_dir / "nh4_admission_trajectory.csv", index=False)

    figure_paths = write_stage1_figures(nh1_df, nh2_df, nh4_df, figures_dir)

    summary = {
        "seed": seed,
        "evidence_scope": "model-conditioned; parameters notional; no external validation",
        "results": [nh1_result.as_dict(), nh2_result.as_dict(), nh4_result.as_dict()],
        "metrics": {"NH1": nh1_metrics, "NH2": nh2_metrics, "NH4": nh4_metrics},
        "figures": [str(p.relative_to(root)) for p in figure_paths],
    }
    import json
    (results_dir / "stage1_cycle1_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
