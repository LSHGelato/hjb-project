# HJB - Run watcher on OrionMega
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Watcher = Join-Path $RepoRoot "scripts\watcher\hjb_watcher.py"

$WatcherId = $env:HJB_WATCHER_ID
if ([string]::IsNullOrWhiteSpace($WatcherId)) {
    throw "Missing machine env var HJB_WATCHER_ID. Set it as a system variable."
}
$WatcherId = $WatcherId.Trim()

if (!(Test-Path $Py)) { throw "Missing venv python: $Py" }

$Poll = $env:HJB_POLL_SECONDS
if ([string]::IsNullOrWhiteSpace($Poll)) { $Poll = "30" }

Set-Location $RepoRoot

# ------------------------------------------------------------------
# Duplicate-start guard (operator ergonomics only):
# If a watcher appears to already be running, refuse to start another.
# Correctness is enforced by the NAS lock in hjb_watcher.py.
# ------------------------------------------------------------------
$wid = [Regex]::Escape($WatcherId)
$existing = Get-CimInstance Win32_Process |
    Where-Object {
        ($_.CommandLine -and ($_.CommandLine -match "hjb_watcher\.py") -and ($_.CommandLine -match $wid))
    } |
    Select-Object -First 1

if ($existing) {
    Write-Host "Watcher already running for watcher_id=$WatcherId (PID $($existing.ProcessId)). Refusing to start another instance."
    exit 0
}

& $Py -u $Watcher --watcher-id $WatcherId --continuous --poll-seconds $Poll
