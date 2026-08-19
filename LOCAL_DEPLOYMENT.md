# Fleet Assurance Simulation 0.2.0 Local Deployment and Reproduction Guide

## 1. Purpose

This guide installs and runs the Fleet Assurance Simulation on a local workstation. The release includes:

- Complete Python source code
- Unit, statistical, replay, integration, and protocol tests
- Baseline and research experiment configurations
- Stage 0, Stage 1, Stage 2, and Stage 3 research scripts
- Existing results, figures, execution manifests, and replay consoles
- Local Python, Docker, and Conda deployment paths
- A deterministic verification workflow

This software is a research simulation. It does not establish deployment security for any real multi-agent implementation.

## 2. Supported local environments

### Required

- Python 3.11 or later
- 64-bit operating system
- A local filesystem with write access to the repository

### Recommended

- Python 3.12 or 3.13 for routine local work; Python 3.13.0 for exact Stage 3 environment reproduction
- 8 GB RAM minimum for routine tests and small scenarios
- 16 GB RAM or more for research cycles and larger result generation
- At least 6 GB of free disk space to retain the full v0.2.0 research workspace, create one Python environment, and generate temporary outputs
- 10 GB of free disk space recommended when rebuilding large Stage 3 console exports or a release archive

Measured on the release workstation before final packaging:

- The Stage 3 working copy occupies approximately 1.79 GiB, including generated evidence and `.venv-stage3-verify`.
- The complete `results/` tree occupies approximately 1.00 GiB.
- Stage 3 results occupy approximately 926 MiB, primarily because the retained HTML and JSON evidence consoles embed large tables.
- The immutable confirmatory execution contains 23,862,646 logical bytes, approximately 22.8 MiB.
- Its retained HTML and JSON console exports contain 347,373,366 logical bytes combined, approximately 331.3 MiB.
- The dedicated verification environment occupies approximately 680 MiB on disk.

The verified v0.2.0 wheel is `dist/fleet_assurance_sim-0.2.0-py3-none-any.whl`, contains 269060 bytes, and has SHA-256 `8b730a9e4d009599c07424ff5fbfe43a5ff3fd4e27516f62617fa0c87320d988`. The final ZIP byte count is read from the materialized archive, and its digest is recorded in the adjacent `.zip.sha256` sidecar. Those archive values are externalized because the ZIP cannot contain its own final digest.

The code is platform independent Python. The deployment scripts cover:

- macOS on Apple Silicon or Intel
- Linux on x86-64 or ARM64 where compatible Python wheels are available
- Windows 10 or 11 through PowerShell
- Docker Desktop or Docker Engine

## 3. Package integrity

The archive has a companion SHA-256 file outside the ZIP. After download, verify it before extraction.

macOS or Linux:

```bash
shasum -a 256 fleet-assurance-sim-local-release-v0.2.0-2026-08-19.zip
```

Windows PowerShell:

```powershell
Get-FileHash .\fleet-assurance-sim-local-release-v0.2.0-2026-08-19.zip -Algorithm SHA256
```

After extraction, `MANIFEST.sha256` contains hashes for the packaged files. Verify on macOS or Linux with:

```bash
cd fleet-assurance-sim-local-release-v0.2.0-2026-08-19
shasum -a 256 -c MANIFEST.sha256
```

On Linux systems that use `sha256sum`:

```bash
sha256sum -c MANIFEST.sha256
```

## 4. Native Python installation

### 4.1 macOS and Linux automated bootstrap

```bash
cd fleet-assurance-sim-local-release-v0.2.0-2026-08-19
chmod +x scripts/bootstrap.sh scripts/quick_demo.sh
./scripts/bootstrap.sh --dev --science
source .venv/bin/activate
```

Bootstrap options:

- No option: install runtime dependencies and the package
- `--dev`: also install pytest, coverage, linting, and typing tools
- `--science`: also install Parquet and Sobol-analysis dependencies
- `--python /path/to/python`: select a specific Python interpreter
- `--venv PATH`: use a virtual-environment path other than `.venv`

### 4.2 Windows PowerShell automated bootstrap

```powershell
cd fleet-assurance-sim-local-release-v0.2.0-2026-08-19
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\bootstrap.ps1 -Dev -Science
.\.venv\Scripts\Activate.ps1
```

Optional parameters:

