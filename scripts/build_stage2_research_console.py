from __future__ import annotations

import html
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "replay_bundles" / "stage2-cycles4-7-research-console.html"


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def figure_html(fig: go.Figure, *, include_js: bool = False) -> str:
    return pio.to_html(
        fig,
        full_html=False,
        include_plotlyjs="inline" if include_js else False,
        config={"displaylogo": False, "responsive": True, "scrollZoom": True},
    )


def criterion_rows(title: str, criteria: dict[str, bool]) -> str:
    parts = [f"<tr class='group'><td colspan='3'>{html.escape(title)}</td></tr>"]
    for name, passed in criteria.items():
        label = name.replace("_", " ")
        state = "PASS" if passed else "FAIL"
        cls = "pass" if passed else "fail"
        parts.append(
            f"<tr><td>{html.escape(label)}</td><td class='{cls}'>{state}</td>"
            f"<td>{'Criterion satisfied' if passed else 'Criterion not satisfied'}</td></tr>"
        )
    return "".join(parts)


cycle5 = load_json("results/stage2_cycle5/stage2_cycle5_summary.json")
cycle6 = load_json("results/stage2_cycle6/stage2_cycle6_summary.json")
cycle7 = load_json("results/stage2_cycle7/stage2_cycle7_summary.json")
manifest7 = load_json("manifests/stage2_cycle7_execution_manifest.json")

c6_nh2 = pd.read_csv(ROOT / "results/stage2_cycle6/nh2_predictions.csv")
c6_nh4 = pd.read_csv(ROOT / "results/stage2_cycle6/nh4_predictions.csv")
c7_pred = pd.read_csv(ROOT / "results/stage2_cycle7/nh2_hurdle_predictions.csv")
c7_blocks = pd.read_csv(ROOT / "results/stage2_cycle7/nh2_hurdle_blocks.csv")

# Figure 1: Cycle 6 temporal compromise predictors.
fig_c6_nh2 = make_subplots(
    rows=1,
    cols=2,
    subplot_titles=(
        "Observed final compromise versus calibrated prediction",
        "Absolute error by candidate",
    ),
    horizontal_spacing=0.13,
)
for predictor, display in (("nb_pre", "Static non-backtracking"), ("propagator_growth", "Temporal propagator")):
    subset = c6_nh2[c6_nh2["predictor"] == predictor]
    fig_c6_nh2.add_trace(
        go.Scatter(
            x=subset["mean_ever_fraction"],
            y=subset["prediction"],
            mode="markers",
            name=display,
            marker={"size": 7, "opacity": 0.65},
            customdata=np.column_stack([subset["scenario_id"], subset["outbreak_rate"]]),
            hovertemplate=(
                "Scenario %{customdata[0]}<br>Observed %{x:.4f}<br>Predicted %{y:.4f}"
                "<br>Outbreak rate %{customdata[1]:.3f}<extra></extra>"
            ),
        ),
        row=1,
        col=1,
    )
fig_c6_nh2.add_trace(
    go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Perfect prediction", line={"dash": "dash"}),
    row=1,
    col=1,
)
metric_rows = pd.read_csv(ROOT / "results/stage2_cycle6/nh2_metrics.csv")
fig_c6_nh2.add_trace(
    go.Bar(
        x=metric_rows["predictor"],
        y=metric_rows["test_mae"],
        text=[f"{value:.4f}" for value in metric_rows["test_mae"]],
        textposition="auto",
        name="Held-out MAE",
        hovertemplate="%{x}<br>MAE %{y:.5f}<extra></extra>",
    ),
    row=1,
    col=2,
)
fig_c6_nh2.update_xaxes(title_text="Observed ever-compromised fraction", row=1, col=1)
fig_c6_nh2.update_yaxes(title_text="Predicted fraction", row=1, col=1)
fig_c6_nh2.update_xaxes(title_text="Predictor", tickangle=-25, row=1, col=2)
fig_c6_nh2.update_yaxes(title_text="Held-out MAE", row=1, col=2)
fig_c6_nh2.update_layout(
    height=510,
    title="Cycle 6 NH2-T: temporal graph score did not improve final-size error",
    legend={"orientation": "h", "y": -0.2},
    margin={"l": 65, "r": 35, "t": 90, "b": 125},
)

