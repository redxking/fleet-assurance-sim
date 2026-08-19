# Contributing

Fleet Assurance Simulation is open for technical review, defect reports, reproducibility work, model extensions, and scientifically distinct follow-on experiments.

## Start with the evidence boundary

The current results are synthetic and model-conditioned. They do not establish implementation security, operational assurance, a secure fleet-size limit, or authority to deploy. Contributions must preserve the distinction among verified artifacts, model results, assumptions, proposals, and external evidence.

The retained Stage 3 confirmation is immutable. Do not alter its protocol, manifest, evidence, execution inventory, or result files in place. A revised model, threshold, comparator, outcome definition, observation process, or acceptance rule requires a new protocol identifier, new seed domain where applicable, new preexecution manifest, and new execution directory.

## Useful contribution areas

- Independent reproduction on additional supported platforms
- External or high-fidelity resource measurements for Stage 3A calibration
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

Do not submit proprietary, classified, export-controlled, personal, operationally sensitive, or third-party restricted data. Synthetic examples must be clearly labeled synthetic. External measurements must include provenance, collection authority, licensing, and an explicit statement of what they do and do not establish.

## Pull-request expectations

A reviewable change should explain its purpose, affected interfaces, scientific or operational impact, failure modes, verification performed, and any remaining uncertainty. Changes that affect frozen scientific logic must be proposed as a new study rather than presented as a correction to the completed confirmation.

By contributing, you agree that your contribution is licensed under the repository's Apache License 2.0.
