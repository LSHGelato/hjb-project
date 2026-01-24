#!/usr/bin/env python3
"""
HJB Stage 2a - Extract Pages from Containers

Purpose:
- Populate pages_t table from IA container OCR files
- Map pages to issues using issue_containers_t
- Update processing_status_t on completion

Usage:
  python extract_pages_from_containers.py --container-id 1 2 3
  python extract_pages_from_containers.py --all-pending
  python extract_pages_from_containers.py --container-id 1 --dry-run

Workflow:
1. Get container metadata from database
2. Locate IA OCR files (raw_input_path)
3. Parse scandata.xml for page structure
4. Parse DjVu XML (or HOCR fallback) for OCR
5. Get issue mappings from issue_containers_t
6. Merge OCR + metadata + issue mapping
7. Batch insert pages into pages_t
8. Update processing_status_t (stage2_ocr_complete = 1)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.common import hjb_db
from scripts.stage2 import hocr_parser


# ============================================================================
# Database Queries
# ============================================================================

def get_pending_containers() -> List[int]:
    """
    Query containers with stage1_ingestion_complete=1 and stage2_ocr_complete=0.

    Returns: List of container_ids
    """
    query = """
        SELECT c.container_id
        FROM containers_t c
        JOIN processing_status_t p ON c.container_id = p.container_id
        WHERE p.stage1_ingestion_complete = 1
        AND p.stage2_ocr_complete = 0
        ORDER BY c.container_id
    """
    try:
        results = hjb_db.execute_query(query, fetch=True)
        return [r["container_id"] for r in results]
    except Exception as e:
        print(f"[ERROR] Failed to query pending containers: {e}", file=sys.stderr)
        return []


def get_container_metadata(container_id: int) -> Optional[Dict[str, Any]]:
    """Get container metadata from database."""
    query = "SELECT * FROM containers_t WHERE container_id = %s"
    try:
        results = hjb_db.execute_query(query, (container_id,), fetch=True)
        return results[0] if results else None
    except Exception as e:
        print(f"  [ERROR] Failed to get container metadata: {e}", file=sys.stderr)
        return None


def get_issue_mappings(container_id: int) -> List[Dict[str, Any]]:
    """
    Query issue_containers_t for page range mappings.

    Returns list of:
    {
        'issue_id': int,
        'start_page': int,  # 1-based
        'end_page': int,    # 1-based
    }
    """
    query = """
        SELECT issue_id, start_page_in_container, end_page_in_container
        FROM issue_containers_t
        WHERE container_id = %s
        ORDER BY start_page_in_container
    """
    try:
        results = hjb_db.execute_query(query, (container_id,), fetch=True)
        return [
            {
                "issue_id": r["issue_id"],
                "start_page": r["start_page_in_container"],
                "end_page": r["end_page_in_container"],
            }
            for r in results
        ]
    except Exception as e:
        print(f"  [WARNING] Failed to get issue mappings: {e}", file=sys.stderr)
        return []


# ============================================================================
# Page Processing
# ============================================================================

def determine_issue_id(
    page_index: int, mappings: List[Dict[str, Any]]
) -> Optional[int]:
    """
    Determine which issue a page belongs to based on page_index (0-based).

    Conversion: page_index (0-based) = start_page (1-based) - 1

    Args:
        page_index: 0-based page index
        mappings: List of issue mappings from issue_containers_t

    Returns:
        issue_id or None if page not mapped to any issue
    """
    # Convert 0-based page_index to 1-based for comparison
    page_num_1based = page_index + 1

    for mapping in mappings:
        if mapping["start_page"] <= page_num_1based <= mapping["end_page"]:
            return mapping["issue_id"]

    return None


def merge_page_data(
    page_index: int,
    container_id: int,
    ocr_data: hocr_parser.PageOCRData,
    metadata: hocr_parser.PageMetadata,
    issue_id: Optional[int],
) -> Dict[str, Any]:
    """
    Merge OCR data, metadata, and issue mapping into a page record.

    Args:
        page_index: 0-based page index
        container_id: Container ID
        ocr_data: OCR information
        metadata: Page metadata
        issue_id: Issue ID (or None)

    Returns:
        Dictionary ready for batch_insert_pages()
    """
    return {
        "container_id": container_id,
        "issue_id": issue_id,
        "page_index": page_index,
        "page_number_printed": metadata.page_number_printed,
        "page_label": metadata.page_label,
        "page_type": metadata.page_type,
        "is_cover": 1 if metadata.page_type == "cover" else 0,
        "is_plate": 1 if metadata.page_type == "plate" else 0,
        "is_blank": 1 if metadata.page_type == "blank" else 0,
        "is_supplement": 0,  # Default: not a supplement
        "has_ocr": 1,
        "ocr_source": ocr_data.ocr_source,
        "ocr_confidence": ocr_data.ocr_confidence,
        "ocr_word_count": ocr_data.ocr_word_count,
        "ocr_char_count": ocr_data.ocr_char_count,
        "ocr_text": ocr_data.ocr_text,
        "image_dpi": 300,
        # Note: is_manually_verified will be added when the schema migration is applied
    }


def locate_ocr_files(raw_input_path: str, identifier: str) -> Dict[str, Optional[Path]]:
    """
    Locate OCR files for a container.

    Returns:
    {
        'djvu_xml': Path or None,
        'hocr_html': Path or None,
        'scandata': Path or None,
    }
    """
    base_path = Path(raw_input_path)

    return {
        "djvu_xml": base_path / f"{identifier}_djvu.xml"
        if (base_path / f"{identifier}_djvu.xml").exists()
        else None,
        "hocr_html": base_path / f"{identifier}_hocr.html"
        if (base_path / f"{identifier}_hocr.html").exists()
        else None,
        "scandata": base_path / f"{identifier}_scandata.xml"
        if (base_path / f"{identifier}_scandata.xml").exists()
        else None,
    }


def process_container(
    container_id: int, dry_run: bool = False
) -> Dict[str, Any]:
    """
    Process a single container: extract pages and populate pages_t.

    Args:
        container_id: Container ID to process
        dry_run: If True, don't write to database

    Returns:
        {
            'container_id': int,
            'pages_inserted': int,
            'ocr_source': str,
            'status': str,  # 'success', 'error', or 'skipped'
            'error_message': str or None,
        }
    """
    print(f"\n[Container {container_id}] Processing...")

    result = {
        "container_id": container_id,
        "pages_inserted": 0,
        "ocr_source": None,
        "status": "skipped",
        "error_message": None,
    }

    # 1. Get container metadata
    container = get_container_metadata(container_id)
    if not container:
        result["status"] = "error"
        result["error_message"] = "Container not found in database"
        print(f"  [ERROR] {result['error_message']}")
        return result

    identifier = container["source_identifier"]
    raw_input_path = container.get("raw_input_path")

    if not raw_input_path:
        result["status"] = "error"
        result["error_message"] = "raw_input_path not set"
        print(f"  [ERROR] {result['error_message']}")
        return result

    print(f"  [Container] identifier={identifier}, path={raw_input_path}")

    # 2. Locate OCR files
    ocr_files = locate_ocr_files(raw_input_path, identifier)
    print(
        f"  [OCR Files] "
        f"djvu_xml={ocr_files['djvu_xml'] is not None}, "
        f"hocr_html={ocr_files['hocr_html'] is not None}, "
        f"scandata={ocr_files['scandata'] is not None}"
    )

    # 3. Parse scandata.xml for page structure
    page_metadata_list: List[hocr_parser.PageMetadata] = []
    if ocr_files["scandata"]:
        page_metadata_list = hocr_parser.parse_scandata_xml(ocr_files["scandata"])
        print(f"  [Scandata] Parsed {len(page_metadata_list)} pages")
    else:
        print(f"  [WARNING] scandata.xml not found, will use defaults")

    # 4. Parse OCR (DjVu preferred, HOCR fallback)
    page_ocr_list: List[hocr_parser.PageOCRData] = []
    ocr_source = None

    if ocr_files["djvu_xml"]:
        page_ocr_list = hocr_parser.parse_djvu_xml(ocr_files["djvu_xml"])
        ocr_source = "ia_djvu"
        print(f"  [OCR] Using DjVu XML, extracted {len(page_ocr_list)} pages")
    elif ocr_files["hocr_html"]:
        page_ocr_list = hocr_parser.parse_hocr_html(ocr_files["hocr_html"])
        ocr_source = "ia_hocr"
        print(f"  [OCR] Using HOCR HTML (fallback), extracted {len(page_ocr_list)} pages")
    else:
        result["status"] = "error"
        result["error_message"] = "No OCR files found (neither DjVu XML nor HOCR HTML)"
        print(f"  [ERROR] {result['error_message']}")
        return result

    result["ocr_source"] = ocr_source

    # 5. Get issue mappings
    issue_mappings = get_issue_mappings(container_id)
    print(f"  [Issues] Found {len(issue_mappings)} issue mapping(s)")

    # 6. Merge data and build page records
    pages_to_insert: List[Dict[str, Any]] = []

    # Ensure we have metadata for all pages (use defaults if scandata missing)
    while len(page_metadata_list) < len(page_ocr_list):
        page_index = len(page_metadata_list)
        page_metadata_list.append(
            hocr_parser.PageMetadata(
                page_index=page_index,
                page_number_printed=None,
                page_label=f"page_{page_index}",
                page_type="content",
            )
        )

    # Build page records
    for page_index, ocr_data in enumerate(page_ocr_list):
        # Get corresponding metadata (or use default)
        metadata = (
            page_metadata_list[page_index]
            if page_index < len(page_metadata_list)
            else hocr_parser.PageMetadata(
                page_index=page_index,
                page_number_printed=None,
                page_label=f"page_{page_index}",
                page_type="content",
            )
        )

        # Determine issue_id
        issue_id = determine_issue_id(page_index, issue_mappings)

        # Merge data
        page_dict = merge_page_data(
            page_index=page_index,
            container_id=container_id,
            ocr_data=ocr_data,
            metadata=metadata,
            issue_id=issue_id,
        )

        pages_to_insert.append(page_dict)

    print(f"  [Merged] Prepared {len(pages_to_insert)} page records for insertion")

    # 7. Batch insert pages
    if dry_run:
        print(f"  [DRY RUN] Would insert {len(pages_to_insert)} pages")
        result["status"] = "success"
        result["pages_inserted"] = len(pages_to_insert)
        return result

    try:
        rows_inserted = hjb_db.batch_insert_pages(pages_to_insert)
        print(f"  [DB] Inserted {rows_inserted} pages into pages_t")

        # 8. Update processing_status_t
        hjb_db.update_stage_completion(
            container_id=container_id, stage="stage2_ocr", complete=True
        )
        print(f"  [DB] Marked stage2_ocr_complete")

        result["status"] = "success"
        result["pages_inserted"] = rows_inserted
        return result

    except Exception as e:
        result["status"] = "error"
        result["error_message"] = str(e)
        print(f"  [ERROR] Failed to insert pages: {e}", file=sys.stderr)

        # Mark stage as failed
        try:
            hjb_db.update_stage_completion(
                container_id=container_id,
                stage="stage2_ocr",
                complete=False,
                error_message=str(e),
            )
        except Exception as e2:
            print(f"  [WARNING] Failed to update error status: {e2}", file=sys.stderr)

        return result


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Extract pages from IA containers to pages_t"
    )
    parser.add_argument(
        "--container-id",
        type=int,
        nargs="+",
        help="Process specific container ID(s)",
    )
    parser.add_argument(
        "--all-pending",
        action="store_true",
        help="Process all containers with stage1 complete and stage2 incomplete",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode (no database writes)",
    )

    args = parser.parse_args()

    # Determine which containers to process
    container_ids: List[int] = []

    if args.container_id:
        container_ids = args.container_id
    elif args.all_pending:
        print("[Info] Querying pending containers...")
        container_ids = get_pending_containers()
        if not container_ids:
            print("[INFO] No pending containers found")
            return 0
    else:
        print("[ERROR] Must specify --container-id or --all-pending", file=sys.stderr)
        parser.print_help()
        return 1

    print(f"[Info] Processing {len(container_ids)} container(s)")

    # Process containers
    results = []
    for container_id in container_ids:
        result = process_container(container_id, dry_run=args.dry_run)
        results.append(result)

    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    total_pages = 0
    successful = 0
    failed = 0

    for result in results:
        status_str = result["status"].upper()
        if result["status"] == "success":
            successful += 1
            total_pages += result["pages_inserted"]
            print(
                f"✓ Container {result['container_id']}: "
                f"{result['pages_inserted']} pages (source: {result['ocr_source']})"
            )
        elif result["status"] == "error":
            failed += 1
            print(
                f"✗ Container {result['container_id']}: "
                f"ERROR - {result['error_message']}"
            )
        else:
            print(f"- Container {result['container_id']}: SKIPPED")

    print(f"\nTotal: {successful} successful, {failed} failed, {total_pages} pages inserted")

    if args.dry_run:
        print("[DRY RUN] No database writes performed")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
