"""Generate a self-contained offline Virtual Fleet Assurance Console."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from plotly.offline.offline import get_plotlyjs


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_config(bundle: Path) -> dict[str, Any]:
    json_path = bundle / "config.json"
    yaml_path = bundle / "config.yaml"
    if json_path.exists():
        value = _load_json(json_path)
    elif yaml_path.exists():
        value = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    else:
        raise FileNotFoundError("replay bundle contains neither config.json nor config.yaml")
    if not isinstance(value, dict):
        raise ValueError("configuration root must be a mapping")
    return value


def _load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"event line {line_number} is not an object")
            events.append(value)
    if not events:
        raise ValueError("replay bundle contains no events")
    return events


def build_console(bundle_dir: str | Path, output_path: str | Path | None = None) -> Path:
    """Build one offline HTML replay application from a deterministic replay bundle."""

    bundle = Path(bundle_dir)
    destination = Path(output_path) if output_path else bundle / "virtual_fleet_assurance_console.html"
    required = ["events.jsonl", "summary.json", "graph_layers.json"]
    missing = [name for name in required if not (bundle / name).exists()]
    if missing:
        raise FileNotFoundError(f"replay bundle is missing required files: {', '.join(missing)}")

    payload = {
        "config": _load_config(bundle),
        "summary": _load_json(bundle / "summary.json"),
        "graph": _load_json(bundle / "graph_layers.json"),
        "events": _load_events(bundle / "events.jsonl"),
    }
    plotly_js = get_plotlyjs()
    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    html = _HTML_TEMPLATE.replace("__PLOTLY_JS__", plotly_js).replace(
        "__BUNDLE_JSON__", payload_json
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html, encoding="utf-8")
    return destination


_HTML_TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Virtual Fleet Assurance Console</title>
<style>
:root {
  --bg: #0b1020;
  --panel: #11182b;
  --panel2: #151f36;
  --text: #eef3ff;
  --muted: #9fb0cf;
  --line: #2b3a5d;
  --accent: #4fd1c5;
  --warning: #f6ad55;
  --critical: #fc8181;
  --ok: #68d391;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font-family: Arial, sans-serif; }
header { padding: 14px 20px; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; align-items: center; gap: 12px; }
h1 { font-size: 20px; margin: 0; }
.sub { color: var(--muted); font-size: 12px; margin-top: 5px; overflow-wrap: anywhere; }
.badge { border: 1px solid var(--accent); color: var(--accent); border-radius: 999px; padding: 5px 10px; font-size: 12px; white-space: nowrap; }
main { display: grid; grid-template-columns: minmax(620px, 1.7fr) minmax(360px, 1fr); gap: 12px; padding: 12px; }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
.panel h2 { margin: 0; padding: 11px 14px; font-size: 14px; border-bottom: 1px solid var(--line); background: var(--panel2); }
#fleetPlot { height: 620px; }
.side { display: grid; grid-template-rows: auto auto auto auto 1fr; gap: 12px; }
.cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; padding: 10px; }
.card { background: var(--panel2); border: 1px solid var(--line); border-radius: 8px; padding: 9px; min-height: 68px; }
.card .label { color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: .06em; }
.card .value { font-size: 18px; font-weight: 650; margin-top: 7px; overflow-wrap: anywhere; }
.controls { padding: 10px; display: grid; gap: 9px; }
.control-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
button, select { background: #1d2945; color: var(--text); border: 1px solid #40527a; border-radius: 6px; padding: 7px 10px; }
button:hover { border-color: var(--accent); }
input[type=range] { width: 100%; }
label { color: var(--muted); font-size: 12px; }
#eventText, #nodeText { padding: 10px 12px; min-height: 108px; max-height: 260px; overflow: auto; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; white-space: pre-wrap; overflow-wrap: anywhere; }
.plot { height: 285px; }
.bottom { grid-column: 1 / -1; }
.legend { padding: 8px 12px; color: var(--muted); font-size: 11px; border-top: 1px solid var(--line); }
.dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 4px; margin-left: 10px; }
.status-ok { color: var(--ok); }
.status-warning { color: var(--warning); }
.status-critical { color: var(--critical); }
.small { font-size: 11px; color: var(--muted); }
@media (max-width: 1080px) { main { grid-template-columns: 1fr; } .bottom { grid-column: 1; } }
</style>
<script>__PLOTLY_JS__</script>
</head>
<body>
<header>
  <div><h1>Virtual Fleet Assurance Console</h1><div class="sub" id="runMeta"></div></div>
  <div class="badge" id="representationBadge">Replay representation</div>
</header>
<main>
  <section class="panel">
    <h2>Fleet topology and dynamic event state</h2>
    <div id="fleetPlot"></div>
    <div class="legend">
      Graph layers:
      <span class="dot" style="background:#4fd1c5"></span>Communication
      <span class="dot" style="background:#b794f4"></span>Authorization
      <span class="dot" style="background:#fc8181"></span>Current causal edge
      <span class="small">Select an agent for state details.</span>
    </div>
  </section>
  <aside class="side">
    <section class="panel">
      <h2>Assurance indicators</h2>
      <div class="cards">
        <div class="card"><div class="label">Simulation time</div><div class="value" id="metricTime">0.0 s</div></div>
        <div class="card"><div class="label">Event</div><div class="value" id="metricEvent">0</div></div>
        <div class="card"><div class="label">Authorization queue</div><div class="value" id="metricQueue">0</div></div>
        <div class="card"><div class="label">Useful tasks</div><div class="value" id="metricUseful">0</div></div>
        <div class="card"><div class="label">Active compromise</div><div class="value" id="metricCompromised">0</div></div>
        <div class="card"><div class="label">Gossip coverage</div><div class="value" id="metricCoverage">0%</div></div>
        <div class="card"><div class="label">Revoked agents</div><div class="value" id="metricRevoked">0</div></div>
        <div class="card"><div class="label">Max clock uncertainty</div><div class="value" id="metricTiming">0 s</div></div>
        <div class="card"><div class="label">Credential storm</div><div class="value" id="metricStorm">inactive</div></div>
      </div>
    </section>
    <section class="panel">
      <h2>Replay controls</h2>
      <div class="controls">
        <div class="control-row">
          <button id="firstButton">First</button><button id="backButton">Back</button><button id="playButton">Play</button><button id="pauseButton">Pause</button><button id="stepButton">Step</button><button id="lastButton">Last</button>
          <label>Rate <select id="speedSelect"><option value="2">2 events/s</option><option value="10" selected>10 events/s</option><option value="50">50 events/s</option><option value="200">200 events/s</option></select></label>
        </div>
        <input id="timeline" type="range" min="0" max="0" value="0" step="1">
        <div class="control-row">
          <label><input id="toggleCommunication" type="checkbox" checked> Communication graph</label>
          <label><input id="toggleAuthorization" type="checkbox" checked> Authorization graph</label>
        </div>
      </div>
    </section>
    <section class="panel"><h2>Current event</h2><div id="eventText"></div></section>
    <section class="panel"><h2>Selected node</h2><div id="nodeText">Select an agent in the topology view.</div></section>
    <section class="panel"><h2>Execution integrity</h2><div id="integrityText" style="padding:12px;font-size:12px;line-height:1.55"></div></section>
  </aside>
  <section class="panel bottom"><h2>Authorization control-plane queue</h2><div id="queuePlot" class="plot"></div></section>
  <section class="panel bottom"><h2>Security containment timeline</h2><div id="securityPlot" class="plot"></div></section>
  <section class="panel bottom"><h2>Timing assurance degradation</h2><div id="timingPlot" class="plot"></div></section>
  <section class="panel bottom"><h2>Credential operations</h2><div id="credentialPlot" class="plot"></div></section>
</main>
<script>
const BUNDLE = __BUNDLE_JSON__;
const events = BUNDLE.events;
const nodes = BUNDLE.graph.nodes;
const nodeLookup = Object.fromEntries(nodes.map((node, index) => [node.id, index]));
const timeline = document.getElementById('timeline');
timeline.max = Math.max(0, events.length - 1);
let currentIndex = 0;
let timer = null;
let state;
let selectedNodeId = null;

const statusColors = {
  idle: '#90cdf4', working: '#f6e05e', compromised: '#fc8181', suspected: '#f6ad55',
  isolated: '#b794f4', revoked: '#718096', terminated: '#1a202c', recovered: '#68d391'
};

function layerEdges(layerName) {
  const layer = BUNDLE.graph.layers[layerName] || {};
  return Array.isArray(layer) ? layer : (layer.edges || []);
}

function resetState() {
  state = {
    agents: Object.fromEntries(nodes.map(n => [n.id, {health:'idle', informed:false, timing:0, credentialEpoch:0, currentTask:null}])),
    queue: 0, utilization: 0, useful: 0, tasksCompleted: 0,
    activeCompromise: 0, gossipCoverage: 0, revoked: 0,
    timingDenial: false, credentialStorm: false, lastEvent: null
  };
}

function applyEvent(event) {
  const target = event.destination_id;
  const source = event.source_id;
  if (event.event_type === 'TASK_DISPATCH' && state.agents[target]) {
    state.agents[target].health = 'working';
    state.agents[target].currentTask = event.task_id;
  }
  if (event.event_type === 'TASK_COMPLETE') {
    if (state.agents[source] && state.agents[source].health === 'working') state.agents[source].health = 'idle';
    if (state.agents[source]) state.agents[source].currentTask = null;
    state.tasksCompleted += 1;
    if (event.metadata && event.metadata.useful) state.useful += 1;
  }
  if (event.event_type === 'TASK_FAILED') {
    const agent = state.agents[source] || state.agents[target];
    if (agent && agent.health === 'working') agent.health = 'idle';
    if (agent) agent.currentTask = null;
  }
  if (event.event_type === 'GOSSIP_SEED' && state.agents[target]) state.agents[target].informed = true;
  if (event.event_type === 'GOSSIP_INFORMED' && state.agents[target]) state.agents[target].informed = true;
  if (event.event_type === 'GOSSIP_ROUND' && event.metadata) state.gossipCoverage = Number(event.metadata.coverage || 0);
  if (event.event_type === 'COMPROMISE' && state.agents[target]) state.agents[target].health = 'compromised';
  if (event.event_type === 'DETECTION' && state.agents[target]) state.agents[target].health = 'suspected';
  if (event.event_type === 'QUARANTINE' && state.agents[target]) state.agents[target].health = 'isolated';
  if (event.event_type === 'REVOCATION' && state.agents[target]) {
    state.agents[target].health = 'revoked';
    if (event.credential_epoch !== null && event.credential_epoch !== undefined) state.agents[target].credentialEpoch = Number(event.credential_epoch);
  }
  if (event.event_type === 'CREDENTIAL_RENEWAL' && state.agents[target] && event.credential_epoch !== null && event.credential_epoch !== undefined) {
    state.agents[target].credentialEpoch = Number(event.credential_epoch);
  }
  if (event.event_type === 'RECOVERY' && state.agents[target]) state.agents[target].health = 'recovered';
  if (event.event_type === 'TIMING_DENIAL_START') state.timingDenial = true;
  if (event.event_type === 'TIMING_UPDATE' && state.agents[target]) state.agents[target].timing = Number(event.timing_uncertainty || 0);
  if (event.event_type === 'QUEUE_SAMPLE' && event.metadata) {
    state.queue = Number(event.metadata.queue_length || 0);
    state.utilization = Number(event.metadata.utilization || 0);
  }
  if (event.event_type === 'SECURITY_ROUND' && event.metadata) state.activeCompromise = Number(event.metadata.active_compromised || 0);
  if (event.event_type === 'CREDENTIAL_REVOCATION_STORM_START') state.credentialStorm = true;
  state.revoked = Object.values(state.agents).filter(agent => agent.health === 'revoked').length;
  state.lastEvent = event;
}

function replayTo(index) {
  resetState();
  const target = Math.max(0, Math.min(index, events.length - 1));
  for (let i = 0; i <= target; i++) applyEvent(events[i]);
  currentIndex = target;
  timeline.value = target;
  render();
}

function edgeTrace(layerName, color, width) {
  const x = [], y = [];
  for (const edge of layerEdges(layerName)) {
    const left = Array.isArray(edge) ? edge[0] : edge.source;
    const right = Array.isArray(edge) ? edge[1] : edge.target;
    if (nodeLookup[left] === undefined || nodeLookup[right] === undefined) continue;
    const a = nodes[nodeLookup[left]], b = nodes[nodeLookup[right]];
    x.push(a.x, b.x, null); y.push(a.y, b.y, null);
  }
  return {type:(nodes.length <= 1000 ? 'scatter' : 'scattergl'), mode:'lines', x, y, hoverinfo:'skip', line:{color, width}, name:layerName};
}

function renderNodeDetail() {
  if (!selectedNodeId || !state.agents[selectedNodeId]) return;
  const node = nodes[nodeLookup[selectedNodeId]];
  const runtime = state.agents[selectedNodeId];
  document.getElementById('nodeText').textContent = JSON.stringify({
    id: selectedNodeId,
    status: runtime.health,
    informed: runtime.informed,
    current_task: runtime.currentTask,
    credential_epoch: runtime.credentialEpoch,
    timing_uncertainty_s: runtime.timing,
    partition: node.partition,
    supervisor_id: node.supervisor_id,
    communication_topology: BUNDLE.graph.layers.communication.topology,
    authorization_topology: BUNDLE.graph.layers.authorization.topology
  }, null, 2);
}

function render() {
  const event = state.lastEvent || events[0];
  const traces = [];
  if (document.getElementById('toggleCommunication').checked) traces.push(edgeTrace('communication', 'rgba(79,209,197,0.20)', 1));
  if (document.getElementById('toggleAuthorization').checked) traces.push(edgeTrace('authorization', 'rgba(183,148,244,0.34)', 1.5));
  if (event && nodeLookup[event.source_id] !== undefined && nodeLookup[event.destination_id] !== undefined) {
    const a = nodes[nodeLookup[event.source_id]], b = nodes[nodeLookup[event.destination_id]];
    traces.push({type:(nodes.length <= 1000 ? 'scatter' : 'scattergl'), mode:'lines', x:[a.x,b.x], y:[a.y,b.y], hoverinfo:'skip', line:{color:'#fc8181',width:4}, name:'current event'});
  }
  const colors = nodes.map(n => statusColors[state.agents[n.id].health] || statusColors.idle);
  const sizes = nodes.map(n => state.agents[n.id].informed ? 13 : 9);
  const symbols = nodes.map(n => state.agents[n.id].informed ? 'circle' : 'circle-open');
  const hover = nodes.map(n => `${n.id}<br>health=${state.agents[n.id].health}<br>informed=${state.agents[n.id].informed}<br>credential epoch=${state.agents[n.id].credentialEpoch}<br>clock uncertainty=${state.agents[n.id].timing.toExponential(3)} s`);
  traces.push({type:(nodes.length <= 1000 ? 'scatter' : 'scattergl'), mode:'markers', x:nodes.map(n=>n.x), y:nodes.map(n=>n.y), text:hover, customdata:nodes.map(n=>n.id), hoverinfo:'text', marker:{color:colors,size:sizes,symbol:symbols,line:{color:'#e2e8f0',width:0.5}}, name:'agents'});
  Plotly.react('fleetPlot', traces, {
    paper_bgcolor:'#11182b', plot_bgcolor:'#11182b', font:{color:'#eef3ff'},
    margin:{l:10,r:10,t:10,b:10}, showlegend:false,
    xaxis:{visible:false, fixedrange:false}, yaxis:{visible:false, fixedrange:false, scaleanchor:'x', scaleratio:1},
    dragmode:'pan'
  }, {displayModeBar:true, responsive:true, scrollZoom:true});

  const maxTiming = Math.max(0, ...Object.values(state.agents).map(agent => Number(agent.timing || 0)));
  document.getElementById('metricTime').textContent = `${Number(event.simulation_time || 0).toFixed(2)} s`;
  document.getElementById('metricEvent').textContent = `${currentIndex + 1}/${events.length}`;
  document.getElementById('metricQueue').textContent = `${state.queue} (${Math.round(state.utilization*100)}%)`;
  document.getElementById('metricUseful').textContent = String(state.useful);
  document.getElementById('metricCompromised').textContent = String(state.activeCompromise);
  document.getElementById('metricCoverage').textContent = `${Math.round(state.gossipCoverage*100)}%`;
  document.getElementById('metricRevoked').textContent = String(state.revoked);
  document.getElementById('metricTiming').textContent = `${maxTiming.toExponential(2)} s`;
  document.getElementById('metricStorm').textContent = state.credentialStorm ? 'active or completed' : 'inactive';
  document.getElementById('eventText').textContent = JSON.stringify(event, null, 2);
  renderNodeDetail();
}

function commonLayout(xTitle, yTitle) {
  return {
    paper_bgcolor:'#11182b', plot_bgcolor:'#11182b', font:{color:'#eef3ff'}, margin:{l:65,r:55,t:20,b:50},
    xaxis:{title:xTitle,gridcolor:'#2b3a5d'}, yaxis:{title:yTitle,gridcolor:'#2b3a5d'}, legend:{orientation:'h'}
  };
}

function buildStaticPlots() {
  const queueEvents = events.filter(e => e.event_type === 'QUEUE_SAMPLE');
  const queueLayout = commonLayout('Simulation time, s', 'Queue length');
  queueLayout.yaxis2 = {title:'Utilization, %',overlaying:'y',side:'right',range:[0,105],gridcolor:'#2b3a5d'};
  Plotly.newPlot('queuePlot', [{
    x: queueEvents.map(e => e.simulation_time), y: queueEvents.map(e => e.metadata.queue_length),
    type:'scatter', mode:'lines', name:'queue length'
  },{
    x: queueEvents.map(e => e.simulation_time), y: queueEvents.map(e => 100*e.metadata.utilization),
    type:'scatter', mode:'lines', name:'utilization percent', yaxis:'y2'
  }], queueLayout, {displayModeBar:false,responsive:true});

  const securityEvents = events.filter(e => e.event_type === 'SECURITY_ROUND');
  Plotly.newPlot('securityPlot', [{
    x: securityEvents.map(e => e.simulation_time), y: securityEvents.map(e => e.metadata.active_compromised), type:'scatter', mode:'lines+markers', name:'active compromised'
  },{
    x: securityEvents.map(e => e.simulation_time), y: securityEvents.map(e => e.metadata.removed), type:'scatter', mode:'lines+markers', name:'contained or removed'
  },{
    x: securityEvents.map(e => e.simulation_time), y: securityEvents.map(e => e.metadata.new_compromises), type:'bar', name:'new compromises'
  }], commonLayout('Simulation time, s', 'Agents'), {displayModeBar:false,responsive:true});

  const timingEvents = events.filter(e => e.event_type === 'TIMING_UPDATE');
  const timingByTime = {};
  for (const event of timingEvents) timingByTime[String(event.simulation_time)] = Number(event.timing_uncertainty || 0);
  const timingTimes = Object.keys(timingByTime).map(Number).sort((a,b)=>a-b);
  Plotly.newPlot('timingPlot', [{
    x: timingTimes, y: timingTimes.map(t => timingByTime[String(t)]), type:'scatter', mode:'lines+markers', name:'maximum node uncertainty'
  }], {...commonLayout('Simulation time, s', 'Clock uncertainty, s'), yaxis:{title:'Clock uncertainty, s',type:'log',gridcolor:'#2b3a5d'}}, {displayModeBar:false,responsive:true});

  const credentialEvents = events.filter(e => ['CREDENTIAL_REVOCATION_STORM_START','REVOCATION','CREDENTIAL_RENEWAL'].includes(e.event_type));
  let revocations = 0, renewals = 0;
  const x = [], rev = [], ren = [];
  for (const event of credentialEvents) {
    if (event.event_type === 'REVOCATION') revocations += 1;
    if (event.event_type === 'CREDENTIAL_RENEWAL') renewals += 1;
    x.push(event.simulation_time); rev.push(revocations); ren.push(renewals);
  }
  Plotly.newPlot('credentialPlot', [{x,y:rev,type:'scatter',mode:'lines+markers',name:'cumulative revocations'}, {x,y:ren,type:'scatter',mode:'lines+markers',name:'cumulative renewals'}], commonLayout('Simulation time, s','Credential operations'), {displayModeBar:false,responsive:true});
}

function startPlayback() {
  if (timer) return;
  const rate = Number(document.getElementById('speedSelect').value);
  timer = setInterval(() => {
    if (currentIndex >= events.length - 1) { stopPlayback(); return; }
    replayTo(currentIndex + 1);
  }, Math.max(5, 1000/rate));
}
function stopPlayback() { if (timer) clearInterval(timer); timer = null; }

document.getElementById('playButton').onclick = startPlayback;
document.getElementById('pauseButton').onclick = stopPlayback;
document.getElementById('stepButton').onclick = () => replayTo(currentIndex + 1);
document.getElementById('backButton').onclick = () => replayTo(currentIndex - 1);
document.getElementById('firstButton').onclick = () => replayTo(0);
document.getElementById('lastButton').onclick = () => replayTo(events.length - 1);
timeline.oninput = () => { stopPlayback(); replayTo(Number(timeline.value)); };
document.getElementById('toggleCommunication').onchange = render;
document.getElementById('toggleAuthorization').onchange = render;
document.getElementById('speedSelect').onchange = () => { if (timer) { stopPlayback(); startPlayback(); } };
const representation = BUNDLE.graph.representation || 'exact';
document.getElementById('representationBadge').textContent = `${representation} visual representation`;
document.getElementById('runMeta').textContent = `Run ${BUNDLE.summary.run_id} | N=${BUNDLE.summary.n_agents} | seed=${BUNDLE.summary.seed} | config ${BUNDLE.summary.configuration_hash.slice(0,16)}`;
const replayValidation = BUNDLE.summary.replay_validation || {};
const replayStatus = replayValidation.passed ? '<span class="status-ok">passed</span>' : '<span class="status-critical">not established</span>';
document.getElementById('integrityText').innerHTML = `
  <span class="status-ok">Replay source:</span> append-only canonical event log<br>
  <span class="status-ok">Replay equivalence:</span> ${replayStatus}<br>
  <span class="status-ok">Event digest:</span> ${BUNDLE.summary.event_log_digest.slice(0,24)}...<br>
  <span class="status-ok">Final state hash:</span> ${BUNDLE.summary.final_state_hash.slice(0,24)}...<br>
  <span class="status-warning">Evidence class:</span> ${BUNDLE.summary.evidence_class}<br>
  <span class="status-warning">Parameter class:</span> ${BUNDLE.summary.parameter_class}<br>
  This display reconstructs the modeled run. It is not a validated digital twin and does not establish production assurance.`;
resetState();
buildStaticPlots();
replayTo(0);
document.getElementById('fleetPlot').on('plotly_click', data => {
  const point = data.points.find(item => item.customdata);
  if (point) { selectedNodeId = point.customdata; renderNodeDetail(); }
});
</script>
</body>
</html>'''
