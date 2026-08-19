from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fleet_sim.control_plane.resource_network import ResourceType
from fleet_sim.empirical.assurance_campaign import (
    PACKAGE_FILES,
    EmpiricalCampaignInput,
    read_empirical_campaign,
    validate_campaign_manifest,
    validate_campaign_measurements,
    verify_empirical_campaign_package,
    write_empirical_campaign_package,
)

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_TEMPLATE = ROOT / "examples" / "empirical_assurance_campaign_template.json"
MEASUREMENT_TEMPLATE = ROOT / "examples" / "empirical_assurance_measurements_template.csv"
BASE_TEMPLATE = ROOT / "examples" / "assurance_resource_measurements_template.csv"
CAMPAIGN_SCHEMA = ROOT / "schemas" / "empirical_assurance_campaign.schema.json"
MEASUREMENT_SCHEMA = ROOT / "schemas" / "empirical_assurance_measurements.schema.json"


def _manifest() -> dict[str, object]:
    return json.loads(CAMPAIGN_TEMPLATE.read_text(encoding="utf-8"))


def _frame() -> pd.DataFrame:
    return pd.read_csv(MEASUREMENT_TEMPLATE)


def _write_sources(
    tmp_path: Path,
    *,
    manifest: dict[str, object] | None = None,
    frame: pd.DataFrame | None = None,
) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    campaign_path = tmp_path / "campaign.json"
    measurement_path = tmp_path / "measurements.csv"
    campaign_path.write_text(
        json.dumps(_manifest() if manifest is None else manifest, indent=2),
        encoding="utf-8",
    )
    (_frame() if frame is None else frame).to_csv(measurement_path, index=False)
    return measurement_path, campaign_path


def _read(measurement_path: Path, campaign_path: Path) -> EmpiricalCampaignInput:
    return read_empirical_campaign(
        measurement_path,
        campaign_path,
        campaign_schema_path=CAMPAIGN_SCHEMA,
        measurement_schema_path=MEASUREMENT_SCHEMA,
    )


def _public_manifest(source_type: str) -> dict[str, object]:
    manifest = _manifest()
    manifest["source_type"] = source_type
    authority = manifest["authority"]
    instrumentation = manifest["instrumentation"]
    assert isinstance(authority, dict)
    assert isinstance(instrumentation, dict)
    authority["collection_authorized"] = True
    authority["data_classification"] = "public"
    instrumentation["quality_reviewed"] = True
    return manifest


def _rewrite_self_integrity(package: Path, evidence: dict[str, object]) -> None:
    evidence.pop("self_integrity_sha256", None)
    canonical = json.dumps(
        evidence,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    evidence["self_integrity_sha256"] = hashlib.sha256(canonical).hexdigest()
    (package / "evidence_manifest.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_templates_preserve_base_measurements_and_cover_contract() -> None:
    empirical = _frame()
    baseline = pd.read_csv(BASE_TEMPLATE)
    pd.testing.assert_frame_equal(
        empirical[list(baseline.columns)],
        baseline,
        check_dtype=False,
    )
    assert len(empirical) == 20
    assert set(empirical["resource_type"]) == {item.value for item in ResourceType}
    assert empirical.groupby("partition").size().to_dict() == {
        "calibration": 10,
        "heldout": 10,
    }

    campaign_schema = json.loads(CAMPAIGN_SCHEMA.read_text(encoding="utf-8"))
    measurement_schema = json.loads(MEASUREMENT_SCHEMA.read_text(encoding="utf-8"))
    assert campaign_schema["$schema"].endswith("draft/2020-12/schema")
    assert measurement_schema["$schema"].endswith("draft/2020-12/schema")
    assert set(measurement_schema["required"]) == set(empirical.columns)
    assert measurement_schema["additionalProperties"] is False


def test_template_reads_with_bounded_nonvalidating_scope(tmp_path: Path) -> None:
    measurement_path, campaign_path = _write_sources(tmp_path)
    campaign = _read(measurement_path, campaign_path)
    assert len(campaign.calibration) == 10
    assert len(campaign.heldout) == 10
    assert campaign.evidence_scope == "synthetic_or_mixed_interface_only"
    assert campaign.dataset_id.startswith("assurance-campaign-")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (("authority", "collection_authorized", "true"), "Boolean"),
        (("authority", "data_rights_confirmed", 1), "Boolean"),
        (("instrumentation", "sampling_interval_ms", "1000"), "numeric"),
        ((None, "collection_start", "2026-08-19T11:59:59"), "timezone-aware"),
    ],
)
def test_manifest_runtime_types_match_the_closed_contract(
    mutation: tuple[str | None, str, object],
    message: str,
) -> None:
    manifest = _manifest()
    section, key, value = mutation
    if section is None:
        manifest[key] = value
    else:
        selected = manifest[section]
        assert isinstance(selected, dict)
        selected[key] = value
    with pytest.raises((TypeError, ValueError), match=message):
        validate_campaign_manifest(manifest)


