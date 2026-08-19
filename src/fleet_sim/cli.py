"""Command-line interface for Fleet Assurance Simulation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fleet_sim.config import load_config
from fleet_sim.experiments.simulator import FleetSimulator
from fleet_sim.model.events import EventLog
from fleet_sim.model.replay import ReplayEngine
from fleet_sim.model.state import FleetState
from fleet_sim.provenance.registry import load_parameter_registry
from fleet_sim.visualization.console import build_console


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def command_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    output_root = Path(args.output).resolve()
    simulator = FleetSimulator(config, _repository_root())
    artifacts = simulator.run(output_root)
    html_path = None
    if args.visualize:
        html_path = build_console(
            artifacts.bundle_dir,
            artifacts.bundle_dir / "virtual_fleet_assurance_console.html",
        )
    summary = json.loads(artifacts.summary_path.read_text(encoding="utf-8"))
    output = {
        "run_id": config.run_id,
        "bundle": str(artifacts.bundle_dir),
        "visual_console": str(html_path) if html_path else None,
        "event_count": summary["event_count"],
        "event_log_digest": artifacts.event_log_digest,
        "final_state_hash": artifacts.final_state_hash,
        "replay_state_hash": artifacts.replay_state_hash,
        "replay_verified": artifacts.final_state_hash == artifacts.replay_state_hash,
        "evidence_class": summary["evidence_class"],
        "parameter_class": summary["parameter_class"],
    }
    print(json.dumps(output, indent=2, sort_keys=True, default=str))
    return 0


def command_visualize(args: argparse.Namespace) -> int:
    output = build_console(args.bundle, args.output)
    print(output)
    return 0


def command_verify_replay(args: argparse.Namespace) -> int:
    bundle = Path(args.bundle)
    initial = FleetState.from_dict(
        json.loads((bundle / "initial_state.json").read_text(encoding="utf-8"))
    )
    expected = FleetState.from_dict(
        json.loads((bundle / "final_state.json").read_text(encoding="utf-8"))
    )
    events = EventLog.read_jsonl(bundle / "events.jsonl")
    replayed = ReplayEngine(initial, events).replay()
    snapshots_path = bundle / "snapshots.jsonl"
    result = {
        "passed": replayed.state_hash() == expected.state_hash(),
        "event_count": len(events),
        "expected_state_hash": expected.state_hash(),
        "replay_state_hash": replayed.state_hash(),
        "event_log_digest": events.digest(),
        "snapshots_present": snapshots_path.exists(),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 2


def command_validate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    records = load_parameter_registry(args.registry)
    output = {
        "status": "valid",
        "scenario_name": config.scenario_name,
        "configuration_hash": config.configuration_hash,
        "parameter_records": len(records),
        "parameter_class": config.provenance,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def command_stage0(args: argparse.Namespace) -> int:
    from fleet_sim.experiments.stage0 import run_stage0

    report = run_stage0(
        repository_root=Path(args.repository_root).resolve(),
        output_root=Path(args.output).resolve(),
        replications=args.replications,
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report["overall_passed"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fleet-sim")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="execute one fleet scenario")
    run_parser.add_argument("--config", required=True, type=Path)
    run_parser.add_argument("--output", default=".", type=Path)
    run_parser.add_argument("--visualize", action="store_true")
    run_parser.set_defaults(func=command_run)

    visual = subparsers.add_parser("visualize", help="build an offline replay console")
    visual.add_argument("--bundle", required=True, type=Path)
    visual.add_argument("--output", required=True, type=Path)
    visual.set_defaults(func=command_visualize)

    replay = subparsers.add_parser("verify-replay", help="verify replay-state equivalence")
    replay.add_argument("--bundle", required=True, type=Path)
    replay.set_defaults(func=command_verify_replay)

    validate = subparsers.add_parser("validate", help="validate configuration and provenance registry")
    validate.add_argument("--config", required=True, type=Path)
    validate.add_argument(
        "--registry",
        default=Path("configs/parameters/registry.yaml"),
        type=Path,
    )
    validate.set_defaults(func=command_validate)

    stage0 = subparsers.add_parser("stage0", help="run Stage 0 verification and build artifacts")
    stage0.add_argument("--repository-root", default=".", type=Path)
    stage0.add_argument("--output", default=".", type=Path)
    stage0.add_argument("--replications", type=int, default=30)
    stage0.set_defaults(func=command_stage0)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        code = int(args.func(args))
    except Exception as exc:
        print(f"fleet-sim failed: {exc}", file=sys.stderr)
        raise
    raise SystemExit(code)


if __name__ == "__main__":
    main()
