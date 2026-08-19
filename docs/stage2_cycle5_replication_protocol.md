# Stage 2 Cycle 5 Independent-Seed Replication Protocol

Date frozen: 2026-08-19

Protocol identifier: FAS-S2-C5-2026-08-19

Primary seed: 20260820

Evidence classification: model-conditioned independent-seed replication using notional parameters. No external validation is claimed.

## 1. Purpose

Stage 2 Cycle 4 completed its numerical matrix, but its execution manifest reported that two frozen input hashes did not match at verification. The Cycle 4 outputs are therefore retained as diagnostic results and are not treated as confirmatory evidence.

Cycle 5 repeats the Cycle 4 equations, topology families, scale ladder, train and test splits, acceptance criteria, and reporting logic without scientific modification. It uses a new primary seed and a pre-execution hash gate. The runner must abort before simulation if any frozen input differs from the preregistration manifest.

Cycle 5 is a replication and audit cycle. Because Cycle 4 outcomes are known, Cycle 5 does not constitute an independent first test of the hypotheses. It tests whether the previously observed support or refutation pattern reproduces under a valid provenance chain and independent randomization.

## 2. Fixed evidence rules

1. No equations, predictor definitions, topology families, matrix dimensions, train and test membership rules, or acceptance thresholds may change from Cycle 4.
2. All source, test, protocol, configuration, and runner files listed in the preregistration manifest must match before execution.
3. Any mismatch causes an immediate abort with no simulation output interpreted as evidence.
4. Every stochastic replication records its seed.
5. Scenario-level means are the unit of predictor comparison.
6. Negative findings remain in the repository.
7. Cycle 4 outputs are not pooled with Cycle 5 outputs for primary acceptance decisions.
8. All findings remain conditioned on the notional model.

## 3. NH2-D replication

The candidate is the dynamic next-generation excess-exposure predictor derived from a directed multilayer compromise substrate containing authorization, communication, dependency, and supervisory pathways. Baselines are raw authorization spectral radius, symmetrized aggregate radius, static next-generation radius, and weighted non-backtracking radius.

The fixed matrix is:

- Fleet sizes: N = 160, 320, and 640.
- Authorization families: random regular, Barabasi-Albert, and hierarchical.
- Dependency families: random regular, Erdos-Renyi, Barabasi-Albert, and hierarchical.
- Segmentation: none and partitioned authorization.
- Propagation intensity levels: 0.055, 0.080, 0.115, and 0.165.
- Intervention strengths: 0.35 and 0.65.
- Intervention times: 10 and 20 simulation steps.
- Horizon: 50 simulation steps.
- Replications: 30 per configuration.
- Robustness blocks: five independent graph-seed blocks.

Training uses N = 160 and 320 with random-regular and Erdos-Renyi dependency families. Held-out testing uses N = 640 with Barabasi-Albert and hierarchical dependency families.

NH2-D is supported in the replicated model only if all conditions hold:

1. Dynamic K(t) reduces held-out MAE by at least 15 percent relative to the best baseline.
2. Dynamic K(t) improves held-out ROC AUC by at least 0.03 relative to the best baseline.
3. Dynamic K(t) improves held-out Brier score relative to the best baseline.
4. At least four of five independent robustness blocks show positive MAE improvement.
5. Dependency-layer ablation degrades held-out prediction when dependency edges contribute nonzero latent hazard.

## 4. NH4-A replication

The candidate is the reflected multi-resource admission-overload index Omega_A. It is computed from the deterministic fluid backlog for identity and authorization control, credential issuance, telemetry registration, and supervisory review. Baselines are final fleet size, maximum raw admission rate, peak instantaneous load Lambda_A, and a joint Lambda_A and Omega_A model.

The fixed matrix is:

- Final fleet sizes: 2,000, 5,000, 10,000, and 20,000.
- Admission profiles: step, linear, smooth, pulse train, front-loaded, and back-loaded.
- Capacity regimes: balanced, control-plane constrained, supervision constrained, and credential constrained.
- Ramp-duration factors: 0.25, 0.45, 0.75, 1.15, and 1.80.
- Time step: 0.5 seconds.
- Recovery window: 120 seconds.
- Replications: 30 per configuration.
- Robustness blocks: five independent stochastic-seed blocks.

Training uses final fleet sizes 2,000, 5,000, and 10,000 with step, linear, smooth, and front-loaded profiles. Held-out testing uses final fleet size 20,000 with pulse-train and back-loaded profiles.

NH4-A is supported in the replicated model only if all conditions hold:

1. Omega_A improves held-out ROC AUC by at least 0.05 relative to peak Lambda_A.
2. Omega_A reduces held-out Brier score by at least 15 percent relative to peak Lambda_A.
3. The fixed analytic threshold Omega_A = 1 achieves held-out balanced accuracy of at least 0.80.
4. The fitted 50 percent failure threshold has coefficient of variation no greater than 0.20 across valid held-out groups.
5. At least four of five robustness blocks preserve positive AUC improvement.

## 5. Statistical controls

- Scenario-level nonparametric bootstrap uses 500 draws for the reported confidence intervals.
- Predictor calibration uses training scenarios only.
- Test scenarios do not influence model selection, thresholds, or acceptance criteria.
- Replication seeds are deterministic functions of the primary seed, scenario identifier, and replication index.
- No warmup deletion is applied because the experiments are terminating transients.

## 6. Execution partitioning

The NH2 primary matrix may be executed as three atomic fleet-size blocks for N = 160, 320, and 640. Fixed structure and scenario identifier offsets reproduce the monolithic seed schedule exactly. Finalization must verify contiguous scenario identifiers 0 through 1,151, exactly 1,152 scenarios, and exactly 34,560 replication rows before analysis. This partitioning changes execution mechanics only.

## 7. Interpretation limits

This cycle can support or refute the candidate predictors only within the declared synthetic model. It cannot establish real-world compromise probabilities, operational control-plane capacity, universal epidemic thresholds, or a deployment-independent fleet admission limit. External validation requires measured authorization and dependency graphs, incident-derived mechanism intensities, measured detection and remediation distributions, and measured assurance-resource work and service rates.
