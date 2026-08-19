"""Self-contained Plotly replay export for deterministic event bundles."""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go

from fleet_sim.model.state import FleetState
from fleet_sim.visualization.bundle import ReplayBundle, load_replay_bundle


STATE_COLORS = {
    "idle": "#4C78A8",
    "working": "#72B7B2",
    "suspected": "#F58518",
    "compromised": "#E45756",
    "isolated": "#B279A2",
    "revoked": "#79706E",
    "terminated": "#1A1A1A",
    "recovered": "#54A24B",
}


IMPORTANT_TYPES = {
    "SIMULATION_START",
    "SIMULATION_END",
    "GOSSIP_SEED",
    "GOSSIP_ROUND",
    "COMPROMISE",
    "DETECTION",
    "QUARANTINE",
    "REVOCATION",
    "RECOVERY",
    "SECURITY_ROUND",
    "TIMING_DENIAL_START",
    "CREDENTIAL_REVOCATION_STORM_START",
}


def _edge_coordinates(bundle: ReplayBundle, layer_name: str) -> tuple[list[float | None], list[float | None]]:
    nodes = {node["id"]: node for node in bundle.graph_layers["nodes"]}
    x: list[float | None] = []
    y: list[float | None] = []
    for source, target in bundle.graph_layers["layers"][layer_name].get("edges", []):
        if source not in nodes or target not in nodes:
            continue
        x.extend([nodes[source]["x"], nodes[target]["x"], None])
        y.extend([nodes[source]["y"], nodes[target]["y"], None])
    return x, y


def _node_payload(bundle: ReplayBundle, state: FleetState) -> tuple[list[str], list[str]]:
    colors: list[str] = []
    hover: list[str] = []
    for node in bundle.graph_layers["nodes"]:
        agent_id = node["id"]
        agent = state.agents[agent_id]
        colors.append(STATE_COLORS[agent.health.value])
        hover.append(
            f"{agent_id}<br>state={agent.health.value}<br>partition={agent.partition}"
            f"<br>credential_epoch={agent.credential_epoch}"
            f"<br>clock_uncertainty={agent.timing_uncertainty_s:.9g} s"
            f"<br>task={agent.current_task_id or 'none'}"
        )
    return colors, hover


