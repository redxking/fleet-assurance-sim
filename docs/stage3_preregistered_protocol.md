# Stage 3 Preregistered Protocol

**Protocol ID:** FAS-S3-C1-2026-08-19  
**Protocol version:** 1.0  
**Status:** Frozen for confirmatory execution  
**Evidence scope:** Synthetic, model-conditioned confirmatory research with calibration-interface verification only  
**External operational measurements supplied:** No

The user-authorized Stage 3 continuation requires a preexecution manifest and confirmatory execution. Following the completed Pilot 05 review and final regression checks, this protocol is frozen for confirmatory execution. Engineering-pilot artifacts, including failed artifacts, are excluded from confirmatory adjudication.

## 1. Purpose and evidence boundary

Stage 3 evaluates two candidates that survived Stage 2 without formal confirmation. It does not revisit the refuted NH2-D dynamic scalar or the refuted, training-selected NH2-T infection propagator. Those negative results remain part of the evidence record.

The study has two tracks:

1. Stage 3A tests whether an ex-ante projection of assurance-resource overload predicts a separately calculated synthetic operational-assurance label across fleet scale, admission trajectory, resource architecture, capacity, and workload shifts. The label expression does not consume `Omega_A`, but the projection and outcome simulator share the same declared trajectory and synthetic resource specifications. This is definition separation, not statistical or generator independence.
2. Stage 3B tests whether separately estimating outbreak initiation, outbreak severity, and non-outbreak severity improves held-out prediction against the strongest calibration-selected comparator. The outcome generator and predictor are separate implementations, but the predictor intentionally consumes noisy observed proxies derived from generator constructs.

All fleet workloads, resource parameters, graphs, defenses, and attack traces in this protocol are synthetic and notional. Calibration-tool execution against the included template establishes interface behavior only. No result may be described as external validation, operational calibration, deployment assurance, or proof of implementation security.

## 2. Fixed scientific integrity controls

- Training, calibration, and held-out seeds are disjoint and listed in `manifests/stage3_seed_manifest.csv`.
- Engineering pilots and confirmation use SHA-256 domain separation. The exact domains are `pilot-stage3a`, `confirmatory-stage3a`, `pilot-stage3a-bootstrap`, `confirmatory-stage3a-bootstrap`, `pilot-stage3b`, `confirmatory-stage3b`, `pilot-stage3b-bootstrap`, and `confirmatory-stage3b-bootstrap`. Stage 3B graph, process, observation, and replication bases remain separately named and globally distinct in the seed manifest before domain derivation.
- Bootstrap base seeds are fixed at `390260819` for Stage 3A and `490260819` for Stage 3B. The execution evidence records the domain-derived Stage 3A seed, the domain-derived Stage 3B final-size seed, and the exact Stage 3B outbreak-Brier seed obtained by adding one to the latter. Stage 3A raw rows record each derived replication seed; Stage 3B scenario specifications and raw rows record graph, process, observation, base replication, and derived replication seeds.
- Training or exploratory data fits model coefficients. Calibration data alone fits monotone probability and severity mappings, interval widths, thresholds, and comparator selection scores. Held-out data is used once for final adjudication.
- The strongest baseline is selected on calibration data, never on held-out performance.
- Confirmatory execution may begin only after `manifests/stage3_preexecution_manifest.json` is created and every frozen input matches.
- The authenticated manifest binds the freeze-time Python, platform, machine, package versions, and numerical thread controls. Confirmation aborts before output-directory creation unless the live environment exactly matches that snapshot.
- `BASELINE_PROVENANCE.json` is a frozen controlling input that binds Stage 3 to the verified immutable Stage 2 parent archive and evidence record.
- A frozen-input mismatch aborts before simulation.
- Every execution uses a new run-specific directory. Existing result directories are never overwritten.
- Failed and null results remain in the evidence ledger.
- Nonfinite scientific inputs, predictor values, or model state cause an explicit failure. Metrics that are mathematically undefined because required class or cell support is absent are serialized as JSON `null` and their criteria are `not_evaluable`, never passed.
- Stage 3B predictor code receives only `ObservedSystemView`. Generator-only latent states, exact hidden edge properties, random draws, and realized causal events are excluded by interface. This boundary does not make the observed proxies statistically independent of the generator.
- Byte-level artifact integrity and cross-platform numerical equivalence are reported separately.
- The visual console consumes evidence artifacts and cannot mutate simulation state or scientific metrics.

