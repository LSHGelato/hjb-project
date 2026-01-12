# scripts/ops/hjb_supervisor.ps1
# HJB Supervisor
# - Watches for ops_update_watcher.flag OR ops_restart_watcher.flag in flags/pending
# - Stops watcher using PID from heartbeat JSON
# - For update: git pull --rebase origin main
# - For restart: no git; just stop/start
# - (optional) run doctor for both
# - restarts watcher via wrapper script
#
# Intended to be run by Windows Task Scheduler on each machine.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Log([string]$msg) {
    $ts = (Get-Date).ToString("s")
    Write-Host "[$ts] $msg"
}

function Get-RepoRoot {
    # This script lives in scripts\ops\; repo root is two levels up
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

function Get-VenvPython([string]$repoRoot) {
    $py = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (!(Test-Path $py)) { throw "Missing venv python: $py" }
    return $py
}

function Get-HjbPathsFromConfig([string]$repoRoot, [string]$py) {
    $cfgYaml = Join-Path $repoRoot "config\config.yaml"
    $cfgExample = Join-Path $repoRoot "config\config.example.yaml"

    # Use config.yaml if present, else config.example.yaml.
    $cfgPath = $cfgYaml
    if (!(Test-Path $cfgPath)) {
        $cfgPath = $cfgExample
    }
    if (!(Test-Path $cfgPath)) {
        throw "Neither config\config.yaml nor config\config.example.yaml exists."
    }

    # Resolve watcher_id from machine env var (required for heartbeat path)
    $watcherId = $env:HJB_WATCHER_ID
    if ([string]::IsNullOrWhiteSpace($watcherId)) {
        throw "Missing machine env var HJB_WATCHER_ID. Set it as a system variable."
    }
    $watcherId = $watcherId.Trim()

    # Python snippet prints a single JSON line with: state_root, flags_root, heartbeat_path
    $pyCode = @"
import json
from pathlib import Path
import yaml
cfg_path = Path(r'''$cfgPath''')
cfg = yaml.safe_load(cfg_path.read_text(encoding='utf-8')) or {}
paths = cfg.get('paths') if isinstance(cfg.get('paths'), dict) else {}
def pick(key):
    v = paths.get(key)
    if isinstance(v, str) and v.strip():
        return v.strip()
    v2 = cfg.get(key)
    if isinstance(v2, str) and v2.strip():
        return v2.strip()
    return None

state_root_s = pick('state_root')
if not state_root_s:
    raise SystemExit("Missing state_root (expected cfg.paths.state_root or cfg.state_root)")
state_root = Path(state_root_s)

flags_root_s = pick('flags_root') or str(state_root / 'flags')
flags_root = Path(flags_root_s)

watcher_id = r'''$watcherId'''
if watcher_id == 'orionmx_1':
    hb = state_root / 'watcher_heartbeat.json'
else:
    hb = state_root / f'watcher_heartbeat_{watcher_id}.json'

print(json.dumps({
    "state_root": str(state_root),
    "flags_root": str(flags_root),
    "heartbeat_path": str(hb),
    "watcher_id": watcher_id,
}, ensure_ascii=False))
"@

    $jsonLine = & $py -c $pyCode
    if ($LASTEXITCODE -ne 0) { throw "Failed to parse config via python." }

    return ($jsonLine | ConvertFrom-Json)
}

function Read-Heartbeat([string]$heartbeatPath) {
    if (!(Test-Path $heartbeatPath)) { return $null }
    try {
        $txt = Get-Content -LiteralPath $heartbeatPath -Raw -ErrorAction Stop
        return ($txt | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Stop-WatcherByHeartbeat($hbObj) {
    if ($null -eq $hbObj) { throw "Heartbeat not found or unreadable; cannot stop watcher safely." }
    if ($null -eq $hbObj.pid) { throw "Heartbeat missing pid; cannot stop watcher safely." }

    $pid = [int]$hbObj.pid
    $host = $hbObj.hostname

    Write-Log "Heartbeat indicates watcher pid=$pid hostname=$host watcher_id=$($hbObj.watcher_id)"

    $p = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($null -eq $p) {
        Write-Log "No process with pid=$pid is running. Treating as already stopped."
        return
    }

    # Best-effort graceful stop (Ctrl+C is not feasible); use Stop-Process.
    Write-Log "Stopping watcher pid=$pid ..."
    Stop-Process -Id $pid -Force -ErrorAction Stop

    Start-Sleep -Seconds 2

    $p2 = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($null -ne $p2) {
        throw "Failed to stop watcher pid=$pid"
    }
    Write-Log "Watcher stopped."
}

function Git-PullRebase([string]$repoRoot) {
    Write-Log "Running git pull --rebase origin main ..."
    & git -C $repoRoot fetch origin
    if ($LASTEXITCODE -ne 0) { throw "git fetch failed" }

    & git -C $repoRoot pull --rebase origin main
    if ($LASTEXITCODE -ne 0) { throw "git pull --rebase failed (resolve manually on this machine)" }

    Write-Log "Git update complete."
}

function Run-DoctorIfPresent([string]$repoRoot, [string]$py) {
    $doctor1 = Join-Path $repoRoot "scripts\ops\hjb_doctor.py"
    $doctor2 = Join-Path $repoRoot "scripts\hjb_doctor.py"

    $doctor = $null
    if (Test-Path $doctor1) { $doctor = $doctor1 }
    elseif (Test-Path $doctor2) { $doctor = $doctor2 }

    if ($null -eq $doctor) {
        Write-Log "Doctor script not found; skipping."
        return
    }

    Write-Log "Running doctor: $doctor"
    & $py $doctor
    if ($LASTEXITCODE -ne 0) { throw "Doctor failed (exit $LASTEXITCODE)" }
    Write-Log "Doctor passed."
}

function Start-WatcherViaWrapper([string]$repoRoot) {
    $watcherId = $env:HJB_WATCHER_ID
    if ([string]::IsNullOrWhiteSpace($watcherId)) {
        throw "Missing machine env var HJB_WATCHER_ID. Cannot choose wrapper."
    }
    $watcherId = $watcherId.Trim()

    $wrapper = $null
    if ($watcherId -eq "orionmx_1") {
        $wrapper = Join-Path $repoRoot "scripts\ops\run_watcher_orionmx.ps1"
    } elseif ($watcherId -eq "orionmega_1") {
        $wrapper = Join-Path $repoRoot "scripts\ops\run_watcher_orionmega.ps1"
    } else {
        throw "Unknown HJB_WATCHER_ID '$watcherId' (expected orionmx_1 or orionmega_1)"
    }

    if (!(Test-Path $wrapper)) { throw "Wrapper script missing: $wrapper" }

    Write-Log "Starting watcher via wrapper: $wrapper"

    # Start detached; Task Scheduler will keep supervisor short-lived.
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $wrapper) `
        -WorkingDirectory $repoRoot `
        -WindowStyle Hidden | Out-Null

    Write-Log "Watcher start requested."
}

function Write-ResultJson([string]$flagsRoot, [string]$status, [hashtable]$data) {
    $ts = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $host = $env:COMPUTERNAME

    if ($status -eq "ok") {
        $outDir = Join-Path $flagsRoot "completed\ops_update_watcher"
        New-Item -ItemType Directory -Force -Path $outDir | Out-Null
        $outPath = Join-Path $outDir "ops_update_watcher.$host.$ts.result.json"
    } else {
        $outDir = Join-Path $flagsRoot "failed\ops_update_watcher"
        New-Item -ItemType Directory -Force -Path $outDir | Out-Null
        $outPath = Join-Path $outDir "ops_update_watcher.$host.$ts.error.json"
    }

    $payload = @{
        schema = if ($status -eq "ok") { "hjb.ops_update_result.v1" } else { "hjb.ops_update_error.v1" }
        utc = (Get-Date).ToUniversalTime().ToString("o")
        hostname = $host
        watcher_id = $env:HJB_WATCHER_ID
        status = $status
    }

    foreach ($k in $data.Keys) { $payload[$k] = $data[$k] }

    $json = ($payload | ConvertTo-Json -Depth 8)
    $tmp = "$outPath.tmp"
    Set-Content -LiteralPath $tmp -Value $json -Encoding UTF8
    Move-Item -LiteralPath $tmp -Destination $outPath -Force
    return $outPath
}

# -------------------------
# Main supervisor logic
# -------------------------
$repoRoot = Get-RepoRoot
$py = Get-VenvPython $repoRoot
$paths = Get-HjbPathsFromConfig $repoRoot $py

$flagsRoot = $paths.flags_root
$pending = Join-Path $flagsRoot "pending"
$processing = Join-Path $flagsRoot "processing"
$completed = Join-Path $flagsRoot "completed"
$failed = Join-Path $flagsRoot "failed"

# Ensure expected dirs exist
foreach ($p in @($flagsRoot, $pending, $processing, $completed, $failed)) {
    if (!(Test-Path $p)) { throw "Required flags directory missing: $p" }
}

# Trigger file name (must NOT be .json and must NOT start with noop_)
$triggers = @(
    @{ name = "ops_update_watcher.flag"; mode = "update" },
    @{ name = "ops_restart_watcher.flag"; mode = "restart" }
)

$selected = $null
foreach ($t in $triggers) {
    $p = Join-Path $pending $t.name
    if (Test-Path $p) { $selected = @{ name = $t.name; mode = $t.mode; path = $p }; break }
}
if ($null -eq $selected) { exit 0 }

# Claim trigger atomically
$host = $env:COMPUTERNAME
$triggerName = $selected.name
$mode = $selected.mode
$triggerPath = $selected.path
$claim = Join-Path $processing "$triggerName.$host.processing"

try {
    Move-Item -LiteralPath $triggerPath -Destination $claim -ErrorAction Stop
} catch {
    # Another supervisor likely claimed it
    exit 0
}

Write-Log "Claimed update trigger: $claim"

try {
    $hb = Read-Heartbeat $paths.heartbeat_path
    Stop-WatcherByHeartbeat $hb

    if ($mode -eq "update") {
        Git-PullRebase $repoRoot
    } else {
        Write-Log "Restart mode: skipping git update."
    }

    Run-DoctorIfPresent $repoRoot $py

    Start-WatcherViaWrapper $repoRoot

    # Mark trigger as done
    $bucket = if ($mode -eq "update") { "ops_update_watcher" } else { "ops_restart_watcher" }
    $doneDir = Join-Path $completed $bucket
    New-Item -ItemType Directory -Force -Path $doneDir | Out-Null
    $donePath = Join-Path $doneDir "$triggerName.$host.done"
    Move-Item -LiteralPath $claim -Destination $donePath -Force

    $out = Write-ResultJson $flagsRoot "ok" @{
        heartbeat_path = $paths.heartbeat_path
        repo_root = $repoRoot
        trigger = $triggerName
        mode = $mode
        trigger_done = $donePath
    }
    Write-Log "Update succeeded. Result: $out"
    exit 0
}
catch {
    $err = $_
    Write-Log "Update FAILED: $($err.Exception.Message)"
    $bucket = if ($mode -eq "update") { "ops_update_watcher" } else { "ops_restart_watcher" }
    $failDir = Join-Path $failed $bucket
    New-Item -ItemType Directory -Force -Path $failDir | Out-Null
    $failPath = Join-Path $failDir "$triggerName.$host.failed"
    try { Move-Item -LiteralPath $claim -Destination $failPath -Force } catch { }

    $out = Write-ResultJson $flagsRoot "error" @{
        heartbeat_path = $paths.heartbeat_path
        repo_root = $repoRoot
        trigger = $triggerName
        mode = $mode
        trigger_failed = $failPath
        error = $err.Exception.Message
    }
    Write-Log "Wrote error record: $out"
    exit 1
}
