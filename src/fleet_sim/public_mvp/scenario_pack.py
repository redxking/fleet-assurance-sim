"""Build and verify the synthetic scenario pack used by the public MVP.

The pack is a deliberately small projection of the non-frozen Stage 3A
interface. It is browser-safe engineering evidence, not measured operational
evidence, external validation, a capacity recommendation, or deployment
authorization.
"""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from fleet_sim.control_plane.resource_network import (
    AdmissionPattern,
    OperationalFailureCriteria,
)
from fleet_sim.experiments.stage3a import Stage3AScenario, run_stage3a

SCHEMA_VERSION: Final = "1.0"
PACK_ID: Final = "fleet-public-mvp-synthetic-v1"
PACK_FILENAME: Final = "scenario-pack.json"
MANIFEST_FILENAME: Final = "manifest.json"
PUBLIC_MVP_PACKAGE_FILES: Final = frozenset({PACK_FILENAME, MANIFEST_FILENAME})
SCHEMA_ID: Final = (
    "https://redxking.github.io/fleet-assurance-sim/schemas/public_mvp_scenario_pack.schema.json"
)
DEFAULT_ROOT_SEED: Final = 20260820
DEFAULT_REPLICATIONS: Final = 16
MAXIMUM_TIMESERIES_POINTS: Final = 61
MAXIMUM_PACK_BYTES: Final = 2_000_000
MAXIMUM_MANIFEST_BYTES: Final = 64_000
MAXIMUM_SCHEMA_BYTES: Final = 256_000
FLEET_SIZES: Final = (100, 1_000, 10_000)
ADMISSION_DURATION_S: Final = 180.0
RECOVERY_WINDOW_S: Final = 120.0
TIME_STEP_S: Final = 1.0
DISTURBANCE_FRACTION: Final = 0.0
CAPACITY_SCALING: Final = "proportional_to_target_fleet_size"
NO_BINDING_RESOURCE: Final = "none_all_projected_pressures_zero"
PACK_TITLE: Final = "Fleet assurance synthetic scenario explorer"
PACK_LIMITATIONS: Final = (
    "All values are generated from notional synthetic engineering fixtures.",
    "The pack is not observed operational evidence or external validation.",
    "The scenarios do not authorize deployment or provide fleet-sizing advice.",
    "Comparisons are model behavior under declared assumptions, not field predictions.",
    (
        "Each resource capacity is recomputed from target fleet size before the "
        "capacity-case multiplier is applied; cross-fleet comparisons use proportional "
        "provisioning rather than fixed capacity."
    ),
    "No disturbance profile is applied to the linear, immediate, or bursty admission cases.",
)

SCENARIO_PROFILES: Final = (
    {
        "id": AdmissionPattern.LINEAR.value,
        "label": "Gradual admission",
        "description": "Admissions are distributed across the planned admission window.",
    },
    {
        "id": AdmissionPattern.STEP.value,
        "label": "Immediate admission",
        "description": "The planned population change is requested at the start of the window.",
    },
    {
        "id": AdmissionPattern.BURSTY.value,
        "label": "Bursty admission",
        "description": "Admissions arrive in deterministic bursts within the planned window.",
    },
)

CAPACITY_CASES: Final = (
    {
        "id": "constrained",
        "label": "Constrained capacity",
        "multiplier": 0.8,
        "description": (
            "Notional resource capacity is 80 percent of the proportionally provisioned "
            "baseline fixture for the target fleet size."
        ),
    },
    {
        "id": "baseline",
        "label": "Baseline capacity",
        "multiplier": 1.0,
        "description": (
            "Notional resource capacity uses the proportionally provisioned baseline "
            "engineering fixture for the target fleet size."
        ),
    },
    {
        "id": "expanded",
        "label": "Expanded capacity",
        "multiplier": 1.25,
        "description": (
            "Notional resource capacity is 125 percent of the proportionally provisioned "
            "baseline fixture for the target fleet size."
        ),
    },
)

_PROFILE_BY_ID: Final = {str(item["id"]): item for item in SCENARIO_PROFILES}
_CAPACITY_BY_ID_FOR_VALIDATION: Final = {str(item["id"]): item for item in CAPACITY_CASES}
_FORBIDDEN_KEY_PARTS: Final = (
    "absolute_path",
    "api_key",
    "credential",
    "directory",
    "password",
    "private_key",
    "secret",
    "token",
)


def _pack_limitations(replications: int) -> list[str]:
    return [
        *PACK_LIMITATIONS,
        (
            f"The {replications} fixed-seed replications provide descriptive sample "
            "summaries only; no confidence, credible, prediction, or transfer interval "
            "is claimed."
        ),
    ]


_FORBIDDEN_VALUE_MARKERS: Final = (
    "/Users/",
    "/home/",
    "C:\\Users\\",
    "file://",
    "ghp_",
    "github_pat_",
    "sk-",
)


@dataclass(frozen=True, slots=True)
class PublicMVPScenarioPackArtifacts:
    """Paths and integrity values for one newly written public pack."""

    output_dir: Path
    pack_path: Path
    manifest_path: Path
    pack_sha256: str
    manifest_sha256: str
    manifest_content_sha256: str
    scenario_count: int
    timeseries_point_count: int


