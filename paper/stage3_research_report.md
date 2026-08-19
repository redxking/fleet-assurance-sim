# Stage 3 Research Report

## Confirmatory Evaluation of Projected Assurance-Resource Overload and Phase-Separated Dynamic Message Passing

**Project:** Formal and Visual Simulation of Secure Multi-Agent Fleet Scaling  
**Protocol:** FAS-S3-C1-2026-08-19, version 1.0  
**Confirmatory execution:** `stage3-confirmatory-20260819-01`  
**Report date:** 2026-08-19  
**Evidence boundary:** Synthetic, model-conditioned confirmatory research with calibration-interface verification only  
**Track dispositions:** Stage 3A `not_supported_under_preregistered_rule`; Stage 3B `not_supported_under_preregistered_rule`

## Abstract

Stage 3 conducted one hash-gated confirmatory execution of two co-primary fleet-assurance hypotheses. Stage 3A tested whether ex-ante projected multi-resource overload, `projected_omega_a`, predicts a separately calculated synthetic operational-assurance label better than the strongest calibration-selected simple comparator across fleet scale, admission profile, architecture, capacity, and workload shifts. Stage 3B tested whether a phase-separated dynamic-message-passing predictor improves outbreak-probability and final-compromise prediction relative to separately selected calibration baselines.

Neither track satisfied its full preregistered conjunctive rule. Stage 3A reduced pooled held-out Brier score from 0.06355470068862228 to 0.04991087241138574, a fractional improvement of 0.2146785073236776. Its paired block-aware bootstrap 95 percent interval for fractional improvement was [0.061698589715370566, 0.3397534586105416], and its ROC AUC was 0.9702029588820625. However, its calibration slope was 0.4539306867708676 rather than the required [0.8, 1.2], and improvement at the non-reference capacity multiplier 1.25 was -0.003672405471146048 rather than positive. Stage 3A therefore remains `not_supported_under_preregistered_rule` despite passing 10 of 12 criteria.

Stage 3B reduced held-out final-size MAE from 0.04918958703703704 for the calibration-selected temporal-propagator baseline to 0.04801817645605284, a fractional improvement of 0.02381419832010778. The 95 percent interval for absolute improvement was [-0.003874748654120741, 0.006453490280560529]. Outbreak Brier score improved from 0.10057552120551853 for the calibration-selected node-hazard baseline to 0.10048888888888889, a fractional improvement of 0.0008613658233260923, with an absolute-improvement interval of [-0.0001989300682397579, 0.0003676186469850001]. Eight of 13 criteria failed, including both minimum-improvement criteria, both bootstrap lower-bound criteria, block consistency for final-size error, detection-response calibration transfer, unseen-scale transfer, and unseen-topology transfer. Stage 3B is `not_supported_under_preregistered_rule`.

The results do not establish a universal Fleet Assurance Law, an operational admission threshold, a validated attack predictor, implementation security, or assurance for a 10,000-agent deployment. They narrow the research direction. Projected cumulative resource stress remains an informative synthetic diagnostic but requires empirical calibration and architecture-specific validation. Phase separation and node-resolved message passing remain useful model architectures, but the tested predictor did not demonstrate the required advantage or transfer.

## 1. Research questions and decisions

Stage 3 addressed two questions.

1. Does an ex-ante projected reflected-backlog measure improve prediction of a definition-separated synthetic operational-failure label across declared admission and resource shifts?
2. Does a phase-separated DMP model improve both outbreak-probability calibration and final compromised-fraction prediction across held-out sizes, topologies, defenses, segmentation conditions, attack classes, and structural blocks?

The confirmatory decisions are:

1. **Stage 3A, NH4-O continuation:** `not_supported_under_preregistered_rule`.
2. **Stage 3B, NH2-H continuation:** `not_supported_under_preregistered_rule`.
3. **Preserved Stage 2 negative result NH2-D:** `refuted_within_current_model`.
4. **Preserved Stage 2 negative result NH2-T selected propagator:** `refuted_within_current_model`.

No engineering-pilot result contributes to these decisions.

## 2. Evidence classification

### 2.1 Verified from the immutable confirmatory artifacts