# Figure 2: Cycle 6 admission overload boundary.
fig_c6_nh4 = make_subplots(
    rows=1,
    cols=2,
    subplot_titles=("Failure frontier versus Omega_A", "Peak Lambda_A versus accumulated Omega_A"),
    horizontal_spacing=0.12,
)
for regime, group in c6_nh4.groupby("capacity_regime"):
    fig_c6_nh4.add_trace(
        go.Scatter(
            x=group["omega"],
            y=group["failure_rate"],
            mode="markers",
            name=str(regime),
            marker={"size": 8, "opacity": 0.75},
            customdata=np.column_stack(
                [group["scenario_id"], group["nf"], group["profile"], group["peak_lambda"]]
            ),
            hovertemplate=(
                "Scenario %{customdata[0]}<br>Nf %{customdata[1]:,.0f}<br>Profile %{customdata[2]}"
                "<br>Omega %{x:.3f}<br>Failure rate %{y:.3f}<br>Peak Lambda %{customdata[3]:.3f}"
                "<extra></extra>"
            ),
        ),
        row=1,
        col=1,
    )
fig_c6_nh4.add_vline(x=1.0, line_dash="dash", row=1, col=1)
fig_c6_nh4.add_trace(
    go.Scatter(
        x=c6_nh4["peak_lambda"],
        y=c6_nh4["omega"],
        mode="markers",
        marker={"size": 6 + 16 * c6_nh4["failure_rate"], "opacity": 0.7},
        name="Scenarios",
        customdata=np.column_stack(
            [c6_nh4["scenario_id"], c6_nh4["failure_rate"], c6_nh4["profile"], c6_nh4["capacity_regime"]]
        ),
        hovertemplate=(
            "Scenario %{customdata[0]}<br>Peak Lambda %{x:.3f}<br>Omega %{y:.3f}"
            "<br>Failure rate %{customdata[1]:.3f}<br>%{customdata[2]} / %{customdata[3]}<extra></extra>"
        ),
    ),
    row=1,
    col=2,
)
fig_c6_nh4.add_hline(y=1.0, line_dash="dash", row=1, col=2)
fig_c6_nh4.update_xaxes(title_text="Omega_A", row=1, col=1)
fig_c6_nh4.update_yaxes(title_text="Boundary-crossing rate", row=1, col=1)
fig_c6_nh4.update_xaxes(title_text="Peak Lambda_A", row=1, col=2)
fig_c6_nh4.update_yaxes(title_text="Omega_A", row=1, col=2)
fig_c6_nh4.update_layout(
    height=510,
    title="Cycle 6 NH4-O: accumulated overload was more informative than peak load",
    legend={"orientation": "h", "y": -0.2},
    margin={"l": 65, "r": 35, "t": 90, "b": 105},
)

# Figure 3: Cycle 7 block results and pooled prediction.
fig_c7 = make_subplots(
    rows=1,
    cols=2,
    subplot_titles=("Held-out MAE by independent block", "Pooled observed versus predicted final size"),
    horizontal_spacing=0.13,
)
fig_c7.add_trace(
    go.Bar(
        x=[f"Block {int(v)}" for v in c7_blocks["block"]],
        y=c7_blocks["best_baseline_mae"],
        name="Best direct spectral baseline",
        text=[f"{v:.4f}" for v in c7_blocks["best_baseline_mae"]],
        textposition="auto",
    ),
    row=1,
    col=1,
)
fig_c7.add_trace(
    go.Bar(
        x=[f"Block {int(v)}" for v in c7_blocks["block"]],
        y=c7_blocks["hurdle_mae"],
        name="Two-stage candidate",
        text=[f"{v:.4f}" for v in c7_blocks["hurdle_mae"]],
        textposition="auto",
    ),
    row=1,
    col=1,
)
fig_c7.add_trace(
    go.Scatter(
        x=c7_pred["mean_ever_fraction"],
        y=c7_pred["best_baseline_prediction"],
        mode="markers",
        name="Direct baseline",
        marker={"size": 6, "opacity": 0.48},
        hovertemplate="Observed %{x:.4f}<br>Baseline %{y:.4f}<extra></extra>",
    ),
    row=1,
    col=2,
)
fig_c7.add_trace(
    go.Scatter(
        x=c7_pred["mean_ever_fraction"],
        y=c7_pred["hurdle_expected_fraction"],
        mode="markers",
        name="Two-stage candidate",
        marker={"size": 6, "opacity": 0.55},
        customdata=np.column_stack(
            [c7_pred["block"], c7_pred["scenario_id"], c7_pred["outbreak_rate"], c7_pred["n_agents"]]
        ),
        hovertemplate=(
            "Block %{customdata[0]} scenario %{customdata[1]}<br>N %{customdata[3]:,.0f}"
            "<br>Observed %{x:.4f}<br>Candidate %{y:.4f}<br>Outbreak rate %{customdata[2]:.3f}"
            "<extra></extra>"
        ),
    ),
    row=1,
    col=2,
)
fig_c7.add_trace(
    go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Perfect prediction", line={"dash": "dash"}),
    row=1,
    col=2,
)
fig_c7.update_xaxes(title_text="Independent block", row=1, col=1)
fig_c7.update_yaxes(title_text="Mean absolute error", row=1, col=1)
fig_c7.update_xaxes(title_text="Observed ever-compromised fraction", row=1, col=2)
fig_c7.update_yaxes(title_text="Predicted fraction", row=1, col=2)
fig_c7.update_layout(
    barmode="group",
    height=530,
    title="Cycle 7 NH2-H: pooled improvement with failed conjunctive support gates",
    legend={"orientation": "h", "y": -0.2},
    margin={"l": 65, "r": 35, "t": 90, "b": 105},
)

