# Stage 3 Architecture and Assurance Boundaries

**Status:** Engineering draft  
**Date:** 2026-08-19  
**Protocol:** `FAS-S3-C1-2026-08-19`  
**Evidence scope:** Synthetic, model-conditioned research with calibration-interface verification only  
**Decision posture:** Complete final pre-freeze verification and await explicit freeze authority. Confirmatory execution is not authorized until the user explicitly freezes the protocol and creates the preexecution manifest.

## 1. Purpose and status language

This document defines the Stage 3 architecture for fleet-admission stability and phase-separated compromise prediction. It preserves the immutable Stage 2 baseline and adds two bounded research tracks:

- Stage 3A evaluates whether an ex-ante assurance-resource overload projection predicts a separately calculated synthetic operational-assurance label. The label expression excludes `Omega_A`, but projection and outcome execution share the declared trajectory and synthetic resource model.
- Stage 3B evaluates whether separate outbreak-initiation, outbreak-severity, and non-outbreak-severity estimators improve held-out prediction across a generator-to-observed-view boundary.

The following status terms are normative in this document:

- **Implemented:** the named source or artifact exists in the working copy.
- **Verification in progress:** implementation exists, but focused or end-to-end verification is not complete.
- **Planned:** the boundary is architectural intent and must not be represented as an implemented capability.
- **Confirmed:** reserved for a completed, protocol-gated confirmatory run that passes the preregistered criteria. Nothing in Stage 3 has this status.

The current implementation is an engineering research platform. It is not evidence of operational deployment, external validation, implementation security, or a universal fleet-scaling law.

## 2. Architecture requirements

| ID | Requirement | Current disposition |
|---|---|---|
| S3-ARCH-001 | Preserve the extracted Stage 2 baseline as read-only provenance and do not rewrite Stage 2 evidence. | Implemented by repository separation and recorded in `BASELINE_PROVENANCE.json`. |
| S3-ARCH-002 | Admit CSV or Parquet assurance measurements only after schema, type, finite-value, provenance, and resource-identity checks. | Implemented in the calibration library and command-line import path. External measurements have not been supplied. |
| S3-ARCH-003 | Represent all ten declared assurance resource types and all ten admission or disturbance patterns. | Implemented in the Stage 3A resource model. |
| S3-ARCH-004 | Compute `Omega_A` ex ante and define the operational label without consuming `Omega_A`, while documenting the shared synthetic resource model. | Implemented and tested. This is definition separation, not model independence. |
| S3-ARCH-005 | Model prerequisite and routing effects among assurance resources rather than treating them as independent load sinks. | Planned. The present Stage 3A simulator is a flat set of parallel aggregate queues. |
| S3-ARCH-006 | Prevent Stage 3B predictors from receiving generator-only latent state, realized random draws, or selected causal events. | Implemented at the class and feature-materialization boundaries with focused tests and a structural review. The review is not proof of statistical independence. |
| S3-ARCH-007 | Keep exploratory, calibration, and held-out partitions disjoint, and use held-out data once for final adjudication. | Implemented in the model APIs and integrated runner, including record-identifier leakage checks and calibration-only comparator selection. |
| S3-ARCH-008 | Freeze source, protocol, configuration, schemas, environment, seeds, and the execution contract before confirmation. Abort on mismatch. | Freeze and verification mechanisms are implemented. No preexecution manifest exists because protocol status remains `engineering_draft`. |
| S3-ARCH-009 | Write run-scoped immutable artifacts with hashes, evidence labels, failure records, checkpoints, and resource-use metadata. | Implemented by the integrated runner. The final release evidence ledger and report remain post-confirmation outputs. |
| S3-ARCH-010 | Use sparse representations through fleet size 10,000 and validate any approximation before using it above that scale. | Sparse Stage 3B primitives and population-independent Stage 3A aggregate state are implemented. Engineering Pilot 03 completed the full two-replication matrix, including 10,000-agent cells; the ten-replication confirmatory performance envelope has not been executed. |
| S3-ARCH-011 | Keep replay and the Stage 3 console read-only with respect to source scientific state and adjudicated metrics. | Implemented. Console output is forced outside source executions; live mode completes a separate bounded demonstration before animation. |
| S3-ARCH-012 | Require no runtime network service, secret, or hardcoded workstation path for scientific execution. | Implemented in the scientific execution paths and offline console. Operating-system egress enforcement remains an environment control. |
| S3-ARCH-013 | Label rendered or exported values as exact, sampled, observed, predicted, estimated, unavailable, or not retained as applicable. | Implemented for Stage 3A traces, Stage 3B console projections, and the Stage 3 console. |
| S3-ARCH-014 | Preserve negative, null, failed, and not-evaluable results. Never replace missing seeds automatically. | Implemented in runner criteria, failure artifacts, no-replace directories, and retained checkpoints. The final release ledger is produced only after confirmation. |

## 3. Component status and boundaries

