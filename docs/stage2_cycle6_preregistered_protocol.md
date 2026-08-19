# Stage 2 Cycle 6 Preregistered Protocol

**Protocol identifier:** FAS-S2-C6-2026-08-19  
**Date fixed:** 2026-08-19  
**Primary seed:** 20260821  
**Evidence scope:** Model-conditioned. All operational parameters are notional. No physical deployment validation is claimed.

## 1. Purpose

Cycle 6 follows the negative diagnostic Cycle 4 result and the invalid Cycle 5 replication attempt. It tests two narrower hypotheses without treating either earlier cycle as confirmation data.

1. **NH2-T:** a response-adjusted temporal non-backtracking metric or a temporal linear infection propagator predicts held-out compromise outcomes better than a pre-intervention non-backtracking metric.
2. **NH4-O:** the reflected multi-resource overload index \(\Omega_A\) transfers across fleet size and continuous admission-profile shape when the experiment deliberately samples both sides of the analytic boundary.

Cycle 4 revealed two design defects that Cycle 6 addresses prospectively. The NH2 majority-outbreak test was severely imbalanced, and quadratic logistic calibration could change scalar score ordering. The NH4 held-out region was almost entirely failed, so discrimination could not be evaluated. These observations define the Cycle 6 design problem. They are not pooled with Cycle 6 outputs.

## 2. Engineering pilot exclusion

Before this protocol was frozen, an engineering-only pilot used NH2 seeds beginning at 606001 and NH4 seeds beginning at 606002. It verified that the implementation executed, that the held-out NH4 subset contained both failure classes, and that output schemas were complete. Pilot values are excluded from all model fitting, candidate selection, confidence intervals, robustness counts, and hypothesis decisions. No acceptance threshold or experimental factor was changed after viewing the pilot.

## 3. Fixed evidence rules

1. Cycle 4 and Cycle 5 datasets and dispositions remain unchanged.
2. Cycle 6 uses new scenario identifiers and disjoint seed ranges derived from primary seed 20260821.
3. Scenario-level aggregates are the unit of predictor comparison.
4. Raw ROC AUC is calculated directly from each scalar score, with no calibration model capable of changing score ordering.
5. Continuous-outcome calibration is monotone in the scalar predictor and includes the same log-fleet-size term for every NH2 predictor.
6. No Cycle 6 test outcome may change targets, splits, equations, candidate selection, or acceptance thresholds.
7. A failed cycle remains a valid result.
8. The execution runner must abort before simulation if any frozen input differs from the preregistration manifest.
9. Every stochastic replication records its seed.
10. No output is described as observed operational data.

## 4. NH2-T: response-adjusted directed propagation metrics

### 4.1 Propagation substrate

The latent directed SIR substrate contains authorization, communication, dependency, and supervision pathways, latent edge multipliers, source privilege, target susceptibility, heterogeneous recovery, and response attenuation. The observable candidate uses noisy node-state estimates and nominal layer weights rather than latent transition intensities.

For source \(i\) and target \(j\), the directed hazard matrix uses row-source and column-target orientation. The stochastic simulator applies infection probability \(1-\exp(-h_j)\) from aggregate incoming hazard and node-specific recovery probability \(1-\exp(-\gamma_i)\) per step.

### 4.2 Candidate metrics

Let \(H_0\) and \(H_1\) be observable pre-response and post-response directed hazard matrices, and let \(\gamma_i\) be the observable source recovery rate.

The weighted non-backtracking operator uses edge transmissibility

\[
T_{ij}=\frac{H_{ij}}{H_{ij}+\gamma_i}.
\]

Let \(r_{NB,0}\) and \(r_{NB,1}\) be pre-response and post-response weighted non-backtracking radii. For intervention time \(t_I\) and horizon \(T\), define

\[
r_{TNB}
=
\exp\left[
\frac{t_I}{T}\ln(r_{NB,0}+\varepsilon)
+
\left(1-\frac{t_I}{T}\right)\ln(r_{NB,1}+\varepsilon)
\right].
\]

The temporal linear infection propagator uses

\[
M_k=\operatorname{diag}(e^{-\gamma})+H_k^\mathsf{T},
\]

and

\[
\Psi=M_1^{T-t_I}M_0^{t_I}.
\]

The reported score is \(g_\Psi=\rho(\Psi)^{1/T}\), estimated by deterministic normalized sparse iteration without explicitly materializing the dense product. These quantities are predictors, not exact finite-network epidemic thresholds.

### 4.3 Experimental matrix

Training region:

- fleet sizes \(N\in\{128,256\}\);
- random-regular authorization;
- random-regular and Erdos-Renyi dependency families.

Held-out region:

- fleet size \(N=512\);
- Barabasi-Albert and hierarchical authorization;
- Barabasi-Albert and hierarchical dependency families.

Both regions use:

- no segmentation and eight-way authorization partitioning;
- target observable pre-response next-generation radii \(\{0.60,0.85,1.10,1.40,1.80,2.30\}\);
- response strengths \(\{0.35,0.65\}\);
- intervention times \(\{10,25\}\) in a 50-step horizon;
- 30 independent SIR replications per scenario.

The hazard scale for each graph is selected analytically from the observable pre-response next-generation radius at unit scale. No stochastic outcome selects the scale.

### 4.4 Comparators and outcomes

