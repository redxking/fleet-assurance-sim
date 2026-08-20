"""Public-safe, offline status UI for the successor empirical study.

The UI is deliberately separate from the frozen Stage 3 evidence console. It
projects only aggregate, verified engineering evidence and never exposes raw
measurements, site or system aliases, collection timestamps, or local paths.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fleet_sim.empirical.assurance_campaign import (
    CampaignPackageVerification,
    verify_empirical_campaign_package,
)
from fleet_sim.empirical.calibration_gate import (
    EmpiricalCalibrationPackageVerification,
    IntervalEstimate,
    verify_empirical_calibration_package,
)
from fleet_sim.empirical.prediction_lock import (
    SuccessorPredictionLockPackageVerification,
    verify_successor_prediction_lock_package,
)
from fleet_sim.empirical.resource_adapter import (
    AdaptedResourcePackageVerification,
    verify_adapted_resource_bundle,
)
from fleet_sim.empirical.successor_protocol import (
    SuccessorEvaluationInputsPackageVerification,
    SuccessorRegistrationPackageVerification,
    verify_successor_evaluation_inputs_package,
    verify_successor_registration_package,
)

STATUS_SCHEMA_VERSION = "successor-study-status-v3"
STATUS_ASSET_NAMES = ("index.html", "successor-status.json")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
INTERVAL_FIELDS = (
    "background_work_per_agent_s",
    "admission_work_units_per_agent",
    "capacity_units_per_second",
    "service_time_window_mean_ms",
    "service_time_between_window_standard_deviation_ms",
    "max_wait_s",
    "dropped_work_fraction",
    "deferred_work_fraction",
)
PUBLIC_FORBIDDEN_KEYS = {
    "authorization_reference",
    "agents_admitted",
    "arrival_count",
    "adapter_bundle_id",
    "campaign_id",
    "calibration_fit_id",
    "cell_id",
    "cells",
    "contract_id",
    "criterion_id",
    "data_rights_reference",
    "dataset_id",
    "site_alias",
    "system_alias",
    "collection_start",
    "collection_end",
    "environment_description",
    "evaluation_campaign_id",
    "evaluation_input_id",
    "prediction_lock_id",
    "prediction_row_id",
    "prediction_parameter_draw_id",
    "parameter_draw_id",
    "fleet_size",
    "implementation",
    "model_id",
    "package_dir",
    "plan_id",
    "planned_collection_end_utc",
    "planned_collection_start_utc",
    "planned_blocks",
    "planned_evaluation_campaign_id",
    "planned_time_block_ids",
    "realized_cells",
    "realized_blocks",
    "registered_at_utc",
    "registration_id",
    "source_path",
    "source_campaign_id",
    "source_dataset_id",
    "local_path",
    "measurement_rows",
    "measurement_provenance",
    "policy_id",
    "raw_rows",
    "prediction_rows",
    "prediction_parameter_draws",
    "parameter_draws",
    "resource_parameters",
    "predicted_arrival_rate",
    "comparator_predicted_arrival_rate",
    "observed_arrival_rate",
    "residual",
    "scores",
    "score",
    "results",
    "result",
    "bootstrap_indices",
    "bootstrap_seed",
    "seed",
    "seeds",
    "candidate_formula",
    "candidate_model_id",
    "comparator_model_id",
    "prediction_formula",
    "comparator_formula",
    "resource_id",
    "adapter_policy_id",
    "study_id",
    "time_block_id",
    "timestamp_utc",
    "prediction_generated_at_utc",
    "prediction_locked_at_utc",
    "prediction_lock_created_at_utc",
    "locked_at_utc",
    "committed_at_utc",
    "outcome_release_at_utc",
    "custodian",
    "custodian_id",
    "signer",
    "signature",
    "receipt_id",
    "custody_reference",
    "window_duration_ms",
}
LOCAL_PATH_PATTERN = re.compile(
    r"(?:"
    r"~[/\\]"
    r"|(?<![A-Za-z0-9:/\\])/{1,2}[A-Za-z0-9._-]+(?:/[^\s,;:)\]}]*)?"
    r"|(?<![A-Za-z0-9.])\.{1,2}[/\\][^\s,;:)\]}]+"
    r"|\b[A-Za-z]:(?:[/\\][^\s,;:)\]}]*|[A-Za-z0-9._-][^\s,;:)\]}]*)"
    r"|\\\\[^\\\s]+\\[^\\\s]+"
    r")"
)
UTC_TIMESTAMP_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\b"
)


@dataclass(frozen=True, slots=True)
class SuccessorStatusBundle:
    """One strict, public-safe successor-study status projection."""

    payload: dict[str, Any]


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object, context: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{context} must be a lowercase SHA-256 digest")
    return value


def _finite_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    selected = float(value)
    return selected if math.isfinite(selected) else None


def _interval_payload(interval: IntervalEstimate | None) -> dict[str, float] | None:
    if interval is None:
        return None
    return {
        "lower": float(interval.lower),
        "point": float(interval.point),
        "upper": float(interval.upper),
    }


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{context} must be an object")
    return value


def _integer(value: object, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{context} must be an integer")
    if value < 0:
        raise ValueError(f"{context} must be nonnegative")
    return value


def _assert_public_safe(value: object, *, key: str = "root") -> None:
    """Reject accidental disclosure and non-JSON values in the projection."""

    if isinstance(value, Path):
        raise TypeError(f"public status payload contains a local path at {key}")
    if isinstance(value, Mapping):
        for child_key, child in value.items():
            name = str(child_key)
            if name.lower() in PUBLIC_FORBIDDEN_KEYS:
                raise ValueError(f"public status payload contains forbidden field: {name}")
            _assert_public_safe(child, key=f"{key}.{name}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_public_safe(child, key=f"{key}[{index}]")
        return
    if isinstance(value, str):
        if (
            value.strip() == "/"
            or value.startswith("file://")
            or LOCAL_PATH_PATTERN.search(value) is not None
        ):
            raise ValueError(f"public status payload contains a local path string at {key}")
        if UTC_TIMESTAMP_PATTERN.search(value) is not None:
            raise ValueError(f"public status payload contains a timestamp string at {key}")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"public status payload contains a nonfinite value at {key}")


def _campaign_projection(campaign: CampaignPackageVerification) -> dict[str, object]:
    evidence = campaign.evidence_manifest
    partitions = _mapping(evidence.get("partitions"), "campaign partitions")
    projected_partitions: dict[str, object] = {}
    for name in ("calibration", "heldout"):
        selected = _mapping(partitions.get(name), f"campaign {name} partition")
        projected_partitions[name] = {
            "content_sha256": _sha256(selected.get("content_sha256"), f"{name} content digest"),
            "row_count": _integer(selected.get("row_count"), f"{name} row count"),
            "time_block_count": _integer(
                selected.get("time_block_count"), f"{name} time-block count"
            ),
        }
    return {
        "evidence_scope": str(campaign.evidence_scope),
        "intake_contract_verified": True,
        "intake_status": str(evidence.get("intake_status", "unknown")),
        "evidence_manifest_sha256": campaign.evidence_manifest_sha256,
        "externally_digest_bound": campaign.externally_digest_bound,
        "external_validation": campaign.external_validation,
        "scientific_use_authorized": campaign.scientific_use_authorized,
        "partitions": projected_partitions,
    }


def _fit_projection(
    package: EmpiricalCalibrationPackageVerification,
) -> dict[str, object]:
    fit = package.fit
    resources: list[dict[str, object]] = []
    for resource in sorted(fit.resources, key=lambda item: item.resource_type):
        intervals = {name: _interval_payload(getattr(resource, name)) for name in INTERVAL_FIELDS}
        resources.append(
            {
                "resource_type": resource.resource_type,
                "gate_status": resource.gate_status,
                "blocking_reasons": list(resource.blocking_reasons),
                "observation_count": resource.observation_count,
                "time_block_count": resource.time_block_count,
                "fleet_size_range": [resource.fleet_size_min, resource.fleet_size_max],
                "admission_rate_range_per_s": [
                    resource.admission_rate_min_per_s,
                    resource.admission_rate_max_per_s,
                ],
                "scaled_design_rank": resource.scaled_design_rank,
                "scaled_design_condition_number": _finite_or_none(
                    resource.scaled_design_condition_number
                ),
                "weighted_normalized_rmse": _finite_or_none(resource.weighted_normalized_rmse),
                "absolute_weighted_relative_bias": _finite_or_none(
                    resource.absolute_weighted_relative_bias
                ),
                "weighted_r_squared": _finite_or_none(resource.weighted_r_squared),
                "bootstrap_success_fraction": resource.bootstrap_success_fraction,
                "parameter_class": resource.parameter_class,
                "intervals": intervals,
            }
        )
    return {
        "gate_status": fit.gate_status,
        "blocking_reasons": list(fit.blocking_reasons),
        "input_partition": fit.input_partition,
        "source_package_heldout_verified": fit.source_package_heldout_verified,
        "heldout_used_for_fit": fit.heldout_used_for_fit,
        "calibration_content_sha256": fit.calibration_content_sha256,
        "policy_sha256": fit.policy_sha256,
        "study_mode": fit.policy.study_mode,
        "fit_evidence_manifest_sha256": package.fit_evidence_manifest_sha256,
        "externally_digest_bound": package.externally_digest_bound,
        "interface_verification_ready": fit.interface_verification_ready,
        "eligible_for_adapter": fit.eligible_for_adapter,
        "runner_authorized": fit.runner_authorized,
        "scientific_use_authorized": fit.scientific_use_authorized,
        "external_validation": fit.external_validation,
        "global_criteria": [
            {
                "criterion": criterion.criterion_id,
                "state": criterion.state,
                "observed": criterion.observed,
                "operator": criterion.operator,
                "threshold": criterion.threshold,
                "reason": criterion.reason,
            }
            for criterion in fit.global_criteria
        ],
        "resource_status_counts": {
            state: sum(resource.gate_status == state for resource in fit.resources)
            for state in ("passed", "failed", "not_evaluable")
        },
        "resources": resources,
    }


def _adapter_projection(
    package: AdaptedResourcePackageVerification,
) -> dict[str, object]:
    bundle = package.bundle
    field_classes: dict[str, set[str]] = {}
    for item in bundle.field_provenance:
        field_classes.setdefault(item.field_name, set()).add(item.evidence_class)
    resources = []
    for resource in sorted(bundle.resources, key=lambda item: item.resource_type.value):
        spec = resource.to_dict()
        resources.append(
            {
                "resource_type": spec["resource_type"],
                "arrival_process": spec["arrival_process"],
                "service_time_distribution": spec["service_time_distribution"],
                "overload_behavior": spec["overload_behavior"],
                "capacity_units_per_second": spec["capacity_units_per_second"],
                "max_wait_s": spec["max_wait_s"],
                "parameter_class": spec["parameter_class"],
            }
        )
    return {
        "adapter_mode": bundle.adapter_mode,
        "adapter_policy_sha256": bundle.adapter_policy_sha256,
        "simulator_semantics_sha256": bundle.simulator_semantics_sha256,
        "specification_sha256": bundle.specification_sha256,
        "adapter_manifest_sha256": package.adapter_manifest_sha256,
        "externally_digest_bound": package.externally_digest_bound,
        "no_fallback": bundle.no_fallback,
        "source_package_heldout_verified": bundle.source_package_heldout_verified,
        "heldout_used_for_adapter": bundle.heldout_used_for_adapter,
        "external_validation": bundle.external_validation,
        "scientific_use_authorized": bundle.scientific_use_authorized,
        "runner_authorized": bundle.runner_authorized,
        "scientific_use": bundle.scientific_use,
        "simulator_limitations": list(bundle.simulator_limitations),
        "semantic_field_evidence_classes": {
            field: sorted(classes) for field, classes in sorted(field_classes.items())
        },
        "resources": resources,
    }


def _registration_projection(
    package: SuccessorRegistrationPackageVerification,
) -> dict[str, object]:
    registration = package.registration
    return {
        "registration_manifest_sha256": package.registration_manifest_sha256,
        "externally_digest_bound": package.externally_digest_bound,
        "registration_mode": registration.registration_mode,
        "planned_cell_count": registration.planned_cell_count,
        "planned_time_block_count": registration.planned_time_block_count,
        "source_campaign_evidence_manifest_sha256": (
            registration.source_campaign_evidence_manifest_sha256
        ),
        "fit_evidence_manifest_sha256": registration.fit_evidence_manifest_sha256,
        "adapter_manifest_sha256": registration.adapter_manifest_sha256,
        "plan_sha256": registration.plan_sha256,
        "transfer_contract_sha256": registration.transfer_contract_sha256,
        "implementation_sha256": registration.implementation_sha256,
        "chronology_consistent": registration.chronology_consistent,
        "registration_time_externally_attested": (
            registration.registration_time_externally_attested
        ),
        "upstream_chain_verified": registration.upstream_chain_verified,
        "prediction_formula_frozen": registration.prediction_formula_frozen,
        "criteria_frozen": package.contract.criteria_frozen,
        "numeric_thresholds_complete": package.contract.thresholds.complete,
        "operational_outcome_extension_enabled": (
            registration.operational_outcome_extension_enabled
        ),
        "execution_chain_ready": registration.execution_chain_ready,
        "external_validation": registration.external_validation,
        "scientific_use_authorized": registration.scientific_use_authorized,
        "runner_authorized": registration.runner_authorized,
    }


def _prediction_lock_projection(
    package: SuccessorPredictionLockPackageVerification,
) -> dict[str, object]:
    prediction_lock = package.lock
    return {
        "prediction_lock_manifest_sha256": package.prediction_lock_manifest_sha256,
        "externally_digest_bound": package.externally_digest_bound,
        "registration_manifest_sha256": prediction_lock.registration_manifest_sha256,
        "prediction_rows_content_sha256": prediction_lock.prediction_rows_content_sha256,
        "prediction_parameter_draws_content_sha256": (
            prediction_lock.prediction_parameter_draws_content_sha256
        ),
        "prediction_row_count": prediction_lock.prediction_row_count,
        "planned_cell_count": prediction_lock.planned_cell_count,
        "planned_time_block_count": prediction_lock.planned_time_block_count,
        "resource_count": prediction_lock.resource_count,
        "paired_bootstrap_replication_count": (prediction_lock.paired_bootstrap_replication_count),
        "upstream_chain_verified": prediction_lock.upstream_chain_verified,
        "registered_semantics_reconciled": (prediction_lock.registered_semantics_reconciled),
        "planned_predictor_design_reconciled": (
            prediction_lock.planned_predictor_design_reconciled
        ),
        "prediction_formula_frozen": prediction_lock.prediction_formula_frozen,
        "comparator_formula_frozen": prediction_lock.comparator_formula_frozen,
        "future_evaluation_campaign_not_supplied": (
            prediction_lock.future_evaluation_campaign_not_supplied
        ),
        "prediction_rows_target_free": prediction_lock.prediction_rows_target_free,
        "local_lock_chronology_consistent": (prediction_lock.local_lock_chronology_consistent),
        "workflow_prediction_commitment": prediction_lock.workflow_prediction_commitment,
        "prediction_rows_preoutcome_locked": (prediction_lock.prediction_rows_preoutcome_locked),
        "prediction_lock_time_externally_attested": (
            prediction_lock.prediction_lock_time_externally_attested
        ),
        "outcome_release_custody_verified": (prediction_lock.outcome_release_custody_verified),
        "execution_chain_ready": prediction_lock.execution_chain_ready,
        "external_validation": prediction_lock.external_validation,
        "scientific_use_authorized": prediction_lock.scientific_use_authorized,
        "runner_authorized": prediction_lock.runner_authorized,
    }


def _evaluation_inputs_projection(
    package: SuccessorEvaluationInputsPackageVerification,
) -> dict[str, object]:
    inputs = package.inputs
    return {
        "evaluation_inputs_manifest_sha256": package.evaluation_inputs_manifest_sha256,
        "externally_digest_bound": package.externally_digest_bound,
        "registration_manifest_sha256": inputs.registration_manifest_sha256,
        "evaluation_campaign_evidence_manifest_sha256": (
            inputs.evaluation_campaign_evidence_manifest_sha256
        ),
        "evaluation_heldout_content_sha256": inputs.evaluation_heldout_content_sha256,
        "prediction_lock_manifest_sha256": inputs.prediction_lock_manifest_sha256,
        "realized_cell_count": inputs.realized_cell_count,
        "realized_time_block_count": inputs.realized_time_block_count,
        "campaign_identity_reconciled": inputs.campaign_identity_reconciled,
        "collection_window_reconciled": inputs.collection_window_reconciled,
        "predictor_design_reconciled": inputs.predictor_design_reconciled,
        "exact_cell_block_reconciliation": inputs.cell_block_reconciliation == "exact",
        "chronology_consistent": inputs.chronology_consistent,
        "registration_time_externally_attested": (inputs.registration_time_externally_attested),
        "prediction_lock_time_externally_attested": (
            inputs.prediction_lock_time_externally_attested
        ),
        "prediction_formula_frozen": inputs.prediction_formula_frozen,
        "prediction_lock_binding_reconciled": inputs.prediction_lock_binding_reconciled,
        "prediction_rows_target_free": inputs.prediction_rows_target_free,
        "workflow_prediction_commitment": inputs.workflow_prediction_commitment,
        "prediction_rows_preoutcome_locked": inputs.prediction_rows_preoutcome_locked,
        "outcome_release_custody_verified": inputs.outcome_release_custody_verified,
        "execution_chain_ready": inputs.execution_chain_ready,
        "external_validation": inputs.external_validation,
        "scientific_use_authorized": inputs.scientific_use_authorized,
        "runner_authorized": inputs.runner_authorized,
    }


def _lifecycle(
    fit: EmpiricalCalibrationPackageVerification | None,
    adapter: AdaptedResourcePackageVerification | None,
    registration: SuccessorRegistrationPackageVerification | None,
    prediction_lock: SuccessorPredictionLockPackageVerification | None,
    evaluation_inputs: SuccessorEvaluationInputsPackageVerification | None,
) -> list[dict[str, object]]:
    fit_state = "pending" if fit is None else fit.fit.gate_status
    if fit is None:
        fit_detail = "No verified calibration-fit package was supplied."
    else:
        fit_detail = (
            "Calibration-only fit was recomputed and passed every configured gate."
            if fit.fit.gate_status == "passed"
            else "Calibration-only fit was recomputed; one or more gates block progression."
        )
    if adapter is not None:
        adapter_state = "verified"
        adapter_detail = "Ten resource specifications were recomputed from fit and policy."
    elif fit is not None and fit.fit.gate_status != "passed":
        adapter_state = "blocked"
        adapter_detail = "Adapter remains blocked by the fit-gate disposition."
    else:
        adapter_state = "pending"
        adapter_detail = "No verified adapter package was supplied."
    if registration is not None:
        registration_state = "verified"
        registration_detail = (
            "The study plan and transfer contract were reverified; this does not authorize a run."
        )
    elif adapter is None or fit is None or fit.fit.gate_status != "passed":
        registration_state = "blocked"
        registration_detail = "Study-plan freezing remains blocked by the upstream evidence chain."
    else:
        registration_state = "pending"
        registration_detail = "No externally digest-bound study-plan package was supplied."
    if prediction_lock is not None:
        prediction_state = "verified"
        prediction_detail = (
            "Prediction rows were generated without supplying the future evaluation campaign. The "
            "declared local lock timestamp is ordered after registration and before the planned "
            "window. This establishes internal chronology only; actual prediction or package "
            "creation, publication, external receipt, and outcome custody are not established. "
            "A scientific pre-outcome lock is therefore not established."
        )
    elif registration is None:
        prediction_state = "blocked"
        prediction_detail = "A prediction-lock package requires a frozen study plan."
    else:
        prediction_state = "pending"
        prediction_detail = "No externally digest-bound prediction-lock package was supplied."
    if evaluation_inputs is not None:
        inputs_state = "verified"
        inputs_detail = (
            "The realized campaign and predictor design reconcile exactly to the frozen plan and "
            "bound prediction lock. This does not verify outcome-release custody."
        )
    elif prediction_lock is None:
        inputs_state = "blocked"
        inputs_detail = "Evaluation inputs cannot be bound before a prediction lock is verified."
    else:
        inputs_state = "pending"
        inputs_detail = "No externally digest-bound evaluation-input package was supplied."
    if prediction_lock is None or evaluation_inputs is None:
        custody_state = "blocked"
        custody_detail = (
            "Outcome custody cannot be evaluated until prediction-lock and evaluation-input "
            "packages are verified."
        )
    else:
        custody_state = "pending"
        custody_detail = "No separately verified outcome-release custody package is connected."
    return [
        {
            "stage": "intake",
            "label": "Evidence intake",
            "state": "verified",
            "detail": "Campaign package and partition commitments were fully reverified.",
        },
        {
            "stage": "fit",
            "label": "Fit quality",
            "state": fit_state,
            "detail": fit_detail,
        },
        {
            "stage": "adapter",
            "label": "Resource adapter",
            "state": adapter_state,
            "detail": adapter_detail,
        },
        {
            "stage": "frozen_study_plan",
            "label": "Frozen study plan",
            "state": registration_state,
            "detail": registration_detail,
        },
        {
            "stage": "prediction_lock",
            "label": "Target-free local commitment",
            "state": prediction_state,
            "detail": prediction_detail,
        },
        {
            "stage": "evaluation_inputs",
            "label": "Evaluation inputs",
            "state": inputs_state,
            "detail": inputs_detail,
        },
        {
            "stage": "outcome_custody",
            "label": "Outcome custody",
            "state": custody_state,
            "detail": custody_detail,
        },
        {
            "stage": "scoring",
            "label": "One-shot scoring",
            "state": "not_implemented",
            "detail": (
                "No separately reviewed one-shot scorer or immutable result package is connected."
            ),
        },
        {
            "stage": "execution",
            "label": "Evaluation execution",
            "state": "not_authorized",
            "detail": (
                "No separate evaluation authorization is connected; no prospective result has "
                "been executed."
            ),
        },
    ]


def assemble_successor_status(
    campaign: CampaignPackageVerification,
    *,
    fit: EmpiricalCalibrationPackageVerification | None = None,
    adapter: AdaptedResourcePackageVerification | None = None,
    registration: SuccessorRegistrationPackageVerification | None = None,
    prediction_lock: SuccessorPredictionLockPackageVerification | None = None,
    evaluation_inputs: SuccessorEvaluationInputsPackageVerification | None = None,
) -> SuccessorStatusBundle:
    """Assemble a data-minimized projection from already verified packages."""

    if not campaign.externally_digest_bound:
        raise ValueError("status UI requires an externally digest-bound campaign package")
    if campaign.external_validation or campaign.scientific_use_authorized:
        raise ValueError("campaign package exceeds the engineering-evidence boundary")
    campaign_projection = _campaign_projection(campaign)
    calibration_digest = _mapping(campaign_projection["partitions"], "projected partitions")[
        "calibration"
    ]
    calibration_digest = _mapping(calibration_digest, "projected calibration partition")[
        "content_sha256"
    ]

    if fit is not None:
        if not fit.externally_digest_bound:
            raise ValueError("status UI requires an externally digest-bound fit package")
        if fit.fit.calibration_content_sha256 != calibration_digest:
            raise ValueError("fit package is bound to a different calibration partition")
        if not fit.fit.source_package_heldout_verified or fit.fit.heldout_used_for_fit:
            raise ValueError("fit package held-out boundary differs from the UI contract")
        if (
            fit.fit.runner_authorized
            or fit.fit.scientific_use_authorized
            or fit.fit.external_validation
        ):
            raise ValueError("fit package exceeds the engineering-evidence boundary")
    if adapter is not None:
        if fit is None:
            raise ValueError("adapter status requires the verified source fit package")
        if not adapter.externally_digest_bound:
            raise ValueError("status UI requires an externally digest-bound adapter package")
        if adapter.bundle.calibration_fit_id != fit.fit.calibration_fit_id:
            raise ValueError("adapter package is bound to a different calibration fit")
        if adapter.bundle.fit_evidence_manifest_sha256 != fit.fit_evidence_manifest_sha256:
            raise ValueError("adapter package is bound to a different fit evidence manifest")
        if (
            not adapter.bundle.source_package_heldout_verified
            or adapter.bundle.heldout_used_for_adapter
        ):
            raise ValueError("adapter package held-out boundary differs from the UI contract")
        if (
            adapter.bundle.runner_authorized
            or adapter.bundle.scientific_use_authorized
            or adapter.bundle.external_validation
        ):
            raise ValueError("adapter package exceeds the engineering-evidence boundary")

    if registration is not None:
        if fit is None or adapter is None:
            raise ValueError("registration status requires the verified upstream fit and adapter")
        record = registration.registration
        if not registration.externally_digest_bound:
            raise ValueError("status UI requires an externally digest-bound registration package")
        if record.source_campaign_evidence_manifest_sha256 != campaign.evidence_manifest_sha256:
            raise ValueError("registration package is bound to a different source campaign")
        if record.fit_evidence_manifest_sha256 != fit.fit_evidence_manifest_sha256:
            raise ValueError("registration package is bound to a different fit manifest")
        if record.adapter_manifest_sha256 != adapter.adapter_manifest_sha256:
            raise ValueError("registration package is bound to a different adapter manifest")
        if not (
            record.chronology_consistent
            and record.upstream_chain_verified
            and record.prediction_formula_frozen
        ):
            raise ValueError("registration verification gates are not all satisfied")
        if (
            record.execution_chain_ready
            or record.operational_outcome_extension_enabled
            or record.runner_authorized
            or record.scientific_use_authorized
            or record.external_validation
        ):
            raise ValueError("registration package exceeds the engineering-evidence boundary")
    if prediction_lock is not None:
        if registration is None:
            raise ValueError("prediction-lock status requires the verified registration package")
        lock = prediction_lock.lock
        if not prediction_lock.externally_digest_bound:
            raise ValueError(
                "status UI requires an externally digest-bound prediction-lock package"
            )
        if lock.registration_manifest_sha256 != registration.registration_manifest_sha256:
            raise ValueError("prediction lock is bound to a different registration manifest")
        if not (
            lock.upstream_chain_verified
            and lock.registered_semantics_reconciled
            and lock.planned_predictor_design_reconciled
            and lock.prediction_formula_frozen
            and lock.comparator_formula_frozen
            and lock.future_evaluation_campaign_not_supplied
            and lock.prediction_rows_target_free
            and lock.local_lock_chronology_consistent
            and lock.workflow_prediction_commitment
        ):
            raise ValueError("prediction-lock target-free workflow gates are not all satisfied")
        if (
            lock.source_historical_heldout_used_for_prediction
            or lock.prediction_rows_preoutcome_locked
            or lock.prediction_lock_time_externally_attested
            or lock.outcome_release_custody_verified
            or lock.execution_chain_ready
            or lock.runner_authorized
            or lock.scientific_use_authorized
            or lock.external_validation
        ):
            raise ValueError("prediction-lock package exceeds the local-commitment boundary")
    if evaluation_inputs is not None:
        if registration is None or prediction_lock is None:
            raise ValueError(
                "evaluation-input status requires the verified registration and prediction lock"
            )
        inputs = evaluation_inputs.inputs
        if not evaluation_inputs.externally_digest_bound:
            raise ValueError(
                "status UI requires an externally digest-bound evaluation-input package"
            )
        if inputs.registration_manifest_sha256 != registration.registration_manifest_sha256:
            raise ValueError("evaluation inputs are bound to a different registration manifest")
        if (
            inputs.prediction_lock_manifest_sha256
            != prediction_lock.prediction_lock_manifest_sha256
        ):
            raise ValueError("evaluation inputs are bound to a different prediction-lock manifest")
        if not (
            inputs.campaign_identity_reconciled
            and inputs.collection_window_reconciled
            and inputs.predictor_design_reconciled
            and inputs.cell_block_reconciliation == "exact"
            and inputs.chronology_consistent
            and inputs.prediction_formula_frozen
            and inputs.prediction_lock_binding_reconciled
            and inputs.prediction_rows_target_free
            and inputs.workflow_prediction_commitment
        ):
            raise ValueError("evaluation-input reconciliation gates are not all satisfied")
        if (
            inputs.registration_time_externally_attested
            or inputs.prediction_lock_time_externally_attested
            or inputs.prediction_rows_preoutcome_locked
            or inputs.outcome_release_custody_verified
            or inputs.execution_chain_ready
            or inputs.runner_authorized
            or inputs.scientific_use_authorized
            or inputs.external_validation
        ):
            raise ValueError("evaluation-input package exceeds the engineering-evidence boundary")

    fit_projection = None if fit is None else _fit_projection(fit)
    adapter_projection = None if adapter is None else _adapter_projection(adapter)
    registration_projection = (
        None if registration is None else _registration_projection(registration)
    )
    prediction_lock_projection = (
        None if prediction_lock is None else _prediction_lock_projection(prediction_lock)
    )
    evaluation_inputs_projection = (
        None if evaluation_inputs is None else _evaluation_inputs_projection(evaluation_inputs)
    )
    blockers = [
        "No separately reviewed one-shot scorer or immutable result package is connected.",
        "Prospective evaluation execution is not authorized.",
        "The prospective evaluation has not been executed.",
        "Outcome-release custody has not been verified.",
        "External validation has not been established.",
    ]
    if fit is None:
        blockers.append("A verified calibration-fit package has not been supplied.")
    elif fit.fit.gate_status != "passed":
        blockers.extend(fit.fit.blocking_reasons)
    if adapter is None:
        blockers.append("A verified resource-adapter package has not been supplied.")
    if registration is None:
        blockers.append("A verified frozen study-plan package has not been supplied.")
    elif not registration.registration.registration_time_externally_attested:
        blockers.append(
            "The registration time is internally consistent but not externally attested."
        )
    if prediction_lock is None:
        blockers.append("A verified target-free prediction-lock package has not been supplied.")
    else:
        blockers.append(
            "The declared prediction-lock timestamp is internally ordered, but prediction and "
            "package creation, publication, and external receipt times are not established."
        )
    if evaluation_inputs is None:
        blockers.append("A verified evaluation-input package has not been supplied.")
    blockers = sorted(set(blockers))

    payload: dict[str, Any] = {
        "schema_version": STATUS_SCHEMA_VERSION,
        "title": "Fleet Assurance Successor Study",
        "subtitle": "Evidence readiness and uncertainty status",
        "overall_state": "engineering_evidence_only",
        "assurance_boundary": {
            "digest_bound_inputs": True,
            "public_safe_projection": True,
            "external_validation": False,
            "scientific_use_authorized": False,
            "runner_authorized": False,
            "registration_verified": registration is not None,
            "prediction_lock_verified": prediction_lock is not None,
            "evaluation_inputs_verified": evaluation_inputs is not None,
            "prediction_rows_preoutcome_locked": False,
            "prediction_lock_time_externally_attested": False,
            "outcome_release_custody_verified": False,
            "scoring_implemented": False,
            "scoring_completed": False,
            "evaluation_executed": False,
        },
        "lifecycle": _lifecycle(
            fit,
            adapter,
            registration,
            prediction_lock,
            evaluation_inputs,
        ),
        "campaign": campaign_projection,
        "fit": fit_projection,
        "adapter": adapter_projection,
        "registration": registration_projection,
        "prediction_lock": prediction_lock_projection,
        "evaluation_inputs": evaluation_inputs_projection,
        "blocking_conditions": blockers,
        "disclosure_boundary": {
            "includes": [
                "aggregate partition counts and integrity commitments",
                "fit-gate dispositions, diagnostics, and uncertainty intervals",
                "adapter semantics and documented simulator limitations",
                "study-plan, prediction-lock, and evaluation-input aggregate commitments",
            ],
            "excludes": [
                "raw measurement rows",
                "campaign, dataset, study, plan, cell, and package identifiers",
                "site and system aliases",
                "collection timestamps",
                "prediction rows, parameter draws, predicted values, scores, and results",
                "prediction, receipt, custody, signer, and release metadata",
                "authority references and local source paths",
            ],
        },
    }
    _assert_public_safe(payload)
    payload["projection_sha256"] = hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()
    return SuccessorStatusBundle(payload=payload)


def load_successor_status(
    campaign_package: str | Path,
    *,
    expected_campaign_evidence_manifest_sha256: str,
    fit_package: str | Path | None = None,
    expected_fit_evidence_manifest_sha256: str | None = None,
    adapter_package: str | Path | None = None,
    expected_adapter_policy_sha256: str | None = None,
    expected_adapter_manifest_sha256: str | None = None,
    registration_package: str | Path | None = None,
    expected_registration_manifest_sha256: str | None = None,
    prediction_lock_package: str | Path | None = None,
    expected_prediction_lock_manifest_sha256: str | None = None,
    evaluation_campaign_package: str | Path | None = None,
    expected_evaluation_campaign_evidence_manifest_sha256: str | None = None,
    evaluation_inputs_package: str | Path | None = None,
    expected_evaluation_inputs_manifest_sha256: str | None = None,
) -> SuccessorStatusBundle:
    """Verify the supplied evidence chain and return its public-safe projection."""

    campaign_digest = _sha256(
        expected_campaign_evidence_manifest_sha256,
        "expected campaign evidence manifest digest",
    )
    if (fit_package is None) != (expected_fit_evidence_manifest_sha256 is None):
        raise ValueError("fit package and externally recorded fit digest must be supplied together")
    adapter_arguments = (
        adapter_package,
        expected_adapter_policy_sha256,
        expected_adapter_manifest_sha256,
    )
    if any(value is not None for value in adapter_arguments) and not all(
        value is not None for value in adapter_arguments
    ):
        raise ValueError("adapter package, policy digest, and manifest digest are one closed set")
    if adapter_package is not None and fit_package is None:
        raise ValueError("adapter verification requires the verified source fit package")
    registration_arguments = (
        registration_package,
        expected_registration_manifest_sha256,
    )
    if any(value is not None for value in registration_arguments) and not all(
        value is not None for value in registration_arguments
    ):
        raise ValueError("registration package and manifest digest are one closed set")
    if registration_package is not None and adapter_package is None:
        raise ValueError("registration verification requires the verified upstream adapter")
    prediction_lock_arguments = (
        prediction_lock_package,
        expected_prediction_lock_manifest_sha256,
    )
    if any(value is not None for value in prediction_lock_arguments) and not all(
        value is not None for value in prediction_lock_arguments
    ):
        raise ValueError("prediction-lock package and manifest digest are one closed set")
    if prediction_lock_package is not None and registration_package is None:
        raise ValueError("prediction-lock verification requires the verified registration")
    evaluation_arguments = (
        evaluation_campaign_package,
        expected_evaluation_campaign_evidence_manifest_sha256,
        evaluation_inputs_package,
        expected_evaluation_inputs_manifest_sha256,
    )
    if any(value is not None for value in evaluation_arguments) and not all(
        value is not None for value in evaluation_arguments
    ):
        raise ValueError(
            "evaluation campaign, evaluation inputs, and both manifest digests are one closed set"
        )
    if evaluation_inputs_package is not None and prediction_lock_package is None:
        raise ValueError("evaluation-input verification requires the verified prediction lock")

    checked_campaign = verify_empirical_campaign_package(
        campaign_package,
        expected_evidence_manifest_sha256=campaign_digest,
    )
    checked_fit = None
    if fit_package is not None and expected_fit_evidence_manifest_sha256 is not None:
        fit_digest = _sha256(
            expected_fit_evidence_manifest_sha256,
            "expected fit evidence manifest digest",
        )
        checked_fit = verify_empirical_calibration_package(
            fit_package,
            source_campaign_package=campaign_package,
            expected_source_evidence_manifest_sha256=campaign_digest,
            expected_fit_evidence_manifest_sha256=fit_digest,
        )
    checked_adapter = None
    if (
        adapter_package is not None
        and expected_adapter_policy_sha256 is not None
        and expected_adapter_manifest_sha256 is not None
        and checked_fit is not None
    ):
        checked_adapter = verify_adapted_resource_bundle(
            adapter_package,
            fit_package=checked_fit,
            expected_policy_sha256=_sha256(
                expected_adapter_policy_sha256,
                "expected adapter policy digest",
            ),
            expected_adapter_manifest_sha256=_sha256(
                expected_adapter_manifest_sha256,
                "expected adapter manifest digest",
            ),
        )
    checked_registration = None
    if (
        registration_package is not None
        and expected_registration_manifest_sha256 is not None
        and checked_fit is not None
        and checked_adapter is not None
    ):
        checked_registration = verify_successor_registration_package(
            registration_package,
            source_campaign=checked_campaign,
            fit_package=checked_fit,
            adapter_package=checked_adapter,
            expected_registration_manifest_sha256=_sha256(
                expected_registration_manifest_sha256,
                "expected registration manifest digest",
            ),
        )
    checked_prediction_lock = None
    if (
        prediction_lock_package is not None
        and expected_prediction_lock_manifest_sha256 is not None
        and checked_fit is not None
        and checked_adapter is not None
        and checked_registration is not None
    ):
        checked_prediction_lock = verify_successor_prediction_lock_package(
            prediction_lock_package,
            source_campaign=checked_campaign,
            fit_package=checked_fit,
            adapter_package=checked_adapter,
            registration_package=checked_registration,
            expected_prediction_lock_manifest_sha256=_sha256(
                expected_prediction_lock_manifest_sha256,
                "expected prediction-lock manifest digest",
            ),
        )
    checked_evaluation_inputs = None
    if (
        evaluation_campaign_package is not None
        and expected_evaluation_campaign_evidence_manifest_sha256 is not None
        and evaluation_inputs_package is not None
        and expected_evaluation_inputs_manifest_sha256 is not None
        and checked_fit is not None
        and checked_adapter is not None
        and checked_registration is not None
        and checked_prediction_lock is not None
    ):
        checked_evaluation_campaign = verify_empirical_campaign_package(
            evaluation_campaign_package,
            expected_evidence_manifest_sha256=_sha256(
                expected_evaluation_campaign_evidence_manifest_sha256,
                "expected evaluation campaign evidence manifest digest",
            ),
        )
        checked_evaluation_inputs = verify_successor_evaluation_inputs_package(
            evaluation_inputs_package,
            source_campaign=checked_campaign,
            fit_package=checked_fit,
            adapter_package=checked_adapter,
            registration_package=checked_registration,
            prediction_lock_package=checked_prediction_lock,
            evaluation_campaign=checked_evaluation_campaign,
            expected_evaluation_inputs_manifest_sha256=_sha256(
                expected_evaluation_inputs_manifest_sha256,
                "expected evaluation-input manifest digest",
            ),
        )
    return assemble_successor_status(
        checked_campaign,
        fit=checked_fit,
        adapter=checked_adapter,
        registration=checked_registration,
        prediction_lock=checked_prediction_lock,
        evaluation_inputs=checked_evaluation_inputs,
    )


def _script_json(value: object) -> str:
    encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return encoded.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _atomic_write(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _status_destination_state(destination: Path) -> str:
    """Classify a status destination without following symlinks."""

    try:
        destination_mode = destination.lstat().st_mode
    except FileNotFoundError:
        return "absent"
    if stat.S_ISLNK(destination_mode):
        raise ValueError("successor status destination must not be a symlink")
    if not stat.S_ISDIR(destination_mode):
        raise NotADirectoryError(destination)

    entries = tuple(destination.iterdir())
    if not entries:
        return "empty"
    if {entry.name for entry in entries} != set(STATUS_ASSET_NAMES):
        raise ValueError("successor status destination must contain exactly the two owned assets")
    for entry in entries:
        mode = entry.lstat().st_mode
        if not stat.S_ISREG(mode):
            raise ValueError(
                "successor status destination assets must be regular, non-symlink files"
            )
    return "complete"


def _remove_owned_status_directory(directory: Path) -> None:
    """Remove a private staging or backup directory containing only owned assets."""

    try:
        directory_mode = directory.lstat().st_mode
    except FileNotFoundError:
        return
    if stat.S_ISLNK(directory_mode) or not stat.S_ISDIR(directory_mode):
        raise RuntimeError("refusing to traverse an unexpected status staging path")
    for entry in tuple(directory.iterdir()):
        if entry.name not in STATUS_ASSET_NAMES or not stat.S_ISREG(entry.lstat().st_mode):
            raise RuntimeError("refusing to remove an unexpected status staging entry")
        entry.unlink()
    directory.rmdir()


def _commit_status_directory(staging: Path, destination: Path, state: str) -> None:
    """Commit a complete staged directory and restore the prior pair on failure."""

    if state == "absent":
        os.replace(staging, destination)
        return

    backup = Path(tempfile.mkdtemp(prefix=f".{destination.name}.previous.", dir=destination.parent))
    backup.rmdir()
    os.replace(destination, backup)
    try:
        os.replace(staging, destination)
    except BaseException:
        try:
            os.replace(backup, destination)
        except BaseException as rollback_error:
            raise RuntimeError(
                "successor status replacement failed and the prior output could not be restored"
            ) from rollback_error
        raise
    _remove_owned_status_directory(backup)


def write_successor_status_assets(
    bundle: SuccessorStatusBundle,
    output_directory: str | Path,
    *,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Write self-contained ``index.html`` and its strict JSON projection."""

    _assert_public_safe(bundle.payload)
    expected_projection_hash = bundle.payload.get("projection_sha256")
    core = dict(bundle.payload)
    core.pop("projection_sha256", None)
    if expected_projection_hash != hashlib.sha256(_canonical_json_bytes(core)).hexdigest():
        raise ValueError("successor status projection integrity check failed")
    destination = Path(os.path.abspath(os.fspath(output_directory)))
    state = _status_destination_state(destination)
    if state == "complete" and not overwrite:
        raise FileExistsError("refusing to overwrite the complete successor status directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    html = _HTML_TEMPLATE.replace("__SUCCESSOR_STATUS_PAYLOAD__", _script_json(bundle.payload))
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.staging.", dir=destination.parent))
    try:
        _atomic_write(
            staging / "successor-status.json",
            json.dumps(bundle.payload, indent=2, sort_keys=True) + "\n",
        )
        _atomic_write(staging / "index.html", html)
        os.chmod(staging, 0o755)
        if _status_destination_state(staging) != "complete":
            raise RuntimeError("successor status staging directory is incomplete")
        state = _status_destination_state(destination)
        if state == "complete" and not overwrite:
            raise FileExistsError("refusing to overwrite the complete successor status directory")
        _commit_status_directory(staging, destination, state)
    finally:
        _remove_owned_status_directory(staging)
    html_path = destination / "index.html"
    json_path = destination / "successor-status.json"
    return html_path, json_path


def build_successor_status(
    campaign_package: str | Path,
    output_directory: str | Path,
    *,
    expected_campaign_evidence_manifest_sha256: str,
    fit_package: str | Path | None = None,
    expected_fit_evidence_manifest_sha256: str | None = None,
    adapter_package: str | Path | None = None,
    expected_adapter_policy_sha256: str | None = None,
    expected_adapter_manifest_sha256: str | None = None,
    registration_package: str | Path | None = None,
    expected_registration_manifest_sha256: str | None = None,
    prediction_lock_package: str | Path | None = None,
    expected_prediction_lock_manifest_sha256: str | None = None,
    evaluation_campaign_package: str | Path | None = None,
    expected_evaluation_campaign_evidence_manifest_sha256: str | None = None,
    evaluation_inputs_package: str | Path | None = None,
    expected_evaluation_inputs_manifest_sha256: str | None = None,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Verify evidence and build a deployable, network-free status directory."""

    destination = Path(os.path.abspath(os.fspath(output_directory)))
    resolved_destination = destination.resolve()
    source_roots = [Path(campaign_package).resolve()]
    source_roots.extend(
        Path(value).resolve()
        for value in (
            fit_package,
            adapter_package,
            registration_package,
            prediction_lock_package,
            evaluation_campaign_package,
            evaluation_inputs_package,
        )
        if value is not None
    )
    if any(
        resolved_destination == root or root in resolved_destination.parents
        for root in source_roots
    ):
        raise ValueError("status output must be outside immutable evidence packages")
    bundle = load_successor_status(
        campaign_package,
        expected_campaign_evidence_manifest_sha256=(expected_campaign_evidence_manifest_sha256),
        fit_package=fit_package,
        expected_fit_evidence_manifest_sha256=expected_fit_evidence_manifest_sha256,
        adapter_package=adapter_package,
        expected_adapter_policy_sha256=expected_adapter_policy_sha256,
        expected_adapter_manifest_sha256=expected_adapter_manifest_sha256,
        registration_package=registration_package,
        expected_registration_manifest_sha256=expected_registration_manifest_sha256,
        prediction_lock_package=prediction_lock_package,
        expected_prediction_lock_manifest_sha256=(expected_prediction_lock_manifest_sha256),
        evaluation_campaign_package=evaluation_campaign_package,
        expected_evaluation_campaign_evidence_manifest_sha256=(
            expected_evaluation_campaign_evidence_manifest_sha256
        ),
        evaluation_inputs_package=evaluation_inputs_package,
        expected_evaluation_inputs_manifest_sha256=(expected_evaluation_inputs_manifest_sha256),
    )
    return write_successor_status_assets(bundle, destination, overwrite=overwrite)


_HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; connect-src 'none'; font-src 'none'; base-uri 'none'; form-action 'none'">
  <meta name="color-scheme" content="dark light">
  <title>Fleet Assurance Successor Study | Evidence Status</title>
  <style>
    :root{--ink:#eaf2f6;--muted:#adc0ca;--panel:#12232c;--panel2:#18303b;--line:#527583;--canvas:#07141b;--accent:#4bd6b2;--blue:#70c5f0;--amber:#f4c774;--red:#ff9189;--white:#fff;--shadow:0 16px 48px rgba(0,0,0,.2);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    *{box-sizing:border-box}html{scroll-behavior:smooth;max-width:100%;overflow-x:hidden}body{margin:0;max-width:100%;overflow-x:hidden;background:radial-gradient(circle at 85% -10%,#123b46 0,transparent 35rem),var(--canvas);color:var(--ink);line-height:1.5}.skip{position:absolute;left:-9999px}.skip:focus{left:1rem;top:1rem;background:var(--white);color:#07141b;padding:.65rem 1rem;border-radius:.4rem;z-index:20}.shell{width:min(1180px,calc(100% - 2rem));margin-inline:auto;min-width:0}.masthead{padding:3.5rem 0 2rem}.eyebrow{margin:0 0 .5rem;color:var(--accent);font-size:.77rem;font-weight:800;letter-spacing:.16em;text-transform:uppercase}.masthead h1{margin:0;font-size:clamp(2rem,5vw,4.2rem);line-height:1.02;letter-spacing:-.045em;max-width:900px;overflow-wrap:break-word}.lead{max-width:760px;color:var(--muted);font-size:1.08rem;margin:1rem 0 1.4rem;overflow-wrap:break-word}.boundary{display:flex;align-items:flex-start;gap:.75rem;width:fit-content;max-width:100%;border:1px solid rgba(240,188,100,.5);background:rgba(240,188,100,.1);padding:.72rem .9rem;border-radius:.55rem;color:#ffe0aa;font-weight:750;overflow-wrap:anywhere}.boundary span{min-width:0}.boundary::before{content:"";width:.7rem;height:.7rem;flex:0 0 auto;border-radius:50%;background:var(--amber);box-shadow:0 0 0 .28rem rgba(240,188,100,.14);margin-top:.35rem}main{padding-bottom:4rem}.section{margin-top:1.2rem;min-width:0;background:linear-gradient(145deg,rgba(24,48,59,.94),rgba(14,31,40,.94));border:1px solid var(--line);border-radius:1rem;box-shadow:var(--shadow);padding:clamp(1rem,2.5vw,1.65rem)}.section-head{display:flex;justify-content:space-between;gap:1rem;align-items:end;margin-bottom:1rem;min-width:0}.section h2{font-size:1.15rem;margin:0;letter-spacing:-.015em}.section-copy{margin:.25rem 0 0;color:var(--muted);font-size:.9rem;overflow-wrap:break-word}.lifecycle{list-style:none;margin:1.4rem 0 .25rem;padding:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.5rem;counter-reset:stage}.life{position:relative;min-width:0;min-height:9rem;padding:1rem .8rem .8rem;border:1px solid var(--line);border-radius:.75rem;background:rgba(7,20,27,.54);overflow-wrap:anywhere}.life::before{counter-increment:stage;content:counter(stage);display:grid;place-items:center;width:1.75rem;height:1.75rem;border-radius:50%;background:var(--line);font-size:.78rem;font-weight:800;margin-bottom:.75rem}.life[data-state="verified"]::before,.life[data-state="passed"]::before{background:var(--accent);color:#06231c}.life[data-state="failed"]::before{background:var(--red);color:#2c0907}.life[data-state="not_evaluable"]::before,.life[data-state="blocked"]::before{background:var(--amber);color:#2a1902}.life strong{display:block;font-size:.9rem}.life p{color:var(--muted);font-size:.76rem;line-height:1.4;margin:.5rem 0 0}.state{display:inline-flex;align-items:center;gap:.35rem;margin-top:.5rem;font-size:.7rem;font-weight:800;letter-spacing:.04em;text-transform:uppercase}.state::before{content:"";width:.44rem;height:.44rem;flex:0 0 auto;border-radius:50%;background:var(--muted)}.state.verified::before,.state.passed::before{background:var(--accent)}.state.failed::before{background:var(--red)}.state.not_evaluable::before,.state.blocked::before{background:var(--amber)}.state.not_authorized::before,.state.not_implemented::before,.state.pending::before{background:#7f929d}.facts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.65rem}.boundary-facts{grid-template-columns:repeat(5,minmax(0,1fr))}.fact{min-width:0;padding:1rem;border:1px solid var(--line);border-radius:.75rem;background:rgba(7,20,27,.48)}.fact small{display:block;color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.08em}.fact strong{display:block;margin-top:.35rem;font-size:1rem;overflow-wrap:anywhere}.fact .ok{color:var(--accent)}.fact .locked{color:var(--amber)}.digest-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.55rem}.digest{min-width:0;padding:.75rem;border-left:3px solid var(--blue);background:rgba(7,20,27,.45);border-radius:.25rem}.digest span{display:block;color:var(--muted);font-size:.72rem}.digest code{display:block;margin-top:.28rem;color:#cbe8f6;font-size:.72rem;overflow-wrap:anywhere}.resource-summary{display:flex;flex-wrap:wrap;gap:.5rem;margin:.25rem 0 1rem}.filter{appearance:none;min-height:2.75rem;border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:999px;padding:.45rem .72rem;font:inherit;font-size:.78rem;cursor:pointer}.filter[aria-pressed="true"]{background:var(--ink);color:#07141b;border-color:var(--ink)}.filter:focus-visible,summary:focus-visible,.adapter-grid:focus-visible{outline:3px solid var(--blue);outline-offset:2px}.resource-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.65rem}.resource{min-width:0;border:1px solid var(--line);border-radius:.75rem;background:rgba(7,20,27,.48);overflow:hidden}.resource summary{cursor:pointer;list-style:none;padding:.85rem 1rem;display:flex;align-items:center;justify-content:space-between;gap:.75rem;min-width:0}.resource summary::-webkit-details-marker{display:none}.resource summary strong{font-size:.88rem}.resource summary small{display:block;color:var(--muted);font-weight:500;overflow-wrap:anywhere}.resource-body{border-top:1px solid var(--line);padding:.8rem 1rem 1rem}.metric-row{display:grid;grid-template-columns:minmax(9rem,1.3fr) 2fr;gap:.75rem;align-items:center;padding:.45rem 0;border-bottom:1px solid rgba(45,72,85,.55)}.metric-row:last-child{border:0}.metric-row label{font-size:.76rem;color:var(--muted)}.interval-value{font-size:.72rem;font-variant-numeric:tabular-nums}.whisker{position:relative;height:.45rem;background:#263f4b;border-radius:999px;margin-top:.35rem}.whisker::after{content:"";position:absolute;left:var(--point);top:-.2rem;width:.12rem;height:.85rem;background:var(--accent);border-radius:1rem}.diagnostics{display:grid;grid-template-columns:repeat(auto-fit,minmax(7.5rem,1fr));gap:.45rem;margin:0 0 .8rem}.diagnostic{min-width:0;padding:.55rem .6rem;background:rgba(24,48,59,.55);border-radius:.4rem}.diagnostic dt{color:var(--muted);font-size:.64rem;line-height:1.3}.diagnostic dd{margin:.2rem 0 0;font-size:.8rem;font-weight:750;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.blocker-list,.limitations{margin:.5rem 0 0;padding-left:1.1rem;color:#d5e1e6}.blocker-list li,.limitations li{margin:.35rem 0;overflow-wrap:anywhere}.adapter-grid{overflow:auto}.adapter-grid table{width:100%;border-collapse:collapse;font-size:.78rem}.adapter-grid th,.adapter-grid td{text-align:left;padding:.65rem;border-bottom:1px solid var(--line);white-space:nowrap}.adapter-grid th{color:var(--muted);font-size:.68rem;text-transform:uppercase;letter-spacing:.06em}.empty{padding:1rem;border:1px dashed var(--line);border-radius:.65rem;color:var(--muted)}.two-col{display:grid;grid-template-columns:1.1fr .9fr;gap:.75rem}.disclosure{display:grid;grid-template-columns:1fr 1fr;gap:.7rem}.disclosure article{padding:.9rem;border:1px solid var(--line);border-radius:.65rem}.disclosure h3{font-size:.85rem;margin:0 0 .5rem}.disclosure ul{margin:0;padding-left:1.1rem;color:var(--muted);font-size:.8rem}.footer{color:var(--muted);font-size:.72rem;padding:1.5rem 0 3rem}.footer code{overflow-wrap:anywhere}noscript{display:block;padding:1rem;background:#3a1e1a;color:#ffe2db}
    .protocol-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.75rem}.protocol-panel{min-width:0;padding:1rem;border:1px solid var(--line);border-radius:.8rem;background:rgba(7,20,27,.4)}.protocol-panel .section-head{align-items:start}.protocol-panel .facts{grid-template-columns:repeat(2,minmax(0,1fr))}.protocol-panel .digest-grid{grid-template-columns:minmax(0,1fr)}#evaluation-inputs-panel{grid-column:1/-1}#evaluation-inputs-panel .facts{grid-template-columns:repeat(3,minmax(0,1fr))}#evaluation-inputs-panel .digest-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
    @media(max-width:900px){.lifecycle{grid-template-columns:repeat(2,minmax(0,1fr))}.facts{grid-template-columns:repeat(2,minmax(0,1fr))}.boundary-facts{grid-template-columns:repeat(3,minmax(0,1fr))}.two-col,.protocol-grid{grid-template-columns:1fr}#evaluation-inputs-panel{grid-column:auto}#evaluation-inputs-panel .facts{grid-template-columns:repeat(2,minmax(0,1fr))}#evaluation-inputs-panel .digest-grid{grid-template-columns:minmax(0,1fr)}}
    .subhead{font-size:.82rem;margin:1rem 0 .55rem;color:var(--muted);text-transform:uppercase;letter-spacing:.07em}.gate-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.5rem}.gate{min-width:0;padding:.7rem;border:1px solid var(--line);border-radius:.55rem;background:rgba(7,20,27,.48)}.gate strong{display:block;font-size:.76rem;overflow-wrap:anywhere}.gate small{display:block;margin-top:.35rem;color:var(--muted);font-size:.68rem;overflow-wrap:anywhere}
    @media(max-width:620px){.shell{width:calc(100% - 1rem)}.masthead{padding-top:2rem}.masthead h1{font-size:clamp(2rem,10vw,3rem)}.boundary{width:100%}.lifecycle,.facts,.boundary-facts,.resource-list,.digest-grid,.disclosure,.gate-grid,.protocol-panel .facts,#evaluation-inputs-panel .facts{grid-template-columns:minmax(0,1fr)}.life{min-height:auto}.section{border-radius:.75rem}.protocol-panel{padding:.8rem}.diagnostics{grid-template-columns:1fr}.metric-row{grid-template-columns:1fr}.section-head{align-items:start;flex-direction:column}}
    @media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
    @media print{body{background:#fff;color:#111}.section,.fact,.life,.resource{box-shadow:none;background:#fff;color:#111;border-color:#bbb}.masthead,.section{break-inside:avoid}.lead,.section-copy,.life p,.fact small{color:#444}}
  </style>
</head>
<body>
  <a class="skip" href="#main">Skip to evidence status</a>
  <noscript>This page needs its embedded offline renderer. It does not contact a server.</noscript>
  <header class="masthead shell">
    <p class="eyebrow">Fleet Assurance / Successor Study</p>
    <h1>Evidence readiness, without overstating the science.</h1>
    <p class="lead">A public-safe view of campaign intake, calibration quality, simulator adaptation, frozen planning, target-free prediction commitment, and realized-input binding. Verified local artifacts remain distinct from external timing, outcome custody, scoring, execution authority, or a transfer claim.</p>
    <div class="boundary" role="status"><span>Engineering evidence only · prospective execution not authorized</span></div>
  </header>
  <main id="main" class="shell">
    <section class="section" aria-labelledby="life-title">
      <div class="section-head"><div><h2 id="life-title">Successor-study lifecycle</h2><p class="section-copy">Nine distinct states separate evidence readiness, local prediction commitment, outcome custody, scoring, and execution authority.</p></div></div>
      <ol id="lifecycle" class="lifecycle"></ol>
    </section>
    <section class="section" aria-labelledby="boundary-title">
      <div class="section-head"><div><h2 id="boundary-title">Assurance boundary</h2><p class="section-copy">False is a deliberate gate, not missing metadata.</p></div></div>
      <div id="facts" class="facts boundary-facts"></div>
    </section>
    <section class="section" aria-labelledby="intake-title">
      <div class="section-head"><div><h2 id="intake-title">Verified intake</h2><p class="section-copy">Only aggregate counts and cryptographic commitments are exposed.</p></div></div>
      <div id="intakeFacts" class="facts"></div>
      <div id="digests" class="digest-grid" style="margin-top:.75rem"></div>
    </section>
    <section class="section" aria-labelledby="fit-title">
      <div class="section-head"><div><h2 id="fit-title">Fit quality and uncertainty</h2><p class="section-copy">The complete source package, including held-out integrity, was verified. Only calibration values were used for fitting.</p></div><div id="fitState"></div></div>
      <div id="fitEmpty" class="empty" hidden></div>
      <div id="fitContent" hidden><h3 class="subhead">Calibration-wide gates</h3><div id="globalGates" class="gate-grid"></div><h3 class="subhead">Resource fits</h3><div id="resourceFilters" class="resource-summary" aria-label="Filter resources by fit status"></div><div id="resourceList" class="resource-list"></div></div>
    </section>
    <section class="section" aria-labelledby="adapter-title">
      <div class="section-head"><div><h2 id="adapter-title">Adapter semantics</h2><p class="section-copy">Aggregate fits do not identify every simulator behavior. Policy-selected semantics remain explicit, and held-out values are not used for adaptation.</p></div><div id="adapterState"></div></div>
      <div id="adapterEmpty" class="empty" hidden></div>
      <div id="adapterContent" hidden><div class="adapter-grid" role="region" aria-label="Generated assurance resource semantics; scroll horizontally to view all columns" tabindex="0"><table><caption class="skip">Generated assurance resource semantics</caption><thead><tr><th>Resource</th><th>Arrival</th><th>Service</th><th>Overload</th><th>Capacity</th><th>Max wait</th><th>Class</th></tr></thead><tbody id="adapterRows"></tbody></table></div><h3 style="font-size:.9rem;margin:1.1rem 0 .35rem">Current simulator limitations</h3><ul id="limitations" class="limitations"></ul></div>
    </section>
    <section class="section" aria-labelledby="protocol-title">
      <div class="section-head"><div><h2 id="protocol-title">Prospective protocol evidence</h2><p class="section-copy">Only aggregate counts, cryptographic commitments, and verifier-produced gate flags are disclosed. A target-free local commitment does not attest external timing or outcome custody.</p></div></div>
      <div class="protocol-grid">
        <article class="protocol-panel" aria-labelledby="registration-title">
          <div class="section-head"><div><h3 id="registration-title" style="margin:0;font-size:1rem">Frozen study plan</h3><p class="section-copy">Plan, transfer criteria, implementation, and upstream evidence commitments.</p></div><div id="registrationState"></div></div>
          <div id="registrationEmpty" class="empty" hidden></div>
          <div id="registrationContent" hidden><div id="registrationFacts" class="facts"></div><div id="registrationDigests" class="digest-grid" style="margin-top:.75rem"></div></div>
        </article>
        <article class="protocol-panel" aria-labelledby="prediction-lock-title">
          <div class="section-head"><div><h3 id="prediction-lock-title" style="margin:0;font-size:1rem">Target-free local commitment</h3><p class="section-copy">The package binds deterministic prediction content generated from the frozen plan without evaluation-campaign input. Creation and publication time are not established.</p></div><div id="predictionLockState"></div></div>
          <div id="predictionLockEmpty" class="empty" hidden></div>
          <div id="predictionLockContent" hidden><div id="predictionLockFacts" class="facts"></div><div class="empty" style="margin-top:.75rem">Verified means the package and digest chain were recomputed and its declared timestamps have internally consistent ordering. It does not establish when predictions or the package were actually created, published, or externally received, or prove that people or outside systems lacked outcome access.</div><div id="predictionLockDigests" class="digest-grid" style="margin-top:.75rem"></div></div>
        </article>
        <article id="evaluation-inputs-panel" class="protocol-panel" aria-labelledby="evaluation-inputs-title">
          <div class="section-head"><div><h3 id="evaluation-inputs-title" style="margin:0;font-size:1rem">Evaluation inputs</h3><p class="section-copy">Realized campaign, predictor design, and ten-resource coverage reconciled to the frozen plan and prediction lock.</p></div><div id="evaluationInputsState"></div></div>
          <div id="evaluationInputsEmpty" class="empty" hidden></div>
          <div id="evaluationInputsContent" hidden><div id="evaluationInputsFacts" class="facts"></div><div id="evaluationInputsDigests" class="digest-grid" style="margin-top:.75rem"></div></div>
        </article>
      </div>
    </section>
    <section class="section two-col" aria-labelledby="blockers-title">
      <article><h2 id="blockers-title">What still blocks evaluation</h2><ul id="blockers" class="blocker-list"></ul></article>
      <article><h2>Public disclosure boundary</h2><div id="disclosure" class="disclosure"></div></article>
    </section>
  </main>
  <footer class="footer shell">Projection integrity: <code id="projectionHash"></code>. This page is a read-only static projection and cannot start, modify, or authorize a research run.</footer>
  <script id="successor-status-data" type="application/json">__SUCCESSOR_STATUS_PAYLOAD__</script>
  <script>
  'use strict';
  const DATA=JSON.parse(document.getElementById('successor-status-data').textContent);
  const byId=id=>document.getElementById(id);
  const make=(tag,className,text)=>{const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=String(text);return node};
  const safeState=value=>['verified','passed','failed','not_evaluable','blocked','pending','not_implemented','not_authorized'].includes(value)?value:'pending';
  const stateLabel=value=>String(value).replaceAll('_',' ');
  const titleLabel=value=>{const label=stateLabel(value);return label.charAt(0).toUpperCase()+label.slice(1)};
  const scopeLabel=value=>({synthetic_or_mixed_interface_only:'Synthetic or mixed · interface only',measured_input_unreviewed:'Measured input · external review pending',replayed_input_unreviewed:'Replayed input · external review pending',mixed_nonsynthetic_input_unreviewed:'Mixed nonsynthetic input · external review pending'})[value]||stateLabel(value);
  const fmt=value=>value===null||value===undefined?'not available':Number(value).toLocaleString(undefined,{maximumSignificantDigits:5});
  function addState(parent,state){const clean=safeState(state),node=make('span','state '+clean,stateLabel(clean));parent.appendChild(node)}
  function renderLifecycle(){DATA.lifecycle.forEach(stage=>{const item=make('li','life');item.dataset.state=safeState(stage.state);item.append(make('strong','',stage.label));addState(item,stage.state);item.append(make('p','',stage.detail));byId('lifecycle').append(item)})}
  function fact(label,value,kind){const node=make('div','fact');node.append(make('small','',label),make('strong',kind||'',value));return node}
  const evidenceKind=value=>['Verified','Consistent','Internally consistent','Frozen','Frozen and complete','Reconciled','Exact','Absent','Not supplied','Target free'].includes(value)?'ok':typeof value==='string'&&value.startsWith('Not ')?'locked':'';
  function renderBoundary(){const b=DATA.assurance_boundary,items=[['Evidence digests',b.digest_bound_inputs?'Bound':'Not bound',b.digest_bound_inputs?'ok':'locked'],['Frozen study plan',b.registration_verified?'Verified':'Not verified',b.registration_verified?'ok':'locked'],['Prediction commitment',b.prediction_lock_verified?'Digest-bound locally':'Not verified',b.prediction_lock_verified?'ok':'locked'],['Evaluation inputs',b.evaluation_inputs_verified?'Verified':'Not verified',b.evaluation_inputs_verified?'ok':'locked'],['External lock time',b.prediction_lock_time_externally_attested?'Attested':'Not attested',b.prediction_lock_time_externally_attested?'ok':'locked'],['Outcome custody',b.outcome_release_custody_verified?'Verified':'Not verified',b.outcome_release_custody_verified?'ok':'locked'],['One-shot scoring',b.scoring_implemented?'Implemented':'Not implemented',b.scoring_implemented?'ok':'locked'],['Evaluation runner',b.runner_authorized?'Authorized':'Not authorized',b.runner_authorized?'ok':'locked'],['Scientific use',b.scientific_use_authorized?'Authorized':'Not authorized',b.scientific_use_authorized?'ok':'locked'],['External validation',b.external_validation?'Established':'Not established',b.external_validation?'ok':'locked']];items.forEach(item=>byId('facts').append(fact(...item)))}
  function digest(label,value){const node=make('div','digest');node.append(make('span','',label),make('code','',value));return node}
  function renderIntake(){const c=DATA.campaign,cal=c.partitions.calibration,held=c.partitions.heldout;[['Evidence scope',scopeLabel(c.evidence_scope)],['Intake contract',c.intake_contract_verified?'Verified':'Not verified'],['Calibration blocks',cal.time_block_count],['Held-out blocks retained',held.time_block_count]].forEach(item=>byId('intakeFacts').append(fact(item[0],item[1],'')));byId('digests').append(digest('Campaign evidence manifest',c.evidence_manifest_sha256),digest('Calibration content commitment',cal.content_sha256),digest('Held-out content commitment',held.content_sha256))}
  const intervalLabels={background_work_per_agent_s:'Background work / agent / s',admission_work_units_per_agent:'Admission work / agent',capacity_units_per_second:'Capacity / s',service_time_window_mean_ms:'Service-time mean, ms',service_time_between_window_standard_deviation_ms:'Between-window service SD, ms',max_wait_s:'Maximum wait, s',dropped_work_fraction:'Dropped-work fraction',deferred_work_fraction:'Deferred-work fraction'};
  function intervalRow(name,value){const row=make('div','metric-row');row.append(make('label','',intervalLabels[name]||name));const holder=make('div','');if(!value){holder.append(make('div','interval-value','not available'));row.append(holder);return row}holder.append(make('div','interval-value',fmt(value.lower)+'  /  '+fmt(value.point)+'  /  '+fmt(value.upper)+'   [lower / point / upper]'));const track=make('div','whisker');const width=value.upper-value.lower;const pct=width>0?Math.max(0,Math.min(100,(value.point-value.lower)/width*100)):50;track.style.setProperty('--point',pct+'%');track.setAttribute('role','img');track.setAttribute('aria-label',(intervalLabels[name]||name)+': lower '+fmt(value.lower)+', point '+fmt(value.point)+', upper '+fmt(value.upper));holder.append(track);row.append(holder);return row}
  function renderResource(resource){const card=make('details','resource');card.dataset.state=safeState(resource.gate_status);const summary=make('summary','');summary.append(make('strong','',titleLabel(resource.resource_type)));addState(summary,resource.gate_status);card.append(summary);const body=make('div','resource-body');const diagnostics=make('dl','diagnostics');diagnostics.setAttribute('aria-label','Resource fit diagnostics');[['Observations',resource.observation_count],['Time blocks',resource.time_block_count],['Scaled design rank',resource.scaled_design_rank],['Scaled condition number',fmt(resource.scaled_design_condition_number)],['Normalized RMSE',fmt(resource.weighted_normalized_rmse)],['Absolute weighted relative bias',fmt(resource.absolute_weighted_relative_bias)],['Weighted R²',fmt(resource.weighted_r_squared)],['Bootstrap success',fmt(resource.bootstrap_success_fraction)]].forEach(item=>{const d=make('div','diagnostic');d.append(make('dt','',item[0]),make('dd','',item[1]));diagnostics.append(d)});body.append(diagnostics);Object.entries(resource.intervals).forEach(([name,value])=>body.append(intervalRow(name,value)));if(resource.blocking_reasons.length){const list=make('ul','blocker-list');resource.blocking_reasons.forEach(reason=>list.append(make('li','',titleLabel(reason))));body.append(list)}card.append(body);return card}
  function renderGlobalGate(criterion){const node=make('article','gate');node.append(make('strong','',titleLabel(criterion.criterion)));addState(node,criterion.state);node.append(make('small','',criterion.observed===null?'Not evaluable':'Observed '+fmt(criterion.observed)+' '+criterion.operator+' '+fmt(criterion.threshold)));return node}
  function renderFit(){const fit=DATA.fit;if(!fit){byId('fitEmpty').hidden=false;byId('fitEmpty').textContent='No fit package is connected. Intake remains visible while calibration readiness is pending.';addState(byId('fitState'),'pending');return}addState(byId('fitState'),fit.gate_status);byId('fitContent').hidden=false;fit.global_criteria.forEach(criterion=>byId('globalGates').append(renderGlobalGate(criterion)));const states=['all','passed','failed','not_evaluable'];states.forEach((state,index)=>{const count=state==='all'?fit.resources.length:fit.resource_status_counts[state];const button=make('button','filter',stateLabel(state)+' · '+count);button.type='button';button.dataset.filter=state;button.setAttribute('aria-pressed',index===0?'true':'false');button.addEventListener('click',()=>{document.querySelectorAll('.filter').forEach(item=>item.setAttribute('aria-pressed','false'));button.setAttribute('aria-pressed','true');document.querySelectorAll('.resource').forEach(item=>{item.hidden=state!=='all'&&item.dataset.state!==state})});byId('resourceFilters').append(button)});fit.resources.forEach(resource=>byId('resourceList').append(renderResource(resource)))}
  function renderAdapter(){const adapter=DATA.adapter;if(!adapter){byId('adapterEmpty').hidden=false;byId('adapterEmpty').textContent='No verified adapter package is connected. No simulator semantics are inferred or filled in.';addState(byId('adapterState'),'pending');return}addState(byId('adapterState'),'verified');byId('adapterContent').hidden=false;adapter.resources.forEach(resource=>{const row=make('tr','');[titleLabel(resource.resource_type),stateLabel(resource.arrival_process),stateLabel(resource.service_time_distribution),stateLabel(resource.overload_behavior),fmt(resource.capacity_units_per_second),fmt(resource.max_wait_s),stateLabel(resource.parameter_class)].forEach(value=>row.append(make('td','',value)));byId('adapterRows').append(row)});adapter.simulator_limitations.forEach(item=>byId('limitations').append(make('li','',titleLabel(item))))}
  function renderRegistration(){const item=DATA.registration;if(!item){byId('registrationEmpty').hidden=false;byId('registrationEmpty').textContent='No verified frozen study-plan package is connected.';addState(byId('registrationState'),'pending');return}addState(byId('registrationState'),'verified');byId('registrationContent').hidden=false;[['Mode',titleLabel(item.registration_mode)],['Planned cells',item.planned_cell_count],['Planned time blocks',item.planned_time_block_count],['Upstream chain',item.upstream_chain_verified?'Verified':'Not verified'],['Declared chronology',item.chronology_consistent?'Consistent':'Not verified'],['Time attestation',item.registration_time_externally_attested?'Externally attested':'Not externally attested'],['Prediction formula',item.prediction_formula_frozen?'Frozen':'Not frozen'],['Transfer criteria',item.criteria_frozen&&item.numeric_thresholds_complete?'Frozen and complete':'Not complete']].forEach(value=>byId('registrationFacts').append(fact(value[0],value[1],evidenceKind(value[1]))));[['Registration manifest',item.registration_manifest_sha256],['Study plan',item.plan_sha256],['Transfer contract',item.transfer_contract_sha256],['Implementation',item.implementation_sha256]].forEach(value=>byId('registrationDigests').append(digest(value[0],value[1])))}
  function renderPredictionLock(){const item=DATA.prediction_lock;if(!item){byId('predictionLockEmpty').hidden=false;byId('predictionLockEmpty').textContent='No verified target-free prediction-lock package is connected.';addState(byId('predictionLockState'),'pending');return}addState(byId('predictionLockState'),'verified');byId('predictionLockContent').hidden=false;[['Prediction rows',item.prediction_row_count],['Planned cells',item.planned_cell_count],['Planned time blocks',item.planned_time_block_count],['Resources',item.resource_count],['Paired bootstrap draws',item.paired_bootstrap_replication_count],['Upstream chain',item.upstream_chain_verified?'Verified':'Not verified'],['Registered semantics',item.registered_semantics_reconciled?'Reconciled':'Not reconciled'],['Predictor design',item.planned_predictor_design_reconciled?'Reconciled':'Not reconciled'],['Prediction formula',item.prediction_formula_frozen?'Frozen':'Not frozen'],['Comparator formula',item.comparator_formula_frozen?'Frozen':'Not frozen'],['Future evaluation campaign input',item.future_evaluation_campaign_not_supplied?'Not supplied':'Supplied'],['Outcome values in prediction artifact',item.prediction_rows_target_free?'Absent':'Present'],['Declared lock ordering',item.local_lock_chronology_consistent?'Internally consistent':'Not verified'],['Local workflow commitment',item.workflow_prediction_commitment?'Verified':'Not verified'],['External lock time',item.prediction_lock_time_externally_attested?'Attested':'Not attested']].forEach(value=>byId('predictionLockFacts').append(fact(value[0],value[1],evidenceKind(value[1]))));[['Prediction-lock manifest',item.prediction_lock_manifest_sha256],['Prediction-row content',item.prediction_rows_content_sha256],['Prediction-parameter draws',item.prediction_parameter_draws_content_sha256],['Frozen registration manifest',item.registration_manifest_sha256]].forEach(value=>byId('predictionLockDigests').append(digest(value[0],value[1])))}
  function renderEvaluationInputs(){const item=DATA.evaluation_inputs;if(!item){byId('evaluationInputsEmpty').hidden=false;byId('evaluationInputsEmpty').textContent='No verified evaluation-input package is connected.';addState(byId('evaluationInputsState'),'pending');return}addState(byId('evaluationInputsState'),'verified');byId('evaluationInputsContent').hidden=false;[['Realized cells',item.realized_cell_count],['Realized time blocks',item.realized_time_block_count],['Campaign identity',item.campaign_identity_reconciled?'Reconciled':'Not reconciled'],['Collection window',item.collection_window_reconciled?'Reconciled':'Not reconciled'],['Predictor design',item.predictor_design_reconciled?'Reconciled':'Not reconciled'],['Plan coverage',item.exact_cell_block_reconciliation?'Exact':'Not exact'],['Declared chronology',item.chronology_consistent?'Consistent':'Not verified'],['Prediction-lock binding',item.prediction_lock_binding_reconciled?'Reconciled':'Not reconciled'],['Prediction rows',item.prediction_rows_target_free?'Target free':'Not target free'],['Workflow commitment',item.workflow_prediction_commitment?'Verified':'Not verified'],['External lock time',item.prediction_lock_time_externally_attested?'Attested':'Not attested'],['Scientific pre-outcome lock',item.prediction_rows_preoutcome_locked?'Established':'Not established'],['Outcome custody',item.outcome_release_custody_verified?'Verified':'Not verified']].forEach(value=>byId('evaluationInputsFacts').append(fact(value[0],value[1],evidenceKind(value[1]))));[['Evaluation-input manifest',item.evaluation_inputs_manifest_sha256],['Prediction-lock manifest',item.prediction_lock_manifest_sha256],['Evaluation campaign evidence',item.evaluation_campaign_evidence_manifest_sha256],['Held-out content commitment',item.evaluation_heldout_content_sha256],['Frozen registration manifest',item.registration_manifest_sha256]].forEach(value=>byId('evaluationInputsDigests').append(digest(value[0],value[1])))}
  function renderBlockers(){DATA.blocking_conditions.forEach(item=>byId('blockers').append(make('li','',titleLabel(item))));[['Included',DATA.disclosure_boundary.includes],['Excluded',DATA.disclosure_boundary.excludes]].forEach(([title,items])=>{const article=make('article','');article.append(make('h3','',title));const list=make('ul','');items.forEach(item=>list.append(make('li','',item)));article.append(list);byId('disclosure').append(article)})}
  renderLifecycle();renderBoundary();renderIntake();renderFit();renderAdapter();renderRegistration();renderPredictionLock();renderEvaluationInputs();renderBlockers();byId('projectionHash').textContent=DATA.projection_sha256;
  </script>
</body>
</html>
"""


__all__ = [
    "STATUS_SCHEMA_VERSION",
    "SuccessorStatusBundle",
    "assemble_successor_status",
    "build_successor_status",
    "load_successor_status",
    "write_successor_status_assets",
]