| Component | Responsibility | Status on 2026-08-19 |
|---|---|---|
| Baseline event engine and replay | Deterministic discrete-event execution, canonical events, state hashes, and replay verification. | Implemented and independently rechecked during Stage 2 handoff. |
| Protocol guard | Hash frozen inputs, verify before execution, reject unsafe paths, reserve a new run directory, and inventory artifacts. | Implemented in `src/fleet_sim/experiments/stage3_protocol.py`; focused tests exist. No Stage 3 preexecution manifest exists yet. |
| Measurement ingestion | Validate CSV or Parquet, normalize timestamps and types, compute source and dataset hashes, and write canonical Parquet plus an import manifest. | Implemented in `src/fleet_sim/calibration/measurements.py` and `scripts/import_assurance_measurements.py`. |
| Admission calibration | Infer nonnegative background and admission work, capacity, service-time moments, wait budget, and overload fractions. | Implemented in `src/fleet_sim/calibration/admission.py` and `scripts/calibrate_admission_model.py`. Current example data is synthetic. |
| Stage 3A projection | Compute ex-ante admission predictors, including projected `Omega_A`, without reading realized outcomes. | Implemented in `src/fleet_sim/analysis/admission_predictors.py`. Projection and outcome execution still share the declared synthetic resource model. |
| Stage 3A simulator | Run deterministic-seed aggregate queues for ten assurance resources and emit bounded labeled traces and immutable run artifacts. | Implemented and tested in `src/fleet_sim/control_plane/resource_network.py` and `src/fleet_sim/experiments/stage3a.py`. |
| Stage 3A prerequisite DAG | Route work according to completion of resource prerequisites and expose dependency-specific failure. | Planned. No DAG executor is connected to the current simulator. |
| Stage 3B generator boundary | Own exact hidden graph and attack state, expose a noisy observation-safe view, and emit attack outcomes. | Implemented and tested in `src/fleet_sim/security/attack_trace.py`. The view is derived from generator constructs and is not statistically independent. |
| Stage 3B predictors | Build a sparse directed operator, run node and edge message passing, retain common-cause vectors, and compute comparator features. | Implemented and tested in `src/fleet_sim/security/dynamic_message_passing.py`. |
| Phase-separated model | Fit initiation, outbreak severity, and non-outbreak severity on exploratory data; fit mappings and intervals on calibration data; reject held-out identifier overlap. | Implemented and tested in `src/fleet_sim/analysis/phase_separated.py`. |
| Predictive metrics | Compute binary calibration and discrimination metrics plus continuous severity errors and interval coverage. | Implemented and tested in `src/fleet_sim/analysis/predictive_metrics.py`, including tie-aggregated PR AUC and `1e-6` log-loss clipping. |
| Stage 3B engineering orchestration | Generate records, select comparators by leave-one-block-out calibration crossfit, fit the DMP-only primary model, evaluate held-out records, and materialize bounded console projections. | Implemented and tested in `src/fleet_sim/experiments/stage3b.py`. Per-block held-out class support is retained for top-level adjudication. |
| Matrix compiler | Expand Stage 3A and Stage 3B partition, block, scale, shift, topology, attack, defense, and replication cells from frozen configuration. | Implemented in `build_stage3a_scenarios` and `build_stage3b_specs` within `src/fleet_sim/experiments/stage3_runner.py`. |
| Protocol-gated Stage 3 runner | Enforce counts, budgets, partitions, hash gates, and seed domains; execute both tracks; checkpoint Stage 3B; record failures; and adjudicate fixed criteria. | Implemented in `src/fleet_sim/experiments/stage3_runner.py` and `scripts/run_stage3.py`. Confirmatory mode remains unavailable until an explicitly authorized manifest exists. |
| Stage 3 evidence console | Load Stage 3 evidence and optional traces, verify loaded artifact digests when listed, render live-completed, replay, or comparison views, and export offline HTML or JSON without changing source runs. | Implemented and tested in `src/fleet_sim/visualization/stage3_console.py`, `src/fleet_sim/visualization/stage3_app.py`, and `scripts/build_stage3_evidence_console.py`. The integrated runner now persists fixed selected Stage 3B lifecycle, DMP-state, and graph projections. |

## 4. System context and data flow

The architecture separates design and freeze, calibration, scientific execution, artifact custody, and presentation.

```text
                         DESIGN AND FREEZE PLANE

 Stage 2 baseline     protocol/configs     schemas     seed manifest
        |                    |                 |              |
        +--------------------+-----------------+--------------+
                                      |
                    explicit freeze and hash verification
                                      |
             preexecution manifest [IMPLEMENTED MECHANISM, NOT CREATED]
                                      |
                    abort on any missing or changed input
                                      |
                                      v
                              EXECUTION AUTHORITY


 CALIBRATION PLANE                                  SCIENTIFIC EXECUTION PLANE

 CSV or Parquet                                      +------------------------+
      |                                               | Stage 3A               |
 schema and semantic checks                           | trajectory             |
      |                                               | -> ex-ante predictors  |
 canonical Parquet + import manifest                  | -> stochastic resource |
      |                                               |    outcomes            |
 parameter calibration                               +-----------+------------+
      |                                                           |
 labeled calibration bundle                                      |
      |                                                           v
      +----------------------------------------------> run-scoped raw and
                                                      derived artifacts

                                                      +------------------------+
                                                      | Stage 3B               |
                                                      | latent generator       |
                                                      |   | outcome labels      |
                                                      |   +------------------+  |
                                                      |   | observed view    |  |
                                                      |   v                  v  |
                                                      | predictors       evaluator
                                                      +-----------+------------+
                                                                  |
                                                                  v
                                                   immutable results + hashes
                                                                  |
                                               +------------------+----------------+
                                               |                                   |
                                      replay verification               console/export
                                       [READ ONLY]                        [READ ONLY]
```

Scientific execution must not fetch data, dependencies, models, or credentials from a network. Installation and release packaging are separate, pre-execution activities.

## 5. Calibration boundary

### 5.1 Accepted measurement contract

The implemented schema requires timestamp, resource identity and type, fleet size, admitted agents, arrivals, completions, queue depth, service and wait time, capacity, deadline, dropped and deferred work, errors, source type, and measurement provenance. The admitted resource types are exactly:

1. identity issuance
2. certificate issuance and renewal
3. authorization-policy evaluation
4. task-dispatch registration
5. telemetry-source registration
6. evidence-ingest initialization
7. supervisory review
8. revocation readiness
9. configuration attestation
10. dependency registration

