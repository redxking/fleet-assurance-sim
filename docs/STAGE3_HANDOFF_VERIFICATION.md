# Stage 3 Handoff Verification

**Project:** Formal and Visual Simulation of Secure Multi-Agent Fleet Scaling  
**Verification date:** 2026-08-19  
**Decision:** CONDITIONAL GO  
**Stage 2 baseline:** `../fleet-assurance-stage2-baseline`  
**Stage 3 working copy:** `../fleet-assurance-stage3-working`

## 1. Executive decision

The supplied Stage 2 release is accepted as the immutable research baseline for Stage 3. Its archive checksum and file-level manifest verify, the documented 51-test suite passes in a clean environment, deterministic smoke and replay results reproduce, the local console responds, and an isolated Cycle 7 regeneration preserves the reported scientific decision.

This is a conditional go. New work must occur only in the Stage 3 working copy. The Stage 2 baseline must remain unchanged. Cross-platform Cycle 7 regeneration preserved numerical results and decisions but did not preserve byte-identical output hashes. Stage 3 must therefore distinguish release integrity, deterministic replay within a fixed environment, and numerical equivalence across environments.

Nothing in this verification establishes deployment assurance, implementation security, a secure fleet-size limit, a universal fleet assurance law, or an operational threshold at `Omega_A = 1`.

## 2. Evidence classification

| Classification | Meaning in this report |
|---|---|
| Verified | Directly checked against the supplied archive, extracted baseline, manifest, or executed verification result |
| Reproduced | Independently executed in the handoff environment with the recorded result |
| Supported within the current model | Numerical evidence from the synthetic model under its declared assumptions |
| Refuted within the current model | The specific preregistered formulation failed its fixed criteria and produced contrary evidence |
| Provisional | Promising model-conditioned evidence that has not passed all fixed criteria or external validation |
| Not established | No sufficient evidence exists for the claim |

## 3. Baseline preservation, checksum result, and provenance

- Source archive: `fleet-assurance-sim-local-release-2026-08-19.zip`
- Reported and verified SHA-256: `bfbb5aeaa3847e7dc765c0842ac4b06d4d6b5e8f1c89ecaf9760ea863fa92945`
- Immutable extraction: `../fleet-assurance-stage2-baseline`
- Extraction time: `2026-08-19T12:38:08-04:00`
- Development location: `../fleet-assurance-stage3-working`
- File-level integrity result: all 412 entries in `MANIFEST.sha256` matched the corresponding archive payload
- Archive inventory: 413 files, including `MANIFEST.sha256`

The Stage 2 baseline is the evidentiary reference. Generated Stage 3 artifacts, local verification outputs, and future experimental outputs must not be written into it.

`manifests/stage2_research_release_manifest.json` records a 392-file research-tree snapshot. `MANIFEST.sha256` covers 412 packaged payload files because release packaging and deployment artifacts were added after that research-tree snapshot. The file-level manifest is the authoritative final archive inventory.

Machine-readable provenance for this handoff is recorded in `BASELINE_PROVENANCE.json`.

## 4. Files inspected

The minimum required handoff files were located and inspected:

- `README.md`
- `QUICKSTART.md`
- `LOCAL_DEPLOYMENT.md`
- `RELEASE_NOTES.md`
- `pyproject.toml`
- `requirements-runtime.txt`
- `requirements-dev.txt`
- `requirements-science.txt`
- `requirements-lock.txt`
- `environment.yml`
- `Dockerfile`
- `docker-compose.yml`
- `docs/acceptance_status.md`
- `docs/stage2_research_decision_table.md`
- `paper/stage2_cycles5_to7_research_report.md`
- `paper/stage2_cycles4_7_research_report.md`
- `results/stage2_synthesis/stage2_synthesis.json`
- `results/stage2_synthesis/evidence_ledger.csv`
- `results/stage2_synthesis/research_decision_table.csv`
- `manifests/stage2_research_release_manifest.json`
- `manifests/stage2_delivery_manifest.json`
- Cycle 5, Cycle 6, and Cycle 7 protocols, preregistration manifests, execution manifests, summaries, metrics, robustness tables, and replication datasets
- `BUILD_INFO.json`
- `docs/local_release_verification.json`
- `MANIFEST.sha256`

## 5. Repository capability map

