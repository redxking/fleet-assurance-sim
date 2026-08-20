(() => {
  "use strict";

  const PACK_URL = "data/scenario-pack.json";
  const MANIFEST_URL = "data/manifest.json";
  const EXPECTED_PACK_ID = "fleet-public-mvp-synthetic-v1";
  const EXPECTED_SCENARIO_IDS = new Set(
    [100, 1000, 10000].flatMap((fleetSize) =>
      ["linear", "step", "bursty"].flatMap((profile) =>
        ["constrained", "baseline", "expanded"].map(
          (capacity) => `n${String(fleetSize).padStart(5, "0")}-${profile}-capacity-${capacity}`,
        ),
      ),
    ),
  );

  const state = { pack: null, primaryId: null, comparisonId: null, compare: false };
  const byId = (id) => document.getElementById(id);

  function invariant(condition, message) {
    if (!condition) throw new Error(message);
  }

  function object(value, context) {
    invariant(value !== null && typeof value === "object" && !Array.isArray(value), `${context} must be an object`);
    return value;
  }

  function exactKeys(value, keys, context) {
    const selected = object(value, context);
    const actual = Object.keys(selected).sort();
    const expected = [...keys].sort();
    invariant(actual.length === expected.length && actual.every((key, index) => key === expected[index]), `${context} contains an unexpected or missing field`);
    return selected;
  }

  function text(value, context) {
    invariant(typeof value === "string" && value.trim().length > 0, `${context} must be nonempty text`);
    return value;
  }

  function finite(value, context, minimum = 0, maximum = Number.POSITIVE_INFINITY) {
    invariant(typeof value === "number" && Number.isFinite(value) && value >= minimum && value <= maximum, `${context} must be a finite number in range`);
    return value;
  }

  function integer(value, context, minimum = 0) {
    invariant(Number.isInteger(value) && value >= minimum, `${context} must be an integer in range`);
    return value;
  }

  function bool(value, expected, context) {
    invariant(typeof value === "boolean" && value === expected, `${context} must be ${String(expected)}`);
  }

  function oneOf(value, allowed, context) {
    invariant(allowed.includes(value), `${context} is outside the closed vocabulary`);
    return value;
  }

  function validateProfile(value, index) {
    const selected = exactKeys(value, ["id", "label", "description"], `design.admission_profiles[${index}]`);
    oneOf(selected.id, ["linear", "step", "bursty"], `admission profile ${index} id`);
    text(selected.label, `admission profile ${index} label`);
    text(selected.description, `admission profile ${index} description`);
  }

  function validateCapacity(value, index) {
    const selected = exactKeys(value, ["id", "label", "multiplier", "description"], `design.capacity_cases[${index}]`);
    oneOf(selected.id, ["constrained", "baseline", "expanded"], `capacity case ${index} id`);
    text(selected.label, `capacity case ${index} label`);
    oneOf(selected.multiplier, [.8, 1, 1.25], `capacity case ${index} multiplier`);
    text(selected.description, `capacity case ${index} description`);
  }

  function validateTimeseriesPoint(value, scenarioId, index, previousTime) {
    const selected = exactKeys(value, ["time_s", "planned_admissions", "admitted_agents", "pending_admissions", "observed_fleet_size", "projected_fleet_size", "projected_maximum_pressure", "observed_maximum_pressure"], `${scenarioId}.timeseries[${index}]`);
    finite(selected.time_s, `${scenarioId} time ${index}`);
    invariant(selected.time_s > previousTime, `${scenarioId} timeseries must be strictly ordered`);
    for (const key of ["planned_admissions", "admitted_agents", "pending_admissions", "observed_fleet_size", "projected_fleet_size"]) integer(selected[key], `${scenarioId} ${key}`);
    finite(selected.projected_maximum_pressure, `${scenarioId} projected pressure`);
    finite(selected.observed_maximum_pressure, `${scenarioId} observed pressure`);
    return selected.time_s;
  }

  function validateScenario(value, index, replications) {
    const keys = ["id", "name", "fleet_size", "initial_fleet_size", "profile", "profile_label", "capacity_case", "capacity_label", "capacity_multiplier", "architecture", "disturbance_fraction", "replications", "ex_ante_pressure", "operational_outcomes", "timeseries"];
    const selected = exactKeys(value, keys, `scenarios[${index}]`);
    invariant(EXPECTED_SCENARIO_IDS.has(selected.id), `scenario ${index} has an unregistered identity`);
    text(selected.name, `${selected.id} name`);
    oneOf(selected.fleet_size, [100, 1000, 10000], `${selected.id} fleet size`);
    integer(selected.initial_fleet_size, `${selected.id} initial fleet size`, 1);
    oneOf(selected.profile, ["linear", "step", "bursty"], `${selected.id} profile`);
    text(selected.profile_label, `${selected.id} profile label`);
    oneOf(selected.capacity_case, ["constrained", "baseline", "expanded"], `${selected.id} capacity case`);
    text(selected.capacity_label, `${selected.id} capacity label`);
    oneOf(selected.capacity_multiplier, [.8, 1, 1.25], `${selected.id} capacity multiplier`);
    invariant(selected.architecture === "centralized", `${selected.id} architecture must be centralized`);
    invariant(selected.disturbance_fraction === 0, `${selected.id} must not activate a disturbance profile`);
    invariant(selected.replications === replications, `${selected.id} replication count is inconsistent`);

    const pressure = exactKeys(selected.ex_ante_pressure, ["metric", "value", "boundary", "boundary_crossed", "binding_resource", "peak_admission_rate_agents_per_s", "not_an_operational_outcome"], `${selected.id}.ex_ante_pressure`);
    invariant(pressure.metric === "omega_a" && pressure.boundary === 1, `${selected.id} pressure contract differs from the registered definition`);
    finite(pressure.value, `${selected.id} pressure value`);
    invariant(pressure.boundary_crossed === (pressure.value >= pressure.boundary), `${selected.id} pressure boundary disposition is inconsistent`);
    text(pressure.binding_resource, `${selected.id} binding resource`);
    invariant(
      pressure.value === 0
        ? pressure.binding_resource === "none_all_projected_pressures_zero"
        : pressure.binding_resource !== "none_all_projected_pressures_zero",
      `${selected.id} pressure binding-resource sentinel is inconsistent`,
    );
    finite(pressure.peak_admission_rate_agents_per_s, `${selected.id} peak admission rate`);
    bool(pressure.not_an_operational_outcome, true, `${selected.id} pressure outcome boundary`);

    const outcomes = exactKeys(selected.operational_outcomes, ["failure_rate", "mean_deadline_miss_fraction", "mean_shed_fraction", "mean_useful_task_throughput_ratio", "mean_incomplete_exposure_per_agent_s", "definition_uses_ex_ante_pressure"], `${selected.id}.operational_outcomes`);
    for (const key of ["failure_rate", "mean_deadline_miss_fraction", "mean_shed_fraction", "mean_useful_task_throughput_ratio"]) finite(outcomes[key], `${selected.id} ${key}`, 0, 1);
    finite(outcomes.mean_incomplete_exposure_per_agent_s, `${selected.id} incomplete exposure`);
    bool(outcomes.definition_uses_ex_ante_pressure, false, `${selected.id} outcome separation`);

    invariant(Array.isArray(selected.timeseries) && selected.timeseries.length >= 2 && selected.timeseries.length <= 61, `${selected.id} timeseries length is invalid`);
    let previousTime = -1;
    selected.timeseries.forEach((point, pointIndex) => { previousTime = validateTimeseriesPoint(point, selected.id, pointIndex, previousTime); });
    return selected;
  }

  function validateDefinitions(value) {
    const selected = exactKeys(value, ["ex_ante_pressure", "operational_outcomes", "timeseries"], "definitions");
    const pressure = exactKeys(selected.ex_ante_pressure, ["metric", "symbol", "boundary", "computed_before_stochastic_simulation", "description"], "definitions.ex_ante_pressure");
    invariant(pressure.metric === "omega_a" && pressure.symbol === "Omega_A" && pressure.boundary === 1, "ex-ante pressure definition is not the registered definition");
    bool(pressure.computed_before_stochastic_simulation, true, "pressure computation ordering");
    text(pressure.description, "pressure description");

    const outcomes = exactKeys(selected.operational_outcomes, ["definition_uses_ex_ante_pressure", "not_claimed_statistically_independent", "description", "failure_criteria"], "definitions.operational_outcomes");
    bool(outcomes.definition_uses_ex_ante_pressure, false, "outcome definition separation");
    bool(outcomes.not_claimed_statistically_independent, true, "outcome independence boundary");
    text(outcomes.description, "outcome description");
    const criteria = exactKeys(outcomes.failure_criteria, ["maximum_deadline_miss_fraction", "maximum_shed_fraction", "maximum_incomplete_exposure_per_agent_s", "minimum_useful_throughput_ratio", "require_recovery"], "definitions.operational_outcomes.failure_criteria");
    finite(criteria.maximum_deadline_miss_fraction, "deadline criterion", 0, 1);
    finite(criteria.maximum_shed_fraction, "shed criterion", 0, 1);
    finite(criteria.maximum_incomplete_exposure_per_agent_s, "exposure criterion");
    finite(criteria.minimum_useful_throughput_ratio, "throughput criterion", 0, 1);
    invariant(typeof criteria.require_recovery === "boolean", "recovery criterion must be boolean");

    const timeseries = exactKeys(selected.timeseries, ["representative_replication", "maximum_points_per_scenario", "selection", "description"], "definitions.timeseries");
    invariant(timeseries.representative_replication === 0 && timeseries.maximum_points_per_scenario === 61 && timeseries.selection === "endpoints_peaks_and_even_interval_sampling", "timeseries selection contract differs from the registered definition");
    text(timeseries.description, "timeseries description");
  }

  function validatePack(value) {
    const rootKeys = ["schema_version", "pack_id", "title", "generated_from", "synthetic_only", "external_validation", "operational_use_authorized", "design", "definitions", "limitations", "scenarios"];
    const pack = exactKeys(value, rootKeys, "scenario pack");
    invariant(pack.schema_version === "1.0" && pack.pack_id === EXPECTED_PACK_ID, "scenario pack identity is unsupported");
    text(pack.title, "scenario pack title");
    bool(pack.synthetic_only, true, "synthetic-only boundary");
    bool(pack.external_validation, false, "external-validation boundary");
    bool(pack.operational_use_authorized, false, "operational-use boundary");

    const generated = exactKeys(pack.generated_from, ["engine", "interface", "package_version", "experiment_id"], "generated_from");
    invariant(generated.engine === "fleet_sim.experiments.stage3a" && generated.interface === "run_stage3a" && generated.package_version === "0.2.0", "scenario generator identity is unsupported");
    invariant(/^stage3a-[0-9a-f]{16}$/.test(generated.experiment_id), "experiment identity is malformed");

    const design = exactKeys(pack.design, ["root_seed", "replications_per_scenario", "fleet_sizes", "admission_duration_s", "recovery_window_s", "time_step_s", "admission_profiles", "capacity_cases", "capacity_scaling", "scenario_count", "timeseries_max_points_per_scenario", "paired_capacity_comparisons"], "design");
    integer(design.root_seed, "root seed");
    integer(design.replications_per_scenario, "replications", 1);
    invariant(JSON.stringify(design.fleet_sizes) === "[100,1000,10000]", "fleet-size grid differs from the registered design");
    finite(design.admission_duration_s, "admission duration", Number.MIN_VALUE);
    finite(design.recovery_window_s, "recovery window");
    finite(design.time_step_s, "time step", Number.MIN_VALUE);
    invariant(Array.isArray(design.admission_profiles) && design.admission_profiles.length === 3, "admission profile grid is incomplete");
    design.admission_profiles.forEach(validateProfile);
    invariant(new Set(design.admission_profiles.map((item) => item.id)).size === 3, "admission profiles must be unique");
    invariant(Array.isArray(design.capacity_cases) && design.capacity_cases.length === 3, "capacity grid is incomplete");
    design.capacity_cases.forEach(validateCapacity);
    invariant(new Set(design.capacity_cases.map((item) => item.id)).size === 3, "capacity cases must be unique");
    invariant(design.capacity_scaling === "proportional_to_target_fleet_size", "capacity scaling differs from the registered proportional-provisioning design");
    invariant(design.scenario_count === 27 && design.timeseries_max_points_per_scenario === 61 && design.paired_capacity_comparisons === true, "scenario design is incomplete or unpaired");
    validateDefinitions(pack.definitions);
    invariant(Array.isArray(pack.limitations) && pack.limitations.length >= 4 && new Set(pack.limitations).size === pack.limitations.length, "limitations must be a unique nonempty list");
    pack.limitations.forEach((item, index) => text(item, `limitations[${index}]`));
    invariant(Array.isArray(pack.scenarios) && pack.scenarios.length === 27, "scenario grid must contain exactly 27 cases");
    pack.scenarios.forEach((scenario, index) => validateScenario(scenario, index, design.replications_per_scenario));
    const ids = new Set(pack.scenarios.map((scenario) => scenario.id));
    invariant(ids.size === 27 && [...EXPECTED_SCENARIO_IDS].every((id) => ids.has(id)), "scenario grid is not the exact registered Cartesian product");
    return pack;
  }

  function canonical(value) {
    if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
    if (value !== null && typeof value === "object") return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
    return JSON.stringify(value);
  }

  async function sha256(bytes) {
    invariant(globalThis.crypto && globalThis.crypto.subtle, "Web Crypto is unavailable; pack integrity cannot be checked");
    const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
    return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  }

  async function loadVerifiedPack() {
    const [packResponse, manifestResponse] = await Promise.all([
      fetch(PACK_URL, { cache: "no-store", credentials: "same-origin" }),
      fetch(MANIFEST_URL, { cache: "no-store", credentials: "same-origin" }),
    ]);
    invariant(packResponse.ok, `scenario pack request returned ${packResponse.status}`);
    invariant(manifestResponse.ok, `manifest request returned ${manifestResponse.status}`);
    const [packBytes, manifest] = await Promise.all([packResponse.arrayBuffer(), manifestResponse.json()]);
    const manifestKeys = ["schema_version", "manifest_id", "pack_id", "artifact", "schema", "scenario_count", "timeseries_point_count", "root_seed", "replications_per_scenario", "synthetic_only", "external_validation", "operational_use_authorized", "generator_name", "manifest_content_sha256"];
    const checkedManifest = exactKeys(manifest, manifestKeys, "manifest");
    invariant(checkedManifest.schema_version === "1.0" && checkedManifest.pack_id === EXPECTED_PACK_ID, "manifest identity is unsupported");
    text(checkedManifest.manifest_id, "manifest identity");
    const artifact = exactKeys(checkedManifest.artifact, ["filename", "bytes", "sha256"], "manifest artifact");
    invariant(artifact.filename === "scenario-pack.json" && artifact.bytes === packBytes.byteLength, "scenario pack byte count differs from the manifest");
    invariant(/^[0-9a-f]{64}$/.test(artifact.sha256), "scenario pack digest is malformed");
    invariant(await sha256(packBytes) === artifact.sha256, "scenario pack bytes do not match the published manifest");
    const schema = exactKeys(checkedManifest.schema, ["id", "bytes", "sha256"], "manifest schema");
    invariant(schema.id === "https://redxking.github.io/fleet-assurance-sim/schemas/public_mvp_scenario_pack.schema.json" && integer(schema.bytes, "schema byte count", 1) && /^[0-9a-f]{64}$/.test(schema.sha256), "manifest schema binding is malformed");
    const claimedSelfHash = checkedManifest.manifest_content_sha256;
    invariant(/^[0-9a-f]{64}$/.test(claimedSelfHash), "manifest self-digest is malformed");
    const withoutSelfHash = { ...checkedManifest };
    delete withoutSelfHash.manifest_content_sha256;
    const canonicalBytes = new TextEncoder().encode(canonical(withoutSelfHash));
    invariant(await sha256(canonicalBytes) === claimedSelfHash, "manifest self-digest does not verify");
    const parsed = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(packBytes));
    const pack = validatePack(parsed);
    invariant(checkedManifest.scenario_count === pack.scenarios.length && checkedManifest.root_seed === pack.design.root_seed && checkedManifest.replications_per_scenario === pack.design.replications_per_scenario, "manifest does not bind the scenario design");
    invariant(checkedManifest.timeseries_point_count === pack.scenarios.reduce((sum, scenario) => sum + scenario.timeseries.length, 0), "manifest timeseries count is inconsistent");
    bool(checkedManifest.synthetic_only, true, "manifest synthetic-only boundary");
    bool(checkedManifest.external_validation, false, "manifest external-validation boundary");
    bool(checkedManifest.operational_use_authorized, false, "manifest operational-use boundary");
    invariant(checkedManifest.generator_name === "build_public_mvp_scenarios", "manifest generator is unsupported");
    return pack;
  }

  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function make(tag, className, value) { const node = document.createElement(tag); if (className) node.className = className; if (value !== undefined) node.textContent = String(value); return node; }
  function formatInteger(value) { return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value); }
  function formatPercent(value, digits = 1) { return `${(value * 100).toFixed(digits)}%`; }
  function formatPointDelta(value, digits = 1) { return `${(Math.abs(value) * 100).toFixed(digits)} percentage points`; }
  function formatNumber(value, digits = 2) { return new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(value); }
  function formatRatio(value, digits = 2) { return `${formatNumber(value, digits)}×`; }
  function formatBoundaryDelta(value, digits = 2) { return `${formatNumber(Math.abs(value), digits)} boundary-ratio units`; }
  function humanLabel(value) { const label = String(value).replaceAll("_", " "); return label.charAt(0).toUpperCase() + label.slice(1); }
  function bindingResourceLabel(value) { return value === "none_all_projected_pressures_zero" ? "No projected queue-pressure binding resource" : humanLabel(value); }
  function scenarioById(id) { return state.pack.scenarios.find((scenario) => scenario.id === id); }
  function selectedComparison() { return state.compare ? scenarioById(state.comparisonId) : null; }

  function addOptions(select, selectedId, excludedId = null) {
    clear(select);
    const groups = new Map();
    state.pack.scenarios.filter((scenario) => scenario.id !== excludedId).forEach((scenario) => {
      const label = `${formatInteger(scenario.fleet_size)} agents`;
      if (!groups.has(label)) groups.set(label, []);
      groups.get(label).push(scenario);
    });
    groups.forEach((scenarios, label) => {
      const group = document.createElement("optgroup");
      group.label = label;
      scenarios.forEach((scenario) => {
        const option = document.createElement("option");
        option.value = scenario.id;
        option.textContent = `${scenario.profile_label} · ${scenario.capacity_label}`;
        option.selected = scenario.id === selectedId;
        group.appendChild(option);
      });
      select.appendChild(group);
    });
  }

  function renderHeader(scenario) {
    const tags = byId("scenario-tags");
    clear(tags);
    [`${formatInteger(scenario.fleet_size)} agents`, scenario.profile_label, scenario.capacity_label, scenario.architecture].forEach((label) => tags.appendChild(make("span", "tag", label)));
    byId("scenario-title").textContent = scenario.name;
    byId("scenario-summary").textContent = `${formatInteger(scenario.fleet_size)}-agent target with ${scenario.profile_label.toLowerCase()}, ${scenario.capacity_label.toLowerCase()} (${formatNumber(scenario.capacity_multiplier)}×), centralized architecture, and ${scenario.replications} synthetic replications.`;
    const index = state.pack.scenarios.findIndex((item) => item.id === scenario.id) + 1;
    byId("scenario-index").textContent = `${String(index).padStart(2, "0")} / 27`;
  }

  const METRICS = [
    { key: "pressure", label: "Ex-ante wait pressure", unit: "registered wait boundary", value: (scenario) => scenario.ex_ante_pressure.value, format: (value) => formatRatio(value) },
    { key: "failure", label: "Failure rate", unit: "of replications", value: (scenario) => scenario.operational_outcomes.failure_rate, format: (value) => formatPercent(value) },
    { key: "deadline", label: "Deadline misses", unit: "mean fraction", value: (scenario) => scenario.operational_outcomes.mean_deadline_miss_fraction, format: (value) => formatPercent(value) },
    { key: "shed", label: "Work shed", unit: "mean fraction", value: (scenario) => scenario.operational_outcomes.mean_shed_fraction, format: (value) => formatPercent(value) },
    { key: "throughput", label: "Useful throughput", unit: "mean ratio", value: (scenario) => scenario.operational_outcomes.mean_useful_task_throughput_ratio, format: (value) => formatPercent(value) },
    { key: "exposure", label: "Incomplete exposure", unit: "seconds per target agent", value: (scenario) => scenario.operational_outcomes.mean_incomplete_exposure_per_agent_s, format: (value) => formatNumber(value) },
  ];

  function renderMetrics(scenario, comparison) {
    const container = byId("metric-cards");
    clear(container);
    METRICS.forEach((metric) => {
      const card = make("article", "metric-card");
      card.appendChild(make("span", "", metric.label));
      const row = make("div", "metric-value");
      row.appendChild(make("strong", "", metric.format(metric.value(scenario))));
      row.appendChild(make("small", "", metric.unit));
      card.appendChild(row);
      const comparisonLine = make("span", "metric-compare", "");
      if (comparison) {
        const delta = metric.value(scenario) - metric.value(comparison);
        if (Math.abs(delta) < 1e-12) comparisonLine.textContent = "Same as comparison";
        else {
          const direction = delta > 0 ? "higher than" : "lower than";
          const difference = metric.key === "exposure"
            ? `${formatNumber(Math.abs(delta))} seconds per target agent`
            : metric.key === "pressure"
              ? formatBoundaryDelta(delta)
              : formatPointDelta(delta);
          comparisonLine.textContent = `${difference} ${direction} comparison`;
        }
      }
      card.appendChild(comparisonLine);
      container.appendChild(card);
    });
  }

  function pressureExtent(primary, comparison) {
    const values = [...primary.timeseries.flatMap((point) => [point.projected_maximum_pressure, point.observed_maximum_pressure])];
    if (comparison) values.push(...comparison.timeseries.flatMap((point) => [point.projected_maximum_pressure, point.observed_maximum_pressure]));
    return Math.max(1.2, ...values) * 1.08;
  }

  function drawSeries(context, points, color, width, height, padding, maxTime, maxPressure) {
    const position = (point) => ({
      x: padding.left + (point.time_s / maxTime) * (width - padding.left - padding.right),
      y: padding.top + (1 - Math.min(point.observed_maximum_pressure, maxPressure) / maxPressure) * (height - padding.top - padding.bottom),
    });
    context.strokeStyle = color;
    context.lineWidth = 2.5;
    context.lineJoin = "round";
    context.lineCap = "round";
    context.beginPath();
    points.forEach((point, index) => { const pos = position(point); if (index === 0) context.moveTo(pos.x, pos.y); else context.lineTo(pos.x, pos.y); });
    context.stroke();
    const stride = Math.max(1, Math.floor(points.length / 10));
    points.forEach((point, index) => {
      if (index % stride !== 0 && index !== points.length - 1) return;
      const pos = position(point);
      context.beginPath();
      context.arc(pos.x, pos.y, 3, 0, Math.PI * 2);
      context.fillStyle = "#071319";
      context.fill();
      context.strokeStyle = color;
      context.lineWidth = 2;
      context.stroke();
    });
  }

  function drawChart(primary, comparison) {
    const canvas = byId("pressure-canvas");
    const bounds = canvas.getBoundingClientRect();
    const ratio = Math.min(globalThis.devicePixelRatio || 1, 2);
    const width = Math.max(300, Math.round(bounds.width));
    const height = Math.max(230, Math.round(bounds.height));
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    const context = canvas.getContext("2d");
    context.scale(ratio, ratio);
    context.clearRect(0, 0, width, height);
    const padding = { top: 18, right: 16, bottom: 30, left: 44 };
    const maxTime = Math.max(primary.timeseries.at(-1).time_s, comparison ? comparison.timeseries.at(-1).time_s : 0);
    const maxPressure = pressureExtent(primary, comparison);
    context.font = "11px system-ui, sans-serif";
    context.textAlign = "right";
    context.textBaseline = "middle";
    [0, .5, 1, maxPressure].forEach((value) => {
      const y = padding.top + (1 - value / maxPressure) * (height - padding.top - padding.bottom);
      context.beginPath();
      context.moveTo(padding.left, y);
      context.lineTo(width - padding.right, y);
      context.strokeStyle = value === 1 ? "#f1bf67" : "#31515d";
      context.lineWidth = value === 1 ? 1.5 : 1;
      context.setLineDash(value === 1 ? [5, 5] : []);
      context.stroke();
      context.fillStyle = value === 1 ? "#f1bf67" : "#789099";
      context.fillText(formatRatio(value, value >= 10 ? 1 : 2), padding.left - 7, y);
    });
    context.setLineDash([]);
    context.textAlign = "center";
    context.textBaseline = "top";
    [0, .5, 1].forEach((fraction) => {
      const x = padding.left + fraction * (width - padding.left - padding.right);
      context.fillStyle = "#789099";
      context.fillText(`${formatNumber(maxTime * fraction, 0)}s`, x, height - padding.bottom + 8);
    });
    drawSeries(context, primary.timeseries, "#56dbb5", width, height, padding, maxTime, maxPressure);
    if (comparison) drawSeries(context, comparison.timeseries, "#73c7eb", width, height, padding, maxTime, maxPressure);
  }

  function renderTable(primary, comparison) {
    const head = byId("pressure-table-head");
    const body = byId("pressure-table-body");
    clear(head); clear(body);
    ["Time", primary.name].concat(comparison ? [comparison.name] : []).forEach((label) => { const heading = make("th", "", label); heading.scope = "col"; head.appendChild(heading); });
    const times = [...new Set(primary.timeseries.map((point) => point.time_s).concat(comparison ? comparison.timeseries.map((point) => point.time_s) : []))].sort((a, b) => a - b);
    const valueAt = (scenario, time) => scenario.timeseries.find((point) => point.time_s === time)?.observed_maximum_pressure;
    times.forEach((time) => {
      const row = document.createElement("tr");
      const timeHeading = make("th", "", `${formatNumber(time, 0)} s`);
      timeHeading.scope = "row";
      row.appendChild(timeHeading);
      const primaryValue = valueAt(primary, time);
      row.appendChild(make("td", "", primaryValue === undefined ? "Not sampled" : formatRatio(primaryValue)));
      if (comparison) { const comparisonValue = valueAt(comparison, time); row.appendChild(make("td", "", comparisonValue === undefined ? "Not sampled" : formatRatio(comparisonValue))); }
      body.appendChild(row);
    });
  }

  function renderReading(scenario, comparison) {
    const container = byId("scenario-reading");
    clear(container);
    const bindingLabel = bindingResourceLabel(scenario.ex_ante_pressure.binding_resource);
    const pressureText = scenario.ex_ante_pressure.value === 0
      ? "All projected queue-pressure values are zero in this scenario. There is no projected queue-pressure binding resource."
      : scenario.ex_ante_pressure.boundary_crossed
        ? `The ex-ante wait-pressure measure crosses its registered 1.0× boundary. ${bindingLabel} is the binding modeled resource.`
        : `The ex-ante wait-pressure measure remains below its registered 1.0× boundary. ${bindingLabel} provides the least modeled headroom.`;
    container.appendChild(make("p", "", pressureText));
    container.appendChild(make("p", "", `Across ${scenario.replications} replications, the operational failure rate is ${formatPercent(scenario.operational_outcomes.failure_rate)} and mean useful throughput is ${formatPercent(scenario.operational_outcomes.mean_useful_task_throughput_ratio)}.`));
    const callout = make("div", "reading-callout");
    callout.appendChild(make("span", "", "Interpretation boundary"));
    callout.appendChild(make("strong", "", "Pressure is computed before the stochastic run and is not itself an operational outcome."));
    container.appendChild(callout);
    const comparisonContainer = byId("comparison-reading");
    comparisonContainer.hidden = !comparison;
    clear(comparisonContainer);
    if (comparison) {
      comparisonContainer.appendChild(make("span", "", "Comparison"));
      const pressureDelta = scenario.ex_ante_pressure.value - comparison.ex_ante_pressure.value;
      const failureDelta = scenario.operational_outcomes.failure_rate - comparison.operational_outcomes.failure_rate;
      const pressurePhrase = Math.abs(pressureDelta) < 1e-12
        ? "the same ex-ante wait pressure as"
        : `${formatBoundaryDelta(pressureDelta)} ${pressureDelta > 0 ? "higher" : "lower"} ex-ante wait pressure than`;
      const failurePhrase = Math.abs(failureDelta) < 1e-12
        ? "the same failure rate as"
        : `a failure rate ${formatPointDelta(failureDelta)} ${failureDelta > 0 ? "higher" : "lower"} than`;
      const comparisonScope = scenario.fleet_size === comparison.fleet_size && scenario.profile === comparison.profile
        ? "This is a paired capacity-case model comparison, not a causal or operational claim."
        : "This is an unpaired descriptive model comparison, not a causal or operational claim.";
      comparisonContainer.appendChild(make("p", "", `${scenario.name} has ${pressurePhrase} ${comparison.name} and ${failurePhrase} ${comparison.name}. ${comparisonScope}`));
    }
  }

  function render() {
    const primary = scenarioById(state.primaryId);
    const comparison = selectedComparison();
    renderHeader(primary);
    byId("replication-summary").textContent = `${primary.replications}-replication sample summaries`;
    byId("selection-announcement").textContent = comparison
      ? `Showing ${primary.name} compared with ${comparison.name}.`
      : `Showing ${primary.name}.`;
    renderMetrics(primary, comparison);
    byId("comparison-legend").hidden = !comparison;
    const maxObserved = Math.max(...primary.timeseries.map((point) => point.observed_maximum_pressure));
    byId("chart-description").textContent = `${primary.name} reaches ${formatRatio(maxObserved)} observed maximum wait pressure over ${formatNumber(primary.timeseries.at(-1).time_s, 0)} seconds.${comparison ? ` The chart also shows ${comparison.name}.` : ""} A table with every retained point follows.`;
    drawChart(primary, comparison);
    renderTable(primary, comparison);
    renderReading(primary, comparison);
  }

  function bindEvents() {
    byId("scenario-select").addEventListener("change", (event) => { state.primaryId = event.target.value; if (state.primaryId === state.comparisonId) state.comparisonId = state.pack.scenarios.find((item) => item.id !== state.primaryId).id; addOptions(byId("compare-select"), state.comparisonId, state.primaryId); render(); });
    byId("compare-toggle").addEventListener("change", (event) => { state.compare = event.target.checked; byId("compare-picker").hidden = !state.compare; render(); });
    byId("compare-select").addEventListener("change", (event) => { state.comparisonId = event.target.value; if (state.comparisonId === state.primaryId) { event.target.setCustomValidity("Choose a different scenario for comparison."); event.target.reportValidity(); return; } event.target.setCustomValidity(""); render(); });
    let resizeFrame = null;
    globalThis.addEventListener("resize", () => { if (resizeFrame) cancelAnimationFrame(resizeFrame); resizeFrame = requestAnimationFrame(() => { resizeFrame = null; if (state.pack) drawChart(scenarioById(state.primaryId), selectedComparison()); }); }, { passive: true });
  }

  function showFailure(error) {
    document.body.dataset.appState = "error";
    byId("load-status").hidden = true;
    byId("explorer").hidden = true;
    byId("load-error").hidden = false;
    byId("load-error-detail").textContent = `${error instanceof Error ? error.message : "Unknown validation failure"}. No fallback values have been substituted.`;
  }

  async function start() {
    try {
      state.pack = await loadVerifiedPack();
      state.primaryId = "n01000-linear-capacity-baseline";
      state.comparisonId = "n01000-linear-capacity-expanded";
      addOptions(byId("scenario-select"), state.primaryId);
      addOptions(byId("compare-select"), state.comparisonId, state.primaryId);
      byId("pack-version").textContent = `${state.pack.pack_id} / schema ${state.pack.schema_version}`;
      byId("pack-integrity").textContent = "Bytes match manifest";
      byId("load-status").hidden = true;
      byId("explorer").hidden = false;
      document.body.dataset.appState = "ready";
      bindEvents();
      render();
    } catch (error) {
      showFailure(error);
    }
  }

  start();
})();
