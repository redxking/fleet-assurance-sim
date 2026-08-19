# Fleet Assurance Simulation 0.2.0 Release Notes

## Release identity

- Release: `fleet-assurance-sim-local-release-v0.2.0-2026-08-19`
- Project version: `0.2.0`
- Evidence baseline: immutable Stage 2 records plus completed Stage 3 confirmation
- Stage 3 execution: `stage3-confirmatory-20260819-01`
- Stage 3 protocol hash: `b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851`
- Intended use: local execution, verification, immutable evidence review, replay, visualization, and continued research in a separate working copy

## Major additions since 0.1.0

- Stage 3A reflected multi-resource fleet-admission confirmation
- Stage 3B separate attack-trace generator, bounded observed view, directed dynamic message passing, and phase-separated initiation and severity prediction
- Explicit detection, quarantine, revocation, recovery, partition, topology, segmentation, and defense-pair experiment factors
- Authenticated preexecution manifest covering schema, protocol state, timestamp, environment, exact command contract, and 151 frozen files
- Fail-closed environment and command checks, safe execution identifiers, immutable result directories, per-scenario Stage 3B checkpoints, and resource ceilings
- Common-random-number pairing and cluster-aware hierarchical bootstrap
- Offline Stage 3 HTML and JSON evidence console with admission, compromise, lifecycle, DMP-state, and sampled-graph views
- Six publication figures with a source-bound SHA-256 manifest, alternative text, and machine-readable provenance
- Expanded unit, statistical, integration, protocol, launcher, and visualization coverage

## Verification status

The complete source suite passed 113 tests immediately before Stage 3 protocol freeze. The immutable confirmation then passed post-execution integrity checks for:

- All 151 frozen-input hashes
- Freeze-time and execution-time numerical environment equality
- Exact resolved command and 12/10/5000 execution contract
- Stage 3A and Stage 3B row and scenario cardinalities
- Seed derivation, pilot-domain separation, and defense-pair equality
- All 240 Stage 3B checkpoints and their exact union with aggregate raw evidence
- Strict finite JSON and Parquet numeric content, with only defined semantic nulls
- Trace identities, seed provenance, graph representation limits, and visualization-only scope
- All 341 pre-manifest artifact sizes and SHA-256 digests
- Wall-clock, memory, and output budgets
- Absence of execution-failure and failed-scenario artifacts

Observed confirmatory resource use was 352.970 seconds wall time, 350.418 seconds CPU, 1,092.563 MiB peak RSS, and 22.537 MiB output before final evidence serialization.

Targeted Ruff checks over the exact Stage 3 source, scripts, and tests passed. A subsequent repository-wide `ruff check src scripts tests` reported 139 pre-existing or legacy findings. This broader lint debt does not alter the frozen inputs, immutable execution, confirmatory metrics, acceptance criteria, or scientific dispositions.

## Confirmatory evidence

Authoritative execution:

```text
results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01/
```

Offline review artifacts:

```text
results/stage3/consoles/stage3-confirmatory-20260819-01.html
results/stage3/consoles/stage3-confirmatory-20260819-01.json
```

The final Pilot 05 record remains under `results/stage3/engineering-pilots/` and is excluded from scientific adjudication.

## Scientific disposition

Execution integrity passed. Hypothesis support did not.

- Stage 3A: `not_supported_under_preregistered_rule`. The candidate failed the calibration-slope interval and positive transfer under the 1.25 capacity shift.
- Stage 3B: `not_supported_under_preregistered_rule`. The candidate failed eight required final-size, outbreak-probability, block, calibration-shift, scale-transfer, and topology-transfer conjuncts.

The release preserves the prior Stage 2 dispositions:

- NH2-D remains refuted within the current model.
- NH2-T remains refuted within the current model.
- NH4-O retains strong provisional Stage 2 evidence but did not satisfy its complete rule.
- NH2-H retains pooled positive Stage 2 evidence but did not satisfy its complete rule.

All results are synthetic and model-conditioned. No external operational dataset was supplied, and no external validation was performed. This release does not establish implementation security, a secure fleet-size limit, or authority to deploy.

## Storage

The measured Stage 3 working copy was approximately 1.79 GiB before final packaging. The immutable confirmatory execution is approximately 22.8 MiB. Its self-contained HTML and JSON exports are approximately 331.3 MiB combined. Retaining multiple console exports can dominate disk usage.

The v0.2.0 wheel is built and isolated-target verified. `BUILD_INFO.json` records its exact path, 269060-byte size, SHA-256 digest, local build backend, no-network build condition, imports, metadata version, and Stage 3 console CLI check. The complete local ZIP is distributed with an adjacent `.zip.sha256` sidecar. The archive digest and byte count are externalized after materialization because an archive cannot contain its own final digest.

## Continued research

Do not rerun or replace the retained Stage 3 confirmation. Start future scientific work in a separate copy with a new protocol identifier, prospective criteria, new seed domains where required, a new execution identifier, and a newly authenticated manifest. Preserve both negative dispositions unchanged unless a scientifically distinct preregistered experiment produces contrary evidence.
