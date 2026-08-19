# Empirical assurance evidence intake

## Purpose

This successor-study component turns a candidate assurance-resource measurement campaign into a portable, checksum-bound review package. It is the gate in front of future resource calibration. It does not calibrate the simulator, run a scientific experiment, alter the completed Stage 3 evidence, or establish external validation.

The intake asks a narrow question: is this measurement campaign sufficiently well described and internally consistent to enter engineering review? A later preregistered protocol must still define fit-quality thresholds, operational outcomes, comparator rules, transfer tests, and scientific acceptance criteria.

## Evidence boundary

The campaign manifest records:

- a portable campaign, site, and system alias;
- collection start and end times;
- collection authority and data-rights references;
- allowed research uses;
- instrumentation, clock, sampling, window, missingness, censoring, and transformation semantics;
- an exact unit contract for every retained measurement.

The current implementation accepts only `public` and `synthetic` classifications. It intentionally rejects internal and controlled data because this package writer does not implement an approved secure-storage, encryption, retention, or export-control policy.

Nonsynthetic rows require affirmative collection authorization, confirmed data rights, a nonsynthetic classification, and an instrumentation quality review. Those fields are supplied by the campaign owner and remain unreviewed assertions at intake. For that reason, measured and replayed packages remain labeled `*_input_unreviewed`, `external_validation` remains `false`, and `scientific_use_authorized` remains `false`.

## Partition and resource rules

Every campaign must contain prospective `calibration` and `heldout` partitions. The word `heldout` is the successor intake spelling; any later adapter to a Stage 3A-style API must translate it explicitly to `held_out`.

Each `time_block_id` is one contemporaneous ten-resource observation vector:

- exactly one observation for each implemented assurance resource;
- one aligned timestamp and one window duration;
- one partition only;
- stable resource identifiers across all blocks and both partitions.

Observation windows are treated as half-open intervals. All calibration windows must finish no later than the first held-out window begins. For `fixed_nonoverlapping` campaigns, a window cannot exceed the declared sampling interval and windows for the same resource cannot overlap.

Rows with censoring or nonzero missingness can be retained for review, but the quality report identifies the required policy work. Every package remains blocked from scientific fitting until a successor protocol and fit review authorize use.

## Package workflow

Start from:

- `examples/empirical_assurance_campaign_template.json`
- `examples/empirical_assurance_measurements_template.csv`

Then create a new package:

```bash
.venv-stage3-verify/bin/python scripts/package_assurance_campaign.py \
  path/to/measurements.csv \
  path/to/campaign.json \
  local_runs/empirical-campaign-001
```

The destination must not exist. The command writes exactly seven regular local files:

| Artifact | Purpose |
|---|---|
| `campaign_manifest.json` | Canonical authority, instrumentation, units, and campaign metadata |
| `campaign_schema.json` | Trusted closed schema used for campaign metadata validation |
| `calibration_measurements.parquet` | Canonical calibration partition |
| `heldout_measurements.parquet` | Canonical prospective held-out partition |
| `measurement_schema.json` | Trusted closed schema used for measurement validation |
| `quality_report.json` | Counts, coverage, missingness, censoring, and fit-blocking status |
| `evidence_manifest.json` | Source, schema, implementation, runtime, transformation, partition, artifact, and self-integrity hashes |

The command prints the SHA-256 digest of `evidence_manifest.json`. Record that digest in an external, access-controlled study ledger if later verification must be bound to a value held outside the mutable package. The self-integrity hash inside the package detects accidental inconsistency; it is not a signature and does not authenticate origin.

The package does not retain the raw source file. It records only the source basename and SHA-256 digest, while the normalized partition artifacts carry the retained data. Raw measurements must remain under their owner-approved custody and retention controls.

## What comes next

The next implementation slice is deliberately separate:

1. Define minimum sample size, rank, conditioning, predictor-range, uncertainty, missingness, and censoring gates per resource.
2. Define an explicit policy for mapping fitted fields into all `AssuranceResourceSpec` semantics, including arrival process, service-time distribution, overload behavior, shedding, and recovery.
3. Bind dataset, package, policy, fitted bundle, and generated resource specifications into a new engineering manifest.
4. Add operational outcome labels and a new preregistered prospective evaluation.
5. Keep the completed Stage 3 hashes, execution, evidence, and negative dispositions unchanged.

No fleet-size, deployment, or security-assurance recommendation should be derived from an intake package alone.
