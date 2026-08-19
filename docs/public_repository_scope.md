# Public Repository Scope

This repository is the public collaboration surface for Fleet Assurance Simulation 0.2.0. The publication boundary is deliberately narrower than the complete local release workspace.

## Included in Git history

- Python source, command-line entry points, schemas, configurations, and tests
- Stage 0 through Stage 3 protocols, architecture records, reports, decision tables, and acceptance records
- Publication figures with SHA-256 manifests, source hashes, alternative text, and provenance
- Compact Stage 2 and Stage 3 synthesis artifacts
- The immutable Stage 3 synthetic confirmatory execution, including its evidence, execution manifest, held-out predictions, and checkpoints required for reproducibility
- Small demonstration replay bundles and documentation assets that remain below GitHub's per-file limit

## Excluded from Git history

- Virtual environments, caches, build directories, package metadata, and local logs
- Engineering-pilot result directories, which are excluded from scientific adjudication
- Oversized offline HTML and JSON console exports, which can be regenerated from retained evidence
- Local verification scratch runs and archived working-copy repair material
- The complete local release ZIP and checksum sidecar

The exclusions reduce accidental publication of local residue and keep the collaboration history usable. They do not change the immutable confirmatory metrics, criteria, dispositions, or evidence scope.

## Evidence and security boundary

All retained Stage 3 evidence is synthetic and model-conditioned. No external operational dataset was supplied, and no external validation was performed. The repository does not establish implementation security, deployment assurance, a universal fleet-assurance law, or a secure fleet-size recommendation.

Do not add proprietary, classified, export-controlled, personal, operationally sensitive, or third-party restricted data. Report suspected vulnerabilities through the private process in `SECURITY.md`.