The importer rejects missing fields, empty identifiers, unsupported resource or source values, invalid timestamps, nonnumeric or nonfinite values, invalid sign constraints, nonintegral count fields, duplicate `(timestamp, resource_id)` observations, and resource identifiers mapped to multiple types.

### 5.2 Provenance and evidence semantics

`source_type` is one of `measured`, `replayed`, or `synthetic`. A dataset containing any synthetic row is labeled `interface_verification_only`. A measured-only dataset can be labeled `external_measurement_calibration`, and a nonsynthetic dataset containing replayed observations is labeled `replayed_measurement_calibration`.

Those labels describe parameter-source provenance, not validation status. The calibration bundle currently sets `external_validation` to `false` for every source type. External validation requires owner-authorized operational measurements, documented scope and instrumentation quality, held-out evaluation against that environment, and an explicit evidence disposition. Merely importing measured data does not satisfy that standard.

### 5.3 Calibration output and model entry

```text
untrusted local file
    -> schema and semantic validation
    -> canonical ordered dataset + source hashes
    -> nonnegative resource fit
    -> immutable calibration bundle
    -> reviewed ResourceSpec construction [PLANNED ADAPTER]
    -> Stage 3A engineering or confirmatory matrix
```

The integrated Stage 3 runner currently constructs the declared notional fixtures through `_stage3a_resource_factory`; it does not consume the calibration bundle. A frozen calibration-bundle-to-`AssuranceResourceSpec` adapter therefore remains planned. That adapter must preserve every source hash, resource identifier, parameter class, fit diagnostic, and evidence-scope label. It must fail closed if one of the ten resources is absent unless a future protocol explicitly allows a partial engineering pilot. Until that adapter is implemented and authorized measurements are supplied, the Stage 3A evidence scope remains calibration-interface verification only.

## 6. Stage 3A resource architecture

### 6.1 Current aggregate model

The current simulator maintains ten aggregate queue states. At each time step it combines background work, newly admitted-agent work, and pattern-specific sybil, restart, or renewal work. It applies declared capacity, service-time distribution, queue, shed, or defer behavior, wait budget, and recovery multiplier. The state dimension is proportional to resources and time steps, not fleet population.

The implemented patterns are step, linear, staged, exponential, bursty, periodic, closed-loop, sybil, mass restart, and mass renewal. All default resource values are notional engineering fixtures. The runner compiles 30 training scenarios, 30 calibration scenarios, and 360 held-out scenarios per block. Held out is the full product of two fleet sizes, ten profiles, three architectures, three capacity multipliers, and two workloads. Across five blocks there are 2,100 scenarios before replication.

Stage 3A uses `randomization_pair_id = block + partition + fleet size + profile`. Replication seeds are SHA-256 derivations of the track root seed, pair identifier, and replication index. Calibration capacity cells and all held-out architecture, capacity, and workload cells inside a pair therefore share a replication seed. The comparison is seed-aligned; different workload distributions can transform or consume the stream differently.

Default capacity is proportional to final population. Architecture scaling applies

```text
C'_r(N) = C_r(N) * architecture_factor_r
          * (max(N, 1000) / 1000)^alpha
```

The exponent is zero for every architecture except `sharded_sublinear_capacity`, where `alpha = -0.20`. Because `C_r(N)` is proportional to `N`, that held-out case scales approximately as `N^0.80` above the reference fleet size `Nref = 1000`. Capacity multipliers 0.80, 1.00, and 1.25 are crossed separately.

The ex-ante candidate is:

```text
Omega_A = max over resource r and time t of
          projected_queue_r(t) / (capacity_r * maximum_wait_r)
```

Predictor calculation consumes only the declared trajectory and resource specifications. It does not consume realized queue, deadline, shedding, recovery, observed `Omega_A`, or the failure label. The operational label expression uses deadline misses, work shedding, incomplete-assurance exposure, useful-throughput loss, target-population failure, and recovery failure without referencing `Omega_A`.

This boundary prevents direct label reuse but does not create an independent outcome generator. Projection and simulation share the same trajectory, resource work, capacity, wait budgets, overload policy, and queue abstractions. The simulator also uses the prior observed queue ratio to activate recovery capacity. Stage 3A findings therefore remain synthetic model-conditioned prediction evidence, not external or strong independence evidence.

### 6.2 Calibration-only analysis boundary

Within each structural block:

1. Candidate `Omega_A` probabilities use a PAVA mapping fit only on calibration rows.
2. Each simple scalar comparator uses its own calibration-only PAVA mapping.
3. The strongest simple comparator is selected by leave-one-scenario-out cross-fitted calibration mean squared error.
4. The multivariate logistic baseline fits coefficients on training rows and its PAVA map on calibration rows. It is reported separately from primary strongest-simple selection.
5. The transfer threshold is selected from calibration `Omega_A` and labels only.
6. Held-out rows are prediction and adjudication only.

Class support is recorded for training, calibration, and held out in every block. The Stage 3A criterion requires both classes in all three partitions. Criteria are serialized as `passed`, `failed`, or `not_evaluable`; only all-passed produces support.

### 6.3 Planned prerequisite and routing DAG

The present model applies admission work to parallel queues. The following DAG is the planned dependency boundary, not current execution behavior:

```text
 admission request
        |
        v
 [identity issuance]
        |
        v
 [certificate issuance / renewal] ----------------------+
        |                                                |
        v                                                v
 [configuration attestation]                    [revocation readiness]
        |
        v
 [dependency registration]
        |
        v
 [authorization policy evaluation] ---------------------+
        |                                                |
        +----------------------+                         |
        |                      |                         |
        v                      v                         |
 [task dispatch         [supervisory review] <------+   |
  registration]                                  |      |
        |                                         |      |
        v                                         |      |
 [telemetry source registration]                  |      |
        |                                         |      |
        v                                         |      |
 [evidence ingest initialization] ----------------+      |
        |                                                |
        +---------------------- admission ready <--------+
```