## 3. Stage 3A hypothesis and system model

### 3.1 Primary hypothesis

For a declared admission trajectory and resource model, the ex-ante candidate

\[
\widehat{\Omega}_A
=
\max_{r,t}
\frac{\widehat{Q}_r(t)}{C_r W_r}
\]

will improve held-out prediction of the separately calculated operational-assurance label relative to the strongest calibration-selected simple comparator.

The candidate is computed before stochastic execution from the declared trajectory, resource workload, effective capacity, and wait budget. The stochastic operational label does not read the projected or observed `Omega_A` fields. Both paths nevertheless use the same declared synthetic resource model and closely related queue quantities, and the simulator uses its prior-step observed queue ratio to activate recovery capacity. Observed queue-boundary crossing is a secondary diagnostic, not the primary label. No external independence claim is permitted.

### 3.2 Resources

The resource workflow includes identity issuance, certificate issuance and renewal, authorization-policy evaluation, task-dispatch registration, telemetry-source registration, evidence-ingest initialization, supervisory review, revocation readiness, configuration attestation, and dependency registration. Each resource declares its arrival process, work per admitted agent, service capacity, queue state, service-time distribution, maximum acceptable wait, overload or shedding behavior, recovery behavior, and measurement provenance.

### 3.3 Admission conditions

Base profiles are step, linear ramp, staged ramp, exponential growth, bursty, periodic, and closed-loop. Sybil admission, mass restart, and mass credential renewal are modeled as explicit disturbance profiles. Comparisons include equal-final-population fleets with different trajectories.

### 3.4 Primary and secondary outcomes

The primary binary outcome is operational assurance failure. Its fixed Boolean expression uses deadline misses, work shedding, incomplete-assurance exposure, useful-throughput loss, failure to reach the target population, and failure to recover within the fixed recovery window. It does not reference `Omega_A`. Because these quantities and `Omega_A` share the trajectory and resource specifications, the outcome is definition-separated from the candidate but not generated from an independent physical model.

Secondary outcomes are queue instability, authorization latency, telemetry-registration delay, credential-issuance delay, supervisory saturation, revocation-readiness delay, deadline misses, work shedding, recovery time, useful task throughput, compromise exposure during incomplete admission, and observed queue-budget crossing.

### 3.5 Comparators

The eight simple scalar comparators are final fleet size, peak admission rate, mean admission rate, projected peak utilization, projected maximum queue depth, total admitted agents, projected backlog area, and projected maximum deadline-miss fraction. Each receives a monotone PAVA mapping fitted on calibration data. The strongest simple comparator is selected by leave-one-scenario-out cross-fitted calibration mean squared error. An interpretable multivariate logistic baseline fits coefficients on training data and a monotone mapping on calibration data; it is reported separately and is not eligible to replace the preregistered strongest-simple primary baseline. Realized held-out outcomes and observed `Omega_A` are not predictor inputs.

### 3.6 Factorial design, paired randomization, and capacity scaling

The Stage 3A compiler creates these cells per structural block:

- Training: 3 fleet sizes x 10 profiles x one assigned architecture, capacity, and workload point, for 30 scenarios.
- Calibration: 1 fleet size x 10 profiles x the assigned `sharded_balanced` architecture x 3 capacity multipliers x Poisson workload, for 30 scenarios.
- Held out: 2 fleet sizes x 10 profiles x 3 architectures x 3 capacity multipliers x 2 workloads, for a full 360-scenario factorial.

Across five blocks, the fixed design contains 2,100 scenarios before replication, including 1,800 held-out scenarios. Confirmatory execution uses 12 replications per scenario.

`randomization_pair_id` is fixed by block, partition, fleet size, and admission profile. Calibration capacity cells, and all held-out architecture, capacity, and workload cells within that identifier, use the same replication seed for a given replication index. This is seed-aligned paired randomization. It does not imply identical realized variates when the selected workload distribution changes.

Default resource capacity is proportional to final fleet size before architecture adjustment. The implemented adjustment is

\[
C_r'(N)=C_r(N)\,a_r\left(\frac{\max(N,N_{ref})}{N_{ref}}\right)^{\alpha},
\qquad N_{ref}=1000.
\]