@dataclass(frozen=True, slots=True)
class PublicMVPScenarioPackVerification:
    """Verified public package plus its parsed browser payload."""

    package_dir: Path
    pack_path: Path
    manifest_path: Path
    pack_sha256: str
    manifest_sha256: str
    manifest_content_sha256: str
    scenario_count: int
    timeseries_point_count: int
    pack: dict[str, Any]


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _pretty_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_bounded_bytes(path: Path, *, maximum_bytes: int, label: str) -> bytes:
    try:
        declared_size = path.stat().st_size
    except OSError as exc:
        raise ValueError(f"{label} cannot be inspected") from exc
    if declared_size > maximum_bytes:
        raise ValueError(f"{label} exceeds the {maximum_bytes}-byte limit")
    try:
        with path.open("rb") as stream:
            value = stream.read(maximum_bytes + 1)
    except OSError as exc:
        raise ValueError(f"{label} cannot be read") from exc
    if len(value) > maximum_bytes:
        raise ValueError(f"{label} exceeds the {maximum_bytes}-byte limit")
    return value


def _reject_nonstandard_number(token: str) -> object:
    raise ValueError(f"nonfinite JSON number {token!r} is not permitted")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key {key!r} is not permitted")
        output[key] = value
    return output


def _read_object_bytes(value: bytes, *, label: str) -> dict[str, Any]:
    try:
        decoded = value.decode("utf-8")
        parsed = json.loads(
            decoded,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_nonstandard_number,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be valid UTF-8 JSON") from exc
    if not isinstance(parsed, dict):
        raise TypeError(f"{label} must be a JSON object")
    return cast(dict[str, Any], parsed)


def _finite_float(value: object, *, name: str) -> float:
    number = float(cast(Any, value))
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    rounded = round(number, 8)
    return 0.0 if rounded == 0.0 else rounded


def _finite_tree(value: object, *, location: str = "$") -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"nonfinite number at {location}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _finite_tree(item, location=f"{location}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _finite_tree(item, location=f"{location}.{key}")
        return
    raise ValueError(f"unsupported JSON value at {location}")


def _assert_public_safe(value: object, *, location: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower()
            if any(marker in normalized for marker in _FORBIDDEN_KEY_PARTS):
                raise ValueError(f"non-public key at {location}.{key}")
            _assert_public_safe(item, location=f"{location}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_public_safe(item, location=f"{location}[{index}]")
        return
    if isinstance(value, str) and any(marker in value for marker in _FORBIDDEN_VALUE_MARKERS):
        raise ValueError(f"path or secret-like value at {location}")


def _scenario_id(fleet_size: int, profile: str, capacity_case: str) -> str:
    return f"n{fleet_size:05d}-{profile}-capacity-{capacity_case}"


def _stage3a_scenarios() -> tuple[Stage3AScenario, ...]:
    scenarios: list[Stage3AScenario] = []
    for fleet_size in FLEET_SIZES:
        initial_n = max(1, round(0.10 * fleet_size))
        for profile in SCENARIO_PROFILES:
            profile_id = str(profile["id"])
            for capacity in CAPACITY_CASES:
                capacity_id = str(capacity["id"])
                scenarios.append(
                    Stage3AScenario(
                        scenario_id=_scenario_id(fleet_size, profile_id, capacity_id),
                        pattern=AdmissionPattern(profile_id),
                        initial_n=initial_n,
                        final_n=fleet_size,
                        admission_duration_s=ADMISSION_DURATION_S,
                        recovery_window_s=RECOVERY_WINDOW_S,
                        dt_s=TIME_STEP_S,
                        disturbance_fraction=DISTURBANCE_FRACTION,
                        capacity_multiplier=float(cast(Any, capacity["multiplier"])),
                        partition="robustness",
                        architecture="centralized",
                        workload="public-synthetic-explorer",
                        shift_label=f"capacity-{capacity_id}",
                        randomization_pair_id=f"n{fleet_size:05d}-{profile_id}",
                    )
                )
    return tuple(sorted(scenarios, key=lambda scenario: scenario.scenario_id))


def _bounded_trace_indices(group: pd.DataFrame) -> list[int]:
    if len(group) <= MAXIMUM_TIMESERIES_POINTS:
        return list(range(len(group)))
    mandatory = {
        0,
        len(group) - 1,
        int(np.argmax(group["projected_maximum_omega"].to_numpy(dtype=float))),
        int(np.argmax(group["maximum_observed_omega"].to_numpy(dtype=float))),
        int(np.argmax(group["planned_admissions"].to_numpy(dtype=float))),
    }
    evenly_spaced = np.linspace(
        0,
        len(group) - 1,
        num=MAXIMUM_TIMESERIES_POINTS,
        dtype=int,
    )
    candidates = list(dict.fromkeys([*sorted(mandatory), *(int(item) for item in evenly_spaced)]))
    selected = set(mandatory)
    for index in candidates:
        if len(selected) >= MAXIMUM_TIMESERIES_POINTS:
            break
        selected.add(index)
    if len(selected) < MAXIMUM_TIMESERIES_POINTS:
        for index in range(len(group)):
            if len(selected) >= MAXIMUM_TIMESERIES_POINTS:
                break
            selected.add(index)
    return sorted(selected)


def _timeseries_rows(group: pd.DataFrame) -> list[dict[str, object]]:
    ordered = group.sort_values("time_s", kind="stable").reset_index(drop=True)
    if ordered["time_s"].duplicated().any():
        raise ValueError("representative timeseries contains duplicate timestamps")
    output: list[dict[str, object]] = []
    for index in _bounded_trace_indices(ordered):
        row = ordered.iloc[index]
        output.append(
            {
                "time_s": _finite_float(row["time_s"], name="time_s"),
                "planned_admissions": int(row["planned_admissions"]),
                "admitted_agents": int(row["admitted_agents"]),
                "pending_admissions": int(row["pending_admissions"]),
                "observed_fleet_size": int(row["fleet_size"]),
                "projected_fleet_size": int(row["projected_fleet_size"]),
                "projected_maximum_pressure": _finite_float(
                    row["projected_maximum_omega"],
                    name="projected_maximum_pressure",
                ),
                "observed_maximum_pressure": _finite_float(
                    row["maximum_observed_omega"],
                    name="observed_maximum_pressure",
                ),
            }
        )
    return output


def _scenario_payload(summary: pd.Series, trace: pd.DataFrame) -> dict[str, object]:
    scenario_id = str(summary["scenario_id"])
    profile_id = str(summary["pattern"])
    capacity_multiplier = _finite_float(summary["capacity_multiplier"], name="capacity_multiplier")
    capacity_matches = [
        item
        for item in CAPACITY_CASES
        if math.isclose(float(cast(Any, item["multiplier"])), capacity_multiplier, abs_tol=1e-12)
    ]
    if len(capacity_matches) != 1:
        raise ValueError(f"unknown capacity case for {scenario_id}")
    capacity = capacity_matches[0]
    profile = _PROFILE_BY_ID.get(profile_id)
    if profile is None:
        raise ValueError(f"unknown admission profile for {scenario_id}")
    expected_id = _scenario_id(int(summary["final_n"]), profile_id, str(capacity["id"]))
    if scenario_id != expected_id:
        raise ValueError("Stage 3A scenario identity drifted from the public design")
    pressure = _finite_float(summary["omega_a"], name="omega_a")
    binding_resource = NO_BINDING_RESOURCE if pressure == 0.0 else str(summary["binding_resource"])
    return {
        "id": scenario_id,
        "name": (f"{int(summary['final_n']):,} agents | {profile['label']} | {capacity['label']}"),
        "fleet_size": int(summary["final_n"]),
        "initial_fleet_size": int(summary["initial_n"]),
        "profile": profile_id,
        "profile_label": str(profile["label"]),
        "capacity_case": str(capacity["id"]),
        "capacity_label": str(capacity["label"]),
        "capacity_multiplier": capacity_multiplier,
        "architecture": "centralized",
        "disturbance_fraction": _finite_float(
            summary["disturbance_fraction"], name="disturbance_fraction"
        ),
        "replications": int(summary["replications"]),
        "ex_ante_pressure": {
            "metric": "omega_a",
            "value": pressure,
            "boundary": 1.0,
            "boundary_crossed": pressure >= 1.0,
            "binding_resource": binding_resource,
            "peak_admission_rate_agents_per_s": _finite_float(
                summary["peak_dndt"], name="peak_admission_rate_agents_per_s"
            ),
            "not_an_operational_outcome": True,
        },
        "operational_outcomes": {
            "failure_rate": _finite_float(
                summary["operational_failure_rate"], name="operational_failure_rate"
            ),
            "mean_deadline_miss_fraction": _finite_float(
                summary["mean_deadline_miss_fraction"], name="mean_deadline_miss_fraction"
            ),
            "mean_shed_fraction": _finite_float(
                summary["mean_shed_fraction"], name="mean_shed_fraction"
            ),
            "mean_useful_task_throughput_ratio": _finite_float(
                summary["mean_useful_task_throughput_ratio"],
                name="mean_useful_task_throughput_ratio",
            ),
            "mean_incomplete_exposure_per_agent_s": _finite_float(
                summary["mean_incomplete_exposure_per_agent_s"],
                name="mean_incomplete_exposure_per_agent_s",
            ),
            "definition_uses_ex_ante_pressure": False,
        },
        "timeseries": _timeseries_rows(trace),
    }


def _definitions_payload() -> dict[str, object]:
    criteria = OperationalFailureCriteria()
    return {
        "ex_ante_pressure": {
            "metric": "omega_a",
            "symbol": "Omega_A",
            "boundary": 1.0,
            "computed_before_stochastic_simulation": True,
            "description": (
                "A dimensionless projected admission-pressure indicator. It is an "
                "ex-ante engineering predictor, not an operational outcome."
            ),
        },
        "operational_outcomes": {
            "definition_uses_ex_ante_pressure": False,
            "not_claimed_statistically_independent": True,
            "description": (
                "Stochastic simulation outcomes use separately defined service, queue, "
                "shedding, exposure, throughput, and recovery criteria."
            ),
            "failure_criteria": {
                "maximum_deadline_miss_fraction": criteria.maximum_deadline_miss_fraction,
                "maximum_shed_fraction": criteria.maximum_shed_fraction,
                "maximum_incomplete_exposure_per_agent_s": (
                    criteria.maximum_incomplete_exposure_per_agent_s
                ),
                "minimum_useful_throughput_ratio": criteria.minimum_useful_throughput_ratio,
                "require_recovery": criteria.require_recovery,
            },
        },
        "timeseries": {
            "representative_replication": 0,
            "maximum_points_per_scenario": MAXIMUM_TIMESERIES_POINTS,
            "selection": "endpoints_peaks_and_even_interval_sampling",
            "description": (
                "A bounded representative replication for visual exploration; aggregate "
                "outcomes remain based on every declared replication."
            ),
        },
    }


def _pack_payload(
    scenario_results: pd.DataFrame,
    admission_trace: pd.DataFrame,
    *,
    root_seed: int,
    replications: int,
) -> dict[str, object]:
    expected_ids = [scenario.scenario_id for scenario in _stage3a_scenarios()]
    actual_ids = sorted(str(item) for item in scenario_results["scenario_id"].tolist())
    if actual_ids != expected_ids:
        raise ValueError("Stage 3A results do not match the frozen public scenario grid")
    if admission_trace["seed"].isna().any():
        raise ValueError("representative Stage 3A trace is missing its internal seed")
    trace_replications = {int(item) for item in admission_trace["replication"].unique()}
    if trace_replications != {0}:
        raise ValueError("public trace must contain representative replication zero only")
    experiment_ids = {str(item) for item in scenario_results["experiment_id"]}
    if len(experiment_ids) != 1:
        raise ValueError("public scenario results must come from one Stage 3A execution")
    scenarios: list[dict[str, object]] = []
    indexed = scenario_results.set_index("scenario_id", drop=False)
    for scenario_id in expected_ids:
        trace = admission_trace.loc[admission_trace["scenario_id"] == scenario_id]
        if trace.empty:
            raise ValueError(f"representative trace missing for {scenario_id}")
        scenarios.append(_scenario_payload(indexed.loc[scenario_id], trace))

    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "pack_id": PACK_ID,
        "title": PACK_TITLE,
        "generated_from": {
            "engine": "fleet_sim.experiments.stage3a",
            "interface": "run_stage3a",
            "package_version": "0.2.0",
            "experiment_id": next(iter(experiment_ids)),
        },
        "synthetic_only": True,
        "external_validation": False,
        "operational_use_authorized": False,
        "design": {
            "root_seed": int(root_seed),
            "replications_per_scenario": int(replications),
            "fleet_sizes": list(FLEET_SIZES),
            "admission_duration_s": ADMISSION_DURATION_S,
            "recovery_window_s": RECOVERY_WINDOW_S,
            "time_step_s": TIME_STEP_S,
            "admission_profiles": [dict(item) for item in SCENARIO_PROFILES],
            "capacity_cases": [dict(item) for item in CAPACITY_CASES],
            "capacity_scaling": CAPACITY_SCALING,
            "scenario_count": len(scenarios),
            "timeseries_max_points_per_scenario": MAXIMUM_TIMESERIES_POINTS,
            "paired_capacity_comparisons": True,
        },
        "definitions": _definitions_payload(),
        "limitations": _pack_limitations(replications),
        "scenarios": scenarios,
    }
    _finite_tree(payload)
    _assert_public_safe(payload)
    _validate_pack(payload, expected_replications=replications)
    return payload


def _required_keys(value: Mapping[str, object], expected: set[str], *, label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"{label} keys mismatch; missing={missing}, extra={extra}")


def _validate_pack(pack: Mapping[str, object], *, expected_replications: int | None = None) -> None:
    _required_keys(
        pack,
        {
            "schema_version",
            "pack_id",
            "title",
            "generated_from",
            "synthetic_only",
            "external_validation",
            "operational_use_authorized",
            "design",
            "definitions",
            "limitations",
            "scenarios",
        },
        label="scenario pack",
    )
    if pack["schema_version"] != SCHEMA_VERSION or pack["pack_id"] != PACK_ID:
        raise ValueError("unsupported public scenario pack identity")
    if pack["title"] != PACK_TITLE:
        raise ValueError("public scenario pack title drift")
    if pack["synthetic_only"] is not True:
        raise ValueError("public scenario pack must remain synthetic-only")
    if pack["external_validation"] is not False:
        raise ValueError("public scenario pack cannot claim external validation")
    if pack["operational_use_authorized"] is not False:
        raise ValueError("public scenario pack cannot claim operational authorization")
    design = pack["design"]
    scenarios = pack["scenarios"]
    definitions = pack["definitions"]
    generated_from = pack["generated_from"]
    limitations = pack["limitations"]
    if not isinstance(design, dict) or not isinstance(scenarios, list):
        raise TypeError("public scenario design and scenarios have invalid types")
    if not isinstance(definitions, dict):
        raise TypeError("public scenario definitions have invalid type")
    if not isinstance(generated_from, dict) or not isinstance(limitations, list):
        raise TypeError("public scenario provenance and limitations have invalid types")
    _required_keys(
        generated_from,
        {"engine", "interface", "package_version", "experiment_id"},
        label="generated_from",
    )
    if generated_from.get("engine") != "fleet_sim.experiments.stage3a":
        raise ValueError("public scenario engine identity drift")
    if generated_from.get("interface") != "run_stage3a":
        raise ValueError("public scenario interface identity drift")
    if generated_from.get("package_version") != "0.2.0":
        raise ValueError("public scenario package-version drift")
    experiment_id = generated_from.get("experiment_id")
    if (
        not isinstance(experiment_id, str)
        or not experiment_id.startswith("stage3a-")
        or len(experiment_id) != 24
        or any(character not in "0123456789abcdef" for character in experiment_id[8:])
    ):
        raise ValueError("public scenario experiment identifier is invalid")
    _required_keys(
        design,
        {
            "root_seed",
            "replications_per_scenario",
            "fleet_sizes",
            "admission_duration_s",
            "recovery_window_s",
            "time_step_s",
            "admission_profiles",
            "capacity_cases",
            "capacity_scaling",
            "scenario_count",
            "timeseries_max_points_per_scenario",
            "paired_capacity_comparisons",
        },
        label="scenario design",
    )
    if design.get("fleet_sizes") != list(FLEET_SIZES):
        raise ValueError("public fleet-size design drift")
    if design.get("admission_profiles") != [dict(item) for item in SCENARIO_PROFILES]:
        raise ValueError("public admission-profile design drift")
    if design.get("capacity_cases") != [dict(item) for item in CAPACITY_CASES]:
        raise ValueError("public capacity-case design drift")
    if design.get("capacity_scaling") != CAPACITY_SCALING:
        raise ValueError("public capacity-scaling design drift")
    if design.get("admission_duration_s") != ADMISSION_DURATION_S:
        raise ValueError("public admission-duration design drift")
    if design.get("recovery_window_s") != RECOVERY_WINDOW_S:
        raise ValueError("public recovery-window design drift")
    if design.get("time_step_s") != TIME_STEP_S:
        raise ValueError("public time-step design drift")
    if design.get("timeseries_max_points_per_scenario") != MAXIMUM_TIMESERIES_POINTS:
        raise ValueError("public timeseries design drift")
    if isinstance(design.get("root_seed"), bool) or not isinstance(design.get("root_seed"), int):
        raise TypeError("public root seed must be an integer")
    if int(design["root_seed"]) < 0:
        raise ValueError("public root seed cannot be negative")
    if definitions != _definitions_payload():
        raise ValueError("public scenario evidence definitions drift")
    ex_ante_definition = definitions.get("ex_ante_pressure")
    outcome_definition = definitions.get("operational_outcomes")
    timeseries_definition = definitions.get("timeseries")
    if not all(
        isinstance(item, dict)
        for item in (ex_ante_definition, outcome_definition, timeseries_definition)
    ):
        raise TypeError("scenario evidence definitions must be objects")
    ex_ante_definition = cast(dict[str, object], ex_ante_definition)
    outcome_definition = cast(dict[str, object], outcome_definition)
    timeseries_definition = cast(dict[str, object], timeseries_definition)
    if (
        ex_ante_definition.get("metric") != "omega_a"
        or ex_ante_definition.get("boundary") != 1.0
        or ex_ante_definition.get("computed_before_stochastic_simulation") is not True
    ):
        raise ValueError("ex-ante pressure definition drift")
    if outcome_definition.get("definition_uses_ex_ante_pressure") is not False:
        raise ValueError("operational outcome definition is not separated")
    if outcome_definition.get("not_claimed_statistically_independent") is not True:
        raise ValueError("operational outcome independence limitation is missing")
    if design.get("scenario_count") != len(_stage3a_scenarios()):
        raise ValueError("public scenario-count design drift")
    if len(scenarios) != int(design["scenario_count"]):
        raise ValueError("scenario payload count does not match the design")
    if design.get("paired_capacity_comparisons") is not True:
        raise ValueError("capacity comparisons must retain paired randomization")
    replications = int(design.get("replications_per_scenario", 0))
    if replications < 1 or (
        expected_replications is not None and replications != expected_replications
    ):
        raise ValueError("replication count is invalid")
    expected_ids = [scenario.scenario_id for scenario in _stage3a_scenarios()]
    expected_by_id = {scenario.scenario_id: scenario for scenario in _stage3a_scenarios()}
    actual_ids: list[str] = []
    total_points = 0
    for index, scenario_value in enumerate(scenarios):
        if not isinstance(scenario_value, dict):
            raise TypeError(f"scenario {index} must be an object")
        scenario = cast(dict[str, object], scenario_value)
        scenario_id = str(scenario.get("id", ""))
        actual_ids.append(scenario_id)
        _required_keys(
            scenario,
            {
                "id",
                "name",
                "fleet_size",
                "initial_fleet_size",
                "profile",
                "profile_label",
                "capacity_case",
                "capacity_label",
                "capacity_multiplier",
                "architecture",
                "disturbance_fraction",
                "replications",
                "ex_ante_pressure",
                "operational_outcomes",
                "timeseries",
            },
            label=f"scenario {scenario_id}",
        )
        expected_scenario = expected_by_id.get(scenario_id)
        if expected_scenario is None:
            raise ValueError(f"scenario {scenario_id} is outside the public grid")
        capacity_id = scenario_id.rsplit("-", 1)[-1]
        capacity = _CAPACITY_BY_ID_FOR_VALIDATION[capacity_id]
        profile = _PROFILE_BY_ID[expected_scenario.pattern.value]
        expected_identity = {
            "name": (
                f"{expected_scenario.final_n:,} agents | {profile['label']} | {capacity['label']}"
            ),
            "fleet_size": expected_scenario.final_n,
            "initial_fleet_size": expected_scenario.initial_n,
            "profile": expected_scenario.pattern.value,
            "profile_label": profile["label"],
            "capacity_case": capacity_id,
            "capacity_label": capacity["label"],
            "capacity_multiplier": capacity["multiplier"],
            "architecture": "centralized",
            "disturbance_fraction": DISTURBANCE_FRACTION,
        }
        for field, expected_value in expected_identity.items():
            if scenario.get(field) != expected_value:
                raise ValueError(f"scenario {scenario_id} {field} drift")
        if scenario.get("replications") != replications:
            raise ValueError(f"scenario {scenario_id} replication count drift")
        pressure = scenario.get("ex_ante_pressure")
        outcomes = scenario.get("operational_outcomes")
        trace = scenario.get("timeseries")
        if not isinstance(pressure, dict) or not isinstance(outcomes, dict):
            raise TypeError(f"scenario {scenario_id} evidence layers are invalid")
        _required_keys(
            pressure,
            {
                "metric",
                "value",
                "boundary",
                "boundary_crossed",
                "binding_resource",
                "peak_admission_rate_agents_per_s",
                "not_an_operational_outcome",
            },
            label=f"scenario {scenario_id} ex-ante pressure",
        )
        _required_keys(
            outcomes,
            {
                "failure_rate",
                "mean_deadline_miss_fraction",
                "mean_shed_fraction",
                "mean_useful_task_throughput_ratio",
                "mean_incomplete_exposure_per_agent_s",
                "definition_uses_ex_ante_pressure",
            },
            label=f"scenario {scenario_id} operational outcomes",
        )
        if pressure.get("metric") != "omega_a" or pressure.get("boundary") != 1.0:
            raise ValueError(f"scenario {scenario_id} pressure definition drift")
        if pressure.get("not_an_operational_outcome") is not True:
            raise ValueError(f"scenario {scenario_id} pressure/outcome boundary is missing")
        pressure_value = float(cast(Any, pressure.get("value")))
        if pressure_value < 0.0 or pressure.get("boundary_crossed") is not (pressure_value >= 1.0):
            raise ValueError(f"scenario {scenario_id} pressure boundary result drift")
        if (
            not isinstance(pressure.get("binding_resource"), str)
            or not str(pressure["binding_resource"]).strip()
        ):
            raise ValueError(f"scenario {scenario_id} binding resource is invalid")
        if pressure_value == 0.0 and pressure.get("binding_resource") != NO_BINDING_RESOURCE:
            raise ValueError(f"scenario {scenario_id} zero-pressure binding resource drift")
        if pressure_value > 0.0 and pressure.get("binding_resource") == NO_BINDING_RESOURCE:
            raise ValueError(f"scenario {scenario_id} positive-pressure binding resource drift")
        if outcomes.get("definition_uses_ex_ante_pressure") is not False:
            raise ValueError(f"scenario {scenario_id} outcome definition is not separated")
        for field in (
            "failure_rate",
            "mean_deadline_miss_fraction",
            "mean_shed_fraction",
            "mean_useful_task_throughput_ratio",
        ):
            value = float(cast(Any, outcomes.get(field)))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"scenario {scenario_id} {field} is outside [0, 1]")
        if float(cast(Any, outcomes.get("mean_incomplete_exposure_per_agent_s"))) < 0.0:
            raise ValueError(f"scenario {scenario_id} incomplete exposure is negative")
        if not isinstance(trace, list) or not trace or len(trace) > MAXIMUM_TIMESERIES_POINTS:
            raise ValueError(f"scenario {scenario_id} timeseries is not properly bounded")
        for point_index, point_value in enumerate(trace):
            if not isinstance(point_value, dict):
                raise TypeError(f"scenario {scenario_id} timeseries point must be an object")
            _required_keys(
                point_value,
                {
                    "time_s",
                    "planned_admissions",
                    "admitted_agents",
                    "pending_admissions",
                    "observed_fleet_size",
                    "projected_fleet_size",
                    "projected_maximum_pressure",
                    "observed_maximum_pressure",
                },
                label=f"scenario {scenario_id} timeseries point {point_index}",
            )
            for field in (
                "planned_admissions",
                "admitted_agents",
                "pending_admissions",
                "observed_fleet_size",
                "projected_fleet_size",
            ):
                value = point_value[field]
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(
                        f"scenario {scenario_id} timeseries {field} must be nonnegative integer"
                    )
            for field in (
                "time_s",
                "projected_maximum_pressure",
                "observed_maximum_pressure",
            ):
                if float(cast(Any, point_value[field])) < 0.0:
                    raise ValueError(
                        f"scenario {scenario_id} timeseries {field} cannot be negative"
                    )
        times = [float(cast(Any, cast(dict[str, object], item)["time_s"])) for item in trace]
        if times != sorted(set(times)):
            raise ValueError(f"scenario {scenario_id} timeseries order is invalid")
        if times[0] != 0.0 or times[-1] != ADMISSION_DURATION_S + RECOVERY_WINDOW_S:
            raise ValueError(f"scenario {scenario_id} timeseries endpoints are invalid")
        total_points += len(trace)
    if actual_ids != expected_ids:
        raise ValueError("public scenario rows are not in deterministic identity order")
    if timeseries_definition.get("maximum_points_per_scenario") != MAXIMUM_TIMESERIES_POINTS:
        raise ValueError("timeseries bound drift")
    if total_points < len(scenarios):
        raise ValueError("timeseries point count is invalid")
    if limitations != _pack_limitations(replications):
        raise ValueError("public scenario limitations drift")
    _finite_tree(pack)
    _assert_public_safe(pack)


def _manifest_without_integrity(manifest: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in manifest.items() if key != "manifest_content_sha256"}


def _manifest_payload(
    *,
    pack_bytes: bytes,
    schema_bytes: bytes,
    root_seed: int,
    replications: int,
    scenario_count: int,
    timeseries_point_count: int,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": f"{PACK_ID}-manifest",
        "pack_id": PACK_ID,
        "artifact": {
            "filename": PACK_FILENAME,
            "bytes": len(pack_bytes),
            "sha256": _sha256_bytes(pack_bytes),
        },
        "schema": {
            "id": SCHEMA_ID,
            "bytes": len(schema_bytes),
            "sha256": _sha256_bytes(schema_bytes),
        },
        "scenario_count": scenario_count,
        "timeseries_point_count": timeseries_point_count,
        "root_seed": root_seed,
        "replications_per_scenario": replications,
        "synthetic_only": True,
        "external_validation": False,
        "operational_use_authorized": False,
        "generator_name": "build_public_mvp_scenarios",
    }
    payload["manifest_content_sha256"] = _sha256_bytes(_canonical_json_bytes(payload))
    return payload


def _validate_manifest(manifest: Mapping[str, object]) -> None:
    _required_keys(
        manifest,
        {
            "schema_version",
            "manifest_id",
            "pack_id",
            "artifact",
            "schema",
            "scenario_count",
            "timeseries_point_count",
            "root_seed",
            "replications_per_scenario",
            "synthetic_only",
            "external_validation",
            "operational_use_authorized",
            "generator_name",
            "manifest_content_sha256",
        },
        label="public scenario manifest",
    )
    if manifest["schema_version"] != SCHEMA_VERSION or manifest["pack_id"] != PACK_ID:
        raise ValueError("unsupported public scenario manifest identity")
    if manifest["manifest_id"] != f"{PACK_ID}-manifest":
        raise ValueError("public scenario manifest identifier drift")
    if manifest["synthetic_only"] is not True:
        raise ValueError("public scenario manifest must remain synthetic-only")
    if manifest["external_validation"] is not False:
        raise ValueError("public scenario manifest cannot claim external validation")
    if manifest["operational_use_authorized"] is not False:
        raise ValueError("public scenario manifest cannot claim operational authorization")
    expected = _sha256_bytes(_canonical_json_bytes(_manifest_without_integrity(manifest)))
    if manifest["manifest_content_sha256"] != expected:
        raise ValueError("public scenario manifest self-integrity mismatch")
    artifact = manifest["artifact"]
    schema = manifest["schema"]
    if not isinstance(artifact, dict) or not isinstance(schema, dict):
        raise TypeError("public scenario manifest bindings must be objects")
    if set(artifact) != {"filename", "bytes", "sha256"}:
        raise ValueError("public scenario artifact binding keys mismatch")
    if artifact.get("filename") != PACK_FILENAME:
        raise ValueError("public scenario artifact filename mismatch")
    if set(schema) != {"id", "bytes", "sha256"} or schema.get("id") != SCHEMA_ID:
        raise ValueError("public scenario schema binding mismatch")
    for value, label in (
        (artifact.get("sha256"), "artifact SHA-256"),
        (schema.get("sha256"), "schema SHA-256"),
        (manifest.get("manifest_content_sha256"), "manifest SHA-256"),
    ):
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError(f"{label} must be a lowercase hexadecimal digest")
        if any(character not in "0123456789abcdef" for character in value):
            raise ValueError(f"{label} must be a lowercase hexadecimal digest")
    _finite_tree(manifest)
    _assert_public_safe(manifest)


def build_public_mvp_scenario_pack(
    output_dir: str | Path,
    *,
    schema_path: str | Path,
    root_seed: int = DEFAULT_ROOT_SEED,
    replications: int = DEFAULT_REPLICATIONS,
) -> PublicMVPScenarioPackArtifacts:
    """Build a new deterministic browser package and refuse all overwrites."""
    if isinstance(root_seed, bool) or not isinstance(root_seed, int) or root_seed < 0:
        raise ValueError("root_seed must be a nonnegative integer")
    if isinstance(replications, bool) or not isinstance(replications, int) or replications < 1:
        raise ValueError("replications must be a positive integer")
    destination = Path(output_dir)
    pack_path = destination / PACK_FILENAME
    manifest_path = destination / MANIFEST_FILENAME
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"refusing to overwrite public MVP package in {destination}")
    schema = Path(schema_path)
    if not schema.is_file() or schema.is_symlink():
        raise ValueError("public MVP scenario schema must be a regular file")
    schema_bytes = _read_bounded_bytes(
        schema,
        maximum_bytes=MAXIMUM_SCHEMA_BYTES,
        label="public MVP scenario schema",
    )
    schema_payload = _read_object_bytes(schema_bytes, label="public MVP scenario schema")
    if schema_payload.get("$id") != SCHEMA_ID:
        raise ValueError("public MVP scenario schema identifier mismatch")

    scenarios = _stage3a_scenarios()
    with tempfile.TemporaryDirectory(prefix="fleet-public-mvp-") as temporary:
        artifacts = run_stage3a(
            scenarios,
            Path(temporary) / "stage3a",
            root_seed=root_seed,
            replications=replications,
            trace_replications_per_scenario=1,
            maximum_trace_rows=100_000,
        )
        if artifacts.admission_trace_path is None:
            raise RuntimeError("Stage 3A did not produce the required representative trace")
        scenario_results = pd.read_parquet(artifacts.scenario_results_path)
        admission_trace = pd.read_parquet(artifacts.admission_trace_path)
        pack = _pack_payload(
            scenario_results,
            admission_trace,
            root_seed=root_seed,
            replications=replications,
        )

    pack_bytes = _pretty_json_bytes(pack)
    scenario_values = cast(list[dict[str, object]], pack["scenarios"])
    timeseries_point_count = sum(
        len(cast(list[object], scenario["timeseries"])) for scenario in scenario_values
    )
    manifest = _manifest_payload(
        pack_bytes=pack_bytes,
        schema_bytes=schema_bytes,
        root_seed=root_seed,
        replications=replications,
        scenario_count=len(scenario_values),
        timeseries_point_count=timeseries_point_count,
    )
    _validate_manifest(manifest)
    manifest_bytes = _pretty_json_bytes(manifest)

    destination.mkdir(parents=True, exist_ok=False)
    try:
        with pack_path.open("xb") as stream:
            stream.write(pack_bytes)
        with manifest_path.open("xb") as stream:
            stream.write(manifest_bytes)
        verify_public_mvp_scenario_pack(
            destination,
            schema_path=schema,
            expected_pack_sha256=_sha256_bytes(pack_bytes),
            expected_manifest_sha256=_sha256_bytes(manifest_bytes),
        )
    except Exception:
        pack_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        destination.rmdir()
        raise

    return PublicMVPScenarioPackArtifacts(
        output_dir=destination,
        pack_path=pack_path,
        manifest_path=manifest_path,
        pack_sha256=_sha256_bytes(pack_bytes),
        manifest_sha256=_sha256_bytes(manifest_bytes),
        manifest_content_sha256=str(manifest["manifest_content_sha256"]),
        scenario_count=len(scenario_values),
        timeseries_point_count=timeseries_point_count,
    )


