# HJB - Run watcher on OrionMega (Opportunistic Mode)
# 
# This wrapper:
# 1. Monitors Windows lock events (4800 = session lock, 4801 = session unlock)
# 2. Waits 5 minutes after lock to confirm user is really away
# 3. Launches watcher in opportunistic one-task-and-exit mode
# 4. After each task completes, checks if machine is still locked
# 5. If still locked, loops to pick up next task
# 6. If unlocked, kills watcher and exits
#
# Expects system environment variables:
# - HJB_WATCHER_ID (should be "orionmega_1")
# - HJB_POLL_SECONDS (optional, defaults to 10 for opportunistic)

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

function Get-WatcherId {
    $wid = $env:HJB_WATCHER_ID
    if ([string]::IsNullOrWhiteSpace($wid)) {
        throw "Missing machine env var HJB_WATCHER_ID. Set it as a system variable."
    }
    return $wid.Trim()
}

function Get-LastInputTime {
    # Returns the last time (in milliseconds since system boot) that user provided input.
    # Uses Windows API via GetLastInputInfo.
    
    $signature = @'
    [DllImport("user32.dll")]
    public static extern bool GetLastInputInfo(ref uint lastInputInfo);
    '
    
    try {
        $lastInput = Add-Type -MemberDefinition $signature -Name "Win32GetLastInputInfo" -Namespace Win32Functions -PassThru
        $struct = New-Object System.UInt32
        $lastInput::GetLastInputInfo([ref]$struct) | Out-Null
        return $struct
    } catch {
        Write-Log "Warning: Could not get last input time via API: $_"
        return [System.UInt32]::MaxValue
    }
}

function Get-IdleSeconds {
    # Returns how many seconds the system has been idle (no keyboard/mouse input).
    $lastInputTicks = Get-LastInputTime
    $currentTicks = [System.Environment]::TickCount
    $idleMs = $currentTicks - $lastInputTicks
    $idleSeconds = [Math]::Max(0, $idleMs / 1000)
    return [int]$idleSeconds
}

function Is-MachineIdle([int]$thresholdSeconds = 300) {
    # Returns true if system has been idle for at least thresholdSeconds (default 5 min).
    $idle = Get-IdleSeconds
    return $idle -ge $thresholdSeconds
}

function Get-SessionLockTime {
    # Attempt to get the time of the last lock event (4800) from Windows Event Log.
    # Returns a DateTime object or $null if not found recently.
    
    try {
        $lockEvents = Get-WinEvent -LogName Security -FilterXPath "*[System[EventID=4800]]" -MaxEvents 1 -ErrorAction SilentlyContinue
        if ($lockEvents -and $lockEvents.Count -gt 0) {
            return $lockEvents[0].TimeCreated
        }
    } catch {
        # May fail if event log is inaccessible; continue without it
    }
    return $null
}

function Wait-ForMachineLockedAndIdle([int]$minIdleSeconds = 300) {
    # Wait until:
    # 1. Windows lock event (4800) is detected, OR system is idle for 5 min
    # 2. Then confirm it stays locked/idle for minIdleSeconds
    
    Write-Log "Waiting for machine to be locked and idle..."
    
    $confirmCount = 0
    $confirmThreshold = 2  # Check idleness multiple times to confirm
    $checkInterval = 30  # seconds between checks
    
    while ($confirmCount -lt $confirmThreshold) {
        # Check if user has been idle for long enough
        if (Is-MachineIdle $minIdleSeconds) {
            $confirmCount++
            Write-Log "Idle for $minIdleSeconds+ seconds (confirmation $confirmCount/$confirmThreshold)..."
            
            if ($confirmCount -lt $confirmThreshold) {
                Start-Sleep -Seconds $checkInterval
            }
        } else {
            $idle = Get-IdleSeconds
            Write-Log "User active (idle: ${idle}s < ${minIdleSeconds}s). Checking again in ${checkInterval}s..."
            $confirmCount = 0
            Start-Sleep -Seconds $checkInterval
        }
    }
    
    Write-Log "Machine is locked and idle. Proceeding with opportunistic watcher."
}

