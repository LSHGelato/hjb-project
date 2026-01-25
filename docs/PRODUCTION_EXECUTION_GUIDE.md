# HJB Stage 2 - Production Execution Guide

**For: Michael**
**Date: 2026-01-25**
**Status: READY FOR EXECUTION**

---

## Overview

This guide walks you through executing the Stage 2 hybrid schema implementation for the HJB project. All production-grade scripts are ready with comprehensive error handling, logging, and documentation.

### What's Included

| Component | File | Status | Purpose |
|-----------|------|--------|---------|
| **Database Migration** | `004_hybrid_schema_page_assets.sql` | Ready | Creates page_assets_t, page_pack_manifests_t |
| **Migration Executor** | `apply_migration.py` | Ready | Safely applies migration with verification |
| **Extraction v2** | `extract_pages_v2.py` | Ready | Extract JP2→JPEG, copy OCR, generate manifests |
| **Segmentation** | `segment_from_page_packs.py` | Ready | Identify work boundaries via heuristics |
| **QA Reports** | `generate_qc_report.py` | Ready | Generate HTML/CSV reports for review |
| **Corrections** | `apply_operator_corrections.py` | Ready | Apply operator corrections to database |

---

## Pre-Execution Checklist

### ✅ Database Prerequisites

- [ ] Database backup scheduled (contact HostGator if needed)
- [ ] You have DBA or admin credentials for applying migration
- [ ] Database connection tested: `python scripts/common/hjb_db.py`
- [ ] Expected output: `[OK] Database connection successful`

### ✅ File System Prerequisites

- [ ] Raw input path accessible: `\\RaneyHQ\Michael\02_Projects\Historical_Journals_And_Books\Raw_Input\0110_Internet_Archive\`
- [ ] Output directories creatable: `0220_Page_Packs/` (will be created by scripts)
- [ ] Disk space available: ~100 GB (53 containers × 1.8 MB avg per page × 1,025 pages)
- [ ] Python dependencies installed:
  ```bash
  pip install Pillow mysql-connector-python PyYAML
  ```

### ✅ Project Readiness

- [ ] All 53 containers in database with raw_input_path set
- [ ] All 1,025 pages registered in pages_t
- [ ] OCR files available in raw input directories
- [ ] Migration script syntax verified (no SQL errors)

---

## Execution Timeline

### Phase 1: Database Migration (Day 1)
**Time: ~15 minutes**

```bash
# Step 1: Test migration syntax (dry-run)
python scripts/database/apply_migration.py \
  --migration-file database/migrations/004_hybrid_schema_page_assets.sql \
  --dry-run

# Expected Output:
# [INFO] Loading migration: database\migrations\004_hybrid_schema_page_assets.sql
# [INFO] Parsed 15 SQL statements
# [INFO] [DRY RUN] Statements parsed but not executed
# [INFO]   [1] CREATE TABLE IF NOT EXISTS page_assets_t ...
# ... (15 statements total)

# Step 2: Apply migration (requires DBA credentials)
python scripts/database/apply_migration.py \
  --migration-file database/migrations/004_hybrid_schema_page_assets.sql

# Expected Output:
# [INFO] Loading migration: database\migrations\004_hybrid_schema_page_assets.sql
# [INFO] Parsed 15 SQL statements
# [INFO] Migration complete: X executed, Y skipped

# Step 3: Verify migration
python scripts/database/apply_migration.py --verify

# Expected Output:
# [INFO] Verifying migration...
# [INFO] [OK] page_assets_t exists with 20 columns
# [INFO] [OK] page_pack_manifests_t exists with N columns
# [INFO] [OK] pages_t has 3 new columns
# [INFO] [OK] Migration verification passed
```

**If migration fails:**
- Check error message in `migration.log`
- Ensure user has CREATE TABLE and ALTER TABLE privileges
- Contact HostGator if permission issue
- Try running with DBA account via direct mysql command

---

### Phase 2a: Test Extraction (Container 1 only)
**Time: ~5-10 minutes**

```bash
# Step 1: Dry-run extraction on Container 1
python scripts/stage2/extract_pages_v2.py \
  --container-id 1 \
  --dry-run

# Expected Output:
# ======================================================================
# Processing Container 1
# ======================================================================
# Container: sim_american-architect-and-architecture_1876-01-01_1_1
# Raw input path: \\RaneyHQ\Michael\02_Projects\...
# Found 14 pages to process
#   Page 1/14: page_id=...
#   Page 2/14: page_id=...
#   ... (14 pages total)
# ======================================================================
# SUMMARY
# ======================================================================
# Containers: 1 successful, 0 failed
# Pages processed: 14
# [DRY RUN] No files or database changes were made

