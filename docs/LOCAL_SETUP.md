# Local Setup Checklist (Execution Hosts)

This document defines the **required local setup** for any machine that runs
Historical Journals & Books (HJB) automation.

It is written as a **per-machine checklist** and should be executed independently
on each execution host (e.g., OrionMX, OrionMega).

The committed version of this file remains **unchecked**. If you want an audit trail,
keep a separate, non-committed run log (recommended) rather than committing checkmarks.

---

## Scope

This checklist prepares a machine to:

- Run HJB watcher processes safely
- Access NAS-hosted pipeline state on RaneyHQ
- Enforce scratch-disk isolation (high-churn work stays off archival storage)
- Execute Python automation deterministically via a project-local venv (Python 3.12)

This checklist does **not**:

- Enable OCR pipelines
- Enable MySQL or MediaWiki integration
- Perform production data ingestion or processing

Those occur after Success v0 is achieved.

---

## Success v0 Definition

Success v0 is achieved when:

- The watcher runs without error
- A heartbeat file is written and updated on the NAS
- A no-op task can be claimed and completed
- Scratch disk requirements are enforced (fail-fast if missing)

No production work occurs at Success v0.

---

## 1) Machine Identification

Complete once per machine.

- Machine name: ___________________________
- Role:
  - [ ] OrionMX (continuous execution)
  - [ ] OrionMega (continuous or opportunistic execution)
- Date completed: __________________________

---

## 2) Operating System Prerequisites

- [ ] Windows system stable and fully booted
- [ ] Administrator access available
- [ ] System clock correct

---

## 3) Python Runtime (Required)

### Standard
- Python **3.12.x**
- Python Launcher (`py`) installed
- Project-local virtual environment at `C:\hjb-project\.venv\`

### Verify Python 3.12 is available
```powershell
py -3.12 --version
```

### Verify launcher default (recommended)
For predictability, set these **System** environment variables:

- `PY_PYTHON=3.12`
- `PY_PYTHON3=3.12`

Verify:
```powershell
py --version
py -0p
```

Expected:
- `py --version` reports Python 3.12.x
- `py -0p` marks 3.12 with `*`

---

## 4) Git

- [ ] Git for Windows installed
- [ ] `git --version` succeeds

---

## 5) Repository Clone

Canonical location:
```text
C:\hjb-project\
```

Clone:
```powershell
cd C:git clone https://github.com/LSHGelato/hjb-project.git
```

Verify:
```powershell
cd C:\hjb-project
git status
```

Expected:
- On `main` (or your default branch)
- Working tree clean

---

## 6) Virtual Environment (venv)

Create venv:
```powershell
cd C:\hjb-project
py -3.12 -m venv .venv
```

Install dependencies:
```powershell
C:\hjb-project\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
C:\hjb-project\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**Note:** venv activation is optional. For automation and scheduled tasks, always
invoke the venv interpreter explicitly, e.g.:
```powershell
C:\hjb-project\.venv\Scripts\python.exe ...
```

If PowerShell blocks Activate.ps1, do not change policy unless you want the convenience.

---

## 7) Scratch Disk (Mandatory)

All execution hosts **must** have a scratch disk mounted at:
```text
C:\Scratch\NVMe
```

Required subdirectories:
- [ ] `_tmp`
- [ ] `_cache`
- [ ] `_staging`
- [ ] `_working`
- [ ] `_spool`
- [ ] `_logs`
- [ ] `_quarantine`

If `C:\Scratch\NVMe` is missing, automation must **fail loudly**.

---

## 8) Configuration File (Local, Not Committed)

Create local configuration:
```powershell
cd C:\hjb-project\config
copy config.example.yaml config.yaml
```

Verify:
- [ ] `config.yaml` exists
- [ ] `config.yaml` is gitignored (never committed)

**Important YAML rule:** `scratch_root` must be a **top-level** key (not under `paths:`).

Example:
```yaml
scratch_root: "C:\Scratch\NVMe"

paths:
  state_root: "\\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE"
  flags_root: "\\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE\flags"
  logs_root: "\\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE\logs"
```

Quick parse check (optional but useful):
```powershell
C:\hjb-project\.venv\Scripts\python.exe -c "import yaml, pathlib; d=yaml.safe_load(pathlib.Path(r'C:\hjb-project\config\config.yaml').read_text(encoding='utf-8')); print('scratch_root:', d.get('scratch_root'))"
```

Expected:
- `scratch_root: C:\Scratch\NVMe`

---

## 9) Success v0 Watcher Smoke Test

Run hjb_doctor and confirm all checks pass before starting watchers.

```powershell
cd C:\hjb-project
C:\hjb-project>C:\hjb-project\.venv\Scripts\python.exe scripts\doctor\hjb_doctor.py
```

Run the watcher using the venv Python:

### OrionMX
```powershell
cd C:\hjb-project
C:\hjb-project\.venv\Scripts\python.exe scripts\watcher\hjb_watcher.py --continuous --watcher-id=orionmx_1 --poll-seconds 30
```

### OrionMega
```powershell
cd C:\hjb-project
C:\hjb-project\.venv\Scripts\python.exe scripts\watcher\hjb_watcher.py --continuous --watcher-id=orionmega_1 --poll-seconds 30
```

Stop the watcher with **Ctrl+C** after validation steps complete.

---

## 10) Verification (NAS)

### Heartbeat files
Confirm heartbeat updates every poll cycle:

- OrionMX:
  - `\\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE\watcher_heartbeat.json`
- OrionMega:
  - `\\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE\watcher_heartbeat_orionmega_1.json`

### No-op task test
1) Create a file in pending:
   - `...\0200_STATE\flags\pending\noop_test_001.txt`
2) Confirm completion appears:
   - `...\0200_STATE\flags\completed\noop_test_001.txt.<watcher_id>.completed.json`

---

## 11) Completion Criteria (per machine)

- [ ] Watcher ran without error
- [ ] Heartbeat confirmed
- [ ] No-op task completed
- [ ] Watcher stopped cleanly

Success v0 is complete for this machine.