def test_duplicate_allowed_use_and_unsupported_storage_classification_fail() -> None:
    duplicate = _manifest()
    authority = duplicate["authority"]
    assert isinstance(authority, dict)
    uses = authority["allowed_uses"]
    assert isinstance(uses, list)
    uses.append("research_calibration")
    with pytest.raises(ValueError, match="duplicates"):
        validate_campaign_manifest(duplicate)

    controlled = _public_manifest("measured")
    authority = controlled["authority"]
    assert isinstance(authority, dict)
    authority["data_classification"] = "controlled_unclassified"
    with pytest.raises(ValueError, match="classification"):
        validate_campaign_manifest(controlled)


def test_runtime_rejects_unsafe_ids_naive_rows_and_boolean_numerics() -> None:
    frame = _frame()
    frame.loc[0, "time_block_id"] = "../escape"
    with pytest.raises(ValueError, match="portable identifier"):
        validate_campaign_measurements(frame, _manifest())

    frame = _frame()
    frame["timestamp"] = frame["timestamp"].str.removesuffix("Z")
    with pytest.raises(ValueError, match="explicit UTC offset"):
        validate_campaign_measurements(frame, _manifest())

    for column in ("fleet_size", "queue_depth", "capacity_units_per_second", "missing_fraction"):
        frame = _frame().astype({column: object})
        frame.at[0, column] = True
        with pytest.raises(TypeError, match="Boolean"):
            validate_campaign_measurements(frame, _manifest())


def test_integer_counts_are_exact_and_bounded() -> None:
    frame = _frame()
    maximum = int(np.iinfo(np.int64).max)
    frame["fleet_size"] = pd.Series([maximum] * len(frame), dtype=object)
    validated = validate_campaign_measurements(frame, _manifest())
    assert set(validated["fleet_size"]) == {maximum}

    frame.at[0, "fleet_size"] = maximum + 1
    with pytest.raises(ValueError, match="int64 range"):
        validate_campaign_measurements(frame, _manifest())


@pytest.mark.parametrize(
    "source_types,manifest_source,expected_scope",
    [
        (["measured"], "measured", "measured_input_unreviewed"),
        (["replayed"], "replayed", "replayed_input_unreviewed"),
        (["measured", "replayed"], "mixed", "mixed_nonsynthetic_input_unreviewed"),
        (["synthetic", "replayed"], "mixed", "synthetic_or_mixed_interface_only"),
    ],
)
def test_evidence_scope_never_promotes_input_to_external_validation(
    tmp_path: Path,
    source_types: list[str],
    manifest_source: str,
    expected_scope: str,
) -> None:
    frame = _frame()
    for index, source_type in enumerate(source_types):
        frame.loc[index :: len(source_types), "source_type"] = source_type
    manifest = _public_manifest(manifest_source)
    measurement_path, campaign_path = _write_sources(
        tmp_path, manifest=manifest, frame=frame
    )
    campaign = _read(measurement_path, campaign_path)
    assert campaign.evidence_scope == expected_scope
    package = write_empirical_campaign_package(campaign, tmp_path / "package")
    checked = verify_empirical_campaign_package(
        package,
        campaign_schema_path=CAMPAIGN_SCHEMA,
        measurement_schema_path=MEASUREMENT_SCHEMA,
    )
    assert checked.evidence_scope == expected_scope
    assert checked.external_validation is False
    assert checked.scientific_use_authorized is False


@pytest.mark.parametrize(
    ("section", "field", "value", "message"),
    [
        ("authority", "collection_authorized", False, "authorized"),
        ("authority", "data_rights_confirmed", False, "rights"),
        ("instrumentation", "quality_reviewed", False, "quality"),
        ("authority", "authorization_reference", "", "nonempty"),
        ("authority", "data_rights_reference", "/private/rights.txt", "local"),
        ("authority", "data_classification", "synthetic", "classification"),
    ],
)
def test_nonsynthetic_authority_gate_fails_closed(
    section: str,
    field: str,
    value: object,
    message: str,
) -> None:
    manifest = _public_manifest("measured")
    selected = manifest[section]
    assert isinstance(selected, dict)
    selected[field] = value
    with pytest.raises((TypeError, ValueError), match=message):
        validate_campaign_manifest(manifest)


