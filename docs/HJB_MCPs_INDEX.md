# HJB MCPs — File Index & Reading Guide

## 📋 Start Here

**New to these MCPs?** Start with:
1. **HJB_MCPs_SUMMARY.md** (this overview — 10 min read)
2. **HJB_MCPs_QUICK_REFERENCE.md** (cheat sheet — 5 min)
3. **HJB_MCPs_DEPLOYMENT_CHECKLIST.md** (setup guide — follow steps)

**Want full details?** Then read:
4. **HJB_MCPs_INTEGRATION_GUIDE.md** (comprehensive documentation — 30 min)

---

## 📁 Files Included

### Executable Scripts (Python)

```
hjb_mysql_mcp.py               298 lines
├─ Connects to your MySQL database (HostGator)
├─ Implements 7 high-level methods
├─ Supports custom SQL queries
└─ JSON request/response protocol

hjb_nas_mcp.py                 457 lines
├─ Browses NAS file system (\\RaneyHQ\Michael\...)
├─ Implements 7 file operation methods
├─ Monitors task flags and watcher heartbeat
└─ Safe path validation (no directory traversal)
```

### Documentation (Markdown)

```
HJB_MCPs_SUMMARY.md            9.2 KB  ← EXECUTIVE SUMMARY (read first)
├─ Overview of what MCPs do
├─ Quick start (5 min setup)
├─ Use cases
├─ Architecture
├─ Limitations & considerations
└─ Next steps

HJB_MCPs_QUICK_REFERENCE.md    4.6 KB  ← CHEAT SHEET
├─ One-page method reference
├─ Common diagnostic commands
├─ Directory structure
├─ Tips & tricks
└─ Key environment variables

HJB_MCPs_DEPLOYMENT_CHECKLIST.md  8.9 KB  ← SETUP GUIDE
├─ Pre-deployment verification
├─ Step-by-step deployment (7 steps)
├─ Manual testing instructions
├─ Integration with Claude
├─ Monitoring setup
├─ Security hardening
└─ Troubleshooting checklist

HJB_MCPs_INTEGRATION_GUIDE.md  12 KB  ← FULL DOCUMENTATION
├─ Complete setup instructions
├─ 7+ database methods with examples
├─ 7+ file system methods with examples
├─ 15+ diagnostic recipes
├─ Security considerations
├─ Troubleshooting (detailed)
└─ Future enhancements
```

---

## 🎯 What To Do First

### Option 1: "Just Show Me How to Set It Up" (30 minutes)
1. Read: **HJB_MCPs_SUMMARY.md** (get context)
2. Read: **HJB_MCPs_DEPLOYMENT_CHECKLIST.md** (follow each step)
3. Run the manual tests (step 3 in checklist)
4. You're done! Use the Quick Reference when needed

### Option 2: "I Want to Understand Everything" (90 minutes)
1. Read: **HJB_MCPs_SUMMARY.md** (overview)
2. Read: **HJB_MCPs_INTEGRATION_GUIDE.md** (full details with examples)
3. Read: **HJB_MCPs_DEPLOYMENT_CHECKLIST.md** (setup)
4. Keep **HJB_MCPs_QUICK_REFERENCE.md** nearby for lookup

### Option 3: "I'm in a Hurry" (5 minutes)
1. Skim: **HJB_MCPs_QUICK_REFERENCE.md** (method names)
2. Follow: **HJB_MCPs_DEPLOYMENT_CHECKLIST.md** (copy-paste commands)
3. Test the examples (step 3 in checklist)
4. Start using them!

---

## 📊 Quick Stats

| Metric | Value |
|--------|-------|
| Total Python code | 755 lines |
| Total documentation | 35 KB |
| Number of methods | 14 (7 per MCP) |
| Example queries | 30+ |
| Setup time | 10-30 min |
| Time to first query | 5 min |

---

## 🔍 Method Reference at a Glance

### MySQL MCP Methods

| Method | Purpose | Time | Use When |
|--------|---------|------|----------|
| `get_pipeline_stats()` | Overall statistics | <1s | Want to see total counts |
| `list_publication_families()` | All families | <1s | Browse all families |
| `get_family_by_code()` | Single family | <1s | Need family details |
| `list_issues()` | Issues for a family | <1s | Check what's been ingested |
| `list_works()` | Articles/ads/chapters | <1s | Browse content |
| `get_work_occurrences()` | Where a work appears | <1s | Find duplicates |
| `query()` | Custom SQL | <1s | Complex questions |

### NAS MCP Methods