Before this DAG can be treated as implemented, the resource model needs typed edges, join semantics, completion tokens, retry and cancellation rules, dependency-specific deadlines, admission-ready criteria, and deterministic tests for partial completion and recovery. Cycles are prohibited in the admission prerequisite graph. Renewal and revocation processes may be modeled as separate post-admission workflows rather than adding cycles to the admission DAG.

### 6.4 Current limitations

- Queue outputs show resource saturation but do not yet establish causal blocking along prerequisites.
- Aggregate counts do not identify which individual agent is incomplete or which prerequisite it lacks.
- Full per-replication time series are intentionally not retained. Selected traces are bounded and labeled `exact` or `sampled`.
- `default_stage3a_scenarios` remains an engineering convenience. Confirmatory execution uses the integrated matrix compiler and enforces the configured 12 replications per scenario.
- The calibration bundle is not wired into the integrated runner. Current Stage 3A parameters are notional fixtures.

## 7. Stage 3B generator and predictor isolation

### 7.1 Isolation boundary

```text
              GENERATOR-ONLY TRUST DOMAIN

 exact latent layers         hidden edge resistance and delay
 exact latent node state     common-cause and identity exposure
 process random draws        realized causal and response events
              |                              |
              |                              +-----> outcome labels
              |
              v  one-way projection
 +---------------------------------------------------------------+
 | ObservedSystemView                                            |
 | edge-missed and augmented sparse layers; noisy susceptibility  |
 | and exploitability; response-rate proxies; initial-risk prior; |
 | noisy common-cause vector; segment IDs; declared time profiles |
 +---------------------------------------------------------------+
              |
              v
     PREDICTOR-ONLY TRUST DOMAIN
 directed sparse operator -> node/edge DMP -> scenario features
 static comparators       -> phase-separated fitted models
              |
              v
 predictions joined with labels only in partition-aware evaluator
```

`AttackTraceGenerator` owns `_LatentSystem`; predictor code accepts `ObservedSystemView`. The generator's exact hidden state includes its latent layer topology, edge resistance and delay, susceptibility, exploitability, detection propensity, common-cause state, identity-provider exposure, random draws, and realized event selection. The observed view contains deliberately noisy or incomplete proxies for some of those constructs, along with exact segment identifiers and declared time profiles. Common-cause risk is an explicit observed vector and is not converted into fabricated pairwise edges.

The Stage 3B experiment code computes predictor features before generating replication outcomes. `dynamic_message_passing.py` imports the observed view type, not the latent type. `phase_separated.py` records the identifiers used for fitting and rejects held-out records whose identifiers overlap those fit records.

This is a software and information-boundary separation, not statistical independence. The noisy observed proxies intentionally depend on generator constructs. It supports the narrower claim that the predictor does not receive exact hidden latents, selected events, or outcome random draws.

### 7.2 Predictor structure

The directed operator preserves row-as-source and column-as-target orientation across authorization, communication, dependency, credential, and supervision layers. Dynamic message passing retains node response compartments, edge no-transmission messages, and common-cause survival rather than reducing the predictor to one spectral scalar.

The primary candidate is DMP-only at the fitted component boundary:

- initiation uses only `dmp_outbreak_probability`;
- outbreak severity uses only `dmp_expected_fraction`; and
- non-outbreak severity is separately fitted using only `dmp_expected_fraction`.

Expected final fraction combines all three components. The non-outbreak term is learned from non-outbreak rows and is not fixed to `1/N`.

Univariate comparators are temporal propagator, node-hazard aggregation, static adjacency, static nonbacktracking, combined scalar, authorization-only, communication-only, and simple reproduction. The `interpretable_multivariate_non_dmp` comparator combines node-hazard aggregation, reachable-component fraction, directed-percolation fraction, and the six static scores. It excludes all `dmp_` features. The temporal propagator remains its own univariate comparator and is not silently added to the multivariate feature set.

Exploratory records fit coefficients. Calibration records fit PAVA maps and severity interval widths. Comparator choice uses leave-one-block-out calibration crossfit, after which the selected final-size and initiation comparators are refit with full calibration data. Held-out records are prediction-only until final evaluation.

Binary fitting and pooled held-out evaluation require both outcome classes. `Stage3BExperimentResult` records `heldout_binary_support_by_block` and `valid_binary_support_blocks`. The top-level runner persists that mapping and requires both outbreak classes in every held-out block as a three-state acceptance criterion.

The DMP conditional-independence assumption and every scalar comparator are model assumptions. DMP output is an estimate even when an observed sparse input is retained exactly. No current result establishes predictive superiority.

Predictive metrics implement tie-aggregated precision-recall AUC: observations with equal scores are accumulated at one threshold before trapezoidal integration. Log-loss scoring clips probabilities to `[1e-6, 1 - 1e-6]`. Calibration intercept and slope use an internal `[1e-8, 1 - 1e-8]` logit-transform clip. Brier score, AUCs, reliability, and exported predictions use the original bounded values.

### 7.3 Isolation verification gate

Implemented tests verify that:

