# Stage 2 Research Report

## Falsification of Scalar Compromise Predictors and Evaluation of Dynamic Fleet-Admission Stability

**Project:** Formal and Visual Simulation of Secure Multi-Agent Fleet Scaling  
**Research framing:** Version-zero strawman for community critique  
**Report date:** 2026-08-19  
**Evidence boundary:** Model-conditioned results using synthetic mechanisms and notional operational parameters  
**Primary protocols:** FAS-S2-C5-2026-08-19, FAS-S2-C6-2026-08-19, and FAS-S2-C7-2026-08-19

## Abstract

This report documents three preregistered or independently replicated research cycles examining two candidate contributions in runtime-agnostic multi-agent fleet assurance. The first candidate was that a directed dynamic attack-reachability scalar could predict stochastic compromise occurrence and final blast radius better than established static spectral baselines. The second was that a reflected multi-resource overload index, denoted \(\Omega_A\), could predict transient assurance-processing failure during fleet admission better than an instantaneous load ratio, denoted \(\Lambda_A\).

The scalar compromise hypotheses were refuted in their tested forms. A dynamic next-generation score in Cycle 5 was worse than the strongest static baseline on held-out mean absolute error, outbreak discrimination, Brier score, robustness, and dependency-layer ablation. A training-selected temporal infection-propagator score in Cycle 6 increased held-out final-size error by 20.5 percent relative to static pre-response non-backtracking structure. These results rule out the tested proposition that one dynamic spectral scalar can serve as a general replacement for static graph predictors across both outbreak initiation and final compromise magnitude.

The admission result was stronger but did not satisfy its deliberately strict conjunctive acceptance rule. In Cycle 6, \(\Omega_A\) achieved held-out ROC AUC 0.992, balanced accuracy 0.833 at the fixed boundary \(\Omega_A=1\), and a 50.6 percent Brier-score reduction relative to \(\Lambda_A\). Its AUC advantage was 0.058 rather than the preregistered 0.080, and only three of five robustness blocks satisfied the complete block rule. The result is therefore classified as strong provisional model-conditioned evidence, not support under the fixed protocol.

Cycle 7 tested a phase-separated compromise estimator that independently models outbreak initiation and conditional outbreak severity. Pooled held-out final-size mean absolute error improved by 18.8 percent relative to the best direct scalar baseline, with a hierarchical-bootstrap 95 percent interval from 8.8 to 29.2 percent and positive improvement in all three independent graph blocks. However, only one block exceeded the preregistered 15 percent improvement requirement, and outbreak-probability Brier noninferiority held in only one block. The hypothesis was not supported under the complete rule. The result nevertheless identifies phase separation as the most credible remaining compromise-prediction direction.

No universal Fleet Assurance Law, deployment architecture, or secure scale limit is established. The strongest current contribution is rigorous negative evidence against single-scalar compromise prediction in the implemented model, accompanied by two narrowed research candidates: cumulative multi-resource admission overload and phase-separated compromise estimation.

## 1. Research questions

Stage 2 addressed four questions.

1. Can a dynamic directed attack-reachability operator estimated from observable authorization, communication, dependency, supervision, recovery, and node-risk information predict held-out compromise behavior better than static spectral structure?
2. Can a temporal propagation scalar account for intervention timing and response attenuation without losing prediction of final compromise magnitude?
3. Does cumulative reflected assurance backlog predict fleet-admission failure across scale and admission-profile shape better than an instantaneous load ratio?
4. Is stochastic compromise better represented as two linked processes, outbreak initiation and conditional final severity, rather than as one scalar regression target?

These questions were selected because the novelty review found extensive prior work on graph epidemic thresholds, non-backtracking operators, message passing, queue stability, authorization propagation, and multi-agent graph representations. Novelty could not defensibly rest on applying any one of those established tools. The research therefore tested whether an assurance-specific composition produced transferable predictive value.

## 2. Evidence classification

### 2.1 Analytically established from prior theory

The following statements are not original findings of this study.