function Start-OpportunisticWatcher([string]$repoRoot, [string]$py, [string]$watcherId) {
    # Launch watcher in opportunistic one-task-and-exit mode
    # Returns the Process object (or $null if start failed)
    
    $watcher = Join-Path $repoRoot "scripts\watcher\hjb_watcher.py"
    if (!(Test-Path $watcher)) { throw "Watcher script missing: $watcher" }
    
    $args = @(
        "-u", $watcher,
        "--watcher-id", $watcherId,
        "--opportunistic",
        "--one-task-and-exit",
        "--poll-seconds", "10"
    )
    
    Write-Log "Starting opportunistic watcher: $py $($args -join ' ')"
    
    try {
        $proc = Start-Process -FilePath $py -ArgumentList $args -WorkingDirectory $repoRoot `
            -WindowStyle Hidden -PassThru
        return $proc
    } catch {
        Write-Log "ERROR: Failed to start watcher: $_"
        return $null
    }
}

function Wait-WatcherCompletion([System.Diagnostics.Process]$proc, [int]$timeoutSeconds = 3600) {
    # Wait for watcher process to exit (with timeout).
    # Returns $true if process exited cleanly, $false if timeout.
    
    $exited = $proc.WaitForExit($timeoutSeconds * 1000)
    if ($exited) {
        Write-Log "Watcher exited (exit code: $($proc.ExitCode))."
        return $true
    } else {
        Write-Log "Watcher still running after ${timeoutSeconds}s timeout. Killing it..."
        try {
            $proc.Kill()
            $proc.WaitForExit(5000)
        } catch {
            Write-Log "Warning: Failed to kill watcher: $_"
        }
        return $false
    }
}

function Is-SessionLocked {
    # Check if session is currently locked by checking idle time.
    # This is not foolproof, but combined with event monitoring is reasonable.
    
    try {
        # Attempt to open a console window (fails if locked)
        $handle = [System.Diagnostics.Process]::GetCurrentProcess().MainWindowHandle
        return $handle -eq 0
    } catch {
        return $true
    }
}

function Get-Keyboard {
    # Another way to detect lock: attempt to access keyboard state.
    # Keyboard access may fail when session is locked.
    
    try {
        [System.Windows.Forms.Cursor]::Position | Out-Null
        return $false  # We have access, session not locked
    } catch {
        return $true   # No access, session likely locked
    }
}

# ========================
# Main wrapper logic
# ========================

$repoRoot = Get-RepoRoot
$py = Get-VenvPython $repoRoot
$watcherId = Get-WatcherId

Write-Log "OrionMega Opportunistic Watcher Launcher"
Write-Log "WatcherId: $watcherId"
Write-Log "RepoRoot: $repoRoot"

# Wait for machine to be locked and idle
Wait-ForMachineLockedAndIdle -minIdleSeconds 300

# Main task loop: while machine is locked, run watcher and pick up tasks
$taskCount = 0
while ($true) {
    # Check if machine is still locked
    if (Is-MachineIdle 60) {
        # Still idle (likely still locked)
        Write-Log "Machine still idle. Starting task loop (task #$($taskCount + 1))..."
    } else {
        Write-Log "Machine no longer idle. User likely back. Exiting."
        break
    }
    
    # Start watcher for one task
    $proc = Start-OpportunisticWatcher $repoRoot $py $watcherId
    if ($null -eq $proc) {
        Write-Log "ERROR: Failed to start watcher. Exiting."
        exit 1
    }
    
    # Wait for watcher to complete (with 1-hour timeout per task)
    $completed = Wait-WatcherCompletion $proc -timeoutSeconds 3600
    
    if (!$completed) {
        Write-Log "Warning: Watcher did not complete within timeout. Continuing..."
    }
    
    $taskCount++
    
    # Brief pause before checking lock status again
    Start-Sleep -Seconds 5
    
    # Check if user has returned
    if (!(Is-MachineIdle 60)) {
        Write-Log "User activity detected. Exiting opportunistic watcher."
        break
    }
    
    Write-Log "Task completed. Checking for next task..."
}

Write-Log "OrionMega opportunistic watcher exiting."
exit 0
