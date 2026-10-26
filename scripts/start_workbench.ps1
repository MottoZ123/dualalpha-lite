$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$frontendRoot = Join-Path $projectRoot "workbench_ui"
if ([string]::IsNullOrWhiteSpace($env:NEXT_PUBLIC_RESEARCH_API_URL)) {
    $env:NEXT_PUBLIC_RESEARCH_API_URL = "http://127.0.0.1:8910"
}

$pnpmCommand = Get-Command "pnpm.cmd" -ErrorAction SilentlyContinue
$pnpmPath = if ($pnpmCommand) { $pnpmCommand.Source } else { $null }

if (-not $pnpmPath) {
    $bundledBin = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback"
    $bundledNode = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin"
    $candidate = Join-Path $bundledBin "pnpm.cmd"
    if (Test-Path -LiteralPath $candidate) {
        $pnpmPath = $candidate
        $env:PATH = "$bundledNode;$bundledBin;$env:PATH"
    }
}

if (-not $pnpmPath) {
    throw "pnpm was not found. Install Node.js 22+ and pnpm, then retry."
}

Push-Location $frontendRoot
try {
    if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot "node_modules"))) {
        & $pnpmPath install
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    & $pnpmPath run dev
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
