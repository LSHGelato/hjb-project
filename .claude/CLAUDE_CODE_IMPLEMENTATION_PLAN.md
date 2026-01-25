# HJB Hybrid Schema Implementation - Claude Code Plan

**Status:** Ready for Claude Code execution  
**Start Date:** 2026-01-25  
**Target Completion:** 2026-01-31 (6 days)  
**Approach:** Systematic implementation with GitHub integration

---

## Phase Overview

```
Phase 1: Database Migrations (Tue-Wed Jan 28-29)
  ├─ Create migration SQL files
  ├─ Test migrations locally
  └─ Document changes in CHANGELOG

Phase 2: Script Refactoring (Wed-Thu Jan 29-30)
  ├─ Refactor extract_pages_from_containers.py
  │  ├─ Add JP2 → JPEG extraction
  │  ├─ Add OCR file copying to page pack
  │  ├─ Generate manifest JSON
  │  └─ Populate page_assets_t
  ├─ Create segment_from_page_packs.py (new)
  └─ Update scripts for hocr_parser.py (if needed)

Phase 3: Backfill & Testing (Thu-Fri Jan 30-31)
  ├─ Run extraction backfill for containers 1-53
  ├─ Verify page_assets_t populated correctly
  ├─ Test segmentation on Container 1
  └─ Manual QA workflow validation

Phase 4: QA Tooling (Fri Feb 1)
  ├─ Generate visual QA aids script
  ├─ Create SQL correction templates
  └─ Document operator workflow

Phase 5: Documentation & Commit (Fri-Mon Jan 31 - Feb 3)
  ├─ Update README.md
  ├─ Create STAGE2_HYBRID_SCHEMA.md guide
  ├─ Commit all changes with Conventional Commits
  └─ Push to GitHub
```

---

## Detailed Tasks for Claude Code

### PHASE 1: DATABASE MIGRATIONS

#### Task 1.1: Create Migration SQL Files

**File:** `database/migrations/004_hybrid_schema_page_assets.sql`

Content needed:
```sql
-- Create page_assets_t
CREATE TABLE page_assets_t (
  asset_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  page_id INT UNSIGNED NOT NULL UNIQUE,
  FOREIGN KEY (page_id) REFERENCES pages_t(page_id),
  ocr_payload_path VARCHAR(512),
  ocr_payload_hash CHAR(64),
  ocr_payload_format ENUM('djvu_xml', 'hocr', 'alto', 'tesseract_json'),
  image_extracted_path VARCHAR(512),
  image_extracted_format VARCHAR(32),
  image_extracted_hash CHAR(64),
  image_source VARCHAR(64),
  image_dpi_normalized INT,
  image_rotation_applied INT,
  was_deskewed TINYINT(1),
  was_binarized TINYINT(1),
  extracted_at DATETIME NOT NULL,
  extraction_script_version VARCHAR(64),
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  INDEX (page_id),
  INDEX (ocr_payload_hash),
  INDEX (image_extracted_hash)
);

-- Create page_pack_manifests_t
CREATE TABLE page_pack_manifests_t (
  manifest_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  container_id INT UNSIGNED NOT NULL,
  FOREIGN KEY (container_id) REFERENCES containers_t(container_id),
  manifest_path VARCHAR(512) NOT NULL,
  manifest_hash CHAR(64),
  manifest_version VARCHAR(32),
  total_pages INT,
  page_ids_included JSON,
  ocr_sources_used JSON,
  image_extraction_params JSON,
  created_at DATETIME NOT NULL,
  created_by VARCHAR(128),
  description VARCHAR(255),
  is_active TINYINT(1) DEFAULT 1,
  superseded_by INT UNSIGNED,
  FOREIGN KEY (superseded_by) REFERENCES page_pack_manifests_t(manifest_id),
  INDEX (container_id),
  INDEX (manifest_hash),
  UNIQUE (manifest_path)
);

-- Alter pages_t
ALTER TABLE pages_t 
ADD COLUMN ocr_text_snippet VARCHAR(500) AFTER ocr_text,
ADD COLUMN ocr_char_count INT AFTER ocr_text_snippet,
ADD COLUMN is_spread TINYINT(1) DEFAULT 0,
ADD COLUMN is_spread_with INT UNSIGNED,
ADD CONSTRAINT fk_is_spread_with FOREIGN KEY (is_spread_with) REFERENCES pages_t(page_id);

-- Alter work_occurrences_t
ALTER TABLE work_occurrences_t 
MODIFY COLUMN image_references JSON,
ADD COLUMN image_extraction_params JSON AFTER image_references;

-- Update schema_version_t
INSERT INTO schema_version_t (version_number, migration_name, applied_at)
VALUES (4, '004_hybrid_schema_page_assets', NOW());
```

