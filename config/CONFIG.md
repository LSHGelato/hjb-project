# HJB Configuration Guide

This document explains how to configure the Historical Journals & Books (HJB) pipeline for your environment.

## Quick Start

1. **Copy the example files:**
   ```bash
   cp config.example.yaml config.yaml
   cp .env.example .env
   ```

2. **Fill in your credentials in `.env`:**
   - MySQL user and password (from HostGator)
   - MediaWiki bot credentials
   - Any API keys (IA, etc.)

3. **Customize `config.yaml` for your environment:**
   - Verify NAS paths match your network setup
   - Adjust OCR settings based on your hardware
   - Set machine-specific values (`watcher.instance_id`, `environment.node_name`)

4. **Load the environment variables:**
   ```bash
   # On Linux/Mac:
   source .env
   
   # On Windows (PowerShell):
   Get-Content .env | ForEach-Object {
       $name, $value = $_ -split '=', 2
       Set-Item -Path env:$name -Value $value
   }
   
   # Or simply ensure they're set in System Environment Variables on Windows
   ```

5. **Test the configuration:**
   ```bash
   python -c "from config import Config; c = Config(); print(f'NAS root: {c.storage.nas_root}')"
   ```

---

## Configuration Files Overview

### `config.yaml` (Main Configuration)

The primary configuration file for the pipeline. It contains:

- **Storage paths** — NAS locations and local scratch directories
- **Database settings** — MySQL connection details (uses env vars for secrets)
- **Source settings** — IA, HathiTrust, USModernist preferences
- **OCR configuration** — Tesseract paths, language models, confidence thresholds
- **Image processing** — DPI, deskew, contrast settings
- **Segmentation rules** — How to detect articles, ads, chapters
- **Deduplication thresholds** — Text similarity for merging duplicates
- **MediaWiki integration** — Wiki API endpoints, templates, categories
- **Watcher settings** — Poll intervals, retry logic, concurrency
- **Scheduled tasks** — Cron definitions for maintenance jobs
- **Retention policy** — Which source files to keep or delete after processing

**Comments in `config.example.yaml` explain each setting.** When deploying, copy this file to `config.yaml` and customize for your environment.

### `.env` (Credentials & Secrets)

Stores sensitive values that should **never be committed to Git**:

- MySQL passwords
- MediaWiki bot password
- API keys (IA, HathiTrust)
- SMTP credentials (for future alerting)
- Environment flags

**Security best practices:**
1. Add `.env` to `.gitignore`
2. Set file permissions to restrict access: `chmod 600 .env`
3. Never share `.env` files in public channels
4. Use strong, unique passwords
5. Rotate credentials periodically
6. Keep encrypted backups on external drives

### `ia_family_mapping.csv` (Data Mapping)

Maps Internet Archive item identifiers to HJB publication families:

```csv
ia_identifier,publication_family_code,publication_title,notes
sim_americanarchitectureandbuildingnews,american_architect,The American Architect and Building News,"Notes"
```

This file is loaded by the ingestion pipeline to:
- Group IA items into logical publication families
- Ensure consistent naming across the database
- Handle unmapped identifiers appropriately

**Maintain this file as you discover new IA collections.**

---

## Machine-Specific Configuration

Different machines (OrionMX, OrionMega, dev workstations) need slightly different settings.

### Option 1: Single `config.yaml` with overrides

Keep one main `config.yaml` and override specific values via environment variables in `.env`:

```bash
# In .env on OrionMX:
NODE_NAME="orionmx"
HJB_WATCHER_INSTANCE_ID="orionmx_watcher_1"
LOCAL_SCRATCH="C:\\Scratch"

# In .env on OrionMega:
NODE_NAME="orionmega"
HJB_WATCHER_INSTANCE_ID="orionmega_watcher_opportunistic"
LOCAL_SCRATCH="D:\\Temp"
```

Then in your Python code, read from env if present, otherwise use config.yaml values.