- The preexecution manifest bound 151 frozen files to protocol hash `b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851`.
- All 151 frozen-input checks matched before the confirmatory execution.
- The final execution manifest has status `completed` and inventories 341 artifacts.
- Stage 3A and Stage 3B each have a complete three-state criterion record. No criterion was `not_evaluable` in this execution.
- The exact track dispositions are `not_supported_under_preregistered_rule` for both tracks.
- The final evidence preserves the Stage 2 NH2-D and selected-propagator NH2-T refutations.

### 2.2 Demonstrated only within the synthetic model

- Projected `Omega_A` improved pooled held-out Brier score relative to the strongest calibration-selected simple comparator and passed the declared architecture, workload, combined-shift, discrimination, block, and threshold-transfer checks.
- The same candidate failed the fixed probability-calibration range and failed to improve at capacity multiplier 1.25.
- The phase-separated DMP candidate improved pooled final-size MAE and outbreak Brier score only slightly, with both paired bootstrap intervals crossing zero.
- Stage 3B transfer was not positive at fleet size 10,000 or on the Barabasi-Albert topology.
- The source-and-interface audit found no identical fitted latent equation reused between generator and predictor in the frozen reviewed implementation.

### 2.3 Not established

The execution does not establish external validity, statistical independence between generated outcomes and observed proxies, operational calibration, causal identification, implementation security, deployment assurance, mission suitability, or a secure fleet-size limit.

## 3. Formal constructs and boundaries

### 3.1 Stage 3A projected overload

For assurance resource \(r\), the ex-ante candidate is

\[
\widehat{\Omega}_A
=
\max_{r,t}
\frac{\widehat{Q}_r(t)}{C_r W_r},
\]

where \(\widehat{Q}_r(t)\) is projected reflected queue work, \(C_r\) is declared capacity, and \(W_r\) is the declared wait budget. The operational-failure label uses deadline misses, shedding, incomplete-assurance exposure, useful-throughput loss, target-population attainment, and recovery-window completion. Its Boolean expression does not consume projected or observed `Omega_A`.

This is definition separation, not external or strong generator independence. The predictor and outcome paths share the declared synthetic admission trajectory and resource specifications. The simulator also uses prior-step observed queue ratio to activate modeled recovery capacity. The result therefore tests predictive transfer inside one declared synthetic resource model.

Capacity begins with a proportional fleet-size base and applies

\[
C'_r(N)=C_r(N)a_r
\left(
\frac{\max(N,N_{ref})}{N_{ref}}
\right)^\alpha,
\qquad N_{ref}=1000.
\]

Only `sharded_sublinear_capacity` uses \(\alpha=-0.20\), producing approximately \(N^{0.80}\) growth after \(N=1000\). Other declared architectures use \(\alpha=0\).

### 3.2 Stage 3B phase-separated DMP

The predictor estimates

\[
\widehat{E[F]}=
\widehat{P(O)}\widehat{E[F\mid O]}
+
\left[1-\widehat{P(O)}\right]\widehat{E[F\mid \neg O]}.
\]

The three primary components use only `dmp_outbreak_probability` for initiation and separately fitted `dmp_expected_fraction` mappings for outbreak and non-outbreak severity. The non-outbreak term is fitted rather than fixed at \(1/N\).

The event generator retains hidden directed layers, resistance, delay, susceptibility, exploitability, detection propensity, common-cause state, identity-provider exposure, selected events, random draws, and realized state. The predictor receives only `ObservedSystemView`, including noisy or declared proxies, observed sparse layers, and declared response profiles. The frozen structural audit reports no identical fitted latent equation reuse. It does not prove statistical independence, causal independence, external validity, or the absence of every information path.

### 3.3 Fitting and evaluation boundary

Training or exploratory partitions fit coefficients. Calibration partitions alone fit monotone PAVA mappings, interval widths, thresholds, and comparator selection scores. Stage 3A selects its strongest simple baseline by leave-one-scenario-out cross-fitted calibration mean squared error. Stage 3B selects final-size and initiation comparators by leave-one-block-out calibration crossfit. Held-out outcomes are used only for final adjudication.

Stage 3B precision-recall AUC aggregates equal-score observations before trapezoidal integration. Log loss clips probabilities to `[1e-6, 1 - 1e-6]`. The logistic recalibration transform uses `[1e-8, 1 - 1e-8]` internally to keep logits finite. Every acceptance criterion has one of three states: `passed`, `failed`, or `not_evaluable`. Only an all-passed track is supported.