def test_prospective_windows_and_block_coherence_are_enforced() -> None:
    frame = _frame()
    frame.loc[frame["partition"] == "calibration", "timestamp"] = "2026-08-19T12:00:01Z"
    frame.loc[frame["partition"] == "heldout", "timestamp"] = "2026-08-19T12:00:00Z"
    with pytest.raises(ValueError, match="prospective heldout"):
        validate_campaign_measurements(frame, _manifest())

    frame = _frame()
    frame["window_duration_ms"] = 1001
    frame.loc[frame["partition"] == "heldout", "timestamp"] = "2026-08-19T12:00:02Z"
    manifest = _manifest()
    manifest["collection_end"] = "2026-08-19T12:00:04Z"
    with pytest.raises(ValueError, match="sampling interval"):
        validate_campaign_measurements(frame, manifest)

    frame = _frame()
    frame.at[0, "timestamp"] = "2026-08-19T11:59:59.100Z"
    with pytest.raises(ValueError, match="aligned timestamp"):
        validate_campaign_measurements(frame, _manifest())

    frame = _frame()
    frame.at[0, "fleet_size"] = 101
    with pytest.raises(ValueError, match="one fleet size"):
        validate_campaign_measurements(frame, _manifest())


def test_partition_and_resource_mapping_fail_closed() -> None:
    frame = _frame().drop(index=0)
    with pytest.raises(ValueError, match="all ten resource types"):
        validate_campaign_measurements(frame, _manifest())

    frame = _frame()
    frame.loc[frame["partition"] == "heldout", "time_block_id"] = "calibration-window-001"
    with pytest.raises(ValueError, match="cannot cross"):
        validate_campaign_measurements(frame, _manifest())

    frame = _frame()
    heldout_identity = (frame["partition"] == "heldout") & (
        frame["resource_type"] == "identity_issuance"
    )
    frame.loc[heldout_identity, "resource_id"] = "identity-secondary"
    with pytest.raises(ValueError, match="stable across partitions"):
        validate_campaign_measurements(frame, _manifest())


