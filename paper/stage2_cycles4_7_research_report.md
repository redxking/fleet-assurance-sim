# Stage 2 Research Report: Cycles 4 Through 7

**Date:** 2026-08-19  
**Author:** Angelis Pseftis  
**Research status:** Version-zero strawman for technical critique  
**Evidence scope:** Analytic derivations and model-conditioned numerical experiments using notional parameters. No external deployment validation.

## Executive decision

Stage 2 did not establish a new assurance scaling law. It did produce three consequential findings that materially narrow the research program.

First, the originally proposed scalar dynamic next-generation score does not predict compromise outcomes better than established static spectral baselines. An exact independent-seed replication confirmed the negative result. This claim should be retired in its original form.

Second, a reflected multi-resource overload index, denoted Omega_A, is a strong candidate for predicting transient fleet-admission failure. In the boundary-targeted Cycle 6 experiment it achieved held-out ROC AUC 0.9917, reduced calibrated probability error by 50.6 percent relative to peak instantaneous load, produced balanced accuracy 0.833 at the analytic threshold Omega_A = 1, and transferred with threshold coefficient of variation 0.1949. It nevertheless failed the preregistered incremental-AUC and robustness gates. Omega_A is promising, but it is not yet supported as a general admission criterion.

Third, compromise propagation behaves as a two-stage stochastic process in the implemented model. Separating outbreak initiation from conditional outbreak severity reduced pooled held-out final-size MAE by 18.8 percent relative to the stronger of two direct spectral comparators. The hierarchical bootstrap 95 percent interval for absolute MAE reduction was [0.00392, 0.01374], and every independent block improved. The Cycle 7 model still failed its conjunctive support rule because only one of three blocks exceeded 15 percent improvement and initiation-probability calibration was noninferior in only one of three blocks. This is the strongest current research direction, but it remains a candidate rather than an accepted contribution.

The correct scientific conclusion is therefore:

> Fleet compromise cannot be reduced to one graph radius, and fleet admission cannot be reduced to final population or peak population velocity. The strongest current models separate initiation from severity and instantaneous load from accumulated overload. Neither formulation is externally validated.

## 1. Research questions

Stage 2 addressed two questions.

### RQ1: Compromise propagation

Can a runtime-agnostic, directed, multilayer graph operator predict compromise initiation and blast radius across unseen fleet sizes and topology families better than raw authorization topology or established non-backtracking predictors?

### RQ2: Fleet admission stability

Can a normalized multi-resource overload quantity predict when agent admission overwhelms identity, credential, telemetry, and supervisory service capacity across fleet sizes and admission profiles?

## 2. Evidence taxonomy

Results are classified as follows.

### 2.1 Established mathematics used by the study

The study uses established results and methods, including:

- message-passing and non-backtracking formulations for irreversible spreading on sparse networks;
- temporal infection propagators based on products of time-indexed linear operators;
- reflected fluid backlog and deterministic queue bounds;
- monotone calibration, constrained regression, bootstrap uncertainty, and two-part statistical models.

These methods are not claimed as original. Non-backtracking message passing is established in the percolation literature, temporal infection propagators are established for time-varying contact networks, and deterministic backlog bounds are established in network calculus.

### 2.2 Model-conditioned numerical evidence

Cycles 5, 6, and 7 generated held-out numerical evidence from a directed multilayer stochastic propagation model and a four-resource stochastic queue model. Every operational parameter remains notional.

### 2.3 External validation

None. No observed autonomous-agent incident, production authorization graph, measured credential service, measured telemetry-registration workload, or operational supervisory queue was used.

## 3. Integrity chronology

### 3.1 Cycle 4

Cycle 4 completed its numerical matrix, but the post-run execution manifest detected frozen-input hash mismatches. The entire cycle was disqualified as confirmatory evidence. Its files were retained as diagnostic data.

The diagnostic pattern was strongly negative for the original dynamic graph score and non-discriminating for the original admission matrix. Those observations informed the independent replication and boundary redesign, but they were not promoted to confirmatory results.

### 3.2 Cycle 5

Cycle 5 was an exact independent-seed replication of Cycle 4, executed through hash-gated atomic partitions. All frozen inputs matched. It reproduced the negative outcome.

### 3.3 Cycle 6