## 4. Confirmatory design and execution integrity

### 4.1 Stage 3A design

Each of five structural blocks contained 30 training scenarios, 30 calibration scenarios, and a 360-scenario held-out factorial. The held-out factorial crossed two fleet sizes, 10 admission profiles, three architectures, three capacity multipliers, and two workload families. The complete design contained 2,100 scenarios and 25,200 replication records at 12 replications per scenario. The held-out partition contained 1,800 scenarios and 21,600 prediction rows.

Randomization pairs were fixed by block, partition, fleet size, and admission profile. Architecture, capacity, and workload cells within a held-out pair used aligned replication seeds. Workload-family changes could still produce different realized variates.

### 4.2 Stage 3B design

Across five structural blocks, Stage 3B contained 90 training, 30 calibration, and 120 held-out scenario specifications. Ten replications per specification produced 2,400 raw records and 1,200 held-out predictions. Training sizes were 100, 250, and 500; calibration size was 750; held-out sizes were 1,000 and 10,000. Held-out topologies were Barabasi-Albert and hierarchical. Held-out nominal and detection-response cases were paired by graph, process, observation, and base-replication seeds, while defense parameters intentionally differed.

### 4.3 Execution record

| Item | Confirmatory record |
|---|---|
| Execution ID | `stage3-confirmatory-20260819-01` |
| Manifest status | `completed` |
| Manifest start | `2026-08-19T18:50:20.028139+00:00` |
| Manifest completion | `2026-08-19T18:56:13.021333+00:00` |
| Evidence wall time | 352.97016516700387 seconds |
| Evidence CPU time | 350.41781 seconds |
| Peak resident memory | 1092.5625 MB |
| Output before evidence | 22.536619186401367 MB |
| Runtime limit | 1800 seconds |
| Memory limit | 4096 MB |
| Output limit | 1500 MB |
| Bootstrap draws | 5000 |
| Network access | Prohibited |
| Python | 3.13.0 |
| Platform | macOS 26.6.1, arm64 |
| Frozen inputs | 151 of 151 matched |
| Final manifest inventory | 341 artifacts, 23,721,069 bytes |

The recorded numerical environment used NumPy 2.3.5, SciPy 1.17.0, pandas 2.2.3, NetworkX 3.6.1, Matplotlib 3.10.8, PyYAML 6.0.3, Pydantic 2.13.4, and PyArrow 25.0.1, with `OMP_NUM_THREADS=1` and `OPENBLAS_NUM_THREADS=1`.

The exact confirmatory seed domains were `confirmatory-stage3a`, `confirmatory-stage3a-bootstrap`, `confirmatory-stage3b`, and `confirmatory-stage3b-bootstrap`. The evidence records bootstrap seeds 7523257667172866170 for Stage 3A, 11430195582013312250 for Stage 3B final size, and 11430195582013312251 for Stage 3B outbreak Brier. Stage 3B graph, process, observation, base-replication, and derived-replication seeds remained separately recorded.

## 5. Stage 3A results

### 5.1 Primary metrics and interval estimates

| Metric | Projected `Omega_A` | Strongest simple baseline | Confirmatory result |
|---|---:|---:|---:|
| Brier score | 0.04991087241138574 | 0.06355470068862228 | 0.2146785073236776 fractional improvement |
| ROC AUC | 0.9702029588820625 | 0.9329513378418113 | Candidate exceeded the 0.90 requirement |
| Precision-recall AUC | 0.9833197595492815 | 0.9685827820684652 | Descriptive |
| Log loss | 0.18421474296094006 | 0.6747947781352155 | Descriptive |
| Expected calibration error | 0.02414666311056075 | 0.0672910741143424 | Descriptive |
| Calibration slope | 0.4539306867708676 | 0.2894148012029462 | Candidate failed required [0.8, 1.2] |
| Calibration intercept | 0.41918350785843966 | -2.608676905506586 | Descriptive |

The paired block-aware bootstrap 95 percent intervals were:

- absolute Brier improvement: [0.0030542664854191505, 0.025639719881214475];
- fractional Brier improvement: [0.061698589715370566, 0.3397534586105416].