def test_canonical_identity_is_order_stable_and_schema_bound(tmp_path: Path) -> None:
    measurement_path, campaign_path = _write_sources(tmp_path / "original")
    original = _read(measurement_path, campaign_path)

    shuffled_dir = tmp_path / "shuffled"
    shuffled_dir.mkdir()
    shuffled = _frame().sample(frac=1.0, random_state=31).reset_index(drop=True)
    shuffled_measurements, shuffled_campaign = _write_sources(
        shuffled_dir,
        manifest=dict(reversed(list(_manifest().items()))),
        frame=shuffled,
    )
    reordered = _read(shuffled_measurements, shuffled_campaign)
    assert reordered.dataset_id == original.dataset_id

    changed_dir = tmp_path / "changed"
    changed_dir.mkdir()
    changed = _frame()
    changed.at[1, "arrival_count"] += 1
    changed_measurements, changed_campaign = _write_sources(changed_dir, frame=changed)
    assert _read(changed_measurements, changed_campaign).dataset_id != original.dataset_id

    altered_schema = tmp_path / "altered_schema.json"
    schema_payload = json.loads(CAMPAIGN_SCHEMA.read_text(encoding="utf-8"))
    schema_payload["description"] = "Contradictory untrusted schema"
    altered_schema.write_text(json.dumps(schema_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="trusted"):
        read_empirical_campaign(
            measurement_path,
            campaign_path,
            campaign_schema_path=altered_schema,
            measurement_schema_path=MEASUREMENT_SCHEMA,
        )


def test_quality_flags_block_silent_scientific_fitting(tmp_path: Path) -> None:
    frame = _frame()
    frame.at[1, "is_censored"] = True
    frame.at[1, "missing_fraction"] = 0.25
    measurement_path, campaign_path = _write_sources(tmp_path, frame=frame)
    package = write_empirical_campaign_package(
        _read(measurement_path, campaign_path), tmp_path / "package"
    )
    quality = json.loads((package / "quality_report.json").read_text(encoding="utf-8"))
    assert quality["data_quality_disposition"] == (
        "requires_missingness_or_censoring_policy"
    )
    assert quality["scientific_fit_status"] == (
        "blocked_pending_successor_protocol_and_fit_review"
    )
    assert len(quality["quality_actions_required"]) == 2


def test_heldout_mutation_cannot_change_calibration_content_hash(tmp_path: Path) -> None:
    original_measurements, original_campaign = _write_sources(tmp_path / "original")
    original_package = write_empirical_campaign_package(
        _read(original_measurements, original_campaign), tmp_path / "package-original"
    )

    changed = _frame()
    heldout_index = changed.index[changed["partition"] == "heldout"][0]
    changed.at[heldout_index, "arrival_count"] += 1
    changed_measurements, changed_campaign = _write_sources(
        tmp_path / "changed", frame=changed
    )
    changed_package = write_empirical_campaign_package(
        _read(changed_measurements, changed_campaign), tmp_path / "package-changed"
    )

    original_evidence = json.loads(
        (original_package / "evidence_manifest.json").read_text(encoding="utf-8")
    )
    changed_evidence = json.loads(
        (changed_package / "evidence_manifest.json").read_text(encoding="utf-8")
    )
    assert (
        original_evidence["partitions"]["calibration"]["content_sha256"]
        == changed_evidence["partitions"]["calibration"]["content_sha256"]
    )
    assert (
        original_evidence["partitions"]["heldout"]["content_sha256"]
        != changed_evidence["partitions"]["heldout"]["content_sha256"]
    )


def test_package_is_portable_digest_bound_and_defensively_copied(tmp_path: Path) -> None:
    measurement_path, campaign_path = _write_sources(tmp_path)
    campaign = _read(measurement_path, campaign_path)
    package = write_empirical_campaign_package(campaign, tmp_path / "package")
    evidence_path = package / "evidence_manifest.json"
    external_digest = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    checked = verify_empirical_campaign_package(
        package,
        campaign_schema_path=CAMPAIGN_SCHEMA,
        measurement_schema_path=MEASUREMENT_SCHEMA,
        expected_evidence_manifest_sha256=external_digest,
    )
    assert checked.externally_digest_bound is True
    assert {path.name for path in package.iterdir()} == PACKAGE_FILES
    assert all(path.is_file() and not path.is_symlink() for path in package.iterdir())
    evidence_text = evidence_path.read_text(encoding="utf-8")
    assert str(ROOT.resolve()) not in evidence_text
    assert str(measurement_path.resolve()) not in evidence_text

    returned = checked.calibration
    returned.at[0, "fleet_size"] = 1
    assert checked.calibration.at[0, "fleet_size"] != 1
    manifest = checked.evidence_manifest
    manifest["external_validation"] = True
    assert checked.evidence_manifest["external_validation"] is False

    with pytest.raises(ValueError, match="externally supplied digest"):
        verify_empirical_campaign_package(
            package,
            campaign_schema_path=CAMPAIGN_SCHEMA,
            measurement_schema_path=MEASUREMENT_SCHEMA,
            expected_evidence_manifest_sha256="0" * 64,
        )


def test_partition_file_swap_and_semantic_manifest_tamper_fail(tmp_path: Path) -> None:
    measurement_path, campaign_path = _write_sources(tmp_path)
    package = write_empirical_campaign_package(
        _read(measurement_path, campaign_path), tmp_path / "package"
    )
    calibration_path = package / "calibration_measurements.parquet"
    heldout_path = package / "heldout_measurements.parquet"
    calibration_bytes = calibration_path.read_bytes()
    heldout_bytes = heldout_path.read_bytes()
    calibration_path.write_bytes(heldout_bytes)
    heldout_path.write_bytes(calibration_bytes)
    evidence = json.loads((package / "evidence_manifest.json").read_text(encoding="utf-8"))
    for record in evidence["artifacts"]:
        artifact = package / record["path"]
        record["bytes"] = artifact.stat().st_size
        record["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    _rewrite_self_integrity(package, evidence)
    with pytest.raises(ValueError, match="calibration artifact"):
        verify_empirical_campaign_package(
            package,
            campaign_schema_path=CAMPAIGN_SCHEMA,
            measurement_schema_path=MEASUREMENT_SCHEMA,
        )


def test_rehashed_false_implementation_claim_is_rejected(tmp_path: Path) -> None:
    measurement_path, campaign_path = _write_sources(tmp_path)
    package = write_empirical_campaign_package(
        _read(measurement_path, campaign_path), tmp_path / "package"
    )
    evidence_path = package / "evidence_manifest.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["implementation"]["runtime"]["python"] = "0.0.0"
    implementation_canonical = json.dumps(
        evidence["implementation"],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    evidence["implementation_sha256"] = hashlib.sha256(
        implementation_canonical
    ).hexdigest()
    _rewrite_self_integrity(package, evidence)
    with pytest.raises(ValueError, match="implementation boundary"):
        verify_empirical_campaign_package(package)


def test_package_rejects_extra_entry_symlink_and_no_overwrite(tmp_path: Path) -> None:
    measurement_path, campaign_path = _write_sources(tmp_path)
    campaign = _read(measurement_path, campaign_path)
    package = write_empirical_campaign_package(campaign, tmp_path / "package")
    with pytest.raises(FileExistsError, match="overwrite"):
        write_empirical_campaign_package(campaign, package)

    (package / "unexpected").mkdir()
    with pytest.raises(ValueError, match="file set mismatch"):
        verify_empirical_campaign_package(
            package,
            campaign_schema_path=CAMPAIGN_SCHEMA,
            measurement_schema_path=MEASUREMENT_SCHEMA,
        )
    (package / "unexpected").rmdir()

    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    target = package / "quality_report.json"
    target.unlink()
    os.symlink(outside, target)
    with pytest.raises(ValueError, match="regular local files"):
        verify_empirical_campaign_package(
            package,
            campaign_schema_path=CAMPAIGN_SCHEMA,
            measurement_schema_path=MEASUREMENT_SCHEMA,
        )


def test_writer_failure_leaves_no_partial_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    measurement_path, campaign_path = _write_sources(tmp_path)
    campaign = _read(measurement_path, campaign_path)
    destination = tmp_path / "failed-package"

    def fail_verification(*args: object, **kwargs: object) -> None:
        raise ValueError("injected verification failure")

    monkeypatch.setattr(
        "fleet_sim.empirical.assurance_campaign.verify_empirical_campaign_package",
        fail_verification,
    )
    with pytest.raises(ValueError, match="injected"):
        write_empirical_campaign_package(campaign, destination)
    assert not destination.exists()
    assert not list(tmp_path.glob(".failed-package.*"))


def test_source_and_package_resource_limits_fail_closed(tmp_path: Path) -> None:
    measurement_path, campaign_path = _write_sources(tmp_path)
    with pytest.raises(ValueError, match="byte intake limit"):
        read_empirical_campaign(
            measurement_path,
            campaign_path,
            campaign_schema_path=CAMPAIGN_SCHEMA,
            measurement_schema_path=MEASUREMENT_SCHEMA,
            maximum_source_bytes=1,
        )
    with pytest.raises(ValueError, match="row limit"):
        read_empirical_campaign(
            measurement_path,
            campaign_path,
            campaign_schema_path=CAMPAIGN_SCHEMA,
            measurement_schema_path=MEASUREMENT_SCHEMA,
            maximum_rows=19,
        )

    package = write_empirical_campaign_package(
        _read(measurement_path, campaign_path), tmp_path / "package"
    )
    with pytest.raises(ValueError, match="byte verification limit"):
        verify_empirical_campaign_package(package, maximum_package_bytes=1)
    with pytest.raises(ValueError, match="row verification limit"):
        verify_empirical_campaign_package(package, maximum_rows=19)


def test_cli_round_trip_and_invalid_input_has_no_partial_output(tmp_path: Path) -> None:
    measurement_path, campaign_path = _write_sources(tmp_path)
    destination = tmp_path / "cli-package"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "package_assurance_campaign.py"),
            str(measurement_path),
            str(campaign_path),
            str(destination),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    output = json.loads(result.stdout)
    assert output["external_validation"] is False
    assert output["scientific_use_authorized"] is False
    assert len(output["evidence_manifest_sha256"]) == 64
    assert {path.name for path in destination.iterdir()} == PACKAGE_FILES

    invalid = _frame().drop(columns=["partition"])
    invalid_path = tmp_path / "invalid.csv"
    invalid.to_csv(invalid_path, index=False)
    invalid_destination = tmp_path / "invalid-package"
    failure = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "package_assurance_campaign.py"),
            str(invalid_path),
            str(campaign_path),
            str(invalid_destination),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert failure.returncode != 0
    assert not invalid_destination.exists()


def test_completed_stage3_frozen_files_remain_unchanged() -> None:
    manifest = json.loads(
        (ROOT / "manifests" / "stage3_preexecution_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    frozen = manifest["files"]
    assert len(frozen) == 151
    mismatches = []
    for relative_path, expected in frozen.items():
        path = ROOT / relative_path
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if actual != expected:
            mismatches.append(relative_path)
    assert mismatches == []
