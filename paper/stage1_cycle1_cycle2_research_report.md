# Stage 1 Research Report: Cycles 1 and 2

Date: 2026-08-19

## Executive finding

The first two falsification cycles produced three materially different outcomes.

1. NH2, the dynamic attack-reachability hypothesis, is the strongest current research candidate. In the refined held-out test, the attack operator reduced propagation-prediction MAE by 14.1 percent relative to the raw authorization spectrum and increased held-out Spearman correlation from 0.839 to 0.908. Across four independent graph-seed robustness blocks, mean MAE improvement was 22.3 percent, the minimum block improvement was 20.8 percent, and the attack operator outperformed raw authorization correlation in all four blocks.
2. NH4, the fleet admission-trajectory hypothesis, is strongly supported inside the current notional model. At the preregistered confirmation point, all 60 step-admission runs crossed the assurance boundary while none of the 60 staged-admission runs did, despite equal final population. The separation persisted at 24 of 27 nearby capacity and ramp-duration points.
3. NH1, the coupled Fleet Assurance Envelope hypothesis, remains provisional. Cycle 1 refuted the broad formulation because the independent ceiling was already highly predictive. The refined interaction-sensitive test succeeded, but seed robustness was inconsistent: the coupled model improved AUC in six of eight independent seed blocks and worsened it in two. This is not yet sufficient to call the coupled envelope a robust scaling law.

All findings in this report are model-conditioned. Parameters are notional. No result constitutes external validation or proof of real-world secure scaling.

## Evidence classes

**Analytic or established mathematics:** none of the new Stage 1 claims are promoted to this category.

**Model-conditioned demonstration:** NH1-R, NH2-R, and NH4-R.

**External validation:** none. Real-system or independently derived data are still required.

## Cycle 1

### NH1: broad coupled-envelope prediction

The initial test compared a learned interaction model against the maximum individual normalized constraint ratio across a broad parameter space. The coupled model did not outperform the simpler baseline.

- Coupled AUC: 0.771
- Independent-ceiling AUC: 0.949
- Coupled Brier score: 0.216
- Independent Brier score: 0.130

Result: **refuted in the broad formulation**.

Interpretation: most failures in the broad sample were directly explained by one or more individual constraints already crossing their declared limits. That left little incremental information for interaction terms. This is a useful negative result because it prevents the project from asserting that coupling is always necessary.

### NH2: initial attack-reachability comparison

The first test showed only a small improvement over raw authorization spectral radius.

- Attack-operator Spearman correlation with ever-compromised fraction: 0.952
- Raw authorization Spearman correlation: 0.936

The preregistered support threshold required more than a 0.10 absolute correlation improvement, so the hypothesis was not supported in Cycle 1.

Interpretation: authorization topology still carried most of the signal in the original experiment design. A matched-authorization design was required to test whether additional graph layers contributed unique predictive information.

### NH4: initial admission-trajectory experiment

The original capacity point made both rapid and gradual admission profiles inadmissible. The step profile was much worse, but the acceptance criterion was defective because it did not require the gradual profile to remain inside the assurance boundary.

Result: **not accepted as confirmation**.

This acceptance-criterion defect was explicitly recorded and corrected before Cycle 2.

## Cycle 2 preregistered refinements

The Cycle 2 protocol is stored in `docs/stage1_cycle2_preregistered_protocol.md`. Cycle 1 data were not overwritten.

### NH1-R: interaction-sensitive assurance region

All seven exogenous normalized constraint ratios were restricted to less than 1.0. Thus the independent conjunctive ceiling considered every sampled configuration nominally inside its individual limits before endogenous interactions were applied.

Held-out results:

- Test samples: 909
- Failure rate: 40.8 percent
- Coupled AUC: 0.851
- Baseline max-margin AUC: 0.797
- AUC improvement: 0.054
- Coupled Brier score: 0.165
- Baseline Brier score: 0.198

The preregistered Cycle 2 support criterion was satisfied.

However, seed robustness reduced confidence:

- Independent seed blocks: 8
- Mean AUC improvement: 0.0295
- Blocks with positive improvement: 6 of 8
- Worst block AUC change: -0.0189

Current assessment: **provisional support only**. The concept appears useful in interaction-sensitive regions, but the present model and interaction basis are not robust enough to claim a general Coupled Fleet Assurance Envelope law.

### NH2-R: matched authorization with held-out dependency families

Authorization graphs were held fixed while dependency graph families varied. Random-regular and Erdos-Renyi dependency families were used for calibration. Barabasi-Albert and hierarchical dependency families were held out.

Results:

- Raw authorization MAE: 0.1268
- Attack-operator MAE: 0.1090
- MAE improvement: 14.1 percent
- Raw authorization Spearman correlation: 0.839
- Attack-operator Spearman correlation: 0.908

