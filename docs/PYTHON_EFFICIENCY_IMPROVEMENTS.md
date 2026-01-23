# Python Code Efficiency Improvements

This document summarizes potential efficiency improvements identified across all Python scripts in the HJB project.

---

## Executive Summary

| File | Issues | Severity | Primary Concerns |
|------|--------|----------|------------------|
| `scripts/common/hjb_db.py` | 6 | **HIGH** | Config caching, SQL injection risk, connection pooling |
| `scripts/doctor/hjb_doctor.py` | 4 | LOW | JSON import repetition, path validation |
| `scripts/stage1/generate_ia_tasks.py` | 5 | MEDIUM | Identifier filtering algorithm, timestamp generation |
| `scripts/stage1/ia_acquire.py` | 9 | **HIGH** | File selection algorithm, database round-trips, retry backoff |
| `scripts/stage1/parse_american_architect_ia.py` | 6 | MEDIUM | Regex compilation, roman numeral caching |
| `scripts/watcher/hjb_watcher.py` | 12 | **HIGH** | I/O frequency, sorting full lists, CSV performance |
| `mcps/hjb_mysql_mcp.py` | 10 | **HIGH** | No connection pooling, no streaming, sync operations |
| `mcps/hjb_nas_mcp.py` | 10 | **HIGH** | Double stat calls, full file reads, no lazy evaluation |

**Total Issues Identified: 62**

---

## 1. scripts/common/hjb_db.py

### Issue 1.1: Config loaded on every connection (Lines 43-65)
**Problem:** `load_config()` is called every time `get_db_config()` is invoked, re-parsing YAML on each database connection.

**Current:**
```python
def get_db_config():
    config = load_config()  # Re-parses YAML every time
    return config.get("database", {})
```

**Recommended:**
```python
from functools import lru_cache

@lru_cache(maxsize=1)
def load_config():
    # ... existing logic
```

### Issue 1.2: No connection pooling (Lines 155-181)
**Problem:** `execute_query()` creates a new connection for every single query.

**Recommended:** Use `mysql.connector.pooling.MySQLConnectionPool` or context manager for connection reuse.

### Issue 1.3: SQL injection risk (Lines 494-496)
**Problem:** Stage parameter interpolated directly into SQL string.

**Recommended:** Use parameterized queries or a mapping dictionary for stage names.

### Issue 1.4: Inefficient migration SQL parsing (Lines 222-225)
**Problem:** Simple string split on semicolons doesn't handle comments or string literals.

**Recommended:** Use proper SQL parser or MySQL batch mode execution.

---

## 2. scripts/doctor/hjb_doctor.py

### Issue 2.1: Repeated JSON imports (Lines 217, 229, 262, 270)
**Problem:** `import json` called 4 times conditionally within exception blocks.

**Recommended:** Import once at module level.

### Issue 2.2: Inefficient directory validation (Lines 145-146)
**Problem:** Calls `exists()` and `is_dir()` separately (2 stat calls per directory).

**Recommended:** Use single `stat()` call and check mode.

---

## 3. scripts/stage1/generate_ia_tasks.py

### Issue 3.1: Inefficient identifier filtering (Lines 53-71)
**Problem:** Uses `any(x in ident.lower() for x in [...])` - calls `.lower()` on every identifier and performs multiple substring searches.

**Current:**
```python
def filter_identifiers(identifiers):
    return [ident for ident in identifiers
            if not any(x in ident.lower() for x in ['_chocr', '_hocr', '_abbyy'])]
```

**Recommended:**
```python
import re
_FILTER_PATTERN = re.compile(r'_(?:chocr|hocr|abbyy)', re.IGNORECASE)

def filter_identifiers(identifiers):
    return [ident for ident in identifiers if not _FILTER_PATTERN.search(ident)]
```

### Issue 3.2: Redundant timestamp processing (Line 83)
**Problem:** `utc_now_iso()` result is string-processed with multiple `.replace()` calls.

