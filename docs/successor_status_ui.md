# Successor-study status UI

The successor-study status UI is a read-only, public-safe view of the empirical
evidence pipeline. It is separate from the frozen Stage 3 console and does not
modify Stage 3 code, results, figures, or manifests.

The page answers one practical question: how far has a verifier-backed evidence
chain progressed, and what still prevents a prospective transfer claim?

## Six distinct lifecycle gates

The version 2 view keeps planning, realized evidence, and execution authority
separate:

1. **Evidence intake**: the source campaign package, schemas, partitions, and
   integrity commitments were reverified.
2. **Fit quality**: the calibration partition was refit and classified as
   `passed`, `failed`, or `not_evaluable` under the retained policy.
3. **Resource adapter**: accepted estimates and explicit semantic policy were
   recomputed into the ten simulator resource specifications.
4. **Frozen study plan**: a registration package binds the source evidence,
   fit, adapter, transfer contract, planned cells, per-block predictor design,
   and implementation commitment before the distinct future campaign begins.
5. **Evaluation inputs**: a second manifest binds the realized future campaign
   to the frozen plan and verifies exact campaign, collection-window, cell,
   predictor-design, time-block, and ten-resource reconciliation.
6. **Execution**: remains `not_authorized`. No evaluation authorization,
   valid pre-target prediction commitment, outcome-custody proof, or result
   artifact is implemented by this view.

Registration and evaluation-input states use `pending`, `blocked`, or
`verified`. Only the execution card uses `not_authorized`. A verified
registration proves that the package and its digest chain were recomputed; it
does not authorize collection, outcome access, evaluation, scientific use, or
operational use. A verified evaluation-input package still leaves execution
locked.

The frozen transfer contract contains the implemented arrival-rate prediction
formula and scoring criteria. That is a semantic and integrity commitment, not
an implemented runner. Executable prediction-row construction and scoring are
not implemented or authorized in this slice.

The source campaign's retained historical held-out partition is not prospective
evidence. Its integrity is verified, but its values are not used for fitting or
adaptation. The evaluation-input stage refers to a distinct future campaign
that begins after registration and matches the frozen plan. That verified
campaign package already contains the `arrival_count` target values. In the
current contract, the prediction rows were not committed before target access
and outcome-release custody is unverified. The UI reports those negative gates
directly; it does not describe the targets as still locked.

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

When an evaluation-input package is supplied, the page shows only:

- realized cell and time-block counts;
- campaign-identity, collection-window, predictor-design, exact-plan, and
  chronology flags;
- pre-target prediction-commitment, outcome-custody, and execution-readiness
  flags; and
- evaluation-input, evaluation-campaign, held-out-content, and registration
  commitments.

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
- planned or realized cell and time-block lists; and
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

Add realized evaluation inputs only after the registration is verified:

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
scrollable resource table. The layout collapses from six to three to one
lifecycle columns, and from two protocol panels to one, without horizontal page
overflow. Reduced-motion and print preferences are respected.

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
