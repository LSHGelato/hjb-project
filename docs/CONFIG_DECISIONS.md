# HJB Configuration Decision Worksheet (Pre-Deployment)

Purpose: capture all environment-specific decisions required to create `config/config.yaml`
on OrionMX and OrionMega, without needing to decide these items live at the machines.

Status:
- Secrets will be supplied via environment variables (recommended).
- Success v0 target: watcher runs on OrionMX, writes heartbeat, and can claim/complete a no-op flag.
  No OCR, no MySQL, no MediaWiki.

Last updated: ____________
Owner: Michael

---

## A. Machines and Roles

### OrionMX (continuous)
- Intended repo path: `C:\hjb-project\`
- Watcher mode: continuous
- Watcher ID (decide now): `orionmx_1`  (change if needed: ____________)
- Expected Python launcher:
  - Preferred: `py -3.11`
  - Alternate full path (if needed): `__________________________________________`

### OrionMega (opportunistic)
- Intended repo path: `C:\hjb-project\`
- Watcher mode: opportunistic
- Watcher ID (decide now): `orionmega_1` (change if needed: ____________)
- Triggering approach:
  - [ ] Manual only (initially)
  - [ ] Task Scheduler (later)
- Expected Python launcher:
  - Preferred: `py -3.11`
  - Alternate full path (if needed): `__________________________________________`

---

## B. NAS Paths (Authoritative)

Confirm these are the canonical values for `config.yaml`:

- nas_root:
  - `\\RaneyHQ\Michael`

- raw_root:
  - `\\RaneyHQ\Michael\01_Research\Historical_Journals_Inputs`

- working_root:
  - `\\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline`

- reference_root:
  - `\\RaneyHQ\Michael\05_Reference\Historical_Journals_Library`

- state_root:
  - `\\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE`

- flags_root:
  - `\\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE\flags`

- logs_root:
  - `\\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE\logs`

Notes / deviations (if any):
- _____________________________________________________________

---

## C. Scratch / Local Working Paths

### OrionMX
- scratch_root (NVMe scratch):
  - `C:\Scratch\NVMe`
- Confirm canonical subfolders exist:
  - `_tmp`, `_cache`, `_staging`, `_working`, `_spool`, `_logs`, `_quarantine`
- Notes:
  - _____________________________________________________________

### OrionMega
- scratch_root:
  - [ ] Same pattern: `C:\Scratch\NVMe`
  - [ ] Alternative local path: `__________________________________________`
- Notes:
  - _____________________________________________________________

---

## D. Watcher Behavior (Success v0)

### Continuous watcher settings (OrionMX)
- poll_interval_seconds: 30
- heartbeat filename: `watcher_heartbeat.json`
- scheduled/background tasks:
  - [ ] disabled for Success v0
  - [ ] enabled (later)

### Opportunistic watcher settings (OrionMega)
- poll_interval_seconds: 10
- heartbeat filename: `watcher_heartbeat_orionmega_1.json`
- priority filter (recommended):
  - enabled: true
  - allowed: `high`, `normal`

---

## E. Secrets and Environment Variables (Selected Model)

Chosen approach: **environment variables** (no secrets in config files).

### MySQL (HostGator)
- database.enabled for Success v0:
  - [x] false (will enable later)
- Env var name:
  - `HJB_MYSQL_PASSWORD`
- Host:
  - `__________________________________________`
- Database name:
  - `__________________________________________`
- Username:
  - `__________________________________________`

### MediaWiki
- mediawiki.enabled for Success v0:
  - [x] false (will enable later)
- Env var name:
  - `HJB_WIKI_PASSWORD`
- API URL:
  - `__________________________________________`
- Username:
  - `__________________________________________`

---

## F. Success v0 Acceptance Criteria

Success v0 is achieved when, on OrionMX:

1. Watcher runs in continuous mode without exceptions.
2. Heartbeat file is created and updates at least once per poll interval:
   - `\\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE\watcher_heartbeat.json`
3. Logs are written under:
   - `\\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE\logs\`
4. A test/no-op task can move:
   - `flags\pending` → `flags\processing` → `flags\completed`
5. No MySQL and no MediaWiki connectivity is required for Success v0.

Notes:
- _____________________________________________________________

---

## G. Deferred Decisions (Intentionally Later)

- Enabling MySQL integration
- Enabling MediaWiki sync
- First real Stage 1 task execution
- Multi-watcher / parallelism
- OrionMega Task Scheduler configuration (lock/idle triggers)
- Migrations application workflow