**Recommended:** Generate timestamp without colons/dashes directly using `strftime()`.

---

## 4. scripts/stage1/ia_acquire.py

### Issue 4.1: Inefficient file selection - O(n²) complexity (Lines 203-213)
**Problem:** `choose_files_for_item()` uses `next()` with linear search for each suffix.

**Current:**
```python
for suffix in suffixes:
    match = next((f for f in files if f.endswith(suffix)), None)
```

**Recommended:**
```python
# Build suffix map once: O(n)
file_by_suffix = {}
for f in files:
    for suffix in suffixes:
        if f.endswith(suffix):
            file_by_suffix.setdefault(suffix, f)
            break
```

### Issue 4.2: Triple iteration over file list (Lines 473-475)
**Problem:**
```python
available_files = list(item.files)
names = [f.get("name") for f in available_files if isinstance(f, dict) and "name" in f]
names = [n for n in names if isinstance(n, str)]
```

**Recommended:** Combine into single comprehension:
```python
names = [f["name"] for f in item.files
         if isinstance(f, dict) and isinstance(f.get("name"), str)]
```

### Issue 4.3: Linear retry backoff (Line 578)
**Problem:** `time.sleep(retry_sleep * attempt)` - linear backoff (1.5s, 3s, 4.5s).

**Recommended:** Exponential backoff: `time.sleep(retry_sleep * (2 ** (attempt - 1)))`

### Issue 4.4: Duplicated identifier prefix stripping logic (Lines 226-228, 240-249, 537-541)
**Problem:** Same string manipulation code repeated 3 times.

**Recommended:** Extract into utility function.

### Issue 4.5: Multiple database round-trips per item (Lines 495-507)
**Problem:** 5+ sequential database operations per item.

**Recommended:** Consider stored procedures or batch operations.

---

## 5. scripts/stage1/parse_american_architect_ia.py

### Issue 5.1: Roman numeral dictionary created on every call (Lines 89-106)
**Problem:** `val` dictionary is created inside function on every invocation.

**Recommended:** Move to module-level constant:
```python
_ROMAN_VALUES = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
```

### Issue 5.2: Regex patterns not pre-compiled (Lines 152-157)
**Problem:** Three regex patterns tried sequentially without pre-compilation.

**Recommended:**
```python
# Module level
_PATTERN_VARIANTS = [
    re.compile(r'pattern1'),
    re.compile(r'pattern2'),
    re.compile(r'pattern3'),
]
```

### Issue 5.3: Mutable default in dataclass (Line 53)
**Problem:** `warnings: list[str] = None` with post-init handling.

**Recommended:** Use `field(default_factory=list)` from dataclasses.

---

## 6. scripts/watcher/hjb_watcher.py

### Issue 6.1: Unnecessary full sort (Line 794)
**Problem:** `sorted([p for p in pending.glob("*.json") if p.is_file()])` sorts entire list but may only need first element.

**Recommended:** If only taking one: use `min()` or `next()`. If taking multiple: consider if sort is necessary.

### Issue 6.2: Inefficient glob pattern (Lines 297-309)
**Problem:**
```python
for task_file in processing.glob("*"):
    if task_file.is_file() and "orionmx_" in task_file.name:
```

**Recommended:**
```python
for task_file in processing.glob("orionmx_*"):
```

### Issue 6.3: Heartbeat written every cycle (Lines 766-784)
**Problem:** Heartbeat JSON written synchronously to NAS on every task cycle.

**Recommended:** Write less frequently (every N cycles) or use async I/O.

### Issue 6.4: CSV inventory with per-file stat calls (Lines 571-648)
**Problem:** `os.walk()` combined with file-by-file stat calls.

**Recommended:** Use `os.scandir()` which returns stat info with directory entry.

### Issue 6.5: Linear retry backoff in write_json (Lines 850-864)
**Problem:** Retry delays are linear (0.15s, 0.30s, 0.45s...).

**Recommended:** Exponential backoff.

---

