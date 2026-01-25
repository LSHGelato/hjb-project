# Fix canonical_issue_key to Include Family Identifier

## Problem
Current `canonical_issue_key` doesn't include publication/family identifier, causing potential collisions when two different publications have:
- Same publication date
- Same volume number  
- Same issue number

Example collision:
- "American Architect" Issue 1, Vol 1, Jan 1 1876 → `ISSUE_18760101_001_0001`
- "Building Age" Issue 1, Vol 1, Jan 1 1876 → `ISSUE_18760101_001_0001` ❌ DUPLICATE!

## Solution

### 1. Modify `scripts/parsers/parse_american_architect_ia.py`

Update the `canonical_issue_key` property to accept and include a family identifier:

**Change from property to method:**

```python
# REMOVE the @property decorator from canonical_issue_key

# REPLACE with this method:
def canonical_issue_key(self, family_code: str = None) -> str:
    """
    Generate canonical issue key for deduplication.
    
    Args:
        family_code: Short family code (e.g., 'AMER_ARCH', 'BLDG_AGE')
                     If None, uses publication name from identifier
    
    Returns:
        Unique key format: {FAMILY}_{TYPE}_{date/year}_{volume}_{issue}
    """
    # Use family_code if provided, otherwise derive from publication
    family_prefix = family_code or self.publication_short.upper()
    
    if self.is_index:
        # INDEX format: {FAMILY}_INDEX_{year}_{volume}
        return f"{family_prefix}_INDEX_{self.year}_{self.volume_num:03d}"
    else:
        # ISSUE format: {FAMILY}_ISSUE_{date}_{volume}_{issue}
        date_str = self.issue_date.strftime("%Y%m%d")
        return f"{family_prefix}_ISSUE_{date_str}_{self.volume_num:03d}_{self.issue_num:04d}"
```

### 2. Update `scripts/stage1/ia_acquire.py`

Modify `create_issue_from_parsed()` to pass family_code:

**Add family_code lookup:**

```python
def create_issue_from_parsed(
    parsed: ParsedIAIdentifier,
    family_id: int,
    title_id: Optional[int] = None,
    container_id: Optional[int] = None
) -> Optional[int]:
    """
    Create an issue record in issues_t from parsed identifier data.
    """
    # Get family_code for canonical key
    family_code = None
    with get_db_connection() as conn:
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT family_code FROM publication_families_t WHERE family_id = %s",
                (family_id,)
            )
            result = cursor.fetchone()
            if result:
                family_code = result['family_code']
            cursor.close()
    
    # Generate canonical key with family code
    canonical_key = parsed.canonical_issue_key(family_code)
    
    # ... rest of function unchanged, use canonical_key as before ...
```

### 3. Update test cases in parser

Update the `__main__` section test output:

```python
if __name__ == "__main__":
    # ... existing test code ...
    
    for parsed in results:
        print(f"Identifier: {parsed.raw_identifier}")
        print(f"  Type: {'Index' if parsed.is_index else 'Issue'}")
        print(f"  Year: {parsed.year}")
        print(f"  Volume: {parsed.volume_label} (num: {parsed.volume_num})")
        if parsed.issue_date:
            print(f"  Date: {parsed.issue_date.strftime('%Y-%m-%d')}")
        if parsed.issue_num:
            print(f"  Issue Num: {parsed.issue_num}")
        if parsed.half_year_range:
            print(f"  Half-Year: {parsed.half_year_range}")
        
        # Show both with and without family code
        print(f"  Canonical Key (no family): {parsed.canonical_issue_key()}")
        print(f"  Canonical Key (AMER_ARCH): {parsed.canonical_issue_key('AMER_ARCH')}")
        
        if parsed.warnings:
            print(f"  ⚠️  Warnings: {', '.join(parsed.warnings)}")
        print()
```

### 4. Update backfill script

Modify `scripts/stage1/backfill_issues.py` to ensure family_code is used:

No changes needed - it calls `create_issue_from_parsed()` which now handles the family lookup internally.

## Expected Results

**Before fix:**
```
American Architect Jan 1 1876: ISSUE_18760101_001_0001
Building Age Jan 1 1876:       ISSUE_18760101_001_0001  ❌ COLLISION
```

**After fix:**
```
American Architect Jan 1 1876: AMER_ARCH_ISSUE_18760101_001_0001
Building Age Jan 1 1876:       BLDG_AGE_ISSUE_18760101_001_0001   ✅ UNIQUE
```

## Database Impact

This will change the format of `canonical_issue_key` values. Since you have **no issues in issues_t yet**, this is the perfect time to make this change!

If you had existing issues, you'd need a migration to regenerate the keys.

## Testing

After changes:

```bash
# Test the parser
python scripts/parsers/parse_american_architect_ia.py

# Should show keys with family prefix
```

Then run your backfill:
```bash
python scripts/stage1/backfill_issues.py --family-id 1 --dry-run --verbose
```

Check the logs for canonical keys - should now have `AMER_ARCH_` prefix.

## Commit Message

```
fix(hjb/parsers): add family identifier to canonical_issue_key

- Change canonical_issue_key from property to method accepting family_code
- Update create_issue_from_parsed() to lookup and pass family_code  
- Prevents key collisions between different publications with same date/vol/issue
- Critical fix before any issues_t records created
```

## Database Verification After Fix

After running backfill with this fix:

```sql
-- All keys should have family prefix
SELECT canonical_issue_key FROM issues_t LIMIT 10;

-- Example results:
-- AMER_ARCH_ISSUE_18760101_001_0001
-- AMER_ARCH_ISSUE_18760108_001_0002
-- AMER_ARCH_INDEX_1876_001
```