def verify_public_mvp_scenario_pack(
    package_dir: str | Path,
    *,
    schema_path: str | Path,
    expected_pack_sha256: str | None = None,
    expected_manifest_sha256: str | None = None,
) -> PublicMVPScenarioPackVerification:
    """Verify physical integrity and closed public semantics before returning data."""
    package = Path(package_dir)
    if not package.is_dir() or package.is_symlink():
        raise ValueError("public MVP package must be a regular directory")
    actual_entries = {item.name for item in package.iterdir()}
    if actual_entries != PUBLIC_MVP_PACKAGE_FILES:
        raise ValueError("public MVP package must contain exactly two declared files")
    pack_path = package / PACK_FILENAME
    manifest_path = package / MANIFEST_FILENAME
    if (
        pack_path.is_symlink()
        or manifest_path.is_symlink()
        or not pack_path.is_file()
        or not manifest_path.is_file()
    ):
        raise ValueError("public MVP package files must be regular files")

    manifest_bytes = _read_bounded_bytes(
        manifest_path,
        maximum_bytes=MAXIMUM_MANIFEST_BYTES,
        label="public MVP manifest",
    )
    manifest_sha256 = _sha256_bytes(manifest_bytes)
    if expected_manifest_sha256 is not None and manifest_sha256 != expected_manifest_sha256:
        raise ValueError("public MVP manifest digest does not match the expected digest")
    manifest = _read_object_bytes(manifest_bytes, label="public MVP manifest")
    _validate_manifest(manifest)

    pack_bytes = _read_bounded_bytes(
        pack_path,
        maximum_bytes=MAXIMUM_PACK_BYTES,
        label="public MVP scenario pack",
    )
    pack_sha256 = _sha256_bytes(pack_bytes)
    artifact = cast(dict[str, object], manifest["artifact"])
    if artifact["bytes"] != len(pack_bytes) or artifact["sha256"] != pack_sha256:
        raise ValueError("public MVP scenario-pack integrity mismatch")
    if expected_pack_sha256 is not None and pack_sha256 != expected_pack_sha256:
        raise ValueError("public MVP scenario-pack digest does not match the expected digest")

    schema = Path(schema_path)
    if not schema.is_file() or schema.is_symlink():
        raise ValueError("public MVP scenario schema must be a regular file")
    schema_bytes = _read_bounded_bytes(
        schema,
        maximum_bytes=MAXIMUM_SCHEMA_BYTES,
        label="public MVP scenario schema",
    )
    schema_binding = cast(dict[str, object], manifest["schema"])
    if schema_binding["bytes"] != len(schema_bytes) or schema_binding["sha256"] != _sha256_bytes(
        schema_bytes
    ):
        raise ValueError("public MVP schema integrity mismatch")
    schema_payload = _read_object_bytes(schema_bytes, label="public MVP scenario schema")
    if schema_payload.get("$id") != SCHEMA_ID:
        raise ValueError("public MVP scenario schema identifier mismatch")

    pack = _read_object_bytes(pack_bytes, label="public MVP scenario pack")
    _validate_pack(pack, expected_replications=int(manifest["replications_per_scenario"]))
    scenarios = cast(list[dict[str, object]], pack["scenarios"])
    timeseries_point_count = sum(
        len(cast(list[object], scenario["timeseries"])) for scenario in scenarios
    )
    if manifest["scenario_count"] != len(scenarios):
        raise ValueError("public MVP scenario count does not match the manifest")
    if manifest["timeseries_point_count"] != timeseries_point_count:
        raise ValueError("public MVP timeseries count does not match the manifest")
    design = cast(dict[str, object], pack["design"])
    if manifest["root_seed"] != design["root_seed"]:
        raise ValueError("public MVP root seed does not match the manifest")

    return PublicMVPScenarioPackVerification(
        package_dir=package,
        pack_path=pack_path,
        manifest_path=manifest_path,
        pack_sha256=pack_sha256,
        manifest_sha256=manifest_sha256,
        manifest_content_sha256=str(manifest["manifest_content_sha256"]),
        scenario_count=len(scenarios),
        timeseries_point_count=timeseries_point_count,
        pack=pack,
    )
