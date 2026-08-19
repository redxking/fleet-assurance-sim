import json
from pathlib import Path

import pytest

from fleet_sim.experiments.stage3_protocol import (
    FrozenInputError,
    build_preexecution_manifest,
    load_preexecution_manifest,
    require_frozen_environment,
    require_frozen_inputs,
    reserve_execution_directory,
    validate_safe_identifier,
    verify_frozen_inputs,
    write_new_json,
)


def test_manifest_detects_frozen_input_change(tmp_path: Path):
    source = tmp_path / "protocol.md"
    source.write_text("frozen\n", encoding="utf-8")
    manifest = build_preexecution_manifest(
        tmp_path,
        protocol_id="FAS-S3-TEST",
        frozen_files=["protocol.md"],
        evidence_scope="test_only",
    )

    passed, checks = verify_frozen_inputs(tmp_path, manifest)
    assert passed
    assert checks[0].match

    source.write_text("changed\n", encoding="utf-8")
    passed, checks = verify_frozen_inputs(tmp_path, manifest)
    assert not passed
    assert not checks[0].match
    with pytest.raises(FrozenInputError):
        require_frozen_inputs(tmp_path, manifest)


def test_manifest_rejects_path_traversal(tmp_path: Path):
    with pytest.raises(ValueError, match="repository relative"):
        build_preexecution_manifest(
            tmp_path,
            protocol_id="FAS-S3-TEST",
            frozen_files=["../outside.txt"],
            evidence_scope="test_only",
        )


def test_execution_directory_and_json_are_no_overwrite(tmp_path: Path):
    destination = reserve_execution_directory(
        tmp_path,
        protocol_hash="abc123",
        execution_id="run-001",
    )
    assert destination.is_dir()
    with pytest.raises(FileExistsError):
        reserve_execution_directory(
            tmp_path,
            protocol_hash="abc123",
            execution_id="run-001",
        )

    artifact = destination / "evidence.json"
    write_new_json(artifact, {"status": "complete"})
    with pytest.raises(FileExistsError):
        write_new_json(artifact, {"status": "replacement"})


def test_manifest_hash_authenticates_execution_contract(tmp_path: Path):
    source = tmp_path / "protocol.md"
    source.write_text("frozen\n", encoding="utf-8")
    manifest = build_preexecution_manifest(
        tmp_path,
        protocol_id="FAS-S3-TEST",
        frozen_files=["protocol.md"],
        evidence_scope="test_only",
        execution_contract={"execution_id": "run-001", "bootstrap_draws": 5000},
    )
    manifest_path = tmp_path / "manifest.json"
    write_new_json(manifest_path, manifest)
    assert load_preexecution_manifest(manifest_path)["protocol_hash"] == manifest["protocol_hash"]

    tampered = json.loads(manifest_path.read_text(encoding="utf-8"))
    tampered["execution_contract"]["bootstrap_draws"] = 5
    manifest_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(FrozenInputError, match="protocol hash is invalid"):
        load_preexecution_manifest(manifest_path)


def test_manifest_hash_authenticates_environment_at_freeze(tmp_path: Path):
    source = tmp_path / "protocol.md"
    source.write_text("frozen\n", encoding="utf-8")
    manifest = build_preexecution_manifest(
        tmp_path,
        protocol_id="FAS-S3-TEST",
        frozen_files=["protocol.md"],
        evidence_scope="test_only",
    )
    manifest_path = tmp_path / "manifest.json"
    write_new_json(manifest_path, manifest)

    tampered = json.loads(manifest_path.read_text(encoding="utf-8"))
    tampered["environment_at_freeze"]["machine"] = "tampered-machine"
    manifest_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(FrozenInputError, match="protocol hash is invalid"):
        load_preexecution_manifest(manifest_path)


def test_manifest_hash_authenticates_protocol_status(tmp_path: Path):
    source = tmp_path / "protocol.md"
    source.write_text("frozen\n", encoding="utf-8")
    manifest = build_preexecution_manifest(
        tmp_path,
        protocol_id="FAS-S3-TEST",
        frozen_files=["protocol.md"],
        evidence_scope="test_only",
    )
    manifest_path = tmp_path / "manifest.json"
    write_new_json(manifest_path, manifest)

    tampered = json.loads(manifest_path.read_text(encoding="utf-8"))
    tampered["protocol_status"] = "tampered"
    manifest_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(FrozenInputError, match="protocol hash is invalid"):
        load_preexecution_manifest(manifest_path)


def test_environment_gate_requires_exact_live_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "protocol.md"
    source.write_text("frozen\n", encoding="utf-8")
    manifest = build_preexecution_manifest(
        tmp_path,
        protocol_id="FAS-S3-TEST",
        frozen_files=["protocol.md"],
        evidence_scope="test_only",
    )
    assert require_frozen_environment(manifest) == manifest["environment_at_freeze"]

    monkeypatch.setenv("OMP_NUM_THREADS", "environment-mismatch")
    with pytest.raises(FrozenInputError, match="thread_controls"):
        require_frozen_environment(manifest)


def test_execution_identifier_is_rejected_before_manifest_build(tmp_path: Path):
    with pytest.raises(ValueError, match="execution_id contains unsafe characters"):
        validate_safe_identifier("../unsafe", label="execution_id")

    source = tmp_path / "protocol.md"
    source.write_text("frozen\n", encoding="utf-8")
    with pytest.raises(ValueError, match="execution_id contains unsafe characters"):
        build_preexecution_manifest(
            tmp_path,
            protocol_id="FAS-S3-TEST",
            frozen_files=["protocol.md"],
            evidence_scope="test_only",
            execution_contract={"execution_id": "../unsafe"},
        )