## 7. mcps/hjb_mysql_mcp.py

### Issue 7.1: No connection pooling (Lines 36-49)
**Problem:** Single connection maintained for entire session lifetime.

**Recommended:**
```python
from mysql.connector.pooling import MySQLConnectionPool

pool = MySQLConnectionPool(pool_name="hjb_pool", pool_size=5, **config)
```

### Issue 7.2: Full result set in memory (Lines 59, 173)
**Problem:** `cursor.fetchall()` loads entire result set.

**Recommended:** Use `fetchmany(size)` for pagination or streaming.

### Issue 7.3: Multiple queries for stats (Lines 160-177)
**Problem:** 5+ separate queries to build stats.

**Recommended:** Single query with UNION or create a database view.

### Issue 7.4: SELECT * everywhere (Lines 100, 109, 125, 135, 150)
**Problem:** Returns all columns even when not needed.

**Recommended:** Specify only required columns.

### Issue 7.5: Synchronous operations block event loop (Lines 51-96)
**Problem:** All database operations are synchronous.

**Recommended:** Use async MySQL library (e.g., `aiomysql`).

### Issue 7.6: Cursor reused across requests (Lines 55-57)
**Problem:** Single cursor for all requests - not thread-safe.

**Recommended:** Create cursor per request or implement locking.

---

## 8. mcps/hjb_nas_mcp.py

### Issue 8.1: Double stat calls per entry (Lines 85-89)
**Problem:**
```python
if entry.is_file():           # First stat
    item["size"] = entry.stat().st_size  # Second stat
```

**Recommended:**
```python
stat_result = entry.stat()
if stat.S_ISREG(stat_result.st_mode):
    item["size"] = stat_result.st_size
item["modified"] = stat_result.st_mtime
```

### Issue 8.2: Full file read into memory (Lines 155-156)
**Problem:** `f.read()` loads entire file regardless of size.

**Recommended:** Read in chunks with early termination on size violation.

### Issue 8.3: No lazy evaluation for glob (Lines 261-271)
**Problem:** `glob()` collects all results in memory.

**Recommended:** Return generator or paginate results with cursor.

### Issue 8.4: List created just to get count (Line 230)
**Problem:** `len(list(target_path.iterdir()))` creates full list for count.

**Recommended:**
```python
sum(1 for _ in target_path.iterdir())
```

### Issue 8.5: No timeout on glob searches (Line 261)
**Problem:** Glob can run indefinitely on large trees.

**Recommended:** Add timeout parameter or result limit.

---

## Top Priority Recommendations

### 1. Configuration & Caching
- Add `@lru_cache` to `load_config()` in `hjb_db.py`
- Pre-compile all regex patterns at module level
- Cache roman numeral lookup table as module constant

### 2. Database Optimization
- Implement connection pooling in both `hjb_db.py` and `hjb_mysql_mcp.py`
- Batch database operations where possible
- Use parameterized queries to prevent SQL injection and enable query plan caching

### 3. Memory Management
- Implement streaming/pagination for large result sets
- Use generators instead of list comprehensions for large datasets
- Read files in chunks instead of all at once

### 4. Algorithm Improvements
- Fix O(n²) patterns in file selection (use sets/dicts for lookups)
- Use compiled regex patterns
- Avoid unnecessary sorts when only first element needed

### 5. I/O Optimization
- Reduce NAS write frequency (heartbeats, locks)
- Use exponential backoff for retries
- Use `os.scandir()` instead of `os.walk()` + stat

### 6. Concurrency
- Consider async/await for I/O-bound MCP operations
- Ensure thread safety for shared resources (cursors, connections)

---

## Implementation Priority

1. **Immediate** (security/correctness): SQL injection fix in `hjb_db.py`
2. **High** (significant performance): Connection pooling, O(n²) algorithm fixes
3. **Medium** (moderate improvement): Caching, regex compilation, retry backoff
4. **Low** (minor optimization): Import cleanup, string operations

---

*Generated: 2026-01-23*