```powershell
.\scripts\bootstrap.ps1 -Python py -VenvPath .venv -Dev -Science
```

### 4.3 Manual installation

macOS or Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev,science]"
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev,science]"
```

The project metadata in `pyproject.toml` is the installation source of truth. `requirements-lock.txt` records the direct dependency versions used in the packaged reference environment. It is not a complete transitive lock with hashes.

## 5. Installation verification

Run the preflight checks:

```bash
python scripts/verify_local_install.py
```

Run preflight, the complete test suite, and a deterministic visual smoke scenario:

```bash
python scripts/verify_local_install.py --tests --demo
```

Expected test result for the packaged release:

```text
113 passed
```

The count records the complete suite immediately before Stage 3 protocol freeze. The exact duration depends on local hardware and Python package versions. A different count means the source, tests, or selected environment differs from the frozen v0.2.0 baseline.

## 6. Command-line use

Display available commands:

```bash
fleet-sim --help
```

Validate a configuration and the parameter registry:

```bash
fleet-sim validate \
  --config configs/baselines/mixed_100_visual.yaml \
  --registry configs/parameters/registry.yaml
```

Run a scenario and generate an offline console:

```bash
fleet-sim run \
  --config configs/baselines/mixed_100_visual.yaml \
  --output local_runs/general-v020-001 \
  --visualize
```

Verify a generated replay bundle:

```bash
fleet-sim verify-replay --bundle local_runs/replay_bundles/<run-id>
```

Regenerate a standalone HTML replay console:

```bash
fleet-sim visualize \
  --bundle local_runs/replay_bundles/<run-id> \
  --output local_runs/replay_bundles/<run-id>/virtual_fleet_assurance_console.html
```

## 7. Visual console

Launch the Bokeh multi-run console locally:

```bash
fleet-console --root .
```

Specify a different port:

```bash
fleet-console --root . --port 5010
```

Run without opening a browser:

```bash
fleet-console --root . --no-browser
```

Bind to a specific address, including Docker or a controlled lab network interface:

```bash
fleet-console --root . --no-browser --address 0.0.0.0 --port 5006
```

Binding to `0.0.0.0` exposes the console to reachable network interfaces. Use host firewall rules, a reverse proxy, or an isolated network as appropriate. The console has no production authentication layer.

Existing offline evidence consoles can be opened directly without starting a server:

- `replay_bundles/stage1-research-console.html`
- `replay_bundles/stage2-research-evidence-console.html`
- `replay_bundles/stage2-cycles4-7-research-console.html`
- `results/stage3/consoles/stage3-confirmatory-20260819-01.html`

The corresponding Stage 3 offline JSON export is:

- `results/stage3/consoles/stage3-confirmatory-20260819-01.json`

The Stage 3 console reports a successful execution-integrity decision and two negative scientific dispositions. It does not convert synthetic, model-conditioned evidence into external validation.

## 8. Reproduction workflows

### 8.1 Stage 0 verification

```bash
fleet-sim stage0 \
  --repository-root . \
  --output local_runs/stage0-v020-001 \
  --replications 30
```

This workflow verifies queueing, gossip, percolation, USL fitting, deterministic replay, and bounded execution paths.

### 8.2 Individual baseline scenarios

```bash
make demo
make flat
make micro
make scale-1000
make scale-10000
```

On Windows without `make`, run the equivalent `fleet-sim` commands shown in the Makefile.

### 8.3 Stage 1 research

```bash
python scripts/run_stage1_cycle1.py
python scripts/run_stage1_cycle2.py
python scripts/run_stage1_robustness.py
python scripts/build_stage1_research_console.py
```

### 8.4 Stage 2 research

The Stage 2 workflows contain preregistration and integrity controls. Read the corresponding protocol before execution.

```bash
python scripts/run_stage2_cycle5.py
python scripts/run_stage2_cycle6.py
python scripts/run_stage2_cycle7.py
python scripts/build_stage2_evidence_console.py
```

Cycle 7 verifies SHA-256 digests for frozen inputs before simulation. Any modification to the protocol, configuration, model, or dependent frozen source causes the runner to abort. This is intentional.

The packaged Cycle 7 reference execution contains:

- 34,560 stochastic replications
- 1,152 scenarios
- 576 held-out predictions
- Three independent seed blocks

The packaged execution manifest reports a reference-environment elapsed interval of approximately 83 seconds. This is an observed reference result, not a runtime guarantee.

### 8.5 Stage 3 controlled execution

Stage 3 uses `.venv-stage3-verify`, single-thread OpenBLAS and OpenMP controls, an authenticated environment snapshot, exact argument matching, 151 frozen input hashes, and append-only execution directories. The engineering pilots are never scientific evidence.

The v0.2.0 confirmation is complete. The current manifest and execution identifier are consumed immutable records, not reusable templates:

```text
Protocol hash: b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851
Execution ID: stage3-confirmatory-20260819-01
Execution path: results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01/
```

The exact recorded confirmation command was:

```bash
.venv-stage3-verify/bin/python scripts/run_stage3.py \
  --mode confirmatory \
  --execution-id stage3-confirmatory-20260819-01 \
  --stage3a-replications 12 \
  --stage3b-replications 10 \
  --bootstrap-draws 5000
