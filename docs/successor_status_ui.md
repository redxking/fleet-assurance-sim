# Successor-study status UI

The successor-study status UI is a read-only, public-safe view of the empirical
evidence pipeline. It is separate from the frozen Stage 3 console and does not
modify Stage 3 code, results, figures, or manifests.

The page answers one practical question: how far has a verifier-backed evidence
chain progressed, and what still prevents a prospective transfer claim?

## Nine distinct lifecycle states

The version 3 view keeps local prediction commitment, external timing,
outcome-release custody, scoring, and execution authority separate:

1. **Evidence intake**: the source campaign package, schemas, partitions, and
   integrity commitments were reverified.
2. **Fit quality**: the calibration partition was refit and classified as
   `passed`, `failed`, or `not_evaluable` under the retained policy.
3. **Resource adapter**: accepted estimates and explicit semantic policy were
   recomputed into the ten simulator resource specifications.
4. **Frozen study plan**: a registration package binds the source evidence,
   fit, adapter, transfer contract, planned cells, per-block predictor design,
   and implementation commitment before the distinct future campaign begins.
5. **Target-free local commitment**: a prediction-lock package records
   deterministic prediction rows and paired parameter draws generated from the
   frozen plan and bound calibration chain without supplying the future
   evaluation campaign.
6. **Evaluation inputs**: a later manifest binds the realized future campaign
   to the frozen plan and verifies exact campaign, collection-window, cell,
   predictor-design, time-block, ten-resource, and prediction-lock
   reconciliation.
7. **Outcome custody**: remains `pending` after the two required packages
   verify. No independent outcome-release custody package is connected.
8. **One-shot scoring**: remains `not_implemented`. No separately reviewed
   scorer or immutable result package is connected.
9. **Evaluation execution**: remains `not_authorized`. No separate evaluation
   authorization is connected and no prospective result has been executed.

Registration, prediction-lock, evaluation-input, and custody states use
`pending`, `blocked`, or `verified`. Scoring uses `not_implemented`, and only
execution uses `not_authorized`. A verified package proves that the package and
its digest chain were recomputed; it does not authorize collection, outcome
access, evaluation, scientific use, or operational use.

The frozen transfer contract contains the arrival-rate prediction formula and
scoring criteria. Prediction-row construction is implemented only as a
target-free local commitment. The one-shot scorer and evaluation runner are not
implemented or authorized by this view.

The source campaign's retained historical held-out partition is not prospective
evidence. Its integrity is verified, but its values are not used for fitting or
adaptation. The prediction-lock builder does not receive the distinct future
evaluation campaign. The declared local lock timestamp is ordered after
registration and before the planned collection window. That establishes only
internal chronology; it does not establish when the prediction rows or package
were actually created, published, or externally received. No independent
timestamp or custodian receipt has been verified, so
`prediction_rows_preoutcome_locked` remains false and a scientific pre-outcome
lock is not established. The later evaluation campaign package contains
`arrival_count` target values. The UI does not describe those targets as still
locked or infer that people and outside systems lacked access.

## What the page shows

The fit section shows every calibration-wide gate with its state, aggregate
observed value, comparison operator, and policy threshold. It also shows
per-resource aggregate diagnostics, uncertainty intervals, and blocker codes.
The adapter section shows the selected arrival, service, overload, capacity,
wait, and parameter-class semantics together with the verified simulator
limitations.

When a registration package is supplied, the page shows only:

- registration mode;
- planned cell and time-block counts;
- chronology, upstream-chain, criteria-freeze, implementation-freeze, and
  authority-boundary flags; and
- registration, study-plan, transfer-contract, and implementation digests.

When a prediction-lock package is supplied, the page shows only:

- prediction-row, planned-cell, planned-time-block, resource, and paired-draw
  counts;
- upstream-chain, predictor-design, formula-freeze, target-exclusion, local
  chronology, workflow-commitment, and authority-boundary flags; and
