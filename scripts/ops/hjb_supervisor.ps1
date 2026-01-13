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

function Get-UtcNowIso() {
    return (Get-Date).ToUniversalTime().ToString("o")
}

function Ensure-Dir([string]$path) {
    if (!(Test-Path $path)) {
        New-Item -ItemType Directory -Force -Path $path | Out-Null
    }
}

function Get-HeartbeatFreshness([object]$hbObj, [int]$pollSeconds) {
    # Returns @{ fresh = $true/$false; age_seconds = <int or $null> }
    if ($null -eq $hbObj) { return @{ fresh = $false; age_seconds = $null } }
    if ($null -eq $hbObj.utc) { return @{ fresh = $false; age_seconds = $null } }
    try {
        $hbUtc = [DateTimeOffset]::Parse([string]$hbObj.utc)
        $age = [int]((Get-Date).ToUniversalTime() - $hbUtc.UtcDateTime).TotalSeconds
        $threshold = (2 * [Math]::Max(1,$pollSeconds)) + 10
        return @{ fresh = ($age -le $threshold); age_seconds = $age }
    } catch {
        return @{ fresh = $false; age_seconds = $null }
    }
}

function Write-SupervisorHeartbeat([string]$stateRoot, [string]$watcherId, [string]$status, [hashtable]$extra) {
    # Always leaves an auditable breadcrumb on the NAS.
    $path = Join-Path $stateRoot ("supervisor_heartbeat_{0}.json" -f $watcherId)
    $payload = @{
        schema     = "hjb.supervisor_heartbeat.v1"
        utc        = Get-UtcNowIso
        hostname   = $env:COMPUTERNAME
        watcher_id = $watcherId
        status     = $status
        pid        = $PID
    }
    foreach ($k in $extra.Keys) { $payload[$k] = $extra[$k] }
    $json = ($payload | ConvertTo-Json -Depth 8)
    $tmp = "$path.tmp"
    Set-Content -LiteralPath $tmp -Value $json -Encoding UTF8
    Move-Item -LiteralPath $tmp -Destination $path -Force
    return $path
}

function Write-SupervisorLog([string]$logsRoot, [string]$watcherId, [string]$msg) {
    # Append-only log on NAS to remove "opaque" behavior from Task Scheduler runs.
    $dir = Join-Path $logsRoot "supervisor"
    Ensure-Dir $dir
    $logPath = Join-Path $dir ("supervisor_{0}.log" -f $watcherId)
    $line = "[{0}] {1}`r`n" -f (Get-Date).ToString("s"), $msg
    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
    return $logPath
}

function New-TempFilePath([string]$prefix, [string]$suffix) {
    $ts = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $rand = [Guid]::NewGuid().ToString("N")
    return (Join-Path $env:TEMP "$prefix.$ts.$rand$suffix")
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

    # Robust config parsing: write a temporary helper Python file and execute it.
    # Avoids fragile quoting issues with `python -c` under PowerShell/Task Scheduler.
    $helperPath = New-TempFilePath "hjb_parse_config" ".py"

    $helperCode = @'
import json
from pathlib import Path
import yaml

def load_cfg(p: Path) -> dict:
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"Config must be a mapping/dict: {p}")
    return data

def pick(cfg: dict, paths: dict, key: str):
    v = paths.get(key)
    if isinstance(v, str) and v.strip():
        return v.strip()
    v2 = cfg.get(key)
    if isinstance(v2, str) and v2.strip():
        return v2.strip()
    return None

