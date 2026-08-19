"""Command-line application for the Stage 3 offline evidence console."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from fleet_sim.visualization.stage3_console import (
    ADMISSION_PATTERNS,
    ATTACK_CLASSES,
    INJECTIONS,
    TOPOLOGIES,
    Stage3ScenarioConfig,
    build_stage3_console,
    export_stage3_console_json,
    run_visual_scenario,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a self-contained Stage 3 evidence console from immutable results, "
            "or create a bounded visual demonstration before building the console."
        )
    )
    parser.add_argument("--mode", choices=("live", "replay", "comparison"), default="replay")
    parser.add_argument(
        "--execution",
        type=Path,
        help="completed Stage 3 execution directory for replay or comparison",
    )
    parser.add_argument("--comparison", type=Path, help="second immutable execution directory")
    parser.add_argument("--output", type=Path, help="offline HTML output outside source runs")
    parser.add_argument("--json-output", type=Path, help="optional bounded evidence JSON export")
    parser.add_argument("--overwrite-output", action="store_true")

    live = parser.add_argument_group("bounded live demonstration")
    live.add_argument("--run-dir", type=Path, help="new immutable visual run directory")
    live.add_argument("--scenario-json", type=Path, help="JSON object with scenario fields")
    live.add_argument("--fleet-size", type=int, default=100)
    live.add_argument("--admission-pattern", choices=ADMISSION_PATTERNS, default="staged")
    live.add_argument("--capacity-multiplier", type=float, default=1.0)
    live.add_argument("--topology", choices=TOPOLOGIES, default="random_regular")
    live.add_argument("--attack-class", choices=ATTACK_CLASSES, default="credential_replay")
    live.add_argument("--injection", choices=INJECTIONS, default="none")
    live.add_argument("--injection-fraction", type=float, default=0.0)
    live.add_argument("--detection-delay-steps", type=int, default=3)
    live.add_argument("--quarantine-delay-steps", type=int, default=2)
    live.add_argument("--revocation-delay-steps", type=int, default=2)
    live.add_argument("--admission-duration-s", type=float, default=30.0)
    live.add_argument("--recovery-window-s", type=float, default=15.0)
    live.add_argument("--horizon-steps", type=int, default=20)
    live.add_argument("--seed", type=int, default=320260819)
    return parser


def _load_scenario(args: argparse.Namespace) -> Stage3ScenarioConfig:
    if args.scenario_json is not None:
        value = json.loads(args.scenario_json.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("scenario JSON root must be an object")
        if "configuration" in value:
            value = value["configuration"]
        if not isinstance(value, dict):
            raise ValueError("scenario configuration must be an object")
        return Stage3ScenarioConfig.from_mapping(value)
    return Stage3ScenarioConfig(
        fleet_size=args.fleet_size,
        admission_pattern=args.admission_pattern,
        capacity_multiplier=args.capacity_multiplier,
        topology=args.topology,
        attack_class=args.attack_class,
        injection=args.injection,
        injection_fraction=args.injection_fraction,
        detection_delay_steps=args.detection_delay_steps,
        quarantine_delay_steps=args.quarantine_delay_steps,
        revocation_delay_steps=args.revocation_delay_steps,
        admission_duration_s=args.admission_duration_s,
        recovery_window_s=args.recovery_window_s,
        horizon_steps=args.horizon_steps,
        seed=args.seed,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    execution = args.execution
    if args.mode == "live":
        if args.run_dir is None:
            raise ValueError("live mode requires --run-dir")
        scenario = _load_scenario(args)
        execution = run_visual_scenario(scenario, args.run_dir)
    elif execution is None:
        raise ValueError("replay and comparison modes require --execution")
    if args.mode == "comparison" and args.comparison is None:
        raise ValueError("comparison mode requires --comparison")
    assert execution is not None
    output = args.output or execution.parent / f"{execution.name}-stage3-console.html"
    console = build_stage3_console(
        execution,
        output,
        comparison_execution=args.comparison,
        initial_mode=args.mode,
        overwrite=args.overwrite_output,
    )
    json_output: Path | None = None
    if args.json_output is not None:
        json_output = export_stage3_console_json(
            execution,
            args.json_output,
            comparison_execution=args.comparison,
            overwrite=args.overwrite_output,
        )
    print(
        json.dumps(
            {
                "status": "completed",
                "mode": args.mode,
                "source_execution": str(execution),
                "comparison_execution": str(args.comparison) if args.comparison else None,
                "console": str(console),
                "json_export": str(json_output) if json_output else None,
                "source_mutation": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