# Step 2: Run extraction for real
python scripts/stage2/extract_pages_v2.py --container-id 1

# Expected Output: Same as above, but with actual file creation
# [DB] Inserted 14 pages into pages_t
# [DB] Created page_pack_manifests entry: 1
# [SUCCESS] Container 1 processing complete
#   Pages processed: 14
#   Pages with images: 14
#   Pages with OCR: 14

# Step 3: Verify output files
ls -la 0220_Page_Packs/1/
# Expected: manifest.json, images/, ocr/ directories

# Step 4: Check database
sqlite3 <<EOF
SELECT COUNT(*) FROM page_assets_t WHERE container_id = 1;
-- Expected: 14

SELECT COUNT(*) FROM page_pack_manifests_t WHERE container_id = 1;
-- Expected: 1
EOF
```

**If extraction fails:**
- Check `extract_pages_v2.log` for details
- Verify OCR files exist in raw input directory
- Ensure Pillow is installed: `pip install Pillow`
- Check that page_assets_t and page_pack_manifests_t exist in DB

---

### Phase 2b: Test Segmentation (Container 1)
**Time: ~3-5 minutes**

```bash
# Run segmentation on Container 1 manifest
python scripts/stage2/segment_from_page_packs.py \
  --container-id 1

# Expected Output:
# [INFO] Loading manifest: 0220_Page_Packs\1\manifest.json
# [INFO] Container 1: 14 pages
# [INFO] Loading page data...
# [INFO] Loaded 14 pages
# [INFO] Detecting work boundaries...
# [INFO] Found X works from 14 pages
# [INFO] Linking images to works...
# [INFO] Generating segmentation manifest...
# [INFO] Generated segmentation manifest: 0220_Page_Packs\1\segmentation\segmentation_v2_1.json
#
# [RESULTS] Container 1
#   Works detected: 10-15 (typical for 14-page issue)
#   By type: {'article': 10, 'advertisement': 2, 'plate': 1}
#   Average confidence: 0.72
#     [1] ARTICLE: pages [0], confidence 0.85
#     [2] ARTICLE: pages [1, 2], confidence 0.70
#     ... (10-15 total)

# Step 2: Verify segmentation output
cat 0220_Page_Packs/1/segmentation/segmentation_v2_1.json | head -50
# Should see valid JSON with works array
```

---

### Phase 3: QA Report Generation (Container 1)
**Time: ~2 minutes**

```bash
# Generate HTML and CSV reports
python scripts/qa/generate_qc_report.py --container-id 1

# Expected Output:
# [INFO] Generating QC reports for Container 1
# [INFO] Loaded segmentation with 10 works
# [INFO] Generated HTML report: 0220_Page_Packs\1\qa\qc_report.html
# [INFO] Generated CSV report: 0220_Page_Packs\1\qa\qc_report.csv
#
# [SUCCESS] Reports generated
#   HTML: 0220_Page_Packs\1\qa\qc_report.html
#   CSV: 0220_Page_Packs\1\qa\qc_report.csv

# Step 2: Open and review HTML report
open 0220_Page_Packs/1/qa/qc_report.html
# Should show:
# - Summary stats (articles, ads, plates count)
# - Table of detected works with confidence scores
# - Page ranges for each work

# Step 3: Review CSV in Excel
open 0220_Page_Packs/1/qa/qc_report.csv
# Should have columns: Work#, Type, Pages, Title, Confidence, ImageCount, Notes
```

---

### Phase 4: Operator QA & Corrections (Container 1)
**Time: ~10-15 minutes**

1. **Review QC Report**
   - Open `0220_Page_Packs/1/qa/qc_report.html` in browser
   - Check work boundaries look reasonable
   - Note any obvious errors (missing headlines, wrong type guesses, etc.)

2. **Apply Corrections (if needed)**
   ```bash
   # Example: Mark pages 10-11 as plate type
   python scripts/qa/apply_operator_corrections.py \
     --page-ids 10 11 \
     --page-type plate

   # Example: Mark pages 5 and 6 as spread
   python scripts/qa/apply_operator_corrections.py \
     --spread 5 6

   # Example: Mark entire container as verified
   python scripts/qa/apply_operator_corrections.py \
     --container-id 1 \
     --mark-verified
   ```

3. **Re-run Reports** (optional)
   ```bash
   python scripts/qa/generate_qc_report.py --container-id 1
   # Review updated report
   ```

4. **Sign-Off**
   - If Container 1 segmentation looks good: ✅ **GO**
   - If problems found: Document and decide whether to refine heuristics or proceed

---

### Phase 5: Scale to All Containers (Containers 2-53)
**Time: ~30-60 minutes (mostly automated)**

```bash
# Option A: Process all pending containers
python scripts/stage2/extract_pages_v2.py --all-pending