# Figure 4: initiation calibration and error improvement distribution.
cal = c7_pred.copy()
cal["probability_bin"] = pd.cut(
    cal["hurdle_outbreak_probability"], bins=np.linspace(0.0, 1.0, 11), include_lowest=True
)
calibration = (
    cal.groupby(["block", "probability_bin"], observed=True, as_index=False)
    .agg(predicted=("hurdle_outbreak_probability", "mean"), realized=("outbreak_rate", "mean"), n=("scenario_id", "size"))
)
fig_diag = make_subplots(
    rows=1,
    cols=2,
    subplot_titles=("Outbreak-initiation calibration", "Candidate error reduction by scenario"),
    horizontal_spacing=0.13,
)
for block, group in calibration.groupby("block"):
    fig_diag.add_trace(
        go.Scatter(
            x=group["predicted"],
            y=group["realized"],
            mode="lines+markers",
            name=f"Block {int(block)}",
            marker={"size": np.maximum(6, np.sqrt(group["n"]) * 3)},
            hovertemplate="Predicted %{x:.3f}<br>Realized %{y:.3f}<extra></extra>",
        ),
        row=1,
        col=1,
    )
fig_diag.add_trace(
    go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Perfect calibration", line={"dash": "dash"}),
    row=1,
    col=1,
)
error_reduction = c7_pred["baseline_absolute_error"] - c7_pred["candidate_absolute_error"]
fig_diag.add_trace(
    go.Histogram(
        x=error_reduction,
        nbinsx=45,
        name="Baseline error minus candidate error",
        hovertemplate="Error reduction %{x:.4f}<br>Scenarios %{y}<extra></extra>",
    ),
    row=1,
    col=2,
)
fig_diag.add_vline(x=0.0, line_dash="dash", row=1, col=2)
fig_diag.update_xaxes(title_text="Predicted outbreak probability", row=1, col=1)
fig_diag.update_yaxes(title_text="Realized outbreak rate", row=1, col=1)
fig_diag.update_xaxes(title_text="Positive values favor candidate", row=1, col=2)
fig_diag.update_yaxes(title_text="Scenario count", row=1, col=2)
fig_diag.update_layout(
    height=510,
    title="Cycle 7 diagnostics: initiation calibration remains the limiting gate",
    legend={"orientation": "h", "y": -0.2},
    margin={"l": 65, "r": 35, "t": 90, "b": 105},
)

criteria_html = (
    criterion_rows("Cycle 5 NH2-D", cycle5["NH2_D"]["criteria"])
    + criterion_rows("Cycle 6 NH2-T", cycle6["NH2_T"]["criteria"])
    + criterion_rows("Cycle 6 NH4-O", cycle6["NH4_O"]["criteria"])
    + criterion_rows("Cycle 7 NH2-H", cycle7["criteria"])
)

