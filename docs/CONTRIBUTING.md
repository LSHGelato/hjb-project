# Contributing to HJB Project

Thank you for contributing to the Historical Journals & Books (HJB) Project! This document provides guidelines for development practices, commit messages, and code standards.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Commit Message Guidelines](#commit-message-guidelines)
- [Code Standards](#code-standards)
- [Testing](#testing)
- [Documentation](#documentation)

---

## Getting Started

### Prerequisites

- Python 3.8+
- Access to RaneyHQ NAS (\\RaneyHQ\Michael)
- MySQL client (for database work)
- Git installed and configured

### Repository Setup

```powershell
# Clone the repository
git clone https://github.com/LSHGelato/hjb-project.git
cd hjb-project

# Install dependencies
pip install -r requirements.txt

# Copy example config
cp config/config.example.yaml config/config.yaml

# Edit config with your paths and credentials
notepad config/config.yaml
```

### Environment Variables

Set these on your development machine:

```powershell
# Database credentials (use app user, not admin)
setx HJB_DB_HOST "your.mysql.host" /M
setx HJB_DB_USER "raneywor_hjb_app" /M
setx HJB_DB_PASSWORD "your_password_here" /M
setx HJB_DB_NAME "raneywor_hjbproject" /M

# Optional: custom paths
setx HJB_REPO_ROOT "C:\hjb-project" /M
```

---

## Development Workflow

### Branching Strategy

- `main` - Production-ready code only
- `dev` - Integration branch for feature development
- `feature/<name>` - Feature branches (branch from `dev`)
- `fix/<name>` - Bug fix branches (branch from `main` or `dev`)
- `docs/<name>` - Documentation updates

### Creating a Feature

```bash
# Create feature branch from dev
git checkout dev
git pull origin dev
git checkout -b feature/stage2-hocr-parser

# Make changes, commit frequently
git add scripts/stage2/parse_hocr.py
git commit -m "feat(stage2): Add HOCR parser skeleton"

# Push to remote
git push origin feature/stage2-hocr-parser

# Create pull request to dev (via GitHub)
```

### Before Committing

1. **Test your changes** - Run relevant test scripts
2. **Check for errors** - Use linting tools if available
3. **Update documentation** - If behavior changes, update docs
4. **Review diff** - `git diff` to verify only intended changes
5. **Write good commit message** - See guidelines below

---

## Commit Message Guidelines

We use **Conventional Commits** format for clear, searchable history.

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type Prefixes

- `feat` - New feature
- `fix` - Bug fix
- `refactor` - Code restructuring (no behavior change)
- `docs` - Documentation only
- `test` - Adding or updating tests
- `chore` - Maintenance (dependencies, config)
- `perf` - Performance improvement
- `style` - Code formatting (no logic change)
- `build` - Build system changes
- `ci` - CI/CD configuration

### Scope Values

Use the most specific scope that applies:

- `stage1` - Stage 1 (Ingestion & Validation)
- `stage2` - Stage 2 (OCR & Segmentation)
- `stage3` - Stage 3 (Canonicalization & Deduplication)
- `stage4` - Stage 4 (Publication & Export)
- `watcher` - Watcher orchestration system
- `ops` - Operational tools (doctor, supervisor)
- `db` - Database schema or hjb_db module
- `config` - Configuration files
- `docs` - Documentation
- `common` - Shared utilities

### Subject Line

- Max 72 characters
- Imperative mood ("Add" not "Added" or "Adds")
- No period at end
- Capitalize first word after scope
- Be specific and descriptive

### Body (Optional but Recommended)

- Wrap at 72 characters
- Explain WHAT and WHY, not HOW
- Use bullet points for multiple changes
- Reference blueprint sections when applicable
- Leave blank line between subject and body

### Footer (Optional)

- `Refs:` - Related documentation or blueprint sections
- `Fixes:` - Bug fixes (use issue number if applicable)
- `Breaking:` - Breaking changes (describe impact)
- `Co-authored-by:` - Collaborators

---

## Examples

### Simple Feature

```
feat(stage1): Add retry logic for IA download failures

Implement exponential backoff retry for transient network errors
during Internet Archive downloads.

- Max 3 retries with 1.5s base delay
- Handles connection timeouts and 503 errors
- Logs each retry attempt with error details

Refs: HJB Blueprint Section 5.2 (Stage 1 Ingestion)
```

### Bug Fix

```
fix(watcher): Prevent duplicate task claiming in multi-watcher setup

Race condition allowed two watchers to claim same task when polling
simultaneously. Now uses atomic file move for claiming.

- Move operation fails if file already moved
- Add claimed_by field to task JSON
- Log warning when claim attempt fails

Fixes: #73
```

### Database Migration

```
feat(db): Add work_authors_t table for multi-author support

Create junction table to support articles with multiple authors,
replacing single author VARCHAR field in works_t.

Migration changes:
- New table: work_authors_t (work_id, author_name, author_order)
- Foreign key to works_t with CASCADE delete
- Index on work_id for fast lookups
- Migration: migrations/003_add_work_authors.sql
- Rollback: migrations/rollback/rollback_003_add_work_authors.sql

hjb_db.py changes:
- Add insert_work_author() function
- Add get_work_authors() query helper
- Update insert_work() to accept authors list

Breaking: Works created before this migration will have NULL authors
until backfilled. Run backfill script after deployment.

Refs: HJB Blueprint Section 4 (Database Schema)
```

### Documentation Update

```
docs(setup): Add Windows Task Scheduler setup guide

Create detailed guide for configuring opportunistic watcher on
OrionMega with screenshots and troubleshooting steps.

- Step-by-step Task Scheduler configuration
- Trigger setup for workstation lock/idle
- Common errors and solutions
- Security considerations for credentials

Refs: HJB Blueprint Appendix D
```

### Refactoring

```
refactor(common): Extract validation logic into reusable module

Move file validation functions from ia_acquire.py into new
common/validators.py for use across all stage scripts.

- No behavior change
- Improves testability
- Enables code reuse in stage2/stage3
- All existing tests still pass
```

### Configuration Change

```
chore(config): Update default OCR engine to Tesseract 5.3

Update config.example.yaml to reference Tesseract 5.3 with LSTM
neural network mode for improved accuracy.

- Change tesseract_version: "5.3.0"
- Enable LSTM mode by default
- Add comment about legacy mode for old scans
- Update installation instructions in README
```

### Multi-Scope Change

```
feat(db,stage1,stage2): Complete database integration for Stages 1-2

Integrate database tracking across acquisition and OCR stages for
end-to-end container lifecycle management.

Stage 1 (ia_acquire.py):
- Register containers_t on download
- Populate file availability flags (has_jp2, has_hocr, etc.)
- Auto-create publication_families_t records
- Mark stage1_ingestion_complete

Stage 2 (ocr_runner.py - new):
- Store OCR text in pages_t
- Update containers_t.total_pages after processing
- Mark stage2_ocr_complete
- Track OCR confidence scores

Database (hjb_db.py):
- Add insert_page() function
- Add update_container_pages() helper
- Add bulk_insert_pages() for performance
- Optimize indexes on containers_t.download_status

Testing:
- End-to-end test with 5 IA items successful
- All containers properly linked to pages
- Stage completion flags working correctly
- No memory leaks in bulk operations

Refs: HJB Blueprint Sections 4-5 (Database & Pipeline)
```

---

## Commit Message Anti-Patterns

❌ **Avoid these:**

```
# Too vague
Update files

# Past tense
Added database support

# No scope
feat: new thing

# Too long subject
feat(stage1): Add comprehensive retry logic with exponential backoff and configurable delays for handling transient network failures

# No context in body
fix(watcher): fix bug

# Mixing unrelated changes
feat(stage1,stage2,stage3,stage4): various updates
```

✅ **Do this instead:**

```
# Clear and specific
feat(stage1): Add exponential backoff for IA downloads

# Present tense
feat(db): Add database integration

# With scope
feat(stage1): Add retry logic

# Concise subject, details in body
feat(stage1): Add retry logic for IA downloads

Implement exponential backoff for network failures with
configurable max retries and base delay parameters.

# Clear purpose
fix(watcher): Prevent race condition in task claiming

File move operation now atomic to prevent multiple watchers
from claiming the same task simultaneously.

# Focused change
feat(stage1): Add database integration to ia_acquire.py
```

---

## Code Standards

### Python Style

- Follow **PEP 8** style guide
- Use **type hints** for function signatures
- Maximum line length: **100 characters** (not 80, to accommodate paths)
- Use **docstrings** for all public functions
- Prefer **explicit** over implicit

### File Organization

```python
#!/usr/bin/env python3
"""
Module-level docstring describing purpose.

Detailed description of what this module does,
design decisions, and usage examples.
"""

# Standard library imports
import os
import sys
from pathlib import Path

# Third-party imports
import internetarchive

# Local imports
from scripts.common import hjb_db

# Constants
DEFAULT_TIMEOUT = 30

# Main code
def main():
    pass

if __name__ == "__main__":
    raise SystemExit(main())
```

### Function Documentation

```python
def register_container_in_db(
    row: IaRow,
    dest_dir: Path,
    downloaded_files: List[str],
    download_status: str,
) -> Optional[int]:
    """
    Register downloaded container in MySQL database.
    
    Creates or updates containers_t record with file availability flags,
    links to publication family, and initializes processing status.
    
    Args:
        row: IaRow containing collection, family, and identifier
        dest_dir: Path to downloaded files directory
        downloaded_files: List of successfully downloaded filenames
        download_status: Status string ('ok', 'error', etc.)
    
    Returns:
        container_id if successful, None on error
        
    Raises:
        None - errors are logged and return None for graceful degradation
        
    Example:
        >>> row = IaRow("SIM", "American_Architect", "sim_aa_1890_01_01")
        >>> container_id = register_container_in_db(row, Path("/data"), ["file.pdf"], "ok")
        >>> print(container_id)
        42
    """
    # Implementation
```

### Error Handling

```python
# Good: Specific exception handling with context
try:
    container_id = hjb_db.insert_container(**params)
except mysql.connector.Error as e:
    eprint(f"[DB ERROR] Failed to insert container: {e}")
    return None
except Exception as e:
    eprint(f"[ERROR] Unexpected error in register_container: {type(e).__name__}: {e}")
    return None

# Bad: Bare except or overly broad
try:
    container_id = hjb_db.insert_container(**params)
except:  # Don't do this
    pass
```

### Logging

```python
# Use consistent prefixes for log levels
print(f"[INFO] Starting IA acquisition for {len(items)} items")
print(f"[DB] Registered container: container_id={container_id}")
eprint(f"[WARNING] Missing jp2.zip for {identifier}")
eprint(f"[ERROR] Failed to download: {error_msg}")
eprint(f"[DB ERROR] Database operation failed: {error_msg}")
```

### Path Handling

```python
# Good: Use pathlib, resolve paths explicitly
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
dest_dir = repo_root / "01_Research" / "Historical_Journals_Inputs"
dest_dir.mkdir(parents=True, exist_ok=True)

# Bad: String concatenation, no resolution
import os
dest_dir = os.path.join(repo_root, "01_Research", "Historical_Journals_Inputs")
```

---

## Testing

### Manual Testing

Before committing code that interacts with the pipeline:

1. **Test without database** (if applicable):
   ```powershell
   python .\scripts\stage1\ia_acquire.py --list test.txt --no-database
   ```

2. **Test with database** on a small dataset:
   ```powershell
   python .\scripts\stage1\ia_acquire.py --list test_small.txt --workers 1
   ```

3. **Verify database records** in phpMyAdmin:
   - Check containers_t for new records
   - Verify foreign keys are correct
   - Confirm flags are set properly

4. **Check for side effects**:
   - No files left in unexpected locations
   - No orphaned database records
   - Proper cleanup of temporary files

### Test Data

Keep small test datasets in `config/test/`:

```
config/
└── test/
    ├── test_single_item.txt      # 1 item for quick tests
    ├── test_small_batch.txt      # 5 items for integration tests
    └── test_edge_cases.txt       # Known problematic items
```

---

## Documentation

### When to Update Documentation

Update documentation when you:

- Add a new feature or script
- Change command-line arguments
- Modify configuration options
- Change database schema
- Fix a bug that was caused by unclear docs
- Add new dependencies

### Documentation Locations

- **README.md** - Project overview, quick start
- **docs/** - Detailed guides and architecture
- **Code docstrings** - Function/class documentation
- **config/config.example.yaml** - Config option descriptions
- **migrations/** - SQL migration comments

### Documentation Style

```markdown
# Use clear, hierarchical headers

## Main Section

Brief introduction to the section.

### Subsection

Specific details with examples.

#### Sub-subsection

Very specific details.

**Use code blocks with syntax highlighting:**

```python
# Python example
def example():
    return "Hello"
```

```powershell
# PowerShell example
Get-Process | Where-Object {$_.Name -eq "python"}
```

**Use tables for comparisons:**

| Feature | Stage 1 | Stage 2 |
|---------|---------|---------|
| OCR     | No      | Yes     |
| DB      | Yes     | Yes     |

**Use admonitions for important notes:**

> **Note:** This feature requires database access.

> **Warning:** This operation cannot be undone.

> **Important:** Run migrations before deploying code.
```

---

## Database Changes

### Creating Migrations

1. **Create forward migration:**
   ```sql
   -- migrations/004_add_quality_score.sql
   -- Add quality_score column to containers_t
   -- Author: Your Name
   -- Date: 2026-01-20
   
   ALTER TABLE containers_t 
   ADD COLUMN quality_score DECIMAL(5,2) DEFAULT NULL
   COMMENT 'OCR quality score (0-100) for canonical selection';
   
   -- Update schema version
   INSERT INTO schema_version_t (version_number, migration_name, applied_at)
   VALUES (4, '004_add_quality_score', NOW());
   ```

2. **Create rollback migration:**
   ```sql
   -- migrations/rollback/rollback_004_add_quality_score.sql
   -- Rollback: Remove quality_score column
   
   ALTER TABLE containers_t DROP COLUMN quality_score;
   
   DELETE FROM schema_version_t WHERE version_number = 4;
   ```

3. **Update hjb_db.py** if needed (new queries, etc.)

4. **Test migration:**
   ```bash
   # Apply
   mysql -u admin < migrations/004_add_quality_score.sql
   
   # Verify
   mysql -u admin -e "DESCRIBE containers_t"
   
   # Rollback test
   mysql -u admin < migrations/rollback/rollback_004_add_quality_score.sql
   ```

5. **Document in commit message** (see examples above)

---

## Pull Request Guidelines

### Before Opening PR

- [ ] All commits follow commit message guidelines
- [ ] Code tested locally (including database operations)
- [ ] Documentation updated if needed
- [ ] No secrets or credentials in code
- [ ] Config changes noted in PR description

### PR Title Format

Use same format as commit messages:

```
feat(stage2): Add HOCR parser for OCR extraction
```

### PR Description Template

```markdown
## Summary
Brief description of what this PR does and why.

## Changes
- Bullet list of key changes
- Organized by file or component
- Include any breaking changes

## Testing
- [ ] Tested without database
- [ ] Tested with database on small dataset
- [ ] Verified database records created correctly
- [ ] No errors in logs

## Documentation
- [ ] README updated (if applicable)
- [ ] Docstrings added/updated
- [ ] Config example updated (if new options)

## Database Changes
- [ ] Migration scripts created (if applicable)
- [ ] Rollback scripts created
- [ ] hjb_db.py updated (if needed)

## Refs
- HJB Blueprint Section X.Y
- Issue #123 (if applicable)
```

---

## Questions?

- Check the [HJB Blueprint](docs/HJB_Blueprint.md) for architecture details
- Review existing code for patterns and examples
- Ask in GitHub Discussions or open an issue

---

## License

This project is private and proprietary. All contributions become property of the project maintainer.