Cycle 6 prospectively replaced the original compromise score with response-adjusted temporal non-backtracking and infection-propagator candidates. It also redesigned the admission experiment to span the predicted Omega_A boundary by solving ramp duration from deterministic fluid equations before stochastic outcomes were generated.

### 3.4 Cycle 7

Cycle 7 tested a preregistered two-stage compromise model using three complete independent graph and stochastic seed blocks. The model separated macroscopic outbreak initiation from compromise severity conditional on an outbreak. All frozen inputs matched and all three blocks passed validity gates.

## 4. Formal models

## 4.1 Directed multilayer compromise substrate

For source agent i and target agent j, the synthetic propagation substrate contains directed authorization, communication, dependency, and supervisory pathways. The true transition intensity is a function of source privilege, target susceptibility, layer membership, layer interactions, latent edge variation, and time-varying response attenuation.

The candidate observable models receive noisy node-risk estimates and nominal graph-layer information. They do not receive the latent edge multipliers or exact recovery parameters.

For candidate hazard matrix H and source recovery vector gamma, the next-generation matrix is

\[
K = \operatorname{diag}(\gamma^{-1})H.
\]

The static next-generation score is

\[
r_K = \rho(K).
\]

The non-backtracking score is the Perron root of the weighted Hashimoto operator constructed from directed edge transmissibilities.

For pre-response and post-response non-backtracking scores, Cycle 6 defined

\[
r_{TNB}
=
\exp\left[
\frac{t_I}{T}\log(r_{NB,0}+\varepsilon)
+
\left(1-\frac{t_I}{T}\right)\log(r_{NB,1}+\varepsilon)
\right].
\]

The temporal infection propagator used one-step operators

\[
M_k = \operatorname{diag}(e^{-\gamma}) + H_k^T
\]

and

\[
\Psi=M_1^{T-t_I}M_0^{t_I},
\qquad
g_{\Psi}=\rho(\Psi)^{1/T}.
\]

These are candidate predictors, not exact finite-network SIR laws.

## 4.2 Two-stage compromise estimator

Cycle 7 modeled outbreak initiation separately from outbreak severity.

The outbreak event was

\[
O = \{F \ge 0.10\},
\]

where F is the ever-compromised fleet fraction.

The initiation model estimated

\[
P_O(x)=P(O\mid x)
\]

using training-only isotonic calibration of r_TNB.

Conditional outbreak severity was

\[
S_O(x)=
\operatorname{clip}_{[0.10,1]}
\left[
\theta_0+
\theta_1\log(1+r_{NB,0})+
\theta_2\log N
\right],
\qquad \theta_1\ge 0.
\]

The non-outbreak fraction was fixed as one initially compromised agent:

\[
S_{\bar O}(N)=\frac{1}{N}.
\]

Expected final compromise was

\[
\widehat F
=
\widehat P_O\widehat S_O
+
(1-\widehat P_O)S_{\bar O}.
\]

This decomposition was motivated by the observation that spectral scores ranked outbreak-prone scenarios well but did not consistently estimate mean final size.

## 4.3 Multi-resource admission overload

For assurance resource r, admission demand was

\[
\lambda_r(t)=b_rN(t)+w_r\dot N_+(t),
\]

where b_r is background work per active agent and w_r is one-time admission work per agent.

Spare capacity was

\[
S_r(t)=C_r-b_rN(t).
\]

Peak instantaneous admission load was

\[
\Lambda_r(t)=
\frac{w_r\dot N_+(t)}{S_r(t)}.
\]

The deterministic reflected backlog was

\[
Q_r^F(t)=
\sup_{0\le s\le t}
\int_s^t[\lambda_r(u)-C_r]du.
\]

With queue budget

\[
B_r=C_rW_{r,\max},
\]

the resource overload index was

\[
\Omega_r=
\frac{\max_t Q_r^F(t)}{B_r},
\]

and the fleet-level index was

\[
\Omega_A=\max_r\Omega_r.
\]

Omega_A = 1 is the deterministic fluid boundary at which one modeled assurance resource exhausts its declared queue-delay budget.

## 5. Experimental matrix

## 5.1 Compromise experiments

The primary Cycle 6 and each Cycle 7 block used:

- N in {128, 256} for training and N = 512 for held-out evaluation;
- random-regular authorization with random-regular and Erdos-Renyi dependencies for training;
- Barabasi-Albert and hierarchical authorization and dependency families for held-out evaluation;
- no segmentation and eight-way authorization partitioning;
- target observable pre-response next-generation radii {0.60, 0.85, 1.10, 1.40, 1.80, 2.30};
- response strengths {0.35, 0.65};
- intervention times {10, 25} in a 50-step horizon;
- 30 independent terminating replications per scenario.