1. For appropriate compartmental epidemic models, a next-generation matrix can define a reproduction threshold through its spectral radius.
2. For sparse and locally tree-like networks, message-passing and non-backtracking formulations can estimate percolation or epidemic behavior more accurately than raw adjacency structure under their stated assumptions.
3. Temporal infection-propagator methods can characterize threshold behavior on time-varying contact structures under the applicable model assumptions.
4. Stochastic epidemic behavior can separate into the probability of a major outbreak and a conditional final-size distribution.
5. Fluid and reflected-fluid queue models provide established tools for reasoning about workload accumulation, stability, and overload in multiclass processing systems.

The project uses these foundations. It does not claim them as original mathematics.

### 2.2 Demonstrated numerically within the implemented model

1. The tested single dynamic next-generation score did not outperform the strongest static baselines in Cycle 5.
2. The training-selected temporal infection-propagator score did not improve held-out final-size prediction in Cycle 6.
3. The cumulative reflected overload index \(\Omega_A\) strongly discriminated admission-boundary crossing in the balanced Cycle 6 design, but missed the fixed superiority margin and robustness count.
4. The Cycle 7 phase-separated model reduced pooled held-out final-size error and improved all three independent blocks, but did not satisfy every preregistered calibration and block-level criterion.

### 2.3 Conjectured and requiring external validation

1. Cumulative assurance backlog may be a more useful operational admission-control variable than instantaneous admission pressure.
2. Compromise initiation and conditional severity may require different predictors and different estimators.
3. A directed multilayer attack representation may remain useful as a state representation even though no tested scalar reduction was adequate.
4. A future fleet-assurance envelope may need phase-specific and resource-specific state variables rather than one aggregate margin or one graph eigenvalue.

## 3. Formal constructs

### 3.1 Directed latent compromise substrate

The implemented propagation substrate is a directed multilayer graph with authorization, communication, dependency, and supervision layers. For source agent \(i\) and target agent \(j\), the latent hazard matrix \(H(t)\) uses row-source and column-target orientation. It incorporates notional source privilege, target susceptibility, image-family correlation, latent edge multipliers, heterogeneous recovery, and response attenuation.

For a susceptible target \(j\), the aggregate incoming hazard at a simulation step is

\[
h_j(t)=\sum_{i\in I(t)} H_{ij}(t),
\]

and the infection probability is

\[
P\{j\text{ compromised at }t+1\}=1-\exp[-h_j(t)].
\]

Recovery for compromised source \(i\) is sampled with probability

\[
P\{i\text{ recovers at }t+1\}=1-\exp[-\gamma_i].
\]

The observable estimator does not receive the latent transition intensities. It receives noisy node-state estimates, nominal layer weights, and observable pre-response and post-response matrices. This separation was introduced to prevent the predictor from being evaluated against outcomes generated from the exact same score.

### 3.2 Tested scalar compromise predictors

Cycle 5 evaluated static and dynamic scalar reductions, including raw authorization radius, symmetrized attack radius, static next-generation radius, non-backtracking radius, and a dynamic next-generation score.

Cycle 6 evaluated a temporal non-backtracking score and an infection-propagator growth score. If \(H_0\) and \(H_1\) are observable pre-response and post-response hazard matrices, and \(\gamma_i\) is observable recovery, weighted directed edge transmissibility is

\[
T_{ij}=\frac{H_{ij}}{H_{ij}+\gamma_i}.
\]

For pre-response and post-response non-backtracking radii \(r_{NB,0}\) and \(r_{NB,1}\), intervention time \(t_I\), and horizon \(T\), the temporal non-backtracking score was

\[
r_{TNB}=\exp\left[
\frac{t_I}{T}\ln(r_{NB,0}+\varepsilon)
+\left(1-\frac{t_I}{T}\right)\ln(r_{NB,1}+\varepsilon)
\right].
\]

The temporal linear infection propagator used

\[
M_k=\operatorname{diag}(e^{-\gamma})+H_k^{\mathsf T}
\]

and

\[
\Psi=M_1^{T-t_I}M_0^{t_I},
\qquad
g_\Psi=\rho(\Psi)^{1/T}.
\]

