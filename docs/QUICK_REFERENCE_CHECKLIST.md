# HJB Stage 2 - Quick Reference Checklist

Print this page and use as you execute.

---

## PRE-EXECUTION ✅

- [ ] Database backup scheduled
- [ ] DBA credentials available
- [ ] Network to NAS working: `ping \\RaneyHQ`
- [ ] Python dependencies: `pip install Pillow mysql-connector-python PyYAML`
- [ ] DB connection test: `python scripts/common/hjb_db.py` → `[OK]`

---

## PHASE 1: Migration (Day 1)

```bash
# DRY-RUN
python scripts/database/apply_migration.py \
  --migration-file database/migrations/004_hybrid_schema_page_assets.sql \
  --dry-run
```
- [ ] No SQL syntax errors

```bash
# APPLY
python scripts/database/apply_migration.py \
  --migration-file database/migrations/004_hybrid_schema_page_assets.sql
```
- [ ] Migration complete
- [ ] Check `migration.log` for errors

```bash
# VERIFY
python scripts/database/apply_migration.py --verify
```
- [ ] `[OK] Migration verification passed`

---

## PHASE 2A: Test Extraction (Container 1)

```bash
# DRY-RUN
python scripts/stage2/extract_pages_v2.py --container-id 1 --dry-run
```
- [ ] 14 pages to process
- [ ] No errors in output

```bash
# EXECUTE
python scripts/stage2/extract_pages_v2.py --container-id 1
```
- [ ] 14 pages processed
- [ ] 14 pages with images
- [ ] 14 pages with OCR

```bash
# VERIFY FILES
ls -la 0220_Page_Packs/1/
```
- [ ] `manifest.json` exists
- [ ] `images/` directory has 14 .jpg files
- [ ] `ocr/` directory has 14 OCR files

```bash
# VERIFY DATABASE
# Run in MySQL:
SELECT COUNT(*) FROM page_assets_t WHERE container_id = 1;
SELECT COUNT(*) FROM page_pack_manifests_t WHERE container_id = 1;
```
- [ ] page_assets_t: 14 rows
- [ ] page_pack_manifests_t: 1 row

---

## PHASE 2B: Test Segmentation (Container 1)

```bash
python scripts/stage2/segment_from_page_packs.py --container-id 1
```
- [ ] `[INFO] Found X works from 14 pages`
- [ ] `[INFO] By type:` shows breakdown
- [ ] `[SUCCESS] Segmentation complete`

```bash
# VERIFY OUTPUT
cat 0220_Page_Packs/1/segmentation/segmentation_v2_1.json | python -m json.tool
```
- [ ] Valid JSON format
- [ ] `works` array has 10+ entries
- [ ] Each work has `type`, `pages`, `confidence`

---

## PHASE 3: QA Reports (Container 1)

```bash
python scripts/qa/generate_qc_report.py --container-id 1
```
- [ ] HTML report generated
- [ ] CSV report generated

```bash
# VIEW REPORTS
open 0220_Page_Packs/1/qa/qc_report.html
open 0220_Page_Packs/1/qa/qc_report.csv
```
- [ ] HTML shows summary stats
- [ ] HTML shows table of works
- [ ] CSV opens in Excel
- [ ] Works and page ranges make sense

**DECISION POINT: Does Container 1 segmentation look good?**
- [ ] YES → Continue to Phase 5
- [ ] NO → Apply corrections (Phase 4) or refine heuristics

---

## PHASE 4: Operator Corrections (if needed)

```bash
# Example: Fix page type
python scripts/qa/apply_operator_corrections.py \
  --page-ids 10 11 \
  --page-type plate
```

```bash
# Example: Mark pages as spread
python scripts/qa/apply_operator_corrections.py \
  --spread 5 6
```

```bash
# Example: Mark all as verified
python scripts/qa/apply_operator_corrections.py \
  --container-id 1 \
  --mark-verified
```

- [ ] Corrections applied successfully
- [ ] Re-generate reports if changed
- [ ] Results verified

---

