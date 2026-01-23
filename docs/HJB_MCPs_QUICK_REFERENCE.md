# HJB MCPs Quick Reference

## MySQL MCP — Database Queries

### Get Overall Stats
```json
{"method": "get_pipeline_stats"}
```
Returns: Total families, issues, works, containers + work type distribution.

### List All Publications
```json
{"method": "list_publication_families"}
```

### Get Specific Family
```json
{"method": "get_family_by_code", "params": {"family_code": "AMER_ARCH"}}
```

### List Issues for a Family
```json
{"method": "list_issues", "params": {"family_id": 1}}
```

### List Works (Articles, Ads, Chapters)
```json
{"method": "list_works", "params": {"family_id": 1, "work_type": "article"}}
```

### Find Occurrences of a Work
```json
{"method": "get_work_occurrences", "params": {"work_id": 42}}
```
Shows all places a work appears (different issues, sources, etc).

### Custom SQL Query
```json
{
  "method": "query",
  "params": {
    "sql": "SELECT COUNT(*) as total FROM works_t WHERE work_type = %s",
    "params": ["advertisement"]
  }
}
```

---

## NAS MCP — File Operations

### List Directory
```json
{"method": "list_directory", "params": {"path": "Working_Files/0200_STATE"}}
```

### Read Text File
```json
{"method": "read_file", "params": {"path": "Working_Files/0200_STATE/pipeline_state.json"}}
```

### Read & Parse JSON
```json
{"method": "read_json_file", "params": {"path": "Working_Files/0200_STATE/watcher_heartbeat.json"}}
```

### Get File Metadata
```json
{"method": "get_file_info", "params": {"path": "Raw_Input/0110_Internet_Archive"}}
```

### Find Files (Glob Pattern)
```json
{
  "method": "find_files",
  "params": {
    "pattern": "*.log",
    "search_path": "Working_Files/0200_STATE/logs",
    "max_results": 20
  }
}
```

### List Task Flags (Status)
```json
{"method": "list_flag_tasks", "params": {"status": "failed"}}
```

Status options: `"pending"`, `"processing"`, `"completed"`, `"failed"`, or omit for all.

### Check Watcher Heartbeat
```json
{"method": "get_watcher_heartbeat"}
```

---

## Common Diagnostic Commands

### 1. Check If Watcher Is Alive
```
NAS MCP: get_watcher_heartbeat()
→ If last_check is within 5 minutes, watcher is OK
```

### 2. See What Tasks Are Pending
```
NAS MCP: list_flag_tasks(status="pending")
→ Shows all enqueued tasks waiting to run
```

### 3. Find Failed Tasks
```
NAS MCP: list_flag_tasks(status="failed")
→ Then read the JSON files to see error details
```

### 4. Get Pipeline Health Summary
```
MySQL MCP: get_pipeline_stats()
→ Shows counts of families, issues, works
```

### 5. Check How Many Times a Work Appears
```
MySQL MCP: get_work_occurrences(work_id=<id>)
→ Shows all occurrences (different scans, editions, etc)
```

### 6. Find Recent Logs
```
NAS MCP: find_files(pattern="*.log", search_path="Working_Files/0200_STATE/logs")
→ Then read one or more logs for debugging
```

---

## Environment Variables Required

```bash
# MySQL
export HJB_MYSQL_HOST=raneywor.mysql.pythonanywhere-services.com
export HJB_MYSQL_USER=raneywor
export HJB_MYSQL_PASSWORD="<your-password>"
export HJB_MYSQL_DB=raneywor_hjbproject

# NAS
export HJB_NAS_ROOT='\\RaneyHQ\Michael\02_Projects\Historical_Journals_And_Books'
export HJB_MAX_FILE_SIZE=1048576  # 1MB
export HJB_MAX_ITEMS_IN_LIST=100
```

---

## Key Directory Paths

```
Historical_Journals_And_Books/
├── Raw_Input/              ← Downloaded files
│   ├── 0100_STATE/         ← Ingestion manifests
│   └── 0110_Internet_Archive/
├── Working_Files/          ← Processing in progress
│   ├── 0200_STATE/         ← FLAGS (tasks) and logs
│   │   ├── flags/
│   │   │   ├── pending/    ← New tasks
│   │   │   ├── processing/ ← Currently running
│   │   │   ├── completed/  ← Finished (success)
│   │   │   └── failed/     ← Finished (error)
│   │   └── logs/           ← Processing logs
│   ├── 0210_Preprocessing/
│   ├── 0220_Page_Packs/
│   ├── 0230_Segmentation/
│   └── 0240_Canonicalization/
└── Reference_Library/      ← Final curated outputs
```

---

## Tips

- **For large files:** Use `MAX_FILE_SIZE` limit to avoid loading huge images.
- **For huge directories:** Use `find_files()` with specific patterns instead of `list_directory()`.
- **For database debugging:** Use `query()` method for custom SQL if built-in methods don't fit.
- **For watcher issues:** Check heartbeat first, then inspect failed flag files.
- **For work deduplication:** Use `get_work_occurrences()` to see if a work was merged correctly.

---

## Support

Refer to `HJB_MCPs_INTEGRATION_GUIDE.md` for full documentation.
