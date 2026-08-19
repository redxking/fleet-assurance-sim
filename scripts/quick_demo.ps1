param(
    [string]$OutputRoot = "local_runs\quick_demo"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

fleet-sim validate `
  --config configs/baselines/mixed_100_visual.yaml `
  --registry configs/parameters/registry.yaml

fleet-sim run `
  --config configs/baselines/mixed_100_visual.yaml `
  --output $OutputRoot `
  --visualize

Write-Host "Quick demo complete. Inspect $OutputRoot\replay_bundles\."
