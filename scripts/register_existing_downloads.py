#!/usr/bin/env python3
"""
HJB - Retroactive Registration of Existing IA Downloads

Registers previously downloaded Internet Archive items in the MySQL database.
Scans a publication family directory and registers any items not already in the database.

Usage:
    # Dry run (preview without database changes)
    python scripts/register_existing_downloads.py --family American_Architect_family --dry-run

    # Actually register
    python scripts/register_existing_downloads.py --family American_Architect_family

    # Verbose mode with custom log directory
    python scripts/register_existing_downloads.py --family American_Architect_family --verbose --log-dir logs

Prerequisites:
    - Database access configured (HJB_DB_PASSWORD environment variable or config.yaml)
    - NAS access to Raw_Input/0110_Internet_Archive/SIM/
    - Publication family directory exists with downloaded items
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add repo root to path for imports
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.stage1.ia_acquire import (
    reconstruct_metadata_from_local,
    register_container_from_local,
    DB_AVAILABLE,
    hjb_db,
)

# Configuration
DEFAULT_BASE_PATH = Path(r"\\RaneyHQ\Michael\02_Projects\Historical_Journals_And_Books")
DEFAULT_RAW_INPUT_IA = DEFAULT_BASE_PATH / "Raw_Input" / "0110_Internet_Archive" / "SIM"
FAMILY_MAPPING_FILE = REPO_ROOT / "config" / "ia_family_mapping.json"


def setup_logging(log_dir: Path, verbose: bool = False) -> logging.Logger:
    """
    Set up logging to both file and console.

    Args:
        log_dir: Directory for log files
        verbose: Enable verbose console output

    Returns:
        Configured logger
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"register_existing_{timestamp}.log"

    logger = logging.getLogger("register_existing")
    logger.setLevel(logging.DEBUG)

    # File handler - always detailed
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s"
    ))
    logger.addHandler(file_handler)

    # Console handler - respects verbose flag
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console_handler)

    logger.info(f"Logging to: {log_file}")

    return logger


def load_family_mapping() -> Dict[str, Dict]:
    """
    Load family mapping from JSON file.

    Returns:
        Dict mapping family_root to family info (family_id, display_name, etc.)
    """
    if not FAMILY_MAPPING_FILE.exists():
        return {}

    try:
        with FAMILY_MAPPING_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Failed to load family mapping: {e}")
        return {}


def scan_family_directory(
    family_root: str,
    base_path: Path = DEFAULT_RAW_INPUT_IA,
) -> List[Path]:
    """
    Find all item directories in a family directory.

    An item directory is identified by containing a _meta.json file or
    having a name starting with 'sim_'.

    Args:
        family_root: Family directory name (e.g., "American_Architect_family")
        base_path: Base path to IA downloads

    Returns:
        List of paths to item directories
    """
    family_dir = base_path / family_root

    if not family_dir.exists():
        raise FileNotFoundError(f"Family directory not found: {family_dir}")

    items = []
    for item_dir in family_dir.iterdir():
        if not item_dir.is_dir():
            continue

        # Check if it looks like an IA item directory
        has_meta = (item_dir / f"{item_dir.name}_meta.json").exists()
        has_any_file = any(item_dir.iterdir())
        is_sim = item_dir.name.startswith("sim_")

        if has_meta or (is_sim and has_any_file):
            items.append(item_dir)

    return sorted(items)


def is_already_registered(
    identifier: str,
    source_system: str = "internet_archive",
) -> Optional[int]:
    """
    Check if a container is already registered in the database.

    Args:
        identifier: The Internet Archive identifier
        source_system: Source system identifier

    Returns:
        container_id if registered, None otherwise
    """
    if not DB_AVAILABLE or hjb_db is None:
        return None

    try:
        existing = hjb_db.get_container_by_source(source_system, identifier)
        if existing:
            return existing.get("container_id")
    except Exception as e:
        print(f"  [WARN] Database query failed: {e}")

    return None


