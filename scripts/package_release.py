#!/usr/bin/env python3
"""Create a reproducible source release ZIP from the repository root."""

from __future__ import annotations

import argparse
import hashlib
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath

EXCLUDED_PARTS = {
    ".git",
    ".venv",
    ".venv-stage3-verify",
    ".matplotlib-cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "local_runs",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".pid"}
EXCLUDED_NAMES = {".DS_Store"}
FIXED_ZIP_TIME = (2026, 8, 19, 0, 0, 0)
SAFE_ARCHIVE_ROOT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def include(relative: Path) -> bool:
    if relative.name in EXCLUDED_NAMES:
        return False
    if relative.suffix in EXCLUDED_SUFFIXES:
        return False
    for part in relative.parts:
        if part in EXCLUDED_PARTS or part.endswith(".egg-info"):
            return False
    return True


def refresh_manifest(root: Path) -> Path:
    """Write file hashes for every packaged file except the manifest itself."""

    manifest = root / "MANIFEST.sha256"
    paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path != manifest
        and include(path.relative_to(root))
    )
    manifest.write_text(
        "".join(f"{digest(path)}  {path.relative_to(root).as_posix()}\n" for path in paths),
        encoding="utf-8",
    )
    return manifest


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--archive-root", default=None)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    output = (args.output or root.parent / f"{root.name}.zip").resolve()
    archive_root = args.archive_root or root.name
    if not SAFE_ARCHIVE_ROOT.fullmatch(archive_root):
        raise ValueError("archive-root must be one safe directory name")
    checksum = output.with_suffix(output.suffix + ".sha256")
    if output.exists() or checksum.exists():
        raise FileExistsError("refusing to overwrite an existing release or checksum")
    refresh_manifest(root)
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and include(path.relative_to(root))
        and path.resolve() != output
    )

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = PurePosixPath(archive_root) / PurePosixPath(
                path.relative_to(root).as_posix()
            )
            info = zipfile.ZipInfo(str(relative), date_time=FIXED_ZIP_TIME)
            mode = path.stat().st_mode
            permissions = 0o755 if mode & stat.S_IXUSR else 0o644
            info.external_attr = (stat.S_IFREG | permissions) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

    checksum.write_text(f"{digest(output)}  {output.name}\n", encoding="utf-8")
    print(output)
    print(checksum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
