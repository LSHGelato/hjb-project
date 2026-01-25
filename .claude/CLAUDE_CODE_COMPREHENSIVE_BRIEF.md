# HJB Hybrid Schema Implementation - Claude Code Brief
## Stage 2 OCR + Images Architecture

**Status:** APPROVED - Ready for Implementation  
**Scope:** Schema migrations + script refactoring + backfill + QA tooling  
**Timeline:** Week of Jan 27 (5 working days)  
**Owner:** Claude Code (with guidance from Michael)

---

## Project Context

**What:** Implementing hybrid database + filesystem page packs architecture for HJB Stage 2  
**Why:** Enable image extraction, rich segmentation, reproducible/auditable runs, future ML support  
**Where:** `/mnt/project/` (GitHub repo + NAS)  
**Database:** `raneywor_hjbproject` on HostGator  

**Current State:**
- 53 containers (IA downloads) in Raw_Input
- 1,025 pages extracted in pages_t with OCR text blobs
- All pages in database; page types manually verified
- Ready for segmentation (Phase 2b)

**Architecture Decision:** Approved by Claude Thinking analysis  
**Go/No-Go:** ✅ **GO** - Proceed with full implementation

---

## MUST-DO Items (Core Implementation)

These are critical; all must be completed and tested.

### 1. Database Schema Migrations

**File:** `database/migrations/004_hybrid_schema_page_assets.sql`

Create three new tables and modify two existing tables:

```sql
-- 1. Create page_assets_t (NEW)
CREATE TABLE page_assets_t (
  asset_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  page_id INT UNSIGNED NOT NULL UNIQUE,
  FOREIGN KEY (page_id) REFERENCES pages_t(page_id) ON DELETE CASCADE,
  
  -- OCR payload references
  ocr_payload_path VARCHAR(512),
  ocr_payload_hash CHAR(64),
  ocr_payload_format ENUM('djvu_xml', 'hocr', 'alto', 'tesseract_json'),
  
  -- Extracted image references
  image_extracted_path VARCHAR(512),
  image_extracted_format VARCHAR(32),
  image_extracted_hash CHAR(64),
  image_source VARCHAR(64),
  
  -- Image normalization metadata
  image_dpi_normalized INT,
  image_rotation_applied INT,
  was_deskewed TINYINT(1),
  was_binarized TINYINT(1),
  
  -- Timestamps
  extracted_at DATETIME NOT NULL,
  extraction_script_version VARCHAR(64),
  
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  
  INDEX (page_id),
  INDEX (ocr_payload_hash),
  INDEX (image_extracted_hash)
);

-- 2. Create page_pack_manifests_t (NEW)
CREATE TABLE page_pack_manifests_t (
  manifest_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  container_id INT UNSIGNED NOT NULL,
  FOREIGN KEY (container_id) REFERENCES containers_t(container_id) ON DELETE CASCADE,
  
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

-- 3. Modify pages_t (ADD COLUMNS)
ALTER TABLE pages_t 
ADD COLUMN ocr_text_snippet VARCHAR(500),
ADD COLUMN ocr_char_count INT,
ADD COLUMN is_spread TINYINT(1) DEFAULT 0,
ADD COLUMN is_spread_with INT UNSIGNED,
ADD CONSTRAINT fk_is_spread_with FOREIGN KEY (is_spread_with) REFERENCES pages_t(page_id);

-- 4. Modify work_occurrences_t (UPDATE COLUMNS)
ALTER TABLE work_occurrences_t 
MODIFY COLUMN image_references JSON,
ADD COLUMN image_extraction_params JSON;
```

**Success Criteria:**
- All tables created successfully
- Foreign keys enforce referential integrity
- Indexes created for common query patterns
- Migration can be run on existing database without data loss
- Can roll back if needed (add DOWN script)

**Verification Query:**
```sql
SHOW TABLES LIKE 'page_%';
DESCRIBE page_assets_t;
DESCRIBE page_pack_manifests_t;
SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='pages_t' AND COLUMN_NAME IN ('ocr_text_snippet', 'is_spread');
```

---

### 2. Refactor `extract_pages_from_containers.py`

**File:** `scripts/stage2/extract_pages_from_containers.py` (v2)

