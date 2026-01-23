# Retroactive Registration of Internet Archive Downloads

This guide explains how to register previously downloaded Internet Archive items in the HJB MySQL database.

## Overview

The retroactive registration system allows you to:
- Register IA items that were downloaded before database integration was added
- Bulk register entire publication families with a single command
- Preview changes with dry-run mode before committing to the database

## Prerequisites

### 1. Database Access
- MySQL database `raneywor_hjbproject` must be accessible
- Set `HJB_DB_PASSWORD` environment variable, or configure in `config/config.yaml`

### 2. NAS Access
- NAS must be mounted at standard path: `\\RaneyHQ\Michael\02_Projects\Historical_Journals_And_Books\`
- Or specify alternate path with `--base-path`

### 3. Downloaded Items
- Items must be in: `Raw_Input/0110_Internet_Archive/SIM/{family_name}/{identifier}/`
- Each item directory should contain downloaded files (JP2, PDF, HOCR, etc.)

## Usage

### Basic Usage

```bash
# Preview what would be registered (dry run)
python scripts/stage1/register_existing_downloads.py --family American_Architect_family --dry-run

# Actually register items
python scripts/stage1/register_existing_downloads.py --family American_Architect_family
```

### Options

| Option | Description |
|--------|-------------|
| `--family` | **(Required)** Publication family name (e.g., `American_Architect_family`) |
| `--dry-run` | Preview without making database changes |
| `--verbose, -v` | Show detailed progress output |
| `--log-dir` | Directory for log files (default: `logs/`) |
| `--base-path` | Override base path to IA downloads |

### Examples

```bash
# Verbose output
python scripts/stage1/register_existing_downloads.py --family American_Architect_family --verbose

# Custom base path (e.g., local copy of IA downloads)
python scripts/stage1/register_existing_downloads.py --family American_Architect_family \
    --base-path "D:\IA_Downloads\SIM"

# Custom log directory
python scripts/stage1/register_existing_downloads.py --family American_Architect_family \
    --log-dir "C:\logs\hjb"
```

## Output

### Console Output

```
============================================================
Scanning family: American_Architect_family
Base path: \\RaneyHQ\Michael\...\0110_Internet_Archive\SIM
Dry run: False
============================================================

Found 142 items

Processing: sim_americanarchitect_27_1890_01
  ✓ Registered (container_id: 1234)

Processing: sim_americanarchitect_27_1890_02
  ⊘ Already registered (container_id: 1235)

Processing: sim_americanarchitect_27_1890_03
  ✗ Error: FileNotFoundError: ...

============================================================
Summary:
  Total:             142
  Newly registered:  101
  Already registered: 38
  Failed:            3
============================================================
```

### Log Files

Detailed logs are written to `logs/register_existing_YYYYMMDD_HHMMSS.log` containing:
- All processed items with timestamps
- Error details and stack traces
- Summary statistics

## How It Works

1. **Directory Scan**: The script scans the family directory for item subdirectories
2. **Duplicate Check**: Each item is checked against the database to avoid duplicates
3. **Metadata Reconstruction**: For each new item:
   - Reads `{identifier}_meta.json` for IA metadata
   - Parses `{identifier}_scandata.xml` for page count
   - Scans directory for available file types (JP2, PDF, HOCR, etc.)
4. **Database Registration**: Creates records in `containers_t` and `processing_status_t`

## Database Records Created

### containers_t

| Field | Value |
|-------|-------|
| `source_system` | `internet_archive` |
| `source_identifier` | IA identifier |
| `source_url` | `https://archive.org/details/{identifier}` |
| `family_id` | FK to publication_families_t |
| `container_label` | Derived from metadata (title, volume, date) |
| `total_pages` | From scandata.xml (if available) |
| `has_jp2`, `has_pdf`, etc. | Detected from directory scan |
| `raw_input_path` | Full path to item directory |
| `download_status` | `complete` |

### processing_status_t

- All stage completion flags set to 0
- `pipeline_status` = `pending`

## Troubleshooting

### "Database module not available"

Install required packages:
```bash
pip install mysql-connector-python PyYAML
```

### "Database connection failed"

1. Check `HJB_DB_PASSWORD` environment variable is set
2. Verify database host is accessible
3. Check `config/config.yaml` database settings

### "Family directory not found"

1. Verify NAS is mounted
2. Check family name spelling
3. Use `--base-path` to specify alternate location

### "Base path not found"

1. Mount NAS drive
2. Or use `--base-path` with local path to downloads

### Items showing as "Failed"

Check the log file for detailed error messages. Common issues:
- Missing or corrupt `_meta.json`
- Invalid XML in `_scandata.xml`
- Database constraint violations

## Re-running the Script

The script is idempotent - it's safe to run multiple times:
- Already-registered items are skipped
- Only new items are added
- No duplicates are created

## Related Files

- `scripts/stage1/register_existing_downloads.py` - Bulk registration CLI script
- `scripts/stage1/ia_acquire.py` - Core acquisition and registration functions
- `scripts/common/hjb_db.py` - Database operations
- `config/config.yaml` - Database configuration