`centralized_balanced`, `centralized_control_constrained`, `sharded_balanced`, and `pipelined_proportional` use `alpha = 0`. `sharded_sublinear_capacity` uses `alpha = -0.20`, so its large-scale capacity grows approximately as `N^0.80` relative to the proportional base after `N = 1000`. The architecture factor and capacity multiplier remain separate declared inputs.

### 3.7 Calibration, eligibility, and acceptance

Within each block, the candidate PAVA map, every simple-comparator PAVA map, strongest-simple selection, and `Omega_A` threshold are calibration-only. The multivariate coefficients are training-only and its PAVA map is calibration-only. Held-out outcomes do not affect any mapping, threshold, feature set, or comparator choice.

Stage 3A is supported within the declared model only if every condition passes:

1. Both operational-failure classes are present in training, calibration, and held-out data in every block.
2. Held-out Brier score improves by at least 15 percent relative to the calibration-selected strongest simple baseline.
3. The lower bound of the paired, block-aware bootstrap interval for fractional Brier improvement is greater than zero.
4. Held-out ROC AUC is at least 0.90.
5. Calibration slope is between 0.8 and 1.2.
6. Improvement is positive in at least four of five declared structural blocks.
7. The calibration-selected threshold transfers to fleet size 10,000 without refitting and achieves balanced accuracy of at least 0.75 in every block.
8. The same threshold achieves balanced accuracy of at least 0.75 at fleet size 10,000 within `sharded_sublinear_capacity` in every block.
9. Fractional Brier improvement is positive for every unseen held-out architecture.
10. Fractional Brier improvement is positive for both non-reference capacity multipliers.
11. Fractional Brier improvement is positive for the held-out gamma workload.
12. Fractional Brier improvement is positive under the combined architecture, capacity, and gamma-workload shift.

Failure of any condition yields `not supported under the preregistered rule`. Promising secondary metrics may be reported only as provisional or exploratory.

## 4. Stage 3B hypothesis and system model

### 4.1 Primary hypothesis

A phase-separated predictor

\[
\widehat{E[F]}
=
\widehat{P(O)}\widehat{E[F\mid O]}
+
\left[1-\widehat{P(O)}\right]\widehat{E[F\mid \neg O]}
\]

will improve held-out final compromised-fraction prediction and outbreak-probability calibration relative to the strongest calibration-selected eligible comparator.

### 4.2 Separate outcome generator and observed-view boundary

The outcome generator is an event process with directed authorization and communication exposure, shared dependencies and images, credential delegation and replay, identity-provider compromise, supervisory relationships, heterogeneous susceptibility and exploitability, detection, quarantine, revocation, recovery, correlated compromise, time-varying defenses, boundary failure, and network partition or delay.

The generator retains exact hidden simulation state for its own use: latent directed layers, edge resistance and delay, susceptibility, exploitability, detection propensity, common-cause state, identity-provider exposure, selected causal events, random draws, and realized compromise and response state. The predictor instead receives `ObservedSystemView`, which contains edge-missed and edge-augmented sparse layers, noisy susceptibility and exploitability proxies, noisy or declared response-rate proxies, an initial-risk prior, a noisy common-cause hazard vector, segment identifiers, and declared time profiles. Common-cause risk remains an explicit vector and is not converted into pairwise transmission edges.

The two implementations do not reuse an identical fitted latent equation, but they are not statistically independent. Some observed fields are deliberately noisy projections of generator constructs, and some declared profiles are shared. Claims must use `separate generator implementation with a bounded observed view`, not `independent ground truth` or `external validation`.

### 4.3 Directed node-resolved operator

The predictor maintains directed mechanism-specific edge intensities, node-level compromise and response marginals, edge no-transmission messages, edge source-active messages, and common-cause survival by time window. The primary initiation component uses only `dmp_outbreak_probability`. The primary outbreak-severity and non-outbreak-severity components each use only `dmp_expected_fraction`; they are fitted separately. Temporal, node-hazard, reachable-component, directed-percolation, and static scores remain comparators and are not added to the primary candidate.

### 4.4 Estimators and metrics

The primary candidate has three fitted components: outbreak initiation, severity conditional on outbreak, and severity conditional on non-outbreak. Exploratory data fits each component's coefficients. Calibration data alone fits each monotone PAVA mapping and each severity interval half-width. The expected final fraction is

\[
\widehat{E[F]}=
\widehat{P(O)}\widehat{E[F\mid O]}
+
\left[1-\widehat{P(O)}\right]\widehat{E[F\mid \neg O]}.
\]