- prediction-lock, prediction-row-content, parameter-draw-content, and
  registration-manifest digests.

`future_evaluation_campaign_not_supplied=true` and
`prediction_rows_target_free=true` describe the code-level input and artifact
boundaries. `local_lock_chronology_consistent=true` describes only the declared
timestamps' internal ordering. None of these fields establishes actual
prediction or package creation time, publication time, external receipt, or
human and outside-system non-access.

When an evaluation-input package is supplied, the page shows only:

- realized cell and time-block counts;
- campaign-identity, collection-window, predictor-design, exact-plan, and
  chronology flags;
- prediction-lock binding, external pre-outcome timing, outcome-custody, and
  execution-readiness flags;
- target-free prediction-row and workflow-commitment flags; and
- evaluation-input, prediction-lock, evaluation-campaign, held-out-content,
  and registration commitments.

The current executable transfer target is resource arrival rate. Operational
failure transfer remains outside this chain until a separately adjudicated,
authorized outcome package and custody protocol exist. Calibration uncertainty
describes mean-parameter uncertainty; it is not a future-observation prediction
interval.

## Public disclosure boundary

The generated projection is deliberately smaller than every source package. It
may contain controlled semantic labels, aggregate counts and diagnostics,
cryptographic commitments, and Boolean gate results.

It excludes:

- raw or row-level measurements;
- campaign, dataset, fit, adapter, study, plan, contract, registration,
  evaluation-input, cell, time-block, site, system, and measurement-resource
  identifiers;
- planned, registration, or collection timestamps;
- authority, data-rights, provenance, and policy references;
- planned or realized cell and time-block lists;
- prediction rows, parameter draws, predicted or comparator values, seeds,
  bootstrap indices, residuals, scores, and results;
- prediction, receipt, custody, signer, and outcome-release metadata; and
- local package or source paths, including POSIX, drive-letter, and UNC paths.

The builder rejects a final projection containing a forbidden field, embedded
local path, timestamp, nonfinite number, or path object. Digests demonstrate
internal content binding only. They do not authenticate origin, attest when a
file existed, establish external validation, or grant authority.

## Build the offline page

The source campaign digest is always required. Every optional layer is a closed
set and requires its externally recorded digest. Later layers require every
earlier verified layer.

Build intake only:

```bash
python scripts/build_successor_status.py \
  /path/to/source-campaign-package \
  build/successor-status \
  --expected-campaign-evidence-manifest-sha256 <source-campaign-sha256>
```

Add the verified fit and adapter:

```bash
python scripts/build_successor_status.py \
  /path/to/source-campaign-package \
  build/successor-status \
  --expected-campaign-evidence-manifest-sha256 <source-campaign-sha256> \
  --fit-package /path/to/calibration-fit-package \
  --expected-fit-evidence-manifest-sha256 <fit-sha256> \
  --adapter-package /path/to/adapter-package \
  --expected-adapter-policy-sha256 <adapter-policy-sha256> \
  --expected-adapter-manifest-sha256 <adapter-manifest-sha256>
```

Add the frozen study plan:

```bash
python scripts/build_successor_status.py \
  /path/to/source-campaign-package \
  build/successor-status \
  --expected-campaign-evidence-manifest-sha256 <source-campaign-sha256> \
  --fit-package /path/to/calibration-fit-package \
  --expected-fit-evidence-manifest-sha256 <fit-sha256> \
  --adapter-package /path/to/adapter-package \
  --expected-adapter-policy-sha256 <adapter-policy-sha256> \
  --expected-adapter-manifest-sha256 <adapter-manifest-sha256> \
  --registration-package /path/to/registration-package \
  --expected-registration-manifest-sha256 <registration-sha256>
```

Add the target-free prediction-lock package without supplying the future
evaluation campaign:

