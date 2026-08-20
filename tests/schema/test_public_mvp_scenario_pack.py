from __future__ import annotations

import hashlib
import json
import math
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, cast

import pytest

from fleet_sim.public_mvp import (
    CAPACITY_CASES,
    CAPACITY_SCALING,
    DEFAULT_REPLICATIONS,
    DEFAULT_ROOT_SEED,
    FLEET_SIZES,
    NO_BINDING_RESOURCE,
    PUBLIC_MVP_PACKAGE_FILES,
    SCENARIO_PROFILES,
    build_public_mvp_scenario_pack,
    verify_public_mvp_scenario_pack,
)
from fleet_sim.public_mvp import scenario_pack as scenario_pack_module

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "public_mvp_scenario_pack.schema.json"
CHECKED_PACKAGE = ROOT / "site" / "data"


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _pretty_json(value: object, *, allow_nan: bool = False) -> str:
    return (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=allow_nan,
        )
        + "\n"
    )


def _copy_package(tmp_path: Path) -> Path:
    return Path(shutil.copytree(CHECKED_PACKAGE, tmp_path / "package"))


def _refresh_manifest(package: Path, *, allow_nan: bool = False) -> None:
    pack_path = package / "scenario-pack.json"
    pack_bytes = pack_path.read_bytes()
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact"] = {
        "filename": "scenario-pack.json",
        "bytes": len(pack_bytes),
        "sha256": hashlib.sha256(pack_bytes).hexdigest(),
    }
    manifest.pop("manifest_content_sha256", None)
    manifest["manifest_content_sha256"] = hashlib.sha256(
        _canonical_json_bytes(manifest)
    ).hexdigest()
    manifest_path.write_text(
        _pretty_json(manifest, allow_nan=allow_nan),
        encoding="utf-8",
    )


def _nested_keys(value: object) -> list[str]:
    output: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            output.append(str(key).lower())
            output.extend(_nested_keys(nested))
    elif isinstance(value, list):
        for nested in value:
            output.extend(_nested_keys(nested))
    return output


@pytest.fixture(scope="module")
def checked_verification() -> Any:
    return verify_public_mvp_scenario_pack(CHECKED_PACKAGE, schema_path=SCHEMA)


@pytest.fixture(scope="module")
def reproduced_package(tmp_path_factory: pytest.TempPathFactory) -> Any:
    destination = tmp_path_factory.mktemp("public-mvp") / "reproduced"
    return build_public_mvp_scenario_pack(
        destination,
        schema_path=SCHEMA,
        root_seed=DEFAULT_ROOT_SEED,
        replications=DEFAULT_REPLICATIONS,
    )


def test_checked_in_package_has_exact_closed_artifacts_and_digests(
    checked_verification: Any,
) -> None:
    verified = checked_verification
    assert {item.name for item in CHECKED_PACKAGE.iterdir()} == PUBLIC_MVP_PACKAGE_FILES
    assert verified.scenario_count == 27
    assert verified.timeseries_point_count == 27 * 61
    assert (
        verified.pack_sha256 == "e2a817f05b7d31ed9581bc12bdaa0e6096efc7d04817922be6c16629e0605016"
    )
    assert (
        verified.manifest_content_sha256
        == "871fd4e240f49442a03f5af81befa3db122c74904fb19b7906dd4498e0f7d3d6"
    )


def test_checked_in_payload_satisfies_the_draft_2020_12_schema(
    checked_verification: Any,
) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(checked_verification.pack)
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        assert schema["properties"]["scenarios"]["minItems"] == 27
        assert schema["properties"]["scenarios"]["maxItems"] == 27
    else:
        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(schema).iter_errors(checked_verification.pack),
            key=lambda error: tuple(str(item) for item in error.absolute_path),
        )
        assert not errors, "\n".join(error.message for error in errors)


