"""Stage 2 Cycle 5 exact independent-seed replication.

Cycle 5 repeats the Stage 2 Cycle 4 equations, matrix, splits, acceptance
criteria, and reporting logic with a new primary seed and a pre-execution hash
gate. Cycle 4 is retained as diagnostic evidence because its execution manifest
identified frozen-input mismatches.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from fleet_sim.experiments.stage2_research import (
    HypothesisAssessment,
    evaluate_nh2_predictors,
    evaluate_nh4_predictors,
    generate_nh2_matrix,
    generate_nh4_matrix,
    nh4_threshold_table,
    run_nh2_robustness,
    run_nh4_robustness,
    summarize_nh2,
    summarize_nh4,
    write_stage2_figures,
)


def run_stage2_cycle5(
    repository_root: str | Path,
    *,
    seed: int = 20260820,
) -> dict[str, object]:
    """Run the exact Cycle 4 design under the Cycle 5 replication identifier."""
    root = Path(repository_root)
    results_dir = root / "results" / "stage2_cycle5"
    figures_dir = root / "figures" / "stage2_cycle5"
    results_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    nh2_rep, nh2_scenarios = generate_nh2_matrix(seed=seed, replications=30)
    nh2_rep.to_csv(results_dir / "nh2_directed_replications.csv", index=False)
    nh2_scenarios.to_csv(results_dir / "nh2_directed_scenarios.csv", index=False)
    nh2_metrics, nh2_fitted = evaluate_nh2_predictors(nh2_scenarios)
    nh2_metrics.to_csv(results_dir / "nh2_predictor_metrics.csv", index=False)
    nh2_robustness = run_nh2_robustness(seed=seed + 3001)
    nh2_robustness.to_csv(results_dir / "nh2_robustness.csv", index=False)
    nh2_summary = summarize_nh2(
        nh2_scenarios,
        nh2_metrics,
        nh2_fitted,
        nh2_robustness,
        seed=seed,
    )

    nh4_rep, nh4_scenarios = generate_nh4_matrix(seed=seed + 5001, replications=30)
    nh4_rep.to_csv(results_dir / "nh4_admission_replications.csv", index=False)
    nh4_scenarios.to_csv(results_dir / "nh4_admission_scenarios.csv", index=False)
    nh4_metrics, nh4_fitted = evaluate_nh4_predictors(nh4_scenarios)
    nh4_metrics.to_csv(results_dir / "nh4_predictor_metrics.csv", index=False)
    nh4_thresholds = nh4_threshold_table(nh4_scenarios)
    nh4_thresholds.to_csv(results_dir / "nh4_thresholds.csv", index=False)
    nh4_robustness = run_nh4_robustness(
        nh4_scenarios,
        nh4_fitted,
        seed=seed + 7001,
    )
    nh4_robustness.to_csv(results_dir / "nh4_robustness.csv", index=False)
    nh4_summary = summarize_nh4(
        nh4_scenarios,
        nh4_metrics,
        nh4_fitted,
        nh4_thresholds,
        nh4_robustness,
        seed=seed,
    )

    figures = write_stage2_figures(
        nh2_scenarios,
        nh2_metrics,
        nh2_fitted,
        nh4_scenarios,
        nh4_metrics,
        figures_dir,
    )

    assessments = [
        HypothesisAssessment(
            hypothesis="NH2-D",
            supported_in_model=bool(nh2_summary["supported_in_model"]),
            evidence_level="model-conditioned independent-seed replication",
            primary_result=(
                f"Dynamic K(t) held-out MAE improvement "
                f"{100 * float(nh2_summary['mae_improvement_fraction']):.1f}% "
                f"and AUC delta {float(nh2_summary['auc_delta']):.3f}."
            ),
            limitations=(
                "The propagation substrate remains synthetic. Candidate features are "
                "separated from latent hazards, but no observed incident data are used."
            ),
        ).as_dict(),
        HypothesisAssessment(
            hypothesis="NH4-A",
            supported_in_model=bool(nh4_summary["supported_in_model"]),
            evidence_level="analytic plus model-conditioned independent-seed replication",
            primary_result=(
                f"Omega_A held-out AUC delta {float(nh4_summary['auc_delta']):.3f}, "
                f"Brier improvement "
                f"{100 * float(nh4_summary['brier_improvement_fraction']):.1f}%."
            ),
            limitations=(
                "The reflected backlog formula is established queue mathematics. Novelty, "
                "if any, is limited to its assurance-resource composition and transfer behavior."
            ),
        ).as_dict(),
    ]

    summary = {
        "date": "2026-08-19",
        "cycle": "Stage 2 Cycle 5",
        "replication_of": "Stage 2 Cycle 4",
        "seed": seed,
        "evidence_scope": (
            "notional parameters; model-conditioned independent-seed replication; "
            "no external validation"
        ),
        "protocol": "docs/stage2_cycle5_replication_protocol.md",
        "NH2_D": nh2_summary,
        "NH4_A": nh4_summary,
        "assessments": assessments,
        "figures": [str(path.relative_to(root)) for path in figures],
        "dataset_counts": {
            "nh2_replications": len(nh2_rep),
            "nh2_scenarios": len(nh2_scenarios),
            "nh4_replications": len(nh4_rep),
            "nh4_scenarios": len(nh4_scenarios),
        },
    }
    (results_dir / "stage2_cycle5_summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=True), encoding="utf-8"
    )
    return summary