- no predictor signature accepts `_LatentSystem`, generator RNG state, or realized `AttackEvent` values;
- graph, process, observation, and replication seeds are distinct and traceable;
- predictor features are materialized before outcome replication and do not consume the outcome replication seed;
- held-out identifiers and seeds cannot enter fit, calibration, model selection, or threshold selection;
- outcome labels are joined only after predictor feature materialization;
- serialized predictor input cannot contain forbidden latent fields; and
- common-cause priors remain distinct from realized common-cause events;
- tied-score precision-recall AUC, log-loss clipping, DMP-only primary features, non-outbreak fitting, and calibration crossfit follow their declared contracts.

The structural audit in `docs/stage3_generator_predictor_independence_audit.json` is narrower than these runtime properties. It records a source-and-interface review and asserts that no identical fitted latent equation was found. It does not establish statistical independence, external validity, implementation security, or absence of every possible leakage path. The audit and its reviewed source files become authoritative only when hash-bound by an explicitly authorized preexecution manifest. Any reviewed-source change invalidates that frozen review.

### 7.4 Paired defense design

Held-out Stage 3B cells contain `nominal` and `detection_response_shift` cases for every base pair. The pair shares the graph, process, observation, and base replication seeds. The shifted case intentionally changes detection probability, quarantine delay, revocation delay, and partition probability. Because detection probability participates in construction of detection propensity, the design is paired on seed inputs and declared structural cell, not identical in every latent or observed value.

`defense_pair_record_id` joins the same replication index across the two cases. Pair completeness is an explicit three-state acceptance criterion. Calibration-slope change is then evaluated across defense case and, separately, segmented versus unsegmented held-out records; missing class support makes the corresponding slope criterion `not_evaluable`, never passed.

## 8. Partitions, selection, and protocol compilation

The preregistered partitions are:

| Partition | Fleet size | Intended use |
|---|---:|---|
| Training, called `exploratory` by the Stage 3B model API | 100, 250, 500 | Fit candidate parameters only. |
| Calibration | 750 | Select comparator, mappings, thresholds, and hyperparameters only. |
| Held out | 1,000 and 10,000 | One-time final evaluation and adjudication. |

Five structural blocks are required. Confirmatory replication counts are 12 per Stage 3A scenario and 10 per Stage 3B scenario. Two-replication engineering pilots are excluded from confirmation.

The integrated compiler now owns the naming translations: manifest `training` maps explicitly to Stage 3B `exploratory`, manifest `held_out` maps explicitly to Stage 3B `heldout`, Stage 3A uses the exact resource and admission enums, and the attack generator supports all four configured topology names. Unknown enum values fail during construction.

Stage 3A per block contains 30 training, 30 calibration, and 360 held-out scenarios. Stage 3B across all five blocks contains 90 exploratory, 30 calibration, and 120 held-out scenario specifications. Stage 3B topology and segmentation use distinct deterministic rotation indices. Every split and block contains all four available topology x segmentation cells. Each attack class sees both topologies and both segmentation policies across the five blocks, but only two of the four joint cells for that attack class. Only the two held-out defense cases are paired within each base cell.

The seed manifest provides one globally distinct graph, process, observation, and replication base seed for each block and manifest partition. Runtime derivation uses these exact domain strings:

```text
pilot-stage3a
confirmatory-stage3a
pilot-stage3a-bootstrap
confirmatory-stage3a-bootstrap
pilot-stage3b
confirmatory-stage3b
pilot-stage3b-bootstrap
confirmatory-stage3b-bootstrap
```

Stage 3A derives per-replication seeds from the track root seed, randomization-pair identifier, and replication index. Stage 3B derives each scenario's four named seeds from its manifest base plus deterministic scenario offset, then derives each outcome replication seed from the scenario replication seed and replication index. Tests verify that pilot and confirmatory derived seed sets are disjoint for the compiled design.

Calibration selects the strongest baseline without inspecting held-out results. Held-out data is used once. Acceptance remains the conjunctive rule in `docs/stage3_preregistered_protocol.md`; secondary or favorable subgroup results cannot override a failed primary condition.

Every criterion uses `passed`, `failed`, or `not_evaluable`. `_all_criteria_pass` returns true only when every status is `passed`. Nonfinite reported values are serialized as JSON `null`, not `NaN`; missing metric prerequisites are never silently promoted to success.

## 9. Immutable outputs and provenance

The implemented run layout is:

```text
results/stage3/<protocol_hash>/<execution_id>/
    execution_started.json
    stage3a/
        block-<b>/<training|calibration|held_out>/
            raw/stage3a_replications.parquet
            derived/stage3a_scenarios.parquet
            traces/stage3a_resource_timeseries.parquet
            traces/stage3a_admission_timeseries.parquet
            stage3a_summary.json
            execution_manifest.json
    checkpoints/stage3b/scenario-<index>.parquet
    stage3b/traces/
        stage3b_lifecycle_timeseries.parquet
        stage3b_dmp_state_summary.parquet
        stage3b_graph_evidence.json
        stage3b_trace_selection.json
    raw/
        stage3a_replications.parquet
        stage3b_scenario_specifications.parquet
        stage3b_replications.parquet
        stage3b_failed_scenario_<index>.json       [ON SCENARIO FAILURE]
    derived/
        stage3a_heldout_predictions.parquet
        stage3b_heldout_predictions.parquet
    stage3_evidence.json                          [ON COMPLETION]
    execution_manifest.json                       [ON COMPLETION]
    execution_failure.json                        [ON WRAPPED FAILURE]
```

The protocol guard reserves a new directory with `exist_ok=False`; existing executions cannot be overwritten. Stage 3A and calibration writers also refuse existing destinations. `execution_started.json` captures environment, command, runtime budget, mode, and identifiers before simulation. The preexecution protocol hash authenticates the frozen file set, exact execution contract, and numerical environment snapshot. Confirmatory execution compares the live Python, platform, machine, package versions, and thread controls before creating an output directory. Confirmatory evidence carries every frozen-input check and the frozen execution contract. Engineering pilots carry a nonauthoritative SHA-256 snapshot of the same draft input closure and remain excluded from adjudication. The final manifest inventories every retained file, except itself, with repository-relative path, byte count, and SHA-256 digest.