## PHASE 5: Scale to All Containers

```bash
# EXTRACTION (all pending)
python scripts/stage2/extract_pages_v2.py --all-pending
```
- [ ] Monitor: `tail -f extract_pages_v2.log`
- [ ] Final summary: 52 successful, 0 failed
- [ ] 1,011 pages processed

```bash
# SEGMENTATION (all)
for i in {1..53}; do
  python scripts/stage2/segment_from_page_packs.py --container-id $i
done
```
- [ ] Monitor: `tail -f segmentation.log`
- [ ] 53 segmentation manifests generated

```bash
# QA REPORTS (spot-check sample)
for i in 1 10 20 30 40 50 53; do
  python scripts/qa/generate_qc_report.py --container-id $i
done
```
- [ ] 7 QC reports generated
- [ ] Spot-check results look reasonable

---

## VERIFICATION (Final)

```bash
# Database counts
SELECT COUNT(*) FROM page_assets_t;           # Should be ~1,025
SELECT COUNT(*) FROM page_pack_manifests_t;   # Should be 53
SELECT COUNT(DISTINCT ocr_source) FROM page_assets_t;  # 2+ formats
```

```bash
# Filesystem checks
find 0220_Page_Packs -type f -name "manifest.json" | wc -l    # 53
find 0220_Page_Packs -type f -name "*.jpg" | wc -l            # ~1,025
find 0220_Page_Packs -type f -name "segmentation*.json" | wc -l # 53
du -sh 0220_Page_Packs/                                        # ~90-100 GB
```

```bash
# Error check
grep -i "error\|failed" extract_pages_v2.log | wc -l           # 0 or very few
grep -i "error\|failed" segmentation.log | wc -l               # 0 or very few
```

---

## FINAL CHECKLIST

- [ ] Migration successful and verified
- [ ] 1,025 JPEG images extracted
- [ ] 53 page pack manifests generated
- [ ] Database populated (page_assets_t, page_pack_manifests_t)
- [ ] Container 1 segmentation reviewed and approved
- [ ] Sample containers (spot-check) look good
- [ ] No critical errors in logs
- [ ] Disk space adequate for results
- [ ] Results documented in STAGE2_IMPLEMENTATION_LOG.md

---

## TROUBLESHOOTING QUICK FIXES

| Issue | Quick Fix |
|-------|-----------|
| Permission denied on NAS | Check network, verify credentials |
| Pillow not installed | `pip install Pillow` |
| DB connection fails | `python scripts/common/hjb_db.py` to debug |
| Extraction slow | Check disk space, network, system load |
| Segmentation > 50 works | Heuristics may not suit this publication |
| Missing OCR files | Check raw_input_path, verify files exist |
| Migration rolls back | Check `migration.log`, try with DBA account |

---

## IMPORTANT FILE LOCATIONS

| File | Purpose | Location |
|------|---------|----------|
| Migration SQL | Creates tables | `database/migrations/004_hybrid_schema_page_assets.sql` |
| Extraction script | JP2→JPEG, manifests | `scripts/stage2/extract_pages_v2.py` |
| Segmentation | Work boundaries | `scripts/stage2/segment_from_page_packs.py` |
| QA Reports | HTML/CSV | `scripts/qa/generate_qc_report.py` |
| Corrections | Operator fixes | `scripts/qa/apply_operator_corrections.py` |
| Execution Guide | Detailed steps | `docs/PRODUCTION_EXECUTION_GUIDE.md` |
| Logs | Error details | `extract_pages_v2.log`, `segmentation.log`, `migration.log` |

---

## SUPPORT CONTACTS

- **Script Issues**: Review docstrings in .py file, check logs
- **Database Issues**: HostGator support for schema/permissions
- **Architecture Questions**: `.claude/CLAUDE_CODE_COMPREHENSIVE_BRIEF.md`
- **Code Modifications**: Contact Claude Code

---

**Estimated Total Time: 2-4 hours** (mostly automated)

**Expected Success Rate: >95%** (with proper pre-execution checks)

Good luck! 🚀
