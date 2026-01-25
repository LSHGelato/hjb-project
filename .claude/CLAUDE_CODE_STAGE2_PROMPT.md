# Claude Code: Stage 2 Phase 2a - OCR Extraction Implementation

## CONTEXT

**Project**: HJB (Historical Journals & Books)

**Current Status**:
- Stage 1 complete: 53 containers downloaded, registered in `containers_t`, `issues_t`, `issue_containers_t`
- `processing_status_t` now populated with `stage1_ingestion_complete=1` and `stage1_completed_at` set
- Ready to begin Stage 2: OCR extraction and page segmentation

**Infrastructure**:
- Database: `raneywor_hjbproject` on HostGator
- NAS: `\\RaneyHQ\Michael\02_Projects\Historical_Journals_and_Books\Raw_Input\0110_Internet_Archive\SIM\American_Architect_family\[identifier]\`
- GitHub: https://github.com/LSHGelato/hjb-project (main branch)

---

## TASK 1: Update Stage 1 Scripts

Update `scripts/stage1/ia_acquire.py` and any related Stage 1 scripts to:

- After successful container registration in `containers_t`, automatically create a `processing_status_t` entry
- Set `stage1_ingestion_complete = 1` and `stage1_completed_at = NOW()`
- Set `stage2_ocr_complete = 0`, `stage2_segmentation_complete = 0`
- Update `processing_status_t.download_status` and `validation_status` appropriately during download/validation

---

## TASK 2: Build Phase 2a - OCR Extraction

### Create: `scripts/stage2/hocr_parser.py`

**Purpose**: Parse HOCR HTML, DjVu XML, and scandata.xml files from IA containers

**Functionality**:
- Parse HOCR HTML files to extract OCR text, confidence scores, layout info
- Parse DjVu XML files to extract OCR text (fallback if HOCR unavailable)
- Parse scandata.xml for page numbering, labels, and page types
- Return structured page data ready for database insertion

**OCR Priority**: 
1. DjVu XML (first choice—better accuracy)
2. HOCR HTML (fallback)

**Output**: Dictionary/dataclass with fields:
- `ocr_text` (full page text)
- `ocr_confidence` (0.00-1.00, averaged from word-level scores if available)
- `ocr_word_count` (count of words in OCR)
- `ocr_char_count` (count of characters in OCR)
- `page_label` (as printed: i, ii, 1, 2, etc.)
- `page_type` (content, cover, advertisement, blank, etc.)
- `ocr_source` (ia_djvu or ia_hocr)

### Create: `scripts/stage2/extract_pages_from_containers.py`

**Purpose**: Main script to populate `pages_t` for given containers

**Workflow**:
1. Accept container ID(s) as argument (or `--all-pending` flag)
2. For each container:
   - Fetch container metadata from database
   - Locate IA OCR files in Raw_Input directory
   - Parse OCR using `hocr_parser.py` (DjVu first, HOCR fallback)
   - Parse scandata.xml for page structure
   - For each page:
     - Determine which issue it belongs to using `issue_containers_t` mappings
     - Create `pages_t` record with all required fields
   - Batch insert pages into database
   - Update `processing_status_t.stage2_ocr_complete = 1` and `stage2_completed_at = NOW()`

**Database Operations**:
- Add `batch_insert_pages(pages: list[dict]) -> int` to `scripts/common/hjb_db.py` if not present
- Query `issue_containers_t` to map page ranges to issues
- Update `processing_status_t` after completion

**`pages_t` Field Mapping**:
```
page_id              → auto-increment
container_id         → from input
issue_id             → from issue_containers_t mapping
page_index           → 0-based (0, 1, 2, ...) — SEQUENTIAL ORDER
page_number_printed  → from scandata (i, ii, 1, 2, etc.)
page_label           → same as page_number_printed
page_type            → from scandata (content, cover, advertisement, blank, etc.)
is_cover             → 1 if page_type = cover, else 0
is_blank             → 1 if page_type = blank, else 0
has_ocr              → 1
ocr_source           → ia_djvu or ia_hocr
ocr_confidence       → 0.00-1.00 (if available from OCR source)
ocr_word_count       → from hocr_parser output
ocr_char_count       → from hocr_parser output
ocr_text             → full page text (MEDIUMTEXT, unreviewed)
is_manually_verified → 0 (operator has not reviewed yet)
image_file_path      → path to JP2 or derived image (optional for now)
image_dpi            → 300 (IA standard, or extract from metadata)
```

### Critical Implementation Details

**Page Numbering Convention**:
- `pages_t.page_index`: **0-based** (0, 1, 2, ...)
  - First page in container: `page_index = 0`
  - Sequential within container for ordering
  
- `issue_containers_t.start_page_in_container` / `end_page_in_container`: **1-based** (1, 2, 3, ...)
  - First page: `start_page_in_container = 1`
  - Last page: `end_page_in_container = N`

**Conversion Formula**:
```
pages_t.page_index = issue_containers_t.start_page_in_container - 1
```

Example: If `issue_containers_t` says pages 1-14 belong to issue X:
- `pages_t` records for those 14 pages have `page_index` 0-13 (0-based)
- All get `issue_id = X`

**Issue Mapping via `issue_containers_t`**:
- Query: `SELECT * FROM issue_containers_t WHERE container_id = ? ORDER BY start_page_in_container`
- For each mapping: pages with `page_index` in range `[start_page - 1, end_page - 1]` get that `issue_id`

**is_manually_verified Field**:
- Add to `pages_t` if not present (default 0)
- Set to 0 on initial insert (OCR is unreviewed)
- Operator can set to 1 after manual review

**Testing Scope**:
- Start with containers 1-3 only (44 main pages from Volume 1)
- Verify output before scaling to all 53 containers

---

## EXPECTED OUTPUT AFTER TESTING

- ~44 `pages_t` records created from containers 1-3
- All pages correctly linked to issues via `issue_containers_t` mappings
- `page_index` 0-based, `issue_containers_t` page ranges 1-based, conversion correct
- `is_manually_verified = 0` for all new pages
- `processing_status_t.stage2_ocr_complete = 1` for processed containers
- `processing_status_t.stage2_completed_at` populated with completion timestamp

---

## GIT COMMITS

Commit each file with Conventional Commits format:
- `feat(hjb): add hocr_parser.py utility for IA OCR parsing`
- `feat(hjb): add extract_pages_from_containers.py for Stage 2a`
- `feat(hjb): update ia_acquire.py to create processing_status_t entries`
- `feat(hjb): add batch_insert_pages() to hjb_db.py`

Include descriptive commit messages explaining what changed and why.

---

## NOTES FOR CLAUDE CODE

- Use `scripts/common/hjb_db.py` for database operations
- Use `scripts/stage1/parse_american_architect_ia.py` as reference for IA identifier parsing if needed
- Handle missing OCR files gracefully (log warning, skip or fallback)
- Ensure all database inserts use parameterized queries (prevent SQL injection)
- Test locally on containers 1-3 before committing; verify database integrity
