# HJB Hybrid Schema Decision Package
## Page Packs + Database Integration for OCR & Images

**Date:** 2026-01-25  
**Status:** Architecture Decision Required  
**Audience:** Claude Thinking or Claude Opus 4.5 for detailed analysis

---

## Executive Summary

We have reached a critical architectural decision point in Stage 2 (OCR extraction and segmentation):

**Current state:** We extract DjVu OCR text into `pages_t.ocr_text` (MEDIUMTEXT blob), lose all structured OCR data (coordinates, confidence, reading order), and have no plan for extracting/linking images to works.

**Problem identified:** This approach is brittle for:
- A/B testing segmentation with different OCR sources
- Reproducible/auditable runs
- Rich segmentation (layout-aware, ads, inline figures)
- Image extraction and linking to works
- Future ML/deduplication that needs structure and images

**Proposed solution:** **Hybrid schema** combining:
1. **Lightweight database** (`pages_t`, `page_assets_t`) storing metadata, pointers, hashes
2. **Page packs** (filesystem bundles) storing full OCR payloads, images, manifests
3. **Explicit separation** between data source (page packs) and authoritative state (DB)

---

## Current Architecture (What We Have)

### Database Tables (Relevant Subset)

```sql
-- pages_t (Stage 2a output)
page_id INT PK
container_id INT FK
issue_id INT FK
page_index INT (0-based)
page_number_printed VARCHAR
page_type ENUM('content', 'cover', 'plate', 'blank', 'advertisement', ...)
is_manually_verified TINYINT(1)
ocr_text MEDIUMTEXT          -- ← FULL TEXT BLOB (all structure lost)
ocr_confidence DECIMAL(3,2)   -- Overall confidence only
has_ocr TINYINT(1)
ocr_source VARCHAR('ia_hocr', 'ia_djvu', 'tesseract', ...)
image_file_path VARCHAR      -- ← Points somewhere, but not extracted
image_dpi INT
image_sha256 CHAR(64)
created_at DATETIME
updated_at DATETIME

-- work_occurrences_t (Stage 2b/3 output)
occurrence_id INT PK
work_id INT FK
issue_id INT FK
container_id INT FK
start_page_id INT FK -> pages_t
end_page_id INT FK -> pages_t
page_range_label VARCHAR
ocr_text MEDIUMTEXT          -- ← Occurrence-specific OCR
is_canonical TINYINT(1)
image_references TEXT        -- ← JSON placeholder, never populated
has_images TINYINT(1)        -- ← Placeholder, never set
```

### Working Directory Structure (Current)

```
Working_Files/
├── 0200_STATE/
│   ├── flags/              (task queue)
│   ├── logs/               (processing logs)
│   └── pipeline_state.json
├── 0210_Preprocessing/     (optional, de-skew, crop, etc.)
└── 0220_Page_Packs/        (abandoned structure, not implemented)
```

### What We're NOT Doing Today

- ❌ Extracting JP2s to usable formats
- ❌ Storing structured OCR (coordinates, bounding boxes, reading order)
- ❌ Creating issue-level bundles with rich metadata
- ❌ Linking images to works
- ❌ Supporting A/B OCR comparison

---

## The Problem: Why This Matters Now

### 1. Images Are Essential

**Volume 1 (American Architect) contains:**
- ~1,200 pages across 53 issues
- Issue 53: 270 supplemental pages with fancy mastheads + classified ads
- Plates: 2-6 per issue (must show as images, especially spreads)
- Inline illustrations: Expected in later volumes

**Current state:** `pages_t.image_file_path` points to source, but we never extract. When we segment and create works, we have no image references to publish to the wiki.

### 2. OCR Structure Matters for Quality

**DjVu XML contains:**
```xml
<PAGE ID="1" HEIGHT="..." WIDTH="...">
  <LINE BBOX="...">
    <WORD BBOX="..." CONFIDENCE="0.95">text</WORD>
    ...
  </LINE>
  ...
</PAGE>
```

**What we store in `pages_t.ocr_text`:**
```
text text text...
```

