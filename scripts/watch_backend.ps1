param(
    [int]$IntervalSeconds = 20,
    [int]$FailureThreshold = 3,
    [int]$CooldownSeconds = 120
)

$ErrorActionPreference = "Continue"
$projectRoot = Split-Path -Parent $PSScriptRoot
$startScript = Join-Path $PSScriptRoot "start_backend.ps1"
$healthUri = "http://127.0.0.1:8910/api/health"
$readyUri = "http://127.0.0.1:8910/api/ready"
$lockPath = Join-Path $projectRoot ".motto-runtime\motto.lock"
$failures = 0
$lastRestart = [DateTimeOffset]::MinValue

while ($true) {
    $healthy = $false
    try {
        $health = Invoke-RestMethod -Uri $healthUri -TimeoutSec 8
        $ready = Invoke-WebRequest -Uri $readyUri -TimeoutSec 12 -UseBasicParsing
        $healthy = [bool]$health.ok -and $ready.StatusCode -eq 200
    } catch {
        $healthy = $false
    }
    if ($healthy) {
        $failures = 0
    } else {
        $failures += 1
    }
    $cooldownElapsed = ([DateTimeOffset]::UtcNow - $lastRestart).TotalSeconds -ge $CooldownSeconds
    if ($failures -ge $FailureThreshold -and $cooldownElapsed) {
        if (Test-Path -LiteralPath $lockPath) {
            try {
                $runtimeState = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
                $child = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$runtimeState.childPid)"
                $expectedPython = [System.IO.Path]::GetFullPath((Join-Path $projectRoot ".venv\Scripts\python.exe"))
                $verified = $child -and ([System.IO.Path]::GetFullPath($child.ExecutablePath) -eq $expectedPython) -and $child.CommandLine.Contains("uvicorn research_api:app")
                if ($verified) {
                    Stop-Process -Id $child.ProcessId -Force
                    for ($attempt = 0; $attempt -lt 20 -and (Test-Path -LiteralPath $lockPath); $attempt += 1) { Start-Sleep -Milliseconds 250 }
                }
            } catch {
                # An unreadable or unverifiable lock is never used to terminate a process.
            }
        }
        Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $startScript) -WorkingDirectory $projectRoot -WindowStyle Hidden
        $lastRestart = [DateTimeOffset]::UtcNow
        $failures = 0
    }
    Start-Sleep -Seconds ([Math]::Max(5, $IntervalSeconds))
}
