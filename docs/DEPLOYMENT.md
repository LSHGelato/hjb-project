# HJB Deployment Runbook

This document defines the **authoritative deployment procedure** for the Historical Journals & Books (HJB) Project. It is an operational runbook intended to be followed step-by-step and reviewed ex post facto to understand system state and change history.

This document complements the Blueprint; it does not replace it.

---

## 1. Purpose and Scope

### What “deployment” means in HJB

Deployment in HJB is a **manual, pull-based update** of code and templates from GitHub onto processing machines. There is no CI/CD pipeline and no automated remote execution.

Deployment consists of:
- Pulling updated code from the `main` branch
- Restarting the watcher **only if required**
- Verifying system health via objective checks

### In-scope systems

- **OrionMX** — primary processing computer (continuous watcher)
- **OrionMega** — opportunistic processing computer (idle/lock watcher)

### Out-of-scope systems

- **RaneyHQ (NAS)** — authoritative data storage; never “deployed”
- **HostGator MySQL / MediaWiki** — only affected by explicit migrations or template syncs

---

## 2. Deployment Prerequisites

Before deploying anything, confirm the following.

### Software requirements (per machine)

- Windows
- Git installed and available in PATH
- Python installed (version used by project)
- Repository cloned locally

### Repository location (canonical)

On both OrionMX and OrionMega:

```
C:\hjb-project\
```

### Configuration requirements

- `config/config.yaml` exists locally
- `config/config.yaml` is **not** committed
- `.gitignore` prevents secrets and data from being tracked

### NAS access

From the machine being deployed to, verify read/write access to:

```
\\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE\
```

In particular, the following subfolders must exist and be writable:

```
flags\pending
flags\processing
flags\completed
flags\failed
logs
```

If SMB access is unreliable, deployment must stop here.

---

## 3. Repository → Machine Mapping

### Code

```
C:\hjb-project\
```

### Local configuration (machine-specific)

```
C:\hjb-project\config\config.yaml
```

### Authoritative workflow state (NAS)

```
\\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE\
```

### Heartbeat files (expected)

- OrionMX:
  ```
  watcher_heartbeat.json
  ```

- OrionMega:
  ```
  watcher_heartbeat_orionmega_1.json
  ```

---

## 4. Release Workflow (GitHub)

HJB uses a simple, explicit branching model.

### Branch roles

- `main`
  - Production branch
  - Must be deployable to OrionMX
- `develop`
  - Integration branch
- `feature/*`
  - Short-lived development branches
- `hotfix/*`
  - Emergency fixes to production

### Release discipline

Every change merged into `main` must:
1. Be deployable
2. Have an entry in `CHANGELOG.md`
3. Not require data-layer modification unless explicitly documented

Tags (e.g., `v2.4.1`) are optional but recommended for major milestones.

---

## 5. Deployment Procedure — OrionMX (Continuous)

### 5.1 Pre-deployment checks

On OrionMX:

1. Open PowerShell
2. Navigate to the repository:
   ```
   cd C:\hjb-project
   ```
3. Confirm clean working tree:
   ```
   git status
   ```

If local changes exist:
- Either commit them
- Or discard them
- Do **not** deploy with an unknown state

---

### 5.2 Pull latest production code

```
git pull origin main
```

Observe output:
- No merge conflicts
- Files update cleanly

---

### 5.3 Determine whether watcher restart is required

| Change type                  | Restart watcher? |
|-----------------------------|------------------|
| Documentation only          | No               |
| Stage scripts (stage1–4)    | No               |
| Templates only              | No               |
| Watcher code                | **Yes**          |
| Config template (`example`) | No               |
| Local `config.yaml` changes | Restart optional |

If watcher code changed, continue to §5.4.

---

### 5.4 Restart watcher (if required)

1. Stop watcher (if running):
   - Close the console window **or**
   - Use Ctrl+C and allow graceful shutdown

2. Start watcher manually:
   ```
   python scripts\watcher\hjb_watcher.py --continuous --watcher-id=orionmx_1
   ```

Watcher should:
- Start without exceptions
- Write/update heartbeat file within one poll interval

---

### 5.5 Post-deployment health checks

Within 1–2 minutes, verify:

1. Heartbeat file updated recently:
   ```
   \\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE\watcher_heartbeat.json
   ```

2. Log file created for today:
   ```
   \\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE\logs\YYYY-MM-DD_processing.log
   ```

3. Watcher is polling (log entries advancing)

---

## 6. Deployment Procedure — OrionMega (Opportunistic)

### Key difference

OrionMega must **not** be actively processing tasks during deployment.

### 6.1 Ensure watcher is not running

- Confirm workstation is unlocked and active
- Confirm no watcher console window is open

---

### 6.2 Pull latest production code

```
cd C:\hjb-project
git pull origin main
```

---

### 6.3 Restart behavior

- If watcher code changed:
  - No manual start required
  - Next lock/idle trigger will start updated code
- If Task Scheduler is in use:
  - Verify task still points to correct script path

---

### 6.4 Verification

After locking workstation:

- Confirm heartbeat file appears:
  ```
  \\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE\watcher_heartbeat_orionmega_1.json
  ```
- Unlock workstation and confirm watcher exits gracefully

---

## 7. Standard Health Checks (Any Time)

Use these checks to confirm system health after deployment or during normal operation.

### Watcher health

- Heartbeat timestamp < 60 seconds old (continuous)
- Heartbeat timestamp < 2 minutes old (opportunistic)

### Queue health

```
flags\pending
flags\processing
flags\completed
flags\failed
```

Normal conditions:
- `processing` usually empty or transient
- `failed` empty or small and understood

---

## 8. Rollback Procedure

Rollback is simple and safe.

### When to rollback

- Watcher crashes repeatedly
- Tasks stall immediately after deployment
- Logs show systematic errors introduced by latest change

### Rollback steps

1. Identify last known-good commit or tag
2. On affected machine:
   ```
   git checkout <commit-or-tag>
   ```
3. Restart watcher if needed
4. Verify heartbeat and queue processing resumes

**Do not rollback for data-layer issues** (NAS, MySQL, MediaWiki outages).

---

## 9. Change-Type Matrix

| Change introduced | Action required |
|------------------|-----------------|
| Docs only        | None            |
| Stage scripts    | Pull code       |
| Watcher logic    | Pull + restart  |
| Config template  | Optional review |
| Local config     | Restart optional|
| DB migration     | Follow §10      |
| Wiki templates   | Optional sync   |

---

## 10. Database Migrations (When Enabled)

**Not active initially.**

When database migrations are introduced:

1. Take MySQL backup (`mysqldump`)
2. Apply migration SQL
3. Verify schema version
4. If failure occurs:
   - Apply rollback script
   - Restore from backup if needed

Migration scripts live in:
```
migrations/
migrations/rollback/
```

---

## 11. Common Failure Modes and Responses

| Symptom | Likely cause | Action |
|--------|--------------|--------|
| Heartbeat stale | Watcher stopped | Restart locally |
| Pending queue grows | Processing failure | Check logs, permissions |
| All processing paused | NAS offline | Wait; do not requeue |
| DB errors | HostGator outage | Disable DB integration |
| OrionMega interference | User activity | Expected; no action |

---

## 12. Final Notes

- Deployment is intentionally boring.
- If deployment feels exciting, stop and reassess.
- Favor explicit steps over clever automation.
- This document is authoritative for “how we deploy”.