We lose:
- Bounding box coordinates (needed for cropping figures)
- Per-word confidence (needed for ranking OCR quality)
- Reading order (needed for layout-aware segmentation)
- Structure (blocks, paragraphs) — collapsed to text blob

### 3. Segmentation Needs Multi-Source Inputs

For robust article/ad boundary detection, we need:
- OCR **text** (dividing lines, headlines)
- OCR **structure** (coordinates, blocks—are these on same line? next line?)
- Page **image** (visual rules, borders, column separators)
- Page **metadata** (rotation, skew, confidence)

A single text blob from SQL doesn't support this.

### 4. Auditability & Reproducibility

**Question:** "Why did article X end at page 5 instead of page 6?"

**Current answer:** "Uh... the script had some heuristics, the OCR was stored in the DB, which might have been updated..."

**With page packs:** "Container 1's page pack manifest (dated 2026-01-25) was processed with segmentation v2.1, which detected dividing lines at [these coordinates]. Here's the intermediate output."

### 5. A/B Testing & Iteration

Without page packs, trying alternative OCR sources means:
- Update DB with new OCR text (corrupts history)
- Re-segment
- Compare to original
- Disaster if original was better—can't roll back cleanly

With page packs:
- Create alternate manifest with Tesseract OCR
- Run segmentation (pure compute, no DB writes)
- Compare outputs
- Keep/discard without touching authoritative data

---

## Proposed Hybrid Architecture

### Core Principle

**Database** = authoritative state & decisions  
**Page Packs** = input artifacts for compute jobs  
**Separation** = clean job boundaries (read pack → process → write results)

### New/Modified Database Tables

#### 1. `page_assets_t` (NEW)

Pointer table linking pages to their asset payloads.

```sql
CREATE TABLE page_assets_t (
  asset_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  page_id INT UNSIGNED NOT NULL UNIQUE,
  FOREIGN KEY (page_id) REFERENCES pages_t(page_id),
  
  -- Pointers to authoritative OCR sources (don't store text here; store path)
  ocr_payload_path VARCHAR(512),      -- e.g., "0220_Page_Packs/1/ocr/page_0000.hocr"
  ocr_payload_hash CHAR(64),          -- SHA256 of OCR file (for change detection)
  ocr_payload_format ENUM('djvu_xml', 'hocr', 'alto', 'tesseract_json'),
  
  -- Image references
  image_extracted_path VARCHAR(512),  -- e.g., "0220_Page_Packs/1/images/page_0000.jpg"
  image_extracted_format VARCHAR(32), -- 'jpeg', 'png', 'tiff', 'jp2'
  image_extracted_hash CHAR(64),
  image_source VARCHAR(64),           -- 'ia_jp2', 'local_tiff', etc.
  
  -- Normalization metadata
  image_dpi_normalized INT,
  image_rotation_applied INT,         -- degrees (0, 90, 180, 270)
  was_deskewed TINYINT(1),
  was_binarized TINYINT(1),
  
  -- Extraction timestamp & source
  extracted_at DATETIME NOT NULL,
  extraction_script_version VARCHAR(64),
  
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  
  INDEX (page_id),
  INDEX (ocr_payload_hash),
  INDEX (image_extracted_hash)
);
```

**Purpose:** Tracks which external files (OCR payloads, images) correspond to which pages. Enables:
- Easy re-extraction if format changes
- Hash-based change detection
- Multi-OCR-source support (same page, different OCR in different rows? No—1:1)
- Audit trail of normalizations applied

#### 2. `pages_t` (MODIFIED)

Reduce to metadata + lightweight search index; remove text blob.