def test_pack_is_the_exact_deterministic_three_by_three_by_three_grid(
    checked_verification: Any,
) -> None:
    pack = checked_verification.pack
    design = cast(dict[str, Any], pack["design"])
    scenarios = cast(list[dict[str, Any]], pack["scenarios"])
    assert design["fleet_sizes"] == list(FLEET_SIZES)
    assert design["admission_profiles"] == [dict(item) for item in SCENARIO_PROFILES]
    assert design["capacity_cases"] == [dict(item) for item in CAPACITY_CASES]
    assert design["capacity_scaling"] == CAPACITY_SCALING
    assert design["replications_per_scenario"] == DEFAULT_REPLICATIONS
    assert design["root_seed"] == DEFAULT_ROOT_SEED
    assert design["paired_capacity_comparisons"] is True
    assert all(scenario["disturbance_fraction"] == 0.0 for scenario in scenarios)
    cells = Counter(
        (scenario["fleet_size"], scenario["profile"], scenario["capacity_case"])
        for scenario in scenarios
    )
    assert len(cells) == 27
    assert set(cells.values()) == {1}
    identifiers = [scenario["id"] for scenario in scenarios]
    assert identifiers == sorted(identifiers)
    assert "n00100-linear-capacity-baseline" in identifiers
    assert "n10000-step-capacity-expanded" in identifiers


def test_replication_specific_limitation_cannot_overstate_a_development_pack() -> None:
    assert scenario_pack_module._pack_limitations(2)[-1].startswith("The 2 fixed-seed replications")


def test_pack_separates_ex_ante_pressure_outcomes_and_representative_traces(
    checked_verification: Any,
) -> None:
    pack = checked_verification.pack
    definitions = cast(dict[str, Any], pack["definitions"])
    assert definitions["ex_ante_pressure"]["computed_before_stochastic_simulation"] is True
    assert definitions["operational_outcomes"]["definition_uses_ex_ante_pressure"] is False
    assert definitions["operational_outcomes"]["not_claimed_statistically_independent"] is True
    assert definitions["timeseries"]["representative_replication"] == 0
    for scenario in cast(list[dict[str, Any]], pack["scenarios"]):
        pressure = scenario["ex_ante_pressure"]
        outcomes = scenario["operational_outcomes"]
        trace = scenario["timeseries"]
        assert pressure["not_an_operational_outcome"] is True
        assert pressure["boundary_crossed"] is (pressure["value"] >= pressure["boundary"])
        if pressure["value"] == 0.0:
            assert pressure["binding_resource"] == NO_BINDING_RESOURCE
        else:
            assert pressure["binding_resource"] != NO_BINDING_RESOURCE
        assert outcomes["definition_uses_ex_ante_pressure"] is False
        assert all(
            math.isfinite(float(value))
            for value in outcomes.values()
            if not isinstance(value, bool)
        )
        assert 2 <= len(trace) <= 61
        times = [point["time_s"] for point in trace]
        assert times == sorted(set(times))
        assert times[0] == 0.0
        assert times[-1] == 300.0


def test_public_payload_contains_no_host_paths_secrets_or_hidden_replication_seeds(
    checked_verification: Any,
) -> None:
    pack = checked_verification.pack
    serialized = json.dumps(pack, sort_keys=True)
    for marker in (
        "/Users/",
        "/home/",
        "C:\\Users\\",
        "file://",
        "ghp_",
        "github_pat_",
        "sk-",
    ):
        assert marker not in serialized
    forbidden_key_fragments = {
        "absolute_path",
        "api_key",
        "credential",
        "directory",
        "password",
        "private_key",
        "secret",
        "token",
    }
    assert not any(
        fragment in key for key in _nested_keys(pack) for fragment in forbidden_key_fragments
    )
    for scenario in cast(list[dict[str, Any]], pack["scenarios"]):
        assert "seed" not in scenario
        assert all("seed" not in point for point in scenario["timeseries"])


def test_default_generation_reproduces_checked_in_bytes_and_refuses_overwrite(
    reproduced_package: Any,
) -> None:
    assert (
        reproduced_package.pack_path.read_bytes()
        == (CHECKED_PACKAGE / "scenario-pack.json").read_bytes()
    )
    assert (
        reproduced_package.manifest_path.read_bytes()
        == (CHECKED_PACKAGE / "manifest.json").read_bytes()
    )
    with pytest.raises(FileExistsError, match="overwrite"):
        build_public_mvp_scenario_pack(
            reproduced_package.output_dir,
            schema_path=SCHEMA,
        )


