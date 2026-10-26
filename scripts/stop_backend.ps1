# Stop only this checkout's registered research backend.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$lockPath = Join-Path $root '.motto-runtime\motto.lock'
if (-not (Test-Path -LiteralPath $lockPath)) { Write-Host 'No backend lock found.'; exit 0 }
$state = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
$process = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$state.childPid)"
if (-not $process) { Write-Host 'The recorded backend is no longer running.'; exit 0 }
$expectedPython = [System.IO.Path]::GetFullPath((Join-Path $root '.venv\Scripts\python.exe'))
if (-not $process.ExecutablePath -or [System.IO.Path]::GetFullPath($process.ExecutablePath) -ne $expectedPython -or -not $process.CommandLine.Contains('uvicorn research_api:app')) {
    throw 'The recorded process does not match this checkout; nothing stopped.'
}
Stop-Process -Id $process.ProcessId
Write-Host 'Research backend stopped.'
