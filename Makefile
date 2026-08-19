.PHONY: install install-dev install-science verify preflight quickstart stage0 demo flat micro scale-1000 scale-10000 cycle7 stage3-pilot stage3-freeze stage3-confirm stage3-confirm-status stage3-confirm-console console console-remote replay-check docker-build docker-console clean package wheel

STAGE3_PROTOCOL_HASH := b8b6b320cb43a16ab0a12203ce63ec15e089fe8736c4849279a32093ffdd4851
STAGE3_CONFIRM_ID := stage3-confirmatory-20260819-01
STAGE3_CONFIRM_DIR := results/stage3/$(STAGE3_PROTOCOL_HASH)/$(STAGE3_CONFIRM_ID)
STAGE3_EXAMPLE_PILOT_ID := stage3-engineering-pilot-20260819-06

install:
	python -m pip install -e .

install-dev:
	python -m pip install -e ".[dev]"

install-science:
	python -m pip install -e ".[dev,science]"

verify:
	pytest -q

preflight:
	python scripts/verify_local_install.py

quickstart:
	python scripts/verify_local_install.py --tests --demo

stage0:
	fleet-sim stage0 --repository-root . --output local_runs/stage0-v020-001 --replications 30

demo:
	fleet-sim run --config configs/experiments/stage0_demo.yaml --output local_runs/demo-v020-001 --visualize

flat:
	fleet-sim run --config configs/baselines/flat_dense_100.yaml --output local_runs/flat-v020-001 --visualize

micro:
	fleet-sim run --config configs/baselines/microsegmented_100.yaml --output local_runs/micro-v020-001 --visualize

scale-1000:
	fleet-sim run --config configs/baselines/low_1000_metrics.yaml --output local_runs/scale-1000-v020-001

scale-10000:
	fleet-sim run --config configs/baselines/low_10000_metrics.yaml --output local_runs/scale-10000-v020-001

cycle7:
	@echo "Refusing: the retained Stage 2 Cycle 7 execution is immutable."
	@false

stage3-pilot:
	OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv-stage3-verify/bin/python scripts/run_stage3.py --mode pilot --execution-id $(STAGE3_EXAMPLE_PILOT_ID) --stage3a-replications 2 --stage3b-replications 2 --bootstrap-draws 200

stage3-freeze:
	@echo "Refusing: the v0.2.0 Stage 3 protocol is already frozen at $(STAGE3_PROTOCOL_HASH)."
	@false

stage3-confirm:
	@echo "Refusing: immutable confirmation $(STAGE3_CONFIRM_ID) is already complete."
	@false

stage3-confirm-status:
	@test -f $(STAGE3_CONFIRM_DIR)/execution_manifest.json
	@echo "Stage 3 confirmation retained at $(STAGE3_CONFIRM_DIR)"

stage3-confirm-console:
	mkdir -p local_runs/stage3-consoles
	fleet-stage3-console --mode replay --execution $(STAGE3_CONFIRM_DIR) --output local_runs/stage3-consoles/$(STAGE3_CONFIRM_ID)-copy.html --json-output local_runs/stage3-consoles/$(STAGE3_CONFIRM_ID)-copy.json

console:
	fleet-console --root .

console-remote:
	fleet-console --root . --no-browser --address 0.0.0.0 --port 5006

replay-check:
	@bundle=$$(find replay_bundles -mindepth 1 -maxdepth 1 -type d -name 'stage0-integrated-visual-demo-*' | sort | tail -1); \
	if [ -z "$$bundle" ]; then echo "No Stage 0 replay bundle found"; exit 2; fi; \
	fleet-sim verify-replay --bundle "$$bundle"

docker-build:
	docker compose build

docker-console:
	docker compose up console

wheel:
	mkdir -p dist
	python -m pip wheel . --no-deps --no-build-isolation --wheel-dir dist

clean:
	rm -rf .pytest_cache build dist *.egg-info local_runs
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

package:
	python scripts/package_release.py --output ../fleet-assurance-sim-local-release-v0.2.0-2026-08-19.zip --archive-root fleet-assurance-sim-local-release-v0.2.0-2026-08-19
