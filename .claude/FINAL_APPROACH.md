# Final Approach: CC Writes, You Execute

**Status:** ✅ Ready  
**Execution Model:** Production scripts written by Claude Code, executed by Michael on real data  
**Timeline:** Tue 1/28 - Mon 2/3  
**Result by Jan 31:** 1,200 JPEG images extracted, 53 manifests generated, DB populated

---

## The Model

### Phase 1: Claude Code Writes Code (Tue-Thu Jan 28-30)

**CC Delivers Production Scripts:**
1. `004_hybrid_schema_page_assets.sql` — Database migration
2. `extract_pages_from_containers.py` v2 — Image extraction + manifest generation
3. `segment_from_page_packs.py` — Segmentation from page packs
4. `generate_qc_report.py` — QA reports (HTML/CSV)
5. `apply_operator_corrections.py` — Database correction helpers
6. `STAGE2_HYBRID_SCHEMA.md` — Complete usage guide

**Each Script Includes:**
- ✅ Error handling (graceful, not crash)
- ✅ Logging (see exactly what's happening)
- ✅ Dry-run mode (preview without executing)
- ✅ Verbose mode (debug output)
- ✅ Usage docs & examples
- ✅ Requirements.txt
- ✅ Idempotent (safe to re-run)

### Phase 2: You Execute on Real Data (Thu-Fri Jan 30-31)

**Thursday:**
```bash
# Apply migration to YOUR database
mysql -u [user] -p [password] raneywor_hjbproject < 004_hybrid_schema_page_assets.sql

# Test extraction on Container 1 (14 pages, takes ~2 min)
python scripts/stage2/extract_pages_from_containers.py 1 --verbose

# Verify: Check images extracted, manifest created, DB populated
ls -lh 0220_Page_Packs/1/images/
cat 0220_Page_Packs/1/manifest.json | head -30
mysql -u [user] -p [password] raneywor_hjbproject -e "SELECT COUNT(*) FROM page_assets_t WHERE page_id <= 14;"

# Test segmentation on Container 1
python scripts/stage2/segment_from_page_packs.py 0220_Page_Packs/1/manifest.json --verbose

# Review segmentation output
cat 0220_Page_Packs/1/segmentation/segmentation_v2_1.json | python -m json.tool | head -50
```

**Friday Morning:**
```bash
# Backfill all 53 containers (takes ~90 minutes)
for i in {1..53}; do
  echo "[$(date)] Processing container $i..."
  python scripts/stage2/extract_pages_from_containers.py $i
done

# Verify completion
mysql -u [user] -p [password] raneywor_hjbproject -e "
  SELECT 
    'page_assets_t' as table_name, COUNT(*) as row_count 
  FROM page_assets_t
  UNION ALL
  SELECT 
    'page_pack_manifests_t', COUNT(*) 
  FROM page_pack_manifests_t;
"
```

**Friday Afternoon:**
```bash
# Generate QA report
python scripts/qa/generate_qc_report.py 1 --output-dir 0220_Page_Packs/1/qa

# Review in browser and Excel
open 0220_Page_Packs/1/qa/qc_report.html
open 0220_Page_Packs/1/qa/qc_report.csv

# Test operator workflow: mark pages as spread
python scripts/qa/apply_operator_corrections.py mark_spread --page-id-1 3 --page-id-2 4

# Verify in database
mysql -u [user] -p [password] raneywor_hjbproject -e "
  SELECT page_id, is_spread, is_spread_with FROM pages_t WHERE page_id IN (3, 4);
"
```

### Phase 3: CC Commits Code (Mon 2/3)

Once you confirm everything works:
- CC documents results
- Commits to GitHub: `feat(hjb/stage2): hybrid schema implementation`
- Updates CHANGELOG.md
- Pushes to main

---

## Why This Approach

✅ **You own the execution**
- Run on YOUR data when YOU want
- See progress in real-time
- Full control and visibility

✅ **Real feedback for CC**
- Actual file paths, actual database behavior
- Real errors → real fixes
- CC can address issues immediately

✅ **No surprises**
- You know exactly what's running
- You inspect every result
- You verify database changes

✅ **Confidence**
- Scripts are tested before you run them
- Logging shows everything
- You understand each step

---

## What You Need

**Before You Start:**
```bash
# Python 3.8+
python --version

# Install dependencies
pip install Pillow mysql-connector-python lxml

# Database access
# - Host: HostGator MySQL
# - Database: raneywor_hjbproject
# - User: [your MySQL user]
# - Password: [your MySQL password]

# File access
# - Read: /mnt/user-data/uploads or local raw inputs
# - Write: /mnt/user-data/outputs or your NAS working directory
```

---

## Expected Output

**When You're Done (Jan 31):**

```
✅ Database
  - page_assets_t: 1,025 rows
  - page_pack_manifests_t: 53 rows

✅ Filesystem
  - 0220_Page_Packs/[1-53]/manifest.json (53 files)
  - 0220_Page_Packs/[1-53]/images/*.jpg (1,025 JPEGs)
  - 0220_Page_Packs/[1-53]/ocr/*.hocr (OCR files)
  - 0220_Page_Packs/[1-53]/segmentation/ (work boundaries)
  - 0220_Page_Packs/[1-53]/qa/ (reports)

✅ You Verified
  - Segmentation boundaries match articles ✓
  - Operator workflow is practical ✓
  - Database integrity is correct ✓

✅ Ready for GitHub
  - All scripts working
  - All data populated
  - Ready to commit
```

---

## If Something Breaks

**You:**
1. Stop the script
2. Share the error with CC
3. CC fixes the code
4. You re-run

Example:
```
Error: "JPEG conversion failed on page 5"
↓
You: "Got error on page 5: [error message]. Here's the jp2 file structure..."
↓
CC: "Found the issue. Here's the fix."
↓
You: "Re-running... Success!"
```

---

## Timeline

| Day | What CC Does | What You Do |
|-----|--------------|-----------|
| Tue 1/28 | Write migration SQL | Validate & apply to DB |
| Wed 1/29 | Refactor extract script | Test on Container 1 |
| Thu 1/30 | Build segmentation script | Test on Container 1, validate boundaries |
| Thu 1/30 | Review & iterate if needed | Run backfill on all 53 |
| Fri 1/31 | Write QA tools | Run operator workflow test |
| Mon 2/3 | Commit & push | Verify database integrity |

---

## Success Checklist

By Jan 31:
- [ ] Migration applied to database
- [ ] extract_pages_from_containers.py working on Container 1
- [ ] 14 JPEGs extracted for Container 1
- [ ] Container 1 manifest.json valid
- [ ] Segmentation working on Container 1
- [ ] All 53 containers processed
- [ ] page_assets_t has 1,025 rows
- [ ] page_pack_manifests_t has 53 rows
- [ ] QA reports generated
- [ ] Operator workflow validated
- [ ] All image paths resolve
- [ ] All database changes verified

---

## Next Step

**Say "ready" and I'll start Claude Code with clear instructions to write production scripts.**

CC will:
1. Write complete, tested code
2. Provide usage documentation
3. Include error handling & logging
4. Make scripts safe to run on real data

You will:
1. Run the scripts on YOUR data
2. Verify the results
3. Confirm everything works
4. Approve for GitHub push

Let's go! 🚀

