# Data Dictionary

## Event log

Primary file: `replay_bundles/<run-id>/events.jsonl`

Each line is a canonical JSON event. Important fields include:

| Field | Meaning |
|---|---|
| run_id | Immutable scenario-run identifier |
| configuration_hash | Hash of the complete validated configuration |
| seed | Root random seed |
| event_id | Unique deterministic event identifier |
| parent_event_id | Causal parent when one is available |
| simulation_time | Continuous simulation timestamp in seconds |
| logical_time | Monotonic logical event index |
| event_type | State transition or observed operation |
| source_id | Initiating component or agent |
| destination_id | Receiving component or agent |
| task_id | Associated task identifier |
| coalition_id | Associated coalition identifier when used |
| capability_id | Capability under authorization or execution |
| authorization_decision | Permit or deny result |
| credential_epoch | Credential generation after renewal or revocation |
| timing_uncertainty | Agent timing uncertainty in seconds |
| message_bytes | Modeled message size |
| severity | Informational, warning, or critical classification |
| metadata | Event-specific structured payload |
| state_before | Optional integrity-checkpoint hash before transition |
| state_after | Optional integrity-checkpoint hash after transition |

## Replay bundle

| File | Purpose |
|---|---|
| config.yaml | Complete validated configuration |
| initial_state.json | Replay starting state |
| final_state.json | Simulator final state |
| events.jsonl | Canonical append-only event stream |
| events.csv | Tabular convenience representation |
| snapshots.jsonl | Periodic replay checkpoints |
| summary.json | Metrics, evidence labels, limitations, and replay validation |
| graph_layers.json | Node layout and graph-layer topology data |
| virtual_fleet_assurance_console.html | Self-contained offline replay application when generated |

## Stage 0 measurement dataset

Primary file: `results/stage0/stage0_measurements.csv`

| Field | Meaning |
|---|---|
| experiment | Verification or analysis family |
| configuration | Human-readable parameter slice |
| replication | Independent replication number |
| seed | Exact seed or SeedSequence child description |
| metric | Measurement name |
| value | Numeric result |
| evidence_class | Analytic, numerical, or software-verification classification |
| parameter_class | Provenance classification for the governing inputs |

## Stage 3 confirmatory execution

Authoritative directory:

```text
results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01/
```

The execution is immutable and model-conditioned. It contains synthetic outcomes only. Engineering-pilot artifacts under `results/stage3/engineering-pilots/` are excluded from scientific adjudication.

| File or directory | Rows or entries | Purpose |
|---|---:|---|
| `execution_started.json` | One object | Start time, exact command, protocol identity, environment, and runtime budget recorded before simulation |
| `stage3_evidence.json` | One object | Confirmatory metrics, frozen criteria, dispositions, limitations, seed domains, bootstrap seeds, execution resources, and all 151 frozen-input checks |
| `execution_manifest.json` | 341 artifact entries | Final inventory of every execution artifact except the manifest itself, with byte count and SHA-256 digest |
| `raw/stage3a_replications.parquet` | 25,200 | Stage 3A replication-level admission and assurance-resource outcomes |
| `derived/stage3a_heldout_predictions.parquet` | 21,600 | Stage 3A held-out candidate and baseline probabilities and error components |
| `raw/stage3b_scenario_specifications.parquet` | 240 | Exact Stage 3B split, block, topology, segmentation, attack, defense, and seed specifications |
| `raw/stage3b_replications.parquet` | 2,400 | Stage 3B generator outcomes and predictor features at replication level |
| `derived/stage3b_heldout_predictions.parquet` | 1,200 | Stage 3B held-out candidate and calibration-selected baseline predictions |
| `checkpoints/stage3b/scenario-*.parquet` | 240 files, 10 rows each | Atomic scenario checkpoints whose union equals the aggregate Stage 3B raw table |
| `stage3a/block-*/*/` | 15 block-partition directories | Stage 3A local raw, derived, trace, summary, and manifest artifacts |
| `stage3b/traces/` | Five selected records | Visualization-only lifecycle, DMP-state, selection, and sampled-graph evidence |

### Stage 3A identity, partition, and seed fields

| Field | Meaning |
|---|---|
| `experiment_id` | Deterministic identifier for one Stage 3A block-partition execution |
| `scenario_id` | Unique fixed-design scenario identifier |
| `partition` | `training`, `calibration`, or `held_out` |
| `block_id` | Independent block from 0 through 4 |
| `randomization_pair_id` | Common-random-number cluster retained by the hierarchical bootstrap |
| `replication` | Zero-based replication index |
| `replication_seed` | Derived seed for the randomization pair and replication in the confirmatory Stage 3A domain |
| `seed` | Execution seed retained by the Stage 3A runner; equal to `replication_seed` in this execution |
| `evidence_scope` | Synthetic, model-conditioned evidence label |