**Task:** Write this SQL file to GitHub, test it locally (if possible), and ensure it's idempotent.

#### Task 1.2: Test & Document Migration

**File:** Database test script (optional, but recommended)

Test:
- Create tables
- Verify foreign keys
- Check indexes exist
- Ensure existing data not affected

Document:
- What changed (new tables, new columns, etc.)
- Why (links to analysis document)
- How to apply: `mysql -u [user] -p [db] < 004_hybrid_schema_page_assets.sql`
- Rollback plan: `DROP TABLE page_assets_t; DROP TABLE page_pack_manifests_t; ALTER TABLE pages_t DROP COLUMN ...` (document exact rollback)

---

### PHASE 2: SCRIPT REFACTORING

#### Task 2.1: Refactor `extract_pages_from_containers.py`

**Current Status:** Extracts OCR text → `pages_t.ocr_text`

**New Behavior:**
1. Extract JP2s from `raw_input/[container_id]/[id]_jp2.zip`
2. Convert each JP2 to JPEG (quality 90, 300 DPI)
3. Copy OCR files (HOCR/DjVu) to page pack
4. Populate `pages_t.ocr_text_snippet` (first 500 chars)
5. Populate `pages_t.ocr_char_count`
6. Create `page_assets_t` rows
7. Generate `page_pack_manifests_t` entry
8. Create manifest.json in 0220_Page_Packs/[container_id]/

**Key Changes:**
- Input: container_id, raw_input_path, output_page_pack_path
- Output: page pack directory with images/, ocr/, manifest.json
- New dependencies: PIL/Pillow (image conversion), json module
- Error handling: Gracefully skip problematic pages, log issues

**Checklist:**
- [ ] Read original script to understand structure
- [ ] Add image extraction logic (JP2 → JPEG)
- [ ] Add OCR file copying logic
- [ ] Add `page_assets_t` insertion logic
- [ ] Add manifest JSON generation
- [ ] Test on Container 1 (14 pages)
- [ ] Verify output structure and hashes

#### Task 2.2: Create `segment_from_page_packs.py` (NEW)

**Purpose:** Read page pack → apply segmentation heuristics → output works

**Interface:**
```
python segment_from_page_packs.py <manifest_path> [--output-dir <path>]
```

**Logic:**
1. Load manifest.json
2. For each page in order:
   - Load OCR file (HOCR/DjVu XML)
   - Load page image
   - Parse OCR text for dividing lines (heuristic: lines with 70%+ dashes/equals)
   - Detect headlines (all-caps, short lines)
   - Clean OCR (remove single-char noise, lines without letters)
3. Group pages into works based on boundaries
4. Output segmentation JSON with work boundaries + page ranges
5. Insert to `works_t` and `work_occurrences_t` (if DB flag set)

**Heuristics to Include:**
```python
def is_dividing_line(line):
    """Detect separator lines (---, ===, etc.)"""
    stripped = line.strip()
    if len(stripped) < 5: return False
    sep_chars = stripped.count('-') + stripped.count('=') + stripped.count('_')
    return sep_chars / len(stripped) > 0.7

def is_headline(line):
    """Detect article titles"""
    if len(line) > 80: return False  # Too long
    if line.isupper(): return True   # All caps
    if line.istitle(): return True   # Title case
    return False

def clean_ocr_text(text):
    """Remove noise from OCR"""
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        if len(line.strip()) <= 1: continue
        if not any(c.isalpha() for c in line): continue
        cleaned.append(line)
    return '\n'.join(cleaned)
```

**Checklist:**
- [ ] Parse manifest.json
- [ ] Load OCR/image files for each page
- [ ] Implement dividing-line detection
- [ ] Implement headline detection
- [ ] Group pages into work candidates
- [ ] Generate output JSON
- [ ] Test on Container 1 manually
- [ ] Verify page ranges match expected articles

#### Task 2.3: Update `hocr_parser.py` (if needed)

Check if existing HOCR parser needs updates to support new page pack structure. Likely no changes needed, but verify coordinates/layout parsing still works.

---

### PHASE 3: BACKFILL & TESTING

#### Task 3.1: Run Extraction Backfill

**For Containers 1-53:**

```bash
for container_id in {1..53}; do
  python scripts/stage2/extract_pages_from_containers.py $container_id
done
```