Cycle 7 executed three full independent blocks totaling:

- 1,152 scenarios;
- 34,560 stochastic replications;
- 576 held-out scenario predictions.

## 5.2 Admission experiments

Cycle 6 used:

- training final fleets N_f in {2,000, 5,000};
- held-out final fleets N_f in {10,000, 20,000};
- training profiles linear, smooth, and front-loaded;
- held-out profiles back-loaded and exponential;
- four resource-capacity regimes;
- target Omega_A values {0.30, 0.55, 0.80, 1.00, 1.25, 1.60, 2.20};
- 30 stochastic replications per scenario.

Ramp duration was solved using only deterministic fluid equations. Stochastic boundary outcomes were not consulted during target selection.

## 6. Results

## 6.1 Cycle 5: exact replication of the original dynamic operator

The dynamic K(t) candidate failed every preregistered criterion.

| Metric | Dynamic candidate | Strongest baseline | Difference |
|---|---:|---:|---:|
| Held-out MAE | 0.03946 | 0.03844 | -2.65% relative improvement |
| ROC AUC | 0.74869 | 0.99215 | -0.24346 |
| Brier score | 0.01646 | 0.00874 | 88.5% worse |
| Positive robustness blocks | 0 of 5 | Required 4 of 5 | Failed |

Dependency-layer ablation did not degrade predictive performance. This matters because the original novelty claim required the dynamic multilayer operator to capture information unavailable in raw authorization structure. Under the implemented model and candidate construction, it did not.

**Decision:** NH2-D was refuted in its original form.

The original admission matrix also failed to span the outcome boundary. Omega_A and peak Lambda_A both had AUC 0.5 because nearly all held-out scenarios occupied the same outcome class. This was a design failure, not evidence that both predictors were equivalent.

## 6.2 Cycle 6: temporal metrics and boundary-targeted admission

### 6.2.1 Temporal compromise prediction

The training-selected temporal infection-propagator candidate did not transfer to held-out topologies.

| Metric | Temporal candidate | Static non-backtracking | Difference |
|---|---:|---:|---:|
| Held-out MAE | 0.05686 | 0.04717 | -20.52% relative improvement |
| ROC AUC | 0.97763 | 0.97619 | +0.00144 |
| Spearman correlation | 0.91165 | 0.90743 | +0.00423 |

The candidate slightly improved ranking while materially worsening calibrated final-size prediction. The bootstrap interval for absolute MAE reduction was entirely negative: [-0.01512, -0.00462].

All five reduced robustness blocks showed positive MAE improvement for the primary selected candidate, but the full held-out matrix did not. This contradiction is a scale and design-transfer warning. Reduced robustness matrices did not substitute for the full held-out region.

**Decision:** NH2-T was not supported.

### 6.2.2 Admission overload

The redesigned admission experiment passed its validity gate and produced both failed and non-failed held-out scenarios.

| Metric | Omega_A | Peak Lambda_A | Difference or threshold |
|---|---:|---:|---:|
| ROC AUC | 0.99167 | 0.93333 | +0.05833 |
| Brier score | 0.11833 | 0.23935 | 50.56% reduction |
| Balanced accuracy at Omega_A = 1 | 0.83333 | Not applicable | Passed 0.80 criterion |
| Threshold coefficient of variation | 0.19487 | Not applicable | Passed 0.20 criterion |
| Robustness blocks passing | 3 of 5 | Required 4 of 5 | Failed |

Omega_A was a strong predictor, but it missed the preregistered incremental AUC requirement of 0.08 and the four-of-five robustness requirement. Two robustness blocks had AUC improvements of 0.07685 and 0.07954, narrowly below the fixed threshold.

**Decision:** NH4-O was not supported under the conjunctive rule. The result remains a strong candidate for external calibration.

## 6.3 Cycle 7: two-stage compromise estimator

All three blocks passed validity gates. The held-out class counts were stable, and each training set contained macroscopic outbreaks.

