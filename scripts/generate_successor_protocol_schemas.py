#!/usr/bin/env python3
"""Generate or verify the checked-in successor protocol JSON Schemas."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fleet_sim.empirical.successor_protocol import (
    successor_evaluation_inputs_schema,
    successor_registration_plan_schema,
    successor_registration_schema,
    transfer_contract_schema,
)


def _schemas(root: Path) -> tuple[tuple[Path, dict[str, object]], ...]:
    return (
        (root / "schemas" / "successor_transfer_contract.schema.json", transfer_contract_schema()),
        (
            root / "schemas" / "successor_registration_plan.schema.json",
            successor_registration_plan_schema(),
        ),
        (
            root / "schemas" / "successor_registration.schema.json",
            successor_registration_schema(),
        ),
        (
            root / "schemas" / "successor_evaluation_inputs.schema.json",
            successor_evaluation_inputs_schema(),
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="replace schemas atomically")
    args = parser.parse_args()
    mismatches: list[str] = []
    for path, schema in _schemas(ROOT):
        encoded = (json.dumps(schema, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
        if args.write:
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_bytes(encoded)
            temporary.replace(path)
        elif not path.is_file() or path.read_bytes() != encoded:
            mismatches.append(path.relative_to(ROOT).as_posix())
    if mismatches:
        parser.error("schema drift: " + ", ".join(mismatches))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