| Capability | Primary implementation |
|---|---|
| Simulation engine | `src/fleet_sim/model/engine.py`, `src/fleet_sim/experiments/simulator.py` |
| Agent interface and state | `src/fleet_sim/model/agent.py`, `src/fleet_sim/model/state.py`, `src/fleet_sim/model/task.py` |
| Event model | `src/fleet_sim/model/events.py` |
| Graph construction and segmentation | `src/fleet_sim/graphs/factory.py`, `src/fleet_sim/graphs/segmentation.py` |
| Queueing and control plane | `src/fleet_sim/control_plane/queueing.py`, `src/fleet_sim/control_plane/service_center.py` |
| Credentials and revocation-related models | `src/fleet_sim/control_plane/credentials.py`, `src/fleet_sim/credentials/models.py`, `src/fleet_sim/timing/credentials.py` |
| Compromise propagation | `src/fleet_sim/security/attack_operator.py`, `src/fleet_sim/security/directed_ngm.py`, `src/fleet_sim/security/epidemic.py` |
| Admission stability | `src/fleet_sim/analysis/admission_stability.py` |
| Phase-separated compromise estimation | `src/fleet_sim/analysis/compromise_hurdle.py` |
| Statistical experiments | `src/fleet_sim/experiments/stage1_research.py`, `stage2_research.py`, `stage2_cycle5.py`, `stage2_cycle6.py`, `stage2_cycle7.py` |
| Replay | `src/fleet_sim/model/replay.py` |
| Visualization | `src/fleet_sim/visualization/`, stored HTML consoles in `replay_bundles/` |
| Provenance and manifests | `src/fleet_sim/provenance/`, `manifests/`, frozen protocol documents |
| Automated tests | `tests/unit/`, `tests/statistical/`, `tests/integration/`, `tests/replay/` |

## 6. Environment used

The handoff verification used:

- Host: macOS 26.6.1 on arm64
- Clean Python virtual environment
- Python: 3.13.0
- Installed dependency sets: pinned runtime, development, and science dependencies
- Installed distribution: `fleet-assurance-sim` wheel version 0.1.0

The stored Stage 2 reference execution used Linux x86-64, Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0, pandas 2.2.3, NetworkX 3.6.1, and Matplotlib 3.10.8. Cross-environment byte equivalence is not claimed.

## 7. Automated test result

**Result:** PASS

- Tests passed: 51
- Tests failed: 0
- Duration: 26.35 seconds
- Scope: unit, statistical, replay, integration, and research-protocol checks included by the repository test suite

The reported handoff count of 51 tests is accurate for the immutable Stage 2 baseline.

## 8. Deterministic smoke and replay verification

Two independent smoke invocations produced the same recorded outputs:

| Field | Run 1 | Run 2 |
|---|---|---|
| Event count | 2,441 | 2,441 |
| Event-log digest | `6598fa0c5266c083c7e232fb221197d1a600af4851062ad953142fcc054d4881` | Same |
| Final-state hash | `750770a4fce83cf10984f3a75feba34cd1c618adddb4f68ab99fa4913149baa7` | Same |
| Replay-state hash | `750770a4fce83cf10984f3a75feba34cd1c618adddb4f68ab99fa4913149baa7` | Same |
| Replay verified | Yes | Yes |

This verifies deterministic execution and replay reconstruction for the smoke configuration in the handoff environment. It does not validate the simulator as a model of any deployed system.

## 9. Visual console verification

**Result:** PASS for launch and HTTP reachability.

- Root request returned HTTP 302 and redirected to `/app`.
- `/app` returned HTTP 200.
- Response body size was 3,390 bytes.

This confirms that the local console process launches and serves the application route. It is not a complete browser-level visual, accessibility, authentication, or adversarial security assessment. The console remains a local research interface without production identity or access-control assurances.

## 10. Stage 2 research claim verification

### 10.1 NH2-D, dynamic attack-reachability scalar

**Disposition:** Refuted within the current model for the tested formulation.

- Dynamic held-out final-size MAE: 0.0394607
- Best baseline MAE: 0.0384427
- Relative MAE improvement: -2.6479 percent
- Dynamic ROC AUC: 0.748691
- Best baseline ROC AUC: 0.992147
- AUC difference: -0.243455
- Dynamic Brier score: 0.016464
- Best baseline Brier score: 0.008736
- Positive robustness blocks: 0 of 5
- Dependency ablation degraded prediction: no

The negative result is consistent across the report, synthesis, evidence ledger, Cycle 5 summary, predictor metrics, robustness table, and execution manifest. Stage 3 must not silently retune or relabel this formulation as supported.