These were treated only as predictors. They were not treated as exact finite-network thresholds.

### 3.3 Reflected fleet-admission overload index

For assurance-processing resource \(r\), arrival work was modeled as

\[
\lambda_r(t)=b_rN(t)+w_r\dot N_+(t),
\]

where \(b_r\) is steady-state work per active agent, \(w_r\) is admission work per newly admitted agent, and \(C_r\) is resource capacity. The reflected fluid backlog evolves as

\[
Q_r(t+\Delta t)=\max\left\{0,
Q_r(t)+[\lambda_r(t)-C_r]\Delta t
\right\}.
\]

With maximum permissible wait \(W_r\), queue budget is

\[
B_r=C_rW_r.
\]

The cumulative multi-resource overload index is

\[
\Omega_A=\max_{r,t}\frac{Q_r(t)}{B_r}.
\]

The instantaneous comparator is

\[
\Lambda_A=\max_{r,t}
\frac{w_r\dot N_+(t)}{C_r-b_rN(t)}.
\]

The fixed boundary \(\Omega_A=1\) means that at least one modeled assurance resource has accumulated work equal to its declared queue budget. This is an analytic property of the reflected model. It is not yet an empirically calibrated operational threshold.

### 3.4 Phase-separated compromise estimator

Cycle 7 tested a fixed two-stage estimator. Let \(O\) denote the event that final compromise fraction exceeds 0.10. Expected final compromise fraction was decomposed as

\[
\mathbb E[F]
=
P(O)\,\mathbb E[F\mid O]
+
[1-P(O)]\,\mathbb E[F\mid \neg O].
\]

Outbreak initiation probability was calibrated monotonically from the temporal non-backtracking score using weighted isotonic regression on training scenarios only. Conditional outbreak severity was estimated using constrained least squares with pre-response non-backtracking structure and \(\log N\):

\[
\widehat{\mathbb E[F\mid O]}
=
\operatorname{clip}
\left(
\theta_0+	heta_1\log(1+r_{NB,0})+\theta_2\log N,
0.10,
1
\right),
\]

with \(\theta_1\ge 0\). Conditional nonoutbreak fraction was fixed at \(1/N\), corresponding to the initial compromised agent when no wider outbreak occurs.

This decomposition follows established stochastic-epidemic reasoning. Its use here is not claimed as new mathematics. The candidate contribution is the assurance-specific application and evaluation against direct graph-score regressions.

## 4. Experimental integrity and provenance

| Cycle | Role | Integrity disposition | Primary use |
|---|---|---|---|
| Cycle 4 | Initial confirmatory execution | Diagnostic only because a frozen source hash did not match the preregistration manifest | Identify experimental and implementation defects; no confirmatory claim |
| Cycle 5 | Independent-seed exact replication | Valid partitioned execution with matching frozen inputs | Confirm refutation of the dynamic scalar and identify admission-test saturation |
| Cycle 6 | Preregistered temporal and admission experiment | Valid hash-gated execution; all frozen inputs matched | Primary evidence for NH2-T and NH4-O |
| Cycle 7 | Preregistered three-block phase-separated experiment | Valid hash-gated execution; all frozen inputs matched | Primary evidence for NH2-H |

The Cycle 7 execution manifest records Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0, pandas 2.2.3, NetworkX 3.6.1, and Matplotlib 3.10.8. Every frozen protocol, configuration, source, test, runner, and environment file matched its preregistered SHA-256 digest before execution. All stochastic replication rows record seeds. No warmup truncation was used because the Stage 2 experiments are terminating transients.

Cycle 7 included 34,560 stochastic replications, 1,152 scenarios, and 576 held-out scenario predictions. Cycle 6 included 30 independent replications per confirmatory scenario and five independent robustness blocks.

## 5. Cycle 5 results

### 5.1 NH2-D: dynamic next-generation scalar

The Cycle 5 independent-seed replication refuted the single dynamic-score formulation.