Stage 3B writes the expanded scenario-specification table before scenario execution and a Parquet checkpoint after each successful scenario. Wall time, resident memory, and accumulated output size are checked after every scenario checkpoint. A scenario exception writes its specification and exception context before propagating failure. The wrapper then inventories retained artifacts and writes `execution_failure.json`. A crash or failure leaves the directory intact and no in-place resume is implemented.

Completed Stage 3B records preserve graph, process, observation, and replication seeds; defense parameters; attack-trace digest; event count; event-type counts; and first and last step by event type. Full event streams are not retained by the integrated runner. The runner uses `materialize_stage3b_console_trace` to retain one fixed visualization-only held-out projection per block. Selection is configured before outcomes by fleet size, attack class, defense case, replication index, and lexical scenario order. The retained projection includes exact synthetic lifecycle summaries, estimated DMP state summaries, a bounded graph of the predictor's observed view, selection metadata, and the attack-trace digest used for regeneration verification.

Representation labels have precise meanings:

- `exact`: complete retained values for the represented model state and interval;
- `sampled`: a declared subset selected from a larger exact trace;
- `aggregated`: a statistic computed from multiple states, agents, edges, or replications;
- `estimated`: output of an estimator or approximation such as DMP;
- `observed`: an outcome retained from the synthetic execution;
- `predicted`: a fitted or ex-ante model value;
- `unavailable` or `not retained`: evidence the source execution did not retain and the console will not reconstruct.

These labels describe representation, not accuracy relative to an operational fleet.

## 10. Sparse scaling and performance boundary

Stage 3A uses count-based state with approximate storage and compute proportional to `R x T`, where `R = 10`. Fleet size changes load magnitude but does not allocate one state object per agent. This makes 10,000-agent admission studies tractable, but it omits agent-specific prerequisite state and contention topology.

Stage 3B stores directed layers and the transmission operator as sparse CSR structures. With bounded mean degree, graph storage is approximately `O(N + E)`, and each DMP step is approximately `O(N + E)`. Retaining node and edge messages for many capture steps increases memory to approximately `O(K(N + E))`, where `K` is the number of retained steps. Sparse storage does not by itself prove acceptable wall time or memory at 10,000 agents.

Retained engineering pilots establish fail-closed behavior and engineering feasibility but do not establish the confirmatory 10,000-agent performance envelope. Pilot 01 failed during strict serialization of a metric without class support; the corrected implementation records undefined metrics as JSON `null` and makes the associated criterion `not_evaluable`. Pilot 02 stopped at 180.362 seconds after Stage 3B scenario 191 of 240 under the former 180-second engineering limit. Pilot 03 then completed the full two-replication matrix in 190.686 seconds with 189.544 CPU seconds, 1,133.234 MB peak resident memory, and 17.274 MB of artifacts before final evidence. It retained all 240 Stage 3B scenario checkpoints and five fixed visualization traces. All three pilot directories remain excluded from confirmation.

The current engineering-pilot limits are 300 seconds, 2,048 MB peak resident memory, and 250 MB of output. The wall limit was increased from 180 to 300 seconds using pilot resource evidence only. The confirmatory limits remain 1,800 seconds, 4,096 MB peak resident memory, and 1,500 MB of output. This resource-only adjustment changes no hypothesis, model, partition, replication count, estimand, statistical method, or acceptance criterion.

Pilot 03 recorded these pre-confirmation engineering checks:

- end-to-end wall time, CPU time, peak resident memory, and output size for the two-replication engineering matrix;
- completion of all 240 Stage 3B scenario checkpoints;
- 205 lifecycle rows and 205 estimated DMP-state rows across five fixed visualization traces;
- a canonical graph projection sampled from 500 of 1,000 observed-view nodes and 2,000 of 2,955 eligible retained-node edges, with 13,433 directed layered edges in the source graph;
- successful verification of all 341 execution-manifest artifact hashes;
- seed and attack-trace-digest agreement between the five visualization traces and their raw records; and
- successful construction of the offline replay console with every optional trace and graph artifact available and no loader warnings.

Pilot 03 did not record timing or resident-memory profiles stratified by track, fleet size, topology, or representation. It also did not test deterministic equivalence across worker counts or execution orders, and it did not exercise the ten-replication confirmatory resource envelope. Those checks remain required before a larger-scale or parallel execution claim.

Fleet sizes 30,000 and 100,000 are outside the current protocol. They require a new preregistration and a validated approximation path, not an extrapolation from 10,000.

## 11. Replay and console read-only boundary

Stage 2 event-log replay remains a separate canonical-event and state-hash mechanism. The implemented Stage 3 console is an artifact viewer. It does not replay hidden generator state or recompute the adjudicated scientific metrics.

Replay mode loads one completed Stage 3 evidence directory. Comparison mode overlays bounded projections from two completed directories. Live mode first creates a new bounded immutable visual-demonstration directory, waits for execution to complete, and then animates its retained evidence. Live mode is labeled `synthetic_model_demonstration_only`; it is not the protocol-gated confirmatory runner. The offline browser can export a bounded run request, but it cannot execute that request or modify an existing run.

The console:

