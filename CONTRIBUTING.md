# Contributing

Fleet Assurance Simulation is open for technical review, defect reports, reproducibility work, model extensions, and scientifically distinct follow-on experiments.

## Start with the evidence boundary

The current results are synthetic and model-conditioned. They do not establish implementation security, operational assurance, a secure fleet-size limit, or authority to deploy. Contributions must preserve the distinction among verified artifacts, model results, assumptions, proposals, and external evidence.

The retained Stage 3 confirmation is immutable. Do not alter its protocol, manifest, evidence, execution inventory, or result files in place. A revised model, threshold, comparator, outcome definition, observation process, or acceptance rule requires a new protocol identifier, new seed domain where applicable, new preexecution manifest, and new execution directory.

## Useful contribution areas

- Independent reproduction on additional supported platforms
- External or high-fidelity resource measurements for Stage 3A calibration
- Review of successor-study fit thresholds, target-domain coverage, and uncertainty methods
- Evidence-backed ten-resource adapter policies and faithful simulator semantics
- External or separately implemented attack traces for Stage 3B validation
- Statistical and numerical review of the acceptance methods
- Additional matched-capacity comparators and uncertainty methods
- Security, correctness, performance, accessibility, and documentation defects
- Compact evidence-distribution and browser-validation improvements

## Development workflow

1. Fork the repository and create a focused branch.
2. Install the development dependencies described in `QUICKSTART.md`.
3. Add or update tests with the change.
4. Run the relevant focused checks and the complete test suite.
5. State the evidence class, assumptions, limitations, and any non-inferences in the pull request.
6. Keep generated caches, local environments, engineering-pilot outputs, large console exports, and verification scratch data out of commits.

When a package schema, verifier, lifecycle state, authorization flag, diagnostic, uncertainty interval, or simulator limitation changes, update the corresponding command-line output, status UI, documentation, and tests in the same change. A UI must display failed, blocked, and not-evaluable states; it must not infer readiness from artifact presence.

The successor empirical workflow is intentionally split into evidence intake, calibration fitting, resource adaptation, future registration, future held-out binding, and future one-shot evaluation. Do not bypass those gates by connecting an engineering-only adapter to the frozen Stage 3 runner. A prospective study requires a new protocol and manifest chain.

Do not submit proprietary, classified, export-controlled, personal, operationally sensitive, or third-party restricted data. Synthetic examples must be clearly labeled synthetic. External measurements must include provenance, collection authority, licensing, and an explicit statement of what they do and do not establish.

Generated successor packages belong under `local_runs/` and are not publication-ready by default. A future GitHub Pages build must use only explicitly approved public artifacts, pass accessibility and clean-checkout checks, link claims to immutable evidence, and receive a separate release authorization.

## Pull-request expectations

A reviewable change should explain its purpose, affected interfaces, scientific or operational impact, failure modes, verification performed, and any remaining uncertainty. Changes that affect frozen scientific logic must be proposed as a new study rather than presented as a correction to the completed confirmation.

By contributing, you agree that your contribution is licensed under the repository's Apache License 2.0.
