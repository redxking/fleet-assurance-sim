# Fleet Assurance Simulation 0.2.0: Local Quick Start

This repository contains the source tree, verification suite, experiment configurations, immutable Stage 2 and Stage 3 evidence, replay artifacts, offline consoles, and local deployment tooling.

All research outcomes are model-conditioned. Stage 3 uses synthetic data and has no external validation. Execution integrity passed, while Stage 3A and Stage 3B are both `not_supported_under_preregistered_rule`.

## Try it in a browser

Open the [Fleet Assurance Scenario Explorer](https://redxking.github.io/fleet-assurance-sim/). It is a static public-feedback MVP with no account, installation, data upload, or telemetry. It lets you choose or compare 27 controlled synthetic scenario cells and keeps projected assurance pressure visibly separate from simulated operational outcomes. Resource capacity scales proportionally with target fleet size before each capacity-case multiplier, and the 16-replication summaries have no confidence, credible, prediction, or transfer intervals.

Use the explorer to understand the model and suggest better experiments. Do not use its outputs as a fleet-size recommendation, security threshold, deployment authorization, or evidence about a real system.

- [Open the explorer](https://redxking.github.io/fleet-assurance-sim/)
- [Report a bug or propose a scenario](https://github.com/redxking/fleet-assurance-sim/issues/new/choose)
- [Review the MVP evidence and reproduction contract](docs/public_mvp.md)

To preview the exact checked-in site from a clone, run:

```bash
make public-mvp-preview
```

Then open `http://127.0.0.1:8000/`. The server is bound to the local machine only. To regenerate the 27-cell scenario pack into a new local output directory and verify the public release surface, run:

```bash
make public-mvp-data
make public-mvp-verify
```

## Recommended path for macOS and Linux

Python 3.11 or later is required. Python 3.13.0 reproduces the frozen Stage 3 environment.

```bash
git clone https://github.com/redxking/fleet-assurance-sim.git
cd fleet-assurance-sim
chmod +x scripts/bootstrap.sh scripts/quick_demo.sh
./scripts/bootstrap.sh --dev --science
source .venv/bin/activate
python scripts/verify_local_install.py --tests --demo
```

Launch the general interactive console:

```bash
fleet-console --root .
```

It normally opens at `http://127.0.0.1:5006`.

## Recommended path for Windows PowerShell

```powershell
git clone https://github.com/redxking/fleet-assurance-sim.git
cd fleet-assurance-sim
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\bootstrap.ps1 -Dev -Science
.\.venv\Scripts\Activate.ps1
python .\scripts\verify_local_install.py --tests --demo
```

Launch the general interactive console:

```powershell
fleet-console --root .
```

## Docker path

```bash
docker compose build
docker compose run --rm cli fleet-sim --help
docker compose run --rm cli python scripts/verify_local_install.py --tests --demo
docker compose up console
```

Open `http://127.0.0.1:5006`.

## Inspect the completed Stage 3 confirmation

The immutable execution is:

```text
results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01/
```

The retained offline evidence exports are:

```text
results/stage3/consoles/stage3-confirmatory-20260819-01.html
results/stage3/consoles/stage3-confirmatory-20260819-01.json
```

Open the HTML directly in a modern browser. No network connection is required.

Build a separate copy at paths that do not collide with the retained artifacts:

```bash
mkdir -p local_runs/stage3-consoles
fleet-stage3-console \
  --mode replay \
  --execution results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01 \
  --output local_runs/stage3-consoles/stage3-confirmatory-20260819-01-copy.html \
  --json-output local_runs/stage3-consoles/stage3-confirmatory-20260819-01-copy.json
```

The builder reads the immutable execution and writes only to `local_runs`. It refuses an existing output by default.

## Run one new notional scenario

Use a new output root rather than the retained release directories:

```bash
fleet-sim run \
  --config configs/baselines/mixed_100_visual.yaml \
  --output local_runs/general-v020-001 \
  --visualize
```

The command prints the new replay-bundle and offline-console paths.

## Reproduce Stage 0 verification

```bash
fleet-sim stage0 \
  --repository-root . \
  --output local_runs/stage0-v020-001 \
  --replications 30
```

## Stage 2 and Stage 3 immutability boundary

Stage 2 Cycle 7 and Stage 3 confirmation are completed records. Do not rerun their retained execution identifiers, replace their output directories, or modify their frozen manifests.

The final excluded Stage 3 engineering pilot was `stage3-engineering-pilot-20260819-05`. If an additional engineering-only diagnostic is necessary, use a new identifier such as the currently unused example below:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv-stage3-verify/bin/python scripts/run_stage3.py \
  --mode pilot \
  --execution-id stage3-engineering-pilot-20260819-06 \
  --stage3a-replications 2 \
  --stage3b-replications 2 \
  --bootstrap-draws 200
```

That pilot remains excluded from scientific adjudication. A second confirmatory experiment requires a separate working copy, a new protocol identifier, new prospective criteria, a new execution identifier, and a newly authenticated preexecution manifest. The existing confirmation must remain unchanged.

For full installation, frozen-environment details, storage requirements, troubleshooting, console security, and evidence locations, read `LOCAL_DEPLOYMENT.md`.
