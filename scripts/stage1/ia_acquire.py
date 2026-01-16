#!/usr/bin/env python3
"""
HJB Stage 1 - Acquisition (Internet Archive)

Purpose
-------
Download "highest-tier" files from Internet Archive for a list of items, and place them into:

  01_Research/Historical_Journals_Inputs/0110_Internet_Archive/{collection}/{pub_family}/{IAIdentifier}/

Design goals (pragmatic + reliable)
-----------------------------------
1) Deterministic destinations: you control {collection} and {pub_family}.
2) Idempotent: if a target file already exists, we skip it.
3) Conservative defaults: low concurrency; retries on common SMB/Windows transient failures.
4) Very explicit logging + comments so you can reason about behavior.

Input file formats
------------------
Each non-empty, non-comment line can be either:

A) Just an identifier:
   sim_american-architect-and-architecture_1900-01-27_67_1257

B) Three fields: collection, pub_family, identifier
   American_Architect_collection,American_Architect_family,sim_american-architect-and-architecture_1900-01-27_67_1257

Separators accepted for (B):
  - comma (,)
  - tab (\t)
  - pipe (|)

Lines starting with # are ignored.

Dependencies
------------
pip install internetarchive

Usage examples (PowerShell)
---------------------------
# From repo root
python .\scripts\stage1\ia_acquire.py `
  --list .\config\ia_items.txt `
  --repo-root C:\hjb-project `
  --workers 2 `
  --tier a

# If your list contains identifier-only lines, you can provide defaults:
python .\scripts\stage1\ia_acquire.py `
  --list .\config\ia_ids_only.txt `
  --default-collection American_Architect_collection `
  --default-family American_Architect_family

Exit codes
----------
0 = all items processed (some may have missing files; that's recorded)
1 = fatal error (e.g., bad paths / dependency missing)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import json
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, List, Optional, Tuple

# External dependency
try:
    import internetarchive  # type: ignore
except Exception as e:
    internetarchive = None


# -----------------------------
# Tier definitions (customize)
# -----------------------------
# "Tier A" = core acquisition artifacts you likely want first.
TIER_A_SUFFIXES = [
    "_jp2.zip",        # high-fidelity page images in a single archive
    ".pdf",            # convenient reading/preview + sometimes text layer
    "_hocr.html",      # OCR with positional layout (when present)
    "_scandata.xml",   # page numbering / structure metadata (when present)
]

# "Tier B" = extra metadata / alternative OCR forms (optional).
TIER_B_SUFFIXES = [
    "_meta.xml",
    "_json.json",
    "_djvu.txt",
    "_djvu.xml",
]


@dataclass(frozen=True)
class IaRow:
    collection: str
    family: str
    identifier: str


# -----------------------------
# Small utilities
# -----------------------------
def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def now_iso_utc() -> str:
    # UTC ISO timestamp for logs/records
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def normalize_token(s: str) -> str:
    # Keep it simple; caller is expected to provide already "safe" folder names
    return s.strip().strip('"').strip("'")


def split_3_fields(line: str) -> Optional[Tuple[str, str, str]]:
    """
    Accept comma, tab, or pipe separated triplets.

    We do not attempt full CSV quoting rules here; if you need commas *inside*
    values, use tab or pipe.
    """
    for sep in ("\t", "|", ","):
        parts = [p.strip() for p in line.split(sep)]
        if len(parts) == 3 and all(p.strip() for p in parts):
            return parts[0], parts[1], parts[2]
    return None


def parse_list_file(
    list_path: Path,
    default_collection: Optional[str],
    default_family: Optional[str],
) -> List[IaRow]:
    """
    Parse the operator list file into IaRow objects.
    """
    rows: List[IaRow] = []
    for raw in list_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        triplet = split_3_fields(line)
        if triplet:
            c, f, ident = triplet
            rows.append(IaRow(normalize_token(c), normalize_token(f), normalize_token(ident)))
            continue

        # If it wasn't a triplet, treat it as identifier-only.
        ident = normalize_token(line)
        if not default_collection or not default_family:
            raise ValueError(
                f"Identifier-only line encountered but defaults not provided: '{line}'. "
                f"Provide --default-collection and --default-family or use 3-field lines."
            )
        rows.append(IaRow(normalize_token(default_collection), normalize_token(default_family), ident))

    return rows


def pick_suffixes(tier: str) -> List[str]:
    t = tier.lower().strip()
    if t == "a":
        return list(TIER_A_SUFFIXES)
    if t == "b":
        return list(TIER_A_SUFFIXES) + list(TIER_B_SUFFIXES)
    raise ValueError("tier must be 'a' or 'b'")


def choose_files_for_item(file_names: List[str], suffixes: List[str]) -> List[str]:
    """
    For each suffix in order, select the first file that endswith that suffix.
    This mirrors your prior approach but makes the selection logic explicit.
    """
    chosen: List[str] = []
    for suf in suffixes:
        match = next((n for n in file_names if n and n.endswith(suf)), None)
        if match:
            chosen.append(match)
    return chosen


def already_have_all(target_dir: Path, identifier: str, files_to_get: List[str]) -> bool:
    """
    Determine if all desired outputs already exist.

    We rename downloads to: {identifier}_{original_filename_without_identifier_prefix_if_present}

    So we check for the final renamed form.
    """
    for original in files_to_get:
        if original.startswith(identifier + "_"):
            suffix = original[len(identifier) + 1 :]
        else:
            suffix = original
        final_name = f"{identifier}_{suffix}"
        if not (target_dir / final_name).exists():
            return False
    return True


def rename_downloads_in_place(identifier_dir: Path, identifier: str, files_downloaded: List[str]) -> None:
    """
    After IA download, rename each file to a stable prefix format:
      {identifier}_{suffix}
    """
    for original_name in files_downloaded:
        p = identifier_dir / original_name
        if not p.exists():
            # IA sometimes skips missing/unavailable; we'll tolerate and log at higher layer.
            continue

        if original_name.startswith(identifier + "_"):
            suffix = original_name[len(identifier) + 1 :]
        else:
            suffix = original_name

        new_name = f"{identifier}_{suffix}"
        if p.name == new_name:
            continue

        dest = identifier_dir / new_name
        try:
            if dest.exists():
                # If the renamed version exists already, keep the existing and remove the duplicate.
                p.unlink()
            else:
                p.rename(dest)
        except Exception:
            # Non-fatal; downstream checks/logs will reveal oddities
            pass


# -----------------------------
# Core download routine
# -----------------------------
def download_one(
    row: IaRow,
    base_dir: Path,
    suffixes: List[str],
    max_retries: int,
    retry_sleep: float,
    verbose: bool,
) -> dict:
    """
    Download for a single IA identifier into:
      base_dir/{collection}/{family}/{identifier}/

    Returns a structured result dict for logging or later ingestion into a manifest.
    """
    ident = row.identifier
    dest_parent = base_dir / row.collection / row.family
    dest_dir = dest_parent / ident

    ensure_dir(dest_parent)
    ensure_dir(dest_dir)

    result = {
        "utc": now_iso_utc(),
        "collection": row.collection,
        "family": row.family,
        "identifier": ident,
        "dest_dir": str(dest_dir),
        "status": "unknown",
        "selected": [],
        "downloaded": [],
        "missing_suffixes": [],
        "note": "",
    }

    # Obtain the IA item (network operation).
    if internetarchive is None:
        raise RuntimeError("internetarchive is not installed. Run: pip install internetarchive")

    for attempt in range(1, max_retries + 1):
        try:
            item = internetarchive.get_item(ident)
            # Listing item.files can throw intermittently; treat as retryable.
            available_files = list(item.files)
            names = [f.get("name") for f in available_files if isinstance(f, dict) and "name" in f]
            names = [n for n in names if isinstance(n, str)]

            selected = choose_files_for_item(names, suffixes)
            result["selected"] = selected

            # Track which suffixes were missing to make later coverage analysis easier.
            missing = []
            for suf in suffixes:
                if not any(n.endswith(suf) for n in selected):
                    # We only say "missing" for suffixes we attempted to select.
                    # For suffixes not represented, we record it.
                    # (This is coarse because file naming can vary, but useful.)
                    if not any(n.endswith(suf) for n in names):
                        missing.append(suf)
            result["missing_suffixes"] = missing

            if not selected:
                result["status"] = "no_matching_files"
                result["note"] = "No requested files found for configured tiers."
                return result

            # Idempotency check: if final renamed files are all present, do nothing.
            if already_have_all(dest_dir, ident, selected):
                result["status"] = "skipped_already_present"
                result["note"] = "All selected files already exist in final renamed form."
                return result

            # IA download behavior:
            # item.download(destdir=X) creates X/{identifier}/ automatically.
            # We want files to end up in dest_parent/{identifier}/, so destdir=dest_parent.
            if verbose:
                print(f"[{ident}] Downloading to {dest_parent} ({len(selected)} file(s))")

            item.download(
                destdir=str(dest_parent),
                files=selected,
                verbose=bool(verbose),
            )

            identifier_dir = dest_parent / ident
            if not identifier_dir.exists():
                result["status"] = "download_error"
                result["note"] = f"Expected IA folder not created: {identifier_dir}"
                return result

            # Rename into stable prefix form.
            rename_downloads_in_place(identifier_dir, ident, selected)

            # Confirm which files exist now.
            downloaded = []
            for original in selected:
                if original.startswith(ident + "_"):
                    suffix = original[len(ident) + 1 :]
                else:
                    suffix = original
                final_name = f"{ident}_{suffix}"
                if (identifier_dir / final_name).exists():
                    downloaded.append(final_name)
            result["downloaded"] = downloaded

            result["status"] = "ok"
            result["note"] = f"Downloaded {len(downloaded)}/{len(selected)} selected files."
            return result

        except Exception as e:
            if attempt >= max_retries:
                result["status"] = "error"
                result["note"] = f"Failed after {attempt} attempt(s): {type(e).__name__}: {e}"
                return result
            # Backoff and retry
            time.sleep(retry_sleep * attempt)

    # Should never reach here
    result["status"] = "error"
    result["note"] = "Unexpected fallthrough."
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True, help="Path to IA list file (identifier-only or 3-field lines).")
    ap.add_argument(
        "--repo-root",
        default=None,
        help="Optional repo root. If omitted, inferred from this script location.",
    )
    ap.add_argument(
        "--base-dir",
        default=None,
        help=(
            "Optional override for acquisition base dir. "
            "Default: <repo_root>/01_Research/Historical_Journals_Inputs/0110_Internet_Archive"
        ),
    )
    ap.add_argument("--default-collection", default=None, help="Used only if list has identifier-only lines.")
    ap.add_argument("--default-family", default=None, help="Used only if list has identifier-only lines.")
    ap.add_argument("--tier", default="a", choices=["a", "b"], help="File tier selection. a=core, b=core+extra.")
    ap.add_argument("--workers", type=int, default=2, help="Parallel workers across identifiers (default 2).")
    ap.add_argument("--retries", type=int, default=3, help="Max retries per identifier for transient IA errors.")
    ap.add_argument("--retry-sleep", type=float, default=1.5, help="Base sleep seconds between retries.")
    ap.add_argument("--verbose", action="store_true", help="Verbose IA downloader output.")
    ap.add_argument("--write-report", action="store_true", help="Write a JSON report into base-dir/_reports.")
    args = ap.parse_args()

    # Resolve repo root deterministically.
    if args.repo_root:
        repo_root = Path(args.repo_root).resolve()
    else:
        # scripts/stage1/ia_acquire.py -> repo root is two levels up (scripts -> repo)
        repo_root = Path(__file__).resolve().parents[2]

    if not repo_root.exists():
        eprint(f"Repo root not found: {repo_root}")
        return 1

    # Default base dir per your requirement.
    if args.base_dir:
        base_dir = Path(args.base_dir).resolve()
    else:
        base_dir = repo_root / "01_Research" / "Historical_Journals_Inputs" / "0110_Internet_Archive"

    ensure_dir(base_dir)

    list_path = Path(args.list).resolve()
    if not list_path.is_file():
        eprint(f"List file not found: {list_path}")
        return 1

    # Parse input list file.
    try:
        rows = parse_list_file(
            list_path=list_path,
            default_collection=args.default_collection,
            default_family=args.default_family,
        )
    except Exception as e:
        eprint(f"Failed to parse list file: {e}")
        return 1

    if not rows:
        print("No rows to process (empty list).")
        return 0

    suffixes = pick_suffixes(args.tier)

    # Run downloads (bounded concurrency).
    workers = max(1, int(args.workers))
    results: List[dict] = []

    print(f"[HJB] IA acquisition starting: items={len(rows)} workers={workers} tier={args.tier}")
    print(f"[HJB] base_dir={base_dir}")
    print(f"[HJB] list={list_path}")

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [
            ex.submit(
                download_one,
                row,
                base_dir,
                suffixes,
                int(args.retries),
                float(args.retry_sleep),
                bool(args.verbose),
            )
            for row in rows
        ]
        for f in as_completed(futs):
            r = f.result()
            results.append(r)
            status = r.get("status")
            ident = r.get("identifier")
            note = r.get("note", "")
            print(f"[{ident}] {status} - {note}")

    # Optional report for later analysis / provenance.
    if args.write_report:
        rep_dir = base_dir / "_reports"
        ensure_dir(rep_dir)
        rep_path = rep_dir / f"ia_acquire_report_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
        rep_path.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[HJB] Wrote report: {rep_path}")

    # Exit 0 even if some identifiers had missing files; that’s expected on IA.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