### 10.2 NH2-T, temporal propagation scalar

**Disposition:** Refuted within the current model for the training-selected infection-propagator formulation.

- Selected candidate held-out MAE: 0.0568567
- Static pre-response non-backtracking MAE: 0.0471747
- Relative MAE improvement: -20.5236 percent
- Bootstrap 95 percent interval for absolute MAE reduction: -0.01512 to -0.00462

An unselected temporal non-backtracking predictor achieved MAE 0.0453046, approximately 3.96 percent better than the static comparator. That result was exploratory, was not the training-selected candidate, and did not meet the fixed 5 percent threshold. The evidence refutes the selected NH2-T formulation, not every possible temporal model.

### 10.3 NH4-O, reflected admission-overload measure

**Disposition:** Strong provisional model-conditioned evidence, not support under the complete preregistered rule.

- Held-out scenarios: 112
- Majority-failure scenarios: 72
- Non-failure scenarios: 40
- `Omega_A` ROC AUC: 0.991667
- Comparator ROC AUC: 0.933333
- AUC improvement: 0.058333, below the required 0.08
- Brier-score improvement: 50.5618 percent
- Balanced accuracy at `Omega_A = 1`: 0.833333
- Transition-threshold coefficient of variation: 0.194867
- Complete robustness blocks passing: 3 of 5, below the required 4 of 5

The modeled resource work, capacities, service distributions, wait budgets, and failure definitions are notional. `Omega_A = 1` is an analytic queue-budget boundary in the implemented model, not a validated operational control threshold.

### 10.4 NH2-H, phase-separated compromise model

**Disposition:** Mixed positive model-conditioned evidence, not support under the complete preregistered rule.

- Pooled hurdle MAE: 0.0365971
- Pooled best-baseline MAE: 0.0450560
- Pooled improvement: 18.7742 percent
- Hierarchical-bootstrap 95 percent interval for fractional improvement: 8.8041 to 29.1917 percent
- Block improvements: 14.3774, 29.2761, and 12.0336 percent
- Blocks meeting at least 15 percent improvement: 1 of 3
- Blocks with outbreak-probability Brier noninferiority: 1 of 3

The supported interpretation is narrower than a general two-stage law: separating outbreak initiation from conditional severity improved pooled final-size prediction in this synthetic substrate, while initiation calibration and block-level transfer remained inadequate.

## 11. Isolated Cycle 7 regeneration

**Result:** Numerically reproduced with the same scientific decision, but not byte-identical across platforms.

- Replications regenerated: 34,560
- Frozen-input gate: passed
- Acceptance decisions: unchanged
- Maximum observed numeric delta against the release result: `2.2404702537670573e-09`
- Output byte hashes: different from the Linux reference release
- Initial headless execution: exited with code 134
- Successful remediation: set `MPLBACKEND=Agg` and rerun in the isolated working location

The magnitude of the numerical differences did not change any Stage 2 metric interpretation or acceptance decision. This is evidence of numerical equivalence at the observed tolerance, not bitwise reproducibility. Stage 3 must record comparison tolerances and environment versions and must not overwrite the Linux release outputs with locally regenerated artifacts.

## 12. Missing or broken dependencies

No required Python dependency remained missing after installation of the pinned runtime, development, and science dependency sets and the 0.1.0 wheel.

One portability defect was observed: the Cycle 7 regeneration aborted in the headless environment with exit code 134 until Matplotlib was forced to the noninteractive `Agg` backend. Required remediation is to set or validate `MPLBACKEND=Agg` in headless experiment and verification entry points.

## 13. Differences from the handoff claims

| Handoff claim | Verification result |
|---|---|
| Reported ZIP checksum | Verified exactly |
| File-level integrity manifests | Present; all 412 payload hashes verified in the archive |
| Complete Python source and Stage 0 through Stage 2 runners | Required modules and runners located |
| Fifty-one automated tests | Verified by clean execution: 51 passed |
| Deterministic replay | Verified in two smoke runs with matching event, final-state, and replay hashes |
| Interactive visual console | Launch and HTTP route verified; full browser rendering was not assessed |
| Docker, Conda, macOS, Linux, and Windows support | Definitions and bootstrap documentation are present; every platform was not independently executed |
| Installable wheel | Wheel 0.1.0 installed successfully |
| Stage 2 results regenerate identically | Scientific decisions and numerical values reproduced within `2.2404702537670573e-09`; byte hashes differed across environments |
| Frozen protocol provenance | Hash matching verified; independently verifiable external timestamps or signatures are not present for every cycle |