```

Do not execute that command again. The runner refuses to replace the existing execution, and changing its identifier would violate the frozen command contract. Do not regenerate `manifests/stage3_preexecution_manifest.json`.

The completed execution retained:

- 2,100 Stage 3A scenarios, 25,200 raw rows, and 21,600 held-out predictions
- 240 Stage 3B specifications, 2,400 raw rows, and 1,200 held-out predictions
- 240 successful Stage 3B checkpoints with ten rows each
- Five fixed visualization traces with 41 lifecycle and DMP steps each
- 341 verified pre-manifest artifacts

Execution integrity passed. Both Stage 3A and Stage 3B are `not_supported_under_preregistered_rule`. The evidence is synthetic and model-conditioned, and no external validation was performed.

Build a new offline console copy outside the immutable execution:

```bash
mkdir -p local_runs/stage3-consoles
fleet-stage3-console \
  --mode replay \
  --execution results/stage3/b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/stage3-confirmatory-20260819-01 \
  --output local_runs/stage3-consoles/stage3-confirmatory-20260819-01-copy.html \
  --json-output local_runs/stage3-consoles/stage3-confirmatory-20260819-01-copy.json
```

For an additional engineering-only diagnostic, first create the exact local verification environment if it is absent:

```bash
python3.13 -m venv .venv-stage3-verify
.venv-stage3-verify/bin/python -m pip install -r requirements-stage3-freeze.txt
.venv-stage3-verify/bin/python -m pip install -e . --no-deps
```

Then use a new pilot identifier that does not collide with a retained directory:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv-stage3-verify/bin/python scripts/run_stage3.py \
  --mode pilot \
  --execution-id stage3-engineering-pilot-20260819-06 \
  --stage3a-replications 2 \
  --stage3b-replications 2 \
  --bootstrap-draws 200
```

The example remains engineering-only and excluded from confirmation. A new scientific confirmation requires a separate working copy, a new protocol identifier, a new execution identifier, and a newly authenticated manifest created before observing the new outcomes.

## 9. Docker deployment

### 9.1 Build

```bash
docker compose build
```

### 9.2 Run command-line checks

```bash
docker compose run --rm cli fleet-sim --help
docker compose run --rm cli python scripts/verify_local_install.py --tests --demo
```

### 9.3 Run a scenario

```bash
docker compose run --rm cli \
  fleet-sim run \
  --config configs/baselines/mixed_100_visual.yaml \
  --output local_runs/docker-v020-001 \
  --visualize
```

The repository is mounted at `/workspace`, so generated files remain on the host.

### 9.4 Run the interactive console

```bash
docker compose up console
```

Open `http://127.0.0.1:5006`.

Stop the service with:

```bash
docker compose down
```

## 10. Conda installation

```bash
conda env create -f environment.yml
conda activate fleet-assurance
python scripts/verify_local_install.py --tests --demo
```

If the environment already exists:

```bash
conda env update -f environment.yml --prune
```

## 11. Output and data locations

By default, scenario outputs are written beneath the output root supplied to `fleet-sim run`.

Typical generated structure:

```text
local_runs/
  manifests/
  replay_bundles/
    <run-id>/
      config.yaml
      initial_state.json
      final_state.json
      events.jsonl
      snapshots.jsonl
      summary.json
      virtual_fleet_assurance_console.html
  results/
```

Research workflows write to the repository's `results/`, `figures/`, `manifests/`, `paper/`, and `replay_bundles/` directories unless otherwise stated.

