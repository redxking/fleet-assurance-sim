# Successor-study status UI

The successor-study status UI is a read-only, public-safe view of the empirical
evidence pipeline. It is separate from the frozen Stage 3 console and does not
modify Stage 3 code, results, figures, or manifests.

The page answers one practical question: how far has a verified evidence chain
progressed, and what still prevents a prospective transfer claim?

## What the page shows

The lifecycle view covers six gates:

1. **Evidence intake:** campaign artifacts, schemas, partitions, and integrity
   commitments were reverified.
2. **Fit quality:** the calibration partition was refit and classified as
   `passed`, `failed`, or `not_evaluable` under the retained policy.
3. **Resource adapter:** accepted estimates and explicit semantic policy were
   recomputed into ten simulator resource specifications.
4. **Frozen registration:** intentionally shown as `not_authorized` until a
   successor registration package and verifier exist.
5. **Held-out binding:** intentionally shown as `not_authorized` until held-out
   evidence is reconciled against the frozen registration.
6. **Prospective evaluation:** intentionally shown as `not_authorized`; the UI
   cannot run or authorize an evaluation.

The fit section first shows every calibration-wide gate with its state, observed
value, comparison operator, and policy threshold. This includes
`joint_target_domain_hull_distance`: the maximum positive signed convex-hull
half-space violation across the four corners of the dimensionless, target-scaled
fleet-size/admission-rate plane. A zero result means all four corners are inside
or on the observed calibration convex hull; a positive result identifies joint-
domain extrapolation. If the joint design is not two-dimensional, the value is
`not_evaluable`. Separate one-dimensional range checks do not substitute for
this joint-coverage gate.

For each available resource fit, the page then shows the disposition and blocker
list; observation and time-block counts; scaled design rank and condition
number; normalized RMSE; absolute weighted relative bias; weighted R²;
bootstrap success fraction; and retained lower/point/upper intervals. These
diagnostics use a compact semantic description list within each expandable
resource card. If an adapter package is available, the page also shows arrival,
service, overload, capacity, wait, and parameter-class semantics together with
limitations supplied by the verified adapter:

- `service_time_mean_ms` is retained in each specification but is not consumed
  by the current aggregate simulator;
- Poisson completion-count policy maps to the legacy `exponential` service-time
  enum;
- empirical arrival replay is not implemented and is rejected;
- empirical service-time replay is not implemented and is rejected;
- legacy per-resource Sybil, restart, and renewal workload multipliers are not
  fit or bound by the adapter policy;
- legacy closed-loop admission thresholds and the deferred-work retry fraction
  are not fit or bound by the adapter policy; and
- generated specifications are engineering-simulation inputs only.

The source-package verifier checks both retained partitions for integrity before
the calibration view is projected. The fit and adapter status therefore report
that held-out integrity was verified while also reporting that held-out values
were not used for fitting or adaptation.

A green fit or adapter state is engineering evidence only. It does not establish
external validity, scientific authorization, operational readiness, or a
successful prospective transfer.

## Public disclosure boundary

The generated payload is deliberately smaller than the source evidence. It may
contain:

- aggregate partition row and time-block counts;
- cryptographic commitments and opaque evidence identifiers;
- fit dispositions, aggregate diagnostics, and uncertainty intervals; and
- explicit adapter semantics and simulator limitations.

It excludes:

- raw measurement rows;
- campaign, site, system, and measurement resource identifiers;
- collection timestamps and environment descriptions;
- authority and data-rights references;
- human-supplied fit and adapter policy identifiers;
- measurement provenance strings; and
- local package or source paths, including `/private/tmp`, `/tmp`, `/var`,
  Windows drive-letter paths, and UNC shares.

The builder retains the policy digests needed to demonstrate evidence binding,
but not the human-supplied policy identifiers. It rejects unbound evidence and
checks the final projection for forbidden local-path and disclosure fields
before writing it.

## Build the offline page

The campaign evidence-manifest digest is always required. Optional fit and
adapter inputs are closed sets: a fit package requires its externally recorded
manifest digest, and an adapter package requires the verified source fit plus
the adapter policy and manifest digests.

```bash
python scripts/build_successor_status.py \
  /path/to/campaign-package \
  build/successor-status \
  --expected-campaign-evidence-manifest-sha256 <campaign-sha256>
```

Add a verified fit:

```bash
python scripts/build_successor_status.py \
  /path/to/campaign-package \
  build/successor-status \
  --expected-campaign-evidence-manifest-sha256 <campaign-sha256> \
  --fit-package /path/to/calibration-fit-package \
  --expected-fit-evidence-manifest-sha256 <fit-sha256>
```

Add a verified adapter after the fit gate has accepted it:

```bash
python scripts/build_successor_status.py \
  /path/to/campaign-package \
  build/successor-status \
  --expected-campaign-evidence-manifest-sha256 <campaign-sha256> \
  --fit-package /path/to/calibration-fit-package \
  --expected-fit-evidence-manifest-sha256 <fit-sha256> \
  --adapter-package /path/to/adapter-package \
  --expected-adapter-policy-sha256 <adapter-policy-sha256> \
  --expected-adapter-manifest-sha256 <adapter-manifest-sha256>
```

The destination receives two files:

- `index.html`: responsive, accessible, self-contained presentation;
- `successor-status.json`: the same strict public-safe projection used by the
  page.

Neither file loads fonts, scripts, styles, telemetry, or data from a network.
The content-security policy disables all network connections. The destination
is closed-world: it must be absent, an existing empty directory, or an existing
directory containing exactly those two regular files. Replacing a complete pair
requires `--overwrite`. A partial pair, extra file or directory, symlink, or
other non-regular entry is rejected even with `--overwrite`. Both assets are
completed in a private sibling staging directory before commit; a staged or
commit failure leaves an existing pair unchanged. Output also cannot be written
inside an immutable evidence package.

## UI maintenance rule

The status view must be checked whenever a verified package contract changes.
The page should add or remove a lifecycle state, flag, diagnostic, interval, or
semantic limitation only when a live verifier exposes corresponding evidence.
It must not infer readiness from file presence or convert an absent verifier
into a positive state.

The frozen Stage 3 console remains unchanged. Successor UI tests cover the
public disclosure boundary, human-supplied policy-identifier exclusion,
embedded POSIX and Windows path rejection, complete digest-verification chain,
calibration-wide and tri-state resource-fit display,
joint-hull coverage, complete per-resource diagnostic rendering, adapter
semantics and limitations, offline operation, accessibility landmarks, and
closed-world transactional output behavior.

## Future GitHub Pages release

The generated directory is intentionally compatible with static hosting and can
later become the input to a GitHub Pages publication workflow. Publishing is a
separate release decision. It should occur only after the successor product,
public-data review, evidence contracts, user experience, repository release
gate, and protocol labeling are stable. This builder does not create a Pages
site, change repository visibility, or publish anything.
