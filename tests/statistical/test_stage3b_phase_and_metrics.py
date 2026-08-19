from dataclasses import replace

import numpy as np
import pytest

from fleet_sim.analysis.phase_separated import (
    PhaseSeparatedRecord,
    fit_phase_separated,
    predict_phase_separated,
)
from fleet_sim.analysis.predictive_metrics import (
    binary_predictive_metrics,
    continuous_predictive_metrics,
)
from fleet_sim.experiments.stage3b import (
    evaluate_phase_model,
    fit_and_evaluate_stage3b,
    stage3b_comparator_specs,
)


def _features(value: float) -> dict[str, float]:
    return {
        "dmp_outbreak_probability": value,
        "node_hazard_aggregation": 0.1 + 0.8 * value,
        "temporal_propagator": 0.7 + value,
        "dmp_expected_fraction": 0.02 + 0.65 * value,
        "reachable_component_fraction": 0.15 + 0.75 * value,
        "directed_percolation_fraction": 0.10 + 0.70 * value,
        "static_adjacency": value,
        "static_nonbacktracking": value**2,
        "combined_scalar": 0.5 + value,
        "authorization_only": 0.2 + 0.5 * value,
        "communication_only": 1.0 - 0.4 * value,
        "simple_reproduction": 0.1 + value**3,
    }


def _records(split: str, count: int, offset: int) -> list[PhaseSeparatedRecord]:
    records = []
    for index, value in enumerate(np.linspace(0.02, 0.98, count)):
        outbreak = int(value >= 0.50)
        final = 0.01 if not outbreak else 0.18 + 0.60 * float(value)
        records.append(
            PhaseSeparatedRecord(
                record_id=f"{split}-{offset + index}",
                scenario_id=f"scenario-{split}-{index // 2}",
                split=split,
                block=index % 2,
                n_agents=100 + 100 * (index % 2),
                topology="random_regular" if index % 2 == 0 else "erdos_renyi",
                attack_class="direct_exploit" if index % 2 == 0 else "credential_replay",
                segmentation_policy="none" if index % 2 == 0 else "partitioned_8_way",
                features=_features(float(value)),
                outbreak=outbreak,
                final_compromise_fraction=final,
                replication_seed=10_000 + offset + index,
                defense_case="nominal" if index % 2 == 0 else "slow_response",
            )
        )
    return records


def test_phase_separated_fit_uses_declared_partitions_and_predictions_are_bounded():
    exploratory = _records("exploratory", 12, 0)
    calibration = _records("calibration", 10, 100)
    heldout = _records("heldout", 10, 200)
    model = fit_phase_separated(
        exploratory,
        calibration,
        initiation_features=("dmp_outbreak_probability", "node_hazard_aggregation"),
        severity_features=("dmp_expected_fraction", "reachable_component_fraction"),
    )
    prediction = predict_phase_separated(model, heldout)
    assert all(record.record_id not in model.fit_record_ids for record in heldout)
    assert np.all((prediction.outbreak_probability >= 0.0) & (prediction.outbreak_probability <= 1.0))
    assert np.all((prediction.conditional_severity >= 0.0) & (prediction.conditional_severity <= 1.0))
    assert np.all(
        (prediction.conditional_nonoutbreak_severity >= 0.0)
        & (prediction.conditional_nonoutbreak_severity <= 1.0)
    )
    assert np.all((prediction.expected_final_fraction >= 0.0) & (prediction.expected_final_fraction <= 1.0))
    assert np.all(
        prediction.expected_final_fraction_lower <= prediction.expected_final_fraction
    )
    assert np.all(
        prediction.expected_final_fraction <= prediction.expected_final_fraction_upper
    )
    inverse_population = np.asarray([1.0 / record.n_agents for record in heldout])
    assert not np.allclose(prediction.conditional_nonoutbreak_severity, inverse_population)

    leaked = replace(heldout[0], record_id=exploratory[0].record_id)
    with pytest.raises(ValueError, match="overlap"):
        predict_phase_separated(model, [leaked, *heldout[1:]])


def test_predictive_metrics_cover_calibration_discrimination_and_intervals():
    binary = binary_predictive_metrics(
        np.array([0, 0, 1, 1]), np.array([0.0, 0.1, 0.9, 1.0]), bins=4
    )
    assert binary.roc_auc == 1.0
    assert binary.precision_recall_auc == 1.0
    assert binary.brier_score < 0.01
    assert len(binary.reliability) > 0

    continuous = continuous_predictive_metrics(
        np.array([0.2, 0.5, 0.8]),
        np.array([0.2, 0.4, 0.9]),
        lower=np.array([0.1, 0.3, 0.7]),
        upper=np.array([0.3, 0.6, 1.0]),
    )
    assert np.isclose(continuous.mean_absolute_error, 0.2 / 3.0)
    assert continuous.interval_coverage == 1.0


def test_binary_log_loss_uses_preregistered_probability_clipping():
    metrics = binary_predictive_metrics(
        np.asarray([0, 1]),
        np.asarray([1.0, 0.0]),
    )
    assert np.isclose(metrics.log_loss, -np.log(1e-6))


def test_precision_recall_auc_is_invariant_to_permutations_with_tied_scores():
    observed = np.asarray([1, 0, 1, 0, 1, 0, 0, 1])
    probability = np.asarray([0.9, 0.9, 0.5, 0.5, 0.5, 0.5, 0.1, 0.1])
    expected = binary_predictive_metrics(observed, probability).precision_recall_auc
    rng = np.random.default_rng(20260819)
    for _ in range(50):
        order = rng.permutation(len(observed))
        actual = binary_predictive_metrics(
            observed[order], probability[order]
        ).precision_recall_auc
        assert actual == expected