**Verification:**
- [ ] All 53 page packs created
- [ ] manifest.json exists for each
- [ ] All ~1,200 images extracted
- [ ] page_assets_t populated
- [ ] page_pack_manifests_t populated

**Timeline:** ~90 minutes for all containers

#### Task 3.2: Test Segmentation on Container 1

```bash
python scripts/stage2/segment_from_page_packs.py \
  0220_Page_Packs/1/manifest.json \
  --output-dir test_segmentation_1
```

**Verify Output:**
- [ ] Segmentation JSON created
- [ ] Work boundaries identified (~10-15 for Issue 1)
- [ ] Page ranges correct
- [ ] Can manually inspect and adjust if needed

#### Task 3.3: Operator Manual QA (Container 1)

**Process:**
1. Open 0220_Page_Packs/1/images/ — view page JPEGs
2. Read segmentation JSON — see detected work boundaries
3. Verify accuracy: do boundaries match article breaks?
4. Mark spreads: if pages 3-4 are two-page plate, mark is_spread
5. Flag OCR issues: if any page has poor OCR, note
6. Set is_manually_verified=1 on validated pages

**Expected Time:** 30-45 min for 14 pages + manual DB updates

---

### PHASE 4: QA TOOLING

#### Task 4.1: Generate Visual QA Aids Script

**Script:** `scripts/stage2/generate_qa_report.py`

**Output:** HTML/CSV showing:
- Page thumbnail grid
- Detected work boundaries overlayed
- OCR text snippets
- Page types (content/cover/blank/ad)

**Usage:**
```bash
python scripts/stage2/generate_qa_report.py 1 --output qa_report_container_1.html
```

#### Task 4.2: SQL Correction Templates

**File:** `scripts/stage2/sql_corrections_template.sql`

Pre-built snippets for:
```sql
-- Merge two works
UPDATE work_occurrences_t SET work_id = [CANONICAL_ID] WHERE work_id = [DUPLICATE_ID];
DELETE FROM works_t WHERE work_id = [DUPLICATE_ID];

-- Split a work at a page boundary
-- (Operator manually creates new work, updates occurrence start/end)

-- Mark a spread
UPDATE pages_t SET is_spread = 1, is_spread_with = [PARTNER_PAGE_ID] WHERE page_id = [PAGE_ID];

-- Flag page for manual OCR
UPDATE pages_t SET notes = 'Poor OCR, needs manual correction' WHERE page_id = [PAGE_ID];
```

---

### PHASE 5: DOCUMENTATION & COMMIT

#### Task 5.1: Update README.md

Add section:
```markdown
## Stage 2b: Segmentation with Hybrid Schema

As of [date], Stage 2 uses a hybrid architecture:
- Images extracted from JP2 → JPEG and stored in `0220_Page_Packs/`
- OCR payloads (HOCR/DjVu XML) stored in page pack
- Database tracks pointers via `page_assets_t` and manifests
- Segmentation reads from page packs, outputs to DB

### Running Stage 2a (Extraction)
```bash
python scripts/stage2/extract_pages_from_containers.py <container_id>
```

### Running Stage 2b (Segmentation)
```bash
python scripts/stage2/segment_from_page_packs.py \
  0220_Page_Packs/<container_id>/manifest.json
```

See `STAGE2_HYBRID_SCHEMA.md` for detailed guide.
```

#### Task 5.2: Create `STAGE2_HYBRID_SCHEMA.md` Guide

Document:
- Architecture overview (hybrid DB + page packs)
- Page pack structure and manifest format
- Extraction process (JP2 → JPEG, OCR copying)
- Segmentation heuristics and workflow
- Operator QA process
- Troubleshooting (common issues and fixes)
- Future enhancements (ML, compression, etc.)

#### Task 5.3: Git Commits

**Commit 1: Schema Migrations**
```
commit: feat(hjb): add hybrid schema tables (page_assets_t, page_pack_manifests_t)

- Create page_assets_t for tracking OCR and image file pointers
- Create page_pack_manifests_t for versioning and audit
- Modify pages_t: add ocr_text_snippet, ocr_char_count, is_spread fields
- Modify work_occurrences_t: make image_references JSON type
- Add migration script 004_hybrid_schema_page_assets.sql
- Update schema_version_t to version 4

See: HYBRID_SCHEMA_DECISION_PACKAGE.md for design rationale
```

**Commit 2: Extract Script Refactoring**
```
commit(hjb/stage2): refactor extract_pages_from_containers.py for page packs

- Add JP2 → JPEG extraction (quality 90, 300 DPI)
- Add OCR file copying to page pack directories
- Implement page_assets_t population
- Generate manifest.json per page pack
- Update pages_t with snippet and char count
- Add error handling and logging

Tested on containers 1-3 successfully.
```

