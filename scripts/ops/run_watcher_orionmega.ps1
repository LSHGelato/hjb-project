# HJB - Run watcher on OrionMega
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Watcher = Join-Path $RepoRoot "scripts\watcher\hjb_watcher.py"

if (!(Test-Path $Py)) { throw "Missing venv python: $Py" }

$Poll = $env:HJB_POLL_SECONDS
if ([string]::IsNullOrWhiteSpace($Poll)) { $Poll = "30" }

Set-Location $RepoRoot
& $Py $Watcher --continuous --poll-seconds $Poll