cards = [
    (
        "Cycle 5 NH2-D",
        "REFUTED",
        "Dynamic K(t)",
        f"MAE change {100 * cycle5['NH2_D']['mae_improvement_fraction']:.1f}%<br>"
        f"AUC delta {cycle5['NH2_D']['auc_delta']:.3f}",
        "bad",
    ),
    (
        "Cycle 6 NH2-T",
        "UNSUPPORTED",
        "Temporal propagator",
        f"MAE change {100 * cycle6['NH2_T']['mae_improvement_fraction']:.1f}%<br>"
        f"AUC delta {cycle6['NH2_T']['auc_delta']:.3f}",
        "bad",
    ),
    (
        "Cycle 6 NH4-O",
        "PROMISING",
        "Accumulated overload",
        f"Omega AUC {cycle6['NH4_O']['omega_auc']:.3f}<br>"
        f"Brier reduction {100 * cycle6['NH4_O']['brier_improvement_fraction']:.1f}%",
        "warn",
    ),
    (
        "Cycle 7 NH2-H",
        "NEAR MISS",
        "Two-stage compromise model",
        f"Pooled MAE improvement {100 * cycle7['pooled_mae_improvement_fraction']:.1f}%<br>"
        f"Supported: {str(cycle7['supported_in_model']).lower()}",
        "warn",
    ),
]
card_html = "".join(
    f"<div class='card {cls}'><div class='eyebrow'>{html.escape(cycle)}</div>"
    f"<div class='state'>{html.escape(state)}</div><div class='concept'>{html.escape(concept)}</div>"
    f"<div class='metric'>{metric}</div></div>"
    for cycle, state, concept, metric, cls in cards
)

integrity_rows = "".join(
    f"<tr><td>{html.escape(item['path'])}</td><td>{item['actual_sha256'][:16]}...</td>"
    f"<td class='{'pass' if item['match'] else 'fail'}'>{'MATCH' if item['match'] else 'MISMATCH'}</td></tr>"
    for item in manifest7["frozen_input_checks"]
)

