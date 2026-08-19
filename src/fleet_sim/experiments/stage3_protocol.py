"""Hash gates and immutable output controls for Stage 3 experiments."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class FrozenInputCheck:
    """One frozen-input verification result."""

    path: str
    expected_sha256: str
    actual_sha256: str | None
    match: bool


class FrozenInputError(RuntimeError):
    """Raised when confirmatory inputs do not match the frozen manifest."""


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for one file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_safe_identifier(value: str, *, label: str) -> str:
    """Return a filesystem-safe protocol or execution identifier."""

    if not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} contains unsafe characters")
    return value


def _validated_relative_path(value: str) -> PurePosixPath:
    relative = PurePosixPath(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError(f"frozen path must be repository relative: {value!r}")
    return relative


def environment_snapshot() -> dict[str, object]:
    """Capture the execution environment relevant to numerical reproduction."""

    packages: dict[str, str | None] = {}
    for name in (
        "numpy",
        "scipy",
        "networkx",
        "pandas",
        "matplotlib",
        "PyYAML",
        "pydantic",
        "pyarrow",
    ):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "thread_controls": {
            "OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS"),
            "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS"),
        },
        "packages": packages,
    }


def build_preexecution_manifest(
    root: Path,
    *,
    protocol_id: str,
    frozen_files: Iterable[str],
    evidence_scope: str,
    protocol_status: str = "frozen_before_confirmatory_execution",
    execution_contract: Mapping[str, Any] | None = None,
) -> dict[str, object]:
    """Build a manifest payload without writing it."""

    validate_safe_identifier(protocol_id, label="protocol_id")
    files: dict[str, str] = {}
    for raw in sorted(set(frozen_files)):
        relative = _validated_relative_path(raw)
        path = root.joinpath(*relative.parts)
        if not path.is_file():
            raise FileNotFoundError(f"frozen input is missing: {relative.as_posix()}")
        files[relative.as_posix()] = sha256_file(path)
    if not files:
        raise ValueError("at least one frozen input is required")
    frozen_environment = environment_snapshot()
    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "protocol_id": protocol_id,
        "protocol_status": protocol_status,
        "evidence_scope": evidence_scope,
        "created_utc": datetime.now(UTC).isoformat(),
        "files": files,
        "environment_at_freeze": frozen_environment,
    }
    if execution_contract is not None:
        frozen_contract = dict(execution_contract)
        execution_id = frozen_contract.get("execution_id")
        if execution_id is not None:
            validate_safe_identifier(execution_id, label="execution_id")
        manifest["execution_contract"] = frozen_contract
    manifest["protocol_hash"] = _canonical_digest(manifest)
    return manifest


def write_new_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write JSON atomically while refusing to replace an existing artifact."""

    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    if temporary.exists():
        raise FileExistsError(f"temporary artifact already exists: {temporary}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_preexecution_manifest(path: Path) -> dict[str, object]:
    """Load and authenticate a Stage 3 preexecution manifest."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("preexecution manifest must contain a JSON object")
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("preexecution manifest files must be a nonempty object")
    expected_hash = payload.get("protocol_hash")
    if not isinstance(expected_hash, str):
        raise TypeError("preexecution manifest is missing protocol_hash")
    if not isinstance(payload.get("environment_at_freeze"), dict):
        raise TypeError("preexecution manifest environment_at_freeze must be an object")
    execution_contract = payload.get("execution_contract")
    if execution_contract is not None and not isinstance(execution_contract, dict):
        raise ValueError("preexecution manifest execution_contract must be an object")
    identity = dict(payload)
    del identity["protocol_hash"]
    actual_hash = _canonical_digest(identity)
    if actual_hash != expected_hash:
        raise FrozenInputError("preexecution manifest protocol hash is invalid")
    return payload


def require_frozen_environment(
    manifest: Mapping[str, object],
) -> dict[str, object]:
    """Abort unless the live numerical environment exactly matches the freeze."""

    frozen = manifest.get("environment_at_freeze")
    if not isinstance(frozen, dict):
        raise TypeError("preexecution manifest environment_at_freeze must be an object")
    live = environment_snapshot()
    if live != frozen:
        changed = sorted(
            key
            for key in set(frozen) | set(live)
            if frozen.get(key) != live.get(key)
        )
        detail = ", ".join(changed) or "unknown"
        raise FrozenInputError(
            f"live environment does not match environment_at_freeze: {detail}"
        )
    return live


def verify_frozen_inputs(
    root: Path,
    manifest: Mapping[str, object],
) -> tuple[bool, list[FrozenInputCheck]]:
    """Verify all paths listed in a preexecution manifest."""

    raw_files = manifest.get("files")
    if not isinstance(raw_files, dict) or not raw_files:
        raise ValueError("preexecution manifest files must be a nonempty object")
    checks: list[FrozenInputCheck] = []
    for raw, expected in sorted(raw_files.items()):
        relative = _validated_relative_path(str(raw))
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError(f"invalid expected digest for {relative.as_posix()}")
        path = root.joinpath(*relative.parts)
        actual = sha256_file(path) if path.is_file() else None
        checks.append(
            FrozenInputCheck(
                path=relative.as_posix(),
                expected_sha256=expected,
                actual_sha256=actual,
                match=actual == expected,
            )
        )
    return all(check.match for check in checks), checks


def require_frozen_inputs(root: Path, manifest: Mapping[str, object]) -> list[FrozenInputCheck]:
    """Return checks or abort before confirmatory execution."""

    passed, checks = verify_frozen_inputs(root, manifest)
    if not passed:
        mismatches = ", ".join(check.path for check in checks if not check.match)
        raise FrozenInputError(f"frozen input verification failed: {mismatches}")
    return checks


def reserve_execution_directory(
    root: Path,
    *,
    protocol_hash: str,
    execution_id: str,
) -> Path:
    """Create one run-specific directory and refuse all replacement."""

    for label, value in (("protocol_hash", protocol_hash), ("execution_id", execution_id)):
        validate_safe_identifier(value, label=label)
    destination = root / "results" / "stage3" / protocol_hash / execution_id
    destination.mkdir(parents=True, exist_ok=False)
    return destination


def checks_as_dicts(checks: Iterable[FrozenInputCheck]) -> list[dict[str, object]]:
    """Convert verification records to a JSON-ready representation."""

    return [asdict(check) for check in checks]


def artifact_inventory(directory: Path, *, root: Path) -> list[dict[str, object]]:
    """Hash every file beneath a completed execution directory."""

    rows: list[dict[str, object]] = []
    for path in sorted(candidate for candidate in directory.rglob("*") if candidate.is_file()):
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows
