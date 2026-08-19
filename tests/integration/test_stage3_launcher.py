from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_launcher_rejects_execution_id_traversal_without_writing(tmp_path: Path) -> None:
    pilot_parent = tmp_path / "results/stage3/engineering-pilots"
    traversal_target = tmp_path / "results/stage3/escape"
    pilot_parent.mkdir(parents=True)
    traversal_target.mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_stage3.py"),
            "--root",
            str(tmp_path),
            "--mode",
            "pilot",
            "--execution-id",
            "../escape",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "execution_id contains unsafe characters" in completed.stderr
    assert not (traversal_target / "execution_failure.json").exists()