`recovery_time_s` is null exactly when `queue_unrecovered_at_horizon` is true. The null denotes an undefined recovery time within the simulated horizon, not a missing measurement.

### Stage 3A primary outcome and prediction fields

| Field | Meaning |
|---|---|
| `observed_omega_a` | Maximum observed normalized assurance-resource backlog measure |
| `operational_failure` | Frozen binary outcome used by Stage 3A evaluation |
| `operational_failure_definition_uses_omega` | Audit field confirming that the outcome definition does not use `Omega_A` |
| `candidate_probability` | Calibrated probability from the preregistered Stage 3A candidate |
| `baseline_probability` | Probability from the calibration-selected strongest simple baseline |
| `multivariate_probability` | Probability from the preregistered multivariate comparator |
| `candidate_squared_error` | Candidate Brier component for the observed outcome |
| `baseline_squared_error` | Selected simple-baseline Brier component |

### Stage 3B identity, defense, and seed fields

| Field | Meaning |
|---|---|
| `record_id` | Scenario identifier plus replication suffix |
| `scenario_id` | One fixed Stage 3B specification, including defense case |
| `split` | `exploratory`, `calibration`, or `heldout` |
| `block` | Independent block from 0 through 4 |
| `defense_case` | `nominal` or `detection_response_shift` |
| `defense_pair_id` | Scenario-level identifier shared across the two held-out defense cases |
| `defense_pair_record_id` | Replication-level paired identifier used for exact defense-case checks and paired bootstrap resampling |
| `graph_seed` | Seed for directed graph construction |
| `process_seed` | Seed for compromise and response dynamics |
| `observation_seed` | Seed for bounded observations exposed to the predictor |
| `base_replication_seed` | Scenario-pair seed retained before replication derivation |
| `replication_seed` | Seed derived from `base_replication_seed` and the replication index |

For every held-out `defense_pair_record_id`, the two defense cases share all five seed fields. `outbreak_onset_step` is null exactly for nonoutbreak records.

### Stage 3B outcomes and predictions

| Field | Meaning |
|---|---|
| `outbreak` | Frozen macroscopic-outbreak indicator |
| `final_compromise_fraction` | Synthetic final fraction ever compromised |
| `attack_trace_digest` | SHA-256 identity of the attack trace produced by the separate generator implementation with a bounded observed view |
| `candidate_outbreak_probability` | Calibrated DMP-based outbreak-initiation probability |
| `candidate_conditional_severity` | Predicted conditional expected severity under outbreak, populated for every held-out row |
| `candidate_conditional_nonoutbreak_severity` | Predicted conditional expected severity under no outbreak, populated for every held-out row |
| `candidate_expected_final_fraction` | Phase-separated expected final compromise fraction |
| `baseline_final_fraction` | Final-size prediction from the calibration-selected comparator, `temporal_propagator` in this confirmation |
| `baseline_outbreak_probability` | Initiation prediction from the calibration-selected comparator, `node_hazard_aggregation` in this confirmation |
| `candidate_final_absolute_error` | Candidate absolute final-size error |
| `baseline_final_absolute_error` | Selected-baseline absolute final-size error |
| `candidate_brier_component` | Candidate outbreak Brier component |
| `baseline_brier_component` | Selected-baseline outbreak Brier component |

## Stage 3 visualization exports

| File | Purpose |
|---|---|
| `results/stage3/consoles/stage3-confirmatory-20260819-01.html` | Self-contained offline confirmatory evidence console |
| `results/stage3/consoles/stage3-confirmatory-20260819-01.json` | Offline bounded evidence export used by the console and external review tools |
| `stage3b_lifecycle_timeseries.parquet` | Observed and predicted detection, quarantine, revocation, recovery, and compromise trajectories for five fixed records |
| `stage3b_dmp_state_summary.parquet` | Node-state and directed-edge message summaries for the same five records |
| `stage3b_trace_selection.json` | Fixed, outcome-independent trace-selection identities and seed provenance |
| `stage3b_graph_evidence.json` | Sampled directed graph for one canonical visual record, with source and rendered graph counts |

All Stage 3 trace and console exports are derived after scientific metrics are computed. They are labeled visualization-only and are not inputs to acceptance metrics.