# Expected Output:
# [INFO] Processing 52 container(s)
# [Container 1] Processing...
# [Container 1] processing complete: 14 pages processed
# [Container 2] Processing...
# [Container 2] processing complete: 14 pages processed
# ... (52 containers total)
# [SUMMARY]
# Containers: 52 successful, 0 failed
# Pages processed: 1,011

# Option B: Process specific containers
python scripts/stage2/extract_pages_v2.py --container-id 2 3 4 5

# Step 2: Run segmentation on all
python scripts/stage2/segment_from_page_packs.py --container-id 1 2 3 4 5 --all

# Step 3: Generate reports for sample containers
for i in 1 5 10 15 20 25 30 35 40 45 50 53; do
  python scripts/qa/generate_qc_report.py --container-id $i
done

# Step 4: Spot-check 5 random containers
# Review their HTML reports for quality
```

**Monitoring:**

While processing runs, monitor:
```bash
# Watch log file in real-time
tail -f extract_pages_v2.log
tail -f segmentation.log

# Check disk usage
du -sh 0220_Page_Packs/

# Check database growth
SELECT COUNT(*) FROM page_assets_t;      -- Should reach ~1,025
SELECT COUNT(*) FROM page_pack_manifests_t;  -- Should reach 53
```

---

## Expected Results

### Database Tables

After completion:

```sql
-- Check page_assets_t
SELECT COUNT(*) FROM page_assets_t;
-- Expected: 1,025 (one per page)

SELECT DISTINCT ocr_source FROM page_assets_t;
-- Expected: ['ia_djvu', 'ia_hocr'] or similar

-- Check page_pack_manifests_t
SELECT COUNT(*) FROM page_pack_manifests_t WHERE is_active = 1;
-- Expected: 53 (one per container)

-- Verify pages_t updates
SELECT COUNT(*) FROM pages_t WHERE ocr_text_snippet IS NOT NULL;
-- Expected: 1,025 (all pages)

SELECT COUNT(*) FROM pages_t WHERE is_manually_verified = 1;
-- Expected: 0+ (after operator corrections)
```

### File System

```bash
# Check page packs directory structure
find 0220_Page_Packs -type f -name "manifest.json" | wc -l
# Expected: 53

find 0220_Page_Packs -type f -name "*.jpg" | wc -l
# Expected: ~1,025

find 0220_Page_Packs -type f -name "segmentation_v2_1.json" | wc -l
# Expected: 53 (if segmentation ran on all)

du -sh 0220_Page_Packs
# Expected: ~90-100 GB (depends on JPEG quality)
```

### Logs

Check for successful completion:

```bash
grep -c "Container.*processing complete" extract_pages_v2.log
# Expected: 53

grep -c "ERROR\|FAILED" extract_pages_v2.log
# Expected: 0 (or very few)

tail -20 extract_pages_v2.log
# Should show final summary with success count
```

---

## Troubleshooting

### Issue: "Permission denied" on raw_input_path

**Cause:** UNC path not accessible or wrong credentials
**Solution:**
1. Verify path: `\\RaneyHQ\Michael\...` is accessible
2. Check network connection to NAS
3. Ensure credentials are valid
4. Try from Command Prompt first: `dir \\RaneyHQ\Michael\...`

### Issue: "Pillow not installed"

**Cause:** Image extraction requires Pillow library
**Solution:**
```bash
pip install Pillow
# Or if issues:
pip install --upgrade Pillow
```

### Issue: Database connection fails

**Cause:** Credentials invalid or database down
**Solution:**
1. Test connection: `python scripts/common/hjb_db.py`
2. Check HJB_MYSQL_* env vars: `set | grep HJB_MYSQL`
3. Verify .env file has correct credentials
4. Check HostGator status dashboard

### Issue: Extraction slow or hanging

**Cause:** Network latency, large files, or system resources
**Solution:**
1. Check network: `ping \\RaneyHQ`
2. Monitor disk space: `df -h`
3. Check system load: `htop` or Task Manager
4. Run one container at a time if needed

### Issue: Missing OCR files in output

**Cause:** OCR files not found in raw input directory
**Solution:**
1. Check raw_input_path in database
2. Manually verify OCR files exist:
   ```bash
   ls \\RaneyHQ\...\raw\sim_american-architect*
   ```
3. If missing, may need to re-download from IA

### Issue: Segmentation produces too few/many works

**Cause:** Heuristics not tuned for this publication
**Solution:**
1. Review detected works in HTML report
2. Check OCR quality (may have errors)
3. Adjust thresholds in `segment_from_page_packs.py`:
   - Line ~96: `threshold` parameter for dividing lines
   - Line ~115: `max_length` parameter for headlines
   - Line ~348-351: confidence thresholds
4. Re-run with adjusted parameters

---

## Rollback Procedures

### If Migration Fails

```bash
# Uncomment DOWN section in migration file
# Or run manually:
DROP TABLE IF EXISTS page_pack_manifests_t;
DROP TABLE IF EXISTS page_assets_t;
ALTER TABLE pages_t DROP COLUMN IF EXISTS is_spread_with;
-- ... etc.

