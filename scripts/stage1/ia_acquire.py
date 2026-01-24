#!/usr/bin/env python3
"""
HJB Stage 1 - Acquisition (Internet Archive)

Purpose
-------
Download "highest-tier" files from Internet Archive for a list of items, and place them into:

  01_Research/Historical_Journals_Inputs/0110_Internet_Archive/{collection}/{pub_family}/{IAIdentifier}/

Also registers each downloaded container in the MySQL database.

Design goals (pragmatic + reliable)
-----------------------------------
1) Deterministic destinations: you control {collection} and {pub_family}.
2) Idempotent: if a target file already exists, we skip it.
3) Conservative defaults: low concurrency; retries on common SMB/Windows transient failures.
4) Very explicit logging + comments so you can reason about behavior.
5) Database registration: Creates container_t and processing_status_t records after download.

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
pip install internetarchive mysql-connector-python PyYAML

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

# Disable database registration (for testing without DB)
python .\scripts\stage1\ia_acquire.py `
  --list .\config\ia_items.txt `
  --no-database

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
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
import xml.etree.ElementTree as ET

# Error Checking
print(f"[ia_acquire] Attempting to import hjb_db...", file=sys.stderr)
try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.common import hjb_db
    DB_AVAILABLE = True
    print(f"[ia_acquire] DB_AVAILABLE=True", file=sys.stderr)
except ImportError as e:
    DB_AVAILABLE = False
    hjb_db = None
    print(f"[ia_acquire] DB_AVAILABLE=False - ImportError: {e}", file=sys.stderr)
except Exception as e:
    DB_AVAILABLE = False
    hjb_db = None
    print(f"[ia_acquire] DB_AVAILABLE=False - Exception: {e}", file=sys.stderr)
  
# External dependency
try:
    import internetarchive  # type: ignore
except Exception as e:
    internetarchive = None

# Database integration (optional - graceful degradation if unavailable)
try:
    # Import from scripts/common/hjb_db.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.common import hjb_db
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    hjb_db = None

# Parser for extracting metadata from IA identifiers
try:
    from scripts.stage1.parse_american_architect_ia import (
        parse_american_architect_identifier,
        ParsedIAIdentifier,
    )
    PARSER_AVAILABLE = True
except ImportError:
    PARSER_AVAILABLE = False
    parse_american_architect_identifier = None
    ParsedIAIdentifier = None


# -----------------------------
# Tier definitions (customize)
# -----------------------------
# Merged "Tier A + B" = comprehensive acquisition artifacts for full processing pipeline.
# Core files: JP2 images, PDF reference, OCR text, page structure.
# Supplementary: Metadata (XML and JSON), DjVu OCR alternatives.
TIER_A_SUFFIXES = [
    "_jp2.zip",        # high-fidelity page images in a single archive
    ".pdf",            # convenient reading/preview + sometimes text layer
    "_hocr.html",      # OCR with positional layout (when present)
    "_scandata.xml",   # page numbering / structure metadata (when present)
]

TIER_B_SUFFIXES = [
    "_meta.xml",       # IA metadata in XML format
    # "_json.json" removed--fetch via API instead
    "_djvu.txt",       # DjVu OCR text (plain text fallback)
    "_djvu.xml",       # DjVu OCR with structure (alternative to HOCR)
]

# Combined tier for standard ingestion: get everything
TIER_COMPREHENSIVE_SUFFIXES = TIER_A_SUFFIXES + TIER_B_SUFFIXES

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
    Uses a suffix map for O(n) complexity instead of O(n*m).
    """
    # Build suffix-to-file map in single pass: O(n)
    suffix_to_file = {}
    for name in file_names:
        if not name:
            continue
        for suf in suffixes:
            if name.endswith(suf) and suf not in suffix_to_file:
                suffix_to_file[suf] = name
                break

    # Return files in suffix order
    return [suffix_to_file[suf] for suf in suffixes if suf in suffix_to_file]