**Responsibilities:**
1. Extract JP2s from IA containers → convert to JPEG
2. Copy OCR payloads (DjVu XML, HOCR) to page pack directory
3. Populate `pages_t` with snippet + metadata
4. Create `page_assets_t` entries with pointers + hashes
5. Generate page pack manifest JSON
6. Create `page_pack_manifests_t` entry
7. Handle errors gracefully with logging

**Inputs:**
- Container ID from flag file
- Raw input path (NAS)
- Output path (0220_Page_Packs)

**Outputs:**
- `0220_Page_Packs/[container_id]/manifest.json`
- `0220_Page_Packs/[container_id]/images/page_XXXX.jpg` (extracted JPEGs)
- `0220_Page_Packs/[container_id]/ocr/page_XXXX.hocr` (or .xml)
- Updated `pages_t.ocr_text_snippet`, `ocr_char_count`
- New `page_assets_t` rows
- New `page_pack_manifests_t` row

**Key Functions:**
```python
def extract_jp2_to_jpeg(jp2_path, output_path, quality=90, normalize_dpi=300):
    """Extract JP2 → JPEG, compute hashes, return metadata."""
    # Use Pillow/OpenCV to convert
    # Normalize DPI to 300 if different
    # Compute SHA256 of both original and extracted
    # Return: (jpeg_path, original_hash, extracted_hash, image_dims, dpi)

def extract_ocr_files(container_path, output_ocr_path):
    """Copy DjVu/HOCR from raw to page pack; return paths + hashes."""
    # Find available OCR formats (djvu.xml, hocr, etc.)
    # Determine priority (prefer DjVu over HOCR)
    # Copy selected to page pack
    # Compute hashes
    # Return: (ocr_path, ocr_hash, ocr_format, ocr_sources_available)

def extract_ocr_text_snippet(ocr_path, length=500):
    """Extract first N chars of OCR as snippet for DB."""
    # Parse HOCR or DjVu XML
    # Extract plain text
    # Return first 500 chars + word count

def generate_manifest_json(container_id, issue_id, pages_data, extraction_params):
    """Create manifest JSON documenting page pack contents."""
    # Build per-page entries (page_id, image path, ocr path, hashes, etc.)
    # Capture extraction parameters (quality, DPI, preprocessing flags)
    # Add statistics (total pages, avg image size, avg OCR confidence)
    # Return JSON dict (later saved to file)

def populate_page_assets_t(db_conn, page_id, asset_data):
    """Insert row into page_assets_t with paths and hashes."""
    # asset_data: {ocr_payload_path, ocr_payload_hash, image_extracted_path, ...}
    # Execute INSERT
    # Return asset_id for verification

def populate_page_pack_manifests_t(db_conn, container_id, manifest_data):
    """Insert row into page_pack_manifests_t."""
    # manifest_data: {manifest_path, manifest_hash, page_ids_included, ...}
    # Execute INSERT
    # Return manifest_id
```

**Error Handling:**
- Try-except around JP2 conversion; if fails, log and skip page, continue
- If OCR file missing, note in manifest and log warning
- If DB insert fails, rollback and re-raise with context
- Log all operations (extraction start/end, pages processed, errors)

**Success Criteria:**
- Script runs on 53 containers without crashing
- All pages extracted to JPEG in 0220_Page_Packs/
- All manifests generated with correct JSON structure
- pages_t populated with snippets + char counts
- page_assets_t populated with 1,025 rows (one per page)
- page_pack_manifests_t populated with 53 rows (one per container)
- Manifest hashes match manifest file contents
- Script is idempotent (can re-run without duplicating rows)

**Testing:**
- Run on Container 1 (Issue 1, 14 pages) → verify all outputs
- Spot-check manifest JSON validity (parse and inspect)
- Verify DB rows match file counts
- Check image quality visually (spot sample JEPGs)
- Ensure OCR text snippets make sense

---

### 3. Build `segment_from_page_packs.py`

**File:** `scripts/stage2/segment_from_page_packs.py` (NEW)

**Purpose:** Read page packs → apply segmentation heuristics → output work boundaries + image references

**Inputs:**
- Manifest path (e.g., `0220_Page_Packs/1/manifest.json`)
- Segmentation parameters (heuristic versions, thresholds, etc.)