The non-outbreak term is fitted from non-outbreak records. It is not fixed to `1/N`.

Comparator selection includes univariate temporal propagator, node-hazard aggregation, static adjacency, static non-backtracking, combined scalar, authorization-only, communication-only, and simple-reproduction models. It also includes `interpretable_multivariate_non_dmp`, whose feature set is node-hazard aggregation, reachable-component fraction, directed-percolation fraction, and the six static scores. The multivariate comparator excludes all `dmp_` features. Strongest final-size and strongest initiation comparators may differ.

Every comparator is scored by leave-one-block-out calibration crossfit across the five calibration blocks. Comparator coefficients are fitted on exploratory data in every fold. Monotone mappings and interval widths use the four nonvalidation calibration blocks, and the omitted calibration block supplies the cross-fitted selection score. After selection, only the selected comparator or comparators are refitted with the full calibration partition. Held-out outcomes are accessed only after selection and refit are fixed.

Initiation metrics are Brier score, log loss, ROC AUC, precision-recall AUC, calibration intercept, calibration slope, reliability data, and expected calibration error. Precision-recall AUC aggregates all equal-score observations at each distinct threshold before trapezoidal integration, making the result invariant to permutations within score ties. Log-loss scoring clips probabilities to `[1e-6, 1 - 1e-6]`. The logistic recalibration transform used for calibration intercept and slope clips only its internal logit input to `[1e-8, 1 - 1e-8]` to keep the transform finite. Brier score, AUCs, reliability, and reported predictions use the bounded unmodified probability.

Severity metrics are MAE, RMSE, quantile loss, and prediction-interval coverage for outbreak severity, non-outbreak severity, and unconditional final size. Final-size errors are also reported by topology, fleet size, attack class, segmentation policy, defense case, and structural block.

Binary model fitting and pooled held-out evaluation require both outcome classes. The implementation also records held-out class support by block. A missing class cannot be treated as successful discrimination or calibration evidence.

### 4.5 Structural boundary audit and its limits

`docs/stage3_generator_predictor_independence_audit.json` is a source-and-interface structural review. Its implemented acceptance check requires `status = passed_structural_review` and `identical_latent_equation_reuse_detected = false`. At freeze, the audit and every reviewed source file are hash-bound by the preexecution manifest.

The audit does not prove statistical independence, causal independence, external validity, implementation security, or absence of every possible information path. It explicitly allows the declared noisy observed proxies. Any change to the generator, DMP, phase-separated model, or Stage 3B orchestration invalidates the frozen audit and requires review and a new manifest.

### 4.6 Acceptance rule

Stage 3B is supported within the declared model only if every condition passes:

1. Held-out final-size MAE improves by at least 15 percent over the strongest calibration-selected final-size comparator.
2. Held-out outbreak-probability Brier score improves by at least 10 percent over the strongest calibration-selected initiation comparator.
3. Final-size improvement is positive in at least four of five declared structural blocks.
4. Outbreak-probability Brier improvement is positive in at least four of five declared structural blocks.
5. The paired, block-aware bootstrap lower bound for final-size improvement is greater than zero.
6. The paired, block-aware bootstrap lower bound for outbreak-probability Brier improvement is greater than zero.
7. Without refitting, candidate final-size MAE improvement is strictly positive separately for each unseen topology.
8. Without refitting, candidate final-size MAE improvement is strictly positive separately at fleet sizes 1,000 and 10,000.
9. Every held-out `defense_pair_record_id` contains exactly the nominal and detection-response-shift cases. The pair shares graph, process, observation, and base replication seeds while defense parameters intentionally differ.
10. Both outbreak classes are present in every held-out structural block.
11. The absolute calibration-slope change between nominal and detection-response-shift held-out cases is no greater than 0.20.
12. The absolute calibration-slope change between segmented and unsegmented held-out cases is no greater than 0.20.
13. The frozen structural review passes and detects no identical latent-equation reuse.

Failure of any condition yields `not supported under the preregistered rule`.

## 5. Scale, topology, partitions, and replication counts

