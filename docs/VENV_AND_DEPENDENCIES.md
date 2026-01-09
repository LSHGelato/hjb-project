# HJB Virtual Environment and Dependencies Plan

This document defines the standard, repeatable approach for Python **3.12** virtual environments (venv)
and dependency management for the Historical Journals & Books (HJB) Project on:

- **OrionMX** (continuous processing)
- **OrionMega** (opportunistic processing)

The goal is to ensure **consistent behavior** across machines and stable, reproducible installs.

---

## 1. Standardization Decisions

### Python version
- Target runtime: **Python 3.12.x** on all processing machines

### Virtual environment location (canonical)
Create the venv inside the repo:

```
C:\hjb-project\.venv\
```

Rationale:
- Keeps project dependencies isolated from system Python
- Easy to rebuild and diagnose
- Same structure on all machines

### What does (and does not) belong in Git

**Commit:**
- `requirements.in` (human-maintained “top-level” dependencies)
- `requirements.txt` (pinned list used for installs)

**Do not commit:**
- `.venv/` directory
- `pip` caches
- any local wheels or build artifacts

---

## 2. Files to Add to the Repository

Create these at the repo root:

### 2.1 `requirements.in` (recommended)
A short list of *top-level* packages your scripts directly depend on.

Example placeholder (adjust later as scripts become real):

```
# HJB top-level dependencies (edit intentionally)
requests
pyyaml
lxml
pillow
python-dateutil
tqdm
```

Add OCR / image tooling only when you implement those stages.

### 2.2 `requirements.txt` (pinned)
Generated from `requirements.in` (preferred) or via `pip freeze` (acceptable early on).

Pinning method options:

**Option A (preferred): pip-tools**
- `pip install pip-tools`
- `pip-compile requirements.in --output-file requirements.txt`

**Option B (simple): pip freeze**
- Install packages you need, then:
  - `pip freeze > requirements.txt`

If you start with Option B, you can switch to Option A later.

---

## 3. Initial Venv Creation (per machine)

These steps are intended for PowerShell.

### 3.1 Verify Python 3.12 is available

```
py -3.12 --version
```

Expected output:
- `Python 3.12.x`

If this fails, install Python 3.12 and ensure the launcher sees it.

### 3.2 Create venv

From the repo root:

```powershell
cd C:\hjb-project
py -3.12 -m venv .venv
```

### 3.3 Activate venv

```powershell
C:\hjb-project\.venv\Scripts\Activate.ps1
```

Expected:
- prompt changes to include `(.venv)`

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Then re-run activation.

### 3.4 Upgrade pip tooling (recommended)

```powershell
python -m pip install --upgrade pip setuptools wheel
```

---

## 4. Installing Dependencies

### 4.1 Install from pinned requirements (recommended)

```powershell
python -m pip install -r requirements.txt
```

### 4.2 If using pip-tools (optional, preferred)

```powershell
python -m pip install pip-tools
pip-compile requirements.in --output-file requirements.txt
python -m pip install -r requirements.txt
```

---

## 5. How to Run Project Commands

Always run Python commands using the venv interpreter.

Two safe patterns:

### Pattern A: Activate then run
```powershell
cd C:\hjb-project
.\.venv\Scripts\Activate.ps1
python scripts\watcher\hjb_watcher.py --continuous --watcher-id=orionmx_1
```

### Pattern B: Call venv python directly (no activation)
```powershell
C:\hjb-project\.venv\Scripts\python.exe scripts\watcher\hjb_watcher.py --continuous --watcher-id=orionmx_1
```

Pattern B is often better for Task Scheduler / services.

---

## 6. Updating Dependencies

When you intentionally add or upgrade dependencies:

1. Update `requirements.in` (if using it)
2. Regenerate `requirements.txt` (pip-tools) **or** re-freeze (pip freeze)
3. Commit `requirements.in` and `requirements.txt` together
4. On each machine:
   - `git pull origin main`
   - `python -m pip install -r requirements.txt`

---

## 7. Verification Checklist (per machine)

- [ ] `C:\hjb-project\.venv\` exists
- [ ] `python --version` returns Python 3.12.x *while venv is active*
- [ ] `python -m pip list` shows expected packages
- [ ] Watcher starts using venv python (no import errors)

---

## 8. Notes / Future Enhancements

- Add `docs/REQUIREMENTS_NOTES.md` if you need to explain why a package is pinned.
- Consider a separate OCR requirements set later (e.g., `requirements-ocr.txt`) if optional components become heavy.
- If you move to Windows services, ensure the service account has access to:
  - `C:\hjb-project\`
  - `\\RaneyHQ\...`
  - Machine-level environment variables for secrets
