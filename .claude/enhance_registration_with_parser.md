# Enhance Registration with IA Identifier Parser

## Goal
Integrate the existing `parse_american_architect_ia.py` parser into the registration system to extract richer metadata from IA identifiers.

## Current State
- Parser exists: `scripts/parsers/parse_american_architect_ia.py`
- Registration script: `scripts/stage1/register_existing_downloads.py`
- Registration currently creates containers with minimal metadata

## Required Changes

### 1. Modify `scripts/stage1/ia_acquire.py`

#### Import the parser at the top
```python
from scripts.parsers.parse_american_architect_ia import (
    parse_american_architect_identifier,
    ParsedIAIdentifier
)
```

#### Update `reconstruct_metadata_from_local()` function

Add parser integration to extract volume, dates, and issue information:

```python
def reconstruct_metadata_from_local(
    identifier: str, 
    download_dir: Path,
    source_system: str = 'ia'
) -> dict:
    """
    Reconstruct metadata from local files AND parse identifier.
    """
    # Existing logic to load _meta.json
    # ...
    
    # NEW: Parse the identifier
    parsed = parse_american_architect_identifier(identifier)
    
    # Build enhanced metadata dict
    metadata = {
        # ... existing fields ...
        
        # ADD THESE FROM PARSER:
        'volume_label': parsed.volume_label if parsed else None,
        'date_start': parsed.issue_date if parsed and parsed.issue_date else None,
        'date_end': parsed.issue_date if parsed and parsed.issue_date else None,
        # For indexes, date_end stays None (as requested)
        
        # Include parsed object for downstream use
        '_parsed_identifier': parsed
    }
    
    return metadata
```

#### Update `register_container_in_db()` function

Use the enhanced metadata to populate `containers_t` fields:

```python
def register_container_in_db(...):
    # ... existing code ...
    
    # Extract parsed data
    parsed = metadata.get('_parsed_identifier')
    
    # When inserting into containers_t, add:
    container_data = {
        # ... existing fields ...
        'volume_label': metadata.get('volume_label'),
        'date_start': metadata.get('date_start'),
        'date_end': metadata.get('date_end'),
        # total_pages is already handled from scandata.xml
    }
```

### 2. Get `total_pages` from scandata.xml

The `total_pages` should come from parsing `{identifier}_scandata.xml`.

**In `reconstruct_metadata_from_local()`**, add this logic:

```python
# Parse scandata.xml for page count
scandata_path = download_dir / f"{identifier}_scandata.xml"
total_pages = None

if scandata_path.exists():
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(scandata_path)
        root = tree.getroot()
        
        # scandata.xml has <pageData> elements, one per page
        # OR a <pageCount> element (depending on IA format)
        pages = root.findall('.//pageData')
        if pages:
            total_pages = len(pages)
        else:
            # Try alternate format
            page_count_elem = root.find('.//pageCount')
            if page_count_elem is not None:
                total_pages = int(page_count_elem.text)
    except Exception as e:
        log.warning(f"Could not parse scandata.xml for {identifier}: {e}")
```

Add `total_pages` to the returned metadata dict.

### 3. Handle Issues Table Population

**NEW FUNCTION** in `ia_acquire.py`:

```python
def create_issue_from_parsed(
    parsed: ParsedIAIdentifier,
    family_id: int,
    title_id: Optional[int] = None,
    container_id: Optional[int] = None
) -> Optional[int]:
    """
    Create an issue record in issues_t from parsed identifier data.
    
    Returns:
        issue_id if created/found, None on error
    """
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Build canonical_issue_key
        canonical_key = parsed.canonical_issue_key
        
        # Check if issue already exists
        cursor.execute("""
            SELECT issue_id FROM issues_t 
            WHERE canonical_issue_key = %s
        """, (canonical_key,))
        
        existing = cursor.fetchone()
        if existing:
            log.info(f"Issue already exists: {canonical_key} (issue_id: {existing['issue_id']})")
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
            'is_book_edition': False,
            'is_special_issue': False,
            'is_supplement': False,
            'canonical_issue_key': canonical_key
        }
        
        # Insert
        columns = ', '.join(issue_data.keys())
        placeholders = ', '.join(['%s'] * len(issue_data))
        sql = f"INSERT INTO issues_t ({columns}) VALUES ({placeholders})"
        
        cursor.execute(sql, list(issue_data.values()))
        conn.commit()
        
        issue_id = cursor.lastrowid
        log.info(f"Created issue: {canonical_key} (issue_id: {issue_id})")
        
        return issue_id
        
    except Exception as e:
        log.error(f"Failed to create issue: {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()
        conn.close()
```

