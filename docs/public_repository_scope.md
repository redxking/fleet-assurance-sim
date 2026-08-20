# Public Repository Scope

This repository is the public collaboration surface for Fleet Assurance Simulation 0.2.0. The publication boundary is deliberately narrower than the complete local release workspace.

## Included in Git history

- Python source, command-line entry points, schemas, configurations, and tests
- Stage 0 through Stage 3 protocols, architecture records, reports, decision tables, and acceptance records
- Publication figures with SHA-256 manifests, source hashes, alternative text, and provenance
- Compact Stage 2 and Stage 3 synthesis artifacts
- The immutable Stage 3 synthetic confirmatory execution, including its evidence, execution manifest, held-out predictions, and checkpoints required for reproducibility
- Small demonstration replay bundles and documentation assets that remain below GitHub's per-file limit
- Successor-study intake, calibration-gate, adapter source, closed schemas, synthetic examples, and tests

## Excluded from Git history

- Virtual environments, caches, build directories, package metadata, and local logs
- Engineering-pilot result directories, which are excluded from scientific adjudication
- Oversized offline HTML and JSON console exports, which can be regenerated from retained evidence
- Local verification scratch runs and archived working-copy repair material
- The complete local release ZIP and checksum sidecar
- Local measurement campaigns and generated intake, fit, adapter, or successor-evaluation packages unless a separate public-scope review explicitly approves a sanitized artifact

The exclusions reduce accidental publication of local residue and keep the collaboration history usable. They do not change the immutable confirmatory metrics, criteria, dispositions, or evidence scope.

## Evidence and security boundary

All retained Stage 3 evidence is synthetic and model-conditioned. No external operational dataset was supplied, and no external validation was performed. The repository does not establish implementation security, deployment assurance, a universal fleet-assurance law, or a secure fleet-size recommendation.

Do not add proprietary, classified, export-controlled, personal, operationally sensitive, or third-party restricted data. Report suspected vulnerabilities through the private process in `SECURITY.md`.

The successor workflow accepts public or synthetic inputs only. Its generated packages stay under `local_runs/`, which Git ignores. A hash proves integrity, not publication approval, provenance authority, or external validation.

## Future public interface

A GitHub Pages interface is a later product milestone, after the successor workflow and evidence contracts stabilize. Publication requires a clean-checkout build, accessibility and responsive-layout checks, an offline/no-secret review, verified links from every displayed claim to immutable public evidence, and explicit release authorization. Negative and not-evaluable results must remain visible; the site must not imply operational approval, external validation, or deployment readiness.