| Method | Purpose | Time | Use When |
|--------|---------|------|----------|
| `list_directory()` | Browse folder | <0.1s | See what's in a directory |
| `read_file()` | Read text file | <0.1s | Check log or config |
| `read_json_file()` | Read JSON | <0.2s | Parse flag files |
| `get_file_info()` | File metadata | <0.1s | Check modification date |
| `find_files()` | Search with pattern | <2s | Find logs, configs, etc |
| `list_flag_tasks()` | Task queue status | <0.5s | See pending/failed tasks |
| `get_watcher_heartbeat()` | Watcher alive? | <0.2s | Check if watcher is running |

---

## 🚀 Common Workflows

### "Check Pipeline Health"
```
HJB_MCPs_QUICK_REFERENCE.md → "Check If Watcher Is Alive"
Run: get_watcher_heartbeat() + get_pipeline_stats()
```

### "Debug a Failed Task"
```
HJB_MCPs_QUICK_REFERENCE.md → "Find Failed Tasks"
Run: list_flag_tasks(status="failed")
Then: read_json_file(path_to_flag)
```

### "Investigate Data Duplication"
```
HJB_MCPs_INTEGRATION_GUIDE.md → "Work Occurrences"
Run: list_works() then get_work_occurrences(work_id)
```

### "Explore Raw Inputs"
```
HJB_MCPs_QUICK_REFERENCE.md → "Directory Paths"
Run: list_directory("Raw_Input/0110_Internet_Archive")
```

---

## 📌 Key Takeaways

### What These MCPs Enable
✓ Claude can query your database directly  
✓ Claude can browse your NAS instantly  
✓ No more manual file copying needed  
✓ Real-time pipeline monitoring  
✓ Faster debugging and investigation  

### What They Require
✓ Python 3.8+  
✓ `mysql-connector-python` library  
✓ Network access to HostGator (MySQL)  
✓ Network access to NAS  
✓ Environment variables set  

### What They Protect Against
✓ SQL injection (parameterized queries)  
✓ Directory traversal attacks (path validation)  
✓ Accidental huge file reads (size limits)  
✓ Credential exposure (env vars only, no code)  

---

## ❓ FAQ

**Q: Do I have to use MCPs with Claude?**  
A: No. They're optional. But they make Claude much more useful for debugging your pipeline.

**Q: Can I use these MCPs without Claude?**  
A: Absolutely! They're standalone Python programs. You can call them from scripts, cron jobs, etc.

**Q: Are MCPs secure?**  
A: Yes. They include security features like path validation, SQL parameterization, and no hardcoded credentials.

**Q: What if my NAS is mounted on Linux?**  
A: See Troubleshooting in DEPLOYMENT_CHECKLIST.md for SMB/NFS mount instructions.

**Q: Can I modify the MCPs?**  
A: Yes! They're Python scripts. Feel free to customize methods or add new ones.

**Q: What if my database password has special characters?**  
A: Set it in the environment variable without quotes. The MCPs will handle it correctly.

---

## 🎓 Learning Path

```
Beginner
  ↓
Read: HJB_MCPs_SUMMARY.md
  ↓
Follow: HJB_MCPs_DEPLOYMENT_CHECKLIST.md
  ↓
Use: HJB_MCPs_QUICK_REFERENCE.md (keep handy)
  ↓
Intermediate
  ↓
Read: HJB_MCPs_INTEGRATION_GUIDE.md (full details)
  ↓
Try: All 30+ example queries
  ↓
Advanced
  ↓
Modify: MCP Python scripts
  ↓
Add: Custom methods/features
  ↓
Expert
  ↓
Contribute: Enhancements back to project
```

---

## 📞 Support Resources

### In This Package
- **HJB_MCPs_INTEGRATION_GUIDE.md** → Troubleshooting section (detailed)
- **HJB_MCPs_DEPLOYMENT_CHECKLIST.md** → Troubleshooting checklist
- **hjb_mysql_mcp.py** → Source code with docstrings
- **hjb_nas_mcp.py** → Source code with docstrings

### Testing MCPs
```bash
# Test MySQL MCP
echo '{"method": "get_pipeline_stats"}' | python hjb_mysql_mcp.py

# Test NAS MCP
echo '{"method": "list_directory", "params": {"path": ""}}' | python hjb_nas_mcp.py
```

---

## ✅ You're Ready!

1. Pick your reading path (Beginner/Intermediate/Advanced)
2. Follow the setup checklist
3. Run the tests
4. Start using them

**Everything you need is in these 6 files.**

Good luck! Your pipeline just got a lot more transparent. 🎉