- Training fleet sizes: 100, 250, and 500.
- Calibration fleet size: 750.
- Held-out fleet sizes: 1,000 and 10,000.
- Training topologies: random regular and Erdos-Renyi.
- Calibration topologies: independently seeded random regular and Erdos-Renyi.
- Held-out topologies: Barabasi-Albert and hierarchical.
- Stage 3B training contains 90 scenario specifications, calibration contains 30, and held out contains 120 across all five blocks, for 240 specifications before replication. Topology and segmentation use distinct deterministic rotation indices. Every split and block contains all four topology x segmentation joint cells available to that split. Each attack class sees both topologies and both segmentation policies across the five blocks, but only two of the four joint cells for that attack class. This is a fixed fractional-factorial assignment across attack class, not a full attack-class x topology x segmentation factorial within each block.
- Held-out nominal and detection-response cases are evaluated for every attack class. Each defense pair shares graph, process, observation, and base replication seed values. Defense parameters intentionally change detection propensity, quarantine delay, revocation delay, and partition probability, so a pair must not be described as identical latent state.
- Seed-separated structural blocks: five.
- Stage 3A confirmatory replications per scenario: 12.
- Stage 3B confirmatory replications per scenario: 10.
- Engineering-pilot replications per scenario: two, excluded from confirmation.

Fleet sizes 30,000 and 100,000 are excluded from this protocol. Any future aggregate or mean-field path requires separate validation against the agent-based implementation, an approximation-error report, and a new preregistration.

## 6. Statistical methods

Primary comparisons are paired within held-out row and structural block. Confidence intervals use a hierarchical common-random-number bootstrap. It resamples blocks, then declared paired-randomization clusters within sampled blocks, then aligned replication units within sampled clusters while retaining every factor or defense row in the selected unit and keeping candidate and comparator errors together. Stage 3A uses `randomization_pair_id` as the cluster and `replication` as the aligned unit. Stage 3B uses `defense_pair_id` as the cluster and `defense_pair_record_id` as the aligned unit. The confirmatory interval is the percentile 95 percent interval from 5,000 draws. The 200-draw engineering-pilot bootstrap is excluded from confirmation.

The implementation pre-groups paired errors into bounded NumPy batches before resampling. This is an algorithmic execution optimization only. It preserves the declared block, paired-cluster, and aligned-replication hierarchy and does not alter the estimand, pairing, number of draws, interval definition, or seed.

Probability mappings use calibration data only. Log-loss scoring clips probabilities to `[1e-6, 1 - 1e-6]`. Calibration slope and intercept use a logistic recalibration fit where both outcome classes are present; its internal logit transform clips to `[1e-8, 1 - 1e-8]` solely to avoid infinite logits. ROC AUC and tie-aggregated precision-recall AUC are reported only with declared class support. Expected calibration error uses ten fixed equal-width bins. Brier score, AUCs, reliability, expected calibration error, and exported predictions use the original bounded probabilities.

Stage 3A simple-baseline selection uses leave-one-scenario-out cross-fitted calibration error. Stage 3B comparator selection uses leave-one-block-out calibration crossfit. Neither procedure uses held-out outcomes.

Every acceptance criterion is serialized in one of three states: `passed`, `failed`, or `not_evaluable`. A missing class, absent transfer cell, nonfinite prerequisite, or other missing metric support cannot be converted into a pass. Track support requires every criterion to be `passed`; either `failed` or `not_evaluable` produces `not_supported_under_preregistered_rule`. A hard schema, partition, seed, or finite-value violation may abort the run before adjudication and remains a failed execution artifact.

The two track-level hypotheses are co-primary. Holm correction at familywise alpha 0.05 applies to inferential p-values, if used. Acceptance remains the fixed conjunctive rule above and is not replaced by a p-value. Secondary analyses are labeled exploratory and do not alter disposition.

## 7. Stopping rules and compute limits

Engineering pilots stop if wall time exceeds 300 seconds, peak resident memory exceeds 2,048 MB, or outputs exceed 250 MB. Confirmatory execution stops before the next atomic checkpoint if wall time exceeds 1,800 seconds, peak resident memory exceeds 4,096 MB, or outputs exceed 1,500 MB.

The 300-second engineering limit was finalized from retained pilot resource observations. Pilot 02 reached 180.362 seconds at Stage 3B scenario 191 of 240 under the former 180-second limit. Pilot 03 then completed the full two-replication engineering matrix in 190.686 seconds, with 1,133.234 MB peak resident memory and 17.274 MB of artifacts before final evidence. Raising only the engineering-pilot wall limit changes no hypothesis, model, partition, replication count, estimand, statistical method, acceptance condition, or confirmatory limit. All engineering-pilot outcomes and dispositions remain excluded from scientific adjudication.