Robustness across four independent graph-seed blocks:

- Mean MAE improvement: 22.3 percent
- Minimum MAE improvement: 20.8 percent
- Blocks exceeding 10 percent improvement: 4 of 4
- Blocks with higher attack-operator correlation: 4 of 4

Current assessment: **strongest model-conditioned result in Stage 1**.

Important limitation: the stochastic compromise process is executed on the candidate weighted attack graph. Therefore, this experiment establishes internal predictive consistency and demonstrates that raw authorization topology loses information when dependency paths materially contribute. It does not validate the proposed edge semantics or weights against observed incidents.

The next scientific requirement is external or independently generated propagation evidence where the attack graph is not also the simulator's propagation substrate.

### NH4-R: equal final N, different admission trajectory

The confirmation run used a nearby capacity point that was not one of the exploratory diagnostic points used after Cycle 1:

- Initial population: 100
- Final population: 4,000
- Control-plane capacity: 165 operations per second
- Supervisory capacity: 27 reviews per second
- Staged ramp duration: 180 seconds
- Replications: 60 paired common-random-number runs

Results:

- Step admission boundary-crossing rate: 100 percent
- Staged admission boundary-crossing rate: 0 percent
- Step mean minimum assurance margin: -292.30
- Staged mean minimum assurance margin: +0.195
- Final N equal: yes

Neighborhood robustness:

- Nearby capacity and ramp-duration points tested: 27
- Points preserving step-fails/staged-passes separation: 24
- Separation fraction: 88.9 percent

Current assessment: **strong model-conditioned support** for the statement that fleet population trajectory can matter independently of final population when admission consumes finite control and supervisory resources.

This does not yet establish a universal maximum safe dN/dt. The next step is to derive and test a normalized admission-rate threshold rather than relying on named profiles such as step or staged.

## Current ranking of research contributions

### 1. Dynamic attack-reachability operator

Status: strongest candidate.

Research question: can a time-varying, multi-layer attack-reachability operator predict compromise phase transitions and blast radius better than communication or authorization topology alone?

Required next evidence:

- directed and asymmetric edge semantics;
- credentials, delegation, dependency, identity-provider, and shared-image edges represented separately;
- calibrated edge weights or uncertainty distributions;
- non-backtracking and next-generation matrix comparisons;
- independent propagation data not generated directly from the candidate operator;
- ablation tests showing which graph layers add predictive information.

### 2. Fleet admission-rate bound

Status: strong model-conditioned support.

Research question: does there exist a normalized population-velocity limit based on control-plane and supervisory settling capacity?

Required next evidence:

- derive a dimensionless admission-load number;
- sweep final N and capacity together;
- verify scale invariance or identify scaling correction terms;
- add credential issuance, telemetry registration, policy evaluation, revocation, and anomaly-review resource pools explicitly;
- test hysteresis and recovery time after a boundary crossing.

### 3. Coupled Fleet Assurance Envelope

Status: provisional.

Research question: in what regions does a coupled admissibility model outperform independent constraint ceilings?

Required next evidence:

- preserve negative Cycle 1 result as a boundary condition;
- identify interactions from mechanism, not statistical convenience;
- evaluate multiple functional forms;
- bootstrap the predicted failure boundary;
- test on held-out topology and fleet-size regions, not only held-out parameter wedges;
- establish whether one envelope transfers across architectures.

## Falsification rules going forward

1. Negative results remain in the repository and paper.
2. Acceptance criteria cannot be relaxed after observing a result. A changed criterion starts a new experimental cycle.
3. Exploratory parameter searches cannot be relabeled confirmatory. Confirmation must use a separate parameter point or held-out region.
4. A model that predicts outcomes generated by its own governing equation is evidence of internal consistency only.
5. No claim is promoted to external validity without measured or independently generated evidence.
6. A proposed scaling law must predict held-out configurations and fleet sizes before it is named as a law in publication.

## Immediate next experiments

The next cycle should prioritize NH2 and NH4.

For NH2, replace the current undirected weighted graph with a directed next-generation attack operator whose entries represent conditional compromise transition intensity. Run layer ablations and compare adjacency spectral radius, weighted spectral radius, non-backtracking radius, and next-generation spectral radius. Introduce correlated supply-chain compromise as a separate seeding process so that topology and initial conditions are not conflated.

For NH4, derive an admission load number of the form

`Lambda_admit = work_per_agent * dN/dt / spare_assurance_service_capacity`

and test whether boundary crossing occurs near a stable critical value across multiple N, capacities, and admission shapes. If a stable threshold emerges on held-out runs, it becomes a substantially stronger contribution than the current profile-based demonstration.

NH1 should continue, but it should not lead the paper until its seed and architecture robustness improves.
