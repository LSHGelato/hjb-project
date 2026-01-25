# HJB Hybrid Schema - Visual Architecture

## Current Architecture (Problem State)

```
┌─────────────────────────────────────────────────────────────────┐
│                    INTERNET ARCHIVE                             │
│  (Original Source: JP2 images, DjVu XML, HOCR, scandata.xml)   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────┐
        │  Stage 2a: Extract (Current)         │
        │  extract_pages_from_containers.py    │
        │                                      │
        │  - Read DjVu XML                     │
        │  - Extract text to MEDIUMTEXT blob   │
        │  - Discard structure (coords, etc)   │
        │  - Ignore JP2 images                 │
        └──────────┬───────────────────────────┘
                   │
      ┌────────────┴────────────┐
      ▼                         ▼
   ┌─────────────────┐    ┌──────────────┐
   │   Database      │    │ NAS Storage  │
   │  pages_t        │    │   (unused)   │
   │  ✗ ocr_text     │    │              │
   │    (TEXT BLOB)  │    └──────────────┘
   │  ✗ images       │
   │    (not linked) │
   └─────────────────┘
           │
           ▼
   ┌─────────────────┐
   │  Stage 2b:      │
   │  Segment        │
   │  (DB-centric)   │
   │                 │
   │  Problem:       │
   │  - No images    │
   │  - No structure │
   │  - Hard to QA   │
   └─────────────────┘
           │
           ▼
   ┌─────────────────┐
   │  works_t        │
   │  ✗ image_refs   │
   │    (empty)      │
   └─────────────────┘
```

---

## Proposed Hybrid Architecture (Solution)

```
┌─────────────────────────────────────────────────────────────────────┐
│                      INTERNET ARCHIVE                               │
│  (Original: JP2 images, DjVu XML, HOCR, scandata.xml)              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
     ┌──────────────────────────────────────────────────┐
     │     Stage 2a: Extract (REFACTORED)               │
     │     extract_pages_from_containers.py (v2)        │
     │                                                  │
     │  For each page:                                  │
     │  1. Extract JP2 → JPEG (300 DPI, q90)           │
     │  2. Copy DjVu/HOCR XML to page pack              │
     │  3. Extract text snippet (first 500 chars)       │
     │  4. Compute hashes (image + OCR file)            │
     │  5. Create page_pack manifest (JSON)             │
     │  6. Populate page_assets_t (pointers)            │
     │  7. Update pages_t (lightweight)                 │
     └──────────┬───────────────────────────────────────┘
                │
      ┌─────────┴────────────────────────────────────────┐
      │                                                  │
      ▼                                                  ▼
 ┌─────────────────────┐                      ┌──────────────────┐
 │    DATABASE         │                      │   NAS STORAGE    │
 │  (Authoritative)    │                      │ (Input Artifacts)│
 │                     │                      │                  │
 │ pages_t             │     ◄────────────    │ 0220_Page_Packs/ │
 │ • page_id           │      pointers        │                  │
 │ • ocr_text_snippet  │      (hashes)        │ [container_id]/  │
 │ • ocr_char_count    │                      │ ├── manifest.json│
 │ • is_spread         │                      │ ├── images/      │
 │ • is_spread_with    │                      │ │  ├── page_*.jpg│
 │                     │                      │ │  └── ...       │
 │ page_assets_t ◄────────────────────┐       │ ├── ocr/         │
 │ • asset_id          │              │       │ │  ├── page_*.xml│
 │ • page_id (FK)      │              │       │ │  └── ...       │
 │ • ocr_payload_path  │          paths       │ └── segmentation/│
 │ • ocr_payload_hash  │          (SHA256)    │    └── runs.json │
 │ • image_*_path      │              │       │                  │
 │ • image_*_hash      │              │       └──────────────────┘
 │                     │              └────────► File sources
 │ page_pack_manifests │                        of truth
 │ • manifest_id       │
 │ • container_id      │
 │ • manifest_path     │
 │ • manifest_hash     │
 │ • composition (JSON)│
 └─────────────────────┘
         │
         ▼
    ┌────────────────────────────────────────┐
    │ Stage 2b: Segmentation (DECOUPLED)     │
    │ segment_from_page_packs.py              │
    │                                        │
    │ Input:  Page pack manifest             │
    │ • Reads images from disk               │
    │ • Reads full OCR XML from disk         │
    │ • Applies segmentation heuristics      │
    │ (dividing lines, headlines, layout)    │
    │ Output: Segmentation manifest (JSON)   │
    │ • Work boundaries                      │
    │ • Classification (article, ad, etc)    │
    │ • Image references (paths)             │
    └────────┬───────────────────────────────┘
             │
             ▼
    ┌────────────────────────────┐
    │ Commit to DB (if approved)  │
    │                             │
    │ works_t                     │
    │ • work_id                   │
    │ • title                     │
    │ • work_type                 │
    │                             │
    │ work_occurrences_t          │
    │ • occurrence_id             │
    │ • work_id (FK)              │
    │ • image_references (JSON)   │
    │   ["0220_Page_Packs/1/     │
    │    images/page_0005.jpg",   │
    │    "0220_Page_Packs/1/     │
    │    images/page_0006.jpg"]   │
    │                             │
    │ pages_t (update)            │
    │ • page_type ← 'plate'       │
    │ • is_spread ← 1             │
    │ • is_spread_with ← partner  │
    └────────┬────────────────────┘
             │
             ▼
    ┌────────────────────────┐
    │ Operator Manual QA     │
    │ • Visual review        │
    │ • Adjust boundaries    │
    │ • Mark spreads/plates  │
    │ • Flag OCR issues      │
    │ is_manually_verified=1 │
    └────────┬───────────────┘
             │
             ▼
    ┌────────────────────────┐
    │ Stage 4: Publication   │
    │ • Generate wiki pages  │
    │ • Use image_references │
    │ • Upload to MediaWiki  │
    └────────────────────────┘
```