```sql
-- ADD these columns to pages_t
ALTER TABLE pages_t 
ADD COLUMN ocr_text_snippet VARCHAR(500),        -- First 500 chars for preview/search
ADD COLUMN ocr_char_count INT,
ADD COLUMN is_spread TINYINT(1) DEFAULT 0,
ADD COLUMN is_spread_with INT UNSIGNED,          -- FOREIGN KEY to pages_t (self-ref)
ADD CONSTRAINT fk_is_spread_with FOREIGN KEY (is_spread_with) REFERENCES pages_t(page_id);

-- REMOVE (or deprecate) these columns from pages_t
-- ocr_text MEDIUMTEXT  -- Too heavy; now in page pack files + maybe indexed separately
-- (keep: ocr_confidence, ocr_source, ocr_word_count for lightweight stats)
```

**Rationale:**
- `ocr_text_snippet` for UI preview without fetching full text
- `ocr_char_count` for quality heuristics (if count too low, OCR failed)
- `is_spread` + `is_spread_with` for tracking 2-page plate spreads
- Remove MEDIUMTEXT blob; page pack files are source of truth

#### 3. `page_pack_manifests_t` (NEW)

Tracks page pack versions & composition.

```sql
CREATE TABLE page_pack_manifests_t (
  manifest_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  container_id INT UNSIGNED NOT NULL,
  FOREIGN KEY (container_id) REFERENCES containers_t(container_id),
  
  -- Manifest identity
  manifest_path VARCHAR(512) NOT NULL,           -- e.g., "0220_Page_Packs/1/manifest.json"
  manifest_hash CHAR(64),                        -- SHA256 of manifest JSON
  manifest_version VARCHAR(32),                  -- e.g., "1.0", for schema/format
  
  -- Composition
  total_pages INT,
  page_ids_included JSON,                        -- Array: [0, 1, 2, ..., 95]
  ocr_sources_used JSON,                         -- {page_0: "ia_djvu", page_1: "ia_hocr", ...}
  image_extraction_params JSON,                  -- {format: "jpeg", dpi: 300, rotation: false}
  
  -- Metadata
  created_at DATETIME NOT NULL,
  created_by VARCHAR(128),                       -- e.g., "extract_pages_from_containers.py v1.2"
  description VARCHAR(255),
  
  -- Status
  is_active TINYINT(1) DEFAULT 1,                -- Set to 0 if superseded
  superseded_by INT UNSIGNED,                    -- FOREIGN KEY to self
  FOREIGN KEY (superseded_by) REFERENCES page_pack_manifests_t(manifest_id),
  
  INDEX (container_id),
  INDEX (manifest_hash),
  UNIQUE (manifest_path)
);
```

**Purpose:** Documents what's in each page pack—essential for auditing & reprocessing.

#### 4. `work_occurrences_t` (MODIFIED)

Update to store actual image references (from page packs).

```sql
-- MODIFY work_occurrences_t
ALTER TABLE work_occurrences_t 
MODIFY COLUMN image_references JSON,              -- e.g., ["0220_Page_Packs/1/images/page_0005.jpg", ...]
ADD COLUMN image_extraction_params JSON;         -- e.g., {count: 2, dpi: 300, format: "jpeg"}
```

**Rationale:** Now that we extract images, `image_references` is populated with paths from page packs.

---

### Page Pack Filesystem Structure

```
0220_Page_Packs/
├── [container_id]/                  (e.g., "1" for container 1)
│   ├── manifest.json                (JSON: composition, versions, metadata)
│   ├── images/
│   │   ├── page_0000.jpg            (extracted from JP2)
│   │   ├── page_0001.jpg
│   │   └── ... (0-based indexed)
│   ├── ocr/
│   │   ├── page_0000.hocr           (or .xml, .json—original format)
│   │   ├── page_0001.hocr
│   │   └── ...
│   └── segmentation/
│       └── segmentation_v2_1.json   (output of a segmentation run)
│
├── [container_id]/
│   └── ...
│
└── _archive/
    └── (previous versions of packs, for comparison)
```

#### Page Pack Manifest (manifest.json)