| Block | Hurdle MAE | Best direct baseline MAE | Improvement | Brier improvement | AUC delta |
|---:|---:|---:|---:|---:|---:|
| 0 | 0.03197 | 0.03734 | 14.38% | -1.94% | +0.00121 |
| 1 | 0.03378 | 0.04777 | 29.28% | +11.71% | -0.00096 |
| 2 | 0.04404 | 0.05007 | 12.03% | -7.57% | +0.00305 |

Pooled results were:

- hurdle MAE: 0.03660;
- best baseline MAE: 0.04506;
- pooled improvement: 18.77 percent;
- bootstrap 95 percent interval for absolute MAE reduction: [0.00392, 0.01374];
- bootstrap 95 percent interval for fractional improvement: [8.80%, 29.19%].

The candidate satisfied five of seven substantive conditions:

- all three blocks valid;
- pooled improvement at least 15 percent;
- all blocks had positive improvement;
- bootstrap lower bound above zero;
- AUC degradation remained within 0.01.

It failed two conditions:

- only one block, rather than at least two, improved by at least 15 percent;
- initiation Brier score was noninferior in only one of three blocks.

The acceptance rule was conjunctive and was not changed after observing results.

**Decision:** NH2-H was not supported under the preregistered rule.

## 7. Interpretation

## 7.1 What the experiments rule out

The following claims should not be made from this project:

1. A single dynamic spectral radius is a general predictor of fleet compromise severity.
2. Time averaging or geometric combination of pre-response and post-response radii automatically improves held-out final-size prediction.
3. A good outbreak-ranking metric is necessarily a good expected-blast-radius estimator.
4. A successful reduced robustness matrix guarantees transfer to the full held-out topology and scale region.
5. Omega_A has been established as a universal safe admission limit.
6. Any result proves secure deployment at N = 10,000 or at unbounded scale.

## 7.2 What the experiments support as model behavior

Within the notional model:

1. Static and temporal non-backtracking scores are strong rank predictors of macroscopic outbreaks.
2. Final compromise fraction contains two distinct sources of uncertainty: whether a macroscopic outbreak begins and how large it becomes if it begins.
3. A two-stage estimator substantially reduces pooled final-size MAE compared with direct scalar prediction.
4. Initiation calibration is the current weak link. The severity component was comparatively stable, while initiation Brier error varied by block.
5. Accumulated overload contains information not represented by peak admission load alone.
6. Solving experimental inputs to span a predicted boundary is necessary before AUC or threshold-transfer claims are interpretable.

## 7.3 Why Cycle 7 matters despite non-support

Cycle 7 did not pass its support rule, but it changed the scientific model of the problem.

A scalar graph score attempts to estimate both the probability of leaving the single-compromise regime and the severity of the resulting cascade. Those are not the same random quantity. The observed improvement from separating them was consistent in direction across three independent blocks and had a positive hierarchical-bootstrap lower bound.

The failure was not lack of signal. It was lack of sufficient block-level consistency and probability-calibration stability under a demanding rule. That distinction should guide the next experiment.

## 8. Novelty assessment after falsification

The individual methods are established and should not be claimed as novel:

- non-backtracking spectra;
- temporal infection propagators;
- reflected backlog and network calculus;
- isotonic calibration;
- hurdle or two-part statistical models.

The remaining candidate contribution is narrower:

> A runtime-agnostic fleet assurance framework that maps authorization, dependency, communication, response timing, and finite assurance-service capacity into separate initiation, severity, and admission-overload predictions, with held-out topology and scale falsification.

That statement is currently a research-program description, not an accepted theorem or externally validated architecture.

The strongest potentially original element is the system-level coupling and experimental discipline, not any one equation. A defensible publication would need to show that the decomposition transfers to an independently generated substrate or measured system data rather than only to additional random seeds of the same simulator.

## 9. Threats to validity

### 9.1 Construct validity

Compromise is represented by a directed SIR-like process. Real autonomous-agent compromise can include persistent credentials, stealth, reinfection, policy manipulation, common-mode software defects, and adversarial adaptation. The current process does not capture all of those mechanisms.

### 9.2 Parameter validity

Layer weights, privilege factors, susceptibility, response attenuation, recovery rates, admission work, and service capacities are notional. Numerical thresholds cannot be transferred to an operational fleet.

### 9.3 Graph validity

Synthetic random-regular, Erdos-Renyi, Barabasi-Albert, and hierarchical graphs are topology families, not measured enterprise or mission authorization graphs. They support structural stress testing but not operational prevalence claims.