- requires `stage3_evidence.json` and reads the execution manifest, retained Parquet tables, Stage 3A time traces, and optional Stage 3B lifecycle or graph artifacts;
- verifies the digests of loaded artifacts when they are listed in the manifest and within the console hashing limit, while visibly reporting missing manifests, unlisted files, size-limited checks, and mismatches;
- writes HTML and JSON exports outside source execution directories and refuses unsafe overwrite;
- embeds Plotly in a self-contained HTML file and performs no runtime network access;
- labels exact, sampled, aggregated, observed, predicted, estimated, unavailable, and not-retained representations;
- exposes DMP-state availability separately from lifecycle and graph availability, labels the DMP values `estimated`, and labels row retention `exact` or `sampled`;
- plots retained DMP susceptible, compromised-undetected, detected, quarantined, revoked, and recovered fractions together with retained edge no-transmission, edge source-active, and common-cause survival means;
- places the five trace-backed Stage 3B scenario identifiers before summary-only scenarios so the initial selection has retained temporal evidence;
- binds the one retained canonical graph to its source `scenario_id` and renders an explicit unavailable state for every nonmatching selection;
- renders calibration-fitted lower and upper bounds for expected-final estimates when present and labels rows without those fields `interval not retained`;
- derives a display-only wait-budget trace as retained wait divided by retained `Omega`, labels it derived, and does not feed it into adjudication;
- preserves visual filtering as presentation state and does not use it for model selection or acceptance; and
- marks optional lifecycle, DMP, or graph views unavailable when their source evidence is absent or unreadable rather than reconstructing them from scalar summaries.

The integrated runner now supplies fixed Stage 3B visualization projections for completed executions. DMP state trajectories and the canonical graph are shown for the primary execution only; comparison mode does not currently overlay a second execution's DMP trajectory or graph. A failed execution that never produced `stage3_evidence.json` remains preserved through `execution_failure.json` and checkpoints but is not loadable by the current console. The console is a generated static file, not a listening service. Remote hosting or multi-user access would require a separate threat model, authentication, authorization, transport protection, audit, and deployment hardening.

## 12. Failure handling and recovery

| Failure | Required behavior |
|---|---|
| Missing or changed frozen input | Abort before simulation and record every mismatch. |
| Missing, duplicated, or reused seed | Abort the affected matrix before execution. Do not generate a replacement seed. |
| Invalid measurement or configuration | Reject with field, row, or path context. Do not coerce silently. |
| Nonfinite scientific input, state, or predictor | Fail the affected execution and retain diagnostics. Never serialize `NaN` as valid evidence. |
| Metric undefined because class or cell support is absent | Serialize the metric as JSON `null` and mark its criterion `not_evaluable`. Never promote it to a pass. |
| Generator-predictor boundary violation | Abort Stage 3B and invalidate the affected execution. |
| Output directory collision | Refuse execution. Never resume into an ambiguous directory. |
| Resource limit reached | Complete the current atomic Stage 3A partition or Stage 3B scenario checkpoint, stop at the next runtime check, and record the stop reason and resource use. |
| Process crash or partial write | Preserve the partial directory and write the wrapper failure artifact when possible. Any retry uses a new execution identifier. |
| Missing outcome class or invalid block | Mark the criterion not evaluable or failed according to protocol. It is never a pass. |
| Rendering or console error | Fail presentation only. Do not change scientific evidence or rerun a seed automatically. |

The current runner does not resume in place and does not import prior checkpoints into a retry. Stage 3A writes immutable block-partition artifacts, and Stage 3B writes one immutable Parquet checkpoint after each successful scenario. A future checkpoint-reuse design would require a new execution directory, exact frozen-hash and seed verification, source-execution linkage, and an explicit provenance rule. It is not part of this protocol version.

## 13. Security and assurance considerations

1. **Research integrity boundary.** Hash verification, disjoint partitions, no-replace outputs, and evidence labels protect experimental integrity. They do not prove application or operational security.
2. **Untrusted data.** Local CSV and Parquet inputs require schema and semantic checks. Before accepting operational data, add explicit file-size and row-count limits, decompression limits, allowed-root and symlink handling, and provenance authorization.
3. **Path safety.** Frozen inputs must remain repository-relative, traversal-free paths. Output paths must be derived from validated identifiers, not user-controlled shell fragments.
4. **Latent-state confidentiality.** Generator-only state is research-sensitive because leakage invalidates the experiment. It must remain private to the generator process or module boundary and must not appear in logs, exceptions, serialized records, or console payloads.
5. **Availability.** Sparse inputs can still be adversarially dense. Enforce node, edge, horizon, capture-step, trace-row, memory, wall-time, and artifact-size budgets before allocation.
6. **Determinism.** Record named seeds and deterministic reduction order. Cross-platform byte identity must be reported separately from numerical tolerance, as demonstrated by the Stage 2 Cycle 7 handoff check.
7. **Secrets and network.** Scientific runtime must use no secrets and make no network calls. Dependency retrieval occurs before freeze in the controlled build environment.
8. **Local presentation.** The console is a self-contained offline HTML artifact and does not open a network listener. Remote hosting or multi-user service exposure requires a separate threat model and production controls.
9. **Evidence minimization.** Store only the traces required for reproducibility and review. Bounded sampling reduces data volume but must preserve its selection rule and representation label.
10. **Operational claims.** Synthetic success cannot be represented as fleet authorization, safe operating limit, deployment readiness, or resistance to a real adversary.

## 14. Principal tradeoffs

