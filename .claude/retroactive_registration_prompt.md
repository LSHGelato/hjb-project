# Retroactive IA Registration Implementation

## Goal
Register previously downloaded Internet Archive items in the MySQL database by modifying existing code and creating a bulk registration script.

## Context
- Repository: https://github.com/RaneyArchive/HJB-project
- Database: `raneywor_hjbproject` on HostGator (MySQL)
- Main script: `scripts/ia_acquire.py` (contains `register_container_in_db()`)
- NAS base: `\\RaneyHQ\Michael\02_Projects\Historical_Journals_And_Books\`
- IA downloads: `Raw_Input/0110_Internet_Archive/SIM/`
- Family mapping: `config/ia_family_mapping.json`

## Implementation Tasks

### 1. Modify `scripts/ia_acquire.py`

#### Update `register_container_in_db()` signature
Change the `metadata` parameter to accept either a dict or an Item object:

```python
def register_container_in_db(
    identifier: str,
    metadata: Union[dict, Any],  # Changed from just Item/Any
    download_dir: Path,
    family_id: int,
    title_id: Optional[int] = None,
    source_system: str = 'ia'
) -> Optional[int]:
```

Add metadata normalization at the start of the function:
- If `metadata` has `.metadata` attribute → it's an Item object, extract it
- If `metadata` is a dict → use directly
- Otherwise → raise TypeError

Keep all other logic unchanged.

#### Add new function `reconstruct_metadata_from_local()`

Insert this function before `register_container_in_db()`:

```python
def reconstruct_metadata_from_local(
    identifier: str, 
    download_dir: Path,
    source_system: str = 'ia'
) -> dict:
    """
    Reconstruct metadata dictionary from locally downloaded IA item.
    
    Reads:
    - {identifier}_meta.json: Primary metadata
    - {identifier}_scandata.xml: Page count (parse with xml.etree.ElementTree)
    - Directory scan: Check for _jp2.zip, _djvu.xml, _hocr.html, .pdf, _scandata.xml
    
    Returns:
        dict matching structure of item.metadata from internetarchive library
        
    Raises:
        FileNotFoundError: If _meta.json missing
        ValueError: If metadata invalid
    """
```

Implementation requirements:
1. Load `{identifier}_meta.json` with error handling
2. Parse `{identifier}_scandata.xml` to get page count
3. Detect available files (set boolean flags)
4. Build `container_label` from metadata (similar to existing download logic)
5. Return dict with all fields needed by `register_container_in_db()`

### 2. Create `scripts/register_existing_downloads.py`

New standalone script for bulk registration.

**Required imports:**
```python
import sys
import argparse
from pathlib import Path
from typing import Optional, List, Tuple
import logging
from datetime import datetime

from ia_acquire import (
    get_db_connection,
    reconstruct_metadata_from_local,
    register_container_in_db
)
```

**Configuration constants:**
```python
BASE_PATH = Path(r"\\RaneyHQ\Michael\02_Projects\Historical_Journals_And_Books")
RAW_INPUT_IA = BASE_PATH / "Raw_Input" / "0110_Internet_Archive" / "SIM"
FAMILY_MAPPING_FILE = Path("config") / "ia_family_mapping.json"
```

**Functions to implement:**

1. `load_family_mapping() -> dict` - Load JSON mapping
2. `scan_family_directory(family_root: str) -> List[Path]` - Find all item directories with `_meta.json`
3. `is_already_registered(identifier: str, source_system: str = 'ia') -> bool` - Query database
4. `register_single_item(identifier: str, download_dir: Path, family_id: int, dry_run: bool = False) -> Tuple[bool, str]` - Register one item
5. `main()` - CLI entry point

**CLI arguments:**
```python
parser.add_argument('--family', required=True, help='Family root (e.g., American_Architect_family)')
parser.add_argument('--dry-run', action='store_true', help='Preview without database changes')
parser.add_argument('--log-dir', default='logs', help='Log directory')
parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
```

**Logging:**
- File: `logs/register_existing_YYYYMMDD_HHMMSS.log`
- Format: `%(asctime)s - %(levelname)s - %(message)s`
- Both file and console handlers

**Console output:**
```
Scanning family: American_Architect_family
Found 142 items

