# HJB Local Setup Checklist (OrionMX & OrionMega)

This document is a **one-time machine initialization checklist** for preparing
OrionMX and OrionMega to run the Historical Journals & Books (HJB) pipeline.

It is intended to be followed **in order**, with boxes checked explicitly.
It complements `DEPLOYMENT.md`, `CONFIG_DECISIONS.md`, and `VENV_AND_DEPENDENCIES.md`.

---

## 1. Scope and Intent

This checklist prepares a machine to:

- Run HJB watcher processes safely
- Access the NAS workflow hub (RaneyHQ)
- Use Python **3.12** inside a project virtual environment (venv)
- Consume secrets via **system-level environment variables**
- Support Success v0 (watcher + heartbeat + no-op task)

This document does **not**:
- Enable OCR
- Enable MySQL or MediaWiki
- Apply database migrations

Those steps are deferred intentionally.

---

## 2. Practical Clean Standardization (Recommended)

Windows machines often accumulate multiple Python installs over time. For HJB, you do **not** need
a perfect purge of old versions to achieve a clean, unmistakable runtime.

**HJB standard** is “practical clean”:
- Ensure **Python 3.12.x** is installed and available via the Python Launcher (`py`)
- Create a **project-local venv** at `C:\hjb-project\.venv\`
- Run HJB only via the venv interpreter (`.venv\Scripts\python.exe`)
- Ignore legacy global packages and older interpreters unless they interfere

**Do not uninstall anything** until you have first verified what is in use (see §5.3).

A full purge of older Pythons is optional and can be done later if you still want it.

---

## 3. Machine Identification

Complete this section before proceeding.

- Machine name: ______________________________
- Role:
  - [ ] OrionMX (continuous)
  - [ ] OrionMega (opportunistic)
- Primary user account used to run watcher:
  - __________________________________________
- Date initialized: ___________________________

---

## 4. Operating System Prerequisites

- [ ] Windows fully booted and stable
- [ ] Local administrator access available
- [ ] System clock correct (date, time, timezone)

---

## 5. Python 3.12 Installation (Required)

### 5.1 Verify Python 3.12 is available

Open PowerShell and run:

```powershell
py -3.12 --version
```

Expected:
- `Python 3.12.x`

If this fails:
- Install Python 3.12 (official Windows installer from python.org)
- Ensure the **Python Launcher** is installed
- Reboot if required

### 5.2 Confirm launcher list (optional but useful)

Run:

```powershell
py -0p
```

Expected:
- A Python 3.12 interpreter path is listed

Record here:
- __________________________________________

### 5.3 Inventory check (practical clean guardrail)

Run and record outputs (for troubleshooting later):

```powershell
where python
where py
py -0p
where pip
```

Expectation for a stable system:
- `py -3.12` works reliably
- You will **not** rely on `python` or `pip` from PATH for HJB (venv only)

---

## 6. Git Installation

### 6.1 Verify Git availability

Run:

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

## 7. Repository Clone

### 7.1 Choose canonical location

The repository must live at:

```
C:\hjb-project\
```

### 7.2 Clone repository

From PowerShell:

```powershell
cd C:\
git clone https://github.com/<username>/hjb-project.git
```

Verify:

- [ ] `C:\hjb-project\README.md` exists
- [ ] `C:\hjb-project\config\config.example.yaml` exists
- [ ] `C:\hjb-project\docs\DEPLOYMENT.md` exists

---

## 8. Create Virtual Environment (venv)

Standard location:

```
C:\hjb-project\.venv\
```

### 8.1 Create venv

```powershell
cd C:\hjb-project
py -3.12 -m venv .venv
```

- [ ] `.venv\` folder created

### 8.2 Activate venv (optional; useful for interactive work)

```powershell
C:\hjb-project\.venv\Scripts\Activate.ps1
python --version
```

Expected:
- `Python 3.12.x`
- Prompt shows `(.venv)`

If activation is blocked, run once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Then re-activate.

### 8.3 Upgrade packaging tools (recommended)

```powershell
C:\hjb-project\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
```

### 8.4 Install project dependencies

```powershell
cd C:\hjb-project
C:\hjb-project\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## 9. Local Configuration File