```json
{
  "manifest_version": "1.0",
  "container_id": 1,
  "container_source": "ia",
  "container_identifier": "loc_booksandmags_14093893",
  "issue_id": 1,
  "created_at": "2026-01-25T14:30:00Z",
  "created_by": "extract_pages_from_containers.py v1.3",
  
  "pages": [
    {
      "page_id": 1,
      "page_index": 0,
      "page_label": "Cover",
      "image_source": "ia_jp2",
      "image_extracted": "images/page_0000.jpg",
      "image_hash_original": "abc123...",
      "image_hash_extracted": "def456...",
      "ocr_sources_available": ["ia_djvu", "ia_hocr"],
      "ocr_selected": "ia_djvu",
      "ocr_file": "ocr/page_0000.hocr",
      "ocr_hash": "ghi789...",
      "metadata": {
        "rotation_applied": 0,
        "dpi_original": 300,
        "dpi_normalized": 300,
        "was_deskewed": false,
        "width_pixels": 2550,
        "height_pixels": 3300
      }
    },
    {
      "page_id": 2,
      "page_index": 1,
      ...
    }
  ],
  
  "extraction_parameters": {
    "image_format": "jpeg",
    "image_quality": 90,
    "ocr_priority_order": ["ia_djvu", "ia_hocr", "tesseract"],
    "preprocessing": {
      "deskew": false,
      "binarize": false,
      "normalize_dpi_to": 300
    }
  },
  
  "statistics": {
    "total_pages": 96,
    "pages_with_images": 96,
    "pages_with_ocr": 96,
    "avg_image_size_mb": 0.85,
    "avg_ocr_confidence": 0.92,
    "total_pack_size_mb": 82
  }
}
```

**Purpose:** Self-documenting artifact. Allows reproduction of exact inputs for any segmentation run.

---

## Implementation Plan

### Phase 1: Schema & Infrastructure (Before Phase 2b Segmentation)

#### Step 1.1: Create New Tables

```sql
-- Create page_assets_t
CREATE TABLE page_assets_t (...);  -- See schema above

-- Create page_pack_manifests_t
CREATE TABLE page_pack_manifests_t (...);  -- See schema above

-- Alter pages_t
ALTER TABLE pages_t ADD COLUMN ocr_text_snippet VARCHAR(500);
ALTER TABLE pages_t ADD COLUMN ocr_char_count INT;
ALTER TABLE pages_t ADD COLUMN is_spread TINYINT(1) DEFAULT 0;
ALTER TABLE pages_t ADD COLUMN is_spread_with INT UNSIGNED;
ALTER TABLE pages_t ADD CONSTRAINT fk_is_spread_with FOREIGN KEY (is_spread_with) REFERENCES pages_t(page_id);

-- Alter work_occurrences_t
ALTER TABLE work_occurrences_t MODIFY COLUMN image_references JSON;
ALTER TABLE work_occurrences_t ADD COLUMN image_extraction_params JSON;
```

**Migration Script:** `database/migrations/004_hybrid_schema_page_assets.sql`

#### Step 1.2: Refactor `extract_pages_from_containers.py`

Current script extracts OCR text → `pages_t.ocr_text`.

**New behavior:**
1. Extract DjVu XML/HOCR to page pack: `0220_Page_Packs/[container_id]/ocr/page_XXXX.hocr`
2. Store only snippet + metadata in `pages_t`:
   ```python
   pages_t.ocr_text_snippet = ocr_text[:500]
   pages_t.ocr_char_count = len(ocr_text)
   pages_t.ocr_confidence = (from DjVu confidence scores)
   ```
3. Create `page_assets_t` row with pointer to OCR file + hash
4. Generate & store `page_pack_manifests_t` entry

#### Step 1.3: Add Image Extraction to `extract_pages_from_containers.py`

New capability:
1. Extract JP2s from `raw_input_path/[container_id]/[id]_jp2.zip`
2. Convert to JPEG (quality 90, DPI normalized to 300)
3. Store in page pack: `0220_Page_Packs/[container_id]/images/page_XXXX.jpg`
4. Record in `page_assets_t` + manifest

**Key decision:** Convert JP2 to JPEG for web compatibility + smaller storage. Keep original JP2 source in Raw_Input for archival.

#### Step 1.4: Populate `page_assets_t` for All Existing Pages