| Metric | Dynamic score | Best baseline | Relative result |
|---|---:|---:|---:|
| Held-out final-size MAE | 0.03946 | 0.03844 | 2.65 percent worse |
| Outbreak ROC AUC | 0.74869 | 0.99215 | 0.24346 lower |
| Brier score | 0.01646 | 0.00874 | 88.5 percent worse |
| Positive robustness blocks | 0 of 5 | Not applicable | Failed |
| Dependency-layer ablation degraded prediction | No | Required yes | Failed mechanism check |

The bootstrap interval for MAE improvement crossed zero, while the Brier-improvement interval was entirely negative. Removing the dependency layer did not degrade the dynamic score, contradicting the declared mechanism that the dependency contribution was necessary to its predictive advantage.

**Decision:** Refuted within the implemented model. Retire the dynamic score as a scalar replacement. Preserve the underlying layers as features or state variables.

### 5.2 NH4-A: first admission formulation

Cycle 5's held-out admission region was saturated. Both \(\Omega_A\) and \(\Lambda_A\) had AUC 0.5 because almost every held-out scenario crossed the boundary. There were no valid fleet-size and profile groups from which to estimate a 50 percent transition threshold.

**Decision:** Not supported and not interpretable as a fair discrimination test. The result motivated the Cycle 6 boundary-spanning design. It did not justify changing the acceptance thresholds.

## 6. Cycle 6 results

### 6.1 NH2-T: training-selected temporal scalar

Training selected infection-propagator growth \(g_\Psi\) as the primary temporal candidate. On the untouched held-out region, it performed worse than static pre-response non-backtracking on final-size error.

| Metric | Selected temporal candidate | Static non-backtracking | Difference |
|---|---:|---:|---:|
| Held-out final-size MAE | 0.05686 | 0.04717 | 20.52 percent worse |
| Raw outbreak ROC AUC | 0.97763 | 0.97619 | +0.00144 |
| Spearman correlation | 0.91165 | 0.90743 | +0.00423 |
| Absolute MAE reduction, bootstrap 95 percent interval | -0.01512 to -0.00462 | Reference | Conclusively negative |
| Reduced robustness blocks with positive MAE improvement | 5 of 5 | Required 4 of 5 | Passed secondary check |

The apparently contradictory pattern is important. The temporal candidate ranked outbreak-prone scenarios well and performed positively in smaller robustness matrices, but its continuous calibration transferred poorly to the full held-out topology and scale region. The primary final-size criterion failed decisively.

An unselected temporal non-backtracking score achieved held-out MAE 0.04530, approximately 3.96 percent better than static non-backtracking, but this result was exploratory because training had not selected it and the improvement did not reach the fixed 5 percent threshold.

**Decision:** NH2-T refuted within the implemented model. Do not use one training-selected temporal scalar to predict both outbreak occurrence and final compromise size.

### 6.2 NH4-O: overload-targeted admission experiment

Cycle 6 deliberately selected ramp durations to span target \(\Omega_A\) values from 0.30 through 2.20 before stochastic execution. The held-out set included 112 scenarios, of which 72 had majority failure and 40 did not. The validity gate passed.

| Criterion | Result | Fixed requirement | Disposition |
|---|---:|---:|---|
| \(\Omega_A\) ROC AUC | 0.99167 | At least 0.90 | Pass |
| \(\Lambda_A\) ROC AUC | 0.93333 | Comparator | Reference |
| AUC improvement | 0.05833 | At least 0.08 | Fail |
| \(\Omega_A\) Brier score | 0.11833 | Lower is better | Pass relative to comparator |
| \(\Lambda_A\) Brier score | 0.23935 | Comparator | Reference |
| Brier reduction | 50.56 percent | At least 15 percent | Pass |
| Balanced accuracy at \(\Omega_A=1\) | 0.83333 | At least 0.80 | Pass |
| Transition-threshold coefficient of variation | 0.19487 | No greater than 0.20 | Pass |
| Full robustness blocks passing | 3 of 5 | At least 4 of 5 | Fail |

The bootstrap 95 percent interval for AUC advantage was 0.01595 to 0.10643. The interval for Brier reduction was 44.9 to 56.1 percent. The model therefore produced a strong and directionally consistent signal, but the predeclared superiority margin and robustness count were not met.