def test_binary_evaluation_and_model_calibration_require_both_outcome_classes():
    with pytest.raises(ValueError, match="both outcome classes"):
        binary_predictive_metrics(np.asarray([0, 0, 0]), np.asarray([0.1, 0.2, 0.3]))

    exploratory = _records("exploratory", 12, 0)
    calibration = [
        replace(record, outbreak=1, final_compromise_fraction=0.5)
        for record in _records("calibration", 10, 100)
    ]
    with pytest.raises(ValueError, match="calibration partition requires both"):
        fit_phase_separated(
            exploratory,
            calibration,
            initiation_features=("dmp_outbreak_probability",),
            severity_features=("dmp_expected_fraction",),
        )

    valid_calibration = _records("calibration", 10, 100)
    model = fit_phase_separated(
        exploratory,
        valid_calibration,
        initiation_features=("dmp_outbreak_probability",),
        severity_features=("dmp_expected_fraction",),
    )
    one_class_heldout = [
        replace(record, outbreak=0, final_compromise_fraction=0.01)
        for record in _records("heldout", 10, 200)
    ]
    with pytest.raises(ValueError, match="held-out evaluation requires both"):
        evaluate_phase_model("candidate", model, one_class_heldout)


def test_static_baseline_selection_is_calibration_only_and_exposes_heldout_predictions():
    exploratory = _records("exploratory", 12, 0)
    calibration = _records("calibration", 10, 100)
    heldout = _records("heldout", 10, 200)
    original = fit_and_evaluate_stage3b([*exploratory, *calibration, *heldout])

    changed_heldout = [
        replace(
            record,
            outbreak=1 - record.outbreak,
            final_compromise_fraction=0.75 if not record.outbreak else 0.02,
        )
        for record in heldout
    ]
    changed = fit_and_evaluate_stage3b(
        [*exploratory, *calibration, *changed_heldout]
    )
    assert original.selection_partition == "calibration"
    assert original.selection_method == "leave_one_block_out_calibration_crossfit"
    assert original.strongest_final_size_baseline == changed.strongest_final_size_baseline
    assert original.strongest_initiation_baseline == changed.strongest_initiation_baseline
    assert set(original.baseline_predictions) == {
        original.strongest_final_size_baseline,
        original.strongest_initiation_baseline,
    }
    assert isinstance(original.positive_final_size_blocks, int)
    assert isinstance(original.positive_outbreak_brier_blocks, int)
    assert original.heldout_binary_support_by_block == {0: True, 1: True}
    assert original.valid_binary_support_blocks == 2
    assert original.candidate_model.initiation.feature_names == (
        "dmp_outbreak_probability",
    )
    assert original.candidate_model.severity.feature_names == ("dmp_expected_fraction",)
    assert original.candidate_model.nonoutbreak_severity.feature_names == (
        "dmp_expected_fraction",
    )
    changed_non_dmp = []
    for record in heldout:
        features = dict(record.features)
        for name in set(features).difference(
            {"dmp_outbreak_probability", "dmp_expected_fraction"}
        ):
            features[name] += 100.0
        changed_non_dmp.append(replace(record, features=features))
    dmp_only_prediction = predict_phase_separated(
        original.candidate_model, changed_non_dmp
    )
    np.testing.assert_array_equal(
        original.candidate_prediction.outbreak_probability,
        dmp_only_prediction.outbreak_probability,
    )
    np.testing.assert_array_equal(
        original.candidate_prediction.expected_final_fraction,
        dmp_only_prediction.expected_final_fraction,
    )
    assert all(
        score.validation_blocks == (0, 1)
        for score in original.baseline_selection_scores.values()
    )
    assert set(original.baseline_selection_scores) == {
        spec.name for spec in stage3b_comparator_specs()
    }
    calibration_ids = {record.record_id for record in calibration}
    assert all(
        calibration_ids.issubset(model.fit_record_ids)
        for model in original.baseline_models.values()
    )


def test_comparator_registry_is_fair_and_keeps_temporal_out_of_candidate():
    specs = {spec.name: spec for spec in stage3b_comparator_specs()}
    assert {
        "temporal_propagator",
        "node_hazard_aggregation",
        "static_adjacency",
        "static_nonbacktracking",
        "combined_scalar",
        "authorization_only",
        "communication_only",
        "simple_reproduction",
        "interpretable_multivariate_non_dmp",
    } == set(specs)
    multivariate = specs["interpretable_multivariate_non_dmp"]
    assert len(multivariate.initiation_features) > 1
    assert all(not feature.startswith("dmp_") for feature in multivariate.initiation_features)
    assert specs["temporal_propagator"].model_class == "univariate"


def test_comparator_crossfit_requires_multiple_calibration_blocks():
    exploratory = _records("exploratory", 12, 0)
    calibration = [
        replace(record, block=0) for record in _records("calibration", 10, 100)
    ]
    heldout = _records("heldout", 10, 200)
    with pytest.raises(ValueError, match="at least two calibration blocks"):
        fit_and_evaluate_stage3b([*exploratory, *calibration, *heldout])


def test_stage3b_reports_invalid_binary_support_per_heldout_block():
    exploratory = _records("exploratory", 12, 0)
    calibration = _records("calibration", 10, 100)
    heldout = [
        replace(record, block=record.outbreak)
        for record in _records("heldout", 10, 200)
    ]
    result = fit_and_evaluate_stage3b([*exploratory, *calibration, *heldout])
    assert result.heldout_binary_support_by_block == {0: False, 1: False}
    assert result.valid_binary_support_blocks == 0