---

## Data Flow Diagram: Current vs Hybrid

### Current (Problem)

```
┌─────────────────────────────────────────────────────────┐
│                    COMPUTATION                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  SQL (DB):                                              │
│  SELECT ocr_text FROM pages_t WHERE container_id = 1   │
│  │                                                      │
│  ├─ [Heavy: 96 pages × 10KB text = 1MB query]          │
│  │                                                      │
│  ▼                                                      │
│  Segmentation heuristics (text only)                    │
│  • Parse text for dividing lines                        │
│  • Find headlines                                       │
│  ✗ Can't use image data (not available)                │
│  ✗ Can't use coordinates (text blob only)              │
│  │                                                      │
│  ▼                                                      │
│  Output: Work boundaries (rough estimate)              │
│  │                                                      │
│  ▼                                                      │
│  Insert works_t + work_occurrences_t                    │
│  ✗ image_references = NULL (no images extracted)       │
│  │                                                      │
│  └─ Problem: Later can't publish images to wiki        │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Hybrid (Solution)

```
┌─────────────────────────────────────────────────────────┐
│                    COMPUTATION (Local)                  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  1. Read page pack (filesystem):                        │
│  ├─ manifest.json (metadata)                            │
│  ├─ images/page_*.jpg (96 images, ~80MB, local I/O)    │
│  └─ ocr/page_*.xml (96 OCR files, full structure)      │
│     (DjVu XML with coordinates, confidence, etc)       │
│                                                         │
│  2. Segmentation heuristics (rich data):                │
│  ├─ Parse OCR text for dividing lines                  │
│  ├─ Find headlines                                      │
│  ├─ Use OCR coordinates to understand layout           │
│  ├─ Analyze page images (visual rules, borders)        │
│  ├─ Detect ad separators (thin lines)                  │
│  ├─ Build confidence scores per boundary               │
│     (high confidence = boundary here)                  │
│                                                         │
│  3. Output: Segmentation manifest                       │
│  ├─ Work boundaries (with coordinates)                 │
│  ├─ Classification confidence scores                    │
│  ├─ Image ranges for each work                         │
│  ├─ Heuristics applied (version, params)               │
│  ├─ Hash of input page pack (for auditing)             │
│     ✓ Fully reproducible & auditable                   │
│                                                         │
│  4. Commit decision to DB:                              │
│  ├─ Create works_t (text-based)                        │
│  ├─ Create work_occurrences_t with:                    │
│  │  ✓ image_references =                               │
│  │    ["0220_Page_Packs/1/images/page_0005.jpg",      │
│  │     "0220_Page_Packs/1/images/page_0006.jpg"]      │
│  └─ Update pages_t (spreads, types)                    │
│     ✓ Now have images linked to works                  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Schema Evolution