A run also stops on frozen-input mismatch, missing seed, schema failure, nonfinite scientific state, generator-predictor boundary violation, output-directory collision, or unhandled exception. The runner records `execution_started.json`, environment and command provenance, immutable Stage 3A block-partition artifacts, Stage 3B scenario specifications, one successful Stage 3B Parquet checkpoint per scenario, per-scenario failure JSON when applicable, final raw and derived tables, top-level evidence, and an artifact hash inventory.

Runtime checks occur after every Stage 3A block-partition, after every Stage 3B scenario, and after analysis. The current implementation does not resume in place. A failed or partial directory is retained; any retry uses a new execution identifier. A future checkpoint-resume design would require identical frozen hashes and explicit provenance linking, and is outside this protocol version.

Each engineering pilot records a nonauthoritative SHA-256 snapshot of the same expanded frozen-file closure plus its execution environment. This proves which draft code and configuration the pilot exercised but does not convert pilot output into confirmatory evidence. Pilot track dispositions are always `not_adjudicated_engineering_pilot`; calculated criteria remain engineering diagnostics only.

## 8. Failure handling and adjudication

Invalid or failed scenarios retain their available specification, failure, checkpoint, and artifact context. A block is valid only when all declared seeds terminate, both outcome classes satisfy the applicable metric prerequisites, and no held-out record was used for fitting or selection. Missing support produces `failed` or `not_evaluable` according to the fixed criterion. There is no automatic seed replacement.

The final evidence JSON records every criterion as passed, failed, or not evaluable. `Not evaluable` is not a pass. The technical report includes negative results, deviations, resource usage, threats to validity, and what the study does not establish.

## 9. Visualization controls

The implemented console reads generated evidence JSON, execution manifests, Parquet summaries, Stage 3A traces, and retained Stage 3B lifecycle, DMP-state, and graph projections. It labels views as exact, sampled, aggregated, observed, predicted, estimated, unavailable, or not retained as applicable. DMP state-summary values remain labeled estimated even when every retained row is loaded exactly. The console plots retained node-compartment fractions and retained edge no-transmission, edge source-active, and common-cause survival means. Expected-final estimates use their calibration-fitted lower and upper bounds when those fields are retained; rows without bounds are labeled `interval not retained`. It does not reconstruct missing lifecycle, DMP, interval, or topology evidence. Its HTML embeds Plotly and requires no runtime network access. It can export a bounded JSON projection and a bounded visual-run request. Rendering and export write outside source executions and do not change source hashes.

Live console mode first completes a separate bounded run labeled `synthetic_model_demonstration_only` and then animates retained evidence. It is not a confirmatory execution path. The protocol-gated runner retains one fixed, visualization-only held-out Stage 3B projection per block using a configuration-declared selection rule that does not inspect outcomes. Standard-run projections include lifecycle time series, estimated DMP state summaries, a bounded observed-view graph, selection metadata, and attack-trace digests. Trace-backed scenarios appear first in the selector. The one retained canonical graph is displayed only when its `scenario_id` matches the selected scenario; every other selection is explicitly unavailable. If any optional artifact is absent or unreadable, the console marks the view unavailable or not retained and does not infer it from scalar summaries.

## 10. Freeze and execution sequence

1. Complete implementation and automated tests.
2. Run engineering pilots only, preserve failed pilots, and record resource use and design corrections.
3. Finalize compute limits and this protocol after the engineering-pilot review and before inspecting confirmatory outcomes. The engineering-pilot wall limit is 300 seconds and the confirmatory wall limit remains 1,800 seconds; this resource-only change does not alter scientific acceptance rules.
4. Generate `manifests/stage3_preexecution_manifest.json` and record its protocol hash.
5. Verify all frozen inputs and the authenticated numerical environment snapshot.
6. Execute confirmation once under a new execution identifier.
7. Adjudicate the fixed criteria without retuning.
8. Generate the Stage 3 report, evidence ledger, decision table, acceptance status, traceability update, console, and release package.

The current status is `Frozen for confirmatory execution`. Step 4 is authorized by the user's Stage 3 continuation request and may occur once against the reviewed closure. Changes after step 4 require a new protocol identifier and a new preexecution manifest. The prior manifest and any partial execution remain preserved.