def test_builder_refuses_even_an_existing_empty_destination(tmp_path: Path) -> None:
    destination = tmp_path / "existing"
    destination.mkdir()
    with pytest.raises(FileExistsError, match="overwrite"):
        build_public_mvp_scenario_pack(destination, schema_path=SCHEMA)


def test_verifier_detects_pack_byte_tampering_before_semantic_use(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    with (package / "scenario-pack.json").open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="integrity"):
        verify_public_mvp_scenario_pack(package, schema_path=SCHEMA)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("external_validation", True, "external validation"),
        ("operational_use_authorized", True, "operational authorization"),
    ],
)
def test_rehashed_manifest_cannot_forge_authority_claims(
    tmp_path: Path,
    field: str,
    value: bool,
    message: str,
) -> None:
    package = _copy_package(tmp_path)
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[field] = value
    manifest.pop("manifest_content_sha256")
    manifest["manifest_content_sha256"] = hashlib.sha256(
        _canonical_json_bytes(manifest)
    ).hexdigest()
    manifest_path.write_text(_pretty_json(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        verify_public_mvp_scenario_pack(package, schema_path=SCHEMA)


def test_rehashed_semantic_tampering_cannot_reorder_scenario_rows(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    pack_path = package / "scenario-pack.json"
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    pack["scenarios"] = list(reversed(pack["scenarios"]))
    pack_path.write_text(_pretty_json(pack), encoding="utf-8")
    _refresh_manifest(package)
    with pytest.raises(ValueError, match="deterministic identity order"):
        verify_public_mvp_scenario_pack(package, schema_path=SCHEMA)


def test_nonfinite_json_is_rejected_even_after_digest_refresh(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    pack_path = package / "scenario-pack.json"
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    pack["scenarios"][0]["ex_ante_pressure"]["value"] = float("nan")
    pack_path.write_text(_pretty_json(pack, allow_nan=True), encoding="utf-8")
    _refresh_manifest(package)
    with pytest.raises(ValueError, match="nonfinite JSON number"):
        verify_public_mvp_scenario_pack(package, schema_path=SCHEMA)


def test_duplicate_json_keys_are_rejected_before_manifest_use(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    manifest_path = package / "manifest.json"
    original = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text('{"schema_version":"1.0",' + original[1:], encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        verify_public_mvp_scenario_pack(package, schema_path=SCHEMA)


def test_duplicate_pack_keys_are_rejected_after_physical_digest_verification(
    tmp_path: Path,
) -> None:
    package = _copy_package(tmp_path)
    pack_path = package / "scenario-pack.json"
    original = pack_path.read_text(encoding="utf-8")
    pack_path.write_text('{"schema_version":"1.0",' + original[1:], encoding="utf-8")
    _refresh_manifest(package)
    with pytest.raises(ValueError, match="duplicate JSON key"):
        verify_public_mvp_scenario_pack(package, schema_path=SCHEMA)


def test_bounded_manifest_read_rejects_oversized_input(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    (package / "manifest.json").write_bytes(b" " * 64_001)
    with pytest.raises(ValueError, match="64000-byte limit"):
        verify_public_mvp_scenario_pack(package, schema_path=SCHEMA)


def test_exact_package_closure_rejects_unexpected_directories(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    (package / "undeclared").mkdir()
    with pytest.raises(ValueError, match="exactly two"):
        verify_public_mvp_scenario_pack(package, schema_path=SCHEMA)


def test_schema_digest_is_physically_bound(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    schema_copy = tmp_path / "schema.json"
    schema_copy.write_bytes(SCHEMA.read_bytes() + b" ")
    with pytest.raises(ValueError, match="schema integrity"):
        verify_public_mvp_scenario_pack(package, schema_path=schema_copy)
