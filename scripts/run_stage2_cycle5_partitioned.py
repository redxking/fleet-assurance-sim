from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

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
from fleet_sim.security.attack_operator import clear_operator_caches

PROTOCOL_ID = "FAS-S2-C5-2026-08-19"
SEED = 20260820
MANIFEST = ROOT / "manifests" / "stage2_cycle5_preregistration_manifest.json"
RESULTS = ROOT / "results" / "stage2_cycle5"
PARTIALS = RESULTS / "partials"
FIGURES = ROOT / "figures" / "stage2_cycle5"
EXECUTION_MANIFEST = ROOT / "manifests" / "stage2_cycle5_execution_manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_frozen_inputs() -> dict[str, bool]:
    prereg = json.loads(MANIFEST.read_text(encoding="utf-8"))
    checks = {
        relative: sha256(ROOT / relative) == expected
        for relative, expected in prereg["files"].items()
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(f"frozen input hash gate failed: {failed}")
    return checks


def write_block_manifest(block: str, started: float, payload: dict[str, object]) -> None:
    PARTIALS.mkdir(parents=True, exist_ok=True)
    body = {
        "protocol_id": PROTOCOL_ID,
        "block": block,
        "status": "complete",
        "runtime_seconds": time.perf_counter() - started,
        **payload,
    }
    (PARTIALS / f"{block}_manifest.json").write_text(
        json.dumps(body, indent=2, allow_nan=True), encoding="utf-8"
    )


def run_nh2_size(n: int) -> None:
    offsets = {160: (0, 0), 320: (24, 384), 640: (48, 768)}
    structure_offset, scenario_offset = offsets[n]
    started = time.perf_counter()
    clear_operator_caches()
    rep, scenarios = generate_nh2_matrix(
        seed=SEED,
        replications=30,
        size_subset=(n,),
        initial_structure_id=structure_offset,
        initial_scenario_id=scenario_offset,
    )
    PARTIALS.mkdir(parents=True, exist_ok=True)
    rep_path = PARTIALS / f"nh2_n{n}_replications.csv"
    scenario_path = PARTIALS / f"nh2_n{n}_scenarios.csv"
    rep.to_csv(rep_path, index=False)
    scenarios.to_csv(scenario_path, index=False)
    write_block_manifest(
        f"nh2_n{n}",
        started,
        {
            "seed": SEED,
            "replications": len(rep),
            "scenarios": len(scenarios),
            "scenario_id_min": int(scenarios.scenario_id.min()),
            "scenario_id_max": int(scenarios.scenario_id.max()),
            "artifacts": {
                str(rep_path.relative_to(ROOT)): sha256(rep_path),
                str(scenario_path.relative_to(ROOT)): sha256(scenario_path),
            },
        },
    )


def run_nh2_robustness_block() -> None:
    started = time.perf_counter()
    clear_operator_caches()
    frame = run_nh2_robustness(seed=SEED + 3001)
    PARTIALS.mkdir(parents=True, exist_ok=True)
    path = PARTIALS / "nh2_robustness.csv"
    frame.to_csv(path, index=False)
    write_block_manifest(
        "nh2_robustness",
        started,
        {"blocks": len(frame), "artifact": {str(path.relative_to(ROOT)): sha256(path)}},
    )


def run_nh4_primary() -> None:
    started = time.perf_counter()
    rep, scenarios = generate_nh4_matrix(seed=SEED + 5001, replications=30)
    PARTIALS.mkdir(parents=True, exist_ok=True)
    rep_path = PARTIALS / "nh4_admission_replications.csv"
    scenario_path = PARTIALS / "nh4_admission_scenarios.csv"
    rep.to_csv(rep_path, index=False)
    scenarios.to_csv(scenario_path, index=False)
    write_block_manifest(
        "nh4_primary",
        started,
        {
            "replications": len(rep),
            "scenarios": len(scenarios),
            "artifacts": {
                str(rep_path.relative_to(ROOT)): sha256(rep_path),
                str(scenario_path.relative_to(ROOT)): sha256(scenario_path),
            },
        },
    )


def run_nh4_robustness_block() -> None:
    started = time.perf_counter()
    scenarios = pd.read_csv(PARTIALS / "nh4_admission_scenarios.csv")
    _, fitted = evaluate_nh4_predictors(scenarios)
    frame = run_nh4_robustness(scenarios, fitted, seed=SEED + 7001)
    path = PARTIALS / "nh4_robustness.csv"
    frame.to_csv(path, index=False)
    write_block_manifest(
        "nh4_robustness",
        started,
        {"blocks": len(frame), "artifact": {str(path.relative_to(ROOT)): sha256(path)}},
    )


def finalize() -> None:
    started = time.perf_counter()
    RESULTS.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    required_blocks = [
        "nh2_n160", "nh2_n320", "nh2_n640", "nh2_robustness",
        "nh4_primary", "nh4_robustness",
    ]
    missing = [name for name in required_blocks if not (PARTIALS / f"{name}_manifest.json").exists()]
    if missing:
        raise RuntimeError(f"missing completed blocks: {missing}")

    nh2_rep = pd.concat(
        [pd.read_csv(PARTIALS / f"nh2_n{n}_replications.csv") for n in (160, 320, 640)],
        ignore_index=True,
    ).sort_values(["scenario_id", "replication"]).reset_index(drop=True)
    nh2_scenarios = pd.concat(
        [pd.read_csv(PARTIALS / f"nh2_n{n}_scenarios.csv") for n in (160, 320, 640)],
        ignore_index=True,
    ).sort_values("scenario_id").reset_index(drop=True)
    if len(nh2_rep) != 34_560 or len(nh2_scenarios) != 1_152:
        raise RuntimeError("NH2 partition counts do not match the frozen matrix")
    if nh2_scenarios.scenario_id.tolist() != list(range(1_152)):
        raise RuntimeError("NH2 scenario identifiers are not contiguous")
    nh2_rep.to_csv(RESULTS / "nh2_directed_replications.csv", index=False)
    nh2_scenarios.to_csv(RESULTS / "nh2_directed_scenarios.csv", index=False)
    nh2_metrics, nh2_fitted = evaluate_nh2_predictors(nh2_scenarios)
    nh2_metrics.to_csv(RESULTS / "nh2_predictor_metrics.csv", index=False)
    nh2_robustness = pd.read_csv(PARTIALS / "nh2_robustness.csv")
    nh2_robustness.to_csv(RESULTS / "nh2_robustness.csv", index=False)
    nh2_summary = summarize_nh2(nh2_scenarios, nh2_metrics, nh2_fitted, nh2_robustness, seed=SEED)

    nh4_rep = pd.read_csv(PARTIALS / "nh4_admission_replications.csv")
    nh4_scenarios = pd.read_csv(PARTIALS / "nh4_admission_scenarios.csv")
    nh4_rep.to_csv(RESULTS / "nh4_admission_replications.csv", index=False)
    nh4_scenarios.to_csv(RESULTS / "nh4_admission_scenarios.csv", index=False)
    nh4_metrics, nh4_fitted = evaluate_nh4_predictors(nh4_scenarios)
    nh4_metrics.to_csv(RESULTS / "nh4_predictor_metrics.csv", index=False)
    thresholds = nh4_threshold_table(nh4_scenarios)
    thresholds.to_csv(RESULTS / "nh4_thresholds.csv", index=False)
    nh4_robustness = pd.read_csv(PARTIALS / "nh4_robustness.csv")
    nh4_robustness.to_csv(RESULTS / "nh4_robustness.csv", index=False)
    nh4_summary = summarize_nh4(
        nh4_scenarios, nh4_metrics, nh4_fitted, thresholds, nh4_robustness, seed=SEED
    )
    figures = write_stage2_figures(
        nh2_scenarios, nh2_metrics, nh2_fitted, nh4_scenarios, nh4_metrics, FIGURES
    )
    assessments = [
        HypothesisAssessment(
            hypothesis="NH2-D",
            supported_in_model=bool(nh2_summary["supported_in_model"]),
            evidence_level="model-conditioned independent-seed replication",
            primary_result=(
                f"Dynamic K(t) held-out MAE improvement "
                f"{100 * float(nh2_summary['mae_improvement_fraction']):.1f}% and "
                f"AUC delta {float(nh2_summary['auc_delta']):.3f}."
            ),
            limitations="Synthetic propagation substrate and notional parameters.",
        ).as_dict(),
        HypothesisAssessment(
            hypothesis="NH4-A",
            supported_in_model=bool(nh4_summary["supported_in_model"]),
            evidence_level="analytic plus model-conditioned independent-seed replication",
            primary_result=(
                f"Omega_A held-out AUC delta {float(nh4_summary['auc_delta']):.3f}, "
                f"Brier improvement {100 * float(nh4_summary['brier_improvement_fraction']):.1f}%."
            ),
            limitations="Synthetic queue substrate and notional service parameters.",
        ).as_dict(),
    ]
    summary = {
        "date": "2026-08-19",
        "cycle": "Stage 2 Cycle 5",
        "replication_of": "Stage 2 Cycle 4",
        "seed": SEED,
        "evidence_scope": "notional parameters; model-conditioned independent-seed replication; no external validation",
        "protocol": "docs/stage2_cycle5_replication_protocol.md",
        "execution_mode": "hash-gated atomic size partitions",
        "NH2_D": nh2_summary,
        "NH4_A": nh4_summary,
        "assessments": assessments,
        "figures": [str(path.relative_to(ROOT)) for path in figures],
        "dataset_counts": {
            "nh2_replications": len(nh2_rep), "nh2_scenarios": len(nh2_scenarios),
            "nh4_replications": len(nh4_rep), "nh4_scenarios": len(nh4_scenarios),
        },
    }
    summary_path = RESULTS / "stage2_cycle5_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, allow_nan=True), encoding="utf-8")
    artifacts = {
        str(path.relative_to(ROOT)): {"sha256": sha256(path), "bytes": path.stat().st_size}
        for path in sorted([*RESULTS.glob("*"), *FIGURES.glob("*")])
        if path.is_file()
    }
    block_manifests = {
        name: json.loads((PARTIALS / f"{name}_manifest.json").read_text(encoding="utf-8"))
        for name in required_blocks
    }
    EXECUTION_MANIFEST.write_text(
        json.dumps(
            {
                "protocol_id": PROTOCOL_ID,
                "primary_seed": SEED,
                "execution_exit_code": 0,
                "frozen_input_hashes_verified": verify_frozen_inputs(),
                "all_frozen_inputs_match": True,
                "execution_mode": "hash-gated atomic size partitions",
                "finalization_runtime_seconds": time.perf_counter() - started,
                "environment": {"python": sys.version, "platform": platform.platform()},
                "block_manifests": block_manifests,
                "artifacts": artifacts,
                "summary": summary,
            },
            indent=2,
            allow_nan=True,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, allow_nan=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "block",
        choices=["nh2-160", "nh2-320", "nh2-640", "nh2-robustness", "nh4-primary", "nh4-robustness", "finalize"],
    )
    args = parser.parse_args()
    verify_frozen_inputs()
    if args.block.startswith("nh2-") and args.block[4:].isdigit():
        run_nh2_size(int(args.block[4:]))
    elif args.block == "nh2-robustness":
        run_nh2_robustness_block()
    elif args.block == "nh4-primary":
        run_nh4_primary()
    elif args.block == "nh4-robustness":
        run_nh4_robustness_block()
    else:
        finalize()


if __name__ == "__main__":
    main()