The group-specific estimated 50 percent failure thresholds were 0.538, 0.764, 0.782, and 0.878. Their variation shows that \(\Omega_A=1\) is not an exact universal phase boundary even inside the notional model. Capacity regime, stochastic variability, and profile shape still matter.

**Decision:** Not supported under the fixed conjunctive rule. Retain as a strong provisional candidate for empirical calibration.

## 7. Cycle 7 results

### 7.1 Fixed hypothesis

Cycle 7 tested whether the fixed two-stage model improved held-out mean final compromise prediction across three independently generated full graph and stochastic blocks. The protocol required all of the following:

1. all three blocks valid;
2. pooled MAE improvement of at least 15 percent;
3. positive MAE improvement in all blocks;
4. at least two blocks with 15 percent or greater improvement;
5. positive lower bound for the hierarchical-bootstrap absolute MAE reduction;
6. outbreak-probability Brier noninferiority in at least two blocks;
7. no outbreak-AUC degradation greater than 0.01.

### 7.2 Block and pooled performance

| Block | Hurdle MAE | Best direct baseline | Best-baseline MAE | MAE improvement | Brier result | AUC difference |
|---:|---:|---|---:|---:|---:|---:|
| 0 | 0.03197 | Temporal non-backtracking | 0.03734 | 14.38 percent | 1.94 percent worse | +0.00121 |
| 1 | 0.03378 | Temporal non-backtracking | 0.04777 | 29.28 percent | 11.71 percent better | -0.00096 |
| 2 | 0.04404 | Temporal non-backtracking | 0.05007 | 12.03 percent | 7.57 percent worse | +0.00305 |
| **Pooled** | **0.03660** | Best baseline per block | **0.04506** | **18.77 percent** | Mixed | No material degradation |

The hierarchical-bootstrap 95 percent interval for absolute MAE reduction was 0.00392 to 0.01374. The interval for fractional improvement was 8.80 to 29.19 percent. Every block improved final-size MAE, and the pooled result exceeded 15 percent.

The constrained severity coefficient on \(\log(1+r_{NB,0})\) was stable across blocks: 1.248, 1.309, and 1.315, with absolute coefficient of variation 0.029. The intercept and \(\log N\) coefficients were less stable. This suggests that pre-response non-backtracking structure carried repeatable information about conditional outbreak severity in the synthetic substrate, while scale correction and baseline offset were more sensitive to graph realization.

### 7.3 Why the hypothesis did not pass

Only Block 1 exceeded 15 percent improvement, while the protocol required at least two blocks. Brier noninferiority for outbreak probability also held only in Block 1. The isotonic initiation calibrator improved expected final-size estimation when combined with conditional severity, but its probability calibration was not consistently superior to the direct non-backtracking comparator.

**Decision:** Not supported under the preregistered rule. Classify the final-size improvement as mixed positive evidence and preserve phase separation as the next research direction.

## 8. Cross-cycle findings

### 8.1 Single-scalar compromise prediction is not adequate in the tested model

Cycles 5 and 6 independently rejected two variants of a single scalar replacement. Dynamic or temporal spectral structure could rank outbreak susceptibility well while still transferring poorly for final-size magnitude. A scalar's ability to distinguish outbreak-prone scenarios does not establish that it can estimate blast radius.

The strongest explanation supported by the experiment chain is that compromise prediction contains at least two different inference tasks:

1. whether propagation escapes the initial stochastic extinction region;
2. how large the compromise becomes after escape.

Established stochastic epidemic theory already recognizes this separation. The Stage 2 contribution is evidence that the same distinction matters when epidemic machinery is used as a runtime-agnostic abstraction for directed agent compromise.

### 8.2 Dynamic layers remain useful, but not as one collapsed score

The scalar hypotheses failed. That does not show that authorization, communication, dependency, supervision, response timing, or recovery are irrelevant. It shows that the tested scalar reductions lost information or transferred poorly. Future models should preserve layer identity and temporal state longer, using message passing, node-level hazard estimation, or phase-specific features rather than collapsing the substrate into one eigenvalue early in the analysis.