def strip_identifier_prefix(filename: str, identifier: str) -> str:
    """
    Strip the identifier prefix from a filename if present.

    E.g., 'sim_foo_1234_file.pdf' with identifier 'sim_foo_1234' -> 'file.pdf'
    """
    prefix = identifier + "_"
    if filename.startswith(prefix):
        return filename[len(prefix):]
    return filename


def get_final_filename(original: str, identifier: str) -> str:
    """Get the final renamed filename for a downloaded file."""
    suffix = strip_identifier_prefix(original, identifier)
    return f"{identifier}_{suffix}"


def already_have_all(target_dir: Path, identifier: str, files_to_get: List[str]) -> bool:
    """
    Determine if all desired outputs already exist.

    We rename downloads to: {identifier}_{original_filename_without_identifier_prefix_if_present}

    So we check for the final renamed form.
    """
    for original in files_to_get:
        final_name = get_final_filename(original, identifier)
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

        new_name = get_final_filename(original_name, identifier)
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

# Add this to scripts/stage1/ia_acquire.py

def fetch_ia_metadata_json(identifier: str, dest_dir: Path, verbose: bool = False) -> Optional[str]:
    """
    Fetch metadata JSON from Internet Archive metadata API.
    
    Args:
        identifier: IA identifier (e.g., 'sim_american-architect-and-architecture_1876-01-01_1_1')
        dest_dir: Destination directory to save the JSON file
        verbose: Print debug info
    
    Returns:
        Path to saved JSON file, or None if fetch failed
    """
    import json
    import requests
    
    dest_file = dest_dir / f"{identifier}_json.json"
    
    if dest_file.is_file():
        if verbose:
            print(f"Metadata JSON already exists: {dest_file}")
        return str(dest_file)
    
    url = f"https://archive.org/metadata/{identifier}"
    
    if verbose:
        print(f"Fetching metadata JSON from: {url}")
    
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        metadata = resp.json()
        
        # Save to file
        dest_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        
        if verbose:
            print(f"Saved metadata JSON: {dest_file}")
        
        return str(dest_file)
    
    except requests.RequestException as e:
        print(f"Failed to fetch metadata JSON from {url}: {e}")
        return None
    except (json.JSONDecodeError, IOError) as e:
        print(f"Failed to save metadata JSON: {e}")
        return None

