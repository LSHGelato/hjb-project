#!/usr/bin/env python3
"""
Test script for Stage 2 implementation

Tests:
1. Database connection and batch_insert_pages method
2. OCR parser (hocr_parser module)
3. Extraction script CLI and logic
4. Full integration test (dry-run)
"""

import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.common import hjb_db
from scripts.stage2 import hocr_parser
from scripts.stage2 import extract_pages_from_containers


def test_database_connection():
    """Test 1: Database connection and batch_insert_pages method"""
    print("\n" + "=" * 70)
    print("TEST 1: Database Connection and batch_insert_pages()")
    print("=" * 70)

    try:
        # Test connection
        if hjb_db.test_connection():
            print("[OK] Database connection successful")
        else:
            print("[FAIL] Database connection failed")
            return False

        # Test batch_insert_pages with empty list
        result = hjb_db.batch_insert_pages([])
        if result == 0:
            print("[OK] batch_insert_pages handles empty list correctly")
        else:
            print(f"[FAIL] Expected 0 rows for empty list, got {result}")
            return False

        return True
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False


def test_ocr_parser():
    """Test 2: OCR parser module"""
    print("\n" + "=" * 70)
    print("TEST 2: OCR Parser Module")
    print("=" * 70)

    try:
        # Test DjVu XML parser with non-existent file
        result = hocr_parser.parse_djvu_xml(Path("/nonexistent/file.xml"))
        if result == []:
            print("[OK] parse_djvu_xml handles missing files gracefully")
        else:
            print("[FAIL] Expected empty list for missing file")
            return False

        # Test HOCR HTML parser with non-existent file
        result = hocr_parser.parse_hocr_html(Path("/nonexistent/file.html"))
        if result == []:
            print("[OK] parse_hocr_html handles missing files gracefully")
        else:
            print("[FAIL] Expected empty list for missing file")
            return False

        # Test scandata parser with non-existent file
        result = hocr_parser.parse_scandata_xml(Path("/nonexistent/file.xml"))
        if result == []:
            print("[OK] parse_scandata_xml handles missing files gracefully")
        else:
            print("[FAIL] Expected empty list for missing file")
            return False

        # Test page type mapping
        test_cases = [
            ("Cover Page", "cover"),
            ("Normal", "content"),
            ("Blank", "blank"),
            ("Contents", "toc"),
            ("Index", "index"),
            ("Advertisement", "advertisement"),
            ("Plate", "plate"),
            (None, "content"),
            ("Unknown Type", "content"),
        ]

        all_ok = True
        for scandata_type, expected in test_cases:
            result = hocr_parser.map_page_type(scandata_type)
            if result != expected:
                print(f"[FAIL] map_page_type('{scandata_type}') = '{result}', expected '{expected}'")
                all_ok = False

        if all_ok:
            print("[OK] map_page_type works correctly for all test cases")
        else:
            return False

        return True
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False


def test_extraction_script():
    """Test 3: Extraction script functions"""
    print("\n" + "=" * 70)
    print("TEST 3: Extraction Script Functions")
    print("=" * 70)

    try:
        # Test determine_issue_id
        mappings = [
            {"issue_id": 1, "start_page": 1, "end_page": 14},
            {"issue_id": 2, "start_page": 15, "end_page": 28},
        ]

        test_cases = [
            (0, 1),   # page_index 0 = page 1-based (in issue 1)
            (5, 1),   # page_index 5 = page 6-based (in issue 1)
            (13, 1),  # page_index 13 = page 14-based (in issue 1)
            (14, 2),  # page_index 14 = page 15-based (in issue 2)
            (27, 2),  # page_index 27 = page 28-based (in issue 2)
            (28, None),  # page_index 28 = page 29-based (not mapped)
        ]

        all_ok = True
        for page_index, expected_issue_id in test_cases:
            result = extract_pages_from_containers.determine_issue_id(page_index, mappings)
            if result != expected_issue_id:
                print(f"[FAIL] determine_issue_id({page_index}) = {result}, expected {expected_issue_id}")
                all_ok = False

        if all_ok:
            print("[OK] determine_issue_id works correctly for all test cases")
        else:
            return False

        # Test merge_page_data
        ocr_data = hocr_parser.PageOCRData(
            page_index=0,
            ocr_text="Test OCR text",
            ocr_confidence=0.95,
            ocr_word_count=3,
            ocr_char_count=13,
            ocr_source="ia_djvu",
        )

        metadata = hocr_parser.PageMetadata(
            page_index=0,
            page_number_printed="1",
            page_label="page_1",
            page_type="content",
        )

        result = extract_pages_from_containers.merge_page_data(
            page_index=0,
            container_id=1,
            ocr_data=ocr_data,
            metadata=metadata,
            issue_id=1,
        )

        # Check required fields
        required_fields = [
            "container_id",
            "issue_id",
            "page_index",
            "page_type",
            "is_cover",
            "is_blank",
            "has_ocr",
            "ocr_source",
            "ocr_text",
            "image_dpi",
        ]

        all_ok = True
        for field in required_fields:
            if field not in result:
                print(f"[FAIL] merge_page_data missing field: {field}")
                all_ok = False

        if all_ok and result["container_id"] == 1 and result["page_type"] == "content":
            print("[OK] merge_page_data creates correct page records")
        else:
            return False

        return True
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False


def test_query_functions():
    """Test 4: Database query functions"""
    print("\n" + "=" * 70)
    print("TEST 4: Database Query Functions")
    print("=" * 70)

    try:
        # Get pending containers
        pending = extract_pages_from_containers.get_pending_containers()
        print(f"[OK] Found {len(pending)} pending container(s) for stage2")

        if len(pending) > 0:
            # Get container metadata for first pending
            container = extract_pages_from_containers.get_container_metadata(pending[0])
            if container:
                print(f"[OK] Retrieved container metadata for container {pending[0]}")

                # Get issue mappings
                mappings = extract_pages_from_containers.get_issue_mappings(pending[0])
                print(f"[OK] Retrieved {len(mappings)} issue mapping(s) for container {pending[0]}")
            else:
                print(f"[FAIL] Could not retrieve container metadata for container {pending[0]}")
                return False

        return True
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("HJB Stage 2 Implementation - Test Suite")
    print("=" * 70)

    results = {
        "Database Connection": test_database_connection(),
        "OCR Parser": test_ocr_parser(),
        "Extraction Script": test_extraction_script(),
        "Database Queries": test_query_functions(),
    }

    # Print summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\nAll tests passed! Implementation is ready for verification.")
        return 0
    else:
        print(f"\n{total - passed} test(s) failed. Review above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
