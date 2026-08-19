# Acceptance Status

## Current release boundary

Package version: 0.2.0  
Research evidence snapshot: Stage 0 through the immutable Stage 3 confirmation  
Confirmatory execution: `stage3-confirmatory-20260819-01`  
Protocol hash: `b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851`  
Date: 2026-08-19

**Software and evidence-integrity status:** PASS for the implemented execution paths. The complete prefreeze suite passed 113 tests, and the completed Stage 3 execution passed its frozen-input, environment, command, artifact-integrity, finite-data, checkpoint, seed, trace, and resource-budget checks.

**Stage 3 hypothesis-support status:** NOT PASS. Stage 3A and Stage 3B are both `not_supported_under_preregistered_rule`.

**Deployment-assurance status:** NOT ESTABLISHED.

The execution-integrity decision and the scientific decision are intentionally separate. A valid confirmatory execution can produce a negative scientific result. All Stage 3 outcomes are synthetic and model-conditioned. No external operational dataset was supplied, and no external validation was performed.

**Release-quality lint scope:** Targeted Ruff checks over the exact Stage 3 source, scripts, and tests passed. A post-confirmation repository-wide `ruff check src scripts tests` reported 139 pre-existing or legacy findings. Those findings are release-engineering debt and do not change any frozen input, confirmatory artifact, metric, acceptance criterion, or scientific disposition.

## Gate status

| Gate | Status | Evidence | Remaining work |
|---|---|---|---|
| A. Feasibility | Pass for implemented paths | Deterministic Stage 0 runs through bounded N=10,000; completed Stage 2 matrices; Stage 3 confirmation completed in 352.970 seconds with 1,092.563 MiB peak RSS and 22.537 MiB recorded pre-evidence output | Qualify additional adversary, consensus, supervisory, and long-horizon workloads |
| B. Verification | Pass for the frozen Stage 3 source | 113 tests passed before protocol freeze across unit, statistical, replay, integration, visualization, and protocol guards; targeted Ruff passed for the exact Stage 3 set | Triage the 139 repository-wide legacy Ruff findings; add cross-platform equivalence, fuzzing, and browser-state assertions |
| C. Reproducibility | Pass in the frozen environment | Authenticated manifest, 151 matching frozen files, exact command and environment checks, deterministic seed domains, immutable directories, and 341 verified execution artifacts | Add signed manifests and container image digests |
| D. Protocol integrity | Pass | Stage 2 negative results were retained; the Stage 3 protocol was frozen before confirmation; no held-out fitting or post-outcome threshold change is permitted | Subject the complete evidence package to independent technical review |
| E. Statistical validity | Pass for execution of the declared Stage 3 analysis; hypothesis support not achieved | Training, calibration, and held-out partitions; five blocks; common-random-number pairing; fixed 5,000-draw hierarchical bootstraps; prospectively frozen conjunctive criteria | Calibrate against external measurements and independently generated operational traces |
| F. Visualization integrity | Pass for the offline Stage 3 evidence console | Console content is derived from immutable artifacts, trace records are labeled visualization-only, graph sampling is disclosed, and console generation performs no source-run mutation | Add automated browser-state tests and smaller publication exports |
| G. Security-claim discipline | Pass | Negative findings remain negative; synthetic and model-conditioned scope is explicit; no secure-scale or deployment claim is issued | Add implementation-specific evidence before any deployment recommendation |
| H. Hypothesis support | Not pass | Stage 2 NH2-D and NH2-T remain refuted; Stage 2 NH4-O and NH2-H remained below their complete rules; Stage 3A and Stage 3B also failed their fixed conjunctive rules | Form new hypotheses only under a new preregistered protocol |
| I. Release quality | Pass for the completed immutable confirmation package | Frozen protocol and manifest, raw and derived Parquet, checkpoints, strict JSON evidence, traces, offline console, publication figures, updated release documentation, explicit negative dispositions, a verified v0.2.0 wheel, and an externally checksummed local archive are present | Preserve the archive and adjacent `.zip.sha256` sidecar together; maintain the curated public-repository boundary |

## Stage 3 confirmatory evidence

Authoritative execution directory:

```text
results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01/
```

Execution-integrity checks passed:

- 151 of 151 frozen inputs matched the authenticated preexecution manifest.
- The live numerical environment and resolved command matched the frozen contract.
- Stage 3A retained 25,200 raw rows over 2,100 scenarios and 21,600 held-out prediction rows.
- Stage 3B retained 2,400 raw rows over 240 specifications and 1,200 held-out prediction rows.
- All 240 Stage 3B checkpoints were present, with ten rows each, and their union matched the aggregate raw table.
- All 600 held-out defense-pair replication groups contained exactly the two declared defense cases with matched graph, process, observation, base-replication, and derived-replication seeds.
- All 341 pre-manifest artifact entries matched their recorded sizes and SHA-256 digests.
- All 35 JSON and 307 Parquet artifacts passed finite-value and semantic-null checks.
- No execution-failure or failed-scenario artifact exists.

The engineering pilots remain excluded from scientific adjudication. Pilot 05 established only that the final code path, resource controls, checkpointing, provenance, and console ingestion operated as intended before freeze.

## Stage 3 scientific dispositions

### Stage 3A: fleet-admission stability

Disposition: `not_supported_under_preregistered_rule`.

The candidate passed most predictive and transfer criteria, including pooled Brier improvement, AUC, bootstrap improvement, block consistency, architecture transfer, workload transfer, and the declared N=10,000 checks. It failed two required conjuncts:

- Calibration slope was 0.453931, outside the fixed interval [0.8, 1.2].
- The 1.25 capacity-shift improvement was -0.003672, below the required positive value.

This result does not erase the Stage 2 provisional signal for `Omega_A`. It establishes that the Stage 3A candidate did not satisfy the stronger preregistered confirmation rule.

### Stage 3B: phase-separated compromise prediction

Disposition: `not_supported_under_preregistered_rule`.

The generator-predictor structural review, held-out class support, defense pairing, segmentation calibration shift, and several transfer components passed. Eight required conjuncts failed, including final-size and outbreak-Brier bootstrap lower bounds, minimum pooled improvements, block consistency for final size, detection-response calibration stability, N=10,000 transfer, and Barabasi-Albert transfer.

The result does not revive the refuted Stage 2 NH2-D or NH2-T scalar formulations. It also does not establish the phase-separated model as a transferable operational predictor.

## Preserved Stage 2 dispositions

- NH2-D: refuted within the current model.
- NH2-T selected temporal propagator: refuted within the current model.
- NH4-O: strong provisional Stage 2 signal, but not supported under the complete preregistered rule.
- NH2-H: pooled positive Stage 2 evidence, but not supported under the complete preregistered rule.

## Claim restrictions

No result supports a statement that 10,000 agents can be deployed securely. No result establishes that a real compromise follows the synthetic attack substrate. No result validates `Omega_A=1` as an operational threshold. No result establishes a universal fleet assurance law, implementation security, patentability, novelty priority, or authority to deploy.
