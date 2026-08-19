# Stage 1 Novelty-Driven Experiment Plan

Stage 1 is now organized around falsification of NH1 through NH5 rather than broad feature accumulation.

## Gate 1: Coupled Fleet Assurance Envelope

Implement an envelope recorder on every integrated run. Record each normalized constraint margin, the binding constraint, and whether the declared operating point is admissible. Begin with a conjunctive independent model, then fit interaction terms only from training runs. Evaluate on held-out parameter regions.

Acceptance criterion: a coupled model must improve held-out prediction of assurance failure over the independent-ceiling baseline before CFAE is claimed as more than synthesis.

## Gate 2: Dynamic attack reachability

Add dependency and supervisory graph layers and derive a time-varying attack-reachability graph. Edge weights must represent modeled exploitability or authorized action transfer, not generic communication. Compare adjacency spectral radius, a weighted next-generation operator, and non-backtracking alternatives against stochastic compromise outcomes.

Acceptance criterion: the proposed attack-reachability operator must outperform raw authorization adjacency for blast-radius and transition prediction under held-out scenarios.

## Gate 3: Admission trajectory

Allow N(t) rather than fixed N. Implement step, linear-ramp, burst, and staged admission profiles. Admission must consume identity issuance, telemetry registration, supervisory review, and control-plane resources. Removal and emergency revocation must produce corresponding transients.

Acceptance criterion: identify at least one reproducible region where two runs with the same final N and workload distribution have different admissibility outcomes because their admission trajectories differ.

## Gate 4: Assurance observability

Define latent critical fleet states and evidence needed to infer them. Implement aggregation/compression channels that can destroy specific evidence features. Measure critical-state miss probability and anomaly-class recall as evidence rate is reduced.

Acceptance criterion: demonstrate a repeatable evidence-rate/fidelity frontier tied to a declared assurance inference task. Generic telemetry compression savings are not sufficient.

## Gate 5: Temporal security interaction

Extend timing degradation beyond transaction wait. Model uncertainty in credential expiry, lease validity, revocation ordering, and forensic event ordering.

Acceptance criterion: timing uncertainty must measurably affect at least one security assurance property distinct from external-consistency throughput before a separate temporal-assurance contribution is claimed.

## Statistical design

Use paired common random numbers for architecture comparisons. Partition parameter space into train, calibration, and held-out regions before model fitting. The envelope and attack-reachability models must be evaluated on held-out runs to prevent a post-hoc boundary from being mistaken for a predictive law. Bootstrap uncertainty around fitted boundaries. Use Sobol-compatible sampling only when estimating Sobol indices.

## Visualization requirements

The Virtual Fleet Assurance Console shall add:

- an assurance-envelope panel showing every constraint margin and the current binding constraint;
- an admission-rate timeline with N(t), dN/dt, supervisory utilization, credential load, and envelope margin;
- layer toggles for dependency, supervisory, and dynamic attack-reachability graphs;
- a boundary-crossing marker when a run changes admissibility state;
- side-by-side playback of rapid and gradual admission runs ending at the same N;
- a model-comparison panel showing predicted versus realized compromise and assurance outcomes.

Every novel-claim visualization must be backed by machine-readable run data. No visual threshold may be inferred only from rendering.