No required handoff artifact was missing. The word "complete" is supported by the presence of the declared repository components, but completeness against an external system specification cannot be proven from the package alone.

## 14. Research artifacts located

- Stage 0, Stage 1, and Stage 2 experiment implementations
- Frozen Cycle 5, Cycle 6, and Cycle 7 protocols
- Preregistration and execution manifests
- Replication-level and scenario-level CSV datasets
- Cycle summaries, predictor metrics, robustness tables, figures, and synthesis outputs
- Stage 2 research reports, decision record, decision tables, evidence ledger, and acceptance status
- Replay bundles and self-contained HTML evidence consoles
- Local visualization implementation
- Docker, Conda, shell, and PowerShell deployment assets
- Installable Python wheel
- Source-tree and package-level integrity manifests

## 15. Missing or incomplete research evidence

The following are not release-package omissions. They are unresolved evidence gaps that bound Stage 3 claims:

- No measured control-plane workload calibration for `Omega_A`
- No externally observed or independently implemented compromise trace set for NH2-H
- No operationally calibrated attack-path, detection, recovery, or containment data
- No independent simulator replication
- No full cross-platform numerical-equivalence specification or container digest pinning
- No independently verifiable external preregistration timestamp or artifact signature for every cycle
- Only three full structural blocks in Cycle 7
- No evidence supporting a secure 10,000-agent deployment decision
- No browser-state assertion suite for the interactive console

The evidence ledger is content-consistent but does not directly include artifact paths, dataset hashes, protocol hashes, execution-manifest references, or seed-set identifiers. Stage 3 should add those fields.

## 16. Claim-language corrections

Before external publication or reuse, correct the following language:

1. `paper/stage2_cycles4_7_research_report.md` states that compromise "behaves as a two-stage stochastic process" and that compromise "cannot be reduced to one graph radius." The evidence supports only that the tested phase-separated estimator improved pooled prediction while failing its complete rule, and that the tested scalar replacements were inadequate in the implemented model.
2. `paper/stage2_cycles5_to7_research_report.md` uses "provably unmanageable" and asserts unbounded scaling along selected complexity axes. Those statements are not established by the Stage 2 evidence chain and should be scoped to explicit mathematical assumptions or removed.
3. The phase-separated formula near line 179 of `paper/stage2_cycles5_to7_research_report.md` contains a malformed `theta_1` term and should be corrected in a new Stage 3 document revision without altering the immutable baseline.
4. NH2-T should be described as refutation of the training-selected infection-propagator formulation, not as refutation of all temporal predictors.
5. All external statements must retain the distinctions among analytic definition, numerical demonstration, model-conditioned support, refutation, provisional evidence, and operational validation.

## 17. Required remediation and Stage 3 controls

1. Keep `fleet-assurance-stage2-baseline` immutable and perform all development in `fleet-assurance-stage3-working`.
2. Use append-only, run-specific output directories. Do not overwrite canonical Stage 2 results, figures, or manifests.
3. Add `MPLBACKEND=Agg` handling to headless verification and experiment entry points.
4. Define cross-platform numerical-equivalence tolerances separately from byte-level release integrity.
5. Record the source archive checksum, baseline path, parent commit or tree hash, environment, protocol identifier, seed sets, and output hashes for every Stage 3 run.
6. Add independently verifiable timestamping or signing for preregistration and execution artifacts.
7. Expand the evidence ledger with direct artifact and manifest references.
8. Preserve NH2-D and the selected NH2-T formulation as negative results. Any new scalar hypothesis requires a scientifically distinct preregistration.
9. Move NH4-O to measured or independently generated resource calibration. Additional synthetic tuning alone is insufficient.
10. Evaluate NH2-H with a stronger initiation estimator, at least five independent structural blocks, held-out scale and topology transfer, and external or independently generated traces.
11. Correct claim-language defects in new Stage 3 documentation while preserving the Stage 2 release unchanged.

## 18. Go or no-go decision

**CONDITIONAL GO for Stage 3 research in the separate working copy.**

The software and evidence package are sufficiently intact and reproducible to support continued research. Stage 3 is not authorized to treat either surviving candidate as an operational control, claim a universal fleet assurance law, or issue deployment assurance. Progression beyond research experimentation requires external calibration, independent evaluation, stronger provenance controls, and implementation-specific operational test evidence.