**Outputs:**
- Segmentation manifest JSON: `0220_Page_Packs/[container_id]/segmentation/segmentation_v2_1.json`
- Console output: work boundaries, confidence scores, notes
- Ready to commit: works_t + work_occurrences_t rows (as JSON or SQL, for manual review)

**Segmentation Heuristics (MVP):**

```python
def is_dividing_line(ocr_line):
    """Detect horizontal rules (---, ===, etc.) as article separators."""
    stripped = ocr_line.strip()
    if len(stripped) < 5:
        return False
    separator_chars = stripped.count('-') + stripped.count('=') + stripped.count('_')
    return separator_chars / len(stripped) > 0.7

def is_headline(ocr_line):
    """Detect lines likely to be article headlines."""
    stripped = ocr_line.strip()
    # Heuristics:
    # - Short (< 80 chars)
    # - All caps or title case
    # - Or precedes byline
    if len(stripped) > 80:
        return False
    if stripped.isupper() or stripped.istitle():
        return True
    return False

def find_work_boundaries(pages_data):
    """
    Given pages with OCR and images, identify work boundaries.
    Returns list of works: [{start_page, end_page, title, type, confidence, ...}]
    """
    works = []
    current_work = None
    
    for page_idx, page_data in enumerate(pages_data):
        ocr_lines = page_data['ocr_text'].split('\n')
        
        for line_idx, line in enumerate(ocr_lines):
            # Check for dividing line (article break)
            if is_dividing_line(line):
                if current_work:
                    works.append(current_work)
                current_work = None
                continue
            
            # Check for headline (new article likely)
            if is_headline(line) and current_work:
                works.append(current_work)
                current_work = {
                    'start_page': page_idx,
                    'start_line': line_idx,
                    'title': line.strip(),
                    'pages': [page_idx],
                    'confidence': 0.85,  # High confidence if headline detected
                    'type': 'article'  # Default; can refine
                }
                continue
            
            # Accumulate text into current work
            if current_work is None:
                current_work = {
                    'start_page': page_idx,
                    'start_line': line_idx,
                    'title': None,
                    'pages': [page_idx],
                    'confidence': 0.60,  # Lower confidence for no headline
                    'type': 'article'
                }
            else:
                if page_idx not in current_work['pages']:
                    current_work['pages'].append(page_idx)
    
    if current_work:
        works.append(current_work)
    
    return works

def link_images_to_works(works, pages_data):
    """
    For each work, identify which images belong to it.
    Returns updated works with image_references populated.
    """
    for work in works:
        image_refs = []
        for page_idx in work['pages']:
            page_data = pages_data[page_idx]
            image_path = page_data['image_extracted_path']  # From manifest
            image_refs.append(image_path)
        work['image_references'] = image_refs
    
    return works

def output_segmentation_manifest(works, output_path):
    """Save segmentation results to JSON for review."""
    manifest = {
        'works': works,
        'heuristics_applied': [
            'dividing_line_detection',
            'headline_detection',
            'page_accumulation'
        ],
        'parameters': {
            'dividing_line_threshold': 0.7,
            'headline_max_length': 80,
            'confidence_high': 0.85,
            'confidence_low': 0.60
        },
        'generated_at': datetime.utcnow().isoformat(),
        'generation_script': 'segment_from_page_packs.py v2.1'
    }
    
    with open(output_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    return manifest
```

**Main Workflow:**
```python
def main(manifest_path, output_dir):
    # 1. Load page pack manifest
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    container_id = manifest['container_id']
    container_path = os.path.dirname(manifest_path)
    
    # 2. Load page data (OCR + image paths from manifest)
    pages_data = []
    for page_entry in manifest['pages']:
        page_id = page_entry['page_id']
        ocr_path = os.path.join(container_path, page_entry['ocr_file'])
        image_path = os.path.join(container_path, page_entry['image_extracted'])
        
        # Parse OCR
        with open(ocr_path) as f:
            ocr_text = parse_hocr(f)  # or parse_djvu_xml, etc.
        
        pages_data.append({
            'page_id': page_id,
            'page_index': page_entry['page_index'],
            'ocr_text': ocr_text,
            'image_extracted_path': image_path,
            'image_dpi': page_entry['metadata']['dpi_normalized']
        })
    
    # 3. Apply segmentation heuristics
    works = find_work_boundaries(pages_data)
    
    # 4. Link images to works
    works = link_images_to_works(works, pages_data)
    
    # 5. Output segmentation manifest
    seg_output_path = os.path.join(output_dir, f'segmentation_v2_1.json')
    seg_manifest = output_segmentation_manifest(works, seg_output_path)
    
    # 6. Log results
    print(f"Segmented {len(works)} works from {len(pages_data)} pages")
    for i, work in enumerate(works):
        print(f"  Work {i+1}: pages {work['pages']}, confidence {work['confidence']:.2f}, title={work['title']}")
    
    return seg_manifest, works
```