### 8.3 Cumulative backlog is more promising than instantaneous admission pressure

The \(\Omega_A\) result is the strongest admission finding. It captured duration and accumulation effects that \(\Lambda_A\) could not. Two admission profiles with similar peak rates can produce different queue histories, while the same final fleet size can be reached with different assurance-processing backlogs.

The finding does not yet establish a universal critical number. The resource work coefficients, capacities, service distributions, wait budgets, and failure definitions are notional. The current evidence supports instrumenting and testing cumulative assurance backlog on a real control plane. It does not support enforcing \(\Omega_A=1\) as an operational policy without calibration.

### 8.4 No evidence yet supports a universal coupled fleet-assurance law

The project began with a candidate Coupled Fleet Assurance Envelope. Earlier Stage 1 work showed that coupling improved prediction in selected interaction-sensitive regions but did not consistently dominate independent ceilings. Stage 2 further shows that security propagation itself resists reduction to one scalar. A credible future assurance envelope will likely need a vector state or multiple phase-specific submodels.

A defensible current statement is:

> Fleet assurance is not determined by fleet population alone, but this study has not established a universal scalar law that maps architecture and population to assurance.

## 9. Novelty assessment after Stage 2

### 9.1 What is not novel

The following should not be presented as new contributions:

1. next-generation matrices and spectral epidemic thresholds;
2. non-backtracking percolation criteria;
3. temporal infection propagators;
4. stochastic separation of major-outbreak probability and conditional final size;
5. reflected-fluid queue analysis;
6. authorization or dependency graphs for agent systems;
7. the general claim that rapid admission can overload finite processing capacity.

### 9.2 What may remain novel

The defensible novelty candidate is narrower:

> A runtime-agnostic assurance experiment framework that maps authorization, communications, common dependencies, supervisory relationships, credentials, response timing, and finite assurance-processing resources into separate compromise-initiation, compromise-severity, and admission-stability models, then evaluates them prospectively under hash-gated preregistration.

That is currently a research-method contribution and a systems synthesis. It becomes a stronger scientific contribution only if the narrowed metrics transfer to measured systems or to multiple independently implemented simulators.

Potentially original future results would include:

1. an empirically calibrated assurance-work model showing that normalized reflected backlog predicts admission failure across heterogeneous real control planes;
2. a phase-separated compromise model that predicts real or high-fidelity attack traces better than static graph and message-passing baselines;
3. a mission-preserving graph-optimization method that demonstrably reduces measured compromise propagation without unacceptable mission-performance loss;
4. a vector-valued fleet-assurance boundary that predicts unseen cross-domain failures better than independent limits.

No priority or patentability claim is made.

## 10. Threats to validity

### 10.1 Construct validity

Compromise is represented through an epidemic abstraction. Real adversaries plan, adapt, select targets, reuse credentials, exploit software, and respond strategically. The simulated mechanism does not capture every causal pathway. Final compromised fraction is only one blast-radius measure and does not represent mission impact, privilege-weighted loss, data exposure, persistence, or recovery cost.

Admission failure is represented as one or more assurance queues exceeding declared wait budgets. A real system may degrade gradually, shed workload, prioritize critical actions, add temporary capacity, or fail through a mechanism not represented by queue length.

### 10.2 Internal validity

The project uses controlled train and held-out partitions, independent seeds, frozen protocols, hash gates, and exact acceptance rules. These controls reduce tuning leakage. They do not remove all researcher degrees of freedom inherited from earlier exploratory cycles, including the selection of graph families, hazard composition, score candidates, and failure definitions.

Cycle 4 is explicitly excluded from confirmatory evidence because of a source-hash mismatch. Cycle 5 is retained as an independent-seed replication. Cycle 6 and Cycle 7 have clean matching execution manifests.

### 10.3 External validity

All operational values are notional. No attack path, workload coefficient, service capacity, detection rate, recovery rate, credential workload, supervisory demand, or wait budget has been calibrated against a deployed agent system. Results therefore transfer only to systems whose behavior is adequately represented by the implemented mechanisms.