Processing: sim_americanarchitect_27_1890_01
  ✓ Registered (container_id: 1234)

Processing: sim_americanarchitect_27_1890_02
  ⊘ Already registered (container_id: 1235)

Summary:
  Total: 142
  Already registered: 38
  Newly registered: 101
  Failed: 3
```

**Error handling:**
- Each item in own try/except block
- Continue on error (don't stop batch)
- Log all errors to file
- Print failed count in summary

### 3. Create `docs/RETROACTIVE_REGISTRATION.md`

Brief documentation with:
- Overview and purpose
- Prerequisites (database access, NAS access)
- Usage examples
- Troubleshooting common issues

Example usage to include:
```bash
# Dry run (preview)
python scripts/register_existing_downloads.py --family American_Architect_family --dry-run

# Actually register
python scripts/register_existing_downloads.py --family American_Architect_family

# Verbose mode
python scripts/register_existing_downloads.py --family American_Architect_family --verbose
```

### 4. Update `CHANGELOG.md`

Add under `## [Unreleased]`:

```markdown
### Added
- Retroactive registration system for previously downloaded IA items
  - Modified `register_container_in_db()` to accept metadata dict or Item object
  - Added `reconstruct_metadata_from_local()` to rebuild metadata from local files
  - Created `scripts/register_existing_downloads.py` for bulk registration
  - Added `docs/RETROACTIVE_REGISTRATION.md` with usage guide

### Changed
- `ia_acquire.py::register_container_in_db()` now accepts `Union[dict, Any]` for metadata
```

## Commit Strategy

Use Conventional Commits with HJB scope prefix:

**Commit 1:**
```
feat(hjb/acquisition): support retroactive container registration

- Modify register_container_in_db() to accept metadata dict or Item object
- Add metadata normalization logic
- Maintains backward compatibility
```

**Commit 2:**
```
feat(hjb/acquisition): add metadata reconstruction from local files

- Implement reconstruct_metadata_from_local()
- Reads _meta.json, scandata.xml, scans directory
- Returns dict compatible with register_container_in_db()
```

**Commit 3:**
```
feat(hjb/acquisition): add bulk registration script

- Create scripts/register_existing_downloads.py
- Family-based scanning with dry-run support
- Duplicate detection and error handling
- Progress reporting and logging
```

**Commit 4:**
```
docs(hjb/acquisition): add retroactive registration guide

- Create RETROACTIVE_REGISTRATION.md
- Update CHANGELOG.md
```

## Key Requirements

1. **Backward compatibility**: Existing download workflow must work unchanged
2. **Transaction safety**: Each registration in own transaction
3. **Idempotency**: Safe to re-run (skip already-registered items)
4. **Error resilience**: One failure doesn't stop batch
5. **Comprehensive logging**: All operations logged to file

## Database Schema Reference

**`containers_t` fields for registration:**
- `source_system` = 'ia'
- `source_identifier` = IA identifier (unique with source_system)
- `source_url` = archive.org URL
- `family_id` = FK to publication_families_t
- `container_label` = human-readable name
- `total_pages` = from scandata.xml
- `has_jp2`, `has_djvu_xml`, `has_hocr`, `has_pdf`, `has_scandata` = boolean flags
- `raw_input_path` = NAS path to item directory
- `download_status` = 'complete' (for retroactive)
- `validation_status` = 'passed' (for retroactive)

**`processing_status_t` gets created with:**
- All stage flags = 0
- `pipeline_status` = 'pending'

## Success Criteria

After implementation:
1. ✓ Can run dry-run and see preview of what would be registered
2. ✓ Can register all items in a family with one command
3. ✓ Database contains containers with correct metadata
4. ✓ Re-running script skips already-registered items
5. ✓ Logs contain detailed information about all operations

## Files to Create/Modify

**Modified:**
- `scripts/ia_acquire.py`
- `CHANGELOG.md`

**Created:**
- `scripts/register_existing_downloads.py`
- `docs/RETROACTIVE_REGISTRATION.md`
