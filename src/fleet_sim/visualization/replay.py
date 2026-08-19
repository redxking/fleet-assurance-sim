"""Offline Virtual Fleet Assurance Console replay generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bokeh.embed import file_html
from bokeh.layouts import column, row
from bokeh.models import (
    Button,
    CheckboxButtonGroup,
    ColumnDataSource,
    CustomJS,
    Div,
    HoverTool,
    Slider,
    Span,
)
from bokeh.plotting import figure
from bokeh.resources import INLINE

from fleet_sim.model.events import EventLog
from fleet_sim.model.state import FleetState


STATUS_COLORS = {
    "idle": "#5B8FF9",
    "working": "#61DDAA",
    "suspected": "#F6BD16",
    "compromised": "#E86452",
    "isolated": "#6F5EF9",
    "revoked": "#5D7092",
    "terminated": "#1F2329",
    "recovered": "#6DC8EC",
    "aggregate": "#8C8C8C",
}


@dataclass(frozen=True, slots=True)
class ReplayFrame:
    event_index: int
    simulation_time: float
    event_type: str
    event_id: str
    description: str
    status: list[str]
    colors: list[str]
    queue_length: float
    queue_utilization: float
    useful_tasks: float
    compromised_count: int
    isolated_count: int
    revoked_count: int


def generate_replay_html(
    bundle_dir: str | Path,
    output_path: str | Path,
    *,
    max_frames: int = 1_500,
) -> Path:
    bundle = Path(bundle_dir)
    output = Path(output_path)
    metadata = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
    graph = json.loads((bundle / "graph.json").read_text(encoding="utf-8"))
    initial_state = FleetState.from_dict(
        json.loads((bundle / "initial_state.json").read_text(encoding="utf-8"))
    )
    event_log = EventLog.read_jsonl(bundle / "events.jsonl")
    frames = build_frames(initial_state, event_log, graph, max_frames=max_frames)
    layout = build_replay_layout(metadata, graph, frames)
    html = file_html(
        layout,
        INLINE,
        title=f"Virtual Fleet Assurance Console | {metadata['run_id']}",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output


def build_frames(
    initial_state: FleetState,
    event_log: EventLog,
    graph_payload: dict[str, Any],
    *,
    max_frames: int,
) -> list[ReplayFrame]:
    if max_frames < 2:
        raise ValueError("max_frames must be at least two")
    node_ids = [str(node["id"]) for node in graph_payload["nodes"]]
    events = event_log.events
    selected = _selected_event_indexes(events, max_frames)
    state = FleetState.from_dict(initial_state.to_dict())
    frames = [_frame_from_state(0, None, state, node_ids, graph_payload)]
    for index, event in enumerate(events, start=1):
        state.apply(event)
        if index in selected:
            frames.append(
                _frame_from_state(index, event, state, node_ids, graph_payload)
            )
    if frames[-1].event_index != len(events):
        final_event = events[-1] if events else None
        frames.append(
            _frame_from_state(
                len(events), final_event, state, node_ids, graph_payload
            )
        )
    return frames


def build_replay_layout(
    metadata: dict[str, Any],
    graph: dict[str, Any],
    frames: list[ReplayFrame],
):
    nodes = graph["nodes"]
    node_ids = [str(node["id"]) for node in nodes]
    x = [float(node["x"]) for node in nodes]
    y = [float(node["y"]) for node in nodes]
    partitions = [str(node.get("partition", "n/a")) for node in nodes]
    first = frames[0]
    node_source = ColumnDataSource(
        data={
            "x": x,
            "y": y,
            "agent_id": node_ids,
            "partition": partitions,
            "status": first.status,
            "color": first.colors,
        }
    )
    position_lookup = {
        node_id: (x_value, y_value)
        for node_id, x_value, y_value in zip(node_ids, x, y, strict=True)
    }
    communication_source = ColumnDataSource(
        data=_edge_coordinates(
            graph["layers"].get("communication", []), position_lookup
        )
    )
    authorization_source = ColumnDataSource(
        data=_edge_coordinates(
            graph["layers"].get("authorization", []), position_lookup
        )
    )

    topology = figure(
        width=760,
        height=660,
        title="Fleet topology and runtime state",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        active_scroll="wheel_zoom",
        match_aspect=True,
    )
    topology.grid.visible = False
    topology.axis.visible = False
    communication_renderer = topology.multi_line(
        xs="xs",
        ys="ys",
        source=communication_source,
        line_alpha=0.18,
        line_width=1,
        line_color="#5B8FF9",
        legend_label="Communication",
    )
    authorization_renderer = topology.multi_line(
        xs="xs",
        ys="ys",
        source=authorization_source,
        line_alpha=0.28,
        line_width=1.5,
        line_color="#F6BD16",
        legend_label="Authorization",
    )
    nodes_renderer = topology.scatter(
        x="x",
        y="y",
        source=node_source,
        size=11 if len(nodes) <= 250 else 6,
        fill_color="color",
        line_color="#FFFFFF",
        line_width=0.5,
        fill_alpha=0.95,
    )
    topology.add_tools(
        HoverTool(
            renderers=[nodes_renderer],
            tooltips=[
                ("Agent", "@agent_id"),
                ("Status", "@status"),
                ("Partition", "@partition"),
            ],
        )
    )
    topology.legend.location = "top_left"
    topology.legend.click_policy = "hide"

    times = [frame.simulation_time for frame in frames]
    compromised = [frame.compromised_count for frame in frames]
    isolated = [frame.isolated_count for frame in frames]
    queue = [frame.queue_length for frame in frames]
    useful = [frame.useful_tasks for frame in frames]
    metric_source = ColumnDataSource(
        data={
            "time": times,
            "compromised": compromised,
            "isolated": isolated,
            "queue": queue,
            "useful": useful,
        }
    )
    metrics_plot = figure(
        width=600,
        height=330,
        title="Security, queue, and mission state",
        x_axis_label="Simulation time, seconds",
        y_axis_label="Count",
        tools="pan,wheel_zoom,box_zoom,reset,save",
    )
    metrics_plot.line(
        "time",
        "compromised",
        source=metric_source,
        line_width=2,
        legend_label="Compromised",
    )
    metrics_plot.line(
        "time",
        "isolated",
        source=metric_source,
        line_width=2,
        legend_label="Isolated",
    )
    metrics_plot.line(
        "time",
        "queue",
        source=metric_source,
        line_width=2,
        legend_label="Authorization queue",
    )
    metrics_plot.line(
        "time",
        "useful",
        source=metric_source,
        line_width=2,
        legend_label="Useful completions",
    )
    metrics_plot.legend.location = "top_left"
    metrics_plot.legend.click_policy = "hide"
    cursor = Span(location=0.0, dimension="height", line_width=2, line_dash="dashed")
    metrics_plot.add_layout(cursor)

    title = Div(
        text=(
            "<h1>Virtual Fleet Assurance Console</h1>"
            f"<p><b>Run:</b> {metadata['run_id']} | "
            f"<b>N:</b> {metadata['n_agents']} | "
            f"<b>Seed:</b> {metadata['seed']} | "
            f"<b>Display:</b> {metadata['display_mode']} | "
            f"<b>Evidence:</b> {metadata['evidence_class']}</p>"
        ),
        width=1360,
    )
    status = Div(width=600, height=220)
    legend = Div(
        text=_status_legend_html(),
        width=600,
        height=120,
    )
    slider = Slider(
        start=0,
        end=max(0, len(frames) - 1),
        value=0,
        step=1,
        title="Replay frame",
        width=1_200,
    )
    play = Button(label="Play", button_type="success", width=100)
    layers = CheckboxButtonGroup(
        labels=["Communication", "Authorization"],
        active=[0, 1],
        width=330,
    )

    frame_payload = [
        {
            "event_index": frame.event_index,
            "simulation_time": frame.simulation_time,
            "event_type": frame.event_type,
            "event_id": frame.event_id,
            "description": frame.description,
            "status": frame.status,
            "colors": frame.colors,
            "queue_length": frame.queue_length,
            "queue_utilization": frame.queue_utilization,
            "useful_tasks": frame.useful_tasks,
            "compromised_count": frame.compromised_count,
            "isolated_count": frame.isolated_count,
            "revoked_count": frame.revoked_count,
        }
        for frame in frames
    ]
    update_code = """
