-- Migration: Add is_manually_verified field to pages_t
-- Purpose: Track whether a page has been manually reviewed/verified
-- Default: 0 (unreviewed)

ALTER TABLE pages_t
ADD COLUMN is_manually_verified TINYINT(1) NOT NULL DEFAULT 0 AFTER ocr_text;

-- Add index for filtering manually verified pages
CREATE INDEX idx_is_manually_verified ON pages_t(is_manually_verified);
