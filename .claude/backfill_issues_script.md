# Backfill Issues for Existing Containers

## Problem
Containers were registered before issue-creation logic was added. Need to create `issues_t` and `issue_containers_t` entries for these existing containers.

## Solution: Create Backfill Script

### Create `scripts/stage1/backfill_issues.py`

New standalone script to process existing containers and create their issues.

```python
#!/usr/bin/env python3
"""
Backfill issues_t records for containers that don't have them yet.

This is for containers registered before the issue-creation logic was added.
"""

import sys
import logging
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.stage1.ia_acquire import (
    get_db_connection,
    create_issue_from_parsed
)
from scripts.parsers.parse_american_architect_ia import (
    parse_american_architect_identifier
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)


def get_containers_without_issues(family_id: Optional[int] = None):
    """
    Get all containers that don't have issue_containers_t entries.
    
    Args:
        family_id: Optional filter by family
        
    Returns:
        List of (container_id, source_identifier, family_id, title_id) tuples
    """
    with get_db_connection() as conn:
        if not conn:
            return []
        
        cursor = conn.cursor(dictionary=True)
        
        # Find containers without issue_containers_t entries
        sql = """
            SELECT c.container_id, c.source_identifier, c.family_id, c.title_id
            FROM containers_t c
            LEFT JOIN issue_containers_t ic ON c.container_id = ic.container_id
            WHERE ic.issue_container_id IS NULL
              AND c.source_system = 'ia'
        """
        
        params = []
        if family_id:
            sql += " AND c.family_id = %s"
            params.append(family_id)
        
        cursor.execute(sql, params)
        results = cursor.fetchall()
        cursor.close()
        
        return results


def create_issue_and_link(container_id: int, source_identifier: str, 
                          family_id: int, title_id: Optional[int],
                          dry_run: bool = False) -> bool:
    """
    Create issue from identifier and link to container.
    
    Returns:
        True if successful, False otherwise
    """
    # Parse identifier
    parsed = parse_american_architect_identifier(source_identifier)
    if not parsed:
        log.warning(f"Could not parse identifier: {source_identifier}")
        return False
    
    log.info(f"Parsed {source_identifier}: {parsed.issue_label}, Vol {parsed.volume_label}")
    
    if dry_run:
        log.info(f"  [DRY RUN] Would create issue: {parsed.canonical_issue_key}")
        return True
    
    # Create issue
    issue_id = create_issue_from_parsed(
        parsed=parsed,
        family_id=family_id,
        title_id=title_id,
        container_id=container_id
    )
    
    if not issue_id:
        log.error(f"Failed to create issue for {source_identifier}")
        return False
    
    # Create issue_containers_t mapping
    with get_db_connection() as conn:
        if not conn:
            return False
        
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO issue_containers_t 
                (issue_id, container_id, is_preferred, is_complete)
                VALUES (%s, %s, 1, 1)
            """, (issue_id, container_id))
            
            conn.commit()
            log.info(f"  ✓ Created issue {issue_id} and linked to container {container_id}")
            return True
            
        except Exception as e:
            log.error(f"Failed to create issue_containers_t mapping: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Backfill issues_t for existing containers'
    )
    parser.add_argument('--family-id', type=int, 
                       help='Optional: Only process this family_id')
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview without database changes')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Get containers without issues
    log.info("Finding containers without issues...")
    containers = get_containers_without_issues(args.family_id)
    
    if not containers:
        log.info("No containers found needing issues. All done!")
        return 0
    
    log.info(f"Found {len(containers)} containers without issues")
    
    if args.dry_run:
        log.info("\n=== DRY RUN MODE ===\n")
    
    # Process each
    success_count = 0
    fail_count = 0
    
    for container in containers:
        container_id = container['container_id']
        source_identifier = container['source_identifier']
        family_id = container['family_id']
        title_id = container['title_id']
        
        log.info(f"\nProcessing container {container_id}: {source_identifier}")
        
        success = create_issue_and_link(
            container_id=container_id,
            source_identifier=source_identifier,
            family_id=family_id,
            title_id=title_id,
            dry_run=args.dry_run
        )
        
        if success:
            success_count += 1
        else:
            fail_count += 1
    
    # Summary
    log.info("\n" + "="*60)
    log.info("SUMMARY")
    log.info("="*60)
    log.info(f"Total containers: {len(containers)}")
    log.info(f"Successfully processed: {success_count}")
    log.info(f"Failed: {fail_count}")
    
    if args.dry_run:
        log.info("\nThis was a dry run. Run without --dry-run to apply changes.")
    
    return 0 if fail_count == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
```

## Usage

### 1. First apply the database connection fix
```bash
claude-code "Apply the fix in .claude/fix_database_connection.md, commit and push"
```

### 2. Create the backfill script
```bash
claude-code "Create the backfill script described in .claude/backfill_issues_script.md, commit and push"
```

### 3. Run the backfill

```bash
# Dry run first
python scripts/stage1/backfill_issues.py --dry-run

# For specific family only
python scripts/stage1/backfill_issues.py --family-id 1 --dry-run

# Actually create the issues
python scripts/stage1/backfill_issues.py --family-id 1

# Verbose mode
python scripts/stage1/backfill_issues.py --family-id 1 --verbose
```

## Expected Output

```
Finding containers without issues...
Found 23 containers without issues

Processing container 1: sim_american-architect-and-architecture_1876-01-01_1_1
Parsed sim_american-architect-and-architecture_1876-01-01_1_1: Issue 1, Vol V1
  ✓ Created issue 1 and linked to container 1

Processing container 2: sim_american-architect-and-architecture_1876-01-08_1_2
Parsed sim_american-architect-and-architecture_1876-01-08_1_2: Issue 2, Vol V1
  ✓ Created issue 2 and linked to container 2

...

============================================================
SUMMARY
============================================================
Total containers: 23
Successfully processed: 23
Failed: 0
```

## Verification

After running, verify:

```sql
-- Should now be 0 (all containers have issues)
SELECT COUNT(*) 
FROM containers_t c
LEFT JOIN issue_containers_t ic ON c.container_id = ic.container_id
WHERE ic.issue_container_id IS NULL
  AND c.source_system = 'ia'
  AND c.family_id = 1;

-- Check the created issues
SELECT i.issue_id, i.canonical_issue_key, i.volume_label, i.issue_date_start
FROM issues_t i
WHERE i.family_id = 1
ORDER BY i.year_published, i.volume_sort, i.issue_sort
LIMIT 10;

-- Check the mappings
SELECT ic.issue_id, ic.container_id, c.source_identifier, i.canonical_issue_key
FROM issue_containers_t ic
JOIN containers_t c ON ic.container_id = c.container_id
JOIN issues_t i ON ic.issue_id = i.issue_id
WHERE c.family_id = 1
LIMIT 10;
```

## Commit Message

```
feat(hjb/acquisition): add backfill script for existing containers

- Create backfill_issues.py to process containers without issues
- Parses identifier and creates issues_t + issue_containers_t
- Supports dry-run and family filtering
- Handles containers registered before issue-creation logic added
```

## Notes

- **Idempotent**: Uses LEFT JOIN to find containers without issues, won't duplicate
- **Safe to re-run**: If issue already exists (by canonical_issue_key), it will be reused
- **Family-specific**: Can limit to one family with `--family-id`
- **Dry run**: Always test with `--dry-run` first