const index = Math.max(0, Math.min(frames.length - 1, slider.value));
const frame = frames[index];
node_source.data.status = frame.status.slice();
node_source.data.color = frame.colors.slice();
node_source.change.emit();
cursor.location = frame.simulation_time;
status.text = `<h2>Frame ${index + 1} of ${frames.length}</h2>` +
  `<p><b>Simulation time:</b> ${frame.simulation_time.toFixed(6)} s</p>` +
  `<p><b>Event:</b> ${frame.event_type} (${frame.event_id})</p>` +
  `<p>${frame.description}</p>` +
  `<p><b>Compromised:</b> ${frame.compromised_count} | ` +
  `<b>Isolated:</b> ${frame.isolated_count} | ` +
  `<b>Revoked:</b> ${frame.revoked_count}</p>` +
  `<p><b>Authorization queue:</b> ${frame.queue_length} | ` +
  `<b>Utilization:</b> ${(100 * frame.queue_utilization).toFixed(1)}% | ` +
  `<b>Useful completions:</b> ${frame.useful_tasks}</p>`;
"""
    callback = CustomJS(
        args={
            "frames": frame_payload,
            "slider": slider,
            "node_source": node_source,
            "cursor": cursor,
            "status": status,
        },
        code=update_code,
    )
    slider.js_on_change("value", callback)
    layers.js_on_change(
        "active",
        CustomJS(
            args={
                "layers": layers,
                "communication": communication_renderer,
                "authorization": authorization_renderer,
            },
            code="""