# Restore from backup if data was corrupted
mysql -h [host] -u [user] -p < backup.sql
```

### If Extraction Causes Issues

```bash
# Delete page pack directory
rm -rf 0220_Page_Packs/

# Rollback database (using backup)
DELETE FROM page_assets_t WHERE container_id = 1;
DELETE FROM page_pack_manifests_t WHERE container_id = 1;
UPDATE pages_t SET ocr_text_snippet = NULL WHERE container_id = 1;
```

---

## Performance Tuning

### To Improve Extraction Speed

1. **Increase parallelism** (if CPU-bound):
   - Modify `extract_pages_v2.py` to use ThreadPoolExecutor
   - Set `workers=4` or similar

2. **Reduce JPEG quality** (if I/O-bound):
   - Change `--jpeg-quality 70` instead of 90
   - Reduces file size, faster disk writes

3. **Use local SSD** for temp files:
   - Copy raw input to local drive first
   - Process locally, then sync results to NAS

### To Improve Segmentation

1. **Cache OCR parsing** (if running multiple times):
   - Segmentation reads OCR files; cache parsed text
   - Saves re-parsing identical files

2. **Parallel work detection** (future enhancement):
   - Process pages in parallel
   - Merge work boundaries at end

---

## Success Checklist

- [ ] Migration applied successfully
- [ ] Container 1 extraction completed (14 pages)
- [ ] Container 1 segmentation completed (10+ works detected)
- [ ] Container 1 QC report generated and reviewed
- [ ] Operator approved Container 1 results
- [ ] All 52 remaining containers processed
- [ ] 1,025 JPEG images extracted
- [ ] 53 page pack manifests generated
- [ ] 1,025 page_assets_t records created
- [ ] 53 page_pack_manifests_t records created
- [ ] Spot-check of 5 random containers shows quality
- [ ] No critical errors in logs
- [ ] Database verified with query checks
- [ ] Results documented in STAGE2_IMPLEMENTATION_LOG.md

---

## Next Steps After Execution

1. **Document Results**
   - Update `STAGE2_IMPLEMENTATION_LOG.md` with stats
   - Record container process times
   - Note any deviations from plan

2. **Stage 2c Preparation** (Image Processing)
   - Review extracted JPEG quality
   - Decide on preprocessing (deskew, binarize, etc.)
   - Plan image normalization strategy

3. **Stage 3 Preparation** (Enrichment)
   - Begin planning layout analysis
   - Consider ML for work type detection
   - Evaluate OCR quality per container

4. **Archive Raw Input** (Optional, after verification)
   - Consider moving raw_input to cheaper storage
   - Keep only page packs on fast SSD

---

## Support & Escalation

**For questions about:**
- Scripts: Review docstrings in relevant .py file
- Database schema: See `.claude/HJB_DATABASE_SCHEMA_REFERENCE.md`
- Architecture: See `.claude/CLAUDE_CODE_COMPREHENSIVE_BRIEF.md`
- Git workflows: See GitHub README

**For issues:**
1. Check logs: `extract_pages_v2.log`, `segmentation.log`, `migration.log`
2. Verify prerequisites: Database connection, file access, dependencies
3. Try dry-run mode: `--dry-run` flag on most scripts
4. Contact Claude Code for code modifications
5. Contact HostGator for database/network issues

---

**You have all the tools you need. Let's make Stage 2 happen! 🚀**