**Success Criteria:**
- Script successfully reads Container 1's page pack manifest
- Identifies ~10-15 articles from 14 pages
- Detects plate pages (if any) and marks type as 'plate'
- Outputs valid JSON to segmentation/segmentation_v2_1.json
- image_references populated with actual file paths
- Manual inspection shows boundaries are reasonable (operator will verify)

**Testing:**
- Run on Container 1 → validate segmentation output
- Check manifest JSON validity
- Manually review first 3 works' boundaries (open images, verify text spans)
- Operator marks is_correct=true/false for feedback

---

## SHOULD-DO Items (Enhancement & QA)

These improve the workflow significantly; should be completed this week.

### 4. Implement QA Visualization Tools

**File:** `scripts/qa/generate_qc_report.py` (NEW)

**Purpose:** Generate HTML/CSV report showing:
- Each detected work with page range and type
- Summary stats (total articles, ads, plates, etc.)
- Segmentation confidence scores
- Quick spot-checks for operator

**Output:** `0220_Page_Packs/[container_id]/qa/qc_report.html` + `.csv`

**Key Features:**
```python
def generate_html_report(container_id, works, pages_data):
    """
    Create HTML report showing:
    - Page thumbnails with work boundaries overlayed
    - Work list with titles, confidence, image count
    - Statistics summary
    """
    html = """
    <html>
    <head><title>QC Report - Container {container_id}</title></head>
    <body>
    <h1>QC Report for Container {container_id}</h1>
    
    <h2>Summary Statistics</h2>
    <ul>
      <li>Total Pages: {total_pages}</li>
      <li>Total Works: {total_works}</li>
      <li>Articles: {article_count}</li>
      <li>Advertisements: {ad_count}</li>
      <li>Plates: {plate_count}</li>
      <li>Avg Confidence: {avg_confidence:.2f}</li>
    </ul>
    
    <h2>Detected Works</h2>
    <table border="1">
    <tr><th>#</th><th>Type</th><th>Pages</th><th>Title</th><th>Confidence</th><th>Images</th></tr>
    """
    
    for i, work in enumerate(works):
        html += f"""
    <tr>
      <td>{i+1}</td>
      <td>{work['type']}</td>
      <td>{work['pages']}</td>
      <td>{work['title']}</td>
      <td>{work['confidence']:.2f}</td>
      <td>{len(work.get('image_references', []))}</td>
    </tr>
        """
    
    html += """
    </table>
    </body>
    </html>
    """
    
    return html

def generate_csv_report(container_id, works):
    """
    Create CSV for operator review in Excel.
    Columns: Work#, Type, Pages, Title, Confidence, ImageCount, Notes(empty for annotation)
    """
    import csv
    rows = [['Work#', 'Type', 'Pages', 'Title', 'Confidence', 'ImageCount', 'Operator Notes']]
    for i, work in enumerate(works):
        rows.append([
            i+1,
            work['type'],
            ','.join(map(str, work['pages'])),
            work.get('title', ''),
            f"{work['confidence']:.2f}",
            len(work.get('image_references', [])),
            ''  # Operator can fill in
        ])
    return rows
```

**Success Criteria:**
- HTML report generated and opens in browser (test with sample)
- CSV report opens in Excel and is editable
- Reports are readable and accurate
- Operator can quickly scan and identify questionable segmentation

---

### 5. Database Correction & Verification Script

**File:** `scripts/qa/apply_operator_corrections.py` (NEW)

**Purpose:** Help operator apply corrections to database (merges, splits, spread marking)

