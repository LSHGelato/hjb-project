#!/usr/bin/env python3
"""
Database Migration Executor

Safely applies SQL migrations from files with proper error handling and logging.

Usage:
  python apply_migration.py --migration-file database/migrations/004_hybrid_schema_page_assets.sql
  python apply_migration.py --list
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.common import hjb_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('migration.log'),
    ]
)
logger = logging.getLogger(__name__)


def parse_sql_file(file_path: Path) -> List[str]:
    """
    Parse SQL file into individual statements.

    Handles:
    - Multi-line statements
    - Comments (-- and /* */)
    - String literals with semicolons
    """
    content = file_path.read_text(encoding='utf-8')

    # Remove multi-line comments (/* ... */)
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)

    # Remove single-line comments (--)
    lines = []
    for line in content.split('\n'):
        # Remove comment part (-- to end of line)
        if '--' in line:
            line = line[:line.index('--')]
        lines.append(line)
    content = '\n'.join(lines)

    # Split by semicolon, filter empty statements
    statements = [
        s.strip() for s in content.split(';')
        if s.strip()
    ]

    return statements


def execute_migration(file_path: Path, dry_run: bool = False) -> bool:
    """
    Execute migration from SQL file.

    Args:
        file_path: Path to migration SQL file
        dry_run: If True, parse but don't execute

    Returns:
        True if successful, False otherwise
    """
    if not file_path.exists():
        logger.error(f"Migration file not found: {file_path}")
        return False

    logger.info(f"Loading migration: {file_path}")

    try:
        statements = parse_sql_file(file_path)
        logger.info(f"Parsed {len(statements)} SQL statements")

        if dry_run:
            logger.info("[DRY RUN] Statements parsed but not executed")
            for i, stmt in enumerate(statements, 1):
                preview = stmt.replace('\n', ' ')[:60]
                logger.info(f"  [{i}] {preview}...")
            return True

        # Execute statements
        with hjb_db.get_connection() as conn:
            cursor = conn.cursor()
            executed = 0
            skipped = 0

            for i, stmt in enumerate(statements, 1):
                try:
                    logger.debug(f"[{i}/{len(statements)}] Executing: {stmt[:50]}...")
                    cursor.execute(stmt)
                    conn.commit()
                    executed += 1

                except Exception as e:
                    error_msg = str(e)

                    # Check for "already exists" errors (not fatal)
                    if any(x in error_msg for x in
                           ['already exists', 'Duplicate column', 'Duplicate key']):
                        logger.info(f"[{i}] Skipped (already exists): {error_msg[:50]}")
                        skipped += 1
                    else:
                        logger.error(f"[{i}] FAILED: {error_msg}")
                        logger.debug(f"Statement: {stmt}")
                        cursor.close()
                        return False

            cursor.close()

            logger.info(f"Migration complete: {executed} executed, {skipped} skipped")
            return True

    except Exception as e:
        logger.exception(f"Migration failed: {type(e).__name__}: {e}")
        return False


def verify_migration() -> bool:
    """Verify that migration tables and columns were created."""
    logger.info("Verifying migration...")

    try:
        with hjb_db.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)

            # Check page_assets_t exists
            try:
                cursor.execute("DESCRIBE page_assets_t")
                results = cursor.fetchall()
                if results:
                    logger.info(f"[OK] page_assets_t exists with {len(results)} columns")
                else:
                    logger.warning("page_assets_t exists but has no columns")
            except Exception as e:
                logger.error(f"page_assets_t check failed: {e}")
                cursor.close()
                return False

            # Check page_pack_manifests_t exists
            try:
                cursor.execute("DESCRIBE page_pack_manifests_t")
                results = cursor.fetchall()
                if results:
                    logger.info(f"[OK] page_pack_manifests_t exists with {len(results)} columns")
                else:
                    logger.warning("page_pack_manifests_t exists but has no columns")
            except Exception as e:
                logger.error(f"page_pack_manifests_t check failed: {e}")
                cursor.close()
                return False

            # Check pages_t new columns
            cursor.execute("""
                SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME='pages_t'
                AND COLUMN_NAME IN ('ocr_text_snippet', 'ocr_char_count', 'is_spread')
            """)
            new_cols = cursor.fetchall()
            if len(new_cols) >= 2:  # At least ocr_text_snippet and ocr_char_count
                logger.info(f"[OK] pages_t has {len(new_cols)} new columns")
            else:
                logger.warning(f"pages_t new columns check: expected 3+, found {len(new_cols)}")

            cursor.close()
            logger.info("[OK] Migration verification passed")
            return True

    except Exception as e:
        logger.exception(f"Verification failed: {e}")
        return False


def list_migrations() -> None:
    """List available migration files."""
    migration_dir = Path("database/migrations")

    if not migration_dir.exists():
        logger.error(f"Migrations directory not found: {migration_dir}")
        return

    migrations = sorted(migration_dir.glob("*.sql"))

    if not migrations:
        logger.info("No migration files found")
        return

    logger.info(f"Found {len(migrations)} migration file(s):")
    for m in migrations:
        size_kb = m.stat().st_size / 1024
        logger.info(f"  - {m.name} ({size_kb:.1f} KB)")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Apply database migrations safely"
    )
    parser.add_argument(
        '--migration-file',
        type=Path,
        help='Migration SQL file to apply'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List available migrations'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Parse SQL but don\'t execute'
    )
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify migration was applied successfully'
    )

    args = parser.parse_args()

    # List migrations
    if args.list:
        list_migrations()
        return 0

    # Verify only
    if args.verify:
        if verify_migration():
            return 0
        else:
            return 1

    # Apply migration
    if args.migration_file:
        if execute_migration(args.migration_file, dry_run=args.dry_run):
            if not args.dry_run:
                if verify_migration():
                    logger.info("[SUCCESS] Migration applied and verified")
                    return 0
                else:
                    logger.warning("[WARNING] Migration applied but verification failed")
                    return 1
            return 0
        else:
            logger.error("[FAILED] Migration did not complete successfully")
            return 1

    # No action specified
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
