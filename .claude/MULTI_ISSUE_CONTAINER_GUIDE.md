# Multi-Issue Container Handling Guide

**Added to HJB Database Schema Reference**  
**Date:** January 23, 2026

---

## Overview

A **multi-issue container** is a single physical file (bound volume PDF, image archive, microfilm reel) that contains multiple journal issues or book sections. This is extremely common in historical archival sources, particularly:

- **Bound volumes** combining 4-6 monthly issues
- **Trade supplements** collected at the end of a volume
- **Index sections** spanning entire volumes
- **Special inserts** bound within issues

The HJB schema handles this elegantly through the `issue_containers_t` mapping table, which links logical issues to physical page ranges within containers.

---

## Your Approach: Manual Review + Database Registration

You've chosen the most practical path for initial processing:

1. **Manual review** of containers to identify issue boundaries (headers, dates, page breaks)
2. **Database registration** of all issues and their mappings
3. **No physical splitting** required—the schema handles multi-issue containers natively

This means:
- ✅ Minimal preprocessing overhead
- ✅ Complete audit trail of boundaries
- ✅ Flexibility for later processing
- ✅ Ability to re-associate separated supplements

---

## How It Works

### The Three-Table Pattern

For a container with multiple issues, you use three coordinated tables:

```
┌──────────────────────────────────────────────────────────────┐
│ containers_t (ONE record for the physical source)            │
│ - Source: IA identifier, URL, format info                   │
│ - Physical facts: total pages, date range                    │
│ - Notes: Issue boundaries identified                         │
└────────────────────────────┬─────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
    │ Issue 1     │  │ Issue 2     │  │ Issue 3     │
    │ (issues_t)  │  │ (issues_t)  │  │ (issues_t)  │
    └─────────────┘  └─────────────┘  └─────────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
    ┌──────────────────────────────────────────┐
    │ issue_containers_t (mappings)            │
    │ - Issue 1 → pages 1-24                   │
    │ - Issue 2 → pages 25-48                  │
    │ - Issue 3 → pages 49-72                  │
    │ Quality scores and completeness flags    │
    └──────────────────────────────────────────┘
```

### Example: American Architect Vol 27 (Jan-Apr 1890)

This is a real scenario you'll encounter:

**What you see in IA:**
- One item ID: `loc_booksandmags_14093893`
- One PDF or image set: ~96 pages
- Four monthly issues bound together

**What you register:**

#### Step 1: One Container Record
```sql
INSERT INTO containers_t
  (source_system, source_identifier, source_url, family_id, 
   container_label, container_type, total_pages, date_start, 
   date_end, notes)
VALUES
  ('ia', 'loc_booksandmags_14093893', 
   'https://archive.org/details/amarch_v27_1890_01', 
   1, 'American Architect Vol 27 1890 Jan-Apr', 'bound_volume', 96, 
   '1890-01-01', '1890-04-30',
   'Bound volume with 4 issues. Pages 1-24: Issue 793 (Jan 10, 1890). 
    Pages 25-48: Issue 794 (Jan 17, 1890). Pages 49-72: Issue 795 
    (Feb 7, 1890). Pages 73-96: Issue 796 (Mar 7, 1890).');
```

#### Step 2: Four Issue Records
```sql
INSERT INTO issues_t
  (title_id, family_id, volume_label, volume_sort, issue_label, 
   issue_sort, issue_date_start, year_published, canonical_issue_key)
VALUES
  (1, 1, '27', 27, '793', 793, '1890-01-10', 1890, 
   'AMER_ARCH_27_793_1890'),
  (1, 1, '27', 27, '794', 794, '1890-01-17', 1890, 
   'AMER_ARCH_27_794_1890'),
  (1, 1, '27', 27, '795', 795, '1890-02-07', 1890, 
   'AMER_ARCH_27_795_1890'),
  (1, 1, '27', 27, '796', 796, '1890-03-07', 1890, 
   'AMER_ARCH_27_796_1890');
```

