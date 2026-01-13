# HJB - Run watcher on OrionMega
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Watcher = Join-Path $RepoRoot "scripts\watcher\hjb_watcher.py"

$WatcherId = $env:HJB_WATCHER_ID
if ([string]::IsNullOrWhiteSpace($WatcherId)) { throw "Missing HJB_WATCHER_ID environment variable." }
$WatcherId = $WatcherId.Trim()

if (!(Test-Path $Py)) { throw "Missing venv python: $Py" }

$Poll = $env:HJB_POLL_SECONDS
if ([string]::IsNullOrWhiteSpace($Poll)) { $Poll = "30" }

Set-Location $RepoRoot
& $Py -u $Watcher --watcher-id $WatcherId --continuous --poll-seconds $Poll
