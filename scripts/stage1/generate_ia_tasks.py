#!/usr/bin/env python3
"""
Generate individual task flags for IA downloads.

Input: Text file with IA identifiers (one per line, or extracted from IA folder listing)
Output: Individual JSON task flags in flags/pending/ ready for watcher to process

Usage:
  python generate_ia_tasks.py --identifiers identifiers.txt \
    --output-dir flags/pending/ \
    --family american_architect_family \
    [--dry-run] [--max-tasks 5]

Example identifiers.txt:
  sim_american-architect-and-architecture_1876_1_index
  sim_american-architect-and-architecture_1876-01-01_1_1
  sim_american-architect-and-architecture_1876-01-08_1_2
  ...
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from datetime import datetime, timezone
from pathlib import Path


# Pre-compiled regex for identifier filtering (case-insensitive)
_FILTER_PATTERN = re.compile(r'_(?:index|superceded|supplemental)', re.IGNORECASE)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def utc_now_compact() -> str:
    """Generate compact UTC timestamp without colons/dashes for task IDs."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_identifiers(input_file: Path) -> list[str]:
    """
    Parse identifiers from input file.
    Handles:
    - One identifier per line
    - Lines starting with 'sim_' (standard format)
    - Empty lines and comments (ignored)
    """
    identifiers = []
    for line in input_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        identifiers.append(line)
    return identifiers


def filter_identifiers(identifiers: list[str]) -> list[str]:
    """
    Filter to production identifiers only.

    Excludes:
    - _index (volume index, not a regular issue)
    - _superceded (old complete package, replaced by individual issues)
    - _supplemental (supplementary content, often end-of-volume)

    We process these separately if needed, but for main acquisition
    we focus on regular issues.
    """
    # Use pre-compiled regex for O(n) filtering instead of O(n*m)
    return [ident for ident in identifiers if not _FILTER_PATTERN.search(ident)]


def generate_task_flag(
    identifier: str,
    family: str,
    task_number: int,
    total_tasks: int,
) -> dict:
    """
    Generate a single task flag JSON for this identifier.
    """
    task_id = f"{utc_now_compact()}_{identifier}"
    
    return {
        "schema": "hjb.task.v1",
        "task_id": task_id,
        "task_type": "stage1.ia_download",
        "created_at": utc_now_iso(),
        "created_by": "generate_ia_tasks.py",
        "priority": "normal",
        "parameters": {
            "ia_identifier": identifier,
            "family": family,
            "include_ocr": True,
            "max_retries": 3,
        },
        "metadata": {
            "batch_info": f"Task {task_number} of {total_tasks}",
            "description": f"Download IA item: {identifier}",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generate individual IA download task flags."
    )
    ap.add_argument(
        "--identifiers",
        required=True,
        type=Path,
        help="Path to file with IA identifiers (one per line)",
    )
    ap.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Output directory for task flags (typically flags/pending/)",
    )
    ap.add_argument(
        "--family",
        required=True,
        help="Publication family name (e.g., american_architect_family)",
    )
    ap.add_argument(
        "--max-tasks",
        type=int,
        default=None,
        help="Limit to first N tasks (default: all)",
    )
    ap.add_argument(
        "--include-index",
        action="store_true",
        help="Include _index identifiers (normally skipped)",
    )
    ap.add_argument(
        "--include-supplemental",
        action="store_true",
        help="Include _supplemental identifiers (normally skipped)",
    )
    ap.add_argument(
        "--include-superceded",
        action="store_true",
        help="Include _superceded identifiers (normally skipped, they're old packages)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without creating files",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output",
    )
    args = ap.parse_args()

    # Validate inputs
    if not args.identifiers.is_file():
        print(f"ERROR: Identifiers file not found: {args.identifiers}", file=sys.stderr)
        return 1

    if not args.dry_run:
        if not args.output_dir.exists():
            print(f"ERROR: Output dir does not exist: {args.output_dir}", file=sys.stderr)
            return 1
        if not args.output_dir.is_dir():
            print(f"ERROR: Output path is not a directory: {args.output_dir}", file=sys.stderr)
            return 1

    # Parse identifiers
    all_identifiers = parse_identifiers(args.identifiers)
    if args.verbose:
        print(f"[*] Parsed {len(all_identifiers)} identifiers from {args.identifiers}")

    # Filter (unless overridden)
    if (
        not args.include_index
        and not args.include_supplemental
        and not args.include_superceded
    ):
        filtered = filter_identifiers(all_identifiers)
        skipped = len(all_identifiers) - len(filtered)
        if args.verbose:
            print(f"[*] Filtered to {len(filtered)} regular issues (skipped {skipped})")
        identifiers = filtered
    else:
        identifiers = all_identifiers
        if args.verbose:
            print(f"[*] Using all {len(identifiers)} identifiers (filter disabled)")

    # Limit if requested
    if args.max_tasks:
        identifiers = identifiers[: args.max_tasks]
        if args.verbose:
            print(f"[*] Limited to first {len(identifiers)} tasks")

    # Generate task flags
    total = len(identifiers)
    created_count = 0
    failed_count = 0

    print(f"\n{'='*70}")
    print(f"Generating {total} task flags for family: {args.family}")
    print(f"Output directory: {args.output_dir}")
    print(f"Dry run: {args.dry_run}")
    print(f"{'='*70}\n")

    for i, identifier in enumerate(identifiers, 1):
        try:
            task = generate_task_flag(identifier, args.family, i, total)

            if args.dry_run:
                print(f"[DRY] Task {i}/{total}: {task['task_id']}")
                if args.verbose:
                    print(f"      Identifier: {identifier}")
            else:
                output_path = args.output_dir / f"{task['task_id']}.json"
                output_path.write_text(
                    json.dumps(task, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                print(f"[OK] Task {i}/{total}: {output_path.name}")
                created_count += 1

        except Exception as ex:
            print(f"[ERROR] Task {i}/{total}: {ex}", file=sys.stderr)
            failed_count += 1

    # Summary
    print(f"\n{'='*70}")
    if args.dry_run:
        print(f"DRY RUN: Would create {total} task flags")
    else:
        print(f"Created: {created_count} task flags")
        if failed_count:
            print(f"Failed:  {failed_count} task flags")
    print(f"{'='*70}\n")

    if not args.dry_run and created_count > 0:
        print(f"✓ Task flags are ready in: {args.output_dir}")
        print(f"  Watcher will pick them up automatically.")
        print(f"  Monitor progress via:")
        print(f"    tail -f Working_Files/0200_STATE/logs/[today]_processing.log")
        print()

    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
