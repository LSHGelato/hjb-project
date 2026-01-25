# Fix Database Connection in create_issue_from_parsed()

## Problem
`create_issue_from_parsed()` is calling `get_db_connection()` incorrectly. The function returns a context manager, not a raw connection object.

**Error:**
```
AttributeError: '_GeneratorContextManager' object has no attribute 'cursor'
```

## Solution

### In `scripts/stage1/ia_acquire.py`

Find the `create_issue_from_parsed()` function and fix the connection handling.

**Replace this:**
```python
def create_issue_from_parsed(...):
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor(dictionary=True)
        # ... rest of code ...
    finally:
        cursor.close()
        conn.close()
```

**With this:**
```python
def create_issue_from_parsed(...):
    # Use the context manager properly
    with get_db_connection() as conn:
        if not conn:
            return None
        
        cursor = conn.cursor(dictionary=True)
        
        try:
            # Check if issue already exists
            cursor.execute("""
                SELECT issue_id FROM issues_t 
                WHERE canonical_issue_key = %s
            """, (parsed.canonical_issue_key,))
            
            existing = cursor.fetchone()
            if existing:
                log.info(f"Issue already exists: {parsed.canonical_issue_key} (issue_id: {existing['issue_id']})")
                return existing['issue_id']
            
            # Create new issue
            issue_data = {
                'title_id': title_id,
                'family_id': family_id,
                'volume_label': parsed.volume_label,
                'volume_sort': parsed.volume_num,
                'issue_label': str(parsed.issue_num) if parsed.issue_num else None,
                'issue_sort': parsed.issue_num,
                'issue_date_start': parsed.issue_date,
                'issue_date_end': parsed.issue_date if not parsed.is_index else None,
                'year_published': parsed.year,
                'is_book_edition': 0,
                'is_special_issue': 0,
                'is_supplement': 0,
                'canonical_issue_key': parsed.canonical_issue_key
            }
            
            # Build INSERT statement
            columns = ', '.join(issue_data.keys())
            placeholders = ', '.join(['%s'] * len(issue_data))
            sql = f"INSERT INTO issues_t ({columns}) VALUES ({placeholders})"
            
            cursor.execute(sql, list(issue_data.values()))
            conn.commit()
            
            issue_id = cursor.lastrowid
            log.info(f"Created issue: {parsed.canonical_issue_key} (issue_id: {issue_id})")
            
            return issue_id
            
        except Exception as e:
            log.error(f"Failed to create issue: {e}")
            conn.rollback()
            return None
        finally:
            cursor.close()
```

## Key Changes

1. **Use `with get_db_connection() as conn:`** - This properly handles the context manager
2. **Remove manual `conn.close()`** - The context manager handles it
3. **Keep cursor management** - Still need to close the cursor in the finally block

## Testing

After fix, run:
```bash
# Re-run registration (will skip already-registered containers)
python scripts/stage1/register_existing_downloads.py --family American_Architect_family --verbose
```

Should now see:
```
[DB] Registered container: container_id=24
[DB] Created issue: ISSUE_18760513_001_0020 (issue_id: 5)
✓ Registered (container_id: 24)
```

## Verification

Check that issues were created:
```sql
SELECT COUNT(*) FROM issues_t WHERE family_id = 1;
SELECT * FROM issues_t WHERE family_id = 1 LIMIT 5;
```

## Commit Message

```
fix(hjb/acquisition): use context manager correctly in create_issue_from_parsed

- Wrap get_db_connection() with 'with' statement
- Remove manual connection close (handled by context manager)
- Fixes AttributeError when creating issues during registration
```