The interpretable multivariate baseline was not eligible to replace the primary baseline. Its held-out Brier score was 0.16180354521786494.

### 5.2 Block results

| Block | Candidate Brier | Selected-baseline Brier | Fractional improvement | Selected simple baseline |
|---:|---:|---:|---:|---|
| 0 | 0.04978065990383732 | 0.059527665228034356 | 0.1637390831113382 | `cumulative_backlog_area` |
| 1 | 0.05016116556528841 | 0.06711547593917294 | 0.25261402287082496 | `cumulative_backlog_area` |
| 2 | 0.048653746493489906 | 0.060922441018868165 | 0.20138218889782414 | `cumulative_backlog_area` |
| 3 | 0.051781774929649464 | 0.06801986416717268 | 0.238725693388843 | `cumulative_backlog_area` |
| 4 | 0.0491770151646636 | 0.062188057089863184 | 0.20922091047800911 | `cumulative_backlog_area` |

All blocks had both outcome classes in training, calibration, and held-out partitions.

### 5.3 Complete preregistered adjudication

| Criterion | Rule | Observed | Status |
|---|---|---|---|
| All blocks have binary class support | Both classes in training, calibration, and held-out | True in all partitions of blocks 0 through 4 | Passed |
| Held-out Brier improvement | At least 0.15 | 0.2146785073236776 | Passed |
| Fractional bootstrap lower bound | Greater than 0 | 0.061698589715370566 | Passed |
| Held-out ROC AUC | At least 0.90 | 0.9702029588820625 | Passed |
| Calibration slope | In [0.8, 1.2] | 0.4539306867708676 | **Failed** |
| Positive block improvement | At least 4 blocks | 5 | Passed |
| Threshold transfer at N=10,000 | Balanced accuracy at least 0.75 in every block | 0.9241531664212077, 0.9216691068814056, 0.9198250728862973, 0.9241531664212077, 0.9222873900293256 | Passed |
| Threshold transfer at N=10,000 under sublinear capacity | Balanced accuracy at least 0.75 in every block | 0.9285714285714286 in every block | Passed |
| Architecture transfer | Improvement greater than 0 for every unseen architecture | `pipelined_proportional` 0.22150146455473255; `sharded_sublinear_capacity` 0.20491938370894006 | Passed |
| Capacity transfer | Improvement greater than 0 at both non-reference capacities | 0.80: 0.5845658286776216; 1.25: -0.003672405471146048 | **Failed** |
| Workload transfer | Improvement greater than 0 for gamma workload | 0.21678102317573575 | Passed |
| Combined shift transfer | Improvement greater than 0 | 0.23724418290085406 | Passed |

**Stage 3A decision:** `not_supported_under_preregistered_rule`. The positive pooled interval and discrimination do not override the two failed conjunctive conditions.

## 6. Stage 3B results

### 6.1 Comparator selection

Leave-one-block-out calibration crossfit selected `temporal_propagator` as the strongest final-size comparator and `node_hazard_aggregation` as the strongest initiation comparator. The final-size and initiation comparisons therefore use different preregistered baselines.

### 6.2 Primary metrics and interval estimates

| Metric | Phase-separated DMP | Selected baseline | Confirmatory result |
|---|---:|---:|---:|
| Final-size MAE | 0.04801817645605284 | 0.04918958703703704 | 0.02381419832010778 fractional improvement |
| Final-size RMSE | 0.054345999857807796 | 0.060253643264095685 | Descriptive |
| Final-size interval coverage | 0.22916666666666666 | 0.32083333333333336 | Descriptive |
| Outbreak Brier score | 0.10048888888888889 | 0.10057552120551853 | 0.0008613658233260923 fractional improvement |
| Outbreak ROC AUC | 0.5 | 0.44526758071649714 | Descriptive, not evidence of required improvement |
| Outbreak precision-recall AUC | 0.5566666666666666 | 0.31231219760631523 | Descriptive |
| Outbreak log loss | 0.35342822141326286 | 0.35386079519176605 | Descriptive |
| Overall outbreak calibration slope | 0.808860145549476 | -11.423883357035344 | Descriptive |

