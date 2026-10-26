param([switch]$FullModelStack)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $root
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        & python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python venv creation failed' }
    }
    & .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt pandas numpy scikit-learn
    if ($LASTEXITCODE -ne 0) { throw 'Core dependency installation failed' }
    if ($FullModelStack) {
        & .\.venv\Scripts\python.exe -m pip install -r requirements-models.txt
        if ($LASTEXITCODE -ne 0) { throw 'Model dependency installation failed' }
    }
    if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
    Push-Location -LiteralPath 'workbench_ui'
    try {
        & pnpm.cmd install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
    } finally { Pop-Location }
    Write-Host 'Installed. Start the backend and frontend using the root README.'
} finally { Pop-Location }