Backfill for the 1,025 pages already in `pages_t` (from Containers 1-53).

```python
for each container in containers_t:
  for each page in pages_t where container_id = container.container_id:
    # Extract images from IA JP2
    # Copy OCR payloads to page pack
    # Insert page_assets_t row
    # Update pages_t.ocr_text_snippet, ocr_char_count
    # Create/update page_pack_manifests_t
```

**This is a one-time backfill; future containers use refactored script.**

### Phase 2: Segmentation Integration (Phase 2b)

#### Step 2.1: Build Segmentation Script to Read Page Packs

New script: `scripts/stage2/segment_from_page_packs.py`

**Input:** Page pack path (e.g., `0220_Page_Packs/1/manifest.json`)  
**Logic:**
1. Read manifest
2. For each page in page pack:
   - Load OCR from file (full structure, not snippet)
   - Load image from file
   - Apply segmentation heuristics (dividing lines, headlines, layout analysis)
3. **Output:** JSON with work boundaries + image references
4. **Write to DB:** Create `works_t` + `work_occurrences_t` rows, populate `image_references`

**Key benefit:** Segmentation runs independently of DB state. Can re-run with different heuristics without touching existing data.

#### Step 2.2: Store Segmentation Outputs

After successful segmentation run:
1. Save segmentation manifest: `0220_Page_Packs/[container_id]/segmentation/segmentation_v2_1.json`
   - Lists work boundaries, heuristics applied, parameters
   - Hash of input page pack (for auditability)
   
2. Commit to DB:
   - Create `works_t` rows
   - Create `work_occurrences_t` rows with populated `image_references` (paths to extracted JEPGs)
   - Mark `is_manually_verified = 0` for manual review
   
3. Flag for manual QA:
   - Create task/flag: `0200_STATE/flags/pending/[date]_qc_segmentation_container_[id].json`
   - Operator reviews boundaries, plate markings, spread detection

#### Step 2.3: Operator Manual Review Workflow

For each container (e.g., container 1):

1. **Visual review:** Operator views `0220_Page_Packs/1/images/` + `works_t` output
2. **Corrections:**
   - Adjust work boundaries if needed
   - Mark plate pages: `pages_t.page_type = 'plate'`
   - Mark spreads: `pages_t.is_spread = 1`, `is_spread_with = [partner_page_id]`
   - Flag for manual transcription if OCR too poor
3. **Mark verified:** Set `is_manually_verified = 1` on confirmed records
4. **Commit:** Create summary flag when container is QA'd

---

## Benefits of This Approach

| Benefit | How Achieved |
|---------|-------------|
| **Reproducibility** | Page pack manifest documents exact inputs for each segmentation run |
| **Auditability** | Can trace: raw IA files → extracted → segmented → published |
| **A/B Testing** | Create alternate page pack (different OCR source) without touching DB; compare outputs |
| **Rich OCR data** | Store full DjVu XML/HOCR in files; DB keeps lightweight pointers |
| **Image support** | Extract JP2s → JPEGs; link to works via `image_references` |
| **Segmentation decoupling** | Compute job runs offline; DB receives only final decisions |
| **Manual QA integration** | Page packs + extracted images = natural QA substrate |
| **Storage efficiency** | DB stays lean; heavy files on NAS with local I/O |
| **Future extensibility** | Layout-aware segmentation, ML, ad deduplication can use rich payloads |

---

## Unknowns / Decisions Needed

### 1. OCR Storage Depth

**Question:** Should `pages_t` still have `ocr_text` at all, or just snippet?

**Option A:** Only snippet (500 chars) in DB
- Pro: Smaller DB, encourages using page pack as source of truth
- Con: Can't do full-text search without querying files or rebuilding full-text index

**Option B:** Full text stays in `pages_t` 
- Pro: Full-text search, backward compatible
- Con: DB bloat, might encourage ignoring page pack as authoritative

**Recommendation:** Option A initially. Full-text search can be done via:
- Storing full text in `work_occurrences_t` (after segmentation)
- Or building separate Elasticsearch index (future)