The final-size paired block-aware bootstrap 95 percent intervals were:

- absolute MAE improvement: [-0.003874748654120741, 0.006453490280560529];
- fractional MAE improvement: [-0.10385572830786145, 0.10685745497658988].

The outbreak-Brier paired block-aware bootstrap 95 percent intervals were:

- absolute Brier improvement: [-0.0001989300682397579, 0.0003676186469850001];
- fractional Brier improvement: [-0.00208141194450202, 0.003930473033929112].

Candidate conditional-outbreak severity had MAE 0.04820259103641457 and interval coverage 0.7426470588235294. Candidate conditional-nonoutbreak severity had MAE 0.03571631030158775 and interval coverage 0.46616541353383456. These are descriptive component metrics and do not replace the fixed acceptance conditions.

### 6.3 Transfer and block results

The candidate improved final-size MAE in two of five structural blocks. Its final-size transfer improvements were:

- fleet size 1,000: 0.07188274395228202;
- fleet size 10,000: -0.02300647639360295;
- Barabasi-Albert topology: -0.2957050294956605;
- hierarchical topology: 0.1640848786909695.

Nominal outbreak calibration slope was 0.9604070931750317. Detection-response-shift slope was 0.6923613400765599, an absolute change of 0.2680457530984718. Unsegmented slope was 0.8504270400198463 and segmented slope was 0.7651244994820204, an absolute change of 0.08530254053782582.

### 6.4 Complete preregistered adjudication

| Criterion | Rule | Observed | Status |
|---|---|---|---|
| Held-out binary support | Both outbreak classes in every held-out block | True in blocks 0 through 4 | Passed |
| Final-size MAE improvement | At least 0.15 | 0.02381419832010778 | **Failed** |
| Outbreak Brier improvement | At least 0.10 | 0.0008613658233260923 | **Failed** |
| Positive final-size blocks | At least 4 | 2 | **Failed** |
| Positive outbreak-Brier blocks | At least 4 | 4 | Passed |
| Final-size bootstrap lower bound | Greater than 0 | -0.003874748654120741 | **Failed** |
| Outbreak-Brier bootstrap lower bound | Greater than 0 | -0.0001989300682397579 | **Failed** |
| Unseen topology transfer | Greater than 0 for every unseen topology | Barabasi-Albert -0.2957050294956605; hierarchical 0.1640848786909695 | **Failed** |
| Unseen scale transfer | Greater than 0 at N=1,000 and N=10,000 | N=1,000 0.07188274395228202; N=10,000 -0.02300647639360295 | **Failed** |
| Paired defense completeness | Both declared cases with required shared seeds | True | Passed |
| Detection-response slope change | At most 0.20 | 0.2680457530984718 | **Failed** |
| Segmentation slope change | At most 0.20 | 0.08530254053782582 | Passed |
| Structural boundary audit | Passed review and no identical latent-equation reuse | `passed_structural_review`; reuse detected false | Passed |

**Stage 3B decision:** `not_supported_under_preregistered_rule`. Five criteria passed and eight failed. Small pooled point improvements do not overcome the intervals crossing zero, transfer failures, or failed stability requirements.

## 7. Confirmatory figures

The six post-confirmatory figures under `figures/stage3/` are deterministic visual summaries of the immutable evidence. They were created after scientific adjudication and did not feed back into metrics, criteria, model selection, or dispositions.

- `stage3a_pooled_brier.png` compares held-out Brier scores and the paired bootstrap improvement interval.
- `stage3a_block_and_shift_improvement.png` shows the five block results and the declared transfer strata, including the failed 1.25 capacity cell.
- `stage3a_reliability.png` shows held-out reliability and the failed candidate calibration slope.
- `stage3b_final_size_mae.png` compares final-size MAE and shows the paired bootstrap interval crossing zero.
- `stage3b_outbreak_brier.png` shows the near tie in outbreak Brier score and its paired bootstrap interval.
- `stage3b_transfer.png` shows the failed N=10,000, Barabasi-Albert, and detection-response transfer criteria.

`figures/stage3/figure_manifest.csv` records each image digest, dimensions, source artifact, source digest, scope, and alternative text. `figures/stage3/figure_provenance.json` records the renderer, immutable protocol and execution identity, source hashes, and the explicit synthetic, model-conditioned, no-external-validation boundary.

