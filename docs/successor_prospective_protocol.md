# Successor prospective transfer protocol

## Purpose

This protocol separates a future transfer study into three immutable evidence packages:

1. A **registration package** whose declared timestamp is ordered before a distinct future evaluation campaign begins.
2. A **target-free prediction-commitment package** generated from the frozen plan without accepting the future evaluation campaign as an input.
3. An **evaluation-input package** that binds realized campaign evidence to both earlier packages.

The implementation closes an important evidence gap. The original calibration campaign can contain a historical held-out partition because the package verifier must inspect the entire package for integrity. That historical held-out partition is verified, but it is not exposed to the estimator and is not used to fit the model. The new registration points to a different campaign identifier and a future collection window, so the later transfer evidence cannot be confused with the historical source package.

[![Six-step successor evidence chain showing bound calibration, frozen registration, target-free prediction commitment, a distinct future campaign, realized-input binding, and a still-locked execution gate.](assets/successor-evidence-chain.svg)](assets/successor-evidence-chain.svg)

The three packages establish a reproducible local evidence chain. They do not provide an independently trusted timestamp, prove that people or outside systems lacked target access, open outcome custody, run a scorer, authorize the simulator, authenticate an external party, or establish external validation.

## Current boundary

| Question | Current answer |
|---|---|
| What can be registered? | Transfer of the fitted arrival-rate model across the ten assurance resources. |
| What is frozen? | The upstream campaign, fit, adapter, candidate and comparator estimators, interval construction, scoring rules, thresholds, planned campaign identity, collection window, cells, per-block predictor design, schemas, and implementation hashes. |
| What predictions are committed? | Candidate and background-only comparator rates and expected counts, with paired calibration-bootstrap mean-parameter intervals, for all ten resources in every planned block. |
| What is collected later? | A distinct campaign whose held-out time blocks must reconcile exactly to the frozen plan. |
| What can execute now? | Nothing in this component. It creates and verifies evidence packages only. |
| Are operational outcomes covered? | No. Operational-outcome transfer is explicitly disabled. |
| Is the registration time externally attested? | No. The implementation checks local timestamp ordering but does not provide trusted timestamping or third-party attestation. |
| Does a complete package establish scientific validity? | No. `external_validation`, `scientific_use_authorized`, and `runner_authorized` remain false. |

## Upstream evidence chain

Registration requires three separately digest-bound packages:

- the source empirical campaign package;
- the accepted calibration-fit package; and
- the ten-resource adapter package.

The verifier checks that the fit is bound to the source calibration partition, the adapter is bound to that fit and fit-manifest digest, and both downstream stages preserve the historical held-out boundary:

```text
source_historical_heldout_verified = true
source_historical_heldout_used_for_fit = false
heldout_used_for_adapter = false
```

This wording is deliberate. Verifying a retained held-out artifact for integrity is not the same as using its values for estimation.

## Executable transfer contract

The only implemented estimand is `resource_arrival_rate_transfer` for exactly ten assurance resource types. The frozen prediction formula is:

```text
arrival_rate = background_work_per_agent_s * fleet_size
             + admission_work_units_per_agent
             * (agents_admitted / window_duration_s)
```

Its predictor fields are `fleet_size`, `agents_admitted`, and `window_duration_ms`; the observed field is `arrival_count`. Protocol version 1.1 also freezes a separate duration-weighted background-only nonnegative least-squares comparator for each resource type:

```text
gamma = max(0, sum(fleet_size * arrival_count)
               / sum(window_duration_s * fleet_size^2))

comparator_arrival_rate = gamma * fleet_size
```

The future scorer must compute the registered metrics separately for every registered cell and resource type. They are duration-weighted normalized RMSE, absolute duration-weighted relative bias, and relative RMSE improvement over that comparator. Every registered resource-cell pair must pass. A ten-resource block containing censoring or nonzero missingness is invalid, no imputation or replacement block is allowed, and zero observed-mean or comparator-RMSE denominators are `not_evaluable` and fail closed.

The prediction intervals apply each retained successful joint calibration-block bootstrap draw to the frozen predictor rows and use two-sided equal-tail linear quantiles at the fit policy's interval level. They are marginal mean-parameter intervals. They are not simultaneous intervals, future-observation intervals, transfer-coverage evidence, or operational-risk bounds.

