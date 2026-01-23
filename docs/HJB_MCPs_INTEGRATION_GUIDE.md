# HJB MCPs Integration Guide

This document explains how to set up and use the two new MCPs for the Historical Journals & Books project.

## Overview

Two MCPs have been created:

1. **hjb_mysql_mcp.py** — Database query/management interface
2. **hjb_nas_mcp.py** — NAS file browsing interface

These allow Claude to directly query the database, inspect flag files, monitor the watcher, and browse the NAS without manual file transfers.

---

## Setup Instructions

### Prerequisites

- Python 3.8+
- `mysql-connector-python` package (for MySQL MCP)
- Access to the MySQL database on HostGator
- Access to the NAS share

### Installation

#### 1. Install MySQL MCP Dependencies

```bash
pip install mysql-connector-python
```

#### 2. Deploy MCPs to Your System

Copy both `.py` files to a known location:

```bash
# Example: Copy to a project scripts directory
cp hjb_mysql_mcp.py /path/to/hjb-project/mcps/
cp hjb_nas_mcp.py /path/to/hjb-project/mcps/
chmod +x /path/to/hjb-project/mcps/*.py
```

#### 3. Set Environment Variables

**On your local machine (or in Claude's configuration):**

```bash
# MySQL Configuration
export HJB_MYSQL_HOST=raneywor.mysql.pythonanywhere-services.com
export HJB_MYSQL_USER=raneywor
export HJB_MYSQL_PASSWORD="<your-password>"  # Store securely, never in code!
export HJB_MYSQL_DB=raneywor_hjbproject

# NAS Configuration
export HJB_NAS_ROOT='\\RaneyHQ\Michael\02_Projects\Historical_Journals_And_Books'
export HJB_MAX_FILE_SIZE=1048576  # 1MB default, adjust as needed
export HJB_MAX_ITEMS_IN_LIST=100
```

**For Windows Task Scheduler or permanent setup:**
- Set these in System Properties → Environment Variables
- Or use `.env` file with a loader

#### 4. Configure Claude's MCP Client

In your Claude chat settings or configuration file, add the MCPs:

**Example configuration (if using Claude desktop client or similar):**

```json
{
  "mcps": [
    {
      "name": "hjb_mysql",
      "type": "stdio",
      "command": "python",
      "args": ["/path/to/hjb_mysql_mcp.py"]
    },
    {
      "name": "hjb_nas",
      "type": "stdio",
      "command": "python",
      "args": ["/path/to/hjb_nas_mcp.py"]
    }
  ]
}
```

**Note:** The exact configuration format depends on your Claude client. Refer to Claude's documentation for your specific interface.

---

## MySQL MCP Methods

### Basic Queries

#### `list_publication_families()`
List all publication families in the system.

```json
{
  "method": "list_publication_families"
}
```

**Response:**
```json
{
  "success": true,
  "rows": [
    {
      "family_id": 1,
      "family_root": "American_Architect",
      "family_code": "AMER_ARCH",
      "display_name": "The American Architect and Building News",
      "family_type": "journal"
    },
    ...
  ],
  "count": 5
}
```

#### `get_family_by_code(family_code)`
Get details for a specific family.

```json
{
  "method": "get_family_by_code",
  "params": {
    "family_code": "AMER_ARCH"
  }
}
```

#### `list_issues(family_id)`
List issues for a family (or all recent issues if family_id omitted).

```json
{
  "method": "list_issues",
  "params": {
    "family_id": 1
  }
}
```

#### `list_works(family_id, work_type)`
List works (articles, ads, chapters) with optional filters.

```json
{
  "method": "list_works",
  "params": {
    "family_id": 1,
    "work_type": "article"
  }
}
```

#### `get_work_occurrences(work_id)`
Get all occurrences (appearances) of a specific work.

```json
{
  "method": "get_work_occurrences",
  "params": {
    "work_id": 42
  }
}
```

**Response shows where that work appeared (which issues, pages, sources).**

#### `get_pipeline_stats()`
Get high-level statistics about the entire pipeline.

```json
{
  "method": "get_pipeline_stats"
}
```

**Response:**
```json
{
  "success": true,
  "stats": {
    "total_families": 5,
    "total_issues": 1234,
    "total_works": 45678,
    "total_containers": 890,
    "works_by_type": {
      "article": 40000,
      "advertisement": 5000,
      "index": 678
    }
  }
}
```

### Custom SQL

For more complex queries:

```json
{
  "method": "query",
  "params": {
    "sql": "SELECT COUNT(*) as count FROM works_t WHERE work_type = %s",
    "params": ["advertisement"]
  }
}
```

---

## NAS MCP Methods

### Directory Operations

#### `list_directory(path)`
List contents of a directory.

```json
{
  "method": "list_directory",
  "params": {
    "path": "Working_Files/0200_STATE"
  }
}
```

**Response:**
```json
{
  "success": true,
  "path": "Working_Files/0200_STATE",
  "items": [
    {
      "name": "flags",
      "type": "dir",
      "path": "Working_Files/0200_STATE/flags",
      "modified": "2026-01-22T14:30:00"
    },
    {
      "name": "logs",
      "type": "dir",
      "path": "Working_Files/0200_STATE/logs",
      "modified": "2026-01-22T14:25:00"
    },
    {
      "name": "watcher_heartbeat.json",
      "type": "file",
      "size": 256,
      "path": "Working_Files/0200_STATE/watcher_heartbeat.json",
      "modified": "2026-01-22T14:31:15"
    }
  ]
}
```

#### `read_file(path)`
Read a text file (up to 1MB by default).

```json
{
  "method": "read_file",
  "params": {
    "path": "Working_Files/0200_STATE/watcher_heartbeat.json"
  }
}
```

#### `read_json_file(path)`
Read and parse a JSON file.

```json
{
  "method": "read_json_file",
  "params": {
    "path": "Working_Files/0200_STATE/watcher_heartbeat.json"
  }
}
```

**Response:**
```json
{
  "success": true,
  "path": "Working_Files/0200_STATE/watcher_heartbeat.json",
  "data": {
    "watcher": "watcher_orionmx_1",
    "last_check": "2026-01-22T14:31:15Z"
  }
}
```

#### `get_file_info(path)`
Get metadata (size, modified date, etc.) for a file or directory.

```json
{
  "method": "get_file_info",
  "params": {
    "path": "Raw_Input/0110_Internet_Archive"
  }
}
```

### Task Monitoring

#### `list_flag_tasks(status)`
List task flags. Status: "pending", "processing", "completed", "failed", or null (all).

```json
{
  "method": "list_flag_tasks",
  "params": {
    "status": "pending"
  }
}
```

**Response:**
```json
{
  "success": true,
  "tasks": {
    "pending": [
      {
        "file": "20260122-143000-ocr-sim_architect_1890jan.json",
        "task_id": "20260122-143000-ocr-sim_architect_1890jan",
        "task_type": "ocr",
        "status": "pending",
        "created_at": "2026-01-22T14:30:00Z"
      }
    ],
    "processing": [],
    "completed": [
      {
        "file": "20260121-150000-download-sim_architect_1890dec.json",
        "task_id": "20260121-150000-download-sim_architect_1890dec",
        "task_type": "download",
        "status": "completed",
        "created_at": "2026-01-21T15:00:00Z"
      }
    ],
    "failed": []
  }
}
```

#### `get_watcher_heartbeat()`
Check if the watcher is alive and running.

```json
{
  "method": "get_watcher_heartbeat"
}
```

**Response:**
```json
{
  "success": true,
  "path": "Working_Files/0200_STATE/watcher_heartbeat.json",
  "data": {
    "watcher": "watcher_orionmx_1",
    "last_check": "2026-01-22T14:31:15Z"
  }
}
```

If the heartbeat is stale (> 5 minutes old), the watcher may have crashed.

### Search

#### `find_files(pattern, search_path, max_results)`
Search for files matching a glob pattern.

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

---

## Usage Examples

### Example 1: Check Pipeline Health

```
Claude: "Check the pipeline health. How many families, issues, and works do we have? Is the watcher running?"

Claude executes:
1. method: "get_pipeline_stats" → returns counts
2. method: "get_watcher_heartbeat" → returns last check time
3. Returns summary to user
```

### Example 2: Investigate a Failed Task

```
Claude: "What tasks failed in the last hour?"

Claude executes:
1. method: "list_flag_tasks", params: {"status": "failed"}
2. For each failed task, reads the JSON file to inspect error details
3. Returns list of failures with error messages
```

### Example 3: Find Recent Log Files

```
Claude: "Show me the most recent processing logs."

Claude executes:
1. method: "find_files", params: {"pattern": "*.log", "search_path": "Working_Files/0200_STATE/logs"}
2. Lists recent log files by modification date
3. Reads one or more for you to inspect
```

### Example 4: Check Work Deduplication

```
Claude: "How many occurrences does the article 'Architectural Advances' have?"

Claude executes:
1. method: "query", params: {"sql": "SELECT work_id FROM works_t WHERE title LIKE %s", "params": ["%Architectural Advances%"]}
2. method: "get_work_occurrences", params: {"work_id": <result>}
3. Returns all places that work appears
```

---

## Security Considerations

### Database Access
- **Never store credentials in code.** Use environment variables.
- The MySQL MCP only provides read/write to the HJB database; it cannot access other databases on HostGator.
- Consider restricting the DB user to read-only if you only need querying (create a separate read-only user in MySQL).

### NAS Access
- The NAS MCP enforces path traversal protection (you cannot escape the project root).
- Files are capped at 1MB for reading (prevents accidentally loading huge files).
- Directory listings are capped at 100 items (prevents timeout on huge directories).

### Best Practices
1. **Keep MCPs on your local machine or trusted network** — don't expose them publicly.
2. **Rotate credentials periodically** — change your MySQL password occasionally.
3. **Monitor access** — if you integrate with a web interface, log who is querying what.
4. **Test in development first** — verify MCPs work in a test environment before production use.

---

## Troubleshooting

### MySQL MCP Connection Fails

**Problem:** `ERROR: Database connection failed`

**Solutions:**
- Verify `HJB_MYSQL_PASSWORD` is set correctly (check HostGator credentials).
- Ensure your local machine has internet access to HostGator.
- Check that the database name (`raneywor_hjbproject`) exists.
- Test connection manually:
  ```bash
  mysql -h raneywor.mysql.pythonanywhere-services.com -u raneywor -p
  ```

### NAS MCP Cannot Find Files

**Problem:** `Path does not exist` or `Invalid path`

**Solutions:**
- Verify `HJB_NAS_ROOT` is set to the correct UNC path.
- On Windows, confirm the NAS is accessible:
  ```bash
  dir "\\RaneyHQ\Michael\02_Projects\Historical_Journals_And_Books"
  ```
- Check file permissions (ensure your user can read the NAS).
- If using WSL or Linux, mount the NAS first:
  ```bash
  sudo mount -t cifs //RaneyHQ/Michael -o username=<user>,password=<pass> /mnt/rnaneyhq
  ```

### MCPs Not Showing in Claude

**Problem:** MCPs don't appear as available tools in Claude.

**Solutions:**
- Ensure Python and dependencies are installed.
- Test MCPs manually from command line:
  ```bash
  echo '{"method": "get_pipeline_stats"}' | python hjb_mysql_mcp.py
  ```
- Check Claude's MCP configuration file (varies by client).
- Verify the command path is absolute, not relative.

### Timeout or Slow Responses

**Problem:** Queries or file operations hang.

**Solutions:**
- Reduce `MAX_FILE_SIZE` or `MAX_ITEMS_IN_LIST` if they're too large.
- Check NAS or database performance (if many concurrent operations).
- For large directory listings, use `find_files` instead of `list_directory` with a specific pattern.

---

## Next Steps

1. **Deploy MCPs** to your system following the setup instructions above.
2. **Test manually** with sample requests (examples provided).
3. **Integrate with Claude** via your client's MCP configuration.
4. **Start using them** for debugging and monitoring the pipeline!

---

## Future Enhancements

Potential additions to these MCPs:

1. **Create/Update Operations** (write flag files, insert DB records).
2. **Real-time Monitoring Dashboard** (websocket support for live stats).
3. **Batch Operations** (process multiple queries in one request).
4. **Event Notifications** (email alerts if watcher crashes, tasks fail, etc.).
5. **Integration with GitHub API** (query recent commits, branches, PRs).

Let me know if you'd like any of these added!