## 8. Preserved negative results

Stage 3 did not retest or rehabilitate the Stage 2 scalar claims.

- **NH2-D:** The single dynamic next-generation attack score remains `refuted_within_current_model`.
- **NH2-T selected propagator:** The training-selected temporal propagator remains `refuted_within_current_model`.

The Stage 3B use of a temporal propagator as a selected comparator does not reverse NH2-T. NH2-T concerned a training-selected scalar used as a general predictor. Stage 3B used calibration crossfit to select distinct baselines for final size and initiation and tested a different phase-separated candidate.

## 9. Interpretation

### 9.1 Stage 3A

Projected cumulative resource stress contained strong discriminative information inside the declared synthetic resource model. It also transferred across the declared unseen architectures, gamma workload, combined shift, and N=10,000 threshold checks. The fixed probability-calibration requirement nevertheless failed substantially, and the candidate did not outperform its strongest simple comparator at capacity multiplier 1.25.

The evidence supports retaining projected `Omega_A` as a diagnostic and experimental covariate. It does not support treating its current mapped probability or threshold as a universal admission-control law. More synthetic repetitions under the same resource assumptions would not resolve the principal external-evidence gap.

### 9.2 Stage 3B

The tested DMP architecture did not deliver the preregistered advantage over calibration-selected comparators. The final-size point improvement was 2.38 percent rather than 15 percent, and outbreak-Brier improvement was 0.086 percent rather than 10 percent. Both bootstrap intervals crossed zero. Negative transfer at N=10,000 and on the Barabasi-Albert topology shows that the pooled point result was not broadly stable across the declared held-out region.

Phase separation remains a sound modeling decomposition, and node-resolved DMP state can remain useful for mechanism inspection. This confirmatory result does not show that the tested DMP-derived primary components improve prediction enough to justify operational use.

## 10. Threats to validity

### 10.1 Construct validity

The Stage 3A operational-failure label is a synthetic Boolean composition of queue and mission-surrogate outcomes. Real assurance failure may involve prioritization, elastic capacity, load shedding, human intervention, policy exceptions, recovery modes, or mission consequences not represented here.

The Stage 3B attack process is a bounded synthetic event model. Real adversaries adapt, chain exploits, exploit identity and software semantics, choose objectives, and react to defenses. Final compromised fraction and outbreak status do not capture privilege-weighted loss, persistence, mission impact, data exposure, recovery cost, or operator decision quality.

### 10.2 Internal validity

The protocol, environment, inputs, partitions, seeds, and acceptance rules were frozen before confirmation. All recorded frozen checks matched. These controls reduce post-outcome tuning risk. They do not eliminate design choices made during engineering pilots, including synthetic parameter ranges, model forms, factor assignments, comparator sets, and outcome definitions. Pilot outcomes were excluded from adjudication, but pilot-informed design choices remain part of the frozen experimental context.

Stage 3A's label excludes `Omega_A` by definition but shares the synthetic resource model and closely related queue quantities. Stage 3B uses a separate generator implementation and bounded observed view, but observed proxies are derived from generator constructs. Neither boundary supports a claim of statistical independence.

### 10.3 External validity

No external operational measurements were supplied. The included calibration template verifies an interface only. No resource capacity, work coefficient, wait budget, graph, attack trace, sensor error, detection rate, quarantine delay, revocation delay, or common-cause process was calibrated to a deployed fleet. Results transfer only to systems adequately represented by the declared synthetic mechanisms.

### 10.4 Statistical validity

The experiment used five structural blocks, fixed partitioning, paired randomization, and 5,000-draw hierarchical bootstrap intervals. The bootstrap intervals are conditional on the declared scenario families and blocks. They do not quantify model-form uncertainty or population variation outside the simulated design. The conjunctive rules protect against selective metric interpretation, but multiple descriptive subgroup metrics should not be treated as separately confirmed discoveries.

Stage 3B final-size interval coverage was 0.22916666666666666, conditional-outbreak coverage was 0.7426470588235294, and conditional-nonoutbreak coverage was 0.46616541353383456. These descriptive values limit any claim that the retained intervals provide reliable uncertainty coverage.

### 10.5 Implementation and numerical validity

