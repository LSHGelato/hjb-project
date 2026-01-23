#!/usr/bin/env python3
"""
HJB Stage 1 - Inventory Generation

Generates CSV inventory of files in specified directories with optional SHA256 hashing.
Can be run standalone via CLI or called from hjb_watcher.py.

Usage (standalone):
    python generate_inventory.py \\
        --roots "\\\\NAS\\path1" "\\\\NAS\\path2" \\
        --output-dir ./inventory_output \\
        --task-id my_inventory_task \\
        [--include-sha256] \\
        [--include-globs "*.pdf" "*.jpg"] \\
        [--exclude-globs "*/_tmp/*" "*/cache/*"] \\
        [--max-files 100000] \\
        [--max-seconds 1800]

Usage (from watcher):
    Called via execute_from_manifest() with task manifest

Output:
    CSV file with columns: root, relpath, fullpath, size_bytes, mtime_utc, [sha256]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
import time
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _matches_any_glob(path_str: str, globs: List[str]) -> bool:
    """
    Windows-friendly glob matching against forward-slash-normalized paths.
    """
    norm = path_str.replace("\\", "/")
    return any(fnmatch(norm, g) for g in globs)


def _compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file in chunks to handle large files."""
    h = hashlib.sha256()
    try:
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def generate_inventory(
    roots: List[str],
    output_dir: Path,
    task_id: str,
    include_sha256: bool = False,
    include_globs: Optional[List[str]] = None,
    exclude_globs: Optional[List[str]] = None,
    max_files: int = 100000,
    max_seconds: int = 1800,
    verbose: bool = False,
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Generate CSV inventory of files in specified directories.

    Args:
        roots: List of directory paths to inventory
        output_dir: Directory to write CSV output
        task_id: Unique task identifier (used in output filename)
        include_sha256: Whether to compute SHA256 hashes
        include_globs: Only include files matching these patterns (None = all)
        exclude_globs: Exclude files matching these patterns
        max_files: Stop after this many files (0 = unlimited)
        max_seconds: Stop after this many seconds (0 = unlimited)
        verbose: Print progress information

    Returns:
        (outputs, metrics) tuple where:
            outputs: List of output file paths
            metrics: Dict with inventory statistics
    """
    started = time.monotonic()
    stopped_reason: Optional[str] = None

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate output filename
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_csv = output_dir / f"inventory_{task_id}_{ts}.csv"

    # CSV fields
    fields = ["root", "relpath", "fullpath", "size_bytes", "mtime_utc"]
    if include_sha256:
        fields.append("sha256")

    files_seen = 0
    bytes_seen = 0

    if verbose:
        print(f"[inventory] Starting inventory generation")
        print(f"[inventory] Roots: {roots}")
        print(f"[inventory] Output: {out_csv}")
        print(f"[inventory] Include SHA256: {include_sha256}")
        print(f"[inventory] Max files: {max_files}")
        print(f"[inventory] Max seconds: {max_seconds}")

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()

        for root_s in roots:
            root = Path(root_s)
            if not root.exists():
                raise FileNotFoundError(f"Inventory root does not exist: {root}")

            if verbose:
                print(f"[inventory] Scanning: {root}")

            for dirpath, dirnames, filenames in os.walk(str(root)):
                # Safety brake: time-based (checked per directory)
                if max_seconds and (time.monotonic() - started) > max_seconds:
                    stopped_reason = f"max_seconds_exceeded({max_seconds})"
                    break

                # Prune excluded directories so we do not traverse them at all
                pruned: List[str] = []
                for d in dirnames:
                    d_full = str(Path(dirpath) / d)

                    # Always prune flag archives (standard HJB convention)
                    if "\\flags\\completed\\" in d_full or "\\flags\\failed\\" in d_full:
                        continue

                    # Operator exclusions prune traversal
                    if exclude_globs and _matches_any_glob(d_full, exclude_globs):
                        continue

                    pruned.append(d)
                dirnames[:] = pruned

                for name in filenames:
                    # Safety brake: count-based
                    if max_files and files_seen >= max_files:
                        stopped_reason = f"max_files_reached({max_files})"
                        break

                    full = Path(dirpath) / name

                    # Normalize once for matching
                    full_str = str(full)

                    # Hard default exclusions (always on)
                    if "\\flags\\completed\\" in full_str or "\\flags\\failed\\" in full_str:
                        continue

                    # Operator-specified exclusions
                    if exclude_globs and _matches_any_glob(full_str, exclude_globs):
                        continue

                    # Operator-specified inclusions
                    if include_globs and not _matches_any_glob(full_str, include_globs):
                        continue

                    try:
                        st = full.stat()
                    except OSError:
                        continue

                    files_seen += 1
                    bytes_seen += int(st.st_size)
                    mtime_utc = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(timespec="seconds")

                    try:
                        rel = str(full.relative_to(root))
                    except Exception:
                        rel = ""

                    row = {
                        "root": str(root),
                        "relpath": rel,
                        "fullpath": str(full),
                        "size_bytes": int(st.st_size),
                        "mtime_utc": mtime_utc,
                    }

                    if include_sha256:
                        row["sha256"] = _compute_sha256(full)

                    w.writerow(row)

                    # Progress reporting
                    if verbose and files_seen % 1000 == 0:
                        elapsed = int(time.monotonic() - started)
                        print(f"[inventory] Progress: {files_seen} files, {bytes_seen:,} bytes, {elapsed}s elapsed")

                if stopped_reason:
                    break

            if stopped_reason:
                break

    elapsed_seconds = int(time.monotonic() - started)

    if verbose:
        print(f"[inventory] Complete: {files_seen} files, {bytes_seen:,} bytes")
        print(f"[inventory] Elapsed: {elapsed_seconds}s")
        if stopped_reason:
            print(f"[inventory] Stopped early: {stopped_reason}")
        print(f"[inventory] Output: {out_csv}")

    outputs = [str(out_csv)]
    metrics = {
        "files_seen": files_seen,
        "bytes_seen": bytes_seen,
        "include_sha256": include_sha256,
        "max_files": max_files,
        "max_seconds": max_seconds,
        "stopped_reason": stopped_reason,
        "elapsed_seconds": elapsed_seconds,
    }

    return outputs, metrics


def execute_from_manifest(
    manifest: Dict[str, Any],
    task_id: str,
    flags_root: Path,
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Execute inventory task from watcher manifest.

    Manifest format:
    {
        "task_type": "stage1.inventory",
        "payload": {
            "roots": ["\\\\NAS\\path1", "\\\\NAS\\path2"],
            "include_sha256": false,
            "include_globs": ["*.pdf", "*.jpg"],
            "exclude_globs": ["*/_tmp/*"],
            "max_files": 100000,
            "max_seconds": 1800
        }
    }

    Args:
        manifest: Task manifest dict
        task_id: Unique task identifier
        flags_root: Path to flags directory (output goes to flags_root/completed/task_id/inventory/)

    Returns:
        (outputs, metrics) tuple
    """
    payload = manifest.get("payload") or {}
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object (dict)")

    # Required: roots
    roots = payload.get("roots")
    if not (isinstance(roots, list) and all(isinstance(x, str) and x.strip() for x in roots)):
        raise KeyError("payload.roots must be a list of path strings")

    # Optional parameters
    include_sha256 = bool(payload.get("include_sha256", False))

    include_globs = payload.get("include_globs")
    if include_globs is not None:
        if not (isinstance(include_globs, list) and all(isinstance(x, str) for x in include_globs)):
            raise ValueError("payload.include_globs must be a list of strings")

    exclude_globs = payload.get("exclude_globs")
    if exclude_globs is not None:
        if not (isinstance(exclude_globs, list) and all(isinstance(x, str) for x in exclude_globs)):
            raise ValueError("payload.exclude_globs must be a list of strings")

    # Safety brakes (defaults ON)
    max_files = payload.get("max_files", 100000)
    max_seconds = payload.get("max_seconds", 1800)  # 30 minutes

    if max_files is None:
        max_files = 100000
    if max_seconds is None:
        max_seconds = 1800

    if not isinstance(max_files, int) or max_files < 0:
        raise ValueError("payload.max_files must be an int >= 0 (0 disables the limit)")
    if not isinstance(max_seconds, int) or max_seconds < 0:
        raise ValueError("payload.max_seconds must be an int >= 0 (0 disables the limit)")

    # Output directory: flags_root/completed/task_id/inventory/
    output_dir = flags_root / "completed" / task_id / "inventory"

    return generate_inventory(
        roots=roots,
        output_dir=output_dir,
        task_id=task_id,
        include_sha256=include_sha256,
        include_globs=include_globs,
        exclude_globs=exclude_globs,
        max_files=max_files,
        max_seconds=max_seconds,
        verbose=True,
    )


def main() -> int:
    """CLI entry point for standalone usage."""
    ap = argparse.ArgumentParser(
        description="Generate CSV inventory of files in specified directories.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic inventory of a directory
  python generate_inventory.py --roots "C:\\Data" --output-dir ./output --task-id test1

  # Multiple roots with SHA256 hashing
  python generate_inventory.py --roots "\\\\NAS\\share1" "\\\\NAS\\share2" \\
      --output-dir ./output --task-id full_inventory --include-sha256

  # Filter to specific file types
  python generate_inventory.py --roots "C:\\Data" --output-dir ./output --task-id pdfs \\
      --include-globs "*.pdf" "*.PDF"

  # Exclude temporary directories
  python generate_inventory.py --roots "C:\\Data" --output-dir ./output --task-id clean \\
      --exclude-globs "*/_tmp/*" "*/cache/*" "*/.git/*"
        """,
    )

    ap.add_argument(
        "--roots",
        required=True,
        nargs="+",
        help="Directory paths to inventory (can specify multiple)",
    )
    ap.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory to write CSV output file",
    )
    ap.add_argument(
        "--task-id",
        required=True,
        help="Task identifier (used in output filename)",
    )
    ap.add_argument(
        "--include-sha256",
        action="store_true",
        help="Compute SHA256 hash for each file (slower)",
    )
    ap.add_argument(
        "--include-globs",
        nargs="*",
        default=None,
        help="Only include files matching these glob patterns",
    )
    ap.add_argument(
        "--exclude-globs",
        nargs="*",
        default=None,
        help="Exclude files matching these glob patterns",
    )
    ap.add_argument(
        "--max-files",
        type=int,
        default=100000,
        help="Stop after this many files (0=unlimited, default=100000)",
    )
    ap.add_argument(
        "--max-seconds",
        type=int,
        default=1800,
        help="Stop after this many seconds (0=unlimited, default=1800)",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress information",
    )
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress all output except errors",
    )

    args = ap.parse_args()

    # Validate roots exist
    for root in args.roots:
        if not Path(root).exists():
            print(f"ERROR: Root path does not exist: {root}", file=sys.stderr)
            return 1

    # Validate output directory parent exists
    if not args.output_dir.parent.exists():
        print(f"ERROR: Output directory parent does not exist: {args.output_dir.parent}", file=sys.stderr)
        return 1

    verbose = args.verbose and not args.quiet

    try:
        outputs, metrics = generate_inventory(
            roots=args.roots,
            output_dir=args.output_dir,
            task_id=args.task_id,
            include_sha256=args.include_sha256,
            include_globs=args.include_globs,
            exclude_globs=args.exclude_globs,
            max_files=args.max_files,
            max_seconds=args.max_seconds,
            verbose=verbose,
        )

        if not args.quiet:
            print(f"\n{'='*60}")
            print(f"Inventory Complete")
            print(f"{'='*60}")
            print(f"  Files:    {metrics['files_seen']:,}")
            print(f"  Bytes:    {metrics['bytes_seen']:,}")
            print(f"  Elapsed:  {metrics['elapsed_seconds']}s")
            if metrics['stopped_reason']:
                print(f"  Stopped:  {metrics['stopped_reason']}")
            print(f"  Output:   {outputs[0]}")
            print(f"{'='*60}\n")

        return 0

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