The graph families are stylized. Real fleets may have temporal, multiplex, geographic, organizational, and common-mode structure that differs materially from the simulated topologies.

### 10.4 Statistical validity

Thirty independent replications were used per confirmatory scenario. Scenario-level held-out comparisons and bootstrap intervals were used. The experiments are terminating transients, so steady-state warmup deletion and batch means were not applicable.

Cycle 7 contains only three full independent graph blocks. The positive pooled interval is meaningful within the model, but three blocks are insufficient to characterize broad graph-family variation. Multiple metrics were evaluated, although the primary acceptance rules were fixed prospectively.

### 10.5 Model implementation validity

The software is deterministic for a fixed seed and environment, and the release test suite passes. Cross-version bit reproducibility is not yet established across Python, NumPy, SciPy, sparse eigensolver, and operating-system variants. Numerical spectral routines can also behave differently under different library versions even when scientifically equivalent.

## 11. Engineering recommendations

### 11.1 Compromise modeling

Retire the tested dynamic and temporal single-scalar models as general blast-radius predictors. Retain static pre-response non-backtracking as the current scalar baseline. Build the next experiment around one of two architectures:

1. dynamic message passing with node-level compromise probabilities and an explicit response transition;
2. a phase-separated model with a better-calibrated initiation component and a conditional severity component.

The next model should report occurrence discrimination, probability calibration, final-size error, and capability-weighted mission impact separately.

### 11.2 Fleet admission control

Instrument four minimum resource classes on a real or high-fidelity control plane:

1. identity and credential issuance;
2. authorization and dispatch;
3. telemetry registration and evidence ingest;
4. automated or human supervision.

Measure admission work \(w_r\), steady-state work \(b_r\), effective service capacity \(C_r\), queue delay, workload shedding, and acceptable wait budget \(W_r\). Compute \(\Omega_A\) prospectively and compare it with actual boundary crossing. Do not calibrate and evaluate on the same incident or admission campaign.

### 11.3 Authorization architecture

Do not infer compromise containment from the authorization graph alone. Maintain distinct authorization, communication, dependency, supervision, identity-infrastructure, and runtime attack-reachability representations. Evaluate directed path semantics and common-mode compromise before claiming a bounded blast radius.

### 11.4 Operational decision at 10,000 agents

No assurance recommendation for 10,000 agents can be issued from the current evidence. The repository demonstrates bounded execution paths and model-conditioned experiments, not deployment security. A 10,000-agent decision requires measured control-plane demand, empirical attack pathways, implementation-specific authorization semantics, timing behavior, failure recovery, and adversarial test evidence.

## 12. Next falsification experiment

The next cycle should test a phase-separated dynamic message-passing model against the strongest current baselines. It should be preregistered before generating confirmatory traces and should use at least five full independent structural blocks. The design should include:

1. held-out graph families and held-out fleet sizes;
2. correlated initial compromise and common-mode dependency events;
3. heterogeneous response delays and partial observation;
4. node-level and fleet-level outcomes;
5. static non-backtracking, temporal non-backtracking, direct regression, and message-passing comparators;
6. calibration metrics and final-size metrics as separate acceptance dimensions;
7. a measured or separately generated external trace set that is not produced by the same hazard implementation.

In parallel, \(\Omega_A\) should move from simulation novelty testing to empirical calibration. Running more synthetic admission scenarios without measured resource work would provide diminishing scientific value.

## 13. What This Study Does Not Establish

A discrete-event simulation establishes the behavior of a model. Its findings transfer to a real deployment only to the degree that the model's assumptions hold. This study cannot establish that any particular implementation is secure. It establishes structural constraints: which architectures are ruled out by mathematics and physics, and which remain candidates. Ruling out is stronger than ruling in. An architecture that violates the epidemic threshold condition or exceeds the observability ceiling is provably unmanageable at the stated scale. An architecture that satisfies every constraint identified here is merely not yet ruled out, and still requires adversarial testing, formal verification of critical components, and operational evaluation before deployment.

