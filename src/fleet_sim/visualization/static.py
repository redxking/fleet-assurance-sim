"""Publication-oriented static figures for the initial replay bundle."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from fleet_sim.visualization.bundle import load_replay_bundle
from fleet_sim.visualization.export_plotly import STATE_COLORS


def export_final_topology(bundle_path: str | Path, output_path: str | Path) -> Path:
    bundle = load_replay_bundle(bundle_path)
    nodes = {node["id"]: node for node in bundle.graph_layers["nodes"]}
    figure, axis = plt.subplots(figsize=(10, 8))
    for source, target in bundle.graph_layers["layers"]["communication"].get("edges", []):
        axis.plot(
            [nodes[source]["x"], nodes[target]["x"]],
            [nodes[source]["y"], nodes[target]["y"]],
            linewidth=0.4,
            alpha=0.25,
        )
    for source, target in bundle.graph_layers["layers"]["authorization"].get("edges", []):
        axis.plot(
            [nodes[source]["x"], nodes[target]["x"]],
            [nodes[source]["y"], nodes[target]["y"]],
            linewidth=0.8,
            alpha=0.45,
        )
    for state_name, color in STATE_COLORS.items():
        selected = [
            agent_id
            for agent_id, state in bundle.final_state.agents.items()
            if state.health.value == state_name
        ]
        if not selected:
            continue
        axis.scatter(
            [nodes[agent_id]["x"] for agent_id in selected],
            [nodes[agent_id]["y"] for agent_id in selected],
            s=28,
            label=state_name.capitalize(),
            color=color,
        )
    axis.set_title(
        f"Final fleet state: {bundle.run_id}\n"
        f"N={bundle.configuration['n_agents']}, seed={bundle.configuration['seed']}, "
        f"representation={bundle.graph_layers.get('representation', 'exact')}"
    )
    axis.set_axis_off()
    axis.legend(loc="best")
    figure.tight_layout()
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return destination