### 9.1 Create config.yaml

From PowerShell:

```powershell
cd C:\hjb-project\config
copy config.example.yaml config.yaml
```

- [ ] `config.yaml` exists
- [ ] `config.yaml` is NOT committed to Git

### 9.2 Edit config.yaml

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

## 10. Scratch Disk Preparation

### 10.1 OrionMX (NVMe scratch)

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

### 10.2 OrionMega (if applicable)

Scratch path:
- [ ] Not configured initially (acceptable)
- [ ] If later configured, record path here: ________________________________

---

## 11. NAS Connectivity (Critical)

### 11.1 Verify access

In File Explorer, navigate to:

```
\\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE\
```

Verify:

- [ ] Folder opens without delay
- [ ] Subfolders exist: `flags`, `logs`, `scheduled`

### 11.2 Write test

Create a temporary file:

```
test_write.txt
```

Delete it afterward.

If this fails:
- STOP setup
- Resolve SMB / permissions issues first

---

## 12. System-Level Environment Variables (Secrets)

Secrets are provided via **system environment variables** to ensure availability
to services and scheduled tasks regardless of user context.

### 12.1 Open Environment Variables UI

1. Press **Win + R**
2. Type `sysdm.cpl` → Enter
3. Advanced tab → **Environment Variables**
4. Under **System variables**, click **New**

### 12.2 Define required variables

Create the following **System variables**:

| Variable name         | Value                      |
|-----------------------|----------------------------|
| HJB_MYSQL_PASSWORD    | (actual MySQL password)    |
| HJB_WIKI_PASSWORD     | (actual Wiki bot password) |

- [ ] Variables created
- [ ] Names exactly match config.yaml references

Click OK to save.

### 12.3 Reboot (required)

**Reboot the machine** to ensure system variables are visible to all processes.

---

## 13. Verify Environment Variables

After reboot, open PowerShell and run:

```powershell
[System.Environment]::GetEnvironmentVariable("HJB_MYSQL_PASSWORD","Machine")
[System.Environment]::GetEnvironmentVariable("HJB_WIKI_PASSWORD","Machine")
```

Expected:
- Values returned (may appear as plain text)

If blank:
- Variable was not created correctly
- Check spelling and scope (must be System, not User)

---

## 14. Initial Watcher Smoke Test (Manual)

For Success v0, run the watcher using the venv Python (avoid PATH ambiguity).

### 14.1 OrionMX (continuous)

```powershell
cd C:\hjb-project
C:\hjb-project\.venv\Scripts\python.exe scripts\watcher\hjb_watcher.py --continuous --watcher-id=orionmx_1
```

### 14.2 OrionMega (opportunistic)

```powershell
cd C:\hjb-project
C:\hjb-project\.venv\Scripts\python.exe scripts\watcher\hjb_watcher.py --opportunistic --watcher-id=orionmega_1
```

Expected:
- No immediate exceptions
- Console shows watcher startup message

---

## 15. Verify Heartbeat

Within 30–60 seconds, confirm file exists and updates:

### OrionMX heartbeat
```
\\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE\watcher_heartbeat.json
```

### OrionMega heartbeat (when running)
```
\\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE\watcher_heartbeat_orionmega_1.json
```

- [ ] Timestamp updates

---

## 16. Stop Watcher

Press **Ctrl+C** and confirm graceful shutdown.

---

## 17. Success v0 Confirmation

Success v0 is achieved when:

- [ ] Watcher starts cleanly (using venv Python)
- [ ] Heartbeat file updates
- [ ] Logs are written
- [ ] No DB or MediaWiki connectivity is required
- [ ] No data processing has been attempted

Record notes/issues:

______________________________________________________________________

---

## 18. Post-Setup Next Steps (Deferred)

Do **not** proceed until Success v0 is stable.

Deferred items:
- Enable MySQL integration
- Enable MediaWiki integration
- Implement real Stage 1 tasks
- Configure OrionMega Task Scheduler
- Parallelize watchers
