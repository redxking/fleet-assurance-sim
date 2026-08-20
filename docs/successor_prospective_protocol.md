# Successor prospective transfer protocol

## Purpose

This protocol separates a future transfer study into two immutable evidence packages:

1. A **registration package** created before a distinct future evaluation campaign begins.
2. An **evaluation-input package** created after collection that binds the realized campaign to the frozen registration.

The implementation closes an important evidence gap. The original calibration campaign can contain a historical held-out partition because the package verifier must inspect the entire package for integrity. That historical held-out partition is verified, but it is not exposed to the estimator and is not used to fit the model. The new registration points to a different campaign identifier and a future collection window, so the later transfer evidence cannot be confused with the historical source package.

[![Five-step successor evidence chain showing bound calibration, frozen registration, a distinct future campaign, realized-input binding, and a still-locked execution gate.](assets/successor-evidence-chain.svg)](assets/successor-evidence-chain.svg)

The two packages establish a reproducible local evidence chain. They do not run an evaluation, open outcome custody, authorize the simulator, authenticate an external party, or establish external validation.

## Current boundary

| Question | Current answer |
|---|---|
| What can be registered? | Transfer of the fitted arrival-rate model across the ten assurance resources. |
| What is frozen? | The upstream campaign, fit, adapter, model formula, predictors, comparator, metrics, thresholds, planned campaign identity, collection window, cells, per-block predictor design, schemas, and implementation hashes. |
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

Its predictor fields are `fleet_size`, `agents_admitted`, and `window_duration_ms`; the observed field is `arrival_count`. The registered metrics are duration-weighted normalized RMSE, absolute duration-weighted relative bias, and relative improvement over a calibration background-only nonnegative least-squares comparator. The uncertainty record describes joint calibration time-block bootstrap uncertainty for mean parameters, not a future-observation interval.

The example contract at [`configs/successor/resource_arrival_transfer_contract.example.json`](../configs/successor/resource_arrival_transfer_contract.example.json) is an `engineering_dry_run`. Its numerical thresholds are intentionally `null` and `criteria_frozen` is false. It demonstrates the interface without inventing scientific acceptance criteria.

A `prospective_transfer` contract is accepted only when all thresholds are numeric and frozen. The corresponding registration also requires:

- a passing, eligible `successor_transfer` fit;
- a `successor_transfer` adapter;
- nonsynthetic calibration evidence;
- no notional adapter fields;
- a future evaluation campaign ID different from the source campaign ID; and
- registration before the planned collection window.

Those checks make a prospective registration stricter than an engineering dry run. They still do not authorize execution or validate the thresholds scientifically.

Operational-outcome transfer is outside this contract. `operational_outcome_extension_enabled` is fixed to false. Mission loss, security incidents, privilege-weighted compromise, recovery cost, and other operational consequences need a separately defined and authorized outcome contract.

## Manifest one: freeze registration before collection

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

## Manifest two: bind realized evaluation inputs

After the separately planned campaign has been collected and packaged, the evaluation-input binder verifies the full upstream chain again. It then requires:

- the realized campaign ID to match the registered future campaign ID;
- the realized campaign to remain distinct from the source campaign;
- collection to occur after local registration and within the registered window;
- the held-out time-block set to match the planned set exactly; and
- every realized block timestamp, fleet size, admission count, and observation-window duration to match its frozen predictor design exactly; and
- every realized held-out block to contain all ten resource types.

The realized evaluation set is taken only from the verified held-out partition. Missing held-out blocks, extra held-out blocks, campaign substitution, collection outside the window, or incomplete resource coverage in that partition fail closed. Calibration rows elsewhere in the valid seven-file campaign package remain part of package verification but are not part of the realized evaluation set. The package binds the registration-manifest digest, realized campaign evidence-manifest digest, and realized held-out content digest.

Create the evaluation-input package:

```bash
python scripts/bind_successor_evaluation_inputs.py \
  local_runs/source-campaign-001 \
  local_runs/calibration-fit-001 \
  local_runs/resource-adapter-001 \
  local_runs/successor-registration-001 \
  local_runs/future-evaluation-campaign-001 \
  local_runs/successor-evaluation-inputs-001 \
  --expected-source-campaign-manifest-sha256 <source-campaign-digest> \
  --expected-fit-manifest-sha256 <fit-digest> \
  --expected-adapter-policy-sha256 <adapter-policy-digest> \
  --expected-adapter-manifest-sha256 <adapter-manifest-digest> \
  --expected-registration-manifest-sha256 <registration-digest> \
  --expected-evaluation-campaign-manifest-sha256 <evaluation-campaign-digest>
```

In this command, the two option names containing `campaign-manifest` refer to the corresponding campaign package's `evidence_manifest.json` SHA-256.

The destination must not exist. The command writes and verifies exactly three files:

| Artifact | Purpose |
|---|---|
| `evaluation_inputs.json` | Registration binding, realized campaign and held-out digests, chronology, and exact block and predictor-design reconciliation |
| `evaluation_inputs_schema.json` | Retained closed evaluation-input schema |
| `evaluation_inputs_manifest.json` | Exact artifact inventory, digests, package identity, and self-integrity hash |

This second manifest still does not make the chain executable. It records:

```text
registration_time_externally_attested = false
predictor_design_reconciled = true
prediction_rows_preoutcome_locked = false
outcome_release_custody_verified = false
execution_chain_ready = false
external_validation = false
scientific_use_authorized = false
runner_authorized = false
```

The verified campaign package already contains the `arrival_count` target, and package verification reads that retained artifact. The evaluation-input package therefore does not establish a preoutcome blind. It documents that no prediction-row commitment was in place before target access and that outcome-release custody is unverified. Those are blockers, not pending details that can be inferred away.

The next protocol slice must create an independent preoutcome prediction commitment and verify outcome-release custody before any one-shot scoring path can be considered. This implementation does not contain that scorer or connect either package to the frozen Stage 3 runner.

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

Loaders reject duplicate JSON keys and nonfinite values. Writers use a cooperative lock, stage a closed file set, refuse overwrite, and atomically rename the completed directory. Verifiers reject symlinked packages or entries, enforce cumulative byte limits, snapshot regular files without following symlinks where supported, verify an externally supplied manifest digest before reading the remaining package, validate exact artifact inventories, compare retained schemas with the live implementation, and deterministically recompute each record from its upstream packages.

The registration implementation record contains hashes for the successor protocol, campaign intake, calibration fit, and resource adapter files plus a runtime digest. The registration bindings separately retain the adapter manifest and its simulator-semantics digest. Any change inside that combined boundary changes the registration identity.

## What remains

The protocol foundation is complete through realized-input binding. A scientific transfer study still requires:

1. justified and frozen prospective thresholds;
2. authorized nonsynthetic calibration and future campaign evidence;
3. an evidence-backed adapter with no notional fields;
4. external registration receipt or trusted timestamp evidence if timing attestation is required;
5. independent prediction-row custody before outcome release;
6. a separately reviewed one-shot scorer and result package; and
7. an explicit adjudication that keeps engineering transfer, operational outcomes, scientific support, and deployment authority separate.

No fleet-size, deployment, operational-assurance, or external-validation claim follows from either manifest alone.