The confirmatory run was deterministic within its frozen environment and all listed artifacts matched the final manifest during synthesis verification. That does not establish cross-platform byte identity or eliminate unmodeled implementation defects. Sparse numerical methods, library versions, and platform behavior may change low-order numerical results. The structural source audit is hash-bound to the frozen reviewed files and must be repeated after changes.

## 11. Novelty boundary

Stage 3 does not claim reflected-fluid queues, monotone calibration, block-aware bootstrap, message passing, dynamic message passing, phase-separated outbreak and severity estimation, non-backtracking structure, temporal propagators, or standard predictive metrics as new mathematics.

The defensible contribution is narrower: a runtime-agnostic, hash-gated assurance experiment that preserves negative results, separates fitting and adjudication partitions, compares projected multi-resource admission stress and phase-separated DMP against calibration-selected baselines, and tests transfer across declared operational and structural shifts. At present this is a systems-engineering and research-method contribution supported only inside the synthetic model. No novelty-priority, patentability, or freedom-to-operate claim is made.

## 12. Engineering implications

1. **Admission logic:** Do not hard-code the synthetic `Omega_A` mapping or threshold as an operational admission gate. Retain projected backlog, binding resource, queue budget, wait time, deadline misses, shedding, incomplete exposure, and recovery as separate telemetry.
2. **Capacity design:** Treat capacity architecture and multiplier as explicit model inputs. The failed 1.25-capacity transfer cell shows that a pooled mapping cannot be assumed to improve monotonically across capacity regimes.
3. **Compromise prediction:** Do not replace static or temporal comparators with the tested phase-separated DMP predictor. Keep initiation, outbreak severity, non-outbreak severity, and final-size uncertainty as separate outputs.
4. **Observed-view design:** Preserve the generator-predictor interface boundary and explicit common-cause vector. Re-run the structural audit whenever generator, observation, DMP, phase-model, or orchestration code changes.
5. **Evidence tooling:** Keep the console read-only and label exact, observed, predicted, estimated, sampled, aggregated, unavailable, and not retained evidence distinctly. A visualization is not a scientific recomputation or deployment control.

## 13. Operational implications

- No result authorizes admission, quarantine, revocation, or deployment action on a live system.
- No result supports a secure or assured fleet-size recommendation, including 10,000 agents.
- A real admission controller requires measured per-resource work, service capacity, wait budgets, priority behavior, recovery behavior, and prospective outcome validation.
- A real compromise predictor requires externally sourced or independently implemented attack traces, measured observation error, implementation-specific topology semantics, and operationally meaningful loss outcomes.
- Source integrity and completed simulation do not establish implementation security, authorization correctness, resilience to an adaptive adversary, or mission acceptance.

## 14. Recommended next research stage

### 14.1 Admission calibration and external transfer

1. Instrument identity, credential, authorization, dispatch, telemetry, evidence-ingest, supervision, revocation, attestation, and dependency-registration services on at least one real or high-fidelity control plane.
2. Estimate work per admission, background work, effective service capacity, queue delay, workload shedding, recovery dynamics, and acceptable wait budgets without using confirmatory outcomes for tuning.
3. Freeze an empirical calibration set and a prospective held-out campaign spanning architectures, capacity regimes, workloads, and equal-final-population trajectories.
4. Test whether projected `Omega_A`, its probability mapping, and any proposed boundary transfer across systems. Retain simple backlog-area and utilization comparators.

### 14.2 Compromise model validation

1. Assemble an external or separately implemented trace corpus with held-out topologies, sizes, attack classes, common-cause events, sensor error, and response shifts.
2. Preserve exact hidden-state and noisy-observation separation where simulation remains necessary, but do not describe it as external independence.
3. Predeclare whether DMP adds value beyond an interpretable non-DMP multivariate comparator and the strongest scalar baselines.
4. Rework interval construction and test coverage prospectively before any operational uncertainty claim.
5. Add privilege-weighted loss, mission degradation, persistence, and recovery cost as distinct outcomes rather than treating final compromised fraction as sufficient.

The current confirmatory directory and manifests should remain immutable. Any retuned model, revised threshold, new observation process, or changed criterion requires a new protocol identifier and a new preexecution manifest.

## 15. What this study does not establish

