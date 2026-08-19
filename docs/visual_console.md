# Virtual Fleet Assurance Consoles

Version 0.2.0 provides two distinct offline visualization paths. The general simulator console replays canonical event logs. The Stage 3 evidence console presents bounded views of immutable admission and compromise evidence. Neither console is an external validation environment or a production monitoring system.

## Stage 3 confirmatory evidence console

The completed confirmatory exports are:

```text
results/stage3/consoles/stage3-confirmatory-20260819-01.html
results/stage3/consoles/stage3-confirmatory-20260819-01.json
```

The HTML is self-contained and can be opened directly in a modern browser without a server or runtime network access. The JSON export supports offline inspection and downstream review. The HTML is 148,129,497 bytes, approximately 141.3 MiB. The JSON export is 199,243,869 bytes, approximately 190.0 MiB. Allow at least 400 MiB for an additional HTML and JSON export pair.

The authoritative source execution is:

```text
results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01/
```

Its protocol hash is:

```text
b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851
```

The console reports execution integrity separately from scientific disposition. Execution integrity passed. Stage 3A and Stage 3B are both `not_supported_under_preregistered_rule`. All outcomes are synthetic and model-conditioned, and no external validation was performed.

### Build a separate offline copy

Run from the repository root. These output names are intentionally different from the retained release artifacts and from the immutable execution directory.

```bash
mkdir -p local_runs/stage3-consoles
.venv-stage3-verify/bin/python scripts/build_stage3_evidence_console.py \
  --mode replay \
  --execution results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01 \
  --output local_runs/stage3-consoles/stage3-confirmatory-20260819-01-copy.html \
  --json-output local_runs/stage3-consoles/stage3-confirmatory-20260819-01-copy.json
```

The builder refuses to write inside an immutable source execution and refuses to replace an existing output unless the caller explicitly requests overwrite. Keep the default refusal for evidence work. Choose another new output name if the example output already exists.

### Compare confirmation with the excluded final pilot

The comparison mode is useful for engineering review, but Pilot 05 remains excluded from scientific adjudication.

```bash
.venv-stage3-verify/bin/python scripts/build_stage3_evidence_console.py \
  --mode comparison \
  --execution results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01 \
  --comparison results/stage3/engineering-pilots/stage3-engineering-pilot-20260819-05 \
  --output local_runs/stage3-consoles/stage3-confirmatory-vs-pilot05.html
```

Do not combine pilot metrics with confirmatory metrics or use a pilot outcome to reinterpret a frozen criterion.

### Stage 3 views and provenance

The Stage 3 console includes:

- Protocol identity, execution scope, integrity status, environment, resource use, and limitations
- Stage 3A predictor-versus-observed views, block results, transfer slices, calibration, and resource traces
- Stage 3B initiation and severity views, calibration-selected baselines, transfer slices, defense pairs, and lifecycle trajectories
- DMP node-state and directed-edge message summaries
- A sampled canonical directed graph with explicit source and rendered counts
- Availability and integrity warnings for every optional trace class

Five Stage 3B records are selected by a fixed, outcome-independent rule. Each lifecycle and DMP trace contains 41 steps. The rendered canonical graph contains 500 sampled nodes and 2,000 edges from a 1,000-node, 13,423-edge source graph. These trace artifacts are generated after metric computation and carry the scope `visualization_only_not_scientific_metric_input`.

## General self-contained replay

Generate a new notional Stage 0 scenario and its offline console under the nonrelease `local_runs` tree:

```bash
fleet-sim run \
  --config configs/experiments/stage0_demo.yaml \
  --output local_runs/stage0-demo-v020 \
  --visualize
```

The command prints the generated replay-bundle path. The bundle contains `virtual_fleet_assurance_console.html`. Plotly JavaScript and run data are embedded, so replay requires no network request.

The general offline console provides:

- Play, pause, previous-event, next-event, timeline seek, and speed controls
- Communication and authorization graph toggles
- Agent state, credential epoch, timing uncertainty, partition, and supervisor inspection
- Authorization queue and utilization history
- Security compromise and containment history
- Timing-assurance degradation history
- Credential-renewal and revocation activity
- Replay equivalence, event-log digest, final-state hash, evidence class, and parameter class

## Local interactive console

Launch the Bokeh multi-run console from the repository root:

```bash
fleet-console --root .
```

For a noninteractive host:

```bash
fleet-console --root . --no-browser --port 5006
```

The general console exposes four modes:

- Replay: inspect an immutable replay bundle.
- Comparison: compare key metrics between two stored runs.
- Scenario: configure and execute a new immutable notional scenario.
- Live: execute a new run and automatically replay the captured stream.

True streaming while the discrete-event model is executing is not implemented. Live mode is capture followed by replay.

## Visualization integrity and security

The canonical event log and immutable Stage 3 Parquet and JSON artifacts are authoritative. Visual state is reconstructed from those artifacts. A console must not infer fleet-wide metrics from sampled or hidden visual elements.

For large graph layers, rendered edges may be sampled while underlying run metrics remain unchanged. The representation label discloses sampling. The N=10,000 paths are execution and transfer checks, not full visual-performance qualifications and not secure-scale demonstrations.

The local Bokeh service has no production authentication or authorization layer. Bind it only to loopback unless a controlled environment provides appropriate network protection. Treat any added operational data as potentially sensitive.