### Option 2: Per-machine config files (if large differences)

If machines have very different setups:

```bash
config.yaml              # Base configuration (committed to Git)
config.orionmx.yaml      # OrionMX-specific overrides
config.orionmega.yaml    # OrionMega-specific overrides
config.dev.yaml          # Local development

# Load hierarchy:
# 1. Start with config.yaml
# 2. Overlay machine-specific config if it exists
# 3. Apply env var overrides last
```

---

## Environment Variables

The pipeline reads credentials from environment variables, never from config files. This is the **secure approach**.

### Setting Environment Variables

**On Windows:**
1. Open "Environment Variables" (System Properties)
2. Add new User or System variables
3. Or use PowerShell:
   ```powershell
   [System.Environment]::SetEnvironmentVariable("HJB_MYSQL_USER", "raneywor_app_hjb", "User")
   ```

**On Linux/macOS:**
1. Edit `~/.bashrc` or `~/.zshrc`:
   ```bash
   export HJB_MYSQL_USER="raneywor_app_hjb"
   export HJB_MYSQL_PASSWORD="..."
   ```
2. Or use `.env` and source it:
   ```bash
   source .env
   ```

**In Python code:**
```python
import os
from config import Config

db_user = os.getenv("HJB_MYSQL_USER")
db_pass = os.getenv("HJB_MYSQL_PASSWORD")

# Or let the Config class handle it:
cfg = Config()
db_user = cfg.get_db_user()  # Reads from env
```

---

## Validation & Testing

After configuring, validate your setup:

### 1. Test NAS connectivity
```python
from pathlib import Path
nas_root = Path("\\\\RaneyHQ\\Michael\\02_Projects\\Historical_Journals_And_Books")
print(f"NAS accessible: {nas_root.exists()}")
```

### 2. Test database connection
```bash
python -c "from database import Database; db = Database(); db.test_connection(); print('DB OK')"
```

### 3. Test IA downloads
```bash
python scripts/stage1/download_from_ia.py --test --identifier "sim_americanarchitectureandbuildingnews"
```

### 4. Test Tesseract/OCR
```bash
python -c "import pytesseract; print(pytesseract.pytesseract.get_tesseract_version())"
```

### 5. Test MediaWiki API (if ready)
```bash
python -c "from mediawiki_integration import MediaWiki; mw = MediaWiki(); mw.test_connection(); print('Wiki OK')"
```

---

## Configuration Sections Explained

### Storage Paths

```yaml
storage:
  nas_root: "\\\\RaneyHQ\\Michael\\02_Projects\\Historical_Journals_And_Books"
```

- Use **UNC paths** (\\\\Server\\Share) for network drives on Windows
- Use **NFS or SMB mounts** (/mnt/nas) on Linux
- **local_scratch** should be a fast local SSD for temporary OCR files

### Database Configuration

```yaml
database:
  host: "raneywor.hosting.mysql.database.com"
  user_env_var: "HJB_MYSQL_USER"
  password_env_var: "HJB_MYSQL_PASSWORD"
  enabled: true
  queue_offline_operations: true
```

- **Credentials come from env vars, never hardcoded**
- `enabled: true` allows pipeline to run; set false to test without DB
- `queue_offline_operations: true` buffers DB inserts if DB is down

### Source Configuration

```yaml
sources:
  internet_archive:
    enabled: true
    collections:
      - "sim_americanarchitectureandbuildingnews"
```

- Enable/disable specific sources as needed
- Add IA collection IDs as you discover them
- Adjust download timeouts based on network speed

### OCR Configuration

```yaml
ocr:
  tesseract:
    executable_path: "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
    languages: ["eng"]
    num_threads: 2
    confidence_threshold_high: 0.85
```

- **executable_path:** Verify Tesseract is installed and path is correct
- **num_threads:** Match to your CPU cores (more = faster but uses more memory)
- **confidence thresholds:** Adjust based on your publication quality
- **languages:** Add if processing non-English publications