def register_single_item(
    identifier: str,
    download_dir: Path,
    family: str,
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None,
) -> Tuple[str, Optional[int], str]:
    """
    Register a single item in the database.

    Args:
        identifier: The Internet Archive identifier
        download_dir: Path to the item directory
        family: Publication family name
        dry_run: If True, don't actually register
        logger: Logger instance

    Returns:
        Tuple of (status, container_id, message)
        status: "registered", "skipped", "failed"
    """
    log = logger or logging.getLogger("register_existing")

    # Check if already registered
    existing_id = is_already_registered(identifier)
    if existing_id:
        return ("skipped", existing_id, f"Already registered (container_id: {existing_id})")

    if dry_run:
        return ("dry_run", None, "Would register (dry run)")

    # Attempt registration
    try:
        container_id = register_container_from_local(
            identifier=identifier,
            download_dir=download_dir,
            family=family,
        )

        if container_id:
            return ("registered", container_id, f"Registered (container_id: {container_id})")
        else:
            return ("failed", None, "Registration returned None")

    except Exception as e:
        log.exception(f"Failed to register {identifier}")
        return ("failed", None, f"Error: {type(e).__name__}: {e}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Register existing IA downloads in the database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Preview what would be registered
    python scripts/register_existing_downloads.py --family American_Architect_family --dry-run

    # Register all items in a family
    python scripts/register_existing_downloads.py --family American_Architect_family

    # Verbose output with custom base path
    python scripts/register_existing_downloads.py --family American_Architect_family -v \\
        --base-path "D:\\IA_Downloads\\SIM"
        """,
    )

    parser.add_argument(
        "--family",
        required=True,
        help="Family root name (e.g., American_Architect_family)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without making database changes",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=REPO_ROOT / "logs",
        help="Directory for log files (default: logs/)",
    )
    parser.add_argument(
        "--base-path",
        type=Path,
        default=DEFAULT_RAW_INPUT_IA,
        help=f"Base path to IA downloads (default: {DEFAULT_RAW_INPUT_IA})",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose console output",
    )

    args = parser.parse_args()

    # Set up logging
    logger = setup_logging(args.log_dir, args.verbose)

    # Check database availability
    if not DB_AVAILABLE:
        logger.error("Database module not available. Install with: pip install mysql-connector-python PyYAML")
        return 1

    if hjb_db is None:
        logger.error("Database connection failed. Check HJB_DB_PASSWORD environment variable.")
        return 1

    # Verify base path exists
    if not args.base_path.exists():
        logger.error(f"Base path not found: {args.base_path}")
        logger.error("Make sure NAS is mounted and accessible.")
        return 1

    # Scan family directory
    print(f"\n{'='*60}")
    print(f"Scanning family: {args.family}")
    print(f"Base path: {args.base_path}")
    print(f"Dry run: {args.dry_run}")
    print(f"{'='*60}\n")

    try:
        items = scan_family_directory(args.family, args.base_path)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1

    if not items:
        logger.warning(f"No items found in {args.family}")
        return 0

    print(f"Found {len(items)} items\n")
    logger.info(f"Found {len(items)} items in {args.family}")

    # Process each item
    stats = {
        "total": len(items),
        "registered": 0,
        "skipped": 0,
        "failed": 0,
        "dry_run": 0,
    }

    for item_dir in items:
        identifier = item_dir.name

        print(f"Processing: {identifier}")
        logger.debug(f"Processing: {identifier} at {item_dir}")

        status, container_id, message = register_single_item(
            identifier=identifier,
            download_dir=item_dir,
            family=args.family,
            dry_run=args.dry_run,
            logger=logger,
        )

        stats[status] = stats.get(status, 0) + 1

        # Console output with status indicator
        if status == "registered":
            print(f"  \u2713 {message}")
            logger.info(f"  REGISTERED: {identifier} -> {container_id}")
        elif status == "skipped":
            print(f"  \u2298 {message}")
            logger.debug(f"  SKIPPED: {identifier} (already registered)")
        elif status == "dry_run":
            print(f"  \u2022 {message}")
            logger.debug(f"  DRY_RUN: {identifier}")
        else:  # failed
            print(f"  \u2717 {message}")
            logger.error(f"  FAILED: {identifier} - {message}")

    # Summary
    print(f"\n{'='*60}")
    print("Summary:")
    print(f"  Total:             {stats['total']}")
    if args.dry_run:
        print(f"  Would register:    {stats['dry_run']}")
    else:
        print(f"  Newly registered:  {stats['registered']}")
    print(f"  Already registered: {stats['skipped']}")
    print(f"  Failed:            {stats['failed']}")
    print(f"{'='*60}\n")

    logger.info(f"Summary: total={stats['total']}, registered={stats['registered']}, "
                f"skipped={stats['skipped']}, failed={stats['failed']}")

    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
