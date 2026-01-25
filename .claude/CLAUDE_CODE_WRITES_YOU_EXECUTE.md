# HJB Hybrid Schema - Code Generation + Live Execution

**Approach:** Claude Code writes production scripts → Michael executes on actual data

**Phases:**
1. **CC Writes Code** (Jan 28-30)
   - Database migration SQL
   - extract_pages_from_containers.py v2
   - segment_from_page_packs.py
   - QA tools

2. **Michael Executes** (Jan 30-31)
   - Apply database migrations
   - Run extraction on 53 containers (90 min)
   - Run segmentation test on Container 1
   - Run operator QA workflow
   - Verify results

3. **CC Writes Commit Messages** (Jan 31-Feb 3)
   - Document results
   - Commit to GitHub
   - Push changes

---

## Phase 1: Code Generation (CC writes, you review)

### Task 1.1: Database Migration Script
**CC Writes:** `database/migrations/004_hybrid_schema_page_assets.sql`

**You Will:**
```bash
# Test on your database
mysql -u [user] -p [password] [database] < 004_hybrid_schema_page_assets.sql

# Verify tables created
mysql -u [user] -p [password] [database] -e "SHOW TABLES LIKE 'page_%';"

# If needed, rollback (CC will document procedure)
# Then re-apply
```

### Task 1.2: Extract Script (Refactored)
**CC Writes:** `scripts/stage2/extract_pages_from_containers.py`

**You Will:**
```bash
# Test on Container 1 first (14 pages)
python scripts/stage2/extract_pages_from_containers.py 1

# Verify output
ls -lh 0220_Page_Packs/1/images/ | head -5
cat 0220_Page_Packs/1/manifest.json | head -20

# Then run on all 53 (takes ~90 minutes)
for i in {1..53}; do
  echo "Processing container $i..."
  python scripts/stage2/extract_pages_from_containers.py $i
done
```

### Task 1.3: Segmentation Script (New)
**CC Writes:** `scripts/stage2/segment_from_page_packs.py`

**You Will:**
```bash
# Test on Container 1
python scripts/stage2/segment_from_page_packs.py \
  0220_Page_Packs/1/manifest.json \
  --output-dir 0220_Page_Packs/1/segmentation

# Review output
cat 0220_Page_Packs/1/segmentation/segmentation_v2_1.json | python -m json.tool | head -50

# Visually inspect images
open 0220_Page_Packs/1/images/
# Compare boundaries to OCR text

# Then run on remaining containers
for i in {2..53}; do
  python scripts/stage2/segment_from_page_packs.py \
    0220_Page_Packs/$i/manifest.json \
    --output-dir 0220_Page_Packs/$i/segmentation
done
```

### Task 1.4: QA Tools
**CC Writes:**
- `scripts/qa/generate_qc_report.py` (HTML/CSV reports)
- `scripts/qa/apply_operator_corrections.py` (SQL helpers)

**You Will:**
```bash
# Generate QA report for Container 1
python scripts/qa/generate_qc_report.py 1 \
  --output-dir 0220_Page_Packs/1/qa

# Review HTML report
open 0220_Page_Packs/1/qa/qc_report.html

# Review CSV in Excel
open 0220_Page_Packs/1/qa/qc_report.csv

# Apply a correction (example: mark pages 3-4 as spread)
python scripts/qa/apply_operator_corrections.py \
  mark_spread \
  --page-id-1 3 \
  --page-id-2 4 \
  --database [dbname] \
  --user [user]
```

---

## Phase 2: You Execute on Real Data

### Prerequisites
```bash
# Have ready:
- Database credentials (raneywor_hjbproject on HostGator)
- Python 3.8+ installed
- Required packages: Pillow, mysql-connector-python, lxml

# Install packages
pip install Pillow mysql-connector-python lxml
```

### Execution Timeline

**Thu Jan 30 Morning:** Database migration
```bash
# 1. Get migration SQL from CC
# 2. Apply to database
mysql -u [user] -p [password] raneywor_hjbproject < 004_hybrid_schema_page_assets.sql

# 3. Verify
mysql -u [user] -p [password] raneywor_hjbproject -e "SHOW TABLES LIKE 'page_%';"
mysql -u [user] -p [password] raneywor_hjbproject -e "SELECT COUNT(*) FROM page_assets_t;"
```