# -----------------------------
# Metadata reconstruction from local files
# -----------------------------
def reconstruct_metadata_from_local(
    identifier: str,
    download_dir: Path,
) -> Dict[str, Any]:
    """
    Reconstruct metadata dictionary from locally downloaded IA item.

    Reads:
    - {identifier}_meta.json: Primary metadata (from IA API)
    - {identifier}_scandata.xml: Page count (optional)
    - Directory scan: Check for _jp2.zip, _djvu.xml, _hocr.html, .pdf, _scandata.xml

    Args:
        identifier: The Internet Archive identifier
        download_dir: Path to the directory containing downloaded files

    Returns:
        dict with metadata and file availability flags

    Raises:
        FileNotFoundError: If directory doesn't exist
        ValueError: If metadata cannot be reconstructed
    """
    if not download_dir.exists():
        raise FileNotFoundError(f"Download directory not found: {download_dir}")

    # Scan directory for available files
    files_in_dir = [f.name for f in download_dir.iterdir() if f.is_file()]

    # Detect available file types
    has_jp2 = any("_jp2.zip" in f for f in files_in_dir)
    has_hocr = any("_hocr.html" in f for f in files_in_dir)
    has_djvu_xml = any("_djvu.xml" in f for f in files_in_dir)
    has_pdf = any(".pdf" in f.lower() for f in files_in_dir)
    has_scandata = any("_scandata.xml" in f for f in files_in_dir)
    has_mets = any("_mets.xml" in f for f in files_in_dir)
    has_alto = any("_alto.xml" in f for f in files_in_dir)
    has_meta_json = any("_meta.json" in f for f in files_in_dir)

    # Try to load metadata from _meta.json (saved by fetch_ia_metadata_json)
    metadata = {}
    meta_json_path = download_dir / f"{identifier}_meta.json"
    if meta_json_path.exists():
        try:
            with meta_json_path.open("r", encoding="utf-8") as f:
                meta_data = json.load(f)
                # IA API returns {"metadata": {...}, "files": [...], ...}
                if "metadata" in meta_data:
                    metadata = meta_data.get("metadata", {})
                else:
                    metadata = meta_data
        except (json.JSONDecodeError, IOError) as e:
            print(f"  [WARN] Failed to parse _meta.json: {e}")

    # Try to get page count from scandata.xml
    total_pages = None
    scandata_path = download_dir / f"{identifier}_scandata.xml"
    if scandata_path.exists():
        try:
            tree = ET.parse(str(scandata_path))
            root = tree.getroot()
            # Count <page> elements
            pages = root.findall(".//page")
            if pages:
                total_pages = len(pages)
        except ET.ParseError as e:
            print(f"  [WARN] Failed to parse scandata.xml: {e}")

    # Build container label from metadata
    title = metadata.get("title", identifier)
    volume = metadata.get("volume", "")
    date = metadata.get("date", "")

    if volume and date:
        container_label = f"{title} Vol.{volume} ({date})"
    elif volume:
        container_label = f"{title} Vol.{volume}"
    elif date:
        container_label = f"{title} ({date})"
    else:
        container_label = title if title != identifier else identifier

    # Truncate if too long
    if len(container_label) > 255:
        container_label = container_label[:252] + "..."

    # Parse the identifier to extract structured metadata
    parsed = None
    volume_label = None
    date_start = None
    date_end = None

    if PARSER_AVAILABLE and parse_american_architect_identifier:
        try:
            parsed = parse_american_architect_identifier(identifier)
            if parsed:
                volume_label = parsed.volume_label
                # For regular issues, use issue_date for both start and end
                # For indexes, date_end stays None (indexes span a range)
                if parsed.issue_date:
                    date_start = parsed.issue_date.date() if hasattr(parsed.issue_date, 'date') else parsed.issue_date
                    if not parsed.is_index:
                        date_end = date_start
        except Exception as e:
            print(f"  [WARN] Parser failed for {identifier}: {e}")

    return {
        "identifier": identifier,
        "metadata": metadata,
        "container_label": container_label,
        "total_pages": total_pages,
        "volume_label": volume_label,
        "date_start": date_start,
        "date_end": date_end,
        "has_jp2": has_jp2,
        "has_hocr": has_hocr,
        "has_djvu_xml": has_djvu_xml,
        "has_pdf": has_pdf,
        "has_scandata": has_scandata,
        "has_mets": has_mets,
        "has_alto": has_alto,
        "has_meta_json": has_meta_json,
        "files_in_dir": files_in_dir,
        "download_dir": str(download_dir),
        "_parsed_identifier": parsed,
    }


def register_container_from_local(
    identifier: str,
    download_dir: Path,
    family: str,
    collection: str = "SIM",
) -> Optional[int]:
    """
    Register a previously downloaded container in the database.

    This is used for retroactive registration of items that were downloaded
    before database integration was added.

    Args:
        identifier: The Internet Archive identifier
        download_dir: Path to the directory containing downloaded files
        family: Publication family name (e.g., "American_Architect_family")
        collection: Collection name (default "SIM")

    Returns:
        container_id if successful, None otherwise
    """
    if not DB_AVAILABLE or hjb_db is None:
        print(f"  [WARN] Database not available, skipping registration")
        return None

    # Reconstruct metadata from local files
    try:
        local_meta = reconstruct_metadata_from_local(identifier, download_dir)
    except (FileNotFoundError, ValueError) as e:
        print(f"  [ERROR] Failed to reconstruct metadata: {e}")
        return None

    # Create IaRow for compatibility with existing registration
    row = IaRow(
        collection=collection,
        family=family,
        identifier=identifier,
    )

    # Use existing registration function with reconstructed file list
    return register_container_in_db(
        row=row,
        dest_dir=download_dir,
        downloaded_files=local_meta["files_in_dir"],
        download_status="ok",
        local_meta=local_meta,
    )


