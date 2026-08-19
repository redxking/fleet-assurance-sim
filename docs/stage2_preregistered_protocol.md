# Stage 2 Preregistered Research Protocol

**Protocol identifier:** FAS-S2-2026-08-19  
**Status:** Frozen before execution of Stage 2 experiments  
**Evidence class:** Model-conditioned unless an input is explicitly identified as measured  
**Primary focus:** NH2-D directed attack-reachability and NH4-L normalized fleet-admission load

## 1. Purpose

Stage 2 attempts to falsify the two strongest Stage 1 research candidates under harder experimental conditions. The protocol is written before executing the confirmatory scripts. Negative results will remain in the repository and the acceptance criteria will not be changed after observing results.

The experiments do not establish security of a physical deployment. They test whether two candidate abstractions provide predictive value inside independently implemented stochastic models.

## 2. Prior Stage 1 limitations addressed

1. The Stage 1 compromise process executed directly on the same undirected weighted graph used as the candidate predictor. Stage 2 separates the latent propagation process from the estimated predictor.
2. The Stage 1 attack operator was undirected and static. Stage 2 uses directed layer semantics, heterogeneous removal rates, credential state, and a piecewise time-varying operator.
3. Stage 1 compared named admission profiles. Stage 2 evaluates a dimensionless load number across fleet sizes, capacities, ramp durations, and held-out profile shapes.
4. Stage 1 did not test scale transfer. Stage 2 holds out larger fleet sizes from threshold fitting.

## 3. NH2-D: Directed next-generation compromise operator

### 3.1 Candidate construct

For source agent \(i\) and target agent \(j\), let the estimated directed compromise intensity at time \(t\) be

\[
\widehat{B}_{ij}(t)=\sum_{\ell\in\mathcal{L}} \widehat{\beta}_{\ell}\,\widehat{x}^{(\ell)}_{ij}(t)\,\widehat{v}_j\,\widehat{d}_{ij},
\]

where \(\mathcal{L}\) contains authorization, communication, dependency, and supervisory pathways, \(\widehat{v}_j\) is an observable vulnerability proxy, and \(\widehat{d}_{ij}\) is an observable defense-effectiveness proxy.

The candidate next-generation operator is

\[
\widehat{K}_{ij}(t)=\frac{\widehat{B}_{ij}(t)}{\widehat{\gamma}_i},
\]

where \(\widehat{\gamma}_i\) is the estimated detection and removal rate for compromised source \(i\). The principal predictor is a duration-weighted temporal pressure derived from the pre-revocation and post-revocation spectral radii. Static \(\rho(\widehat{K}(0))\), weighted adjacency radius, and weighted non-backtracking radius are retained as comparators.

This construction is informed by next-generation matrix methods, message-passing and non-backtracking threshold methods, and temporal infection-propagator methods. It is not asserted as an exact theorem for cyber compromise.

### 3.2 Independent latent propagation model

The stochastic propagation model will not execute on \(\widehat{K}\). It will use latent edge intensities generated separately from the observable proxies. The latent model includes:

- directed, layer-specific transition intensities;
- heterogeneous target susceptibility and source removal rates;
- credential revocation that changes only applicable pathways;
- correlated supply-chain seeding by image family;
- common identity-infrastructure shock as a separate exogenous process;
- nonlinear retry or repeated-attempt effects at compromised high-authority nodes;
- stochastic recovery and finite-horizon SIR dynamics.

The estimator receives noisy proxies and declared graph layers, not latent edge multipliers or latent node susceptibility.

### 3.3 Experimental splits

- **Training region:** smaller fleet sizes and random-regular or Erdos-Renyi dependency families.
- **Held-out topology region:** Barabasi-Albert and hierarchical dependency families not used for fitting.
- **Held-out scale region:** the largest fleet size is excluded from fitting.
- **Robustness blocks:** at least five independent graph and parameter seed blocks.

Replications are aggregated at the scenario level to prevent pseudo-replication.

### 3.4 Comparators

1. Raw directed authorization adjacency spectral radius.
2. Static weighted union adjacency spectral radius.
3. Weighted non-backtracking spectral radius.
4. Static next-generation spectral radius \(\rho(\widehat{K}(0))\).
5. Temporal next-generation pressure using pre-revocation and post-revocation operators.
6. Layer ablations for authorization, communication, dependency, and supervisory pathways.

All comparators receive the same exogenous seed-burden features.

### 3.5 Primary outcomes

- mean ever-compromised fraction;
- mean peak-compromised fraction;
- large-outbreak probability, defined before execution as ever-compromised fraction at least 0.15;
- containment duration;
- prediction MAE and RMSE on held-out scenario means;
- Spearman rank correlation;
- ROC AUC for large-outbreak classification.

### 3.6 NH2-D acceptance criteria

NH2-D is supported in the model only if all conditions hold:

1. Temporal \(\widehat{K}\) reduces held-out mean absolute error for ever-compromised fraction by at least 10 percent relative to raw authorization radius in both the held-out topology and held-out scale regions.
2. Temporal \(\widehat{K}\) improves large-outbreak ROC AUC by at least 0.05 in at least one held-out region and is not worse by more than 0.01 in the other.
3. At least one non-authorization layer ablation worsens held-out MAE by at least 5 percent, demonstrating information beyond raw authorization topology.
4. The MAE improvement is positive in at least four of five independent robustness blocks.
5. No test-region result is used to select layer weights or alter the acceptance threshold.

Failure of any condition prevents promotion beyond provisional model-conditioned evidence.

## 4. NH4-L: Normalized fleet-admission load

### 4.1 Candidate construct