The phrase "unlimited agents" should be retired in favor of the precise finding this study will produce: fleets scale without bound only along axes where required coordination is O(1) or O(log N) in fleet size, and every remaining axis has a computable ceiling.

For the Stage 2 results specifically, this study does not establish that compromise behaves like an epidemic in a deployed agent system, that non-backtracking structure predicts a real cyber incident, that \(\Omega_A=1\) is an operational failure boundary, that the phase-separated estimator transfers outside the synthetic substrate, or that a fleet of any specified size can be operated with adequate assurance. It also does not establish novelty priority, patentability, freedom to operate, implementation security, or mission suitability.

## 14. Research decision

The current evidence supports four decisions.

1. **Refute and retire the tested single dynamic and temporal scalar compromise claims.**
2. **Retain \(\Omega_A\) as a strong provisional admission-stability candidate requiring empirical calibration.**
3. **Retain phase-separated compromise prediction as a narrowed hypothesis, not as an established model.**
4. **Do not claim a universal Fleet Assurance Law or a secure 10,000-agent reference architecture.**

This is a successful research outcome. The project has eliminated two attractive but inadequate formulations, preserved a promising admission construct without overstating it, and identified the specific statistical and architectural work required for the next defensible contribution.

## References

1. Britton, T. (2010). Stochastic epidemic models: A survey. *Mathematical Biosciences*, 225(1), 24-35. DOI: 10.1016/j.mbs.2010.01.006.
2. Dai, J. G., and Meyn, S. P. (1995). Stability and convergence of moments for multiclass queueing networks via fluid limit models. *IEEE Transactions on Automatic Control*, 40(11), 1889-1904.
3. Karrer, B., and Newman, M. E. J. (2010). Message passing approach for general epidemic models. *Physical Review E*, 82, 016101. DOI: 10.1103/PhysRevE.82.016101.
4. Karrer, B., Newman, M. E. J., and Zdeborova, L. (2014). Percolation on sparse networks. *Physical Review Letters*, 113, 208702. DOI: 10.1103/PhysRevLett.113.208702.
5. Tallam, K. (2026). Authorization Propagation in Multi-Agent AI Systems: Identity Governance as Infrastructure. arXiv:2605.05440.
6. Valdano, E., Ferreri, L., Poletto, C., and Colizza, V. (2015). Analytical computation of the epidemic threshold on temporal networks. *Physical Review X*, 5, 021005. DOI: 10.1103/PhysRevX.5.021005.
7. van den Driessche, P., and Watmough, J. (2002). Reproduction numbers and sub-threshold endemic equilibria for compartmental models of disease transmission. *Mathematical Biosciences*, 180, 29-48. DOI: 10.1016/S0025-5564(02)00108-6.
8. Li, C., Zhang, L., Zhai, J., et al. (2026). Towards Security-Auditable LLM Agents: A Unified Graph Representation. arXiv:2605.06812.
9. AgentFlow authors. (2026). AgentFlow: Building Agent Dependency Graphs for Static Analysis of Agent Programs. arXiv:2607.01640.

## Artifact traceability

- Cycle 5 protocol: `docs/stage2_cycle5_replication_protocol.md`
- Cycle 5 summary: `results/stage2_cycle5/stage2_cycle5_summary.json`
- Cycle 5 execution manifest: `manifests/stage2_cycle5_execution_manifest.json`
- Cycle 6 protocol: `docs/stage2_cycle6_preregistered_protocol.md`
- Cycle 6 summary: `results/stage2_cycle6/stage2_cycle6_summary.json`
- Cycle 6 execution manifest: `manifests/stage2_cycle6_execution_manifest.json`
- Cycle 7 protocol: `docs/stage2_cycle7_preregistered_protocol.md`
- Cycle 7 summary: `results/stage2_cycle7/stage2_cycle7_summary.json`
- Cycle 7 execution manifest: `manifests/stage2_cycle7_execution_manifest.json`
- Evidence ledger: `results/stage2_synthesis/evidence_ledger.csv`
- Research decision table: `results/stage2_synthesis/research_decision_table.csv`
- Machine-readable synthesis: `results/stage2_synthesis/stage2_synthesis.json`