Comparators:

1. raw authorization adjacency radius;
2. static pre-response next-generation radius;
3. static pre-response weighted non-backtracking radius;
4. time-weighted geometric next-generation radius;
5. temporal non-backtracking radius \(r_{TNB}\);
6. temporal propagator growth \(g_\Psi\).

Primary outcome: mean ever-compromised fraction.

Secondary outcome: scenario outbreak probability, where a replication is an outbreak when ever-compromised fraction is at least 0.10. For rank discrimination, a scenario is positive when its estimated outbreak probability is at least 0.10. This threshold is fixed before execution.

### 4.5 NH2-T acceptance rule

The better of \(r_{TNB}\) and \(g_\Psi\) is selected only from training MAE. NH2-T receives model-conditioned support only if the selected candidate satisfies every condition against static pre-response non-backtracking:

1. held-out MAE improves by at least 5 percent;
2. raw held-out ROC AUC improves by at least 0.01;
3. held-out Spearman correlation with mean ever-compromised fraction does not decrease;
4. the scenario-bootstrap 95 percent lower bound for absolute MAE improvement is greater than zero;
5. positive MAE improvement occurs in at least four of five independent reduced robustness blocks.

## 5. NH4-O: overload-targeted assurance admission experiment

### 5.1 Candidate metric

For resource \(r\), let arrival work be

\[
\lambda_r(t)=b_rN(t)+w_r\dot N_+(t),
\]

with capacity \(C_r\), wait limit \(W_r\), queue budget \(B_r=C_rW_r\), and reflected fluid backlog

\[
Q_r(t+\Delta t)=\max\{0,Q_r(t)+[\lambda_r(t)-C_r]\Delta t\}.
\]

The fleet-level overload index is

\[
\Omega_A=\max_{r,t}\frac{Q_r(t)}{B_r}.
\]

The instantaneous comparator is

\[
\Lambda_A=\max_{r,t}\frac{w_r\dot N_+(t)}{C_r-b_rN(t)}.
\]

### 5.2 Boundary-spanning design

For each fleet size, profile, and resource regime, ramp duration is solved deterministically before stochastic execution so nominal \(\Omega_A\) is closest to one of

\[
\{0.30,0.55,0.80,1.00,1.25,1.60,2.20\}.
\]

The duration solver uses only the reflected fluid equations and never observes stochastic boundary-crossing outcomes.

Training region:

- \(N_f\in\{2{,}000,5{,}000\}\);
- linear, smooth, and front-loaded profiles.

Held-out region:

- \(N_f\in\{10{,}000,20{,}000\}\);
- back-loaded and exponential profiles.

Both regions use balanced, control-constrained, supervision-constrained, and credential-constrained resource regimes, a 0.5 second time step, a 120 second recovery window, and 30 stochastic replications per scenario.

The stochastic model uses independent Poisson work arrivals and service completions for four finite-capacity resource pools: control plane, credential authority, telemetry control, and supervision.

### 5.3 Validity gate

The held-out design is valid only if at least 20 percent of scenarios have majority failure and at least 20 percent do not. Failure of this gate invalidates discrimination claims but does not support or refute the metric.

### 5.4 NH4-O acceptance rule

NH4-O receives model-conditioned support only if all conditions hold:

1. the held-out validity gate passes;
2. raw held-out AUC for \(\Omega_A\) is at least 0.90;
3. \(\Omega_A\) improves held-out AUC by at least 0.08 relative to \(\Lambda_A\);
4. fixed threshold \(\Omega_A=1\) achieves balanced accuracy of at least 0.80;
5. monotone training calibration gives a held-out Brier score at least 15 percent lower than corresponding \(\Lambda_A\) calibration;
6. the fitted 50 percent failure threshold has coefficient of variation no greater than 0.20 across held-out fleet-size and profile groups where both classes exist;
7. at least four of five independent stochastic seed blocks meet conditions 2 through 5.

## 6. Statistical controls

- Thirty independent replications per confirmatory scenario.
- Scenario-level bootstrap with 1,000 resamples.
- Five independent robustness seed blocks.
- NH2 robustness uses a reduced but fixed topology matrix.
- NH4 robustness reuses deterministic trajectories but draws independent stochastic arrival and service sequences.
- Monotone calibration is fit only on training scenarios.
- Test scenarios do not influence candidate selection or fitted calibration.
- No warmup deletion is used because both experiments are terminating transients.
- Common structural seeds are retained across predictors within a scenario.

## 7. Required outputs

1. Replication-level and scenario-level CSV datasets for NH2-T and NH4-O.
2. Predictor comparison tables.
3. Bootstrap intervals and five-block robustness tables.
4. Exact configuration, seed, code-hash, environment, and artifact manifests.
5. Figures for held-out predictor behavior, admission-boundary transition, and comparator performance.
6. A technical report that distinguishes analytical definitions, model-conditioned numerical findings, refutations, and unresolved questions.
7. A locally viewable research console that displays the held-out results and acceptance decisions.

## 8. Interpretation limits

Cycle 6 cannot establish real-world compromise rates, universal epidemic thresholds, or deployment-independent admission limits. It tests predictive transfer inside notional, independently randomized models. External validation requires measured directed dependency and authorization graphs, incident-derived transition evidence, measured credential and telemetry work, and observed supervisory service capacity.
