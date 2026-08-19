# Stage 1 Cycle 2 Preregistered Protocol

Date: 2026-08-19

This protocol was written after Cycle 1 and is therefore a refinement study, not an untouched confirmatory first test. Cycle 1 results remain immutable and are not overwritten.

## NH1-R: Interaction-sensitive Coupled Fleet Assurance Envelope

Purpose: determine whether coupling adds predictive value in a region where every exogenous normalized constraint ratio is individually below 1.0.

Sampling: 4,000 configurations, seven exogenous ratios uniformly sampled from [0.45, 0.98]. Thus the independent conjunctive ceiling classifies every configuration as nominally admissible before endogenous interactions are applied.

Held-out region: 0.55 < observability ratio < 0.82, revocation ratio > 0.68, and control-plane ratio < 0.86. No samples from this geometric region are used to fit the candidate coupled model.

Primary comparison: held-out ROC AUC of the predeclared coupled interaction model versus max-single-margin score. Secondary metric: Brier score.

Support criterion: coupled AUC improvement >= 0.02 and lower Brier score. This supports only predictive value inside the declared notional model.

## NH2-R: Matched-Authorization Attack-Reachability Test

Purpose: determine whether a multi-layer attack-reachability operator predicts propagation better than raw authorization spectrum when authorization topology is held fixed and dependency topology changes.

Authorization families: random regular degree 4, random regular degree 8, Barabasi-Albert m=2, hierarchical span 6.

Dependency families: random regular degree 3 and 10, Erdos-Renyi mean degree 3 and 12, Barabasi-Albert m=1 and 5, hierarchical span 4 and 12.

Training dependency families: random regular and Erdos-Renyi. Held-out dependency families: Barabasi-Albert and hierarchical.

Replications: 30 per scenario, common deterministic seed schedule. Outcome is ever-compromised fraction under weighted stochastic SIR.

Primary comparison: held-out mean absolute error after one-dimensional linear calibration using raw authorization threshold product versus attack-operator threshold product. Secondary metric: Spearman correlation.

Support criterion: attack-operator MAE at least 10 percent lower than raw-authorization MAE and held-out Spearman correlation higher.

## NH4-R: Confirmation of Admission-Trajectory Effect

Cycle 1 exploratory diagnostics showed that the original capacities made all profiles inadmissible. The confirmation run therefore uses a nearby capacity point not used in that diagnostic sweep: control-plane capacity 165 ops/s and supervisory capacity 27 reviews/s, ramp duration 180 s.

Population: N0=100, Nf=4,000. All profiles end at the same N.

Profiles: step and staged smooth admission. Replications: 60 paired common-random-number runs.

Primary outcome: probability that the run ever crosses the declared assurance boundary. Secondary outcomes: minimum assurance margin and maximum queue sizes.

Support criterion: step profile is inadmissible in at least 95 percent of replications while staged profile remains admissible in at least 90 percent of replications.

## Evidence limitation

All parameters are notional and all findings are model-conditioned. A positive result verifies that the proposed research construct has discriminatory power inside the simulator. It does not establish external validity or a physical law.
