# Stage 2 Cycle 7 Preregistered Protocol

**Protocol identifier:** FAS-S2-C7-2026-08-19  
**Date fixed:** 2026-08-19  
**Primary seed:** 20260823  
**Evidence scope:** Model-conditioned. All operational parameters are notional. No physical deployment validation is claimed.

## 1. Purpose

Cycle 7 tests a fixed two-stage compromise-propagation estimator. Prior cycles showed that a single scalar score can rank outbreak-prone scenarios while still predicting mean final compromise poorly. The candidate therefore separates two stochastic quantities:

1. outbreak initiation probability; and
2. final compromised fraction conditional on an outbreak.

The Cycle 7 model was selected before Cycle 7 execution. Cycle 5B and the Cycle 6 secondary analysis motivated the model but are excluded from Cycle 7 fitting, bootstrap intervals, and acceptance decisions.

## 2. Fixed model

For scenario state vector \(x\), define

\[
P_O(x)=P(\text{ever-compromised fraction}\ge 0.10\mid x).
\]

The initiation component estimates \(P_O\) using a nondecreasing isotonic calibration of temporal non-backtracking score \(r_{TNB}\), fitted on training scenarios only.

Conditional outbreak severity is modeled as

\[
S_O(x)=\operatorname{clip}_{[0.10,1]}
\left[
\theta_0+\theta_1\log(1+r_{NB,0})+\theta_2\log N
\right],
\]

with \(\theta_1\ge 0\). The coefficients are estimated by weighted constrained least squares. Each training scenario is weighted by the square root of its number of outbreak replications.

The conditional non-outbreak fraction is fixed analytically as

\[
S_{\bar O}(N)=\frac{1}{N},
\]

which represents one initially compromised agent when no macroscopic outbreak occurs.

The expected final compromise fraction is

\[
\widehat F
=
\widehat P_O\widehat S_O
+
(1-\widehat P_O)S_{\bar O}.
\]

No predictor, coefficient form, clipping bound, or score assignment may change after this protocol is frozen.

## 3. Experimental substrate

Cycle 7 reuses the independently randomized, directed multilayer SIR generator from Cycle 6. The latent substrate contains authorization, communication, dependency, and supervisory pathways, heterogeneous node recovery, latent edge multipliers, and response attenuation. Candidate scores use noisy observable quantities rather than latent transition parameters.

Each independent block contains the full matrix:

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
- 30 independent stochastic replications per scenario.

Three complete independent graph and stochastic seed blocks are executed. Their block seeds are deterministic offsets from primary seed 20260823 and are fixed in configuration.

## 4. Comparators

The candidate is compared against two direct continuous predictors, each fitted on training scenarios using the same constrained score and log-fleet-size form:

1. static pre-response non-backtracking score \(r_{NB,0}\);
2. temporal non-backtracking score \(r_{TNB}\).

For every block, the primary comparator is the lower-MAE direct predictor on that held-out block. This is conservative because it grants the baseline oracle selection between the two prespecified direct forms.

For initiation calibration, the comparator is an isotonic calibration of static pre-response non-backtracking score.

## 5. Outcomes

Primary outcome:

- scenario mean ever-compromised fraction.

Primary error metric:

- held-out mean absolute error.

Secondary outcomes:

- outbreak-probability Brier score against observed scenario outbreak rate;
- ROC AUC for classifying scenarios with outbreak rate at least 0.10;
- conditional-severity coefficient stability;
- fraction of training scenarios containing at least one outbreak.

## 6. Validity gate

A block is valid only if:

1. its held-out set contains at least 20 positive and 20 negative scenarios under the fixed 0.10 outbreak-rate label;
2. at least 20 percent of training scenarios contain one or more outbreak replications;
3. all 30 replication seeds are present for every scenario;
4. no fitted or predicted value is nonfinite.

A failed validity gate is reported as invalid, not as support or refutation.

## 7. Acceptance rule

NH2-H receives model-conditioned support only if every condition holds:

1. all three independent blocks pass the validity gate;
2. pooled held-out MAE improves by at least 15 percent relative to the stronger direct comparator;
3. all three blocks have positive MAE improvement, and at least two blocks improve by at least 15 percent;
4. the hierarchical scenario bootstrap 95 percent lower bound for absolute MAE reduction is greater than zero;
5. initiation Brier score is no worse than static non-backtracking in at least two of three blocks;
6. initiation ROC AUC is not lower than static non-backtracking by more than 0.01 in any block.

The acceptance rule is conjunctive. A near miss is not converted into support.

## 8. Statistical controls

- Thirty independent terminating replications per scenario.
- Three complete independent graph and stochastic seed blocks.
- Training and held-out topology families remain disjoint within every block.
- All model fitting occurs independently inside each block using only that block's training partition.
- Held-out outcomes do not select predictors or alter equations.
- Hierarchical bootstrap samples blocks and then scenarios within sampled blocks, preserving paired candidate and comparator errors.
- No warmup deletion is used because the experiment is terminating.
- All seeds, source hashes, environment versions, and output hashes are recorded.

## 9. Interpretation limits

Cycle 7 can support or refute this estimator only inside the notional directed propagation model. It cannot establish real-world compromise probabilities, validate an epidemic threshold for deployed autonomous agents, or demonstrate implementation security. External validation requires measured authorization and dependency graphs, observed incident propagation, measured detection and remediation rates, and prospectively collected test cases.
