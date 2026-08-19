# Stage 2 Cycle 4 Preregistered Protocol

Date fixed: 2026-08-19

## Purpose

Stage 2 Cycle 4 tests two candidate contributions that survived Stage 1:

1. NH2-D: a directed, time-varying next-generation compromise operator predicts outbreak probability and blast radius better than raw authorization topology and simpler aggregate graph metrics.
2. NH4-A: a normalized multi-resource admission-overload index predicts assurance boundary crossing across fleet sizes and admission shapes better than final fleet population, raw population velocity, or peak instantaneous admission load alone.

All parameters in this cycle are notional unless explicitly identified otherwise. All results are model-conditioned. This protocol does not provide external validation.

## Fixed evidence rules

1. Training, calibration, and test partitions are assigned by topology family, fleet size, and admission-profile family before any outcome model is fitted.
2. A result generated from the same mechanistic model used to construct a predictor is classified as internal or model-conditioned evidence, not external validation.
3. Negative results remain in the repository.
4. Acceptance criteria in this protocol will not be relaxed after results are observed.
5. If the primary criterion fails, any changed design begins a new exploratory cycle with a new protocol and separate result directory.
6. Every stochastic replication records its seed.
7. Scenario-level means, rather than individual replications, are the primary unit for predictor comparison to avoid pseudo-replication.

## NH2-D: directed next-generation compromise operator

### Ground-truth propagation substrate

The stochastic propagation process uses a directed multilayer hazard graph. The graph contains separate authorization, communication, dependency, and supervisory layers. Each node has source privilege, target susceptibility, detection and recovery rate, and a correlated software-image family.

The true directed transition intensity from compromised source i to susceptible target j is generated from:

- layer-specific directed reachability;
- source privilege;
- target susceptibility;
- heterogeneous recovery;
- layer interactions;
- latent edge variation not exposed to the candidate predictor;
- a time-dependent authorization and supervisory attenuation schedule representing credential restriction and response hardening.

The candidate predictor does not receive the latent edge variation, the exact interaction coefficient, or the exact recovery rate. It receives noisy node-risk estimates and nominal layer weights. This separation prevents the candidate operator from being numerically identical to the simulation substrate.

### Candidate and baselines

The following scenario-level predictors are compared using identical calibration functions:

1. Raw directed authorization adjacency spectral radius.
2. Symmetrized Stage 1 aggregate attack-graph spectral radius.
3. Static directed next-generation spectral radius at time zero.
4. Weighted non-backtracking spectral radius at time zero.
5. Dynamic next-generation excess exposure, defined as the time integral of max(0, rho(K(t)) - 1).

Layer ablations remove one of authorization, communication, dependency, or supervision from the candidate K(t). A homogeneous-recovery ablation removes node-level recovery heterogeneity.

### Experimental matrix

- Fleet sizes: N = 160, 320, 640.
- Authorization families: random regular, Barabasi-Albert, hierarchical.
- Dependency families: random regular, Erdos-Renyi, Barabasi-Albert, hierarchical.
- Segmentation policies: none and partitioned authorization.
- Propagation intensity multipliers: four levels spanning subcritical and supercritical regimes.
- Response hardening: two intervention strengths and two intervention times.
- Replications: 30 per configuration used in the primary matrix.

The held-out test set contains N = 640 and dependency families Barabasi-Albert and hierarchical. Training uses N = 160 and 320 with random-regular and Erdos-Renyi dependency families. A calibration subset is drawn from N = 320 near the observed outbreak transition without changing test membership.

### Outcomes

- Probability ever-compromised fraction exceeds 10 percent.
- Mean ever-compromised fraction.
- Mean peak-compromised fraction.
- Mean time to extinction or horizon.

### Primary acceptance criterion

NH2-D is supported in the current model only if all conditions hold on the held-out test scenarios:

1. Dynamic K(t) reduces mean absolute error for mean ever-compromised fraction by at least 15 percent relative to the best baseline.
2. Dynamic K(t) improves ROC AUC for the 10 percent outbreak event by at least 0.03 relative to the best baseline.
3. Dynamic K(t) improves Brier score relative to the best baseline.
4. At least four of five graph-seed robustness blocks show positive MAE improvement.
5. Dependency-layer ablation degrades held-out performance when dependency edges contribute nonzero true hazard.

