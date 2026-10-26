$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found: $python"
}
$runtime = Join-Path $projectRoot ".motto-runtime"
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$defaultData = Join-Path $runtime "live-data"
$defaultReports = Join-Path $projectRoot "AB_Test_Reports"
if ([string]::IsNullOrWhiteSpace($env:RESEARCH_DATA_DIR)) {
    $env:RESEARCH_DATA_DIR = $defaultData
}
if ([string]::IsNullOrWhiteSpace($env:RESEARCH_REPORTS_DIR)) {
    $env:RESEARCH_REPORTS_DIR = $defaultReports
}
New-Item -ItemType Directory -Force -Path $env:RESEARCH_DATA_DIR, $env:RESEARCH_REPORTS_DIR | Out-Null
$env:ENABLE_BACKTEST_API = "false"
$env:RESEARCH_ALLOW_ORIGINS = if ([string]::IsNullOrWhiteSpace($env:RESEARCH_ALLOW_ORIGINS)) { "http://127.0.0.1:5899,http://localhost:5899" } else { $env:RESEARCH_ALLOW_ORIGINS }
$lockPath = Join-Path $runtime "motto.lock"
$resolvedLock = [System.IO.Path]::GetFullPath($lockPath)
if (-not $resolvedLock.StartsWith([System.IO.Path]::GetFullPath($projectRoot), [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Runtime lock escaped project root"
}
try {
    $lock = [System.IO.File]::Open($resolvedLock, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::Read)
} catch {
    throw "Motto Research Core already has an active local instance (lock: $resolvedLock)"
}
try {
    Set-Location -LiteralPath $projectRoot
    $stamp = [DateTimeOffset]::UtcNow.ToString("yyyyMMdd-HHmmss")
    $stdout = Join-Path $runtime "motto-$stamp.out.log"
    $stderr = Join-Path $runtime "motto-$stamp.err.log"
    $process = Start-Process -FilePath $python -ArgumentList @("-m", "uvicorn", "research_api:app", "--host", "127.0.0.1", "--port", "8910") -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $lock.SetLength(0)
    $writer = [System.IO.StreamWriter]::new($lock, [System.Text.UTF8Encoding]::new($false), 1024, $true)
    $writer.Write((@{ launcherPid = $PID; childPid = $process.Id; startedAt = [DateTimeOffset]::UtcNow.ToString('o'); projectRoot = $projectRoot } | ConvertTo-Json -Compress))
    $writer.Flush()
    $writer.Dispose()
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) { exit $process.ExitCode }
} finally {
    $lock.Dispose()
    if (Test-Path -LiteralPath $resolvedLock) { Remove-Item -LiteralPath $resolvedLock -Force }
}
