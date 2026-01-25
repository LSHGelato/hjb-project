#!/usr/bin/env python3
"""
HJB QA - Apply Operator Corrections to Database

Purpose:
  - Safe templates for common operator corrections
  - Prevent accidental data corruption (with confirmations)
  - Log all changes for audit trail
  - Support corrections identified during QC review

Corrections Supported:
  - Mark pages as manually verified
  - Update page types (article, advertisement, plate, etc.)
  - Mark pages as spreads (2-page images)
  - Merge works
  - Split works

Usage:
  # Mark container as verified
  python scripts/qa/apply_operator_corrections.py --container-id 1 --mark-verified

  # Update page type
  python scripts/qa/apply_operator_corrections.py --page-ids 5 6 7 --page-type plate

  # Mark pages as spread
  python scripts/qa/apply_operator_corrections.py --spread 10 11 12

  # Interactive mode
  python scripts/qa/apply_operator_corrections.py --interactive
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.common import hjb_db
import mysql.connector

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('corrections.log'),
    ]
)
logger = logging.getLogger(__name__)


# =============================================================================
# Correction Functions
# =============================================================================

def mark_pages_verified(
    db_conn: Any,
    container_id: int,
    page_ids: Optional[List[int]] = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Mark pages as manually verified.

    Args:
        db_conn: Database connection
        container_id: Container ID (required)
        page_ids: Specific page IDs (if None, all in container)
        dry_run: If True, don't execute

    Returns:
        Result dictionary
    """
    result = {
        'operation': 'mark_verified',
        'container_id': container_id,
        'rows_affected': 0,
        'error': None,
    }

    try:
        cursor = db_conn.cursor()

        if page_ids:
            # Mark specific pages
            placeholders = ','.join(['%s'] * len(page_ids))
            query = f"""
                UPDATE pages_t
                SET is_manually_verified = 1, updated_at = NOW()
                WHERE page_id IN ({placeholders})
                AND container_id = %s
            """
            params = page_ids + [container_id]
            logger.info(f"Marking {len(page_ids)} specific pages as verified")
        else:
            # Mark all pages in container
            query = """
                UPDATE pages_t
                SET is_manually_verified = 1, updated_at = NOW()
                WHERE container_id = %s
            """
            params = [container_id]
            logger.info(f"Marking all pages in container {container_id} as verified")

        if dry_run:
            logger.info("[DRY RUN] Would execute:")
            logger.info(f"  {query % tuple(params)}")
            result['rows_affected'] = 0
        else:
            cursor.execute(query, params)
            db_conn.commit()
            result['rows_affected'] = cursor.rowcount
            logger.info(f"Marked {cursor.rowcount} pages as verified")

        cursor.close()
        return result

    except mysql.connector.Error as e:
        result['error'] = f"Database error: {e}"
        logger.error(result['error'])
        db_conn.rollback()
        return result