The example contract at [`configs/successor/resource_arrival_transfer_contract.example.json`](../configs/successor/resource_arrival_transfer_contract.example.json) is an `engineering_dry_run`. Its numerical thresholds are intentionally `null` and `criteria_frozen` is false. It demonstrates the interface without inventing scientific acceptance criteria.

A `prospective_transfer` contract is accepted only when all thresholds are numeric and frozen. The corresponding registration also requires:

- a passing, eligible `successor_transfer` fit;
- a `successor_transfer` adapter;
- nonsynthetic calibration evidence;
- no notional adapter fields;
- a future evaluation campaign ID different from the source campaign ID; and
- a declared registration timestamp ordered before the planned collection window.

Those checks make a prospective registration stricter than an engineering dry run. They still do not authorize execution or validate the thresholds scientifically.

Operational-outcome transfer is outside this contract. `operational_outcome_extension_enabled` is fixed to false. Mission loss, security incidents, privilege-weighted compromise, recovery cost, and other operational consequences need a separately defined and authorized outcome contract.

## Manifest one: freeze registration and declared chronology

The registration plan at [`configs/successor/successor_registration_plan.example.json`](../configs/successor/successor_registration_plan.example.json) declares:

- one study and plan identity;
- the registration mode;
- a distinct future campaign identity;
- the planned UTC collection window;
- exact cell identifiers and per-block time-block ID, timestamp, fleet size, admission count, and observation-window duration, with timestamps and durations aligned to whole microseconds;
- one-shot evaluation;
- fail-closed deviation handling; and
- mandatory prediction locking and outcome custody.

The example is an engineering interface demonstration with a future placeholder window. Replace its identities and window for a real study. Do not convert it to `prospective_transfer` until the fit, adapter policy, target domain, and numeric acceptance criteria have been reviewed and frozen.

Create a registration package from separately recorded upstream digests:

```bash
python scripts/freeze_successor_registration.py \
  local_runs/source-campaign-001 \
  local_runs/calibration-fit-001 \
  local_runs/resource-adapter-001 \
  local_runs/successor-registration-001 \
  --expected-campaign-evidence-manifest-sha256 <source-campaign-digest> \
  --expected-fit-evidence-manifest-sha256 <fit-digest> \
  --expected-adapter-policy-sha256 <adapter-policy-digest> \
  --expected-adapter-manifest-sha256 <adapter-manifest-digest> \
  --plan configs/successor/successor_registration_plan.example.json \
  --contract configs/successor/resource_arrival_transfer_contract.example.json
```

The destination must not exist. The command writes and verifies exactly seven files:

| Artifact | Purpose |
|---|---|
| `registration.json` | Frozen evidence-chain identities, chronology result, protocol limits, and implementation hashes |
| `registration_plan.json` | Canonical future campaign, window, cell, block, lock, and custody plan |
| `transfer_contract.json` | Canonical estimand, formula, predictors, metrics, uncertainty, and criteria contract |
| `registration_schema.json` | Retained closed registration schema |
| `registration_plan_schema.json` | Retained closed plan schema |
| `transfer_contract_schema.json` | Retained closed transfer-contract schema |
| `registration_manifest.json` | Exact artifact inventory, digests, package identity, and self-integrity hash |

The command prints `registration_manifest_sha256`. Record that digest outside the package before future collection and supply it to the evaluation-input command. A locally ordered `registered_at_utc` proves only that the record is internally consistent. The package explicitly records `registration_time_externally_attested=false`; a SHA-256 digest is not a trusted timestamp, signature, identity assertion, or proof of when an external party received the plan.

The optional `--registered-at-utc` argument exists for controlled testing and reproducible interface demonstrations. It does not create timestamp attestation and must not be used to backdate a scientific registration.

## Manifest two: commit target-free predictions

The intended workflow runs the prediction builder before the planned collection window begins. The builder reverifies the complete physical source, fit, adapter, and registration chain. It does not accept an evaluation-campaign path, evaluation-input package, outcome path, target values, or authorization override. It constructs one row for every registered block and resource type, plus paired candidate and comparator parameter draws reconstructed from the calibration-only bootstrap sequence. The verifier checks the declared timestamp's internal ordering; it does not establish the builder's actual invocation or publication time.

