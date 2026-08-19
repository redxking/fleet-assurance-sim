# Experiment Roadmap

## Stage 0: Analytic and software verification

Status: implemented and passing.

Purpose: verify deterministic execution, replay, known queueing behavior, gossip scaling trend, percolation transition behavior, analytic consensus accounting, physical formulas, and integrated visualization.

## Stage 1: Novelty-driven falsification and parameter screening

Stage 1 is governed by `docs/novelty_review_2026-08-19.md`, `docs/stage1_novelty_driven_plan.md`, and `configs/research_claims.yaml`. Feature work that does not test NH1 through NH5 is lower priority.

Planned outputs:

- Coupled Fleet Assurance Envelope recorder and independent-ceiling baseline
- Dynamic dependency, supervisory, and attack-reachability graph layers
- Time-varying fleet population N(t) with step, ramp, burst, and staged admission
- Assurance-specific observability experiment with latent hazard state and evidence-loss model
- Timing effects on credential, revocation, and forensic-order semantics
- Train/calibration/held-out experiment partitions for predictive boundary testing
- Valid scenario generator covering every topology, coordination, consistency, and segmentation family
- Morris or elementary-effects screening for a broad parameter set
- Common-random-number pairing across architecture variants
- First controlled flat versus hierarchical architecture comparison
- Warmup classification by experiment type
- Measurement schema extended to duration, event count, trace level, approximation mode, envelope margin, and binding constraint

## Stage 2: Global sensitivity

Planned outputs:

- Saltelli or another Sobol-compatible design
- First-order and total-order Sobol indices
- Confidence intervals on sensitivity estimates
- Explicit separation of stochastic noise from parametric uncertainty
- Optional SALib dependency acceptance gate

## Stage 3: Threshold-focused experiments

Planned outputs:

- Utilization cliffs around rho=0.7 through saturation
- USL retrograde-point localization
- Spectral-radius and recovery-rate phase boundaries
- Bond-percolation critical regions
- Supervisory-loop oscillation boundaries
- Timing-denial crossover from commit wait to logical clocks
- Observability ceilings under rate-distortion constraints

## Stage 4: Scale-ladder architecture comparison

Scale values: 1, 10, 100, 1,000, 10,000, 30,000, and 100,000.

Every reported stochastic configuration will use at least 30 independent replications. Exact event simulation will be used where feasible. Any mean-field, graph-sampled, or aggregate model must first be compared against exact execution at N=1,000 and report approximation error.

## Stage 5: Adversarial and rare-event stress

Planned adversaries:

- Dolev-Yao network manipulation
- Byzantine and colluding agents
- Credentialed insiders
- Correlated supply-chain compromise
- Instruction-channel manipulation within held capability
- Sybil identity-admission pressure
- Identity and control-plane common-mode compromise

Rare-event methods will be considered only after ordinary Monte Carlo is shown to be insufficient for the target probability range.

## Stage 6: Large-scale approximation checks

Planned outputs:

- Agent-based versus mean-field comparison at N=1,000
- Error bounds by metric and parameter region
- Memory and wall-clock budgets
- Trace sampling policy that does not change scientific metrics
- 30,000 and 100,000 agent extrapolation checks
