from __future__ import annotations

import base64
import html
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "replay_bundles" / "stage2-research-evidence-console.html"


def load_json(path: str) -> dict[str, Any]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def image_uri(path: str) -> str:
    raw = (ROOT / path).read_bytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def pct(value: float, digits: int = 1) -> str:
    return f"{100.0 * value:.{digits}f}%"


def num(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}"


c5 = load_json("results/stage2_cycle5/stage2_cycle5_summary.json")
c6 = load_json("results/stage2_cycle6/stage2_cycle6_summary.json")
c7 = load_json("results/stage2_cycle7/stage2_cycle7_summary.json")
syn = load_json("results/stage2_synthesis/stage2_synthesis.json")
m7 = load_json("manifests/stage2_cycle7_execution_manifest.json")

images = {
    "c5_dynamic": image_uri("figures/stage2_cycle5/nh2_dynamic_operator_prediction.png"),
    "c6_temporal": image_uri("figures/stage2_cycle6/nh2_temporal_predictor_scatter.png"),
    "c6_mae": image_uri("figures/stage2_cycle6/nh2_predictor_mae.png"),
    "c6_omega": image_uri("figures/stage2_cycle6/nh4_omega_transition.png"),
    "c6_compare": image_uri("figures/stage2_cycle6/nh4_lambda_vs_omega.png"),
    "c7_blocks": image_uri("figures/stage2_cycle7/cycle7_block_mae.png"),
    "c7_pool": image_uri("figures/stage2_cycle7/cycle7_pooled_prediction.png"),
    "c7_prob": image_uri("figures/stage2_cycle7/cycle7_initiation_probability.png"),
}

block_rows = "".join(
    f"<tr><td>{b['block']}</td><td>{b['seed']}</td><td>{b['hurdle_mae']:.5f}</td>"
    f"<td>{b['best_baseline_mae']:.5f}</td><td>{pct(b['mae_improvement_fraction'])}</td>"
    f"<td>{pct(b['brier_improvement_fraction'])}</td><td>{b['auc_delta']:+.4f}</td></tr>"
    for b in c7["block_results"]
)

hash_rows = "".join(
    f"<tr><td><code>{html.escape(item['path'])}</code></td>"
    f"<td>{'MATCH' if item['match'] else 'MISMATCH'}</td>"
    f"<td><code>{item['actual_sha256'][:16]}...</code></td></tr>"
    for item in m7["frozen_input_checks"]
)

ledger_rows = "".join(
    f"<tr><td><strong>{html.escape(item['claim_id'])}</strong></td>"
    f"<td>{html.escape(item['cycle'])}</td><td>{html.escape(item['status'])}</td>"
    f"<td>{html.escape(item['primary_metric'])}</td>"
    f"<td>{html.escape(item['binding_failure'])}</td></tr>"
    for item in syn["decisions"]
)

embedded_json = json.dumps(
    {
        "cycle5": c5,
        "cycle6": c6,
        "cycle7": c7,
        "synthesis": syn,
        "cycle7_manifest": m7,
    },
    separators=(",", ":"),
)

