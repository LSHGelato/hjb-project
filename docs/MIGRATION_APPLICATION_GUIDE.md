# Migration 004 Application Guide

## Overview

Migration `004_hybrid_schema_page_assets.sql` creates the hybrid database+filesystem schema required for Stage 2 page packs.

**Status:** Ready for application
**Size:** 10.9 KB
**Tables Created:** 2
**Columns Added:** 6
**Indexes Added:** 7

## What Gets Created

### New Tables

1. **`page_assets_t`** - References extracted images and OCR files per page
   - 20 columns including hashes, DPI normalization, preprocessing flags
   - 1:1 relationship with pages_t (UNIQUE constraint)
   - Indexed for common queries

2. **`page_pack_manifests_t`** - Documents page pack contents
   - Container-level manifest tracking
   - JSON fields for page list, OCR sources, extraction parameters
   - Versioning support (is_active, superseded_by)
   - Indexed by container_id, manifest_hash, created_at

### Modified Tables

1. **`pages_t`** - 4 new columns:
   - `ocr_text_snippet VARCHAR(500)` - First 500 chars of OCR for UI
   - `ocr_char_count INT` - Total character count
   - `is_spread TINYINT(1)` - Is this part of 2-page spread?
   - `is_spread_with INT UNSIGNED` - FK to other page in spread

2. **`work_occurrences_t`** - 1 new column:
   - `image_extraction_params JSON` - Extraction settings per work

## Pre-Migration Checklist

- [ ] Database backup taken (contact HostGator to confirm)
- [ ] You have DBA/admin privileges on MySQL
- [ ] Migration file location verified: `database/migrations/004_hybrid_schema_page_assets.sql`
- [ ] Network connection to database is stable

## How to Apply

### Option 1: Using Migration Script (Recommended)

```bash
# Dry-run first (verifies parsing without executing)
python scripts/database/apply_migration.py \
  --migration-file database/migrations/004_hybrid_schema_page_assets.sql \
  --dry-run

# If dry-run succeeds, apply for real
python scripts/database/apply_migration.py \
  --migration-file database/migrations/004_hybrid_schema_page_assets.sql

# Verify migration was applied
python scripts/database/apply_migration.py --verify
```

### Option 2: Direct MySQL (if script fails due to permissions)

```bash
# With a DBA account that has ALTER TABLE privileges
mysql -h [host] -u [admin_user] -p raneywor_hjbproject \
  < database/migrations/004_hybrid_schema_page_assets.sql
```

### Option 3: HostGator Support (if no local DB access)

Contact HostGator support with:
- Database name: `raneywor_hjbproject`
- SQL file path: `database/migrations/004_hybrid_schema_page_assets.sql`
- Request: "Apply this migration script to add page_assets_t and page_pack_manifests_t tables"

## Post-Migration Verification

Run these queries to confirm:

```sql
-- Check new tables exist
SHOW TABLES LIKE 'page_%';
-- Expected: page_assets_t, page_pack_manifests_t, pages_t

-- Verify column types
DESCRIBE page_assets_t;
DESCRIBE page_pack_manifests_t;

-- Check pages_t modifications
SELECT COLUMN_NAME, COLUMN_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME='pages_t'
AND COLUMN_NAME IN ('ocr_text_snippet', 'ocr_char_count', 'is_spread', 'is_spread_with')
ORDER BY ORDINAL_POSITION;

-- Count rows (should be 0 for new tables)
SELECT COUNT(*) FROM page_assets_t;    -- Should be 0
SELECT COUNT(*) FROM page_pack_manifests_t;  -- Should be 0
```

## Rollback Procedure

If migration causes problems:

1. **Backup current state:**
   ```bash
   mysqldump -h [host] -u [user] -p raneywor_hjbproject > backup_$(date +%Y%m%d_%H%M%S).sql
   ```

2. **Uncomment DOWN section in migration file** and apply it:
   ```bash
   python scripts/database/apply_migration.py \
     --migration-file database/migrations/004_hybrid_schema_page_assets_rollback.sql
   ```

   Or run manually:
   ```sql
   DROP TABLE IF EXISTS page_pack_manifests_t;
   DROP TABLE IF EXISTS page_assets_t;
   ALTER TABLE pages_t
   DROP COLUMN IF EXISTS is_spread_with,
   DROP COLUMN IF EXISTS is_spread,
   DROP COLUMN IF EXISTS ocr_char_count,
   DROP COLUMN IF EXISTS ocr_text_snippet;
   ```

3. **Restore from backup if needed:**
   ```bash
   mysql -h [host] -u [user] -p < backup_YYYYMMDD_HHMMSS.sql
   ```

## Troubleshooting

### Error: "Table already exists"
**Cause:** Migration was run before
**Solution:** This is expected and safe. The `IF NOT EXISTS` clauses prevent errors. Check that the table has the expected columns.

### Error: "Syntax error in SQL statement"
**Cause:** MySQL version may not support some syntax
**Solution:** Contact Claude Code or Michael. May need syntax adjustment.

### Error: "Access denied for CREATE TABLE"
**Cause:** User doesn't have DBA privileges
**Solution:** Use Option 2 (direct mysql with admin account) or Option 3 (contact HostGator)

### Error: "Foreign key constraint fails"
**Cause:** Existing data conflicts with new FK constraints
**Solution:** Check data integrity. May need to skip FK creation and add manually.

## Performance Impact

- **Schema Changes:** Minimal (adding columns and indexes)
- **Downtime:** None required (ALTER TABLE is online in modern MySQL)
- **Storage:** +~5 MB for new tables (before backfill)
- **Query Performance:** Improved for page pack queries (new indexes)

## Next Steps

After migration is applied successfully:

1. Run `scripts/stage2/extract_pages_from_containers.py` to populate new tables
2. Verify page_assets_t and page_pack_manifests_t are populated
3. Generate QA reports using `scripts/qa/generate_qc_report.py`

## Support

Questions or issues?
- Check migration.log for detailed error messages
- Review CLAUDE_CODE_COMPREHENSIVE_BRIEF.md for context
- Contact Michael directly for HostGator coordination