Create the prediction-commitment package:

```bash
python scripts/lock_successor_predictions.py \
  local_runs/source-campaign-001 \
  local_runs/calibration-fit-001 \
  local_runs/resource-adapter-001 \
  local_runs/successor-registration-001 \
  local_runs/successor-prediction-lock-001 \
  --expected-source-campaign-manifest-sha256 <source-campaign-digest> \
  --expected-fit-manifest-sha256 <fit-digest> \
  --expected-adapter-policy-sha256 <adapter-policy-digest> \
  --expected-adapter-manifest-sha256 <adapter-manifest-digest> \
  --expected-registration-manifest-sha256 <registration-digest>
```

The destination must not exist. The command writes and verifies exactly seven files:

| Artifact | Purpose |
|---|---|
| `prediction_lock.json` | Upstream bindings, aggregate counts, local chronology, model semantics, and explicit negative custody and authority gates |
| `prediction_rows.parquet` | Canonically ordered target-free candidate and comparator predictions for every planned block-resource pair |
| `prediction_parameter_draws.parquet` | Paired candidate and comparator calibration-bootstrap parameters |
| `prediction_lock_schema.json` | Retained closed prediction-lock schema |
| `prediction_rows_schema.json` | Retained exact prediction-row contract |
| `prediction_parameter_draws_schema.json` | Retained exact paired-draw contract |
| `prediction_lock_manifest.json` | Exact artifact inventory, digests, package identity, and self-integrity hash |

The command prints `prediction_lock_manifest_sha256`. Record that digest outside the package. The package records that the future campaign was not supplied, its prediction rows are target-free, and its declared local lock timestamp is ordered after registration and before the planned collection window. It does not establish package creation or publication time. It also records:

```text
prediction_lock_time_externally_attested = false
prediction_rows_preoutcome_locked = false
outcome_release_custody_verified = false
execution_chain_ready = false
external_validation = false
scientific_use_authorized = false
runner_authorized = false
```

Those false values are not implementation defects. A local timestamp and digest cannot prove when an independent party received the commitment or that people and outside systems lacked target access. A later receipt-verification package must bind the registration and prediction-manifest digests to an approved trust anchor and a receipt time before planned and realized collection before the scientific pre-outcome gate may change.

## Manifest three: bind realized evaluation inputs

The intended workflow runs the evaluation-input binder after the separately planned campaign has been collected and packaged. The binder verifies the full upstream chain and prediction commitment again, while making no claim about the campaign package's wall-clock creation time. It then requires:

- the realized campaign ID to match the registered future campaign ID;
- the realized campaign to remain distinct from the source campaign;
- recorded collection timestamps to occur after the declared registration timestamp and within the registered window;
- the held-out time-block set to match the planned set exactly; and
- every realized block timestamp, fleet size, admission count, and observation-window duration to match its frozen predictor design exactly; and
- every realized held-out block to contain all ten resource types.

The binder also requires the externally recorded prediction-manifest digest and records `prediction_lock_binding_reconciled=true`. Binding proves that the same local commitment is referenced throughout the software evidence chain. It does not establish external timing or outcome-release custody.

The realized evaluation set is taken only from the verified held-out partition. Missing held-out blocks, extra held-out blocks, campaign substitution, collection outside the window, or incomplete resource coverage in that partition fail closed. Calibration rows elsewhere in the valid seven-file campaign package remain part of package verification but are not part of the realized evaluation set. The package binds the registration-manifest digest, realized campaign evidence-manifest digest, and realized held-out content digest.

Create the evaluation-input package:

```bash
python scripts/bind_successor_evaluation_inputs.py \
  local_runs/source-campaign-001 \
  local_runs/calibration-fit-001 \
  local_runs/resource-adapter-001 \
  local_runs/successor-registration-001 \
  local_runs/successor-prediction-lock-001 \
  local_runs/future-evaluation-campaign-001 \
  local_runs/successor-evaluation-inputs-001 \
  --expected-source-campaign-manifest-sha256 <source-campaign-digest> \
  --expected-fit-manifest-sha256 <fit-digest> \
  --expected-adapter-policy-sha256 <adapter-policy-digest> \
  --expected-adapter-manifest-sha256 <adapter-manifest-digest> \
  --expected-registration-manifest-sha256 <registration-digest> \
  --expected-prediction-lock-manifest-sha256 <prediction-lock-digest> \
  --expected-evaluation-campaign-manifest-sha256 <evaluation-campaign-digest>
```