**Usage:**
```python
# Example: Merge works 5 and 6 (operator found they belong to same article)
merge_works(db_conn, work_id_1=5, work_id_2=6, target_work_id=5)

# Example: Mark pages 10-11 as a spread
mark_spread(db_conn, page_id_1=10, page_id_2=11)

# Example: Bulk update page types
update_page_type(db_conn, container_id=1, page_ids=[15, 16], new_type='plate')

# Example: Set is_manually_verified flag
mark_verified(db_conn, container_id=1)
```

**Functions to Implement:**
```python
def merge_works(db_conn, work_id_1, work_id_2, target_work_id):
    """Merge two works into one (consolidate occurrences)."""

def split_work(db_conn, work_id, split_at_page_id):
    """Split a work into two at a given page boundary."""

def mark_spread(db_conn, page_id_1, page_id_2):
    """Mark two pages as a spread (2-page plate)."""

def update_page_type(db_conn, page_ids, new_type):
    """Bulk update page_type for given pages."""

def mark_verified(db_conn, container_id):
    """Mark all pages in container as is_manually_verified=1."""
```

**Success Criteria:**
- Script provides safe templates for common corrections
- Prevents accidental data corruption (with confirmations)
- Logs all changes for audit trail
- Makes operator workflow smooth

---

### 6. Comprehensive Testing & Documentation

**File:** `docs/STAGE2_IMPLEMENTATION_LOG.md` (document as we go)

**What to Document:**
- Migration success/issues
- Backfill statistics (containers processed, pages extracted, etc.)
- Container 1 segmentation results (works detected, confidence, etc.)
- Operator QA feedback
- Any deviations from plan
- Lessons learned

**Test Plan:**
```markdown
## Test 1: Schema Migration
- [ ] Apply migration script to database
- [ ] Verify all tables created
- [ ] Verify foreign keys work
- [ ] Rollback and re-apply (test idempotency)

## Test 2: Image Extraction (Container 1)
- [ ] extract_pages_from_containers.py runs successfully
- [ ] 14 JPEGs created in 0220_Page_Packs/1/images/
- [ ] manifest.json generated with correct structure
- [ ] page_assets_t has 14 rows
- [ ] pages_t has ocr_text_snippet populated
- [ ] Visual check: JPEG quality looks good

## Test 3: Segmentation (Container 1)
- [ ] segment_from_page_packs.py reads manifest successfully
- [ ] Detects ~10-15 articles from OCR + layout heuristics
- [ ] segmentation_v2_1.json generated
- [ ] image_references populated with file paths
- [ ] QC report generated and readable

## Test 4: Operator QA (Container 1)
- [ ] Operator reviews QC report
- [ ] Operator opens page images from 0220_Page_Packs/1/images/
- [ ] Operator identifies any segmentation errors
- [ ] Operator applies 1-2 corrections using apply_operator_corrections.py
- [ ] Database reflects corrections correctly

## Test 5: Scale-Up (Containers 2-53)
- [ ] Run backfill script on all containers
- [ ] Monitor for errors; log any failures
- [ ] Verify final counts: 1,025 pages, 53 containers in DB
- [ ] Spot-check 5 random containers for manifest validity
```

**Success Criteria:**
- All tests pass
- Documentation complete
- Operator confirms workflow is feasible
- Ready for Stage 2b segmentation at scale

---

## COULD-DO Items (Nice-to-Have)

These are optional but would significantly improve workflow quality. Include if time permits.

### 7. Lightweight QA Web Interface (Optional)

**File:** `scripts/qa/qc_web_ui.py` (NEW, Flask-based)

**Purpose:** Simple web UI showing:
- Page images with segmentation boundaries overlayed
- Click to mark pages as spreads
- Click to adjust work boundaries
- Submit corrections back to database

**Minimal Implementation:**
```python
from flask import Flask, render_template, request
app = Flask(__name__)

@app.route('/qc/<int:container_id>')
def qc_view(container_id):
    """Display pages and segmentation for manual QA."""
    manifest = load_manifest(container_id)
    works = load_segmentation(container_id)
    
    return render_template('qc.html', container_id=container_id, 
                          manifest=manifest, works=works)

@app.route('/api/mark_spread', methods=['POST'])
def mark_spread_api():
    """Operator clicks to mark two pages as a spread."""
    data = request.json
    mark_spread(db_conn, data['page_id_1'], data['page_id_2'])
    return {'status': 'ok'}
```

**Success Criteria:**
- UI loads and displays page images
- Operator can view work boundaries overlayed on images
- Simple interactions (click, drag) feel responsive
- Corrections sync to database