### Watcher Configuration

```yaml
watcher:
  instance_id: "orionmx_watcher_1"
  poll_interval: 30
  max_concurrent_tasks: 1
```

- **instance_id:** Must be unique per watcher instance
- **poll_interval:** Lower = more responsive but more NAS traffic; 30s is good
- **max_concurrent_tasks:** 1 for single CPU, increase for multi-core

### Scheduled Tasks

```yaml
scheduled_tasks:
  nightly_validation:
    enabled: true
    schedule: "0 2 * * *"  # 2 AM daily
```

- Uses **cron format** (minute, hour, day, month, day-of-week)
- Disable individual tasks by setting `enabled: false`
- Add your own scheduled tasks as needed

### Retention Policy

```yaml
retention:
  tier0_sources: ["local_scans"]
  tier2_sources: ["internet_archive", "hathi_trust"]
  keep_raw_after_processing: false
  quarantine_retention_days: 60
```

- **Tier 0:** Never delete (irreplaceable)
- **Tier 2:** Can delete after processing (can re-download)
- **Quarantine:** Safety buffer before permanent deletion

---

## Troubleshooting Configuration Issues

### Problem: "NAS path not found"

**Cause:** UNC path is wrong or NAS is unreachable  
**Fix:**
1. Verify NAS IP: `ping RaneyHQ`
2. Check SMB share is accessible: `net use \\RaneyHQ\Michael`
3. Ensure network credentials are correct
4. Test path exists: `dir \\RaneyHQ\Michael\02_Projects\...`

### Problem: "Database connection refused"

**Cause:** Credentials are wrong or DB host is inaccessible  
**Fix:**
1. Verify credentials in `.env` are correct
2. Check HostGator remote MySQL is enabled (in cPanel)
3. Test connection: `mysql -h raneywor.hosting.mysql.database.com -u app_user -p`
4. Verify firewall allows outbound port 3306

### Problem: "Tesseract executable not found"

**Cause:** Tesseract not installed or path is wrong  
**Fix:**
1. Install Tesseract: https://github.com/UB-Mannheim/tesseract/wiki
2. Verify install path: `where tesseract` (Windows) or `which tesseract` (Linux)
3. Update `config.yaml` with correct path
4. Test: `tesseract --version`

### Problem: "MediaWiki API rate limited"

**Cause:** Too many rapid requests  
**Fix:**
1. Increase `mediawiki.rate_limit_seconds`
2. Decrease `mediawiki.rate_limit_calls`
3. Stagger uploads (export tasks run in sequence, not parallel)

---

## Adding New Configuration Options

When implementing new features, follow this pattern:

1. **Add to `config.example.yaml`** with a clear comment
2. **Add to validation logic** (ensure required values are set)
3. **Add to `.env.example`** if it's a secret
4. **Document in this file** (CONFIG.md)
5. **Reference in code comments** why the setting exists

Example:

```yaml
new_feature:
  enabled: false
  timeout_seconds: 300  # Comment: How long before aborting
  retry_attempts: 3     # Comment: Number of retries on failure
```

---

## Version Control & Config Hygiene

### `.gitignore` should include:

```gitignore
# Configuration & secrets
config.yaml
.env
config.*.yaml  # Machine-specific configs

# Logs
*.log
logs/

# Python
__pycache__/
*.pyc
venv/
.venv/

# OS
.DS_Store
Thumbs.db
```

### Committed to Git:

```
✓ config.example.yaml    (template with defaults)
✓ .env.example           (shows required vars, no values)
✓ CONFIG.md              (this documentation)
✓ ia_family_mapping.csv  (if it's just reference data)
```

### NOT committed to Git:

```
✗ config.yaml            (your actual config)
✗ .env                   (your actual secrets)
✗ Logs, temp files, build artifacts
```

---

## Questions?

Refer to the blueprint document (section 7) for more details on deployment strategy and configuration management.