### 9.4 Statistical validity

Thirty replications per scenario provide scenario-level estimates but can leave outbreak probability noisy near transition regions. Cycle 7 showed that initiation calibration remains sensitive to this variation.

### 9.5 External validity

No red-team trace, incident graph, production identity provider, certificate authority, telemetry pipeline, or human-review queue was used. The study remains one level removed from operational evidence.

## 10. Recommended next research gate

The next cycle should not be another unrestricted synthetic parameter sweep. It should be an evidence-transfer gate.

### 10.1 Compromise data required

Collect or construct an independently governed test corpus containing:

- directed authorization edges with capability scopes;
- communication and service-dependency edges;
- credential lifetime and revocation timestamps;
- detection and containment timestamps;
- attack or red-team transition paths;
- initially compromised identity or software-image family;
- final affected-resource set and mission-weighted consequence.

The minimum useful corpus should preserve events that did not propagate, because initiation calibration cannot be evaluated from successful cascades alone.

### 10.2 Admission data required

Instrument a real or representative control plane to measure:

- identity issuance operations per admitted workload;
- authorization-policy compilation and distribution work;
- certificate issuance and renewal work;
- telemetry-registration and schema-validation work;
- supervisory alerts generated during admission;
- service capacity, queue depth, and delay by resource pool;
- recovery time after burst admission.

Use these measurements to replace notional b_r, w_r, C_r, and W_r,max values.

### 10.3 Decision rule

Do not promote a fleet assurance scaling law unless the candidate predicts:

1. unseen topology families;
2. unseen fleet sizes;
3. unseen stochastic seeds;
4. an independently generated simulator or measured testbed;
5. at least one operational dataset collected prospectively.

## 11. What this study does not establish

A discrete-event simulation establishes the behavior of a model. Its findings transfer to a real deployment only to the degree that the model's assumptions hold. This study cannot establish that any particular implementation is secure. It establishes structural constraints: which architectures are ruled out by mathematics and physics, and which remain candidates. Ruling out is stronger than ruling in. An architecture that violates the epidemic threshold condition or exceeds the observability ceiling is provably unmanageable at the stated scale. An architecture that satisfies every constraint identified here is merely not yet ruled out, and still requires adversarial testing, formal verification of critical components, and operational evaluation before deployment.

The phrase "unlimited agents" should be retired in favor of the precise finding this study will produce: fleets scale without bound only along axes where required coordination is O(1) or O(log N) in fleet size, and every remaining axis has a computable ceiling.

For this Stage 2 increment, the stronger statement is:

> No scalar graph metric tested here was sufficient to predict both compromise initiation and severity across unseen topology and scale. A two-stage estimator was materially better in pooled error but did not meet all preregistered consistency and calibration gates. Accumulated assurance-resource overload was strongly predictive in the notional queue model but did not meet all incremental and robustness gates.

## 12. Reproducibility and artifacts

The repository contains:

- frozen protocols and preregistration manifests for Cycles 5, 6, and 7;
- execution manifests with source and output hashes;
- all scenario and replication datasets;
- predictor outputs and robustness tables;
- static figures;
- automated tests;
- a self-contained Stage 2 research console.

Cycle 7 completed with every frozen input matching its preregistration manifest.

## References

1. Karrer, B., Newman, M. E. J., and Zdeborova, L. (2014). Percolation on sparse networks. *Physical Review Letters*, 113, 208702. https://doi.org/10.1103/PhysRevLett.113.208702
2. Valdano, E., Ferreri, L., Poletto, C., and Colizza, V. (2015). Analytical computation of the epidemic threshold on temporal networks. *Physical Review X*, 5, 021005. https://doi.org/10.1103/PhysRevX.5.021005
3. Valdano, E., Poletto, C., and Colizza, V. (2015). Infection propagator approach to compute epidemic thresholds on temporal networks. *European Physical Journal B*, 88, 341. https://doi.org/10.1140/epjb/e2015-60620-5
4. Le Boudec, J.-Y., and Thiran, P. (2001). *Network Calculus: A Theory of Deterministic Queuing Systems for the Internet*. Springer, LNCS 2050.
5. Tallam, K. et al. (2026). Authorization Propagation in Multi-Agent AI Systems. arXiv:2605.05440.
6. Muruaga, X. (2026). Bounded Agents: Delegation Security for Multi-Agent AI Systems. arXiv:2608.15888.
