"""Bokeh server application for the Virtual Fleet Assurance Console."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from bokeh.layouts import column, row
from bokeh.models import (
    Button,
    CheckboxGroup,
    ColumnDataSource,
    DataTable,
    Div,
    HoverTool,
    NumberFormatter,
    Select,
    Slider,
    Spinner,
    TableColumn,
    Toggle,
)
from bokeh.plotting import curdoc, figure

from fleet_sim.config import SimulationConfig
from fleet_sim.experiments import FleetSimulator
from fleet_sim.model.state import FleetState
from fleet_sim.visualization.bundle import ReplayBundle, discover_bundles, load_replay_bundle
from fleet_sim.visualization.export_plotly import STATE_COLORS, export_replay_html


REPOSITORY_ROOT = Path(os.environ.get("FLEET_SIM_ROOT", Path(__file__).resolve().parents[3]))
MAX_RENDERED_EDGES = 5_000


def _bundle_options() -> list[tuple[str, str]]:
    return [(str(path), path.name) for path in discover_bundles(REPOSITORY_ROOT)]


def _edge_lines(bundle: ReplayBundle, layer: str) -> tuple[list[list[float]], list[list[float]], str]:
    nodes = {node["id"]: node for node in bundle.graph_layers["nodes"]}
    edges = bundle.graph_layers["layers"][layer].get("edges", [])
    representation = bundle.graph_layers["layers"][layer].get("representation", "exact")
    if len(edges) > MAX_RENDERED_EDGES:
        stride = max(1, len(edges) // MAX_RENDERED_EDGES)
        edges = edges[::stride][:MAX_RENDERED_EDGES]
        representation = "sampled"
    xs: list[list[float]] = []
    ys: list[list[float]] = []
    for source, target in edges:
        if source in nodes and target in nodes:
            xs.append([nodes[source]["x"], nodes[target]["x"]])
            ys.append([nodes[source]["y"], nodes[target]["y"]])
    return xs, ys, representation


def _state_at(bundle: ReplayBundle, event_index: int) -> FleetState:
    event_index = max(0, min(event_index, len(bundle.events.events)))
    snapshot = None
    for candidate in bundle.snapshots:
        if candidate.event_index <= event_index:
            snapshot = candidate
        else:
            break
    if snapshot is None:
        state = FleetState.from_dict(bundle.initial_state.to_dict())
        start = 0
    else:
        state = FleetState.from_dict(snapshot.state)
        start = snapshot.event_index
    for event in bundle.events.events[start:event_index]:
        state.apply(event)
    return state


def _node_data(bundle: ReplayBundle, state: FleetState) -> dict[str, list[Any]]:
    output: dict[str, list[Any]] = {
        "x": [],
        "y": [],
        "agent_id": [],
        "health": [],
        "color": [],
        "partition": [],
        "supervisor": [],
        "credential_epoch": [],
        "timing_uncertainty": [],
        "task": [],
        "informed": [],
    }
    for node in bundle.graph_layers["nodes"]:
        agent_id = node["id"]
        agent = state.agents[agent_id]
        output["x"].append(node["x"])
        output["y"].append(node["y"])
        output["agent_id"].append(agent_id)
        output["health"].append(agent.health.value)
        output["color"].append(STATE_COLORS[agent.health.value])
        output["partition"].append(agent.partition)
        output["supervisor"].append(agent.supervisor_id or "root")
        output["credential_epoch"].append(agent.credential_epoch)
        output["timing_uncertainty"].append(agent.timing_uncertainty_s)
        output["task"].append(agent.current_task_id or "none")
        output["informed"].append(agent.informed)
    return output


def _summary_html(bundle: ReplayBundle, state: FleetState, event_index: int) -> str:
    event = bundle.events.events[event_index - 1] if event_index > 0 else None
    compromised = sum(
        agent.health.value in {"compromised", "suspected"}
        for agent in state.agents.values()
    )
    isolated = sum(agent.health.value in {"isolated", "revoked"} for agent in state.agents.values())
    queue = state.queues.get("authorization", 0)
    useful = int(state.counters.get("useful_tasks_completed", 0))
    event_text = (
        f"{event.event_type} at {event.simulation_time:.3f} s" if event is not None else "Initial state"
    )
    return (
        f"<b>Run:</b> {bundle.run_id}<br>"
        f"<b>Representation:</b> {bundle.graph_layers.get('representation', 'exact')}<br>"
        f"<b>Event:</b> {event_index}/{len(bundle.events.events)} | {event_text}<br>"
        f"<b>Compromised or suspected:</b> {compromised} | "
        f"<b>Isolated or revoked:</b> {isolated}<br>"
        f"<b>Authorization queue:</b> {queue} | <b>Useful completions:</b> {useful}<br>"
        f"<b>Configuration:</b> {bundle.summary['configuration_hash']} | "
        f"<b>Seed:</b> {bundle.configuration['seed']} | "
        f"<b>Parameter class:</b> {bundle.summary['parameter_class']}"
    )


def _comparison_html(primary: ReplayBundle, secondary: ReplayBundle | None) -> str:
    if secondary is None:
        return "Select a comparison run."
    p = primary.summary
    s = secondary.summary
    rows = [
        ("N", p["n_agents"], s["n_agents"]),
        ("Useful throughput, Hz", p["tasks"]["useful_throughput_hz"], s["tasks"]["useful_throughput_hz"]),
        ("p95 latency, s", p["tasks"]["latency_s"]["p95"], s["tasks"]["latency_s"]["p95"]),
        ("Control utilization", p["control_plane"]["observed_utilization"], s["control_plane"]["observed_utilization"]),
        ("Blast radius fraction", p["security"]["blast_radius_fraction"], s["security"]["blast_radius_fraction"]),
        ("Authorization spectral radius", p["security"]["authorization_spectral_radius"], s["security"]["authorization_spectral_radius"]),
        ("Event count", p["event_count"], s["event_count"]),
    ]
    body = "".join(
        f"<tr><td>{name}</td><td>{left}</td><td>{right}</td></tr>" for name, left, right in rows
    )
    return (
        "<table style='width:100%;border-collapse:collapse'>"
        "<tr><th>Metric</th><th>Primary</th><th>Comparison</th></tr>"
        f"{body}</table>"
    )


options = _bundle_options()
if not options:
    raise RuntimeError(
        f"No replay bundles found under {REPOSITORY_ROOT / 'replay_bundles'}. Run fleet-sim first."
    )

initial_path = Path(options[0][0])
current_bundle = load_replay_bundle(initial_path)
comparison_bundle: ReplayBundle | None = None
current_state = FleetState.from_dict(current_bundle.initial_state.to_dict())

node_source = ColumnDataSource(_node_data(current_bundle, current_state))
communication_x, communication_y, communication_representation = _edge_lines(current_bundle, "communication")
authorization_x, authorization_y, authorization_representation = _edge_lines(current_bundle, "authorization")
communication_source = ColumnDataSource({"xs": communication_x, "ys": communication_y})
authorization_source = ColumnDataSource({"xs": authorization_x, "ys": authorization_y})

plot = figure(
    height=680,
    sizing_mode="stretch_both",
    tools="pan,wheel_zoom,box_zoom,reset,tap,save",
    active_scroll="wheel_zoom",
    title="Virtual Fleet Assurance Console",
)
communication_renderer = plot.multi_line(
    xs="xs", ys="ys", source=communication_source, line_alpha=0.25, line_width=0.6,
    legend_label=f"Communication, {communication_representation}",
)
authorization_renderer = plot.multi_line(
    xs="xs", ys="ys", source=authorization_source, line_alpha=0.55, line_width=1.2,
    legend_label=f"Authorization, {authorization_representation}",
)
node_renderer = plot.scatter(
    x="x",
    y="y",
    source=node_source,
    size=10,
    fill_color="color",
    line_color="white",
    line_width=0.5,
    legend_label="Agents",
)
plot.add_tools(
    HoverTool(
        renderers=[node_renderer],
        tooltips=[
            ("Agent", "@agent_id"),
            ("Health", "@health"),
            ("Partition", "@partition"),
            ("Supervisor", "@supervisor"),
            ("Credential epoch", "@credential_epoch"),
            ("Clock uncertainty", "@timing_uncertainty{0.000000000}"),
            ("Task", "@task"),
            ("Gossip informed", "@informed"),
        ],
    )
)
plot.axis.visible = False
plot.grid.visible = False
plot.legend.click_policy = "hide"

mode_select = Select(
    title="Mode",
    value="Replay",
    options=["Replay", "Comparison", "Scenario", "Live"],
)
bundle_select = Select(title="Primary replay bundle", value=str(initial_path), options=options)
comparison_select = Select(title="Comparison bundle", value="", options=[("", "None"), *options])
layer_select = CheckboxGroup(labels=["Communication graph", "Authorization graph"], active=[0, 1])
event_slider = Slider(
    title="Event index",
    start=0,
    end=len(current_bundle.events.events),
    value=0,
    step=1,
    sizing_mode="stretch_width",
)
play_toggle = Toggle(label="Play", active=False, button_type="success")
step_back = Button(label="Previous event")
step_forward = Button(label="Next event")
speed_slider = Slider(title="Playback interval, ms", start=50, end=1000, value=150, step=50)
summary_div = Div(text=_summary_html(current_bundle, current_state, 0), sizing_mode="stretch_width")
comparison_div = Div(text="Select a comparison run.", sizing_mode="stretch_width")
node_detail = Div(text="Select an agent to inspect its replay state.", sizing_mode="stretch_width")
status_div = Div(
    text=(
        "Stage 0 console. Replay is deterministic. Scenario mode creates a new immutable run. "
        "Live mode currently executes the run first, then autoplays its captured events. "
        "Streaming during model execution remains an open implementation item."
    ),
    sizing_mode="stretch_width",
)

recent_source = ColumnDataSource({"time": [], "type": [], "source": [], "destination": [], "severity": []})
recent_table = DataTable(
    source=recent_source,
    columns=[
        TableColumn(field="time", title="Time", formatter=NumberFormatter(format="0.000")),
        TableColumn(field="type", title="Event"),
        TableColumn(field="source", title="Source"),
        TableColumn(field="destination", title="Destination"),
        TableColumn(field="severity", title="Severity"),
    ],
    height=240,
    sizing_mode="stretch_width",
    index_position=None,
)

scenario_n = Spinner(title="N", low=1, high=1000, step=1, value=64)
scenario_comm = Select(
    title="Communication topology",
    value="random_regular",
    options=["complete", "random_regular", "erdos_renyi", "barabasi_albert", "hierarchical"],
)
scenario_auth = Select(
    title="Authorization topology",
    value="hierarchical",
    options=["complete", "random_regular", "erdos_renyi", "barabasi_albert", "hierarchical"],
)
scenario_segmentation = Select(
    title="Segmentation policy",
    value="dynamic_microsegmentation",
    options=["none", "flat_tenancy", "partition", "dynamic_microsegmentation", "degree_cap"],
)
scenario_seed = Spinner(title="Seed", low=0, high=2**31 - 1, step=1, value=20260819)
run_scenario = Button(label="Execute immutable scenario", button_type="primary")
export_html_button = Button(label="Export self-contained replay HTML")
scenario_panel = column(
    Div(text="<b>Scenario controls</b>"),
    row(scenario_n, scenario_seed),
    scenario_comm,
    scenario_auth,
    scenario_segmentation,
    run_scenario,
    export_html_button,
    visible=False,
)

periodic_callback_id = None


def update_event_view(event_index: int) -> None:
    global current_state
    current_state = _state_at(current_bundle, event_index)
    node_source.data = _node_data(current_bundle, current_state)
    summary_div.text = _summary_html(current_bundle, current_state, event_index)
    start = max(0, event_index - 20)
    recent = current_bundle.events.events[start:event_index]
    recent_source.data = {
        "time": [event.simulation_time for event in recent],
        "type": [event.event_type for event in recent],
        "source": [event.source_id or "" for event in recent],
        "destination": [event.destination_id or "" for event in recent],
        "severity": [event.severity for event in recent],
    }
    if event_index > 0:
        event = current_bundle.events.events[event_index - 1]
        plot.title.text = f"{current_bundle.run_id} | t={event.simulation_time:.3f} s | {event.event_type}"
    else:
        plot.title.text = f"{current_bundle.run_id} | initial state"


def load_primary(path_value: str) -> None:
    global current_bundle
    current_bundle = load_replay_bundle(path_value)
    event_slider.end = len(current_bundle.events.events)
    event_slider.value = 0
    communication_x, communication_y, comm_repr = _edge_lines(current_bundle, "communication")
    authorization_x, authorization_y, auth_repr = _edge_lines(current_bundle, "authorization")
    communication_source.data = {"xs": communication_x, "ys": communication_y}
    authorization_source.data = {"xs": authorization_x, "ys": authorization_y}
    communication_renderer.legend_label = f"Communication, {comm_repr}"
    authorization_renderer.legend_label = f"Authorization, {auth_repr}"
    update_event_view(0)
    comparison_div.text = _comparison_html(current_bundle, comparison_bundle)


def bundle_changed(attr: str, old: str, new: str) -> None:
    load_primary(new)


def comparison_changed(attr: str, old: str, new: str) -> None:
    global comparison_bundle
    comparison_bundle = load_replay_bundle(new) if new else None
    comparison_div.text = _comparison_html(current_bundle, comparison_bundle)


def slider_changed(attr: str, old: float, new: float) -> None:
    update_event_view(int(new))


def layer_changed(attr: str, old: list[int], new: list[int]) -> None:
    communication_renderer.visible = 0 in new
    authorization_renderer.visible = 1 in new


def previous_event() -> None:
    event_slider.value = max(0, event_slider.value - 1)


def next_event() -> None:
    if event_slider.value >= event_slider.end:
        play_toggle.active = False
        return
    event_slider.value += 1


def periodic_step() -> None:
    next_event()


def play_changed(active: bool) -> None:
    global periodic_callback_id
    if active and periodic_callback_id is None:
        play_toggle.label = "Pause"
        periodic_callback_id = curdoc().add_periodic_callback(periodic_step, speed_slider.value)
    elif not active and periodic_callback_id is not None:
        curdoc().remove_periodic_callback(periodic_callback_id)
        periodic_callback_id = None
        play_toggle.label = "Play"


def speed_changed(attr: str, old: float, new: float) -> None:
    if play_toggle.active:
        play_changed(False)
        play_changed(True)


def mode_changed(attr: str, old: str, new: str) -> None:
    scenario_panel.visible = new in {"Scenario", "Live"}
    comparison_select.visible = new == "Comparison"
    comparison_div.visible = new == "Comparison"


def selection_changed(attr: str, old: list[int], new: list[int]) -> None:
    if not new:
        node_detail.text = "Select an agent to inspect its replay state."
        return
    index = new[0]
    data = node_source.data
    node_detail.text = (
        f"<b>{data['agent_id'][index]}</b><br>"
        f"Health: {data['health'][index]}<br>"
        f"Partition: {data['partition'][index]}<br>"
        f"Supervisor: {data['supervisor'][index]}<br>"
        f"Credential epoch: {data['credential_epoch'][index]}<br>"
        f"Clock uncertainty: {data['timing_uncertainty'][index]:.9g} s<br>"
        f"Current task: {data['task'][index]}<br>"
        f"Gossip informed: {data['informed'][index]}"
    )


def execute_scenario() -> None:
    status_div.text = "Executing scenario with notional parameters..."
    try:
        duration = 30.0
        config = replace(
            SimulationConfig(),
            scenario_name=f"console-{mode_select.value.lower()}-{int(scenario_n.value)}",
            seed=int(scenario_seed.value),
            n_agents=int(scenario_n.value),
            duration_s=duration,
            communication_topology=scenario_comm.value,
            authorization_topology=scenario_auth.value,
            segmentation_policy=scenario_segmentation.value,
            gossip_start_s=2.0,
            attack_start_s=8.0,
            timing_denial_start_s=18.0,
            mass_revocation_start_s=24.0,
            trace_level="full" if int(scenario_n.value) <= 250 else "security",
            tags=("console", "stage0"),
        )
        artifacts = FleetSimulator(config, REPOSITORY_ROOT).run(REPOSITORY_ROOT)
        replay_path = export_replay_html(artifacts.bundle_dir)
        refreshed = _bundle_options()
        bundle_select.options = refreshed
        comparison_select.options = [("", "None"), *refreshed]
        bundle_select.value = str(artifacts.bundle_dir)
        status_div.text = (
            f"Scenario complete. Run {artifacts.run_id}. Replay state hash matched. "
            f"Self-contained replay: {replay_path}."
        )
        if mode_select.value == "Live":
            event_slider.value = 0
            play_toggle.active = True
    except Exception as exc:  # Bokeh must surface failures instead of swallowing them.
        status_div.text = f"Scenario failed: {type(exc).__name__}: {exc}"


def export_current_html() -> None:
    try:
        path = export_replay_html(current_bundle.path)
        status_div.text = f"Self-contained replay exported to {path}."
    except Exception as exc:
        status_div.text = f"Export failed: {type(exc).__name__}: {exc}"


bundle_select.on_change("value", bundle_changed)
comparison_select.on_change("value", comparison_changed)
event_slider.on_change("value", slider_changed)
layer_select.on_change("active", layer_changed)
step_back.on_click(previous_event)
step_forward.on_click(next_event)
play_toggle.on_click(play_changed)
speed_slider.on_change("value", speed_changed)
mode_select.on_change("value", mode_changed)
node_source.selected.on_change("indices", selection_changed)
run_scenario.on_click(execute_scenario)
export_html_button.on_click(export_current_html)

comparison_select.visible = False
comparison_div.visible = False

controls = column(
    Div(text="<h2>Virtual Fleet Assurance Console</h2>"),
    mode_select,
    bundle_select,
    comparison_select,
    layer_select,
    event_slider,
    row(step_back, play_toggle, step_forward),
    speed_slider,
    summary_div,
    comparison_div,
    node_detail,
    scenario_panel,
    status_div,
    recent_table,
    width=430,
    sizing_mode="stretch_height",
)
curdoc().add_root(row(controls, plot, sizing_mode="stretch_both"))
curdoc().title = "Virtual Fleet Assurance Console"
update_event_view(0)