def update_page_types(
    db_conn: Any,
    page_ids: List[int],
    new_type: str,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Update page_type for given pages.

    Args:
        db_conn: Database connection
        page_ids: List of page IDs
        new_type: New page type (enum: content, cover, index, toc, advertisement, plate, blank, other)
        dry_run: If True, don't execute

    Returns:
        Result dictionary
    """
    result = {
        'operation': 'update_page_type',
        'page_ids': page_ids,
        'new_type': new_type,
        'rows_affected': 0,
        'error': None,
    }

    # Validate page type
    valid_types = ['content', 'cover', 'index', 'toc', 'advertisement', 'plate', 'blank', 'other']
    if new_type not in valid_types:
        result['error'] = f"Invalid page_type: {new_type}. Must be one of: {valid_types}"
        logger.error(result['error'])
        return result

    try:
        cursor = db_conn.cursor()

        placeholders = ','.join(['%s'] * len(page_ids))
        query = f"""
            UPDATE pages_t
            SET page_type = %s, updated_at = NOW()
            WHERE page_id IN ({placeholders})
        """
        params = [new_type] + page_ids

        logger.info(f"Updating {len(page_ids)} pages to type '{new_type}'")

        if dry_run:
            logger.info("[DRY RUN] Would execute:")
            logger.info(f"  UPDATE pages_t SET page_type = '{new_type}' WHERE page_id IN ({placeholders})")
            result['rows_affected'] = len(page_ids)
        else:
            cursor.execute(query, params)
            db_conn.commit()
            result['rows_affected'] = cursor.rowcount
            logger.info(f"Updated {cursor.rowcount} pages")

        cursor.close()
        return result

    except mysql.connector.Error as e:
        result['error'] = f"Database error: {e}"
        logger.error(result['error'])
        db_conn.rollback()
        return result


def mark_spread(
    db_conn: Any,
    page_id_1: int,
    page_id_2: int,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Mark two pages as a spread (2-page image).

    Args:
        db_conn: Database connection
        page_id_1: First page ID
        page_id_2: Second page ID
        dry_run: If True, don't execute

    Returns:
        Result dictionary
    """
    result = {
        'operation': 'mark_spread',
        'page_id_1': page_id_1,
        'page_id_2': page_id_2,
        'rows_affected': 0,
        'error': None,
    }

    try:
        cursor = db_conn.cursor()

        # Mark both pages as spreads and link them
        query1 = """
            UPDATE pages_t
            SET is_spread = 1, is_spread_with = %s, updated_at = NOW()
            WHERE page_id = %s
        """

        logger.info(f"Marking pages {page_id_1} and {page_id_2} as spread")

        if dry_run:
            logger.info("[DRY RUN] Would mark pages as spread:")
            logger.info(f"  Page {page_id_1} <-> Page {page_id_2}")
            result['rows_affected'] = 2
        else:
            # Update page 1
            cursor.execute(query1, (page_id_2, page_id_1))
            db_conn.commit()

            # Update page 2
            cursor.execute(query1, (page_id_1, page_id_2))
            db_conn.commit()

            result['rows_affected'] = 2
            logger.info(f"Marked spread: {page_id_1} <-> {page_id_2}")

        cursor.close()
        return result

    except mysql.connector.Error as e:
        result['error'] = f"Database error: {e}"
        logger.error(result['error'])
        db_conn.rollback()
        return result


def unmark_spread(
    db_conn: Any,
    page_id: int,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Unmark a page from spread.

    Args:
        db_conn: Database connection
        page_id: Page ID
        dry_run: If True, don't execute

    Returns:
        Result dictionary
    """
    result = {
        'operation': 'unmark_spread',
        'page_id': page_id,
        'rows_affected': 0,
        'error': None,
    }

    try:
        cursor = db_conn.cursor()

        # First, find linked page
        query_get = "SELECT is_spread_with FROM pages_t WHERE page_id = %s"
        cursor.execute(query_get, (page_id,))
        row = cursor.fetchone()

        if not row:
            result['error'] = f"Page {page_id} not found"
            logger.error(result['error'])
            cursor.close()
            return result

        linked_page_id = row[0] if row else None

        query = """
            UPDATE pages_t
            SET is_spread = 0, is_spread_with = NULL, updated_at = NOW()
            WHERE page_id = %s
        """

        logger.info(f"Unmarking page {page_id} from spread")

        if dry_run:
            logger.info(f"[DRY RUN] Would unmark page {page_id} from spread")
            result['rows_affected'] = 1
        else:
            # Unmark both pages
            cursor.execute(query, (page_id,))
            db_conn.commit()

            if linked_page_id:
                cursor.execute(query, (linked_page_id,))
                db_conn.commit()

            result['rows_affected'] = 1
            logger.info(f"Unmarked page {page_id}")

        cursor.close()
        return result

    except mysql.connector.Error as e:
        result['error'] = f"Database error: {e}"
        logger.error(result['error'])
        db_conn.rollback()
        return result


def show_page_info(
    db_conn: Any,
    page_id: int
) -> Dict[str, Any]:
    """Display current information about a page."""
    try:
        cursor = db_conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT page_id, container_id, page_index, page_type,
                   is_cover, is_blank, is_spread, is_spread_with,
                   ocr_confidence, is_manually_verified
            FROM pages_t
            WHERE page_id = %s
        """, (page_id,))

        row = cursor.fetchone()
        cursor.close()

        if row:
            logger.info(f"Page {page_id} Info:")
            for key, value in row.items():
                logger.info(f"  {key}: {value}")
            return row
        else:
            logger.warning(f"Page {page_id} not found")
            return None

    except Exception as e:
        logger.error(f"Failed to query page: {e}")
        return None


# =============================================================================
# Interactive Mode
# =============================================================================

def interactive_mode(db_conn: Any):
    """Interactive menu for corrections."""
    logger.info("\n" + "=" * 70)
    logger.info("HJB Operator Corrections - Interactive Mode")
    logger.info("=" * 70)

    while True:
        logger.info("""
Options:
  1. Mark container as verified
  2. Update page type
  3. Mark pages as spread
  4. Unmark page from spread
  5. Show page info
  6. Exit
        """)

        choice = input("Enter choice (1-6): ").strip()

        try:
            if choice == '1':
                container_id = int(input("Container ID: "))
                confirm = input(f"Mark ALL pages in container {container_id} as verified? (yes/no): ")
                if confirm.lower() == 'yes':
                    result = mark_pages_verified(db_conn, container_id)
                    logger.info(f"Result: {result}")

            elif choice == '2':
                page_ids_str = input("Page IDs (comma-separated): ")
                page_ids = [int(x.strip()) for x in page_ids_str.split(',')]
                page_type = input("New type (content/cover/index/toc/advertisement/plate/blank/other): ")
                result = update_page_types(db_conn, page_ids, page_type)
                logger.info(f"Result: {result}")

            elif choice == '3':
                page_id_1 = int(input("First page ID: "))
                page_id_2 = int(input("Second page ID: "))
                result = mark_spread(db_conn, page_id_1, page_id_2)
                logger.info(f"Result: {result}")

            elif choice == '4':
                page_id = int(input("Page ID: "))
                result = unmark_spread(db_conn, page_id)
                logger.info(f"Result: {result}")

            elif choice == '5':
                page_id = int(input("Page ID: "))
                show_page_info(db_conn, page_id)

            elif choice == '6':
                logger.info("Exiting")
                break

            else:
                logger.warning("Invalid choice")

        except KeyboardInterrupt:
            logger.info("\nExiting")
            break
        except Exception as e:
            logger.error(f"Error: {e}")


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Apply operator corrections to HJB database'
    )
    parser.add_argument('--container-id', type=int, help='Container ID')
    parser.add_argument('--page-ids', type=int, nargs='+', help='Page IDs')
    parser.add_argument('--page-type', type=str, help='New page type')
    parser.add_argument('--spread', type=int, nargs='+', help='Page IDs to mark as spread')
    parser.add_argument('--mark-verified', action='store_true', help='Mark container as verified')
    parser.add_argument('--unspread', type=int, help='Page ID to unmark from spread')
    parser.add_argument('--interactive', action='store_true', help='Interactive mode')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
    parser.add_argument('--show-page', type=int, help='Display page info')

    args = parser.parse_args()

    try:
        with hjb_db.get_connection() as db_conn:
            # Interactive mode
            if args.interactive:
                interactive_mode(db_conn)
                return 0

            # Show page info
            if args.show_page:
                show_page_info(db_conn, args.show_page)
                return 0

            # Mark container verified
            if args.mark_verified and args.container_id:
                result = mark_pages_verified(db_conn, args.container_id, dry_run=args.dry_run)
                logger.info(f"Result: {result}")
                return 0 if not result['error'] else 1

            # Update page types
            if args.page_ids and args.page_type:
                result = update_page_types(db_conn, args.page_ids, args.page_type, dry_run=args.dry_run)
                logger.info(f"Result: {result}")
                return 0 if not result['error'] else 1

            # Mark spread
            if args.spread and len(args.spread) >= 2:
                for i in range(0, len(args.spread) - 1, 2):
                    result = mark_spread(db_conn, args.spread[i], args.spread[i + 1], dry_run=args.dry_run)
                    logger.info(f"Result: {result}")
                return 0

            # Unmark spread
            if args.unspread:
                result = unmark_spread(db_conn, args.unspread, dry_run=args.dry_run)
                logger.info(f"Result: {result}")
                return 0 if not result['error'] else 1

            # No action specified
            parser.print_help()
            return 1

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
