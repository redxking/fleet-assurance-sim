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
from fleet_sim.empirical.resource_adapter import (
    AdaptedResourcePackageVerification,
    verify_adapted_resource_bundle,
)

STATUS_SCHEMA_VERSION = "successor-study-status-v1"
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
    "campaign_id",
    "data_rights_reference",
    "site_alias",
    "system_alias",
    "collection_start",
    "collection_end",
    "environment_description",
    "package_dir",
    "source_path",
    "local_path",
    "measurement_rows",
    "measurement_provenance",
    "policy_id",
    "raw_rows",
    "resource_id",
    "adapter_policy_id",
}
LOCAL_PATH_PATTERN = re.compile(
    r"(?:~[/\\]|/(?:Users|home|private|tmp|var|etc|opt|Volumes|mnt|srv)(?:/|$)"
    r"|[A-Za-z]:[/\\]|\\\\[^\\\s]+\\[^\\\s]+)"
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
    if isinstance(value, str) and (
        value.startswith("file://") or LOCAL_PATH_PATTERN.search(value) is not None
    ):
        raise ValueError(f"public status payload contains a local path string at {key}")
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
        "dataset_id": str(campaign.dataset_id),
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
        "calibration_fit_id": fit.calibration_fit_id,
        "model_id": fit.model_id,
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
        "global_criteria": [criterion.to_dict() for criterion in fit.global_criteria],
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
        "adapter_bundle_id": bundle.adapter_bundle_id,
        "adapter_mode": bundle.adapter_mode,
        "calibration_fit_id": bundle.calibration_fit_id,
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


def _lifecycle(
    fit: EmpiricalCalibrationPackageVerification | None,
    adapter: AdaptedResourcePackageVerification | None,
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
    return [
        {
            "stage": "intake",
            "label": "Evidence intake",
            "state": "verified",
            "detail": "Campaign package and partition commitments were fully reverified.",
        },
        {"stage": "fit", "label": "Fit quality", "state": fit_state, "detail": fit_detail},
        {
            "stage": "adapter",
            "label": "Resource adapter",
            "state": adapter_state,
            "detail": adapter_detail,
        },
        {
            "stage": "registration",
            "label": "Frozen registration",
            "state": "not_authorized",
            "detail": "No successor registration verifier is connected to this status build.",
        },
        {
            "stage": "heldout_binding",
            "label": "Held-out binding",
            "state": "not_authorized",
            "detail": "Held-out evidence is retained but not bound to a frozen protocol here.",
        },
        {
            "stage": "evaluation",
            "label": "Prospective evaluation",
            "state": "not_authorized",
            "detail": "The successor evaluation runner is not authorized or executed.",
        },
    ]


def assemble_successor_status(
    campaign: CampaignPackageVerification,
    *,
    fit: EmpiricalCalibrationPackageVerification | None = None,
    adapter: AdaptedResourcePackageVerification | None = None,
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

    fit_projection = None if fit is None else _fit_projection(fit)
    adapter_projection = None if adapter is None else _adapter_projection(adapter)
    blockers = [
        "No verified successor registration manifest is connected.",
        "Held-out evidence is not bound to a frozen successor protocol.",
        "The prospective evaluation runner is not authorized.",
        "External validation has not been established.",
    ]
    if fit is None:
        blockers.append("A verified calibration-fit package has not been supplied.")
    elif fit.fit.gate_status != "passed":
        blockers.extend(fit.fit.blocking_reasons)
    if adapter is None:
        blockers.append("A verified resource-adapter package has not been supplied.")
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
            "registration_verified": False,
            "heldout_binding_verified": False,
            "evaluation_executed": False,
        },
        "lifecycle": _lifecycle(fit, adapter),
        "campaign": campaign_projection,
        "fit": fit_projection,
        "adapter": adapter_projection,
        "blocking_conditions": blockers,
        "disclosure_boundary": {
            "includes": [
                "aggregate partition counts and integrity commitments",
                "fit-gate dispositions, diagnostics, and uncertainty intervals",
                "adapter semantics and documented simulator limitations",
            ],
            "excludes": [
                "raw measurement rows",
                "site and system aliases",
                "collection timestamps",
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
    return assemble_successor_status(
        checked_campaign,
        fit=checked_fit,
        adapter=checked_adapter,
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
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Verify evidence and build a deployable, network-free status directory."""

    destination = Path(os.path.abspath(os.fspath(output_directory)))
    resolved_destination = destination.resolve()
    source_roots = [Path(campaign_package).resolve()]
    source_roots.extend(
        Path(value).resolve() for value in (fit_package, adapter_package) if value is not None
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
    :root{--ink:#eaf2f6;--muted:#9fb2bd;--panel:#12232c;--panel2:#18303b;--line:#2d4855;--canvas:#07141b;--accent:#4bd6b2;--blue:#5db8e8;--amber:#f0bc64;--red:#f17c75;--white:#fff;--shadow:0 16px 48px rgba(0,0,0,.2);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    *{box-sizing:border-box}html{scroll-behavior:smooth;max-width:100%;overflow-x:hidden}body{margin:0;max-width:100%;overflow-x:hidden;background:radial-gradient(circle at 85% -10%,#123b46 0,transparent 35rem),var(--canvas);color:var(--ink);line-height:1.5}.skip{position:absolute;left:-9999px}.skip:focus{left:1rem;top:1rem;background:var(--white);color:#07141b;padding:.65rem 1rem;border-radius:.4rem;z-index:20}.shell{width:min(1180px,calc(100% - 2rem));margin-inline:auto;min-width:0}.masthead{padding:3.5rem 0 2rem}.eyebrow{margin:0 0 .5rem;color:var(--accent);font-size:.77rem;font-weight:800;letter-spacing:.16em;text-transform:uppercase}.masthead h1{margin:0;font-size:clamp(2rem,5vw,4.2rem);line-height:1.02;letter-spacing:-.045em;max-width:900px;overflow-wrap:break-word}.lead{max-width:720px;color:var(--muted);font-size:1.08rem;margin:1rem 0 1.4rem;overflow-wrap:break-word}.boundary{display:flex;align-items:flex-start;gap:.75rem;width:fit-content;max-width:100%;border:1px solid rgba(240,188,100,.5);background:rgba(240,188,100,.1);padding:.72rem .9rem;border-radius:.55rem;color:#ffe0aa;font-weight:750;overflow-wrap:anywhere}.boundary span{min-width:0}.boundary::before{content:"";width:.7rem;height:.7rem;flex:0 0 auto;border-radius:50%;background:var(--amber);box-shadow:0 0 0 .28rem rgba(240,188,100,.14);margin-top:.35rem}main{padding-bottom:4rem}.section{margin-top:1.2rem;min-width:0;background:linear-gradient(145deg,rgba(24,48,59,.94),rgba(14,31,40,.94));border:1px solid var(--line);border-radius:1rem;box-shadow:var(--shadow);padding:clamp(1rem,2.5vw,1.65rem)}.section-head{display:flex;justify-content:space-between;gap:1rem;align-items:end;margin-bottom:1rem;min-width:0}.section h2{font-size:1.15rem;margin:0;letter-spacing:-.015em}.section-copy{margin:.25rem 0 0;color:var(--muted);font-size:.9rem;overflow-wrap:break-word}.lifecycle{list-style:none;margin:1.4rem 0 .25rem;padding:0;display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:.5rem;counter-reset:stage}.life{position:relative;min-width:0;min-height:10rem;padding:1rem .8rem .8rem;border:1px solid var(--line);border-radius:.75rem;background:rgba(7,20,27,.54);overflow-wrap:anywhere}.life::before{counter-increment:stage;content:counter(stage);display:grid;place-items:center;width:1.75rem;height:1.75rem;border-radius:50%;background:var(--line);font-size:.78rem;font-weight:800;margin-bottom:.75rem}.life[data-state="verified"]::before,.life[data-state="passed"]::before{background:var(--accent);color:#06231c}.life[data-state="failed"]::before{background:var(--red);color:#2c0907}.life[data-state="not_evaluable"]::before,.life[data-state="blocked"]::before{background:var(--amber);color:#2a1902}.life strong{display:block;font-size:.9rem}.life p{color:var(--muted);font-size:.76rem;line-height:1.4;margin:.5rem 0 0}.state{display:inline-flex;align-items:center;gap:.35rem;margin-top:.5rem;font-size:.7rem;font-weight:800;letter-spacing:.04em;text-transform:uppercase}.state::before{content:"";width:.44rem;height:.44rem;flex:0 0 auto;border-radius:50%;background:var(--muted)}.state.verified::before,.state.passed::before{background:var(--accent)}.state.failed::before{background:var(--red)}.state.not_evaluable::before,.state.blocked::before{background:var(--amber)}.state.not_authorized::before,.state.pending::before{background:#7f929d}.facts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.65rem}.fact{min-width:0;padding:1rem;border:1px solid var(--line);border-radius:.75rem;background:rgba(7,20,27,.48)}.fact small{display:block;color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.08em}.fact strong{display:block;margin-top:.35rem;font-size:1rem;overflow-wrap:anywhere}.fact .ok{color:var(--accent)}.fact .locked{color:var(--amber)}.digest-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.55rem}.digest{min-width:0;padding:.75rem;border-left:3px solid var(--blue);background:rgba(7,20,27,.45);border-radius:.25rem}.digest span{display:block;color:var(--muted);font-size:.72rem}.digest code{display:block;margin-top:.28rem;color:#cbe8f6;font-size:.72rem;overflow-wrap:anywhere}.resource-summary{display:flex;flex-wrap:wrap;gap:.5rem;margin:.25rem 0 1rem}.filter{appearance:none;min-height:2.75rem;border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:999px;padding:.45rem .72rem;font:inherit;font-size:.78rem;cursor:pointer}.filter[aria-pressed="true"]{background:var(--ink);color:#07141b;border-color:var(--ink)}.filter:focus-visible,summary:focus-visible,.adapter-grid:focus-visible{outline:3px solid var(--blue);outline-offset:2px}.resource-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.65rem}.resource{min-width:0;border:1px solid var(--line);border-radius:.75rem;background:rgba(7,20,27,.48);overflow:hidden}.resource summary{cursor:pointer;list-style:none;padding:.85rem 1rem;display:flex;align-items:center;justify-content:space-between;gap:.75rem;min-width:0}.resource summary::-webkit-details-marker{display:none}.resource summary strong{font-size:.88rem}.resource summary small{display:block;color:var(--muted);font-weight:500;overflow-wrap:anywhere}.resource-body{border-top:1px solid var(--line);padding:.8rem 1rem 1rem}.metric-row{display:grid;grid-template-columns:minmax(9rem,1.3fr) 2fr;gap:.75rem;align-items:center;padding:.45rem 0;border-bottom:1px solid rgba(45,72,85,.55)}.metric-row:last-child{border:0}.metric-row label{font-size:.76rem;color:var(--muted)}.interval-value{font-size:.72rem;font-variant-numeric:tabular-nums}.whisker{position:relative;height:.45rem;background:#263f4b;border-radius:999px;margin-top:.35rem}.whisker::after{content:"";position:absolute;left:var(--point);top:-.2rem;width:.12rem;height:.85rem;background:var(--accent);border-radius:1rem}.diagnostics{display:grid;grid-template-columns:repeat(auto-fit,minmax(7.5rem,1fr));gap:.45rem;margin:0 0 .8rem}.diagnostic{min-width:0;padding:.55rem .6rem;background:rgba(24,48,59,.55);border-radius:.4rem}.diagnostic dt{color:var(--muted);font-size:.64rem;line-height:1.3}.diagnostic dd{margin:.2rem 0 0;font-size:.8rem;font-weight:750;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.blocker-list,.limitations{margin:.5rem 0 0;padding-left:1.1rem;color:#d5e1e6}.blocker-list li,.limitations li{margin:.35rem 0;overflow-wrap:anywhere}.adapter-grid{overflow:auto}.adapter-grid table{width:100%;border-collapse:collapse;font-size:.78rem}.adapter-grid th,.adapter-grid td{text-align:left;padding:.65rem;border-bottom:1px solid var(--line);white-space:nowrap}.adapter-grid th{color:var(--muted);font-size:.68rem;text-transform:uppercase;letter-spacing:.06em}.empty{padding:1rem;border:1px dashed var(--line);border-radius:.65rem;color:var(--muted)}.two-col{display:grid;grid-template-columns:1.1fr .9fr;gap:.75rem}.disclosure{display:grid;grid-template-columns:1fr 1fr;gap:.7rem}.disclosure article{padding:.9rem;border:1px solid var(--line);border-radius:.65rem}.disclosure h3{font-size:.85rem;margin:0 0 .5rem}.disclosure ul{margin:0;padding-left:1.1rem;color:var(--muted);font-size:.8rem}.footer{color:var(--muted);font-size:.72rem;padding:1.5rem 0 3rem}.footer code{overflow-wrap:anywhere}noscript{display:block;padding:1rem;background:#3a1e1a;color:#ffe2db}
    @media(max-width:900px){.lifecycle{grid-template-columns:repeat(3,1fr)}.facts{grid-template-columns:repeat(2,1fr)}.two-col{grid-template-columns:1fr}}
    .subhead{font-size:.82rem;margin:1rem 0 .55rem;color:var(--muted);text-transform:uppercase;letter-spacing:.07em}.gate-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.5rem}.gate{min-width:0;padding:.7rem;border:1px solid var(--line);border-radius:.55rem;background:rgba(7,20,27,.48)}.gate strong{display:block;font-size:.76rem;overflow-wrap:anywhere}.gate small{display:block;margin-top:.35rem;color:var(--muted);font-size:.68rem;overflow-wrap:anywhere}
    @media(max-width:620px){.shell{width:calc(100% - 1rem)}.masthead{padding-top:2rem}.masthead h1{font-size:clamp(2rem,10vw,3rem)}.boundary{width:100%}.lifecycle,.facts,.resource-list,.digest-grid,.disclosure,.gate-grid{grid-template-columns:minmax(0,1fr)}.life{min-height:auto}.section{border-radius:.75rem}.diagnostics{grid-template-columns:1fr}.metric-row{grid-template-columns:1fr}.section-head{align-items:start;flex-direction:column}}
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
    <p class="lead">A public-safe view of campaign intake, calibration quality, uncertainty, and simulator adaptation. Every downstream research action remains locked until a new protocol is frozen and bound to externally recorded digests.</p>
    <div class="boundary" role="status"><span>Engineering evidence only · prospective evaluation not authorized</span></div>
  </header>
  <main id="main" class="shell">
    <section class="section" aria-labelledby="life-title">
      <div class="section-head"><div><h2 id="life-title">Successor-study lifecycle</h2><p class="section-copy">The connected evidence chain ends before protocol registration and held-out evaluation.</p></div></div>
      <ol id="lifecycle" class="lifecycle"></ol>
    </section>
    <section class="section" aria-labelledby="boundary-title">
      <div class="section-head"><div><h2 id="boundary-title">Assurance boundary</h2><p class="section-copy">False is a deliberate gate, not missing metadata.</p></div></div>
      <div id="facts" class="facts"></div>
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
  const safeState=value=>['verified','passed','failed','not_evaluable','blocked','pending','not_authorized'].includes(value)?value:'pending';
  const stateLabel=value=>String(value).replaceAll('_',' ');
  const titleLabel=value=>{const label=stateLabel(value);return label.charAt(0).toUpperCase()+label.slice(1)};
  const scopeLabel=value=>({synthetic_or_mixed_interface_only:'Synthetic or mixed · interface only',measured_input_unreviewed:'Measured input · external review pending',replayed_input_unreviewed:'Replayed input · external review pending',mixed_nonsynthetic_input_unreviewed:'Mixed nonsynthetic input · external review pending'})[value]||stateLabel(value);
  const fmt=value=>value===null||value===undefined?'not available':Number(value).toLocaleString(undefined,{maximumSignificantDigits:5});
  function addState(parent,state){const clean=safeState(state),node=make('span','state '+clean,stateLabel(clean));parent.appendChild(node)}
  function renderLifecycle(){DATA.lifecycle.forEach(stage=>{const item=make('li','life');item.dataset.state=safeState(stage.state);item.append(make('strong','',stage.label));addState(item,stage.state);item.append(make('p','',stage.detail));byId('lifecycle').append(item)})}
  function fact(label,value,kind){const node=make('div','fact');node.append(make('small','',label),make('strong',kind||'',value));return node}
  function renderBoundary(){const b=DATA.assurance_boundary,items=[['Evidence digests',b.digest_bound_inputs?'Bound':'Not bound',b.digest_bound_inputs?'ok':'locked'],['Scientific use',b.scientific_use_authorized?'Authorized':'Not authorized',b.scientific_use_authorized?'ok':'locked'],['Evaluation runner',b.runner_authorized?'Authorized':'Locked',b.runner_authorized?'ok':'locked'],['External validation',b.external_validation?'Established':'Not established',b.external_validation?'ok':'locked']];items.forEach(item=>byId('facts').append(fact(...item)))}
  function digest(label,value){const node=make('div','digest');node.append(make('span','',label),make('code','',value));return node}
  function renderIntake(){const c=DATA.campaign,cal=c.partitions.calibration,held=c.partitions.heldout;[['Evidence scope',scopeLabel(c.evidence_scope)],['Intake contract',c.intake_contract_verified?'Verified':'Not verified'],['Calibration blocks',cal.time_block_count],['Held-out blocks retained',held.time_block_count]].forEach(item=>byId('intakeFacts').append(fact(item[0],item[1],'')));byId('digests').append(digest('Campaign evidence manifest',c.evidence_manifest_sha256),digest('Calibration content commitment',cal.content_sha256),digest('Held-out content commitment',held.content_sha256),digest('Dataset identity',c.dataset_id))}
  const intervalLabels={background_work_per_agent_s:'Background work / agent / s',admission_work_units_per_agent:'Admission work / agent',capacity_units_per_second:'Capacity / s',service_time_window_mean_ms:'Service-time mean, ms',service_time_between_window_standard_deviation_ms:'Between-window service SD, ms',max_wait_s:'Maximum wait, s',dropped_work_fraction:'Dropped-work fraction',deferred_work_fraction:'Deferred-work fraction'};
  function intervalRow(name,value){const row=make('div','metric-row');row.append(make('label','',intervalLabels[name]||name));const holder=make('div','');if(!value){holder.append(make('div','interval-value','not available'));row.append(holder);return row}holder.append(make('div','interval-value',fmt(value.lower)+'  /  '+fmt(value.point)+'  /  '+fmt(value.upper)+'   [lower / point / upper]'));const track=make('div','whisker');const width=value.upper-value.lower;const pct=width>0?Math.max(0,Math.min(100,(value.point-value.lower)/width*100)):50;track.style.setProperty('--point',pct+'%');track.setAttribute('role','img');track.setAttribute('aria-label',(intervalLabels[name]||name)+': lower '+fmt(value.lower)+', point '+fmt(value.point)+', upper '+fmt(value.upper));holder.append(track);row.append(holder);return row}
  function renderResource(resource){const card=make('details','resource');card.dataset.state=safeState(resource.gate_status);const summary=make('summary','');summary.append(make('strong','',titleLabel(resource.resource_type)));addState(summary,resource.gate_status);card.append(summary);const body=make('div','resource-body');const diagnostics=make('dl','diagnostics');diagnostics.setAttribute('aria-label','Resource fit diagnostics');[['Observations',resource.observation_count],['Time blocks',resource.time_block_count],['Scaled design rank',resource.scaled_design_rank],['Scaled condition number',fmt(resource.scaled_design_condition_number)],['Normalized RMSE',fmt(resource.weighted_normalized_rmse)],['Absolute weighted relative bias',fmt(resource.absolute_weighted_relative_bias)],['Weighted R²',fmt(resource.weighted_r_squared)],['Bootstrap success',fmt(resource.bootstrap_success_fraction)]].forEach(item=>{const d=make('div','diagnostic');d.append(make('dt','',item[0]),make('dd','',item[1]));diagnostics.append(d)});body.append(diagnostics);Object.entries(resource.intervals).forEach(([name,value])=>body.append(intervalRow(name,value)));if(resource.blocking_reasons.length){const list=make('ul','blocker-list');resource.blocking_reasons.forEach(reason=>list.append(make('li','',titleLabel(reason))));body.append(list)}card.append(body);return card}
  function renderGlobalGate(criterion){const node=make('article','gate');node.append(make('strong','',titleLabel(criterion.criterion_id)));addState(node,criterion.state);node.append(make('small','',criterion.observed===null?'Not evaluable':'Observed '+fmt(criterion.observed)+' '+criterion.operator+' '+fmt(criterion.threshold)));return node}
  function renderFit(){const fit=DATA.fit;if(!fit){byId('fitEmpty').hidden=false;byId('fitEmpty').textContent='No fit package is connected. Intake remains visible while calibration readiness is pending.';addState(byId('fitState'),'pending');return}addState(byId('fitState'),fit.gate_status);byId('fitContent').hidden=false;fit.global_criteria.forEach(criterion=>byId('globalGates').append(renderGlobalGate(criterion)));const states=['all','passed','failed','not_evaluable'];states.forEach((state,index)=>{const count=state==='all'?fit.resources.length:fit.resource_status_counts[state];const button=make('button','filter',stateLabel(state)+' · '+count);button.type='button';button.dataset.filter=state;button.setAttribute('aria-pressed',index===0?'true':'false');button.addEventListener('click',()=>{document.querySelectorAll('.filter').forEach(item=>item.setAttribute('aria-pressed','false'));button.setAttribute('aria-pressed','true');document.querySelectorAll('.resource').forEach(item=>{item.hidden=state!=='all'&&item.dataset.state!==state})});byId('resourceFilters').append(button)});fit.resources.forEach(resource=>byId('resourceList').append(renderResource(resource)))}
  function renderAdapter(){const adapter=DATA.adapter;if(!adapter){byId('adapterEmpty').hidden=false;byId('adapterEmpty').textContent='No verified adapter package is connected. No simulator semantics are inferred or filled in.';addState(byId('adapterState'),'pending');return}addState(byId('adapterState'),'verified');byId('adapterContent').hidden=false;adapter.resources.forEach(resource=>{const row=make('tr','');[titleLabel(resource.resource_type),stateLabel(resource.arrival_process),stateLabel(resource.service_time_distribution),stateLabel(resource.overload_behavior),fmt(resource.capacity_units_per_second),fmt(resource.max_wait_s),stateLabel(resource.parameter_class)].forEach(value=>row.append(make('td','',value)));byId('adapterRows').append(row)});adapter.simulator_limitations.forEach(item=>byId('limitations').append(make('li','',titleLabel(item))))}
  function renderBlockers(){DATA.blocking_conditions.forEach(item=>byId('blockers').append(make('li','',titleLabel(item))));[['Included',DATA.disclosure_boundary.includes],['Excluded',DATA.disclosure_boundary.excludes]].forEach(([title,items])=>{const article=make('article','');article.append(make('h3','',title));const list=make('ul','');items.forEach(item=>list.append(make('li','',item)));article.append(list);byId('disclosure').append(article)})}
  renderLifecycle();renderBoundary();renderIntake();renderFit();renderAdapter();renderBlockers();byId('projectionHash').textContent=DATA.projection_sha256;
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