page = f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<title>Stage 2 Fleet Assurance Research Console</title>
<style>
:root {{
  --bg: #08111d;
  --panel: #0f1b2d;
  --panel2: #14243a;
  --text: #e9f0f7;
  --muted: #9fb0c5;
  --line: #263a52;
  --accent: #65c8ff;
  --good: #74d6a3;
  --warn: #f4c86b;
  --bad: #ff8585;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; }}
header {{ padding: 32px clamp(20px, 5vw, 72px) 24px; border-bottom: 1px solid var(--line); background: radial-gradient(circle at top left, #183756 0, var(--bg) 48%); }}
h1 {{ margin: 0 0 8px; font-size: clamp(28px, 4vw, 48px); letter-spacing: -0.02em; }}
.subtitle {{ color: var(--muted); max-width: 1100px; font-size: 17px; }}
.banner {{ margin-top: 20px; border: 1px solid var(--warn); background: rgba(244,200,107,.08); padding: 12px 16px; border-radius: 10px; max-width: 1100px; }}
nav {{ position: sticky; top: 0; z-index: 10; display: flex; gap: 8px; overflow-x: auto; padding: 12px clamp(16px, 5vw, 72px); background: rgba(8,17,29,.96); border-bottom: 1px solid var(--line); backdrop-filter: blur(12px); }}
nav button {{ background: transparent; border: 1px solid var(--line); color: var(--muted); border-radius: 999px; padding: 8px 14px; cursor: pointer; white-space: nowrap; }}
nav button.active {{ color: var(--text); border-color: var(--accent); background: rgba(101,200,255,.10); }}
main {{ padding: 28px clamp(16px, 5vw, 72px) 64px; max-width: 1600px; margin: auto; }}
section.tab {{ display: none; }}
section.tab.active {{ display: block; }}
h2 {{ font-size: 28px; margin-top: 0; }}
h3 {{ margin-top: 0; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(245px, 1fr)); gap: 16px; margin: 18px 0 28px; }}
.card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 18px; box-shadow: 0 12px 30px rgba(0,0,0,.18); }}
.card .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .09em; }}
.card .value {{ font-size: 30px; font-weight: 720; margin: 6px 0; }}
.card .detail {{ color: var(--muted); font-size: 14px; }}
.status {{ display: inline-block; padding: 4px 9px; border-radius: 999px; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }}
.status.bad {{ background: rgba(255,133,133,.13); color: var(--bad); }}
.status.warn {{ background: rgba(244,200,107,.13); color: var(--warn); }}
.status.good {{ background: rgba(116,214,163,.13); color: var(--good); }}
.callout {{ background: var(--panel2); border-left: 4px solid var(--accent); padding: 16px 18px; border-radius: 8px; margin: 18px 0; }}
.figure-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 18px; }}
.figure {{ background: white; border-radius: 12px; padding: 8px; overflow: hidden; }}
.figure img {{ width: 100%; height: auto; display: block; }}
.caption {{ color: var(--muted); font-size: 13px; padding: 8px 2px 2px; }}
table {{ width: 100%; border-collapse: collapse; margin: 16px 0 28px; background: var(--panel); border: 1px solid var(--line); }}
th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .06em; background: var(--panel2); }}
tr:last-child td {{ border-bottom: 0; }}
code {{ color: #c9eaff; overflow-wrap: anywhere; }}
.metric-line {{ display: flex; align-items: center; gap: 12px; margin: 9px 0; }}
.bar {{ flex: 1; height: 10px; background: #243247; border-radius: 999px; overflow: hidden; }}
.fill {{ height: 100%; background: linear-gradient(90deg, #65c8ff, #74d6a3); }}
.small {{ color: var(--muted); font-size: 13px; }}
.controls {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 18px 0; }}
.controls button {{ padding: 9px 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel2); color: var(--text); cursor: pointer; }}
pre {{ background: #06101b; border: 1px solid var(--line); padding: 14px; border-radius: 10px; overflow: auto; max-height: 420px; }}
footer {{ color: var(--muted); border-top: 1px solid var(--line); padding: 22px clamp(16px,5vw,72px); }}
@media (max-width: 650px) {{ .figure-grid {{ grid-template-columns: 1fr; }} th, td {{ font-size: 12px; padding: 8px; }} }}
</style>
</head>
<body>
<header>
  <h1>Stage 2 Fleet Assurance Research Console</h1>
  <div class=\"subtitle\">Interactive evidence review for Cycles 5 through 7. All operational parameters are notional. Results describe the implemented model and do not establish deployment security.</div>
  <div class=\"banner\"><strong>Current decision:</strong> No universal Fleet Assurance Law is established. Two scalar compromise hypotheses were refuted. The admission overload index and phase-separated compromise model remain provisional research candidates.</div>
</header>
<nav>
  <button class=\"active\" data-tab=\"overview\">Overview</button>
  <button data-tab=\"compromise\">Compromise</button>
  <button data-tab=\"admission\">Admission</button>
  <button data-tab=\"provenance\">Provenance</button>
  <button data-tab=\"novelty\">Novelty and Decision</button>
</nav>
<main>
<section id=\"overview\" class=\"tab active\">
  <h2>Research disposition</h2>
  <div class=\"grid\">
    <div class=\"card\"><span class=\"status bad\">Refuted</span><div class=\"value\">NH2-D</div><div class=\"detail\">Dynamic next-generation scalar. Held-out MAE was {pct(-c5['NH2_D']['mae_improvement_fraction'])} worse and outbreak AUC was {abs(c5['NH2_D']['auc_delta']):.3f} lower than the strongest baseline.</div></div>
    <div class=\"card\"><span class=\"status bad\">Refuted</span><div class=\"value\">NH2-T</div><div class=\"detail\">Training-selected temporal scalar. Held-out final-size MAE was {pct(-c6['NH2_T']['mae_improvement_fraction'])} worse than static non-backtracking.</div></div>
    <div class=\"card\"><span class=\"status warn\">Provisional</span><div class=\"value\">NH4-O</div><div class=\"detail\">Cumulative admission overload. AUC {c6['NH4_O']['omega_auc']:.3f}, balanced accuracy {c6['NH4_O']['omega_one_balanced_accuracy']:.3f}, but missed the fixed superiority and robustness bars.</div></div>
    <div class=\"card\"><span class=\"status warn\">Mixed</span><div class=\"value\">NH2-H</div><div class=\"detail\">Phase-separated model. Pooled final-size MAE improved {pct(c7['pooled_mae_improvement_fraction'])}, but probability calibration and block-level criteria did not all pass.</div></div>
  </div>
  <div class=\"callout\"><strong>Principal scientific result.</strong> Outbreak occurrence and final compromise magnitude should not be forced into one scalar predictor in this model. Dynamic structure may still matter, but it must remain phase-specific, layer-specific, or node-resolved long enough to preserve information.</div>
  <h3>Evidence ledger</h3>
  <table><thead><tr><th>Claim</th><th>Cycle</th><th>Status</th><th>Primary metric</th><th>Binding failure</th></tr></thead><tbody>{ledger_rows}</tbody></table>
  <div class=\"controls\"><button onclick=\"downloadEvidence()\">Download embedded evidence JSON</button><button onclick=\"window.print()\">Print console</button></div>
</section>

<section id=\"compromise\" class=\"tab\">
  <h2>Compromise prediction</h2>
  <div class=\"grid\">
    <div class=\"card\"><div class=\"label\">Cycle 5 dynamic MAE</div><div class=\"value\">{c5['NH2_D']['dynamic_mae']:.4f}</div><div class=\"detail\">Best baseline {c5['NH2_D']['best_baseline_mae']:.4f}</div></div>
    <div class=\"card\"><div class=\"label\">Cycle 6 temporal MAE</div><div class=\"value\">{c6['NH2_T']['candidate_test_mae']:.4f}</div><div class=\"detail\">Static non-backtracking {c6['NH2_T']['baseline_test_mae']:.4f}</div></div>
    <div class=\"card\"><div class=\"label\">Cycle 7 pooled hurdle MAE</div><div class=\"value\">{c7['pooled_hurdle_mae']:.4f}</div><div class=\"detail\">Best direct baseline {c7['pooled_best_baseline_mae']:.4f}</div></div>
    <div class=\"card\"><div class=\"label\">Cycle 7 bootstrap interval</div><div class=\"value\">{pct(c7['bootstrap_95pct']['fractional_mae_improvement'][0])} to {pct(c7['bootstrap_95pct']['fractional_mae_improvement'][1])}</div><div class=\"detail\">Fractional pooled final-size MAE improvement</div></div>
  </div>
  <h3>Cycle 7 independent blocks</h3>
  <table><thead><tr><th>Block</th><th>Seed</th><th>Hurdle MAE</th><th>Baseline MAE</th><th>MAE improvement</th><th>Brier improvement</th><th>AUC delta</th></tr></thead><tbody>{block_rows}</tbody></table>
  <div class=\"figure-grid\">
    <div><div class=\"figure\"><img src=\"{images['c7_blocks']}\" alt=\"Cycle 7 block MAE\"></div><div class=\"caption\">Cycle 7 final-size error by independent graph block. Thirty replications per scenario.</div></div>
    <div><div class=\"figure\"><img src=\"{images['c7_pool']}\" alt=\"Cycle 7 pooled prediction\"></div><div class=\"caption\">Observed versus predicted mean final compromised fraction in held-out scenarios.</div></div>
    <div><div class=\"figure\"><img src=\"{images['c7_prob']}\" alt=\"Cycle 7 initiation probability\"></div><div class=\"caption\">Outbreak-initiation calibration. Final-size improvement did not guarantee consistently better Brier calibration.</div></div>
    <div><div class=\"figure\"><img src=\"{images['c6_temporal']}\" alt=\"Cycle 6 temporal predictor\"></div><div class=\"caption\">Cycle 6 temporal predictor behavior on the held-out region.</div></div>
  </div>
  <div class=\"callout\"><strong>Decision.</strong> Retire the tested single-scalar replacements. Preserve static non-backtracking as the scalar baseline, then compare phase-separated or dynamic message-passing models against it.</div>
</section>

<section id=\"admission\" class=\"tab\">
  <h2>Dynamic fleet admission</h2>
  <p>The candidate overload index integrates reflected backlog across control-plane, credential, telemetry-control, and supervisory resources. It is not a measured operational law.</p>
  <div class=\"grid\">
    <div class=\"card\"><div class=\"label\">Held-out scenarios</div><div class=\"value\">{c6['NH4_O']['test_scenarios']}</div><div class=\"detail\">{c6['NH4_O']['positive_test_scenarios']} majority-failure and {c6['NH4_O']['negative_test_scenarios']} non-failure scenarios</div></div>
    <div class=\"card\"><div class=\"label\">Omega ROC AUC</div><div class=\"value\">{c6['NH4_O']['omega_auc']:.3f}</div><div class=\"detail\">Lambda comparator {c6['NH4_O']['lambda_auc']:.3f}</div></div>
    <div class=\"card\"><div class=\"label\">Brier reduction</div><div class=\"value\">{pct(c6['NH4_O']['brier_improvement_fraction'])}</div><div class=\"detail\">Monotone training calibration evaluated on held-out profiles and sizes</div></div>
    <div class=\"card\"><div class=\"label\">Fixed-boundary accuracy</div><div class=\"value\">{c6['NH4_O']['omega_one_balanced_accuracy']:.3f}</div><div class=\"detail\">Balanced accuracy at Omega = 1</div></div>
  </div>
  <div class=\"metric-line\"><span style=\"width:180px\">Omega AUC advantage</span><div class=\"bar\"><div class=\"fill\" style=\"width:{min(100, c6['NH4_O']['auc_delta']/0.08*100):.1f}%\"></div></div><span>{c6['NH4_O']['auc_delta']:.3f} / 0.080 required</span></div>
  <div class=\"metric-line\"><span style=\"width:180px\">Robustness blocks</span><div class=\"bar\"><div class=\"fill\" style=\"width:{c6['NH4_O']['positive_robustness_blocks']/5*100:.1f}%\"></div></div><span>{c6['NH4_O']['positive_robustness_blocks']} / 5, with 4 required</span></div>
  <div class=\"figure-grid\">
    <div><div class=\"figure\"><img src=\"{images['c6_omega']}\" alt=\"Omega transition\"></div><div class=\"caption\">Held-out failure rate as cumulative reflected overload increases.</div></div>
    <div><div class=\"figure\"><img src=\"{images['c6_compare']}\" alt=\"Lambda versus Omega\"></div><div class=\"caption\">Instantaneous admission pressure compared with accumulated assurance backlog.</div></div>
  </div>
  <div class=\"callout\"><strong>Engineering consequence.</strong> A control plane should measure admission work and queue accumulation, not only fleet size or peak spawn rate. The current coefficients and threshold remain notional and require prospective calibration.</div>
</section>

<section id=\"provenance\" class=\"tab\">
  <h2>Reproducibility and provenance</h2>
  <div class=\"grid\">
    <div class=\"card\"><div class=\"label\">Cycle 7 frozen inputs</div><div class=\"value\">{len(m7['frozen_input_checks'])}</div><div class=\"detail\">All matched before execution</div></div>
    <div class=\"card\"><div class=\"label\">Cycle 7 replications</div><div class=\"value\">{c7['dataset_counts']['replications']:,}</div><div class=\"detail\">Across {c7['dataset_counts']['scenarios']:,} scenarios</div></div>
    <div class=\"card\"><div class=\"label\">Execution environment</div><div class=\"value\">Python {m7['environment']['python'].split()[0]}</div><div class=\"detail\">NumPy {m7['environment']['packages']['numpy']}, SciPy {m7['environment']['packages']['scipy']}</div></div>
    <div class=\"card\"><div class=\"label\">Cycle 7 decision</div><div class=\"value\">Not supported</div><div class=\"detail\">Decision preserved despite positive pooled MAE evidence</div></div>
  </div>
  <h3>Cycle 7 frozen input checks</h3>
  <table><thead><tr><th>Artifact</th><th>Result</th><th>SHA-256 prefix</th></tr></thead><tbody>{hash_rows}</tbody></table>
  <h3>Evidence integrity rules</h3>
  <ul>
    <li>Cycle 4 is diagnostic only because a frozen source hash did not match.</li>
    <li>Cycle 5 is an independent-seed exact replication and is retained.</li>
    <li>Cycles 6 and 7 are hash-gated preregistered executions.</li>
    <li>All operational parameters remain labeled notional.</li>
    <li>No negative result was converted to support by changing a threshold after execution.</li>
  </ul>
  <details><summary>Embedded manifest and summaries</summary><pre id=\"jsonView\"></pre></details>
</section>

<section id=\"novelty\" class=\"tab\">
  <h2>Novelty boundary and research decision</h2>
  <div class=\"callout\"><strong>What is established prior art.</strong> Next-generation matrices, non-backtracking thresholds, message passing, temporal infection propagators, stochastic outbreak and final-size separation, reflected-fluid queues, authorization graphs, and agent dependency graphs.</div>
  <h3>Potentially defensible contribution</h3>
  <p>A runtime-agnostic assurance experiment framework that maps authorization, communications, common dependencies, supervision, credentials, response timing, and finite assurance-processing resources into separate compromise-initiation, compromise-severity, and fleet-admission models, then evaluates those models under prospective hash-gated protocols.</p>
  <h3>What remains unestablished</h3>
  <ul>
    <li>No universal fleet assurance law.</li>
    <li>No operationally validated attack-reachability operator.</li>
    <li>No calibrated universal Omega threshold.</li>
    <li>No assurance recommendation for 10,000 agents.</li>
    <li>No patentability or priority determination.</li>
  </ul>
  <h3>Recommended next decision</h3>
  <p>Move Omega from synthetic exploration to measured control-plane calibration. For compromise prediction, test phase-separated dynamic message passing against static non-backtracking on externally generated or measured traces. More synthetic tuning of scalar spectral scores has low expected value.</p>
</section>
</main>
<footer>Generated from immutable Stage 2 result summaries and the Cycle 7 execution manifest. This console performs no network calls and embeds all displayed figures.</footer>
<script>
const DATA = {embedded_json};
const buttons = document.querySelectorAll('nav button');
const tabs = document.querySelectorAll('section.tab');
buttons.forEach(button => button.addEventListener('click', () => {{
  buttons.forEach(b => b.classList.remove('active'));
  tabs.forEach(t => t.classList.remove('active'));
  button.classList.add('active');
  document.getElementById(button.dataset.tab).classList.add('active');
  window.scrollTo({{top: 0, behavior: 'smooth'}});
}}));
document.getElementById('jsonView').textContent = JSON.stringify(DATA, null, 2);
function downloadEvidence() {{
  const blob = new Blob([JSON.stringify(DATA, null, 2)], {{type: 'application/json'}});
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'stage2_embedded_evidence.json';
  link.click();
  URL.revokeObjectURL(link.href);
}}
</script>
</body>
</html>
"""

if "—" in page:
    raise RuntimeError("em dash detected in generated console")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(page, encoding="utf-8")
print(OUT)
print(f"bytes={OUT.stat().st_size}")