In this command, the two option names containing `campaign-manifest` refer to the corresponding campaign package's `evidence_manifest.json` SHA-256.

The destination must not exist. The command writes and verifies exactly three files:

| Artifact | Purpose |
|---|---|
| `evaluation_inputs.json` | Registration and prediction-lock bindings, realized campaign and held-out digests, chronology, and exact block and predictor-design reconciliation |
| `evaluation_inputs_schema.json` | Retained closed evaluation-input schema |
| `evaluation_inputs_manifest.json` | Exact artifact inventory, digests, package identity, and self-integrity hash |

This third manifest still does not make the chain executable. It records:

```text
registration_time_externally_attested = false
predictor_design_reconciled = true
prediction_lock_binding_reconciled = true
prediction_rows_preoutcome_locked = false
outcome_release_custody_verified = false
execution_chain_ready = false
external_validation = false
scientific_use_authorized = false
runner_authorized = false
```

The verified campaign package contains the `arrival_count` target, and package verification reads that retained artifact. The evaluation-input package therefore cannot retroactively establish a trusted pre-outcome blind. It proves exact software-chain reconciliation while preserving the false external-timing and outcome-custody gates.

The next protocol slice must verify an independent prediction receipt and outcome-release custody before any one-shot scoring path can be considered. This implementation does not contain that scorer or connect any successor package to the frozen Stage 3 runner.

## Library API

The public implementation is in [`src/fleet_sim/empirical/successor_protocol.py`](../src/fleet_sim/empirical/successor_protocol.py). Its main entry points are:

- `load_resource_arrival_transfer_contract(...)`
- `load_successor_registration_plan(...)`
- `freeze_successor_registration(...)`
- `write_successor_registration_package(...)`
- `verify_successor_registration_package(...)`
- `bind_successor_evaluation_inputs(...)`
- `write_successor_evaluation_inputs_package(...)`
- `verify_successor_evaluation_inputs_package(...)`
- `transfer_contract_schema()`
- `successor_registration_plan_schema()`
- `successor_registration_schema()`
- `successor_evaluation_inputs_schema()`

The target-free prediction implementation is isolated in [`src/fleet_sim/empirical/prediction_lock.py`](../src/fleet_sim/empirical/prediction_lock.py). Its public entry points are:

- `build_successor_prediction_lock(...)`
- `write_successor_prediction_lock_package(...)`
- `verify_successor_prediction_lock_package(...)`
- `successor_prediction_lock_schema()`
- `successor_prediction_rows_schema()`
- `successor_prediction_parameter_draws_schema()`

Loaders reject duplicate JSON keys and nonfinite values. Writers use a cooperative lock, stage a closed file set, refuse overwrite, and atomically rename the completed directory. Verifiers reject symlinked packages or entries, enforce cumulative byte limits, snapshot regular files without following symlinks where supported, verify an externally supplied manifest digest before reading the remaining package, validate exact artifact inventories, compare retained schemas with the live implementation, and deterministically recompute each record from its upstream packages.

The registration implementation record contains hashes for the successor protocol, campaign intake, calibration fit, and resource adapter files plus a runtime digest. The prediction package adds the prediction builder to that implementation boundary and separately binds its canonical row and paired-draw content. The registration bindings retain the adapter manifest and simulator-semantics digest. Any change inside the applicable boundary changes the resulting package identity.

## What remains

The protocol foundation is complete through target-free local commitment and realized-input binding. A scientific transfer study still requires:

1. justified and frozen prospective thresholds;
2. authorized nonsynthetic calibration and future campaign evidence;
3. an evidence-backed adapter with no notional fields;
4. an independent prediction-manifest receipt or trusted timestamp binding before future collection;
5. verified outcome-release custody that cannot be inferred from package order;
6. a separately reviewed one-shot scorer and result package; and
7. an explicit adjudication that keeps engineering transfer, operational outcomes, scientific support, and deployment authority separate.

No fleet-size, deployment, operational-assurance, or external-validation claim follows from any package in this chain alone.
