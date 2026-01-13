# HJB - Run watcher on OrionMX
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Watcher = Join-Path $RepoRoot "scripts\watcher\hjb_watcher.py"

if (!(Test-Path $Py)) { throw "Missing venv python: $Py" }

$WatcherId = $env:HJB_WATCHER_ID
if ([string]::IsNullOrWhiteSpace($WatcherId)) {
    throw "Missing machine env var HJB_WATCHER_ID. Set it as a system variable."
}
$WatcherId = $WatcherId.Trim()

$Poll = $env:HJB_POLL_SECONDS
if ([string]::IsNullOrWhiteSpace($Poll)) { $Poll = "30" }

Set-Location $RepoRoot

# ------------------------------------------------------------------
# Duplicate-start guard (operator ergonomics):
# If *any* hjb_watcher.py is already running for this watcher_id,
# refuse to start a new one.
# ------------------------------------------------------------------
$existing = Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -match "scripts\\watcher\\hjb_watcher\.py" -and
        $_.CommandLine -match [Regex]::Escape($WatcherId)
    } |
    Select-Object -First 1

if ($existing) {
    Write-Host "Watcher already running for watcher_id=$WatcherId (PID $($existing.ProcessId)). Refusing to start another instance."
    exit 0
}

+& $Py -u $Watcher --watcher-id $WatcherId --continuous --poll-seconds $Poll