The retained Stage 3 layout is:

```text
results/stage3/
  b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851/
    stage3-confirmatory-20260819-01/
  engineering-pilots/
    stage3-engineering-pilot-20260819-05/
  consoles/
    stage3-confirmatory-20260819-01.html
    stage3-confirmatory-20260819-01.json
```

Only the hash-addressed confirmatory execution carries the declared confirmatory evidence scope. Engineering-pilot directories are diagnostic and excluded. The console files are derived review artifacts and are not metric inputs.

Use a cloned or copied workspace for new research cycles. Preserve the packaged directory as the immutable reference record.

## 12. Determinism and reproducibility

The simulator uses named NumPy PCG64DXSM random substreams and stable event ordering. Reproducibility still depends on:

- Exact source and configuration content
- Random seeds
- Python and dependency versions
- Numeric library behavior
- Operating-system and hardware differences for floating-point operations

For strict comparison:

1. Record `python --version`.
2. Record `python -m pip freeze`.
3. Preserve the generated manifest.
4. Preserve configuration and source SHA-256 hashes.
5. Compare output digests and replay-state hashes.

The replay check validates event-log reconstruction against the stored final state. It does not establish that the model correctly represents a real deployment.

## 13. Common problems

### `fleet-sim` or `fleet-console` is not found

Activate the virtual environment and reinstall the package:

```bash
source .venv/bin/activate
python -m pip install -e ".[dev,science]"
```

Windows:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,science]"
```

### Binary dependency installation fails on Apple Silicon

Use a native ARM64 Python from Homebrew, pyenv, or the official Python distribution, then recreate the virtual environment. Use Python 3.13.0 for the frozen Stage 3 package set. Avoid mixing an x86-64 Python interpreter with ARM64 wheels.

### Matplotlib fails on a headless host

Set a noninteractive backend:

```bash
export MPLBACKEND=Agg
```

PowerShell:

```powershell
$env:MPLBACKEND = "Agg"
```

The Docker image sets `MPLBACKEND=Agg` by default.

### Bokeh console is unreachable in Docker

Confirm the console uses:

```text
--address 0.0.0.0 --port 5006
```

and confirm port `5006` is published by Docker Compose.

### Cycle 7 aborts before execution

The hash gate detected a change to a frozen input. Compare the output against `manifests/stage2_cycle7_preregistration_manifest.json`. Run new experimental work under a new protocol identifier instead of overwriting the preregistered study.

### Stage 3 freeze or confirmation refuses to run

For this release, refusal is expected. The preexecution manifest and `stage3-confirmatory-20260819-01` already exist and are immutable. Do not remove them to force a rerun. Use the retained evidence for review, or create a separate working copy and new protocol for future science.

If a new engineering pilot fails at the environment gate, compare Python, package versions, platform, machine type, `OPENBLAS_NUM_THREADS`, and `OMP_NUM_THREADS` with the intended pilot environment. Never weaken the frozen confirmatory environment check.

### Stage 3 console output already exists

The builder refuses replacement by default. Choose a new file name outside the immutable execution directory. Do not use `--overwrite-output` for a retained evidence artifact.

### Results differ slightly across platforms

Check dependency versions and numeric tolerances first. Deterministic pseudo-random streams do not guarantee bit-identical results across every possible BLAS, operating system, compiler, and floating-point implementation.

## 14. Security and operational limitations

- The Bokeh console is a local research interface and has no production identity or access-control layer.
- Do not expose it directly to untrusted networks.
- Scenario configurations and result bundles may contain sensitive mission assumptions if you add real data.
- The packaged parameters are notional or model-conditioned unless their provenance records state otherwise.
- Do not treat successful simulation output as authority to deploy an autonomous fleet.
- Preserve immutable experiment inputs when making scientific claims.

## 15. Recommended local workflow for new research

1. Preserve this extracted package as a read-only reference.
2. Copy it to a new working directory.
3. Create a new branch or initialize a Git repository.
4. Run `python scripts/verify_local_install.py --tests --demo`.
5. Create a new protocol and configuration identifier.
6. Freeze source and configuration hashes before confirmatory execution.
7. Execute exploratory work separately from confirmatory work.
8. Retain negative results and deviation records.
9. Rebuild evidence consoles only from immutable result artifacts.
10. Package the next stage with a new release manifest and archive checksum.