html_doc = f"""<!doctype html>
<html lang='en'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Fleet Assurance Stage 2 Research Console</title>
<style>
:root {{ color-scheme: dark; --bg:#0d1117; --panel:#151b23; --panel2:#1b2430; --text:#e6edf3; --muted:#9ba7b4; --line:#303b47; --good:#56d364; --bad:#ff7b72; --warn:#d29922; --accent:#79c0ff; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background:var(--bg); color:var(--text); }}
header {{ padding:42px 5vw 26px; border-bottom:1px solid var(--line); background:linear-gradient(135deg,#111827,#0d1117); }}
h1 {{ margin:0 0 10px; font-size:clamp(28px,4vw,48px); letter-spacing:-0.03em; }}
.subtitle {{ max-width:1050px; color:var(--muted); line-height:1.55; font-size:16px; }}
.badge {{ display:inline-block; margin-top:16px; padding:7px 11px; border:1px solid var(--line); border-radius:999px; color:var(--accent); background:#111923; font-size:13px; }}
main {{ width:min(1580px,96vw); margin:0 auto; padding:28px 0 70px; }}
.grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:16px; margin-bottom:24px; }}
.card {{ min-height:172px; padding:20px; border:1px solid var(--line); border-radius:14px; background:var(--panel); box-shadow:0 8px 24px rgba(0,0,0,.18); }}
.card.bad {{ border-top:4px solid var(--bad); }} .card.warn {{ border-top:4px solid var(--warn); }}
.eyebrow {{ color:var(--muted); font-size:12px; letter-spacing:.09em; text-transform:uppercase; }}
.state {{ font-weight:800; font-size:25px; margin:8px 0 6px; }}
.concept {{ color:var(--accent); font-weight:650; margin-bottom:14px; }}
.metric {{ color:var(--muted); line-height:1.5; font-variant-numeric:tabular-nums; }}
.section {{ margin:22px 0; border:1px solid var(--line); border-radius:14px; background:var(--panel); overflow:hidden; }}
.section h2 {{ margin:0; padding:18px 22px; font-size:21px; border-bottom:1px solid var(--line); background:var(--panel2); }}
.section .copy {{ padding:18px 22px 0; color:var(--muted); line-height:1.55; }}
.plot {{ width:100%; overflow:hidden; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th,td {{ padding:11px 14px; text-align:left; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.06em; }}
.group td {{ background:var(--panel2); color:var(--accent); font-weight:700; }}
.pass {{ color:var(--good); font-weight:700; }} .fail {{ color:var(--bad); font-weight:700; }}
.scroll {{ overflow:auto; max-height:430px; }}
.callout {{ margin:24px 0; padding:20px 24px; border-left:4px solid var(--accent); background:#111923; color:var(--text); line-height:1.55; }}
small {{ color:var(--muted); }}
@media (max-width:1050px) {{ .grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
@media (max-width:650px) {{ .grid {{ grid-template-columns:1fr; }} header {{ padding:30px 4vw 20px; }} main {{ width:98vw; }} }}
</style>
</head>
<body>
<header>
  <h1>Fleet Assurance Stage 2 Research Console</h1>
  <div class='subtitle'>Cycles 4 through 7 tested directed compromise metrics and multi-resource fleet-admission stability under preregistered, hash-gated numerical experiments. This console presents model-conditioned evidence only. Every operational parameter remains notional.</div>
  <div class='badge'>Cycle 7 frozen inputs: {'ALL MATCH' if manifest7['all_frozen_inputs_match'] else 'MISMATCH DETECTED'}</div>
</header>
<main>
  <div class='grid'>{card_html}</div>
  <div class='callout'><strong>Current decision:</strong> no Stage 2 candidate satisfies its complete preregistered support rule. The two-stage compromise model is the strongest near-term research direction. Omega_A remains a promising admission-risk indicator. Neither is an externally validated assurance law.</div>

  <section class='section'><h2>Cycle 6 compromise prediction</h2><div class='copy'>The temporal propagator improved rank behavior but increased held-out final-size error relative to the static non-backtracking baseline. This result rules out the selected scalar temporal score in its tested form.</div><div class='plot'>{figure_html(fig_c6_nh2, include_js=True)}</div></section>

  <section class='section'><h2>Cycle 6 fleet-admission boundary</h2><div class='copy'>Omega_A represents accumulated reflected backlog relative to queue budget across identity, credential, telemetry, and supervisory resources. It separated the targeted boundary substantially better than peak Lambda_A, but missed the full robustness gate.</div><div class='plot'>{figure_html(fig_c6_nh4)}</div></section>

  <section class='section'><h2>Cycle 7 two-stage compromise estimator</h2><div class='copy'>The candidate separately estimates macroscopic outbreak initiation and conditional severity. Pooled final-size MAE improved 18.8 percent, with positive improvement in all three independent blocks. The model remained unsupported because only one block exceeded 15 percent improvement and initiation-probability Brier performance was noninferior in only one block.</div><div class='plot'>{figure_html(fig_c7)}</div></section>

  <section class='section'><h2>Cycle 7 diagnostic evidence</h2><div class='copy'>Positive values in the error-reduction distribution favor the two-stage model. The initiation calibration panel exposes the remaining limitation: improved final-size prediction does not guarantee improved probability calibration.</div><div class='plot'>{figure_html(fig_diag)}</div></section>

  <section class='section'><h2>Preregistered acceptance gates</h2><div class='scroll'><table><thead><tr><th>Criterion</th><th>State</th><th>Interpretation</th></tr></thead><tbody>{criteria_html}</tbody></table></div></section>

  <section class='section'><h2>Cycle 7 frozen-input integrity</h2><div class='copy'>The execution manifest recomputed every frozen file hash after the run. A matching hash supports procedural integrity and reproducibility. It does not validate the model assumptions.</div><div class='scroll'><table><thead><tr><th>Frozen input</th><th>SHA-256 prefix</th><th>State</th></tr></thead><tbody>{integrity_rows}</tbody></table></div></section>

  <section class='section'><h2>Evidence boundaries</h2><div class='copy' style='padding-bottom:20px'>A discrete-event or stochastic network simulation establishes behavior of its declared model. These results do not establish implementation security, operational incident prediction, safe deployment at N = 10,000, or priority over all prior art. The next evidence gate is transfer to independently generated or measured authorization, dependency, response, and service-capacity data.</div></section>
  <small>Generated from machine-readable Cycle 5, Cycle 6, and Cycle 7 artifacts. Offline Plotly runtime is embedded in this file. No network access is required.</small>
</main>
</body>
</html>"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(html_doc, encoding="utf-8")
print(OUT)
print(f"bytes={OUT.stat().st_size}")
