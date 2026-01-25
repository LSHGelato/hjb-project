-- HJB Database Migration: Fix year_published column and populate 1876
-- Problem: YEAR(4) type has limited range; may fail on 1876
-- Solution: Change to INT or use DATE type, then populate 1876

-- Option 1: Convert year_published to INT (most flexible)
-- This allows any year from -2147483648 to 2147483647
ALTER TABLE issues_t 
MODIFY COLUMN year_published INT(11) UNSIGNED NULL
COMMENT 'Year of publication (e.g., 1876, 1877, etc.)';

-- Now populate with 1876
UPDATE issues_t SET year_published = 1876 WHERE year_published IS NULL OR year_published = 0;

-- Verify the update
SELECT year_published, COUNT(*) as count
FROM issues_t
GROUP BY year_published
ORDER BY year_published;

-- Expected output: All 53 rows should show year_published = 1876