def main():
    cfg_path = Path(r"{CFG_PATH}")
    watcher_id = r"{WATCHER_ID}"

    cfg = load_cfg(cfg_path)
    paths = cfg.get("paths") if isinstance(cfg.get("paths"), dict) else {}

    state_root_s = pick(cfg, paths, "state_root")
    if not state_root_s:
        raise SystemExit("Missing state_root (expected cfg.paths.state_root or cfg.state_root)")
    state_root = Path(state_root_s)

    flags_root_s = pick(cfg, paths, "flags_root") or str(state_root / "flags")
    flags_root = Path(flags_root_s)

    # Heartbeat naming convention matches watcher
    if watcher_id == "orionmx_1":
        hb = state_root / "watcher_heartbeat.json"
    else:
        hb = state_root / f"watcher_heartbeat_{watcher_id}.json"

    # Also expose scratch_root (useful for future supervisor actions; tolerant to current config shape)
    scratch_root = None
    scratch = cfg.get("scratch")
    if isinstance(scratch, dict):
        v = scratch.get("root")
        if isinstance(v, str) and v.strip():
            scratch_root = v.strip()
    if not scratch_root:
        v2 = cfg.get("scratch_root")
        if isinstance(v2, str) and v2.strip():
            scratch_root = v2.strip()
    if not scratch_root:
        v3 = paths.get("scratch_root")
        if isinstance(v3, str) and v3.strip():
            scratch_root = v3.strip()

    print(json.dumps({
        "config_path": str(cfg_path),
        "state_root": str(state_root),
        "flags_root": str(flags_root),
        "heartbeat_path": str(hb),
        "watcher_id": watcher_id,
        "scratch_root": scratch_root,
    }, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
'@

    $cfgEsc = $cfgPath.Replace("\", "\\")
    $widEsc = $watcherId.Replace("\", "\\")
    $helperCode = $helperCode.Replace("{CFG_PATH}", $cfgEsc).Replace("{WATCHER_ID}", $widEsc)
    Set-Content -LiteralPath $helperPath -Value $helperCode -Encoding UTF8

    $jsonLine = & $py $helperPath
    $exit = $LASTEXITCODE
    Remove-Item -LiteralPath $helperPath -Force -ErrorAction SilentlyContinue

    if ($exit -ne 0) { throw "Failed to parse config via python helper. ExitCode=$exit" }

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

    $watcherpid = [int]$hbObj.pid
    $hostname = $hbObj.hostname

    Write-Log "Heartbeat indicates watcher pid=$watcherpid hostname=$hostname watcher_id=$($hbObj.watcher_id)"

    $p = Get-Process -Id $watcherpid -ErrorAction SilentlyContinue
    if ($null -eq $p) {
        Write-Log "No process with pid=$watcherpid is running. Treating as already stopped."
        return
    }

    # Stop the *entire process tree* rooted at the heartbeat PID.
    # This is required on Windows when venv python spawns a child base-python process.
    Write-Log "Stopping watcher process tree rooted at pid=$watcherpid ..."
    & taskkill.exe /PID $watcherpid /T /F | Out-Null

    Start-Sleep -Seconds 2

    $p2 = Get-Process -Id $watcherpid -ErrorAction SilentlyContinue
    if ($null -ne $p2) { throw "Failed to stop watcher pid=$watcherpid (still running)" }
    Write-Log "Watcher stopped (tree kill)."
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
    $computerName = $env:COMPUTERNAME

    if ($status -eq "ok") {
        $outDir = Join-Path $flagsRoot "completed\ops_update_watcher"
        New-Item -ItemType Directory -Force -Path $outDir | Out-Null
        $outPath = Join-Path $outDir "ops_update_watcher.$computerName.$ts.result.json"
    } else {
        $outDir = Join-Path $flagsRoot "failed\ops_update_watcher"
        New-Item -ItemType Directory -Force -Path $outDir | Out-Null
        $outPath = Join-Path $outDir "ops_update_watcher.$computerName.$ts.error.json"
    }

    $payload = @{
        schema = if ($status -eq "ok") { "hjb.ops_update_result.v1" } else { "hjb.ops_update_error.v1" }
        utc = (Get-Date).ToUniversalTime().ToString("o")
        hostname = $computerName
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

# Supervisor observability (NAS-based)
$watcherId = [string]$env:HJB_WATCHER_ID
if ([string]::IsNullOrWhiteSpace($watcherId)) { $watcherId = [string]$paths.watcher_id }
$watcherId = $watcherId.Trim()
$logsRoot = Join-Path $paths.state_root "logs"
$superLog = $null
try {
    $superLog = Write-SupervisorLog $logsRoot $watcherId "Supervisor start. repoRoot=$repoRoot config=$($paths.config_path)"
} catch { }
try {
    Write-SupervisorHeartbeat $paths.state_root $watcherId "running" @{ note = "start"; log_path = $superLog } | Out-Null
} catch { }

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

# If no trigger exists, still leave a breadcrumb and optionally exit early if watcher is healthy.
if ($null -eq $selected) {
    try {
        $hb0 = Read-Heartbeat $paths.heartbeat_path
        $poll = 30
        if ($hb0 -and $hb0.poll_seconds) { $poll = [int]$hb0.poll_seconds }
        $fresh = Get-HeartbeatFreshness $hb0 $poll
        $msg = if ($fresh.fresh) { "No trigger. Watcher heartbeat fresh (age=$($fresh.age_seconds)s). Exiting." } else { "No trigger. Heartbeat stale/missing (age=$($fresh.age_seconds)). Exiting." }
        Write-Log $msg
        if ($superLog) { Write-SupervisorLog $logsRoot $watcherId $msg | Out-Null }
        Write-SupervisorHeartbeat $paths.state_root $watcherId "ok" @{ mode="noop"; heartbeat_path=$paths.heartbeat_path; heartbeat_age_seconds=$fresh.age_seconds } | Out-Null
    } catch { }
    exit 0
}

# Claim trigger atomically
$computerName = $env:COMPUTERNAME
$triggerName = $selected.name
$mode = $selected.mode
$triggerPath = $selected.path
$claim = Join-Path $processing "$triggerName.$computerName.processing"

try {
    Move-Item -LiteralPath $triggerPath -Destination $claim -ErrorAction Stop
} catch {
    # Another supervisor likely claimed it
    exit 0
}

Write-Log "Claimed update trigger: $claim"
if ($superLog) { try { Write-SupervisorLog $logsRoot $watcherId "Claimed trigger: $claim mode=$mode" | Out-Null } catch { } }

try {
    $hb = Read-Heartbeat $paths.heartbeat_path
    # If watcher appears healthy and this is a restart-only trigger, we still honor the trigger.
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
    $donePath = Join-Path $doneDir "$triggerName.$computerName.done"
    Move-Item -LiteralPath $claim -Destination $donePath -Force

    $out = Write-ResultJson $flagsRoot "ok" @{
        heartbeat_path = $paths.heartbeat_path
        repo_root = $repoRoot
        trigger = $triggerName
        mode = $mode
        trigger_done = $donePath
    }
    Write-Log "Update succeeded. Result: $out"
    if ($superLog) { try { Write-SupervisorLog $logsRoot $watcherId "Succeeded. result=$out done=$donePath" | Out-Null } catch { } }
    try { Write-SupervisorHeartbeat $paths.state_root $watcherId "ok" @{ trigger=$triggerName; mode=$mode; result_path=$out; done_path=$donePath } | Out-Null } catch { }
    exit 0
}
catch {
    $err = $_
    Write-Log "Update FAILED: $($err.Exception.Message)"
    $bucket = if ($mode -eq "update") { "ops_update_watcher" } else { "ops_restart_watcher" }
    $failDir = Join-Path $failed $bucket
    New-Item -ItemType Directory -Force -Path $failDir | Out-Null
    $failPath = Join-Path $failDir "$triggerName.$computerName.failed"
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
    if ($superLog) { try { Write-SupervisorLog $logsRoot $watcherId "FAILED. error=$($err.Exception.Message) result=$out fail=$failPath" | Out-Null } catch { } }
    try { Write-SupervisorHeartbeat $paths.state_root $watcherId "error" @{ trigger=$triggerName; mode=$mode; result_path=$out; fail_path=$failPath; error=$($err.Exception.Message) } | Out-Null } catch { }
    exit 1
}