### 2. Image Extraction Timing

**Question:** When do we extract JP2→JPEG?

**Option A:** During Phase 2a (when populating `page_assets_t`)
- Pro: Images ready for manual QA in Phase 2b
- Con: Heavy compute upfront; takes 30 min per container

**Option B:** Lazy extraction during Phase 2b (segmentation)
- Pro: Only extract images for pages we care about
- Con: Slower QA workflow (waiting for extraction)

**Recommendation:** Option A. One-time cost; benefits outweigh compute time. Plus, enables visual page-type review before segmentation.

### 3. Page Pack Versioning

**Question:** If we re-extract (e.g., new DPI normalization), do we:

**Option A:** Overwrite existing page pack (one version per container)
- Pro: Cleaner filesystem
- Con: Lose history; can't compare old vs new extraction

**Option B:** Version packs (v1, v2, v3) + keep history
- Pro: Full audit trail
- Con: Disk space for duplicates

**Recommendation:** Option A + `_archive/` folder. Keep only active pack on NAS; archive old versions to offline storage if needed.

### 4. JP2 Retention Policy

**Question:** After extracting JP2→JPEG, do we delete the original JP2 zip?

**Answer:** Keep in `Raw_Input/` per existing retention policy. This is stable external data (IA holds canonical copies). JPEG is cached derivative.

---

## Rollout Timeline

1. **This week:** Finalize schema, review with Opus 4.5/Thinking
2. **Early next week:**
   - Apply migrations
   - Refactor `extract_pages_from_containers.py`
   - Run backfill for containers 1-53
3. **Mid-week:**
   - Build `segment_from_page_packs.py`
   - Test on container 1 (Issue 1)
4. **End of week:**
   - Manual QA workflow on container 1
   - Adjust heuristics
5. **Next week:** Scale to all 53 containers

---

## Questions for Deep Analysis

Please address in your response:

1. **Schema refinement:** Are there missing columns or tables? Better structure for `page_assets_t`?

2. **Manifest design:** Is the JSON structure in `manifest.json` the right level of detail? Too verbose? Missing anything?

3. **Segmentation interface:** Should segmentation script read from files or DB? Trade-offs?

4. **Image format choice:** JPEG quality 90 @ 300 DPI is right, or should we optimize differently? Keep original JP2 for archival?

5. **Operator workflow:** How to make manual QA (marking spreads, fixing boundaries) smooth? UI tool needed?

6. **Future ML/dedup:** Does this architecture support ad fingerprinting, text similarity, layout classification?

7. **Storage footprint:** Estimate total NAS usage for page packs (1,200 pages, ~0.85 MB images/page). Acceptable?

---

## Appendix: Quick Reference

### Table Summary

| Table | Purpose | New? | Key Change |
|-------|---------|------|-----------|
| `pages_t` | Individual pages | No | Remove `ocr_text` blob; add `is_spread`, snippet |
| `page_assets_t` | Pointers to OCR/image files | **Yes** | New table for hybrid model |
| `page_pack_manifests_t` | Documents page pack composition | **Yes** | Auditability & versioning |
| `work_occurrences_t` | Work appearances | No | Populate `image_references` (JSON paths) |

### Scripts to Build/Modify

| Script | Status | Purpose |
|--------|--------|---------|
| `extract_pages_from_containers.py` | Modify | Extract → page packs; populate `page_assets_t` + manifest |
| `segment_from_page_packs.py` | New | Read page packs; output work boundaries + image refs |
| `004_hybrid_schema_*.sql` | New | Migration to create/alter tables |

### Directories

| Path | Purpose |
|------|---------|
| `0220_Page_Packs/[container_id]/` | **Active** page packs (images, OCR, manifest) |
| `0220_Page_Packs/_archive/` | Previous versions of packs |
| `0250_Export/` | Stage 4 wiki export (separate concern) |

---

**End of Document**

---

**Prepared by:** Claude (Assistant)  
**For:** Michael Raney  
**Format:** Decision package for deep analysis  
**Expected Output:** Detailed architectural review + refinements