def _selected_event_indices(bundle: ReplayBundle, max_frames: int) -> list[int]:
    count = len(bundle.events.events)
    selected = {0, count}
    stride = max(1, count // max(1, max_frames - 2))
    selected.update(range(stride, count + 1, stride))
    for index, event in enumerate(bundle.events.events, start=1):
        if event.event_type in IMPORTANT_TYPES:
            selected.add(index)
    ordered = sorted(selected)
    if len(ordered) <= max_frames:
        return ordered
    important = {
        index
        for index, event in enumerate(bundle.events.events, start=1)
        if event.event_type in IMPORTANT_TYPES
    }
    retained = {0, count, *important}
    remaining = max(0, max_frames - len(retained))
    candidates = [index for index in ordered if index not in retained]
    if remaining and candidates:
        step = max(1, len(candidates) // remaining)
        retained.update(candidates[::step][:remaining])
    return sorted(retained)


def export_replay_html(
    bundle_path: str | Path,
    output_path: str | Path | None = None,
    *,
    max_frames: int = 300,
) -> Path:
    bundle = load_replay_bundle(bundle_path)
    target = Path(output_path) if output_path else bundle.path / "replay.html"
    nodes = bundle.graph_layers["nodes"]
    x = [node["x"] for node in nodes]
    y = [node["y"] for node in nodes]
    communication_x, communication_y = _edge_coordinates(bundle, "communication")
    authorization_x, authorization_y = _edge_coordinates(bundle, "authorization")

    state = FleetState.from_dict(bundle.initial_state.to_dict())
    initial_colors, initial_hover = _node_payload(bundle, state)
    traces = [
        go.Scatter(
            x=communication_x,
            y=communication_y,
            mode="lines",
            line={"width": 0.6, "color": "rgba(90,90,90,0.30)"},
            hoverinfo="skip",
            name="Communication graph",
        ),
        go.Scatter(
            x=authorization_x,
            y=authorization_y,
            mode="lines",
            line={"width": 1.2, "color": "rgba(130,70,170,0.45)"},
            hoverinfo="skip",
            name="Authorization graph",
        ),
        go.Scatter(
            x=x,
            y=y,
            mode="markers",
            marker={"size": 10, "color": initial_colors, "line": {"width": 0.5, "color": "white"}},
            text=initial_hover,
            hoverinfo="text",
            name="Agents",
        ),
    ]

    for state_name, color in STATE_COLORS.items():
        traces.append(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                marker={"size": 9, "color": color},
                name=state_name.capitalize(),
                hoverinfo="skip",
            )
        )

    selected = set(_selected_event_indices(bundle, max_frames))
    frames: list[go.Frame] = []
    frame_state = FleetState.from_dict(bundle.initial_state.to_dict())
    if 0 in selected:
        frames.append(
            go.Frame(
                name="0",
                data=[go.Scatter(marker={"color": initial_colors}, text=initial_hover)],
                traces=[2],
                layout=go.Layout(title_text=f"{bundle.run_id} | t=0.000 s | initial state"),
            )
        )
    for index, event in enumerate(bundle.events.events, start=1):
        frame_state.apply(event)
        if index not in selected:
            continue
        colors, hover = _node_payload(bundle, frame_state)
        compromised = sum(
            agent.health.value in {"compromised", "suspected"}
            for agent in frame_state.agents.values()
        )
        queue = frame_state.queues.get("authorization", 0)
        title = (
            f"{bundle.run_id} | t={event.simulation_time:.3f} s | {event.event_type} | "
            f"compromised or suspected={compromised} | auth queue={queue}"
        )
        frames.append(
            go.Frame(
                name=str(index),
                data=[go.Scatter(marker={"color": colors}, text=hover)],
                traces=[2],
                layout=go.Layout(title_text=title),
            )
        )

    slider_steps = [
        {
            "args": [[frame.name], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}],
            "label": frame.name,
            "method": "animate",
        }
        for frame in frames
    ]
    figure = go.Figure(data=traces, frames=frames)
    figure.update_layout(
        title=f"{bundle.run_id} | Exact event replay, visual layout {bundle.graph_layers.get('representation', 'exact')}",
        showlegend=True,
        hovermode="closest",
        xaxis={"visible": False, "scaleanchor": "y", "scaleratio": 1},
        yaxis={"visible": False},
        margin={"l": 10, "r": 10, "t": 70, "b": 10},
        updatemenus=[
            {
                "type": "buttons",
                "showactive": False,
                "x": 0.0,
                "y": 1.08,
                "buttons": [
                    {
                        "label": "Play",
                        "method": "animate",
                        "args": [None, {"frame": {"duration": 120, "redraw": False}, "fromcurrent": True}],
                    },
                    {
                        "label": "Pause",
                        "method": "animate",
                        "args": [[None], {"frame": {"duration": 0}, "mode": "immediate"}],
                    },
                ],
            }
        ],
        sliders=[
            {
                "active": 0,
                "currentvalue": {"prefix": "Event index: "},
                "pad": {"t": 35},
                "steps": slider_steps,
            }
        ],
        annotations=[
            {
                "text": (
                    f"Seed {bundle.configuration['seed']} | N={bundle.configuration['n_agents']} | "
                    f"configuration {bundle.summary['configuration_hash']} | parameter class "
                    f"{bundle.summary['parameter_class']}"
                ),
                "xref": "paper",
                "yref": "paper",
                "x": 1.0,
                "y": -0.08,
                "showarrow": False,
                "xanchor": "right",
            }
        ],
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(target, include_plotlyjs=True, full_html=True, auto_open=False)
    return target
