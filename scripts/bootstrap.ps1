param(
    [string]$Python = "python",
    [string]$VenvPath = ".venv",
    [switch]$Dev,
    [switch]$Science
)

$ErrorActionPreference = "Stop"

& $Python -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11 or later is required'; print('Using Python', sys.version.split()[0])"
& $Python -m venv $VenvPath

$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    throw "Virtual environment Python not found at $VenvPython"
}

& $VenvPython -m pip install --upgrade pip setuptools wheel

$Extras = @()
if ($Dev) { $Extras += "dev" }
if ($Science) { $Extras += "science" }

if ($Extras.Count -eq 0) {
    $InstallTarget = "."
} else {
    $InstallTarget = ".[" + ($Extras -join ",") + "]"
}

& $VenvPython -m pip install -e $InstallTarget

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host "Activate the environment with:"
Write-Host "  .\$VenvPath\Scripts\Activate.ps1"
Write-Host "Then verify with:"
Write-Host "  python .\scripts\verify_local_install.py --tests --demo"