| Decision | Benefit | Cost or risk | Revisit trigger |
|---|---|---|---|
| Aggregate Stage 3A queues | Population-independent state size and interpretable resource saturation. | No per-agent prerequisite or routing state. | Evidence shows dependency order or partial completion changes outcomes. |
| Planned acyclic admission DAG | Explicit prerequisites and causal blocking without admission-cycle ambiguity. | More state, join semantics, and recovery complexity. | Before any multi-stage dependency claim. |
| Separate Stage 3B generator and predictor view | Reduces latent-equation leakage and makes prediction tests meaningful. | Observability assumptions must be modeled and audited. | Any new feature or generator mechanism. |
| Sparse directed DMP | Preserves direction and node or edge dynamics at useful scale. | Conditional-independence approximation and potentially large edge-message state. | Calibration failure, dense graphs, or larger horizons. |
| Calibration-selected simple baseline | Prevents comparison against a conveniently weak baseline. | Selection consumes calibration information and must be frozen. | Any comparator-set change. |
| Seed-aligned Stage 3A cells and paired Stage 3B defense cases | Reduces stochastic noise in declared contrasts. | Shared seeds do not guarantee identical realized variates or identical latent state after workload or defense parameters change. | Any randomization-unit or defense-construction change. |
| Leave-one-block-out Stage 3B calibration crossfit | Estimates comparator selection performance without scoring a block on its own calibration map. | Uses less calibration data per fold and still depends on the declared five-block structure. | Any block-count, mapping, or comparator-set change. |
| Immutable run directories | Strong provenance and no silent replacement. | Partial runs consume storage and resume is less convenient. | Storage pressure or distributed execution. |
| Bounded trace retention | Controls artifact growth while retaining selected transition evidence. | Sampled traces cannot support every post hoc analysis. | A required diagnostic is not reconstructable. |
| Offline, read-only console | Keeps presentation outside scientific authority. | No interactive mutation or ad hoc metric recomputation. | A separately governed execution-control service is approved. |

## 15. Items to revisit beyond 10,000 agents

Before increasing scale, revisit all of the following as explicit architecture decisions:

- validate aggregate Stage 3A behavior against a smaller agent-resolved prerequisite model;
- quantify approximation error for DMP and any mean-field or graph-coarsening method by topology and attack class;
- replace in-memory result assembly with partitioned, streaming Parquet writes and atomic dataset manifests;
- bound graph construction, spectral computation, event queues, bootstrap resampling, and retained DMP states;
- define deterministic parallel partitioning and reduction across processes or hosts;
- evaluate 64-bit identifier, count, and offset limits;
- separate compute placement from evidence custody and define worker attestation;
- introduce checkpoint provenance without permitting artifact mutation;
- quantify console sampling error and prevent browser memory from setting scientific retention policy;
- recalibrate capacity nonlinearities, correlated arrivals, dependency fan-in, and retry storms with authorized measurements;
- reassess privacy and classification of node-level traces; and
- create a new preregistered protocol with scale-specific resource limits and acceptance criteria.

No result at 100, 1,000, or 10,000 agents authorizes a claim at 30,000 or 100,000 agents without that work.

## 16. Pre-freeze completion gates

The core matrix compiler, partition guards, Stage 3A and Stage 3B models, protocol-gated runner, three-state adjudicator, immutable artifact writers, per-scenario checkpoints, resource monitor, fixed visualization-trace writer, and offline console are implemented. The prerequisite DAG is explicitly deferred, and claims in this document are constrained to the current parallel aggregate queue model. The calibration-bundle adapter also remains planned; confirmatory execution therefore remains synthetic and calibration-interface-only.

Stage 3 remains pre-freeze until all of these remaining gates close:

1. Complete focused and full regression verification against the final source and document set.
2. Reconcile every explicit file and test glob in `configs/stage3/protocol.yaml`, including the completed Pilot 03 log and the structural boundary audit.
3. Keep the calibration adapter and prerequisite DAG explicitly deferred unless they are implemented and verified before freeze. Do not broaden the evidence claim if they remain deferred.
4. Obtain explicit user authorization to change protocol state from `engineering_draft` and generate `manifests/stage3_preexecution_manifest.json` with the frozen execution contract.
5. Verify every frozen digest and abort before simulation on any mismatch.
6. Execute confirmation once under the new frozen execution identifier.
7. Adjudicate every fixed criterion without retuning and produce the evidence ledger, decision table, acceptance status, report, traceability update, and console from immutable artifacts.

Until gate 6 completes, all performance and scientific results are engineering evidence only. Until the fixed acceptance rules are adjudicated, the correct language is `not yet evaluated`, not `supported` or `confirmed`. Pilot 03 produced `not_supported_under_preregistered_rule` for both tracks under two-replication engineering settings; those dispositions are excluded from confirmation and do not pre-adjudicate the confirmatory run.

## 17. Controlling references

- `docs/STAGE3_HANDOFF_VERIFICATION.md` records the local Stage 2 handoff verification and conditional-GO basis.
- `BASELINE_PROVENANCE.json` binds the immutable baseline path and verified package provenance.
- `docs/stage3_preregistered_protocol.md` defines the current confirmatory hypotheses, partitions, acceptance rules, stopping rules, and freeze sequence. Its status remains `Engineering draft`.
- `docs/stage3_generator_predictor_independence_audit.json` records the narrow source-and-interface structural review. It becomes authoritative only when its digest and reviewed source digests are frozen together.
- `docs/stage3_engineering_pilot_log.md` records retained pilot failures, corrective actions, the 300-second engineering limit, and their exclusion from confirmation.
- `configs/stage3/protocol.yaml` is the machine-readable protocol input. Its status remains `engineering_draft`, and no preexecution manifest exists.
- `configs/stage3/compute_budget.yaml` defines the 300-second engineering-pilot limit and unchanged 1,800-second confirmatory limit.
- `manifests/stage3_seed_manifest.csv` is the declared seed source and must be bound into the final preexecution manifest.

If this document conflicts with a completed preexecution manifest, execution must stop. The discrepancy must be resolved by a new documented protocol version rather than by interpreting the manifest after outcomes are known.