This study does not establish a universal Fleet Assurance Law; an exact or universal admission boundary at `Omega_A=1`; externally calibrated resource demand; a general DMP advantage; an operationally valid outbreak probability; a secure 10,000-agent architecture; implementation security; authorization correctness; formal verification; adversarial robustness; mission suitability; novelty priority; patentability; or freedom to operate.

Passing selected metrics is not equivalent to track support. Stage 3A passed 10 of 12 fixed criteria and Stage 3B passed 5 of 13, but both failed their all-criteria rules. Their exact dispositions remain `not_supported_under_preregistered_rule`.

## 16. Final research decision

Stage 3 produced a scientifically useful negative result. The projected admission candidate retained a strong model-conditioned signal but failed calibration and one capacity-transfer requirement. The phase-separated DMP candidate did not provide the required predictive advantage or transfer. Both candidates remain research constructs rather than validated operational controls.

The program should move from repeated synthetic confirmation toward measured admission calibration and externally grounded attack-trace validation. Until those steps are completed under new frozen protocols, no deployment assurance or fleet-size recommendation is warranted.

## 17. Artifact traceability and checksums

Primary immutable sources:

- Protocol Markdown: `docs/stage3_preregistered_protocol.md`, SHA-256 `2a5ce8b93f55c1f2294b3126797d35d5be27ea031899648f52eaf1f3305fdab3`.
- Protocol configuration: `configs/stage3/protocol.yaml`, SHA-256 `7b6dcd3f8478229e49c239a762ca3f15ba9de13c504a6a2aa6c95e5d998e9f15`.
- Preexecution manifest: `manifests/stage3_preexecution_manifest.json`, SHA-256 `9e926aa66b9da993eddd4dfce5aff209935298e4451bcf402c485d671bbdfeb7`.
- Confirmatory evidence: `results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01/stage3_evidence.json`, SHA-256 `39f0ee1b82096c89c0fe6c7a162bccc6601653492eeb27c80672a773421dd280`.
- Execution manifest: `results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01/execution_manifest.json`, SHA-256 `5da08ab9a9300c01df700fe7cf36318bad4f507f1e382fb1e765e693d1927f0d`.
- Stage 3A raw replications: `results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01/raw/stage3a_replications.parquet`, SHA-256 `34205c8fe8bc09c603e41d5d63e8a3f6c49a9a0c51230da81c96229d4014bcb3`.
- Stage 3A held-out predictions: `results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01/derived/stage3a_heldout_predictions.parquet`, SHA-256 `d1408d7a3cd04136df7768336b33424e07eb7a3b70efad20bdc30b7a5953a41b`.
- Stage 3B raw replications: `results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01/raw/stage3b_replications.parquet`, SHA-256 `bb3b718fd4acee9e96ab64fafb989ac9fa323698567cda1e81e8653160ad7e3a`.
- Stage 3B held-out predictions: `results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01/derived/stage3b_heldout_predictions.parquet`, SHA-256 `cbec4354f0aecc2d5c538d150db1d63b35fc01ed63ec3fe9d8d8ca24f0dabdf1`.

Stage 2 canonical sources used only for continuity and document structure:

- `paper/stage2_cycles5_to7_research_report.md`, SHA-256 `a952cb2fdaa8b5b4a4c31d77f79b67afc11ac230b27ebb0b5876be1b42ecc761`.
- `results/stage2_synthesis/stage2_synthesis.json`, SHA-256 `cb2722f3837248452d8801d02f8c83b8fac715b060b21fd549828b4be72f131a`.
- `results/stage2_synthesis/evidence_ledger.csv`, SHA-256 `405103129a75e8d4a230e62ca99a5f42f02eacb684071b254e28675f22431564`.
- `results/stage2_synthesis/research_decision_table.csv`, SHA-256 `55e27f68a678f7c5cf12712026c20e2c06fd30b16ec4218f5f43d93721ba5e43`.

The machine-readable synthesis is `results/stage3_synthesis/stage3_synthesis.json`. The evidence ledger is `results/stage3_synthesis/evidence_ledger.csv`. The machine-readable and human-readable decision tables are `results/stage3_synthesis/research_decision_table.csv` and `docs/stage3_research_decision_table.md`.