#### Update `register_container_in_db()` to call this

After creating the container, create/link the issue:

```python
def register_container_in_db(...):
    # ... existing container creation ...
    
    container_id = cursor.lastrowid
    
    # NEW: Create issue if we have parsed data
    parsed = metadata.get('_parsed_identifier')
    if parsed:
        issue_id = create_issue_from_parsed(
            parsed=parsed,
            family_id=family_id,
            title_id=title_id,
            container_id=container_id
        )
        
        # Create issue_containers_t mapping
        if issue_id:
            cursor.execute("""
                INSERT INTO issue_containers_t 
                (issue_id, container_id, is_preferred, is_complete)
                VALUES (%s, %s, 1, 1)
            """, (issue_id, container_id))
    
    # ... rest of existing code ...
```

### 4. Update `scripts/stage1/register_existing_downloads.py`

No changes needed - it will automatically use the enhanced `reconstruct_metadata_from_local()`.

### 5. Error Handling

Add safeguards:

1. **If parser fails** (returns None), log warning but continue with basic metadata
2. **If scandata.xml missing**, log warning and set `total_pages = None`
3. **If issue creation fails**, log error but don't fail the entire container registration

### 6. Testing

After implementation, test with:

```bash
# Dry run to verify parsing works
python scripts/stage1/register_existing_downloads.py --family American_Architect_family --dry-run --verbose

# Check one item manually
python -c "
from scripts.parsers.parse_american_architect_ia import parse_american_architect_identifier
result = parse_american_architect_identifier('sim_american-architect-and-architecture_1890-01-01_27_1')
print(f'Volume: {result.volume_label}')
print(f'Date: {result.issue_date}')
print(f'Canonical: {result.canonical_issue_key}')
"

# Run actual registration
python scripts/stage1/register_existing_downloads.py --family American_Architect_family
```

### 7. Database Verification

After running, verify:

```sql
-- Check containers have volume and dates
SELECT container_id, source_identifier, volume_label, date_start, date_end, total_pages
FROM containers_t
WHERE source_system = 'ia' AND family_id = 1
LIMIT 10;

-- Check issues were created
SELECT i.issue_id, i.canonical_issue_key, i.volume_label, i.issue_date_start, i.year_published
FROM issues_t i
WHERE i.family_id = 1
LIMIT 10;

-- Check issue-container mappings
SELECT ic.issue_id, ic.container_id, c.source_identifier
FROM issue_containers_t ic
JOIN containers_t c ON ic.container_id = c.container_id
WHERE c.family_id = 1
LIMIT 10;
```

## Summary of Changes

**Files to modify:**
1. `scripts/stage1/ia_acquire.py`
   - Import parser
   - Enhance `reconstruct_metadata_from_local()` with parser integration
   - Update `register_container_in_db()` to use parsed metadata
   - Add new `create_issue_from_parsed()` function

**No changes needed:**
- `scripts/stage1/register_existing_downloads.py` (will use enhanced functions automatically)
- `scripts/parsers/parse_american_architect_ia.py` (already complete)

## Expected Outcome

After implementation, containers will have:
- ✓ `volume_label` extracted from identifier
- ✓ `date_start` and `date_end` from issue date (or NULL for indexes)
- ✓ `total_pages` from scandata.xml
- ✓ Linked `issues_t` record with proper canonical key
- ✓ `issue_containers_t` mapping created

## Commit Message

```
feat(hjb/acquisition): integrate IA identifier parser with registration

- Import parse_american_architect_ia parser
- Enhance reconstruct_metadata_from_local() to extract volume, dates
- Parse scandata.xml for accurate page counts
- Add create_issue_from_parsed() to populate issues_t
- Create issue_containers_t mappings automatically
- Containers now have complete metadata from identifier parsing
```
