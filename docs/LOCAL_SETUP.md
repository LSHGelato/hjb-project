# HJB Local Setup Checklist (OrionMX & OrionMega)

This document is a **one-time machine initialization checklist** for preparing
OrionMX and OrionMega to run the Historical Journals & Books (HJB) pipeline.

It is intended to be followed **in order**, with boxes checked explicitly.
It complements `DEPLOYMENT.md` and `CONFIG_DECISIONS.md`.

---

## 1. Scope and Intent

This checklist prepares a machine to:

- Run HJB watcher processes safely
- Access the NAS workflow hub (RaneyHQ)
- Consume secrets via **system-level environment variables**
- Support Success v0 (watcher + heartbeat + no-op task)

This document does **not**:
- Enable OCR
- Enable MySQL or MediaWiki
- Apply database migrations

Those steps are deferred intentionally.

---

## 2. Machine Identification

Complete this section before proceeding.

- Machine name: ______________________________
- Role:
  - [ ] OrionMX (continuous)
  - [ ] OrionMega (opportunistic)
- Primary user account used to run watcher:
  - __________________________________________
- Date initialized: ___________________________

---

## 3. Operating System Prerequisites

- [ ] Windows fully booted and stable
- [ ] Local administrator access available
- [ ] System clock correct (date, time, timezone)

---

## 4. Git Installation

### 4.1 Verify Git availability

Open PowerShell and run:

```powershell
git --version
```

Expected:
- Git version prints successfully

If Git is missing:
- Install Git for Windows
- Ensure it is added to PATH
- Reboot if required

---

## 5. Python Installation

### 5.1 Verify Python launcher

Run:

```powershell
py -0p
```

Expected:
- Python 3.x interpreter listed (preferred 3.10+)

### 5.2 Verify default Python version

Run:

```powershell
py -3 --version
```

Record version here:
- __________________________________________

If Python is missing or outdated:
- Install official Python for Windows
- Enable “Add Python to PATH”
- Reboot if required

---

## 6. Repository Clone

### 6.1 Choose canonical location

The repository must live at:

```
C:\hjb-project\
```

### 6.2 Clone repository

From PowerShell:

```powershell
cd C:\
git clone https://github.com/<username>/hjb-project.git
```

Verify:

- [ ] `C:\hjb-project\README.md` exists
- [ ] `C:\hjb-project\config\config.example.yaml` exists

---

## 7. Local Configuration File

### 7.1 Create config.yaml

From PowerShell:

```powershell
cd C:\hjb-project\config
copy config.example.yaml config.yaml
```

- [ ] `config.yaml` exists
- [ ] `config.yaml` is NOT committed to Git

### 7.2 Edit config.yaml

Fill in **only** the following for initial Success v0:

- paths (NAS roots)
- watcher section (mode, watcher_id)
- scratch_root

Ensure the following are set:

```yaml
database:
  enabled: false

mediawiki:
  enabled: false
```

Save and close the file.

---

## 8. Scratch Disk Preparation

### 8.1 OrionMX (NVMe scratch)

Expected root:

```
C:\Scratch\NVMe\
```

Verify subfolders exist:

- [ ] `_tmp`
- [ ] `_cache`
- [ ] `_staging`
- [ ] `_working`
- [ ] `_spool`
- [ ] `_logs`
- [ ] `_quarantine`

If missing, create them manually.

### 8.2 OrionMega (if applicable)

Scratch path:
- __________________________________________

Verify writable and stable.

---

## 9. NAS Connectivity (Critical)

### 9.1 Verify access

In File Explorer, navigate to:

```
\\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE\
```

Verify:

- [ ] Folder opens without delay
- [ ] Subfolders exist: `flags`, `logs`, `scheduled`

### 9.2 Write test

Create a temporary file:

```
test_write.txt
```

Delete it afterward.

If this fails:
- STOP setup
- Resolve SMB / permissions issues first

---

## 10. System-Level Environment Variables (Secrets)

Secrets are provided via **system environment variables** to ensure availability
to services and scheduled tasks regardless of user context.

### 10.1 Open Environment Variables UI

1. Press **Win + R**
2. Type `sysdm.cpl` → Enter
3. Advanced tab → **Environment Variables**
4. Under **System variables**, click **New**

---

### 10.2 Define required variables

Create the following **System variables**:

| Variable name         | Value                      |
|-----------------------|----------------------------|
| HJB_MYSQL_PASSWORD    | (actual MySQL password)    |
| HJB_WIKI_PASSWORD     | (actual Wiki bot password) |

- [ ] Variables created
- [ ] Names exactly match config.yaml references

Click OK to save.

### 10.3 Reboot (required)

**Reboot the machine** to ensure system variables are visible to all processes.

---

## 11. Verify Environment Variables

After reboot, open PowerShell and run:

```powershell
[System.Environment]::GetEnvironmentVariable("HJB_MYSQL_PASSWORD","Machine")
[System.Environment]::GetEnvironmentVariable("HJB_WIKI_PASSWORD","Machine")
```

Expected:
- Password values returned (may appear as plain text)

If blank:
- Variable was not created correctly
- Check spelling and scope (must be System, not User)

---

## 12. Initial Watcher Smoke Test (Manual)

### 12.1 Start watcher

From PowerShell:

```powershell
cd C:\hjb-project
python scripts\watcher\hjb_watcher.py --continuous --watcher-id=orionmx_1
```

(Use opportunistic flags for OrionMega.)

Expected:
- No immediate exceptions
- Console shows watcher startup message

---

### 12.2 Verify heartbeat

Within 30–60 seconds, confirm file exists and updates:

```
\\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE\watcher_heartbeat.json
```

- [ ] Timestamp updates

---

### 12.3 Stop watcher

Press **Ctrl+C** and confirm graceful shutdown.

---

## 13. Success v0 Confirmation

Success v0 is achieved when:

- [ ] Watcher starts cleanly
- [ ] Heartbeat file updates
- [ ] Logs are written
- [ ] No DB or MediaWiki connectivity is required
- [ ] No data processing has been attempted

Record notes/issues:

______________________________________________________________________

---

## 14. Post-Setup Next Steps (Deferred)

Do **not** proceed until Success v0 is stable.

Deferred items:
- Enable MySQL integration
- Enable MediaWiki integration
- Implement real Stage 1 tasks
- Configure OrionMega Task Scheduler
- Parallelize watchers

---

## 15. Sign-off

- Setup completed by: ______________________
- Date: ______________________
- Machine role confirmed:
  - [ ] OrionMX
  - [ ] OrionMega
