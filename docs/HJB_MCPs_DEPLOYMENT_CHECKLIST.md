# HJB MCPs Deployment Checklist

Use this to deploy and verify the MCPs are working correctly.

---

## Pre-Deployment Verification

- [ ] Python 3.8+ installed on deployment machine
- [ ] `mysql-connector-python` available:
  ```bash
  pip install mysql-connector-python
  ```
- [ ] NAS is accessible from your machine (can you browse \\RaneyHQ\Michael\02_Projects\...?)
- [ ] MySQL credentials are correct (test with `mysql` client)

---

## Step 1: Deploy Files

- [ ] Copy `hjb_mysql_mcp.py` to project scripts directory
- [ ] Copy `hjb_nas_mcp.py` to project scripts directory
- [ ] Make scripts executable:
  ```bash
  chmod +x hjb_mysql_mcp.py hjb_nas_mcp.py
  ```
- [ ] Verify file permissions (should be readable/executable by the user running them)

---

## Step 2: Configure Environment Variables

### Option A: System Environment Variables (Recommended)

**Windows (Command Prompt, elevated):**
```cmd
setx HJB_MYSQL_HOST raneywor.mysql.pythonanywhere-services.com
setx HJB_MYSQL_USER raneywor
setx HJB_MYSQL_PASSWORD "your_password_here"
setx HJB_MYSQL_DB raneywor_hjbproject
setx HJB_NAS_ROOT "\\RaneyHQ\Michael\02_Projects\Historical_Journals_And_Books"
setx HJB_MAX_FILE_SIZE 1048576
setx HJB_MAX_ITEMS_IN_LIST 100
```

**Windows (PowerShell, elevated):**
```powershell
[Environment]::SetEnvironmentVariable("HJB_MYSQL_HOST", "raneywor.mysql.pythonanywhere-services.com", "User")
[Environment]::SetEnvironmentVariable("HJB_MYSQL_USER", "raneywor", "User")
[Environment]::SetEnvironmentVariable("HJB_MYSQL_PASSWORD", "your_password_here", "User")
[Environment]::SetEnvironmentVariable("HJB_MYSQL_DB", "raneywor_hjbproject", "User")
[Environment]::SetEnvironmentVariable("HJB_NAS_ROOT", "\\RaneyHQ\Michael\02_Projects\Historical_Journals_And_Books", "User")
[Environment]::SetEnvironmentVariable("HJB_MAX_FILE_SIZE", "1048576", "User")
[Environment]::SetEnvironmentVariable("HJB_MAX_ITEMS_IN_LIST", "100", "User")
```

**Linux/macOS:**
```bash
export HJB_MYSQL_HOST=raneywor.mysql.pythonanywhere-services.com
export HJB_MYSQL_USER=raneywor
export HJB_MYSQL_PASSWORD="your_password_here"
export HJB_MYSQL_DB=raneywor_hjbproject
export HJB_NAS_ROOT='/mnt/rnaneyhq/Michael/02_Projects/Historical_Journals_And_Books'
export HJB_MAX_FILE_SIZE=1048576
export HJB_MAX_ITEMS_IN_LIST=100

# Add to ~/.bashrc or ~/.zshrc for persistence
```

### Option B: .env File (Alternative)

Create `.env` in the project root:
```
HJB_MYSQL_HOST=raneywor.mysql.pythonanywhere-services.com
HJB_MYSQL_USER=raneywor
HJB_MYSQL_PASSWORD=your_password_here
HJB_MYSQL_DB=raneywor_hjbproject
HJB_NAS_ROOT=\\RaneyHQ\Michael\02_Projects\Historical_Journals_And_Books
HJB_MAX_FILE_SIZE=1048576
HJB_MAX_ITEMS_IN_LIST=100
```

Then modify the MCPs to load `.env` at startup:
```python
from dotenv import load_dotenv
load_dotenv()
```

- [ ] Environment variables are set and verified
- [ ] Can view variables:
  ```bash
  # Windows
  echo %HJB_MYSQL_PASSWORD%
  
  # Linux/macOS
  echo $HJB_MYSQL_PASSWORD
  ```

---

## Step 3: Test MCPs Manually

### Test MySQL MCP

```bash
echo '{"method": "get_pipeline_stats"}' | python hjb_mysql_mcp.py
```

Expected output: JSON with stats like `{"success": true, "stats": {...}}`

If error:
- [ ] Check `HJB_MYSQL_PASSWORD` is correct
- [ ] Verify database is accessible from your network
- [ ] Check HostGator status (no outage?)

### Test NAS MCP

```bash
echo '{"method": "list_directory", "params": {"path": ""}}' | python hjb_nas_mcp.py
```

Expected output: JSON listing the root of the NAS project folder

If error:
- [ ] Check `HJB_NAS_ROOT` path is correct
- [ ] Verify NAS share is accessible:
  ```bash
  # Windows
  dir "\\RaneyHQ\Michael\02_Projects\Historical_Journals_And_Books"
  
  # Linux (if mounted)
  ls /mnt/rnaneyhq/...
  ```
- [ ] Check network connectivity to NAS

---

## Step 4: Test Specific Operations

Run each of these to ensure MCPs are fully functional:

### MySQL Tests