**Commit 3: New Segmentation Script**
```
commit(hjb/stage2): add segment_from_page_packs.py for Stage 2b

- Read page packs (manifest.json + images + OCR)
- Implement dividing-line detection heuristic
- Implement headline detection
- Group pages into work candidates
- Output segmentation JSON
- Support committing to works_t/work_occurrences_t

Includes unit tests for heuristics.
```

**Commit 4: QA Tooling**
```
commit(hjb/stage2): add QA tooling and documentation

- Generate QA visual aids (HTML reports with boundaries overlayed)
- Add SQL correction templates for common operator fixes
- Create STAGE2_HYBRID_SCHEMA.md guide
- Update README.md with Stage 2b workflow
- Add troubleshooting section

Supports operator manual QA workflow.
```

All commits use `feat(hjb/stage2): ...` format (Conventional Commits).

---

## Implementation Checklist

### Week 1 (Jan 28-31)

**Tuesday Jan 28:**
- [ ] Claude Code: Write migration SQL files
- [ ] Claude Code: Test migrations (conceptually)
- [ ] Manual: Apply migrations to test DB

**Wednesday Jan 29:**
- [ ] Claude Code: Refactor extract_pages_from_containers.py
- [ ] Claude Code: Test on Containers 1-3 (verify output structure)
- [ ] Manual: Backfill all 53 containers (90 min runtime)

**Thursday Jan 30:**
- [ ] Claude Code: Create segment_from_page_packs.py
- [ ] Claude Code: Test segmentation on Container 1
- [ ] Manual: Verify segmentation output (boundaries match articles?)

**Friday Jan 31:**
- [ ] Claude Code: Generate QA tooling scripts
- [ ] Manual: Run operator QA on Container 1 (45 min)
- [ ] Claude Code: Document STAGE2_HYBRID_SCHEMA.md

**Monday Feb 3:**
- [ ] Claude Code: Commit all changes with Conventional Commits
- [ ] Manual: Push to GitHub
- [ ] Manual: Verify builds/CI passes

### Week 2 (Feb 3-7)

**Scale to all 53 containers:**
- [ ] Run extraction backfill (if not done)
- [ ] Run segmentation on remaining containers
- [ ] Operator QA on representative sample (Containers 5, 20, 50)
- [ ] Adjust heuristics if needed based on feedback

---

## Key Files to Create/Modify

**CREATE:**
- `database/migrations/004_hybrid_schema_page_assets.sql`
- `scripts/stage2/segment_from_page_packs.py` (new)
- `scripts/stage2/generate_qa_report.py` (new)
- `scripts/stage2/sql_corrections_template.sql` (template)
- `docs/STAGE2_HYBRID_SCHEMA.md` (new guide)

**MODIFY:**
- `scripts/stage2/extract_pages_from_containers.py` (refactor)
- `README.md` (add Stage 2b section)
- `CHANGELOG.md` (add entries for each commit)

**REFERENCE:**
- All decisions in `HYBRID_SCHEMA_DECISION_PACKAGE.md`
- All analysis in `Deep_Analysis_of_the_HJB_Hybrid_Schema_...docx`

---

## Success Criteria

At the end of this implementation:

✅ Schema migrations applied successfully  
✅ 1,200+ JPEG images extracted to page packs  
✅ 53+ manifest.json files generated  
✅ `page_assets_t` fully populated  
✅ `page_pack_manifests_t` fully populated  
✅ Segmentation script produces valid output  
✅ Operator can review Container 1 manually  
✅ QA tooling helps operator verify boundaries  
✅ All changes committed with good messages  
✅ Documentation up-to-date  

Then: Scale to all 53 containers → Stage 3 (deduplication)

---

## Notes for Claude Code Sessions

- **Use GitHub integration:** Edit files directly in repo, commit with Conventional Commits
- **Test incrementally:** Verify each script works before moving to next
- **Reference the analysis:** All design decisions are documented in the decision package
- **Error handling is important:** Scripts deal with file I/O, image conversion, DB inserts — handle failures gracefully
- **Stay focused:** Stick to Must-Do items first, then Should-Do, then Could-Do
- **Document as you go:** Update code comments, docstrings, and guides so Michael can follow along

Good luck! This is a substantial refactor, but it's well-planned and the analysis gives you full confidence. Execute systematically, test thoroughly, and you'll deliver a solid implementation.

