# Refactoring Plan: Extract Task Handlers from hjb_watcher.py

## Current State

`scripts/watcher/hjb_watcher.py` contains three inline task handlers:

| Handler | Lines | Purpose |
|---------|-------|---------|
| `task_stage1_generate_ia_tasks()` | 340-466 | Invokes `generate_ia_tasks.py` via subprocess |
| `task_stage1_inventory()` | 510-665 | Generates CSV inventory of NAS directories |
| `task_stage1_ia_download()` | 669-733 | Downloads from Internet Archive via `ia_acquire.py` |

## Proposed Structure

```
scripts/
├── stage1/
│   ├── generate_ia_tasks.py      # EXISTS - add execute_from_manifest()
│   ├── generate_inventory.py     # NEW - extract from watcher
│   └── ia_acquire.py             # EXISTS - add execute_from_manifest()
└── watcher/
    └── hjb_watcher.py            # REFACTOR - import handlers
```

---

## Changes Per File

### 1. `scripts/stage1/generate_ia_tasks.py` (MODIFY)

**Add:** `execute_from_manifest(manifest, task_id, flags_root)` function

```python
def execute_from_manifest(
    manifest: dict,
    task_id: str,
    flags_root: Path,
) -> tuple[list[str], dict]:
    """
    Execute task from watcher manifest.

    Args:
        manifest: Task manifest dict with 'parameters' key
        task_id: Unique task identifier
        flags_root: Path to flags directory

    Returns:
        (outputs, metrics) tuple
    """
    # Extract and validate parameters from manifest
    # Call existing main logic
    # Return outputs and metrics
```

**Rationale:** The current handler in watcher.py calls this script via subprocess. We'll keep that approach but wrap it in a clean function that can be imported.

---

### 2. `scripts/stage1/generate_inventory.py` (NEW)

**Create:** New file with inventory logic extracted from watcher

```python
#!/usr/bin/env python3
"""
HJB Stage 1 - Inventory Generation

Generates CSV inventory of files in specified directories.
Can be run standalone or called from hjb_watcher.py.

Usage (standalone):
    python generate_inventory.py --roots "\\\\NAS\\path1" "\\\\NAS\\path2" \\
        --output-dir ./output --include-sha256

Usage (from watcher):
    Called via execute_from_manifest() with task manifest
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import time
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _matches_any_glob(path_str: str, globs: List[str]) -> bool:
    """Windows-friendly glob matching against forward-slash-normalized paths."""
    norm = path_str.replace("\\", "/")
    return any(fnmatch(norm, g) for g in globs)


def generate_inventory(
    roots: List[str],
    output_dir: Path,
    task_id: str,
    include_sha256: bool = False,
    include_globs: Optional[List[str]] = None,
    exclude_globs: Optional[List[str]] = None,
    max_files: int = 100000,
    max_seconds: int = 1800,
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Generate CSV inventory of files.

    Returns:
        (outputs, metrics) tuple
    """
    # ... inventory logic from watcher ...


def execute_from_manifest(
    manifest: dict,
    task_id: str,
    flags_root: Path,
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Execute inventory task from watcher manifest.

    Manifest format:
    {
        "payload": {
            "roots": ["\\\\NAS\\path1", "\\\\NAS\\path2"],
            "include_sha256": false,
            "include_globs": ["*.pdf", "*.jpg"],
            "exclude_globs": ["*/_tmp/*"],
            "max_files": 100000,
            "max_seconds": 1800
        }
    }
    """
    # Extract parameters from manifest
    # Call generate_inventory()
    # Return results


def main() -> int:
    """CLI entry point for standalone usage."""
    # argparse-based CLI
    pass


if __name__ == "__main__":
    raise SystemExit(main())
```

---

### 3. `scripts/stage1/ia_acquire.py` (MODIFY)

**Add:** `execute_from_manifest(manifest, task_id, flags_root)` function

```python
def execute_from_manifest(
    manifest: dict,
    task_id: str,
    flags_root: Path,
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Execute IA download task from watcher manifest.

    Manifest format:
    {
        "parameters": {
            "ia_identifier": "sim_american-architect_1900-01-01_1_1",
            "family": "American_Architect_family"
        }
    }

    Returns:
        (outputs, metrics) tuple
    """
    # Extract parameters
    # Call download_one()
    # Return results
```

**Note:** This already has `download_one()` which does the actual work. We just need a manifest adapter.

---

### 4. `scripts/watcher/hjb_watcher.py` (REFACTOR)

**Remove:**
- `task_stage1_generate_ia_tasks()` (lines 340-466)
- `task_stage1_inventory()` (lines 510-665)
- `task_stage1_ia_download()` (lines 669-733)
- `_matches_any_glob()` helper (lines 501-507)

**Add:** Imports and delegation

```python
# At top of file, after other imports
from scripts.stage1 import generate_ia_tasks
from scripts.stage1 import generate_inventory
from scripts.stage1 import ia_acquire


def execute_manifest_task(
    manifest: Dict[str, Any],
    task_id: str,
    task_type: str,
    attempt: int,
    state_root: Path,
    flags_root: Path,
    watcher_id: str,
) -> Tuple[List[str], Dict[str, Any]]:
    """Execute a manifest-driven JSON flag."""

    if task_type == "noop":
        # ... existing noop logic ...
        return [str(marker)], {"noop": True}

    if task_type == "stage1.inventory":
        return generate_inventory.execute_from_manifest(manifest, task_id, flags_root)

    if task_type == "stage1.ia_download":
        return ia_acquire.execute_from_manifest(manifest, task_id, flags_root)

    if task_type == "stage1.generate_ia_tasks":
        return generate_ia_tasks.execute_from_manifest(manifest, task_id, flags_root)

    raise ValueError(f"Unknown task_type: {task_type}")
```

---

## Benefits

1. **Separation of Concerns**: Task logic lives with related scripts
2. **Testability**: Each handler can be unit tested independently
3. **Reusability**: Handlers can be called from CLI or watcher
4. **Maintainability**: Changes to task logic don't require touching watcher
5. **Reduced Complexity**: `hjb_watcher.py` drops from ~1020 lines to ~750 lines

---

## File Size Impact

| File | Before | After |
|------|--------|-------|
| `hjb_watcher.py` | ~1020 lines | ~750 lines |
| `generate_ia_tasks.py` | ~253 lines | ~320 lines |
| `generate_inventory.py` | N/A (new) | ~200 lines |
| `ia_acquire.py` | ~731 lines | ~780 lines |

---

## Migration Steps

1. Create `scripts/stage1/generate_inventory.py` with extracted logic
2. Add `execute_from_manifest()` to `generate_ia_tasks.py`
3. Add `execute_from_manifest()` to `ia_acquire.py`
4. Update `hjb_watcher.py` to import and delegate
5. Test each task type end-to-end
6. Commit changes

---

## Approval Required

Please confirm this plan before I implement:

- [ ] Structure looks correct
- [ ] Function signatures are acceptable
- [ ] Any naming changes needed
- [ ] Additional requirements?
