# Fleet Assurance Simulation

Public repository: [github.com/redxking/fleet-assurance-sim](https://github.com/redxking/fleet-assurance-sim)

Version 0.2.0 contains the executable foundation for formal and visual simulation of secure multi-agent fleet scaling, the Stage 0 analytic verification base, Stage 1 exploratory work, Stage 2 preregistered falsification cycles, and the completed immutable Stage 3 confirmation of the surviving fleet-admission and phase-separated compromise candidates.

This repository does not claim that any deployed multi-agent system is secure. Results are evidence about the implemented model under explicit assumptions and parameter provenance. The current integrated scenarios are notional.


## Local deployment

For a clean workstation setup, start with `QUICKSTART.md` and then use `LOCAL_DEPLOYMENT.md` for complete macOS, Linux, Windows, Docker, Conda, verification, and troubleshooting instructions.

The current research working copy occupies approximately 1.79 GiB, including generated evidence and the dedicated Stage 3 verification environment. The immutable confirmatory execution occupies approximately 22.8 MiB, while its retained HTML and JSON console exports occupy approximately 331.3 MiB combined. See `LOCAL_DEPLOYMENT.md` before copying or regenerating evidence.

## Current build status

The implemented software and evidence-integrity gates pass. Stage 2 Cycles 5 through 7 and the Stage 3 confirmation completed under their documented evidence rules. Scientific hypothesis support is a separate decision and did not pass for either Stage 3 track.

- The complete prefreeze suite passed 113 unit, statistical, replay, integration, visualization, and research-protocol tests.
- Stage 0 M/M/1, gossip, percolation, deterministic replay, and bounded N=10,000 execution-path checks remain valid.
- Cycle 5 independently replicated and refuted the tested single dynamic next-generation compromise score.
- Cycle 6 preregistered and refuted the training-selected temporal scalar for final-size prediction.
- Cycle 6 produced strong provisional evidence for the reflected multi-resource fleet-admission overload index `Omega_A`, but the hypothesis did not satisfy its fixed superiority and robustness requirements.
- Cycle 7 improved pooled held-out final-size MAE by 18.8 percent with a positive hierarchical-bootstrap interval, but the fixed two-stage hypothesis did not pass all block-level and probability-calibration criteria.
- Cycle 7 executed 34,560 stochastic replications across 1,152 scenarios, with every frozen protocol, configuration, source, test, and environment input matching its preregistered SHA-256 digest.
- Stage 3 confirmation `stage3-confirmatory-20260819-01` passed all execution-integrity checks under protocol hash `b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851`.
- Stage 3A retained 25,200 raw rows and 21,600 held-out predictions. It failed calibration-slope and 1.25-capacity-transfer conjuncts and is `not_supported_under_preregistered_rule`.
- Stage 3B retained 2,400 raw rows and 1,200 held-out predictions. It failed eight required prediction, calibration, block, and transfer conjuncts and is `not_supported_under_preregistered_rule`.
- All Stage 3 results are synthetic and model-conditioned. No external operational dataset was supplied, and no external validation was performed.

The current research decision is deliberately conservative. No universal fleet assurance law, operationally validated attack-reachability operator, secure 10,000-agent architecture, or deployment assurance claim has been established.

The public repository is intentionally curated. It includes source, protocols, tests, reports, figures, compact synthesis, and the immutable synthetic confirmation needed for technical review. It excludes local environments, caches, engineering-pilot outputs, oversized offline console exports, and verification scratch data. See `docs/public_repository_scope.md` and `CONTRIBUTING.md` before proposing changes.

Primary Stage 2 artifacts:

- `paper/stage2_cycles5_to7_research_report.md`
- `replay_bundles/stage2-research-evidence-console.html`
- `results/stage2_synthesis/stage2_synthesis.json`
- `results/stage2_synthesis/evidence_ledger.csv`
- `results/stage2_synthesis/research_decision_table.csv`
- `manifests/stage2_cycle6_execution_manifest.json`
- `manifests/stage2_cycle7_execution_manifest.json`

Primary Stage 3 artifacts:

- `docs/stage3_preregistered_protocol.md`
- `docs/stage3_architecture.md`
- `manifests/stage3_preexecution_manifest.json`
- `results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01/stage3_evidence.json`
- `results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01/execution_manifest.json`
- `results/stage3/consoles/stage3-confirmatory-20260819-01.html`
- `results/stage3/consoles/stage3-confirmatory-20260819-01.json`
- `paper/stage3_research_report.md`
- `results/stage3_synthesis/stage3_synthesis.json`
- `results/stage3_synthesis/evidence_ledger.csv`
- `results/stage3_synthesis/research_decision_table.csv`
- `docs/stage3_research_decision_table.md`
- `figures/stage3/figure_manifest.csv`
- `figures/stage3/figure_provenance.json`
- `figures/stage3/*.png`
- `manifests/stage3_research_release_manifest.json`

## Implemented capabilities

### Scientific and mathematical foundation

- Universal Scalability Law prediction, fitting, bootstrap intervals, and retrograde point
- Candidate Coupled Fleet Assurance Envelope primitives with normalized constraint margins and binding-constraint identification
- Candidate containment-race and dynamic fleet-admission-rate constructs, explicitly marked for falsification rather than established as laws
- Directed multilayer authorization, communication, dependency, and supervisory compromise operators
- Static and temporal non-backtracking predictors, infection-propagator candidates, and layer ablations
- Two-stage compromise estimation separating outbreak initiation from conditional severity
- Separate Stage 3 attack-trace generation, bounded observed predictor views, directed dynamic message passing, and explicit common-cause inputs
- Ten-resource Stage 3A assurance-admission network covering identity issuance, certificate issuance and renewal, authorization policy evaluation, task dispatch registration, telemetry source registration, evidence ingest initialization, supervisory review, revocation readiness, configuration attestation, and dependency registration
- Reflected fluid backlog, peak admission load, accumulated overload, and boundary-targeted experiment generation
- Authenticated preregistration manifests, atomic checkpoints, held-out topology and fleet-size tests, common-random-number pairs, and hierarchical bootstrap intervals
- M/M/1 and M/M/c analytics, Erlang C, Little's Law checks, and server sizing
- PBFT-class, threshold-leader, and bounded-committee message and byte accounting
- Gossip dissemination over complete and sparse topology families
- Finite stochastic SIS and SIR compromise models
- Spectral-radius and heterogeneous mean-field diagnostics
- Bond-percolation blast-radius distributions and critical-q approximation
- First-order-plus-dead-time control analysis and Foster-Lyapunov drift helper
- Hierarchical telemetry, Gaussian rate-distortion, and observability ceiling primitives
- Fiber propagation, clock holdover, ordering, Landauer, credential, cost, and energy primitives

### Simulation and security architecture

- Runtime-agnostic agent and capability interface
- Deterministic callback event queue with stable tie breaking
- Named NumPy PCG64DXSM random substreams
- Separate communication and authorization graphs
- Complete, random regular, Erdos-Renyi, Barabasi-Albert, and hierarchical topologies
- Partition, gateway-based microsegmentation, and degree-cap policies
- Multi-server authorization queue
- Task arrival, authorization, dispatch, completion, and useful-completion accounting
- Compromise, boundary traversal, detection, quarantine, revocation, recovery, timing denial, credential renewal, and mass-revocation events
- Canonical JSONL event log, CSV export, snapshots, state hashes, and execution manifests

### Visualization

- Self-contained offline HTML replay console with no runtime network dependency
- Local Bokeh console with Replay, Comparison, Scenario, and Live-capture modes
- Separate Stage 3 offline HTML and JSON evidence console with admission, compromise, defense, DMP-state, lifecycle, and sampled-graph views
- Communication and authorization layer toggles
- Event playback, stepping, seek, and speed controls
- Node inspection and operational timelines for control-plane queueing, security, timing, and credentials
- Representation labels when graph rendering is sampled or aggregated

## Repository layout

```text
configs/                Scenario, parameter, and visualization configuration
docs/                   Architecture, RTM, acceptance status, roadmap, and prompt
figures/                Generated PNG and SVG figures
manifests/              Environment and seed manifests
replay_bundles/         Immutable run artifacts and visual consoles
results/                Machine-readable metrics and reports
scripts/                Reproducible build entry points
src/fleet_sim/          Simulation, models, analysis, and visualization code
tests/                  Unit, statistical, replay, and integration verification
```

## Installation

Python 3.11 or later is required. The immutable Stage 3 confirmation used Python 3.13.0 and the exact packages in `requirements-stage3-freeze.txt`.

```bash
python -m pip install -e ".[dev]"
```

Optional scientific outputs require:

```bash
python -m pip install -e ".[science]"
```

`pyarrow` is required for Parquet output. `SALib` is required for the future Sobol sensitivity workflow. Stage 0 does not silently substitute another method when those dependencies are absent.

## Reproduce Stage 0

```bash
fleet-sim stage0 \
  --repository-root . \
  --output local_runs/stage0-v020-001 \
  --replications 30
```

Primary outputs:

```text
local_runs/stage0-v020-001/results/stage0/stage0_report.json
local_runs/stage0-v020-001/paper/stage0_verification_report.md
local_runs/stage0-v020-001/results/stage0/queue_verification.csv
local_runs/stage0-v020-001/results/stage0/gossip_verification.csv
local_runs/stage0-v020-001/results/stage0/percolation_verification.csv
local_runs/stage0-v020-001/results/stage0/usl_verification_observations.csv
local_runs/stage0-v020-001/figures/stage0/
local_runs/stage0-v020-001/replay_bundles/mixed-100-visual-*/
```

## Inspect the immutable Stage 3 confirmation

The Stage 3 protocol has already been frozen and executed. Do not rerun the recorded confirmation command in this release or replace its directory. Inspect the machine-readable disposition with:

```bash
python -m json.tool \
  results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01/stage3_evidence.json \
  > /dev/null
```

Build a separate offline console copy without mutating the execution:

```bash
mkdir -p local_runs/stage3-consoles
.venv-stage3-verify/bin/python scripts/build_stage3_evidence_console.py \
  --mode replay \
  --execution results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01 \
  --output local_runs/stage3-consoles/stage3-confirmatory-20260819-01-copy.html \
  --json-output local_runs/stage3-consoles/stage3-confirmatory-20260819-01-copy.json
```

Stage 2 Cycle 7 also remains frozen and retained. Run `scripts/run_stage2_cycle7.py` only in a separate research copy with the corresponding immutable protocol inputs intact.

Verify the entire repository test suite:

```bash
pytest -q
```

The frozen preexecution source reported `113 passed`. Documentation-only release packaging occurs after that scientific freeze.

## Execute one scenario

```bash
fleet-sim run \
  --config configs/baselines/mixed_100_visual.yaml \
  --output local_runs/general-v020-001 \
  --visualize
```

Verify a stored replay bundle:

```bash
fleet-sim verify-replay \
  --bundle replay_bundles/<run-id>
```

Regenerate a self-contained console from a bundle:

```bash
fleet-sim visualize \
  --bundle replay_bundles/<run-id> \
  --output replay_bundles/<run-id>/virtual_fleet_assurance_console.html
```

## Open the visual environment

The self-contained HTML console can be opened directly in a browser.

The completed Stage 3 confirmatory console and offline JSON export are:

```text
results/stage3/consoles/stage3-confirmatory-20260819-01.html
results/stage3/consoles/stage3-confirmatory-20260819-01.json
```

The multi-run local console is launched with:

```bash
fleet-console --root .
```

For a remote or noninteractive host:

```bash
fleet-console --root . --no-browser --port 5006
```

Live mode currently executes an immutable scenario and then autoplays the captured event stream. True streaming while the simulation is executing remains planned and is not represented as complete.

## Baseline scenarios

- `configs/baselines/mixed_100_visual.yaml`: integrated 100-agent Stage 0 visual verification scenario
- `configs/experiments/stage0_demo.yaml`: extended 64-agent attack, timing-denial, and revocation demonstration
- `configs/baselines/flat_dense_100.yaml`: flat communication and authorization demonstration
- `configs/baselines/microsegmented_100.yaml`: segmented authorization demonstration
- `configs/baselines/low_1000_metrics.yaml`: bounded N=1,000 scale check
- `configs/baselines/low_10000_metrics.yaml`: bounded N=10,000 scale check

The flat and microsegmented scenarios are demonstrations with multiple architecture variables changed. They must not be treated as a controlled causal estimate of segmentation benefit.

## Evidence and provenance

Each simulation summary includes an evidence class, parameter class, limitations, configuration hash, event-log digest, and replay-validation hashes. The parameter registry is in `configs/parameters/registry.yaml`.

The current registry is incomplete relative to the final study. Any parameter without a named published measurement or stated real-system measurement method must remain labeled notional or inferred.

## Acceptance and traceability

- Stage 0 report: `paper/stage0_verification_report.md`
- Stage 2 report: `paper/stage2_cycles4_7_research_report.md`
- Stage 2 research decision record: `docs/stage2_research_decision_record.md`
- Cycle 7 protocol: `docs/stage2_cycle7_preregistered_protocol.md`
- Cycle 7 execution manifest: `manifests/stage2_cycle7_execution_manifest.json`
- Machine-readable Stage 0 report: `results/stage0/stage0_report.json`
- Acceptance gates: `docs/acceptance_status.md`
- Architecture: `docs/architecture.md`
- Visualization guide: `docs/visual_console.md`
- Experiment roadmap: `docs/experiment_roadmap.md`
- Novelty review: `docs/novelty_review_2026-08-19.md`
- Novelty-driven Stage 1 plan: `docs/stage1_novelty_driven_plan.md`
- Candidate research claims: `configs/research_claims.yaml`
- Data dictionary: `docs/data_dictionary.md`
- Requirements traceability matrix: `docs/requirements_traceability.csv`
- Stage 2 research report: `paper/stage2_cycles5_to7_research_report.md`
- Stage 2 evidence console: `replay_bundles/stage2-research-evidence-console.html`
- Stage 2 research decision table: `docs/stage2_research_decision_table.md`
- Stage 3 preregistered protocol: `docs/stage3_preregistered_protocol.md`
- Stage 3 architecture: `docs/stage3_architecture.md`
- Stage 3 preexecution manifest: `manifests/stage3_preexecution_manifest.json`
- Stage 3 confirmatory evidence: `results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01/stage3_evidence.json`
- Stage 3 confirmatory console: `results/stage3/consoles/stage3-confirmatory-20260819-01.html`
- Stage 3 research report: `paper/stage3_research_report.md`
- Stage 3 machine-readable synthesis: `results/stage3_synthesis/stage3_synthesis.json`
- Stage 3 evidence ledger: `results/stage3_synthesis/evidence_ledger.csv`
- Stage 3 machine-readable decision table: `results/stage3_synthesis/research_decision_table.csv`
- Stage 3 research decision table: `docs/stage3_research_decision_table.md`
- Stage 3 publication figures: `figures/stage3/*.png`
- Stage 3 figure manifest and provenance: `figures/stage3/figure_manifest.csv`; `figures/stage3/figure_provenance.json`
- Stage 3 research release manifest: `manifests/stage3_research_release_manifest.json`
- Public repository scope: `docs/public_repository_scope.md`
- Contribution guidance: `CONTRIBUTING.md`
- Security reporting: `SECURITY.md`

## Explicitly incomplete

The following are not complete in version 0.2.0:

- Full staged design of experiments across all architecture combinations
- Thirty or more replications for each published integrated configuration
- Sobol global sensitivity analysis
- Steady-state warmup, batch-means, and autocorrelation workflow for integrated queues
- Dolev-Yao, Byzantine, insider, and instruction-manipulation event models; broader package-lineage supply-chain and identity-adversary models also remain incomplete, while Stage 3 implements bounded synthetic, model-conditioned shared-image common-cause compromise and Sybil admission mechanisms
- CRDT payload and convergence simulation
- Closed-loop supervisory thrashing simulation
- Rate-distortion anomaly-loss model
- Remaining controlled hypothesis tests in the broader H1 through H7 program
- Doctoral technical paper
- Production reference architecture recommendation
- Scale-ladder decision table

## Scientific interpretation rule

A simulation establishes the behavior of a model. An architecture that violates a mathematical or physical constraint can be ruled out under the stated assumptions. An architecture that satisfies the implemented constraints is only not yet ruled out. Deployment assurance still requires implementation-specific threat modeling, formal verification of critical components, adversarial testing, and operational evaluation.