For assurance resource pool \(j\), define nominal spare service capacity at time \(t\) as

\[
S_j(t)=u_j C_j-b_jN(t),
\]

where \(C_j\) is service capacity, \(u_j\) is the declared target utilization, and \(b_j\) is baseline per-agent work rate.

The candidate fleet-admission load number is

\[
\Lambda_A(t)=\max_j\frac{w_j\,[dN(t)/dt]^+}{\max(S_j(t),\varepsilon)},
\]

where \(w_j\) is one-time assurance work introduced per admitted agent. The primary scalar predictor is peak \(\Lambda_A\). Duration above one and integrated excess above one are secondary predictors.

The analytic interpretation is limited: \(\Lambda_A<1\) means nominal admission work is below declared spare target capacity for every modeled resource pool at that instant. It does not by itself prove stochastic queue stability.

### 4.2 Independent queueing model

The simulated outcome uses a multi-pool stochastic fluid queue with:

- identity issuance;
- authorization and policy registration;
- telemetry and evidence registration;
- supervisory review;
- heterogeneous service capacities and wait limits;
- correlated service-capacity disturbances;
- queue-dependent retries;
- delayed capacity recovery;
- sustained-boundary dwell logic;
- final unregistered-agent backlog.

The candidate \(\Lambda_A\) is calculated from nominal capacities and first-order work. It does not include realized disturbances or retry feedback.

### 4.3 Experimental splits

- **Training sizes:** 1,000 and 2,500 agents.
- **Held-out scale sizes:** 5,000 and 10,000 agents.
- **Training profile shapes:** linear, staged, and burst.
- **Held-out profile shapes:** exponential and finite step-ramp.
- **Capacity and duration sweep:** at least three baseline-load fractions, four ramp durations, and three disturbance levels.
- **Robustness:** at least five independent seed blocks.

Every scenario is constructed so that final baseline load, with admission complete and no transient work, remains below the target utilization for each resource pool. This isolates admission transients from trivial final-state overload.

### 4.4 Comparators

1. Final fleet population \(N_f\).
2. Peak raw admission rate \(\max dN/dt\).
3. Conventional peak total offered-load ratio.
4. Peak \(\Lambda_A\).
5. Peak \(\Lambda_A\) plus integrated excess above one.

### 4.5 Primary outcome

A run is inadmissible if any of the following occurs:

- a resource-specific wait limit is exceeded continuously for at least the declared dwell interval;
- the unregistered fleet fraction exceeds 5 percent at the end of the horizon;
- the coupled retry loop causes queue growth through the final 20 percent of the horizon.

Scenario outcome is the fraction of replications that become inadmissible.

### 4.6 NH4-L acceptance criteria

NH4-L is supported in the model only if all conditions hold:

1. A threshold \(\Lambda_c\) fitted only on the training region achieves held-out balanced accuracy of at least 0.80 in both the held-out scale and held-out shape regions.
2. Peak \(\Lambda_A\) improves held-out ROC AUC by at least 0.08 relative to both final \(N\) and peak raw \(dN/dt\).
3. The fitted \(\Lambda_c\) lies within 25 percent of one and has coefficient of variation no greater than 20 percent across robustness blocks.
4. Directionality is monotone: scenario failure probability must not decrease materially as peak \(\Lambda_A\) increases after conditioning on disturbance level and final baseline load. Operationally, held-out Spearman correlation must be at least 0.70.
5. At least four of five robustness blocks satisfy criteria 1 and 2.

If the threshold transfers only after adding architecture-specific correction terms, the universal formulation is refuted and replaced with a conditional model.

## 5. Statistical methods

- Minimum 20 independent replications per scenario for confirmatory runs.
- Common random numbers are used only for paired profile comparisons within a scenario block.
- Scenario means are the independent units for regression and correlation.
- Ninety-five percent bootstrap confidence intervals use scenario-level resampling.
- Threshold selection on training data maximizes balanced accuracy with deterministic tie-breaking toward the threshold closest to one.
- All random seeds are written to the result dataset.
- No warmup deletion is applied to terminating transient experiments.

## 6. Publication gates

A candidate will not be called a law, theorem, or externally validated metric unless it later satisfies all of the following:

1. predicts outcomes generated by an independent implementation;
2. transfers to unseen architectures and fleet sizes;
3. survives parameter and seed robustness tests;
4. has uncertainty bounds and identified failure regions;
5. receives empirical calibration or adversarial test evidence from a real system.

## 7. Foundational references

- P. van den Driessche and J. Watmough, "Reproduction Numbers and Sub-threshold Endemic Equilibria for Compartmental Models of Disease Transmission," Mathematical Biosciences 180, 29-48, 2002. DOI: 10.1016/S0025-5564(02)00108-6.
- B. Karrer, M. E. J. Newman, and L. Zdeborova, "Percolation on Sparse Networks," Physical Review Letters 113, 208702, 2014. DOI: 10.1103/PhysRevLett.113.208702.
- E. Valdano, L. Ferreri, C. Poletto, and V. Colizza, "Analytical Computation of the Epidemic Threshold on Temporal Networks," Physical Review X 5, 021005, 2015. DOI: 10.1103/PhysRevX.5.021005.
- J. G. Dai and S. P. Meyn, "Stability and Convergence of Moments for Multiclass Queueing Networks via Fluid Limit Models," IEEE Transactions on Automatic Control 40, 1889-1904, 1995. DOI: 10.1109/9.471210.

## 8. Frozen decision rule

This protocol may be corrected only for an implementation error that makes the stated experiment impossible to execute. Any scientific change after observing results creates a new cycle with a new protocol identifier. Original outputs remain preserved.