---

### 8. ML Preparation & Schema Documentation

**File:** `docs/SCHEMA_ML_READY.md` (NEW)

**Purpose:** Document how schema supports future ML tasks

**Topics:**
- How to extract ad images for deduplication (using work_occurrences_t.image_references)
- How to train layout classifiers (using pages_t with OCR structure + images)
- Where to store ML outputs (proposed embeddings_t, fingerprints_t tables)
- Example: building ad perceptual hash table

**Success Criteria:**
- Documentation is clear enough for future ML developer to build ad dedup
- Schema extensions are sketched out
- Data pipeline is extensible without major refactoring

---

## Summary of Deliverables

### By End of Week 1 (Jan 31):

✅ **Must-Do:**
1. Database schema migrations applied & tested
2. extract_pages_from_containers.py v2 refactored & tested on all 53 containers
3. segment_from_page_packs.py built & tested on Container 1
4. 1,025 pages extracted to JPEG; 53 manifests generated; DBpopulated

✅ **Should-Do:**
5. QA visualization tools (HTML + CSV reports) working
6. Operator correction script available & tested
7. Comprehensive testing & documentation complete

💡 **Could-Do (if time permits):**
8. QA web UI implemented (optional)
9. ML preparation documentation complete (optional)

### Success Metrics:

- All 53 containers processed without errors
- 1,025 JPEG images extracted (avg 0.85 MB each)
- 53 page pack manifests generated with correct JSON
- Database: page_assets_t (1,025 rows), page_pack_manifests_t (53 rows)
- Container 1 segmentation validated by operator
- QA report generated and operator confirms workflow is practical
- All changes committed to GitHub with clear commit messages
- Database migrations can be reproduced on clean instance

---

## GitHub Workflow

**For Every Major Task:**
1. Create feature branch: `git checkout -b feat(hjb): task-name`
2. Make changes; test locally
3. Commit with message: `feat(hjb): description` (Conventional Commits)
4. Push: `git push origin feat/task-name`
5. Create pull request with summary
6. Merge after verification

**CHANGELOG Entry (after each PR merge):**
```markdown
## [Unreleased]

### Added
- page_assets_t and page_pack_manifests_t tables for hybrid schema
- extract_pages_from_containers.py v2 with JPEG extraction & manifest generation
- segment_from_page_packs.py for content segmentation from page pack files
- QA report generators (HTML/CSV) for operator workflow

### Changed
- pages_t: added ocr_text_snippet, ocr_char_count, is_spread tracking
- work_occurrences_t: image_references now properly typed as JSON

### Database
- Migration 004: hybrid_schema_page_assets (adds 2 tables, modifies 2)
- All 53 containers backfilled to new schema
```

---

## Next Steps for Claude Code

1. **Read this brief** carefully
2. **Create GitHub branch:** `git checkout -b feat(hjb): hybrid-schema-stage2`
3. **Start with migrations:**
   - Write `database/migrations/004_hybrid_schema_page_assets.sql`
   - Test on dev database
   - Document rollback procedure
4. **Then refactor extract script:** (v2)
5. **Then build segmentation script** (new)
6. **Then QA tools** (reports + correction script)
7. **Then testing & documentation**
8. **Commit & document** everything

---

## Key References

- **Project Blueprint:** `/mnt/project/Historical_Journals___Books_Project_Blueprint__Proposed_Design_.docx`
- **Database Schema:** `/mnt/project/HJB_DATABASE_SCHEMA_REFERENCE.md`
- **Decision Analysis:** `/mnt/user-data/outputs/ANALYSIS_DECISION_SUMMARY.md`
- **Current Scripts:** `scripts/stage2/extract_pages_from_containers.py` (v1, to refactor)

---

## Communication with Michael

- **Questions:** Ask directly in chat; Michael is available
- **Daily status:** Update progress in STAGE2_IMPLEMENTATION_LOG.md
- **Blockers:** Flag immediately; don't work around
- **Testing:** Request Michael's approval before moving from one container to batch processing
- **Go/No-Go Decision:** Container 1 test decides if approach is sound; if problems found, escalate

---

**Claude Code: You have everything you need. Let's make this happen. 🚀**

**Start with:** Creating the migration script + testing it on a sample database connection.