**Thu Jan 30 Afternoon:** Extract Container 1 test
```bash
# Test extraction on just 14 pages
python scripts/stage2/extract_pages_from_containers.py 1 --verbose

# Check results
ls -lh 0220_Page_Packs/1/images/
cat 0220_Page_Packs/1/manifest.json

# Verify database
mysql -u [user] -p [password] raneywor_hjbproject \
  -e "SELECT COUNT(*) FROM page_assets_t WHERE page_id BETWEEN 1 AND 14;"
```

**Thu Jan 30 Evening:** Segmentation Container 1 test
```bash
# Test segmentation
python scripts/stage2/segment_from_page_packs.py \
  0220_Page_Packs/1/manifest.json \
  --output-dir 0220_Page_Packs/1/segmentation \
  --verbose

# Review results
cat 0220_Page_Packs/1/segmentation/segmentation_v2_1.json | python -m json.tool
```

**Fri Jan 31 Morning:** Backfill all 53 containers
```bash
# Run extraction on all containers (90 min total)
for i in {1..53}; do
  echo "[$(date)] Processing container $i..."
  python scripts/stage2/extract_pages_from_containers.py $i
  
  # Progress check
  if [ $((i % 10)) -eq 0 ]; then
    echo "Completed $i containers. Checking database..."
    mysql -u [user] -p [password] raneywor_hjbproject \
      -e "SELECT COUNT(*) FROM page_assets_t;"
  fi
done

# After completion: verify totals
echo "Final verification:"
mysql -u [user] -p [password] raneywor_hjbproject \
  -e "SELECT COUNT(*) as 'Total Pages' FROM page_assets_t;"
mysql -u [user] -p [password] raneywor_hjbproject \
  -e "SELECT COUNT(*) as 'Total Manifests' FROM page_pack_manifests_t;"
```

**Fri Jan 31 Afternoon:** Operator QA workflow
```bash
# Generate QA report
python scripts/qa/generate_qc_report.py 1 \
  --output-dir 0220_Page_Packs/1/qa

# Open and review
open 0220_Page_Packs/1/qa/qc_report.html
open 0220_Page_Packs/1/qa/qc_report.csv

# Test workflow: mark 1-2 corrections
python scripts/qa/apply_operator_corrections.py \
  mark_spread \
  --page-id-1 3 \
  --page-id-2 4

python scripts/qa/apply_operator_corrections.py \
  update_page_type \
  --page-ids 10,11 \
  --new-type plate

# Verify corrections in database
mysql -u [user] -p [password] raneywor_hjbproject \
  -e "SELECT page_id, is_spread, is_spread_with FROM pages_t WHERE page_id IN (3, 4);"
```

---

## How CC Helps You Execute

### Before You Run Each Script:

**CC Provides:**
1. ✅ Complete, tested code
2. ✅ Requirements.txt (for pip install)
3. ✅ README with usage examples
4. ✅ --help output (what parameters are available)
5. ✅ Logging (so you can see what's happening)
6. ✅ Error handling (graceful failures, not crashes)

### As You Run:

**You Have:**
1. ✅ CC's script running on your actual data
2. ✅ Real progress (images being extracted, DB being populated)
3. ✅ Real feedback (logs showing what's happening)
4. ✅ Real results (can inspect manifest.json, check database)

### If Something Goes Wrong:

**You Do:**
1. Stop the script
2. Share the error with CC
3. CC fixes the code
4. You re-run

Example:
```
Error: "cannot find JP2 files in /Raw_Input/[container_id]/"
→ Tell CC the actual path structure
→ CC fixes the path handling
→ You re-run
```

---

## What CC Will Include in Each Script

### Every Script Has:

```python
#!/usr/bin/env python3
"""
Script description
Usage: python script.py [args]
"""

import logging
import argparse

# Setup logging so you can see progress
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description='...')
    parser.add_argument('container_id', help='Container ID to process')
    parser.add_argument('--verbose', action='store_true', help='Enable debug logging')
    parser.add_argument('--dry-run', action='store_true', help='Show what would happen without doing it')
    
    args = parser.parse_args()
    
    # Actual work
    logger.info(f"Processing container {args.container_id}...")
    
    try:
        # Do the thing
        result = process_container(args.container_id)
        logger.info(f"Success! Processed {result['pages']} pages")
    except Exception as e:
        logger.error(f"Failed: {e}")
        raise

if __name__ == '__main__':
    main()
```

**You'll See Output Like:**
```
2026-01-30 14:23:45 - INFO - Processing container 1...
2026-01-30 14:23:47 - INFO - Found 14 pages in raw input
2026-01-30 14:23:48 - INFO - Extracting images...
2026-01-30 14:23:50 - INFO - Converting page 1: page_0001.jp2 → page_0001.jpg
2026-01-30 14:23:51 - INFO - Converting page 2: page_0002.jp2 → page_0002.jpg
...
2026-01-30 14:26:15 - INFO - Generated manifest.json (125 KB)
2026-01-30 14:26:16 - INFO - Populating database...
2026-01-30 14:26:17 - INFO - Created page_assets_t entries for 14 pages
2026-01-30 14:26:18 - INFO - Created page_pack_manifests_t entry
2026-01-30 14:26:19 - INFO - Success! Processed 14 pages
```

---

## Why This Works Better

✅ **You see the real data being processed**
- Images actually being extracted
- Database actually being populated
- Real pages, real containers, real results

✅ **You control the execution**
- Run when you want
- Stop if needed
- Retry with fixes
- Know exactly what happened

✅ **CC gets real feedback**
- If something doesn't work with your actual file structure
- If database behaves unexpectedly
- If heuristics need tuning
- Real errors → real fixes

✅ **You maintain control**
- Database operations are yours
- File operations are yours
- Can inspect intermediate results
- Understand every step

---

## Workflow Summary

**CC:**
- Jan 28-30: Write complete, tested scripts
- Provide requirements.txt, usage docs
- Include error handling & logging
- Make scripts idempotent (safe to re-run)

**You:**
- Jan 30: Apply migration, test on Container 1
- Jan 31: Run extraction on 53 containers (90 min)
- Jan 31: Test segmentation, run QA workflow
- Jan 31-Feb 3: Verify results, confirm success

**Together:**
- Any issues → CC fixes code → you re-run
- Real progress on real data
- Confident handoff to GitHub

---

## File Locations (Where You'll Find Things)

**Scripts CC Writes:**
```
scripts/stage2/
├── extract_pages_from_containers.py    (refactored v2)
├── segment_from_page_packs.py          (new)
└── __init__.py

scripts/qa/
├── generate_qc_report.py               (new)
└── apply_operator_corrections.py       (new)

database/migrations/
└── 004_hybrid_schema_page_assets.sql   (new)

docs/
└── STAGE2_HYBRID_SCHEMA.md             (guide, new)
```

**You'll Execute From:**
```bash
cd /path/to/hjb-project/  # Your GitHub repo root

# Migrations
mysql -u [user] -p [password] [db] < database/migrations/004_hybrid_schema_page_assets.sql

# Scripts
python scripts/stage2/extract_pages_from_containers.py 1
python scripts/stage2/segment_from_page_packs.py 0220_Page_Packs/1/manifest.json
python scripts/qa/generate_qc_report.py 1
```

**Output Generated:**
```
0220_Page_Packs/
├── 1/
│   ├── manifest.json              (you'll review this)
│   ├── images/page_*.jpg          (you'll see JPEG extraction)
│   ├── ocr/page_*.hocr            (OCR copied)
│   ├── segmentation/              (work boundaries detected)
│   └── qa/
│       ├── qc_report.html         (you'll open in browser)
│       └── qc_report.csv          (you'll review in Excel)
├── 2/
│   └── ...
└── ... (through 53/)

Database populated:
├── page_assets_t:           1,025 rows (you'll verify with SQL)
└── page_pack_manifests_t:   53 rows
```

---

## Next Steps

1. **CC writes the code** (complete with error handling, logging, documentation)
2. **You run the code** (on your actual data, your actual database)
3. **CC commits the results** (to GitHub with your approval)

Ready to start? I'll have Claude Code write production-quality scripts for you to execute.