# -----------------------------
# Issue creation from parsed identifier
# -----------------------------
def create_issue_from_parsed(
    parsed: "ParsedIAIdentifier",
    family_id: int,
    title_id: Optional[int] = None,
) -> Optional[int]:
    """
    Create an issue record in issues_t from parsed identifier data.

    Args:
        parsed: ParsedIAIdentifier from the parser
        family_id: Foreign key to publication_families_t
        title_id: Optional foreign key to publication_titles_t

    Returns:
        issue_id if created/found, None on error
    """
    if not DB_AVAILABLE or hjb_db is None:
        return None

    if parsed is None:
        return None

    # Use the context manager properly
    with hjb_db.get_connection() as conn:
        if not conn:
            return None

        cursor = conn.cursor(dictionary=True)

        try:
            # Build canonical_issue_key
            canonical_key = parsed.canonical_issue_key

            # Check if issue already exists
            cursor.execute("""
                SELECT issue_id FROM issues_t
                WHERE canonical_issue_key = %s
            """, (canonical_key,))

            existing = cursor.fetchone()
            if existing:
                print(f"  [DB] Issue already exists: {canonical_key} (issue_id: {existing['issue_id']})")
                return existing['issue_id']

            # Prepare issue data
            issue_date_start = None
            issue_date_end = None
            if parsed.issue_date:
                issue_date_start = parsed.issue_date.date() if hasattr(parsed.issue_date, 'date') else parsed.issue_date
                # For regular issues, start and end are the same
                # For indexes, date_end stays None
                if not parsed.is_index:
                    issue_date_end = issue_date_start

            # Create new issue
            sql = """
                INSERT INTO issues_t
                (title_id, family_id, volume_label, volume_sort, issue_label, issue_sort,
                 issue_date_start, issue_date_end, year_published,
                 is_book_edition, is_special_issue, is_supplement, canonical_issue_key)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            values = (
                title_id,
                family_id,
                parsed.volume_label,
                parsed.volume_num,
                str(parsed.issue_num) if parsed.issue_num else ("Index" if parsed.is_index else None),
                parsed.issue_num,
                issue_date_start,
                issue_date_end,
                parsed.year,
                0,  # is_book_edition
                0,  # is_special_issue
                0,  # is_supplement
                canonical_key,
            )

            cursor.execute(sql, values)
            conn.commit()

            issue_id = cursor.lastrowid
            print(f"  [DB] Created issue: {canonical_key} (issue_id: {issue_id})")

            return issue_id

        except Exception as e:
            eprint(f"  [DB ERROR] Failed to create issue: {type(e).__name__}: {e}")
            conn.rollback()
            return None
        finally:
            cursor.close()


# -----------------------------
# Database registration
# -----------------------------
def register_container_in_db(
    row: IaRow,
    dest_dir: Path,
    downloaded_files: List[str],
    download_status: str,
    local_meta: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """
    Register the downloaded container in the MySQL database.

    Uses ACTUAL containers_t schema (with source_system, source_identifier, etc.)
    If local_meta is provided (from reconstruct_metadata_from_local), uses parsed
    identifier data for enhanced metadata (volume, dates, page count).

    Returns: container_id (int) if successful, None otherwise
    """
    if not DB_AVAILABLE or hjb_db is None:
        return None

    try:
        # Check if this container already exists (idempotency)
        existing = hjb_db.get_container_by_source("internet_archive", row.identifier)
        if existing:
            container_id = existing["container_id"]
            print(f"  [DB] Container already registered: container_id={container_id}")

            # Update download status if it changed
            if download_status == "ok":
                hjb_db.update_container_download_status(container_id, "complete", str(dest_dir))
                print(f"  [DB] Updated download_status to 'complete'")

            return container_id

        # Get or create the publication family
        family = hjb_db.get_family_by_root(row.family)
        if not family:
            # Create new family record
            family_id = hjb_db.insert_family(
                family_root=row.family,
                display_name=row.family.replace("_", " ").title(),
                family_type="journal",
            )
            print(f"  [DB] Created new family: family_id={family_id} ({row.family})")
        else:
            family_id = family["family_id"]

        # Determine which files we have (for has_* flags)
        has_jp2 = any("_jp2.zip" in f for f in downloaded_files)
        has_hocr = any("_hocr.html" in f for f in downloaded_files)
        has_djvu_xml = any("_djvu.xml" in f for f in downloaded_files)
        has_pdf = any(".pdf" in f for f in downloaded_files)
        has_scandata = any("_scandata.xml" in f for f in downloaded_files)
        has_mets = any("_mets.xml" in f for f in downloaded_files)
        has_alto = any("_alto.xml" in f for f in downloaded_files)

        # Extract enhanced metadata from local_meta if available
        volume_label = None
        date_start = None
        date_end = None
        total_pages = None
        container_label = row.identifier
        parsed = None

        if local_meta:
            volume_label = local_meta.get("volume_label")
            date_start = local_meta.get("date_start")
            date_end = local_meta.get("date_end")
            total_pages = local_meta.get("total_pages")
            container_label = local_meta.get("container_label", row.identifier)
            parsed = local_meta.get("_parsed_identifier")

        # Create the container record
        # Using ACTUAL schema parameter names
        container_id = hjb_db.insert_container(
            source_system="internet_archive",
            source_identifier=row.identifier,
            family_id=family_id,
            source_url=f"https://archive.org/details/{row.identifier}",
            title_id=None,  # Will be set later when we parse metadata
            container_label=container_label,
            container_type="journal_issue",  # Default; can be 'book_volume', etc.
            volume_label=volume_label,
            date_start=date_start,
            date_end=date_end,
            total_pages=total_pages,
            has_jp2=has_jp2,
            has_hocr=has_hocr,
            has_djvu_xml=has_djvu_xml,
            has_alto=has_alto,
            has_mets=has_mets,
            has_pdf=has_pdf,
            has_scandata=has_scandata,
            raw_input_path=str(dest_dir),
        )

        # Update download_status based on result
        if download_status == "ok":
            hjb_db.update_container_download_status(container_id, "complete", str(dest_dir))
        else:
            hjb_db.update_container_download_status(container_id, "failed", str(dest_dir))

        print(f"  [DB] Registered container: container_id={container_id}")

        # Create issue from parsed identifier if available
        if parsed is not None:
            try:
                issue_id = create_issue_from_parsed(
                    parsed=parsed,
                    family_id=family_id,
                    title_id=None,
                )

                # Create issue_containers_t mapping
                if issue_id and container_id:
                    with hjb_db.get_connection() as conn:
                        if conn:
                            cursor = conn.cursor()
                            try:
                                cursor.execute("""
                                    INSERT INTO issue_containers_t
                                    (issue_id, container_id, is_preferred, is_complete)
                                    VALUES (%s, %s, 1, 1)
                                    ON DUPLICATE KEY UPDATE is_preferred = 1
                                """, (issue_id, container_id))
                                conn.commit()
                                print(f"  [DB] Mapped issue {issue_id} to container {container_id}")
                            finally:
                                cursor.close()
            except Exception as e:
                # Don't fail container registration if issue creation fails
                eprint(f"  [DB WARN] Issue creation failed (container still registered): {e}")

        return container_id

    except Exception as e:
        eprint(f"  [DB ERROR] Failed to register container: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)
        return None

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
    enable_db: bool = True,
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
        "container_id": None,
    }

    # Obtain the IA item (network operation).
    if internetarchive is None:
        raise RuntimeError("internetarchive is not installed. Run: pip install internetarchive")

    for attempt in range(1, max_retries + 1):
        try:
            item = internetarchive.get_item(ident)
            # Listing item.files can throw intermittently; treat as retryable.
            # Combined into single comprehension for efficiency
            names = [
                f["name"] for f in item.files
                if isinstance(f, dict) and isinstance(f.get("name"), str)
            ]

            selected = choose_files_for_item(names, suffixes)
            result["selected"] = selected

            # Track which suffixes were missing to make later coverage analysis easier.
            # Use sets for O(1) membership tests
            selected_suffixes = {suf for suf in suffixes if any(n.endswith(suf) for n in selected)}
            available_suffixes = {suf for suf in suffixes if any(n.endswith(suf) for n in names)}
            result["missing_suffixes"] = [suf for suf in suffixes if suf not in selected_suffixes and suf not in available_suffixes]

            if not selected:
                result["status"] = "no_matching_files"
                result["note"] = "No requested files found for configured tiers."
                # Register even if no files (for tracking failed items)
                if enable_db:
                    container_id = register_container_in_db(row, dest_dir, [], result["status"])
                    result["container_id"] = container_id
                return result

            # Idempotency check: if final renamed files are all present, do nothing.
            if already_have_all(dest_dir, ident, selected):
                result["status"] = "skipped_already_present"
                result["note"] = "All selected files already exist in final renamed form."
                result["downloaded"] = selected  # Mark as downloaded for DB
                # Register in DB (will update if exists)
                if enable_db:
                    container_id = register_container_in_db(row, dest_dir, selected, "ok")
                    result["container_id"] = container_id
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
                if enable_db:
                    container_id = register_container_in_db(row, dest_dir, [], result["status"])
                    result["container_id"] = container_id
                return result

            # Rename into stable prefix form.
            rename_downloads_in_place(identifier_dir, ident, selected)

            # Confirm which files exist now.
            downloaded = []
            for original in selected:
                final_name = get_final_filename(original, ident)
                if (identifier_dir / final_name).exists():
                    downloaded.append(final_name)
            result["downloaded"] = downloaded

            result["status"] = "ok"
            result["note"] = f"Downloaded {len(downloaded)}/{len(selected)} selected files."

            # Fetch metadata JSON from IA API
            metadata_file = fetch_ia_metadata_json(
                identifier=row.identifier,
                dest_dir=dest_dir,
                verbose=verbose
            )
            if metadata_file:
                downloaded.append(metadata_file)
                if verbose:
                    print(f"Metadata JSON added to downloads: {metadata_file}")
          
            # Register in database
            if enable_db:
                container_id = register_container_in_db(row, dest_dir, downloaded, result["status"])
                result["container_id"] = container_id
            
            return result

        except Exception as e:
            if attempt >= max_retries:
                result["status"] = "error"
                result["note"] = f"Failed after {attempt} attempt(s): {type(e).__name__}: {e}"
                # Register failure in database
                if enable_db:
                    container_id = register_container_in_db(row, dest_dir, [], result["status"])
                    result["container_id"] = container_id
                return result
            # Exponential backoff for better retry behavior
            time.sleep(retry_sleep * (2 ** (attempt - 1)))

    # Should never reach here
    result["status"] = "error"
    result["note"] = "Unexpected fallthrough."
    return result


def execute_from_manifest(
    manifest: Dict[str, Any],
    task_id: str,
    flags_root: Path,
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Execute IA download task from watcher manifest.

    Manifest format:
    {
        "task_type": "stage1.ia_download",
        "parameters": {
            "ia_identifier": "sim_american-architect_1900-01-01_1_1",
            "family": "American_Architect_family"
        }
    }

    Args:
        manifest: Task manifest dict
        task_id: Unique task identifier
        flags_root: Path to flags directory

    Returns:
        (outputs, metrics) tuple
    """
    import yaml

    parameters = manifest.get("parameters") or {}
    if not isinstance(parameters, dict):
        raise ValueError("parameters must be an object (dict)")

    # Required: ia_identifier
    ia_identifier = parameters.get("ia_identifier")
    if not (isinstance(ia_identifier, str) and ia_identifier.strip()):
        raise KeyError("parameters.ia_identifier must be a string")
    ia_identifier = ia_identifier.strip()

    # Optional: family (default to "Unknown")
    family = parameters.get("family", "Unknown")
    if isinstance(family, str):
        family = family.strip() or "Unknown"

    # Get repo root and config
    repo_root = Path(__file__).resolve().parents[2]

    # Load config to get raw_input path
    cfg_path = repo_root / "config" / "config.yaml"
    if not cfg_path.is_file():
        cfg_path = repo_root / "config" / "config.example.yaml"

    if cfg_path.is_file():
        with cfg_path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    else:
        cfg = {}

    storage = cfg.get("storage", {})
    raw_input_path = storage.get("raw_input")

    if not raw_input_path:
        # Fallback to standard location
        raw_input_path = str(repo_root / "01_Research" / "Historical_Journals_Inputs")

    base_dir = Path(raw_input_path) / "0110_Internet_Archive"

    # Prepare IaRow
    ia_row = IaRow(
        collection="SIM",
        family=family,
        identifier=ia_identifier,
    )

    # Download
    started = time.time()
    download_result = download_one(
        row=ia_row,
        base_dir=base_dir,
        suffixes=TIER_COMPREHENSIVE_SUFFIXES,
        max_retries=3,
        retry_sleep=2.0,
        verbose=True,
        enable_db=DB_AVAILABLE,
    )
    elapsed = int(time.time() - started)

    status = download_result.get("status", "unknown")
    if status not in ["ok", "partial", "skipped_already_present"]:
        raise RuntimeError(
            f"Download failed: {status}. "
            f"Note: {download_result.get('note', 'No details')}"
        )

    outputs = [download_result.get("dest_dir", "")]
    metrics = {
        "identifier": ia_identifier,
        "family": family,
        "status": status,
        "duration_seconds": elapsed,
        "file_count": len(download_result.get("downloaded", [])),
        "container_id": download_result.get("container_id"),
        "downloaded_files": download_result.get("downloaded", []),
        "missing_suffixes": download_result.get("missing_suffixes", []),
    }

    return outputs, metrics


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
    ap.add_argument("--no-database", action="store_true", help="Disable database registration (for testing).")
    args = ap.parse_args()

    # Check database availability
    enable_db = not args.no_database
    if enable_db and not DB_AVAILABLE:
        eprint("[WARNING] Database module not available. Install with: pip install mysql-connector-python PyYAML")
        eprint("[WARNING] Continuing without database registration. Use --no-database to suppress this warning.")
        enable_db = False
    
    if enable_db:
        # Test database connection
        try:
            if not hjb_db.test_connection():
                eprint("[WARNING] Database connection test failed. Continuing without database registration.")
                enable_db = False
            else:
                print("[DB] Database connection successful")
        except Exception as e:
            eprint(f"[WARNING] Database connection error: {e}")
            eprint("[WARNING] Continuing without database registration.")
            enable_db = False

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
    print(f"[HJB] database_enabled={enable_db}")

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
                enable_db,
            )
            for row in rows
        ]
        for f in as_completed(futs):
            r = f.result()
            results.append(r)
            status = r.get("status")
            ident = r.get("identifier")
            note = r.get("note", "")
            container_id = r.get("container_id")
            
            if container_id:
                print(f"[{ident}] {status} - {note} (container_id={container_id})")
            else:
                print(f"[{ident}] {status} - {note}")

    # Optional report for later analysis / provenance.
    if args.write_report:
        rep_dir = base_dir / "_reports"
        ensure_dir(rep_dir)
        rep_path = rep_dir / f"ia_acquire_report_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
        rep_path.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[HJB] Wrote report: {rep_path}")

    # Summary
    successful = sum(1 for r in results if r.get("status") in ["ok", "skipped_already_present"])
    failed = sum(1 for r in results if r.get("status") in ["error", "download_error", "no_matching_files"])
    registered = sum(1 for r in results if r.get("container_id") is not None)
    
    print(f"\n[HJB] Summary: {successful} successful, {failed} failed, {registered} registered in database")

    # Exit 0 even if some identifiers had missing files; that's expected on IA.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