#### Step 3: Issue-to-Container Mappings
```sql
INSERT INTO issue_containers_t
  (issue_id, container_id, start_page_in_container, 
   end_page_in_container, is_preferred, is_complete, 
   ocr_quality_score)
VALUES
  (1, 1, 1, 24, 1, 1, 0.92),   -- Jan issue
  (2, 1, 25, 48, 1, 1, 0.91),  -- Feb issue
  (3, 1, 49, 72, 1, 1, 0.90),  -- Mar issue
  (4, 1, 73, 96, 1, 1, 0.89);  -- Apr issue
```

---

## Special Case: Advertising Supplements

Your note about the "advertisers trade supplement pages" is important. This is when:

- The last issue of a volume contains pages of advertisements/trade sections
- These pages are indexed by the original issue they belong to
- They're physically separated from the main issue content
- You want to re-unite them with their parent issues for the reference library

### Two Handling Options

#### Option 1: Keep in Main Container (Simpler, Recommended)
Don't split anything. Register the entire container including supplements:

```sql
-- Container with main content + supplements
INSERT INTO containers_t
  (..., notes)
VALUES
  (..., 'Vol 27 Issue 4 (pages 1-20) + Trade supplements for all 
         4 issues of volume (pages 21-96). See issue_containers 
         for page mappings.');

-- Issue 4 mapping (main content only)
INSERT INTO issue_containers_t
  (issue_id, container_id, start_page_in_container, 
   end_page_in_container, ..., coverage_notes)
VALUES
  (4, 1, 1, 20, ..., 'Main content only. Trade supplements for this 
   issue are on pages 21-36.');
```

Then during Stage 2 processing, your segmentation logic can:
- Extract main pages by issue normally (Issue 4: pages 1-20)
- Identify supplement pages (pages 21-96)
- Re-associate supplements with their parent issues during Stage 3

#### Option 2: Create Secondary Container (More Flexible)
If supplements warrant separate tracking:

```sql
-- Primary container: main issue content
INSERT INTO containers_t
  (..., container_label, total_pages, notes)
VALUES
  (..., 'American Architect Vol 27 Issue 4 Main Content', 20, 
   'Main pages of final issue of volume.');

-- Secondary container: supplements only
INSERT INTO containers_t
  (..., source_identifier, container_label, total_pages, notes)
VALUES
  (..., 'loc_booksandmags_14093893_supplements', 
   'American Architect Vol 27 Trade Supplements', 76,
   'Advertising/trade supplement pages extracted from final issue. 
    Maps to issues 1-4 per coverage_notes.');

-- Map each issue to its supplement pages
INSERT INTO issue_containers_t
  (issue_id, container_id, start_page_in_container, 
   end_page_in_container, ..., coverage_notes)
VALUES
  (1, 2, 1, 18, ..., 'Trade supplement pages for Jan issue'),
  (2, 2, 19, 35, ..., 'Trade supplement pages for Feb issue'),
  (3, 2, 36, 52, ..., 'Trade supplement pages for Mar issue'),
  (4, 2, 53, 76, ..., 'Trade supplement pages for Apr issue + volume index');
```

**Recommendation:** Start with Option 1 (keep in main container). It's simpler and the `issue_containers_t` mapping makes it clear where supplements are. You can always refactor later if you need separate processing.

---

## During Manual Review

When you examine a multi-issue container to identify boundaries, document in `containers_t.notes`:

```
ISSUE BOUNDARIES (Manual Review - Jan 23, 2026):
- Pages 1-24: Issue 793, Volume 27, January 10, 1890
  Header marked "793" at top of p. 1
- Pages 25-48: Issue 794, Volume 27, January 17, 1890
  Header marked "794" at top of p. 25, clear page break
- Pages 49-72: Issue 795, Volume 27, February 7, 1890
  Header marked "795" at top of p. 49
- Pages 73-96: Issue 796, Volume 27, March 7, 1890
  Header marked "796" at top of p. 73

SPECIAL NOTES:
- No supplement pages in this container
- All issues appear complete
- Page numbering: continuous throughout (1-96)
```