### Old (Current)

```
pages_t
├─ page_id (PK)
├─ ocr_text ← MEDIUMTEXT (BLOB)
│             Problem: Structure lost
├─ ocr_confidence (scalar)
├─ has_ocr (binary)
├─ ocr_source (string)
├─ image_file_path ← Points somewhere
│                   (never extracted)
└─ image_dpi, image_sha256, etc.

work_occurrences_t
├─ image_references ← TEXT (never populated)
└─ has_images ← TINYINT (always 0)
```

### New (Hybrid)

```
pages_t (LEAN)
├─ page_id (PK)
├─ ocr_text_snippet ← VARCHAR(500) (search preview)
├─ ocr_char_count ← INT (quality heuristic)
├─ ocr_confidence (scalar)
├─ ocr_source (string)
├─ is_spread ← TINYINT(1) (plate spreads)
├─ is_spread_with ← INT UNSIGNED FK (partner page)
└─ is_manually_verified ← TINYINT(1) (QA flag)

page_assets_t (NEW POINTER TABLE)
├─ asset_id (PK)
├─ page_id (FK) → pages_t
├─ ocr_payload_path ← "0220_Page_Packs/1/ocr/page_0000.hocr"
├─ ocr_payload_hash ← SHA256(ocr file)
├─ ocr_payload_format ← ENUM('djvu_xml', 'hocr', 'alto')
├─ image_extracted_path ← "0220_Page_Packs/1/images/page_0000.jpg"
├─ image_extracted_hash ← SHA256(image file)
├─ image_source ← 'ia_jp2', 'local_tiff', etc
├─ image_dpi_normalized ← INT
├─ was_deskewed, was_binarized, etc.
└─ extracted_at, extraction_script_version

page_pack_manifests_t (NEW AUDIT TABLE)
├─ manifest_id (PK)
├─ container_id (FK)
├─ manifest_path ← "0220_Page_Packs/1/manifest.json"
├─ manifest_hash ← SHA256(manifest JSON)
├─ page_ids_included ← JSON array [0,1,2,...]
├─ ocr_sources_used ← JSON {page_0:"ia_djvu",...}
├─ image_extraction_params ← JSON {format:"jpeg", dpi:300}
└─ created_by, description, is_active, superseded_by

work_occurrences_t (ENHANCED)
├─ occurrence_id (PK)
├─ work_id (FK)
├─ image_references ← JSON (POPULATED)
│                     ["0220_Page_Packs/1/images/page_0005.jpg",
│                      "0220_Page_Packs/1/images/page_0006.jpg"]
├─ image_extraction_params ← JSON {count:2, dpi:300, format:"jpeg"}
└─ (other fields)
```

---

## Process Flow with Checkpoints

