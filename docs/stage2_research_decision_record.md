# Stage 2 Research Decision Record

**Decision date:** 2026-08-19  
**Scope:** Cycles 4 through 7  
**Decision authority:** Research protocol and preregistered acceptance gates  
**Evidence class:** Analytic derivation plus model-conditioned numerical evidence using notional parameters

## Decision summary

No Stage 2 construct is promoted to an accepted assurance law, operational predictor, or externally validated architecture rule.

The research program will retain three distinct decisions.

1. Retire the original scalar dynamic K(t) compromise score in its tested form.
2. Continue Omega_A as a bounded fleet-admission research candidate, but do not claim a general threshold.
3. Advance the Cycle 7 two-stage compromise model to an independent-data transfer gate, but retain its unsupported status under the Cycle 7 preregistered rule.

## Decision 1: Original dynamic K(t)

**State:** Refuted in the implemented model and independently replicated.

Cycle 5 reproduced the negative Cycle 4 pattern with all frozen-input hashes matching.

- Dynamic held-out MAE: 0.03946
- Best baseline MAE: 0.03844
- Relative MAE improvement: -2.65 percent
- Dynamic AUC: 0.74869
- Best baseline AUC: 0.99215
- AUC difference: -0.24346
- Positive robustness blocks: 0 of 5
- Dependency ablation degraded performance: no

**Disposition:** Do not spend additional synthetic-compute budget tuning a single scalar radius intended to predict both outbreak initiation and final blast radius.

## Decision 2: Temporal spectral alternatives

**State:** Unsupported.

Cycle 6 prospectively tested temporal non-backtracking and infection-propagator candidates. The selected candidate improved rank behavior slightly but worsened held-out final-size MAE.

- Candidate MAE: 0.05686
- Static baseline MAE: 0.04717
- Relative MAE improvement: -20.52 percent
- Candidate AUC: 0.97763
- Baseline AUC: 0.97619
- AUC difference: +0.00144
- Bootstrap 95 percent interval for absolute MAE reduction: [-0.01512, -0.00462]

**Disposition:** Retain temporal graph metrics as explanatory covariates, not standalone final-size predictors.

## Decision 3: Multi-resource admission overload Omega_A

**State:** Promising but unsupported.

Cycle 6 redesigned the admission experiment to span the predicted boundary and held final background utilization below its resource limits.

- Held-out scenarios: 112
- Positive scenarios: 72
- Negative scenarios: 40
- Omega_A AUC: 0.99167
- Peak Lambda_A AUC: 0.93333
- AUC difference: +0.05833
- Omega_A Brier score: 0.11833
- Peak Lambda_A Brier score: 0.23935
- Brier reduction: 50.56 percent
- Balanced accuracy at Omega_A = 1: 0.83333
- Threshold coefficient of variation: 0.19487
- Robustness blocks satisfying the complete block rule: 3 of 5

The preregistered support rule required AUC improvement of at least 0.08 and four of five passing robustness blocks. Those conditions were not met.

**Disposition:** Preserve Omega_A as a candidate admission-risk indicator. The next experiment must use measured or independently generated resource-demand and service-capacity data. Another synthetic parameter search is not sufficient evidence.

## Decision 4: Two-stage compromise estimator

**State:** Strongest candidate, but unsupported under the Cycle 7 conjunctive rule.

Cycle 7 separated two processes:

1. probability of a macroscopic outbreak;
2. expected compromise severity conditional on an outbreak.

The final estimator was the probability-weighted combination of those stages. Three complete independent blocks were executed with all frozen-input hashes matching.

- Replications: 34,560
- Scenarios: 1,152
- Held-out predictions: 576
- Pooled candidate MAE: 0.03660
- Pooled best-baseline MAE: 0.04506
- Pooled relative improvement: 18.77 percent
- Bootstrap 95 percent interval for absolute MAE reduction: [0.00392, 0.01374]
- Bootstrap 95 percent interval for fractional improvement: [8.80 percent, 29.19 percent]
- Blocks with positive MAE improvement: 3 of 3
- Blocks with at least 15 percent MAE improvement: 1 of 3
- Blocks with noninferior initiation Brier score: 1 of 3

The candidate passed the pooled-improvement, all-block-positive, bootstrap, validity, and AUC-nondegradation gates. It failed two conjunctive gates, so the decision remains unsupported.

**Disposition:** Advance only to an evidence-transfer experiment. Do not tune the Cycle 7 model against the existing held-out results. Freeze the current form and evaluate it against an independently generated propagation substrate or measured operational data.

## Load-bearing scientific conclusion

The implemented evidence rejects the assumption that one scalar graph score should predict both whether compromise becomes macroscopic and how large the compromise becomes after initiation.

The strongest current formulation treats fleet compromise as a hurdle process:

\[
P(F) = P(O)P(F\mid O) + P(\neg O)P(F\mid \neg O),
\]

where O is a macroscopic outbreak event and F is final compromised fraction.

The admission results similarly reject final fleet population and peak population velocity as sufficient descriptors. Accumulated overload across finite assurance resources carries additional predictive information.

These conclusions are model-conditioned. They identify which research directions survived falsification. They do not establish operational security.

## Next evidence gate

The next cycle shall be designed around evidence transfer rather than additional unrestricted synthetic tuning.

Minimum required inputs are:

- directed authorization and delegation relationships from an operational or independently generated system;
- communication and dependency relationships that are not derived from the candidate predictor;
- measured or defensibly estimated detection, recovery, credential, and revocation times;
- measured control-plane, credential-authority, telemetry-registration, and supervisory service rates;
- incident or controlled-adversary outcomes sufficient to distinguish outbreak initiation from conditional severity;
- separate training and held-out organizations, architectures, or operating periods.

The frozen Cycle 7 candidate shall be evaluated without refitting on the held-out transfer set. Any recalibration creates a new model version and requires a new protocol.

## Traceability

- Full report: `paper/stage2_cycles4_7_research_report.md`
- Visual console: `replay_bundles/stage2-cycles4-7-research-console.html`
- Cycle 5 summary: `results/stage2_cycle5/stage2_cycle5_summary.json`
- Cycle 6 summary: `results/stage2_cycle6/stage2_cycle6_summary.json`
- Cycle 7 summary: `results/stage2_cycle7/stage2_cycle7_summary.json`
- Cycle 7 protocol: `docs/stage2_cycle7_preregistered_protocol.md`
- Cycle 7 preregistration manifest: `manifests/stage2_cycle7_preregistration_manifest.json`
- Cycle 7 execution manifest: `manifests/stage2_cycle7_execution_manifest.json`
