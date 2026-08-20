# Public MVP

The public MVP is a browser-based engineering sandbox for exploring a bounded set of precomputed Fleet Assurance scenarios and providing structured feedback. It is intended to make the model, its assumptions, and its negative results easier to inspect. It is not a fleet-sizing calculator or an operational assurance product.

## What a reviewer can do

The first release presents a fixed 27-cell design formed by three fleet sizes, three admission profiles, and three capacity cases. Each cell summarizes 16 fixed-seed stochastic replications from a deterministically generated public pack and retains no more than 61 representative trace points from replication 0. A reviewer can:

- compare how modeled assurance-service pressure changes across the checked-in cells;
- inspect aggregate outcome summaries, a representative time-series trace, and stated limitations;
- read plain-language explanations of what each measure represents;
- download the same public scenario pack used by the page;
- reproduce the public pack locally from the checked-in simulator; and
- submit a product defect, bounded scenario proposal, or research review through a structured GitHub form.

The capacity cases are proportional engineering fixtures: each resource capacity is recomputed for the target fleet size before the `0.8`, `1.0`, or `1.25` case multiplier is applied. Cross-fleet comparisons therefore do not hold absolute service capacity fixed. The three admission profiles apply no disturbance profile. The displayed values are descriptive summaries of 16 replications; this MVP claims no confidence, credible, prediction, or transfer interval.

The page performs no live simulation. It loads only versioned static files from this repository. The deployed package includes the exact schema identified by the data manifest so reviewers can inspect the browser contract at its public identifier. It has no account system, upload path, server-side application, telemetry, advertising, analytics, cookies, or third-party runtime asset dependency.

GitHub Pages controls the HTTP response headers. The page's HTML-delivered content-security policy restricts resource loading, but it must not be treated as evidence of response-header protections such as enforceable frame-ancestor control. A future authenticated or action-taking service would require a separately reviewed host and response-header policy.

## Evidence boundary

All MVP scenarios are synthetic and model-conditioned. The interface can help a reviewer understand or challenge implemented behavior under stated assumptions. It cannot establish:

- a safe or unsafe fleet size for a real system;
- implementation security, operational readiness, or deployment authority;
- external validation or successful transfer to an operational environment;
- ownership, compromise, controllability, or mission impact in any outside system;
- independently attested prediction timing, outcome custody, or scientific authorization; or
- support for a hypothesis that failed its preregistered all-criteria decision rule.

The retained Stage 3 record remains immutable. Public-MVP feedback may produce a UI correction, a new scenario pack, or a separately identified follow-on study. It must not silently rewrite a frozen protocol, threshold, result, or evidence package.

## Run the public page locally

From the repository root, start a loopback-only static server:

```bash
python -m http.server 8000 --bind 127.0.0.1 --directory site
```

Open `http://127.0.0.1:8000/`. Do not open `site/index.html` directly: the browser loads the scenario pack with a relative request, and browsers normally restrict that request for local files.

The local page uses the same `site/` artifact set that the publication workflow deploys. It does not contact an application backend.

## Reproduce the public data

Use Python 3.11 or later with the development and scientific dependencies installed. The scientific extra supplies PyArrow, which the retained Stage 3A generator uses for its intermediate evidence tables:

```bash
python -m pip install -e ".[dev,science]"
```

Generate into a new directory because the builder fails rather than replacing an existing package:

```bash
PYTHONPATH=src python scripts/build_public_mvp_scenarios.py build/public-mvp-reproduction
```

The builder uses the frozen public-MVP defaults unless explicit development options are supplied: root seed `20260820`, 16 replications per cell, 27 closed scenario cells, and no more than 61 representative replication-0 trace points per cell. It applies the closed semantic contract and writes a manifest that binds:

- the scenario-pack SHA-256 digest and exact byte count;
- the schema identifier and SHA-256 digest;
- the scenario and time-point counts;
- the root seed and replication count; and
- a canonical content digest for the manifest itself.

The release gate separately validates the resulting instance against the bound Draft 2020-12 schema with a pinned validator. The public copy of that schema must be byte-identical to the canonical repository schema. Schema identity and digest binding are not substitutes for instance validation, so all three checks are required.

The checked-in publication surface can be verified without a web server:

```bash
pytest -q tests/integration/test_public_mvp_release_surface.py
```

That release check rejects an unexpected, missing, empty, oversized, or linked artifact; malformed or non-finite scenario data; manifest or schema drift; a digest or byte-count mismatch; unsafe HTML; a missing content-security policy; an external runtime asset; and network-capable browser code.

## Provide feedback safely

Choose the form that matches the issue:

- **Public MVP bug:** a reproducible usability, accessibility, rendering, download, or data-loading defect.
- **Public scenario proposal:** a bounded decision question that can be represented with synthetic data or lawfully public data with documented reuse rights.
- **Research or evidence review:** a claim-to-evidence, assumption, statistical, uncertainty, reproducibility, comparator, or interpretation concern.

Keep observed facts separate from assumptions and analytical judgments. Link to the exact public artifact and provide the shortest reproducible case. Do not submit proprietary, classified, export-controlled, personal, operationally sensitive, security-sensitive, or third-party restricted information. Do not upload local measurement packages. Report suspected vulnerabilities privately through the process in `SECURITY.md`.

A usability correction does not validate a scientific claim. A research concern does not establish that a claim is wrong until the concern is reproduced and evaluated against the applicable protocol and evidence. A scenario proposal is a candidate experiment, not a requested conclusion.

## Publication acceptance gate

The Pages workflow is intentionally fail-closed. Publication from `main` requires all of the following:

1. The public directory contains exactly the approved static artifact set and no symbolic or hard links.
2. The scenario pack satisfies its closed schema, uses finite values, contains exactly 27 unique cells and 16 replications per cell, and respects the time-point limit.
3. The data and schema identities, byte counts, counts, and SHA-256 digests reconcile with the manifest.
4. HTML declares a restrictive content-security policy and safe document metadata.
5. Scripts, styles, images, and data load only from the deployed static package; no external asset, analytics, telemetry, or general network interface is present.
6. Page navigation and asset references remain within the approved public surface, apart from clearly marked ordinary links to public project resources.
7. Focused data reproduction, schema, integration, accessibility-structure, responsive-CSS, and JavaScript-runtime checks pass in a clean checkout.
8. The interface keeps synthetic status, negative results, uncertainty, and non-inferences visible and does not imply operational or scientific authorization.
9. The reviewed files are merged to `main`, which is the release authorization for this static MVP, and GitHub Pages is configured to use GitHub Actions as its source.

The validation job receives read-only repository access. Artifact packaging runs only for `main`. The separate deploy job configures and publishes Pages with the minimum `pages: write` and `id-token: write` permissions required by GitHub Pages. A feature branch can be tested but cannot upload or deploy a Pages artifact through this workflow.

## Withdrawal and recovery

If an integrity check, displayed value, material limitation, or critical user flow fails after publication, stop publication or revert the affected `main` change, preserve the reported evidence, and publish a separately identified corrected artifact after the acceptance gate passes again. Do not overwrite a frozen scientific record. If a displayed result is under review, label it as under review or withdraw that public pack rather than treating silence as validation.
