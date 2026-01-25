# Multi-Issue Container Registration Cheat Sheet

## Quick Summary

**Multi-issue container?** One physical file (PDF, image archive) containing multiple issues.

**Your workflow:**
1. Manually identify issue boundaries (headers, dates, page breaks)
2. Register everything in the database (don't split files)
3. Let the schema handle the rest

---

## Three-Step Registration

### Step 1: Create ONE Container Record

```sql
INSERT INTO containers_t
  (source_system, source_identifier, source_url, family_id, 
   container_label, container_type, total_pages, date_start, date_end, notes)
VALUES
  ('ia', 'IDENTIFIER', 'URL', family_id, 'Label', 'bound_volume', page_count,
   'start_date', 'end_date', 'Detailed notes of issue boundaries here...');
```

**Key points:**
- One record per physical source file
- Total pages = entire container
- Notes = your boundary findings

---

### Step 2: Create Multiple Issue Records

```sql
INSERT INTO issues_t
  (title_id, family_id, volume_label, volume_sort, issue_label, 
   issue_sort, issue_date_start, year_published, canonical_issue_key)
VALUES
  (title_id, family_id, 'vol', vol_num, 'issue_num', issue_num, 'date', year, 'KEY'),
  (title_id, family_id, 'vol', vol_num, 'issue_num', issue_num, 'date', year, 'KEY'),
  -- repeat for each issue in container
  ;
```

**Key points:**
- One record per logical issue
- Even if they're in the same physical file
- Use canonical_issue_key to prevent duplicates

---

### Step 3: Create Mappings

```sql
INSERT INTO issue_containers_t
  (issue_id, container_id, start_page_in_container, 
   end_page_in_container, is_preferred, is_complete, ocr_quality_score)
VALUES
  (issue_id_1, container_id, 1, 24, 1, 1, 0.92),
  (issue_id_2, container_id, 25, 48, 1, 1, 0.91),
  (issue_id_3, container_id, 49, 72, 1, 1, 0.90),
  (issue_id_4, container_id, 73, 96, 1, 1, 0.89);
```

**Key points:**
- One row per issue
- **start_page_in_container** = first page of this issue in the file
- **end_page_in_container** = last page of this issue in the file
- Set is_preferred=1 unless you have another source for same issue
- ocr_quality_score = average OCR quality for this issue

---

## Manual Review Documentation Template

When reviewing the container, document in `containers_t.notes`:

```
ISSUE BOUNDARIES (Reviewed [DATE] by [REVIEWER]):

Issue [NUM], Vol [VOL], [DATE]:
- Pages: [START]-[END]
- Header indicator: [DESCRIBE]
- Quality: [NOTES]

Issue [NUM], Vol [VOL], [DATE]:
- Pages: [START]-[END]
- Header indicator: [DESCRIBE]
- Quality: [NOTES]

SPECIAL NOTES:
- [Any supplements, missing pages, format issues, etc.]

CONFIDENCE: [High/Medium/Low] - [REASON]
```

---

## Real Example

**Container:** American Architect Vol 27 (Jan-Apr 1890), IA ID: loc_booksandmags_14093893

### Step 1: Container
```sql
INSERT INTO containers_t (source_system, source_identifier, source_url, 
family_id, container_label, container_type, total_pages, date_start, date_end, notes)
VALUES
('ia', 'loc_booksandmags_14093893', 
 'https://archive.org/details/amarch_v27_1890_01', 
 1, 'American Architect Vol 27 1890 Jan-Apr', 'bound_volume', 96,
 '1890-01-01', '1890-04-30',
 'ISSUE BOUNDARIES (Reviewed Jan 23, 2026):
  Issue 793, Vol 27, Jan 10, 1890: Pages 1-24 (header marked "793")
  Issue 794, Vol 27, Jan 17, 1890: Pages 25-48 (header marked "794")
  Issue 795, Vol 27, Feb 7, 1890: Pages 49-72 (header marked "795")
  Issue 796, Vol 27, Mar 7, 1890: Pages 73-96 (header marked "796")
  SPECIAL: No supplements in this container.');
```

### Step 2: Issues (assume title_id=1)
```sql
INSERT INTO issues_t 
(title_id, family_id, volume_label, volume_sort, issue_label, issue_sort, 
 issue_date_start, year_published, canonical_issue_key)
VALUES
(1, 1, '27', 27, '793', 793, '1890-01-10', 1890, 'AMER_ARCH_27_793_1890'),
(1, 1, '27', 27, '794', 794, '1890-01-17', 1890, 'AMER_ARCH_27_794_1890'),
(1, 1, '27', 27, '795', 795, '1890-02-07', 1890, 'AMER_ARCH_27_795_1890'),
(1, 1, '27', 27, '796', 796, '1890-03-07', 1890, 'AMER_ARCH_27_796_1890');
```

### Step 3: Mappings (assume container_id=1, issue_ids=1-4)
```sql
INSERT INTO issue_containers_t 
(issue_id, container_id, start_page_in_container, end_page_in_container, 
 is_preferred, is_complete, ocr_quality_score)
VALUES
(1, 1, 1, 24, 1, 1, 0.92),
(2, 1, 25, 48, 1, 1, 0.91),
(3, 1, 49, 72, 1, 1, 0.90),
(4, 1, 73, 96, 1, 1, 0.89);
```

**Done!** The system now knows:
- Container 1 = 96 pages total, from IA
- Issues 1-4 = logical units within that container
- Pages 1-24 = Issue 1, Pages 25-48 = Issue 2, etc.

---

## Troubleshooting

### "I'm not sure where one issue ends and another begins"
→ Document your uncertainty in notes: "Boundary between issues X and Y unclear. Assuming page break indicates boundary."

### "Some pages appear to be missing"
→ Set `is_complete = 0` in issue_containers_t and note in coverage_notes: "Pages 45-48 missing (blank)"

### "The supplements are physically separate"
→ **Option A:** Keep in main container, note location in coverage_notes
→ **Option B:** Create secondary container, map each issue to its supplement pages

### "Two issues have the same content (reprint)"
→ Create both issues_t records. Let Stage 3 deduplication handle it. Set one as `is_preferred=1` when multiple containers have same issue.

### "I found the same issue in two different containers"
→ Create mappings in issue_containers_t for both. Mark one as `is_preferred=1`. Set `is_complete` and `ocr_quality_score` appropriately for each.

---

## Don't Forget

✅ **Document in notes** — How you identified boundaries  
✅ **Set page ranges** — Be precise with start/end pages  
✅ **Set quality scores** — Helps later processing  
✅ **Mark complete/incomplete** — Flag missing content  
✅ **Use canonical_issue_key** — Prevents duplicate registrations  

---

## After Registration

The system will:
1. **Stage 1:** Validate the container
2. **Stage 2:** Use page mappings to extract per-issue content
3. **Stage 3:** Deduplicate and prepare canonical versions
4. **Stage 4:** Publish each issue separately to wiki

You don't need to split files or do any preprocessing. Just register the mappings and let the pipeline handle it.