This creates an **audit trail** that explains:
- How boundaries were identified
- When the review happened
- Any uncertainties or assumptions

---

## Processing Implications

### Stage 1 (Ingestion)
- Download container ✓
- Create `issues_t` records for each issue within container ✓
- Create `issue_containers_t` mappings with page ranges ✓
- Document boundaries in `containers_t.notes` ✓

### Stage 2 (OCR & Segmentation)
- Process container once (pages 1-96)
- Use `issue_containers_t` mappings to extract per-issue content
- Segment works within each issue (articles, ads, etc.)

### Stage 3 (Canonicalization)
- Deduplicate works normally
- Re-associate supplements with parent issues if applicable
- Prepare reference files per issue

### Stage 4 (Publication)
- Each issue publishes independently to wiki
- Supplements (if tracked separately) can be included in parent issue page

---

## Best Practices

### DO:

✅ **Document everything in notes**
- Include dates of manual review
- Explain how boundaries were identified
- Note any uncertainties

✅ **Use `issue_containers_t` to store the mapping**
- This is exactly what the table is for
- Page ranges define issue boundaries precisely
- Creates a queryable record

✅ **Set quality scores per issue**
- If Issue 1 has clearer OCR than Issue 4, note it
- Helps Stage 3 choose canonical versions

✅ **Mark incomplete issues**
- If pages are missing, set `is_complete = 0`
- Document in `coverage_notes`

### DON'T:

❌ **Split the physical container files**
- Keep the container as downloaded
- Let page mappings handle the logical splitting
- This preserves the original source

❌ **Guess at boundaries**
- If unsure, flag for second review
- Mark with uncertainty in notes
- Better to be accurate than fast

❌ **Create multiple containers for one physical source**
- Unless there's a strong reason (supplements needing separate processing)
- Multiple containers → duplicate download/storage
- Start simple, refactor if needed

---

## Example Workflow

### 1. You Download from IA
```
Downloaded: loc_booksandmags_14093893
Format: JP2 images in archive.zip
Pages: 96
Metadata: IA's scandata.xml provided
```

### 2. You Review Manually
```
Open PDF or image viewer
Scan through identifying issue boundaries
Note headers: "793", "794", "795", "796"
Identify page breaks and dates
Document findings
```

### 3. You Register in Database
```
INSERT into containers_t (one record for the physical source)
INSERT into issues_t (four records, one per issue)
INSERT into issue_containers_t (four mappings with page ranges)
```

### 4. System Processes
```
Stage 1: Validates download, confirms 96 pages, checks OCR files
Stage 2: Processes all 96 pages; uses mappings to extract per-issue
Stage 3: Deduplicates; creates canonical versions; prepares reference
Stage 4: Publishes Issue 793, 794, 795, 796 as separate wiki pages
```

---

## Questions to Ask During Review

When manually reviewing a multi-issue container:

1. **Clear boundaries?** Are headers/dates indicating issue changes obvious?
2. **Page continuity?** Are page numbers continuous or reset per issue?
3. **TOC present?** Does metadata or a table of contents indicate structure?
4. **Supplements?** Are there separate pages with different formatting/content?
5. **Missing content?** Are any pages blank or clearly missing?
6. **Quality variation?** Does OCR quality differ across issues?

Document all findings in `containers_t.notes`. This information guides Stage 2 and Stage 3 processing.

---

## Summary

You've chosen the right approach:

1. **Manual review** ensures accuracy for the American Architect family
2. **Database registration** creates a complete, queryable record
3. **No file splitting** keeps things simple and preserves sources
4. **Flexible for later** allows you to handle supplements however makes sense

The schema already supports this perfectly through `issue_containers_t`. Your job is simply to:
- Identify boundaries (manual review)
- Register the mappings (SQL)
- Document your findings (notes fields)

And the system takes it from there.

---

**Added to:** HJB_DATABASE_SCHEMA_REFERENCE.md (Operational Notes section)

