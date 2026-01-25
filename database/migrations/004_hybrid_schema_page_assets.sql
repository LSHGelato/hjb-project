-- =============================================================================
-- HJB Database Migration 004 - Hybrid Schema: Page Assets & Pack Manifests
-- =============================================================================
--
-- Purpose: Add support for hybrid database + filesystem architecture
--   - page_assets_t: Track extracted images and OCR file references
--   - page_pack_manifests_t: Document page pack contents and extraction metadata
--   - Extend pages_t with snippet, spread tracking, and character count
--   - Extend work_occurrences_t with image references and extraction params
--
-- Timeline: Stage 2 OCR + Images (Phase 2a/2b)
-- Author: Claude Code
-- Date: 2026-01-25
--
-- Safety:
--   - All new tables use FOREIGN KEY ON DELETE CASCADE for data integrity
--   - Migration is idempotent (can run multiple times safely)
--   - Rollback: Run DOWN section at bottom
-- =============================================================================

-- Check schema version (optional, for documentation)
-- Current tables expected: publication_families_t, publication_titles_t,
--                        issues_t, containers_t, pages_t, work_occurrences_t

-- =============================================================================
-- PART 1: Create page_assets_t (references to extracted images and OCR files)
-- =============================================================================

CREATE TABLE IF NOT EXISTS page_assets_t (
  asset_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  page_id INT UNSIGNED NOT NULL UNIQUE,
  FOREIGN KEY (page_id) REFERENCES pages_t(page_id) ON DELETE CASCADE,

  -- OCR payload references (file paths and metadata)
  ocr_payload_path VARCHAR(512),
  ocr_payload_hash CHAR(64) COMMENT 'SHA256 of OCR file',
  ocr_payload_format ENUM('djvu_xml', 'hocr', 'alto', 'tesseract_json')
    COMMENT 'Original OCR format from Internet Archive',

  -- Extracted image references (filesystem location and metadata)
  image_extracted_path VARCHAR(512) COMMENT 'Path to extracted JPEG in page pack',
  image_extracted_format VARCHAR(32) COMMENT 'e.g., JPEG, PNG',
  image_extracted_hash CHAR(64) COMMENT 'SHA256 of extracted image',
  image_source VARCHAR(64) COMMENT 'e.g., ia_jp2, ia_pdf, etc.',

  -- Image processing metadata
  image_dpi_normalized INT COMMENT 'DPI after normalization (e.g., 300)',
  image_rotation_applied INT COMMENT 'Degrees rotated (0, 90, 180, 270)',
  was_deskewed TINYINT(1) DEFAULT 0 COMMENT 'Boolean: deskew preprocessing applied',
  was_binarized TINYINT(1) DEFAULT 0 COMMENT 'Boolean: binarization preprocessing applied',

  -- Audit trail
  extracted_at DATETIME NOT NULL COMMENT 'When extraction completed',
  extraction_script_version VARCHAR(64) COMMENT 'e.g., extract_pages_v2.1',

  -- Timestamps
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  -- Indexes for common queries
  INDEX idx_page_id (page_id),
  INDEX idx_ocr_payload_hash (ocr_payload_hash),
  INDEX idx_image_extracted_hash (image_extracted_hash),
  INDEX idx_extracted_at (extracted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Tracks extracted images and OCR file references for each page';

-- =============================================================================
-- PART 2: Create page_pack_manifests_t (documents page pack contents)
-- =============================================================================

CREATE TABLE IF NOT EXISTS page_pack_manifests_t (
  manifest_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  container_id INT UNSIGNED NOT NULL,
  FOREIGN KEY (container_id) REFERENCES containers_t(container_id) ON DELETE CASCADE,

  -- Manifest file reference
  manifest_path VARCHAR(512) NOT NULL COMMENT 'Path to manifest.json in page pack',
  manifest_hash CHAR(64) COMMENT 'SHA256 of manifest JSON file',
  manifest_version VARCHAR(32) COMMENT 'Format version, e.g., 1.0, 2.1',

  -- Content summary
  total_pages INT COMMENT 'Number of pages in this manifest',
  page_ids_included JSON COMMENT 'Array of page_id integers included',
  ocr_sources_used JSON COMMENT 'Array of OCR formats used: ["djvu_xml", "hocr", ...]',
  image_extraction_params JSON COMMENT 'Extraction settings: quality, dpi, preprocessing flags',

  -- Audit and provenance
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_by VARCHAR(128) COMMENT 'User or script that created manifest',
  description VARCHAR(255) COMMENT 'Human-readable summary of manifest',

  -- Versioning
  is_active TINYINT(1) DEFAULT 1 COMMENT 'Is this the current manifest?',
  superseded_by INT UNSIGNED COMMENT 'If inactive, which manifest replaced it',
  FOREIGN KEY (superseded_by) REFERENCES page_pack_manifests_t(manifest_id),

  -- Indexes
  INDEX idx_container_id (container_id),
  INDEX idx_manifest_hash (manifest_hash),
  INDEX idx_created_at (created_at),
  UNIQUE KEY uk_manifest_path (manifest_path)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Manifests document page pack contents and extraction metadata';

-- =============================================================================
-- PART 3: Extend pages_t with new columns
-- =============================================================================

-- Add ocr_text_snippet (first 500 chars of OCR for quick preview in UI)
ALTER TABLE pages_t
ADD COLUMN IF NOT EXISTS ocr_text_snippet VARCHAR(500)
AFTER ocr_text
COMMENT 'First 500 characters of OCR text for UI preview';

-- Add ocr_char_count (total character count in OCR)
ALTER TABLE pages_t
ADD COLUMN IF NOT EXISTS ocr_char_count INT
AFTER ocr_text_snippet
COMMENT 'Total character count in full OCR text';

-- Add is_spread and is_spread_with (tracking 2-page spreads)
ALTER TABLE pages_t
ADD COLUMN IF NOT EXISTS is_spread TINYINT(1) DEFAULT 0
AFTER ocr_char_count
COMMENT 'Is this page part of a 2-page spread?';

ALTER TABLE pages_t
ADD COLUMN IF NOT EXISTS is_spread_with INT UNSIGNED
AFTER is_spread
COMMENT 'Foreign key: page_id of the other page in spread';

-- Add foreign key constraint for is_spread_with (only if columns exist)
ALTER TABLE pages_t
ADD CONSTRAINT IF NOT EXISTS fk_is_spread_with
FOREIGN KEY (is_spread_with) REFERENCES pages_t(page_id) ON DELETE SET NULL;

-- =============================================================================
-- PART 4: Extend work_occurrences_t with image references and params
-- =============================================================================

-- Modify image_references to be explicitly JSON type (if exists)
-- Note: This may already be JSON; this ensures proper type
ALTER TABLE work_occurrences_t
MODIFY COLUMN image_references JSON
COMMENT 'Array of image file paths: ["/path/to/page_001.jpg", ...]';

-- Add image_extraction_params JSON
ALTER TABLE work_occurrences_t
ADD COLUMN IF NOT EXISTS image_extraction_params JSON
AFTER image_references
COMMENT 'Parameters used for image extraction: quality, dpi, preprocessing';

-- =============================================================================
-- PART 5: Create indexes for performance
-- =============================================================================

-- Page assets queries
ALTER TABLE page_assets_t
ADD INDEX IF NOT EXISTS idx_extraction_script (extraction_script_version);

-- Page pack queries
ALTER TABLE page_pack_manifests_t
ADD INDEX IF NOT EXISTS idx_is_active (is_active);

-- Pages query by spread status
ALTER TABLE pages_t
ADD INDEX IF NOT EXISTS idx_is_spread (is_spread);

-- =============================================================================
-- PART 6: Documentation and versioning
-- =============================================================================

-- Create a migration history table if it doesn't exist (optional, for tracking)
CREATE TABLE IF NOT EXISTS database_migrations (
  migration_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  migration_name VARCHAR(128) NOT NULL UNIQUE,
  applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  applied_by VARCHAR(128),
  status ENUM('success', 'partial', 'failed', 'rolled_back') DEFAULT 'success',
  notes TEXT,
  INDEX idx_applied_at (applied_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Record this migration
INSERT INTO database_migrations (migration_name, applied_by, notes)
VALUES ('004_hybrid_schema_page_assets', 'claude_code',
  'Added page_assets_t, page_pack_manifests_t; extended pages_t and work_occurrences_t')
ON DUPLICATE KEY UPDATE applied_at = CURRENT_TIMESTAMP;

-- =============================================================================
-- VERIFICATION QUERIES (run these after migration to confirm success)
-- =============================================================================

/*
-- Check that all new tables exist:
SHOW TABLES LIKE 'page_%';

-- Expected output: page_assets_t, page_pack_manifests_t, pages_t (modified)

-- Describe new tables:
DESCRIBE page_assets_t;
DESCRIBE page_pack_manifests_t;

-- Check new columns on pages_t:
SELECT COLUMN_NAME, COLUMN_TYPE, COLUMN_KEY, COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME='pages_t'
AND COLUMN_NAME IN ('ocr_text_snippet', 'ocr_char_count', 'is_spread', 'is_spread_with')
ORDER BY ORDINAL_POSITION;

-- Check new columns on work_occurrences_t:
SELECT COLUMN_NAME, COLUMN_TYPE, COLUMN_KEY
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME='work_occurrences_t'
AND COLUMN_NAME IN ('image_references', 'image_extraction_params')
ORDER BY ORDINAL_POSITION;

-- Verify foreign keys:
SELECT CONSTRAINT_NAME, TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE TABLE_NAME IN ('page_assets_t', 'page_pack_manifests_t')
AND REFERENCED_TABLE_NAME IS NOT NULL;
*/

-- =============================================================================
-- DOWN - ROLLBACK SCRIPT (uncomment to undo this migration)
-- =============================================================================

/*
-- WARNING: This will DELETE all data in new tables and remove new columns!
-- Only run if migration failed or needs to be undone.

-- 1. Drop new tables (CASCADE deletes dependent rows)
DROP TABLE IF EXISTS page_pack_manifests_t;
DROP TABLE IF EXISTS page_assets_t;

-- 2. Remove new columns from pages_t
ALTER TABLE pages_t
DROP COLUMN IF EXISTS is_spread_with,
DROP COLUMN IF EXISTS is_spread,
DROP COLUMN IF EXISTS ocr_char_count,
DROP COLUMN IF EXISTS ocr_text_snippet,
DROP CONSTRAINT IF EXISTS fk_is_spread_with;

-- 3. Remove new columns from work_occurrences_t
ALTER TABLE work_occurrences_t
DROP COLUMN IF EXISTS image_extraction_params;

-- 4. Record rollback in migration history
UPDATE database_migrations
SET status = 'rolled_back', applied_at = CURRENT_TIMESTAMP
WHERE migration_name = '004_hybrid_schema_page_assets';
*/