communication.visible = layers.active.includes(0);
authorization.visible = layers.active.includes(1);
""",
        ),
    )
    play.js_on_click(
        CustomJS(
            args={"slider": slider, "play": play},
            code="""
if (window.__fleet_assurance_timer) {
  clearInterval(window.__fleet_assurance_timer);
  window.__fleet_assurance_timer = null;
  play.label = "Play";
} else {
  play.label = "Pause";
  window.__fleet_assurance_timer = setInterval(() => {
    if (slider.value >= slider.end) {
      slider.value = 0;
    } else {
      slider.value = slider.value + 1;
    }
  }, 180);
}
""",
        )
    )
    slider.value = 0
    status.text = (
        f"<h2>Frame 1 of {len(frames)}</h2>"
        "<p><b>Simulation time:</b> 0.000000 s</p>"
        "<p><b>Event:</b> INITIAL_STATE</p>"
        "<p>Initial replay state before the first recorded event.</p>"
    )
    controls = row(play, layers)
    right_column = column(metrics_plot, status, legend)
    return column(title, slider, controls, row(topology, right_column))


def _selected_event_indexes(events: tuple[Any, ...], max_frames: int) -> set[int]:
    count = len(events)
    if count <= max_frames - 1:
        return set(range(1, count + 1))
    security_types = {
        "COMPROMISE",
        "DETECTION",
        "QUARANTINE",
        "REVOCATION",
        "RECOVERY",
        "TIMING_DENIAL_START",
        "TIMING_UPDATE",
        "SIMULATION_END",
    }
    mandatory = {
        index
        for index, event in enumerate(events, start=1)
        if event.event_type in security_types
    }
    remaining = max(1, max_frames - 1 - len(mandatory))
    stride = max(1, count // remaining)
    sampled = set(range(1, count + 1, stride))
    selected = mandatory | sampled | {count}
    if len(selected) > max_frames - 1:
        nonmandatory = sorted(selected - mandatory - {count})
        keep_count = max(0, max_frames - 1 - len(mandatory | {count}))
        if keep_count < len(nonmandatory):
            step = len(nonmandatory) / max(keep_count, 1)
            nonmandatory = [
                nonmandatory[min(len(nonmandatory) - 1, int(i * step))]
                for i in range(keep_count)
            ]
        selected = mandatory | set(nonmandatory) | {count}
    return selected


def _frame_from_state(
    event_index: int,
    event: Any | None,
    state: FleetState,
    node_ids: list[str],
    graph_payload: dict[str, Any],
) -> ReplayFrame:
    if graph_payload.get("display_mode") == "aggregated":
        status = ["aggregate"] * len(node_ids)
    else:
        status = [state.agents[node_id].health.value for node_id in node_ids]
    colors = [STATUS_COLORS.get(value, "#8C8C8C") for value in status]
    health_values = [runtime.health.value for runtime in state.agents.values()]
    queue_length = float(state.queues.get("authorization", 0))
    queue_utilization = float(state.queue_utilization.get("authorization", 0.0))
    if event is None:
        event_type = "INITIAL_STATE"
        event_id = "initial"
        simulation_time = 0.0
        description = "Initial replay state before the first recorded event."
    else:
        event_type = event.event_type
        event_id = event.event_id
        simulation_time = event.simulation_time
        description = _event_description(event)
    return ReplayFrame(
        event_index=event_index,
        simulation_time=simulation_time,
        event_type=event_type,
        event_id=event_id,
        description=description,
        status=status,
        colors=colors,
        queue_length=queue_length,
        queue_utilization=queue_utilization,
        useful_tasks=float(state.counters.get("useful_tasks_completed", 0.0)),
        compromised_count=health_values.count("compromised")
        + health_values.count("suspected"),
        isolated_count=health_values.count("isolated"),
        revoked_count=health_values.count("revoked"),
    )


def _event_description(event: Any) -> str:
    components = []
    if event.source_id:
        components.append(f"source {event.source_id}")
    if event.destination_id:
        components.append(f"destination {event.destination_id}")
    if event.task_id:
        components.append(f"task {event.task_id}")
    if event.authorization_decision:
        components.append(f"decision {event.authorization_decision}")
    if event.graph_layer:
        components.append(f"layer {event.graph_layer}")
    if event.metadata:
        concise = ", ".join(
            f"{key}={value}"
            for key, value in sorted(event.metadata.items())
            if key
            in {
                "reason",
                "useful",
                "latency_s",
                "queue_length",
                "utilization",
                "cumulative_compromised",
            }
        )
        if concise:
            components.append(concise)
    return "; ".join(components) if components else "No additional event fields."


def _edge_coordinates(
    edges: list[dict[str, Any]],
    positions: dict[str, tuple[float, float]],
) -> dict[str, list[list[float]]]:
    xs: list[list[float]] = []
    ys: list[list[float]] = []
    for edge in edges:
        source = str(edge["source"])
        target = str(edge["target"])
        if source not in positions or target not in positions:
            continue
        left = positions[source]
        right = positions[target]
        xs.append([left[0], right[0]])
        ys.append([left[1], right[1]])
    return {"xs": xs, "ys": ys}


def _status_legend_html() -> str:
    entries = "".join(
        f'<span style="display:inline-block;margin-right:14px;">'
        f'<span style="display:inline-block;width:12px;height:12px;'
        f'background:{color};margin-right:5px;"></span>{status}</span>'
        for status, color in STATUS_COLORS.items()
        if status != "aggregate"
    )
    return f"<h3>Agent state legend</h3><p>{entries}</p>"