```
     PHASE 1: Setup (This Week)
     ┌─────────────────────────────┐
     │ 1. Create new schema tables  │
     │    • page_assets_t           │
     │    • page_pack_manifests_t   │
     │                              │
     │ 2. Alter pages_t             │
     │    • Add ocr_text_snippet    │
     │    • Add is_spread fields    │
     │                              │
     │ 3. Backfill for containers   │
     │    1-53 (one-time)           │
     └──────────────┬───────────────┘
                    │
                    ▼
     PHASE 2: Extract (Next Week)
     ┌──────────────────────────────┐
     │ 1. Refactor extract script    │
     │    • Extract JP2 → JPEG      │
     │    • Copy OCR files          │
     │    • Generate manifest.json  │
     │    • Populate page_assets_t  │
     │                              │
     │ 2. Run on all 53 containers  │
     │    (80-90 min total)         │
     └──────────────┬────────────────┘
                    │
                    ▼ 1,200+ JPEG images + OCR files extracted
              ┌─────────────────┐
              │ 0220_Page_Packs │
              │ (Ready for QA)  │
              └────────┬────────┘
                       │
                       ▼
    PHASE 3: Segmentation (Mid-Week)
    ┌────────────────────────────────────┐
    │ 1. Build segment_from_page_packs.py│
    │    • Heuristics for dividing lines │
    │    • Headline detection            │
    │    • Layout analysis (images)      │
    │                                    │
    │ 2. Test on Container 1 (Issue 1)   │
    │    • Process 14 pages              │
    │    • Expect ~10-15 articles        │
    │    • Expect 2-6 plates             │
    │                                    │
    │ 3. Operator manual QA              │
    │    • Review boundaries             │
    │    • Mark spreads                  │
    │    • Fix page types                │
    │    • Sign off: is_manually_verified│
    └────────────────┬────────────────────┘
                     │
                     ▼ (Validated, Container 1 done)
                ┌──────────┐
                │ Database │
                │ works_t +│
                │ occurrenc│
                │ es_t ✓   │
                │ images   │
                │ linked   │
                └────┬─────┘
                     │
    PHASE 4: Scale (End of Week)
    ┌────────────────────────────┐
    │ Apply to containers 2-53   │
    │ (batch processing loop)    │
    │ • Segment → QA → Validate  │
    │ • Adjust heuristics as     │
    │   needed                   │
    └────────────────────────────┘
```

---

## Decision Matrix: Current vs Proposed

| Aspect | Current | Proposed | Benefit |
|--------|---------|----------|---------|
| **OCR Storage** | Text blob in `pages_t.ocr_text` | Files in page pack + snippet in DB | Rich structure preserved; DB lean |
| **Image Extraction** | Not done | JP2 → JPEG + page pack | Images available for wiki |
| **Auditability** | Implicit (in code) | Manifest documents inputs | Can reproduce exact run |
| **A/B Testing** | Destructive (update DB) | Create alternate pack | Non-destructive comparison |
| **QA Substrate** | Text only (DB queries) | Images + OCR files (local) | Better UI/UX possible |
| **Segmentation** | DB-centric | File-centric (compute) | Cleaner pipeline boundary |
| **Manual Verification** | Hard (scattered data) | Natural (page pack = unit) | Operator-friendly |
| **Storage I/O** | Remote DB (slow) | Local NAS (fast) | Performance |
| **Future ML** | Text only | Full structure + images | Enables advanced features |

---

## Filesystem Footprint Estimate

```
Volume 1: 53 containers × 53 issues = 1,025 pages

Per page (typical):
├─ Source JP2: ~20 MB (in Raw_Input, kept)
├─ Extracted JPEG: 0.85 MB (in page pack)
├─ DjVu/HOCR XML: 150 KB (in page pack)
└─ Manifest entries: ~2 KB (JSON)

Total for all pages:
├─ JPEG images: 1,025 × 0.85 MB = ~870 MB
├─ OCR files: 1,025 × 150 KB = ~154 MB
├─ Manifests: 53 × 100 KB = ~5 MB
└─ Segmentation outputs: 53 × 50 KB = ~3 MB
   ─────────────────────────────────────
   Total: ~1 GB (acceptable; NAS has ~few TB)

Plus:
├─ Raw_Input (source JP2 zips): ~1+ TB (kept indefinitely)
├─ Database: ~5 MB (schema + metadata)
└─ Reference_Library: ~100 MB (curated outputs after Stage 3)
```

**Conclusion:** Hybrid schema uses ~1 GB for page packs (1,025 pages). Storage is acceptable.

---

**End of Visual Diagrams**
