#!/usr/bin/env python3
"""
Backfill issues_t records for containers that don't have them yet.

This is for containers registered before the issue-creation logic was added.

Usage:
    # Dry run first
    python scripts/stage1/backfill_issues.py --dry-run

    # For specific family only
    python scripts/stage1/backfill_issues.py --family-id 1 --dry-run

    # Actually create the issues
    python scripts/stage1/backfill_issues.py --family-id 1

    # Verbose mode
    python scripts/stage1/backfill_issues.py --family-id 1 --verbose
"""

import sys
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.common import hjb_db
from scripts.stage1.ia_acquire import create_issue_from_parsed
from scripts.stage1.parse_american_architect_ia import parse_american_architect_identifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)


def get_containers_without_issues(family_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Get all containers that don't have issue_containers_t entries.

    Args:
        family_id: Optional filter by family

    Returns:
        List of container dicts with container_id, source_identifier, family_id, title_id
    """
    with hjb_db.get_connection() as conn:
        if not conn:
            return []

        cursor = conn.cursor(dictionary=True)

        # Find containers without issue_containers_t entries
        sql = """
            SELECT c.container_id, c.source_identifier, c.family_id, c.title_id
            FROM containers_t c
            LEFT JOIN issue_containers_t ic ON c.container_id = ic.container_id
            WHERE ic.issue_container_id IS NULL
              AND c.source_system = 'internet_archive'
        """

        params = []
        if family_id:
            sql += " AND c.family_id = %s"
            params.append(family_id)

        cursor.execute(sql, params)
        results = cursor.fetchall()
        cursor.close()

        return results


def create_issue_and_link(
    container_id: int,
    source_identifier: str,
    family_id: int,
    title_id: Optional[int],
    dry_run: bool = False
) -> bool:
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
        # Get family_code for display
        family_code = None
        with hjb_db.get_connection() as conn:
            if conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    "SELECT family_code FROM publication_families_t WHERE family_id = %s",
                    (family_id,)
                )
                result = cursor.fetchone()
                if result:
                    family_code = result['family_code']
                cursor.close()

        log.info(f"  [DRY RUN] Would create issue: {parsed.canonical_issue_key(family_code)}")
        return True

    # Create issue (this also handles the issue_containers_t mapping internally now)
    issue_id = create_issue_from_parsed(
        parsed=parsed,
        family_id=family_id,
        title_id=title_id,
    )

    if not issue_id:
        log.error(f"Failed to create issue for {source_identifier}")
        return False

    # Create issue_containers_t mapping
    with hjb_db.get_connection() as conn:
        if not conn:
            return False

        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO issue_containers_t
                (issue_id, container_id, is_preferred, is_complete)
                VALUES (%s, %s, 1, 1)
                ON DUPLICATE KEY UPDATE is_preferred = 1
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


def main() -> int:
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
    log.info("\n" + "=" * 60)
    log.info("SUMMARY")
    log.info("=" * 60)
    log.info(f"Total containers: {len(containers)}")
    log.info(f"Successfully processed: {success_count}")
    log.info(f"Failed: {fail_count}")

    if args.dry_run:
        log.info("\nThis was a dry run. Run without --dry-run to apply changes.")

    return 0 if fail_count == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
