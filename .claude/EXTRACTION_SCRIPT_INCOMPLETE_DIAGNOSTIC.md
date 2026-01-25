# HJB Stage 2 - Extract Pages v2 Script Diagnostic

**Issue:** Script runs successfully but "Pages with images: 0" and "Pages with OCR: 0"

**Root Cause:** The extraction script is an incomplete skeleton. It's missing the core logic that actually:
1. Locates and extracts JP2 images from raw input
2. Converts JP2 → JPEG using Pillow
3. Copies OCR files (HOCR, DjVu XML) to page pack directory
4. Computes SHA256 hashes
5. Increments the `pages_with_images` and `pages_with_ocr` counters

---

## Evidence

### Location of Problem: Lines 663-668 in extract_pages_v2.py

```python
# For now, log what would be extracted
logger.debug(f"    Would extract: images/{page_index:04d}.jpg")
logger.debug(f"    Would copy: ocr/page_{page_index:04d}.*")

result['pages_processed'] += 1
# NOTE: pages_with_images and pages_with_ocr are NEVER incremented
```

### What's Missing

The page extraction loop should:

1. **Find JP2 files in raw input directory**
   - Pattern: `{raw_input_path}/*_jp2.zip` OR individual JP2 files
   - Extract or convert JP2 → JPEG

2. **Find OCR files in raw input directory**
   - Patterns: `*_hocr.html`, `*_djvu.xml`, `*_scandata.xml`, `*_alto.xml`
   - Copy to page pack OCR directory

3. **Handle file operations**
   - Use Pillow to convert JP2 to JPEG
   - Compute SHA256 hashes of extracted files
   - Create page_assets_t entries with paths and hashes

4. **Populate pages_t with OCR data**
   - Extract OCR text snippet (first 200 chars)
   - Store char count
   - Update ocr_text_snippet, ocr_char_count columns

5. **Increment counters**
   - If image extracted: `result['pages_with_images'] += 1`
   - If OCR copied: `result['pages_with_ocr'] += 1`

---

## Expected vs Actual Output

### Expected (from PRODUCTION_EXECUTION_GUIDE.md Line 134-135)
```
[SUCCESS] Container 1 processing complete
  Pages processed: 14
  Pages with images: 14
  Pages with OCR: 14
```

### Actual (from user's test run)
```
[SUCCESS] Container 1 processing complete
  Pages processed: 14
  Pages with images: 0
  Pages with OCR: 0
```

---

## What Needs to Be Done

Claude Code needs to complete the `process_container()` function by implementing the actual extraction loop (currently lines 660-668).

**Key Integration Points:**

1. **Image Extraction:**
   - Use `hocr_parser.py` that's already available (has OCR parsing logic)
   - Use Pillow `PIL.Image` for JP2 → JPEG conversion
   - Call `extract_jp2_images()` function (currently referenced but not implemented)

2. **OCR File Handling:**
   - Scan raw input directory for `.hocr`, `.xml`, `.txt` files
   - Copy files to `page_packs/{container_id}/ocr/`
   - Parse OCR files to extract text snippet

3. **Database Integration:**
   - Call `populate_page_assets_t()` to insert file references
   - Call `populate_pages_t()` to update OCR snippets
   - These functions are already defined but not called in the extraction loop

4. **Error Handling:**
   - Gracefully skip pages with missing JP2 (continue with next page)
   - Gracefully skip pages with missing OCR (allow OCR text to be NULL)
   - Log warnings but don't fail entire container

---

## Files Available for CC

1. **hocr_parser.py** — Parses HOCR HTML and DjVu XML OCR formats
   - `parse_djvu_xml()` — Extract text, confidence, word count from DjVu
   - `parse_hocr_html()` — Extract text, confidence, word count from HOCR
   - `parse_scandata_xml()` — Extract page type and metadata
   - **Already provides:** PageOCRData dataclass with all needed fields

2. **extract_pages_v2.py** — Main script
   - Already has helper functions: `extract_jp2_images()`, `populate_page_assets_t()`, `populate_pages_t()`
   - Missing: Loop logic that *calls* these functions and increments counters
   - Missing: JP2/OCR file discovery in raw input directory

---

## Test Data Available

**Container 1:**
- Container ID: 1
- Pages: 14
- Identifier: `sim_american-architect-and-architecture_1876-01-01_1_1`
- Raw Input Path: `\\RaneyHQ\Michael\02_Projects\Historical_Journals_And_Books\Raw_Input\0110_Internet_Archive\SIM\American_Architect_family\sim_american-architect-and-architecture_1876-01-01_1_1`

Files in raw input should include:
- `*.jp2` or `*_jp2.zip` (images)
- `*_hocr.html` (OCR)
- `*_djvu.xml` (OCR alternative)
- `*_scandata.xml` (metadata)

---

## Next Steps

1. **Claude Code:** Implement the extraction loop (lines 660-668)
   - Discover JP2 and OCR files in raw input
   - Extract/convert images
   - Copy OCR files
   - Call database population functions
   - Increment result counters

2. **Michael:** Run test again after CC completes
   ```bash
   python scripts/stage2/extract_pages_v2.py --container-id 1 --dry-run
   python scripts/stage2/extract_pages_v2.py --container-id 1
   ```
   Should show: `Pages with images: 14` and `Pages with OCR: 14`

3. **Verification:** Check output directory and database
   ```bash
   ls -la 0220_Page_Packs/1/images/      # Should have 14 JPEGs
   ls -la 0220_Page_Packs/1/ocr/         # Should have 14 OCR files
   SELECT COUNT(*) FROM page_assets_t WHERE container_id = 1;  # Should be 14
   ```

---

## CC Priority Items

**Must Have:**
- Discover JP2 and OCR files in raw input directory
- Extract JP2 → JPEG (using PIL)
- Copy OCR files to page pack directory
- Increment counters correctly
- Database inserts via `populate_page_assets_t()`

**Should Have:**
- SHA256 hashing of files
- OCR text extraction (first 200 chars) via hocr_parser
- Update pages_t with ocr_text_snippet

**Nice to Have:**
- Progress logging per page
- Parallel processing (low priority)
- Image preprocessing (deskew, binarization)

---

**Status:** Ready for CC implementation. Michael's test run worked correctly for the framework — just needs the extraction loop completed.