```bash
# 1. Get all families
echo '{"method": "list_publication_families"}' | python hjb_mysql_mcp.py

# 2. Get specific family
echo '{"method": "get_family_by_code", "params": {"family_code": "AMER_ARCH"}}' | python hjb_mysql_mcp.py

# 3. List issues
echo '{"method": "list_issues"}' | python hjb_mysql_mcp.py

# 4. Custom query
echo '{"method": "query", "params": {"sql": "SELECT COUNT(*) as total FROM publication_families_t"}}' | python hjb_mysql_mcp.py
```

- [ ] All MySQL tests pass

### NAS Tests

```bash
# 1. List Working_Files
echo '{"method": "list_directory", "params": {"path": "Working_Files"}}' | python hjb_nas_mcp.py

# 2. Read watcher heartbeat
echo '{"method": "read_json_file", "params": {"path": "Working_Files/0200_STATE/watcher_heartbeat.json"}}' | python hjb_nas_mcp.py

# 3. List flag tasks
echo '{"method": "list_flag_tasks", "params": {"status": "completed"}}' | python hjb_nas_mcp.py

# 4. Find logs
echo '{"method": "find_files", "params": {"pattern": "*.log", "search_path": "Working_Files/0200_STATE/logs", "max_results": 5}}' | python hjb_nas_mcp.py
```

- [ ] All NAS tests pass

---

## Step 5: Integrate with Claude

### For Claude Desktop Client

If you're using the Claude desktop application, the MCP integration depends on your client version. Check Claude's documentation or contact support for the exact configuration method.

### For Claude.ai Web Interface

The web interface may not support local MCPs directly. Consider:
- Using a Docker container to expose MCPs over HTTP
- Checking if Claude.ai has MCP integration (as of Jan 2026)
- Running MCPs locally and manually sharing results

### Manual Testing with Claude

You can always test by:
1. Running the MCP from command line
2. Copying the JSON output
3. Pasting into Claude chat

Example:
```bash
python hjb_mysql_mcp.py << EOF
{"method": "get_pipeline_stats"}
EOF
```

Then share the result with Claude for interpretation.

- [ ] MCPs integrated with your Claude interface (or tested manually)

---

## Step 6: Monitor and Maintain

### Set Up Heartbeat Monitoring (Optional)

Create a simple monitor script (`check_watcher.py`):

```python
#!/usr/bin/env python3
import json
import subprocess
from datetime import datetime, timedelta

result = subprocess.run(
    ['python', 'hjb_nas_mcp.py'],
    input='{"method": "get_watcher_heartbeat"}',
    capture_output=True,
    text=True
)

data = json.loads(result.stdout)

if data['success']:
    last_check = datetime.fromisoformat(data['data']['last_check'].replace('Z', '+00:00'))
    age = datetime.now(last_check.tzinfo) - last_check
    
    if age > timedelta(minutes=5):
        print(f"⚠️  WATCHER STALE: Last check {age.total_seconds()/60:.0f} minutes ago")
    else:
        print(f"✓ WATCHER OK: Last check {age.total_seconds():.0f} seconds ago")
else:
    print(f"✗ WATCHER ERROR: {data['error']}")
```

Run this periodically (e.g., via cron or Task Scheduler) to monitor watcher health.

- [ ] Monitoring set up (optional but recommended)

---

## Step 7: Security Hardening

- [ ] Never commit credentials to Git (keep in env vars only)
- [ ] Restrict file permissions on any .env file:
  ```bash
  chmod 600 .env
  ```
- [ ] Periodically rotate MySQL password (change on HostGator, update env var)
- [ ] Review logs for unusual queries or file access
- [ ] Consider read-only MySQL user for safety (if only querying)

---

## Troubleshooting Checklist

### MCP won't start

- [ ] Python 3.8+ installed?
- [ ] `mysql-connector-python` installed?
- [ ] Syntax error in script? (Try running directly to see error)

### Database connection fails

- [ ] `HJB_MYSQL_PASSWORD` set correctly?
- [ ] Can you ping HostGator? (Network issue?)
- [ ] Database still exists on HostGator?
- [ ] User account not locked or suspended?

### NAS access fails

- [ ] `HJB_NAS_ROOT` path is correct?
- [ ] NAS is powered on and accessible?
- [ ] Network connection to NAS working?
- [ ] User has permissions to read the share?

### Slow responses

- [ ] Large files or directories? (Increase limits or use find_files)
- [ ] Database under load? (Check HostGator performance)
- [ ] Network latency? (Test ping times)

---

## Verification Checklist

After full deployment:

- [ ] `hjb_mysql_mcp.py` can connect to database
- [ ] `hjb_nas_mcp.py` can browse NAS
- [ ] All manual tests pass
- [ ] Environment variables are persistent (survive reboot)
- [ ] MCPs accessible from Claude (or tested manually)
- [ ] Monitoring in place (optional)
- [ ] Documentation reviewed (INTEGRATION_GUIDE.md, QUICK_REFERENCE.md)

---

## Deployment Complete!

Once all checkmarks are done, you're ready to use the MCPs for:
- Querying pipeline stats
- Monitoring watcher health
- Investigating failed tasks
- Browsing NAS files
- Debugging database issues

**Next steps:**
1. Start using them in Claude for pipeline monitoring
2. Create custom queries as needed
3. Set up alerts if desired
4. Iterate and improve MCPs based on usage

---

## Questions or Issues?

Refer to:
- `HJB_MCPs_INTEGRATION_GUIDE.md` — Full documentation
- `HJB_MCPs_QUICK_REFERENCE.md` — Quick lookup
- Script docstrings — Detailed method descriptions