```bash
python scripts/build_successor_status.py \
  /path/to/source-campaign-package \
  build/successor-status \
  --expected-campaign-evidence-manifest-sha256 <source-campaign-sha256> \
  --fit-package /path/to/calibration-fit-package \
  --expected-fit-evidence-manifest-sha256 <fit-sha256> \
  --adapter-package /path/to/adapter-package \
  --expected-adapter-policy-sha256 <adapter-policy-sha256> \
  --expected-adapter-manifest-sha256 <adapter-manifest-sha256> \
  --registration-package /path/to/registration-package \
  --expected-registration-manifest-sha256 <registration-sha256> \
  --prediction-lock-package /path/to/prediction-lock-package \
  --expected-prediction-lock-manifest-sha256 <prediction-lock-sha256>
```

Add realized evaluation inputs only after the registration and prediction lock
are verified:

```bash
python scripts/build_successor_status.py \
  /path/to/source-campaign-package \
  build/successor-status \
  --expected-campaign-evidence-manifest-sha256 <source-campaign-sha256> \
  --fit-package /path/to/calibration-fit-package \
  --expected-fit-evidence-manifest-sha256 <fit-sha256> \
  --adapter-package /path/to/adapter-package \
  --expected-adapter-policy-sha256 <adapter-policy-sha256> \
  --expected-adapter-manifest-sha256 <adapter-manifest-sha256> \
  --registration-package /path/to/registration-package \
  --expected-registration-manifest-sha256 <registration-sha256> \
  --prediction-lock-package /path/to/prediction-lock-package \
  --expected-prediction-lock-manifest-sha256 <prediction-lock-sha256> \
  --evaluation-campaign-package /path/to/evaluation-campaign-package \
  --expected-evaluation-campaign-evidence-manifest-sha256 <evaluation-campaign-sha256> \
  --evaluation-inputs-package /path/to/evaluation-inputs-package \
  --expected-evaluation-inputs-manifest-sha256 <evaluation-inputs-sha256>
```

The destination receives exactly two regular files:

- `index.html`, a responsive, accessible, self-contained presentation; and
- `successor-status.json`, the same strict projection embedded in the page.

Neither asset loads fonts, scripts, styles, telemetry, or data from a network.
The content-security policy disables all network connections. The destination
must be absent, empty, or contain exactly the two owned regular files. Replacing
a complete pair requires `--overwrite`. Partial pairs, extra entries,
directories, symlinks, and other special files are rejected even with
`--overwrite`. Both files are completed in a private sibling staging directory
before commit; a staging or commit failure preserves an existing pair. Output
cannot be written inside any immutable evidence package used by the build.

## Accessibility and responsive behavior

The page uses semantic landmarks, ordered lifecycle structure, text labels in
addition to color, visible focus indicators, native keyboard controls, minimum
44-pixel filter targets, accessible interval descriptions, and a labeled
scrollable resource table. The lifecycle uses three columns on wide screens,
two on tablets, and one on narrow screens. The frozen-plan and prediction-lock
panels sit side by side while evaluation inputs span the wide layout; all three
collapse to one column without horizontal page overflow. Reduced-motion and
print preferences are respected.

Automated checks do not replace manual VoiceOver or NVDA testing. Before public
release, verify keyboard-only operation, screen-reader announcements, contrast,
200% zoom, and narrow mobile widths on the rendered artifact.

## UI maintenance rule

Update this view whenever a verified package contract changes. Add or remove a
lifecycle state, flag, diagnostic, interval, or semantic limitation only when a
live verifier exposes corresponding evidence. Do not infer readiness from file
presence, turn a digest match into external validation, or convert a verified
registration into authorization.

The frozen Stage 3 console remains unchanged.

## Future GitHub Pages release

The two-file directory is compatible with static hosting and can later become
the input to a GitHub Pages release workflow. Publication remains a separate
decision after the successor protocol, public-data review, accessibility checks,
release controls, and product labeling are stable. This builder does not change
repository visibility, create a Pages site, or publish anything.
