#!/usr/bin/env bash
set -euo pipefail

OUTPUT_ROOT="${1:-local_runs/quick_demo}"
mkdir -p "$OUTPUT_ROOT"

fleet-sim validate \
  --config configs/baselines/mixed_100_visual.yaml \
  --registry configs/parameters/registry.yaml

fleet-sim run \
  --config configs/baselines/mixed_100_visual.yaml \
  --output "$OUTPUT_ROOT" \
  --visualize

echo "Quick demo complete. Inspect $OUTPUT_ROOT/replay_bundles/."