### Falsification conditions

The hypothesis is refuted for this model if raw authorization topology matches or exceeds dynamic K(t), if performance does not transfer to held-out N and topology families, or if layer ablations do not behave consistently with the declared propagation mechanism.

## NH4-A: multi-resource assurance admission index

### Resource model

Admission consumes four finite resource pools:

1. Identity and authorization control plane.
2. Credential issuance authority.
3. Telemetry registration and ingest control.
4. Supervisory review.

For resource r:

lambda_r(t) = b_r N(t) + w_r dN_+(t)/dt

where b_r is background work per active agent and w_r is one-time admission work per agent.

Spare service capacity is:

S_r(t) = C_r - b_r N(t)

The peak instantaneous admission load is:

Lambda_r(t) = w_r dN_+(t)/dt / S_r(t)

The deterministic fluid backlog is the reflected cumulative excess input:

Q_r^F(t) = sup over 0 <= s <= t of integral from s to t of [lambda_r(u) - C_r] du

The normalized overload impulse is:

Omega_r = max_t Q_r^F(t) / B_r

where B_r = C_r W_r,max is the declared queue budget. The fleet-level index is:

Omega_A = max_r Omega_r

### Experimental matrix

- Final fleet sizes: N_f = 2,000, 5,000, 10,000, 20,000.
- Admission shapes: step, linear, smooth staged, pulse train, front-loaded, and back-loaded.
- Resource-capacity regimes: balanced, control-plane constrained, supervisory constrained, and credential constrained.
- Ramp duration multipliers: five levels selected before execution.
- Final background utilization is constrained below 0.70 for every resource so that final N alone is not an overload condition.
- Replications: 30 per configuration.

The held-out test set contains N_f = 20,000 and the pulse-train and back-loaded profiles. Training uses N_f = 2,000, 5,000, and 10,000 with the other profiles. Calibration uses a subset of N_f = 10,000 scenarios around the boundary.

### Stochastic simulation

Arrivals and service completions are sampled independently per resource and time step from Poisson processes with the declared rates. Common random numbers are used when comparing admission profiles within a capacity regime. Boundary crossing occurs when any resource waiting-time estimate exceeds its declared maximum.

### Predictors

1. Final N only.
2. Maximum raw dN/dt.
3. Peak Lambda_A.
4. Fluid overload index Omega_A.
5. Joint model using log(1 + Lambda_A) and log(1 + Omega_A).

### Primary acceptance criterion

NH4-A is supported in the current model only if all conditions hold on the held-out test scenarios:

1. Omega_A improves ROC AUC by at least 0.05 relative to peak Lambda_A.
2. Omega_A reduces Brier score by at least 15 percent relative to peak Lambda_A.
3. The fixed analytic threshold Omega_A = 1 achieves balanced accuracy of at least 0.80.
4. The fitted 50 percent failure threshold for Omega_A has coefficient of variation no greater than 0.20 across held-out fleet sizes and resource regimes.
5. At least four of five seed blocks preserve positive AUC improvement.

### Falsification conditions

The hypothesis is refuted for this model if final N or raw dN/dt predicts boundary crossing as well as Omega_A, if the threshold fails to transfer to N_f = 20,000, or if profile shape causes material error not captured by the reflected fluid backlog.

## Statistical analysis

- Scenario-level outbreak or boundary-crossing rates are computed from 30 independent replications.
- Logistic calibration uses training scenarios only.
- Final-size calibration uses the same quadratic log-predictor form for every graph metric.
- Uncertainty is estimated by nonparametric bootstrap over scenarios, stratified by fleet size and held-out family.
- Report 95 percent percentile intervals for AUC differences, MAE improvement, Brier improvement, and fitted threshold values.
- Robustness blocks use independent graph seeds or independent stochastic seed ranges.

## Required outputs

1. Machine-readable scenario and replication datasets.
2. Summary JSON with every acceptance criterion and pass or fail state.
3. Layer-ablation results.
4. Robustness-block results.
5. Static figures and a self-contained offline research console.
6. A technical report that clearly distinguishes analytic derivation, model-conditioned evidence, refutation, and remaining evidence gaps.
