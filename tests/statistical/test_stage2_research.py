import numpy as np
import pandas as pd

from fleet_sim.experiments.stage2_research import (
    _build_directed_layers,
    _nh2_split,
    _nh4_split,
    _roc_auc,
    evaluate_nh2_predictors,
    evaluate_nh4_predictors,
)


def test_directed_layer_builder_is_seed_reproducible():
    _, first = _build_directed_layers(
        48,
        auth_family="random_regular",
        dependency_family="erdos_renyi",
        segmentation="partitioned",
        seed=71,
    )
    _, second = _build_directed_layers(
        48,
        auth_family="random_regular",
        dependency_family="erdos_renyi",
        segmentation="partitioned",
        seed=71,
    )
    assert set(first) == {
        "authorization",
        "communication",
        "dependency",
        "supervision",
    }
    for name in first:
        assert first[name].is_directed()
        assert set(first[name].edges()) == set(second[name].edges())


def test_stage2_partition_rules_are_fixed_and_disjoint():
    assert _nh2_split(160, "random_regular") == "train"
    assert _nh2_split(640, "barabasi_albert") == "test"
    assert _nh2_split(320, "hierarchical") == "calibration"
    assert _nh4_split(2_000, "linear") == "train"
    assert _nh4_split(20_000, "pulse_train") == "test"
    assert _nh4_split(10_000, "back_loaded") == "calibration"


def test_nh2_predictor_evaluator_executes_on_scenario_units():
    rng = np.random.default_rng(17)
    rows = []
    predictors = [
        "raw_auth_radius",
        "sym_attack_radius",
        "static_k_radius",
        "nonbacktracking_radius",
        "dynamic_excess_exposure",
        "dynamic_without_authorization",
        "dynamic_without_communication",
        "dynamic_without_dependency",
        "dynamic_without_supervision",
        "dynamic_homogeneous_recovery",
    ]
    for split, count in (("train", 30), ("test", 20)):
        for _ in range(count):
            latent = float(rng.uniform(0.0, 3.0))
            row = {
                "split": split,
                "mean_ever_fraction": float(np.clip(0.04 + 0.20 * latent + rng.normal(0, 0.03), 0, 1)),
                "outbreak_successes": int(np.clip(round(30 * min(1.0, latent / 2.5)), 0, 30)),
                "outbreak_rate": float(np.clip(latent / 2.5, 0, 1)),
                "replications": 30,
            }
            for index, name in enumerate(predictors):
                row[name] = max(0.0, latent * (1.0 + 0.02 * index) + rng.normal(0, 0.04))
            rows.append(row)
    metrics, fitted = evaluate_nh2_predictors(pd.DataFrame(rows))
    assert len(metrics) == 10
    assert set(metrics.predictor) == {
        "raw_authorization",
        "symmetrized_attack",
        "static_next_generation",
        "nonbacktracking",
        "dynamic_k",
        "ablate_authorization",
        "ablate_communication",
        "ablate_dependency",
        "ablate_supervision",
        "homogeneous_recovery",
    }
    assert len(fitted["dynamic_k"]["final_prediction"]) == 20
    assert np.isfinite(metrics.test_mae_mean_ever).all()


def test_nh4_predictor_evaluator_executes_and_auc_is_well_formed():
    rng = np.random.default_rng(29)
    rows = []
    for split, count in (("train", 36), ("test", 24)):
        for _ in range(count):
            omega = float(rng.uniform(0.0, 2.5))
            failure_rate = float(np.clip((omega - 0.45) / 1.4, 0, 1))
            rows.append(
                {
                    "split": split,
                    "final_n": int(rng.choice([2_000, 5_000, 10_000, 20_000])),
                    "max_admission_rate": float(rng.uniform(2, 80)),
                    "peak_lambda": float(max(0.0, omega + rng.normal(0, 0.30))),
                    "omega": omega,
                    "failure_successes": int(round(30 * failure_rate)),
                    "failure_rate": failure_rate,
                    "replications": 30,
                }
            )
    metrics, fitted = evaluate_nh4_predictors(pd.DataFrame(rows))
    assert len(metrics) == 5
    assert len(fitted["omega"]["probability"]) == 24
    assert metrics.test_auc_majority_failure.between(0.0, 1.0).all()
    assert np.isclose(_roc_auc(np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.8, 0.9])), 1.0)
