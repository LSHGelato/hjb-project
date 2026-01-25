# HJB Database Schema Reference

**Version:** 1.0  
**Last Updated:** January 23, 2026  
**Database:** `raneywor_hjbproject`  
**Author:** Michael Raney

---

## Table of Contents

1. [Overview & Design Philosophy](#overview--design-philosophy)
2. [Nomenclature Convention](#nomenclature-convention)
3. [Table Relationship Diagram](#table-relationship-diagram)
4. [Core Tables](#core-tables)
5. [Data Integrity Rules](#data-integrity-rules)
6. [Common Queries](#common-queries)
7. [Operational Notes](#operational-notes)

---

## Overview & Design Philosophy

The HJB database implements a **Works & Occurrences model** that separates intellectual content from physical instances. This allows us to:

- Track the same article/chapter across multiple issues/editions
- Manage duplicate detection and canonicalization
- Handle multi-source content (Internet Archive, HathiTrust, local scans, etc.)
- Support both journals (with multiple issues) and books (with multiple editions)
- Preserve provenance while identifying authoritative versions

**Key Design Principles:**

1. **Family → Title → Issue/Edition**: Publications are organized hierarchically
2. **Containers**: Physical scanning units (e.g., a PDF, a bound volume) from an external source
3. **Works & Occurrences**: A Work is unique intellectual content; an Occurrence is where it appears
4. **Status Tracking**: Every stage of the pipeline is tracked (download, validation, processing)
5. **Denormalization for Performance**: Some fields are duplicated strategically (e.g., `family_id` in `issues_t`)

---

## Nomenclature Convention

### Publication Family Naming

Publications are organized into **families** to represent serial titles that change names or merge/split over time.

#### For Journals (with `family_type = 'journal'`)

Suffix: **`_family`**

Examples:
- `American_Architect_family` (journal title changed multiple times: "American Architect and Building News" → "The American Architect" → "American Architect and Architectural Review" → "The American Architect")
- `American_Builder_family`
- `Building_Age_family`
- `Railway_Engineering_and_Maintenance_of_Way_family`

**Rationale:** Journals historically changed names, merged with others, or split. A "family" represents the continuous intellectual lineage of the serial, even as its masthead changed.

#### For Book Series (with `family_type = 'book_series'`)

Suffix: **`_series`**

Example:
- `Cyclopedia_of_Architecture_Building_Construction_series` (multi-volume work with editions)

**Rationale:** A book series consists of multiple volumes with the same overarching title/subject.

#### For Single-Volume Books (with `family_type = 'book'`)

Suffix: **`_book`**

Examples:
- `History_of_Architecture_book` (single book, may have multiple editions)
- `Theory_and_Practice_of_Bridge_Design_book`
- `A_Treatise_on_Masonry_Construction_book`

**When Books Share the Same Title:** Differentiate by author or editor name, appended before `_book`:

- `Theory_of_Design_book_Jones` (authored/edited by Jones)
- `Theory_of_Design_book_Smith` (authored/edited by Smith)

**Rationale:** A single-volume book is treated as its own "family" to clarify that it's a complete intellectual work, not a series or ongoing serial. The `family_root` name uses only the title (unless that exact title is part of the official title). When name collisions occur, the author/editor surname is appended to ensure uniqueness. The year is **not** included unless it is actually part of the published title.

**Note on Editions:** Multiple editions of the same book (e.g., 1st edition 1890, 2nd edition 1900) share the same `family_id` and are differentiated in `publication_titles_t` with `edition_label` and `edition_sort` fields.

### Additional Naming Rules

1. **Underscores replace spaces:** `American_Architect` not `American Architect`
2. **No special characters:** Keep alphanumeric and underscore only
3. **Case:** Use `PascalCase` for readability (or lowercase with underscores)
4. **Uniqueness:** `family_root` is UNIQUE in the database

---

## Table Relationship Diagram

```
                       ┌─────────────────────────────────────────────────┐
                       │     publication_families_t                      │
                       │  (Families: journals, book series, single books)│
                       │                                                  │
                       │  • family_id (PK)                               │
                       │  • family_root (UNIQUE) "American_Architect..."│
                       │  • family_code "AMER_ARCH"                      │
                       │  • display_name "American Architect"            │
                       │  • family_type {journal, book_series, book}     │
                       └────────────────────┬────────────────────────────┘
                                            │
                                   (1:N relationship)
                                            │
                ┌───────────────────────────┼───────────────────────────┐
                │                           │                           │
                ▼                           ▼                           ▼
    ┌──────────────────────┐    ┌──────────────────────┐    ┌─────────────────────┐
    │ publication_titles_t │    │    containers_t      │    │    issues_t         │
    │  (Title variants)    │    │ (Source files: PDF,  │    │  (Issues/Editions)  │
    │                      │    │  image archives)     │    │                     │
    │  • title_id (PK)     │    │                      │    │  • issue_id (PK)    │
    │  • family_id (FK)    │    │  • container_id (PK) │    │  • title_id (FK)    │
    │  • display_title     │    │  • family_id (FK)    │    │  • family_id (FK)   │
    │  • publisher         │    │  • source_system     │    │  • volume_label     │
    │  • city, country     │    │  • source_identifier │    │  • issue_label      │
    │  • run_start/end     │    │  • container_label   │    │  • issue_date_start │
    │  • is_primary        │    │  • container_type    │    │  • is_book_edition  │
    └──────────────┬───────┘    │  • has_jp2, _djvu... │    └────────┬────────────┘
                  │              │  • total_pages       │             │
                  │              │  • download_status   │             │
                  │              └─────────────┬────────┘             │
                  │                            │                     │
                  │              ┌─────────────┼─────────────┐        │
                  │              │             │             │        │
                  │              ▼             ▼             ▼        │
                  │         ┌──────────────────────────┐             │
                  │         │  issue_containers_t      │             │
                  │         │ (Maps issues to sources) │             │
                  │         │                          │             │
                  │         │ • issue_container_id(PK) │             │
                  │         │ • issue_id (FK)          │◄────────────┘
                  │         │ • container_id (FK)      │
                  │         │ • start_page_in_container│
                  │         │ • end_page_in_container  │
                  │         │ • is_preferred           │
                  │         │ • ocr_quality_score      │
                  │         └──────────┬───────────────┘
                  │                    │
                  │                    ▼
                  │         ┌──────────────────────────┐
                  │         │      pages_t             │
                  │         │  (Individual pages)      │
                  │         │                          │
                  │         │ • page_id (PK)           │
                  │         │ • container_id (FK)      │
                  │         │ • issue_id (FK)          │
                  │         │ • page_index             │
                  │         │ • page_number_printed    │
                  │         │ • page_type              │
                  │         │ • ocr_text (search)      │
                  │         │ • has_ocr, ocr_source    │
                  │         │ • image_dpi, _sha256     │
                  │         └──────────┬───────────────┘
                  │                    │
                  │                    │ (1:N relationship)
                  │                    │
                  │         ┌──────────┴───────────────┐
                  │         │                          │
                  │         ▼                          ▼
                  │ ┌──────────────────────┐   ┌────────────────────┐
                  │ │   works_t            │   │ work_occurrences_t │
                  │ │  (Unique content)    │   │ (Where works are)  │
                  │ │                      │   │                    │
                  │ │ • work_id (PK)       │   │ • occurrence_id(PK)│
                  │ │ • title              │   │ • work_id (FK)     │
                  │ │ • author             │   │ • issue_id (FK)    │
                  │ │ • work_type          │   │ • container_id(FK) │
                  │ │ • canonical_text     │   │ • start_page_id(FK)│
                  │ │ • dedup_fingerprint  │   │ • end_page_id (FK) │
                  │ │ • canonical_work_id  │──→│ • ocr_text         │
                  │ │   (self-ref)         │   │ • is_canonical     │
                  │ │ • dedup_status       │   │ • image_references │
                  │ └──────────────────────┘   └────────────────────┘
                  │
                  └─ (Historical: publication_titles supports browsing by publisher/date)

┌─────────────────────────────────────────────────────────────────────────────┐
│ SUPPORTING TABLES                                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  processing_status_t    - Tracks pipeline stage completion (1:1 w/ container)
│  task_executions_t      - Watcher task execution log                        │
│  schema_version_t       - Database migration tracking                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Core Tables

### 1. `publication_families_t`

**Purpose:** Represents the top-level grouping of publications (serial families, book series, or single books).

| Column | Type | Nullable | Key | Description |
|--------|------|----------|-----|-------------|
| `family_id` | INT(10) UNSIGNED | NO | PK, AI | Unique identifier for the family. Auto-incremented. |
| `family_root` | VARCHAR(255) | NO | UNIQUE | **Filesystem-safe family name** used in directory structures and configuration. No spaces; underscores separate words. Examples: `American_Architect_family`, `Cyclopedia_of_Architecture_series`, `History_of_Architecture_book`, `Theory_of_Design_book_Jones`. When multiple books share the same title, differentiate by author/editor: `Theory_of_Design_book_Smith`. This is the stable identifier across all project systems. |
| `family_code` | VARCHAR(64) | YES | | **Short alphanumeric code** for the family, used in abbreviated references, logs, and UI. Examples: `AMER_ARCH`, `AMER_BLDR`, `CARP_BLDG`. Can be NULL if not assigned. |
| `display_name` | VARCHAR(255) | NO | | **Human-readable name** as it should appear in the UI, research output, and publication. Examples: "American Architect family", "Cyclopedia of Architecture, Building and Construction", "Theory and Practice of Design (1890 edition)". This is for end-users. |
| `family_type` | ENUM('journal', 'book_series', 'book') | NO | | **Type of publication**. `journal` = ongoing periodical; `book_series` = multi-volume work with shared title; `book` = single-volume book (possibly with multiple editions). Determines how to interpret child titles and issues. |
| `notes` | TEXT | YES | | **Long-form description or bibliographic notes**. May include publication history, name changes, mergers, content notes, or references to sources. Used to document why a family exists and its scope. |
| `created_at` | DATETIME | NO | | Timestamp when the record was inserted. |
| `updated_at` | DATETIME | NO | | Timestamp of last update; automatically refreshed. |

**Examples:**

```sql
INSERT INTO publication_families_t 
  (family_root, family_code, display_name, family_type, notes)
VALUES
  ('American_Architect_family', 'AMER_ARCH', 'American Architect family', 'journal', 
   'Serial journal founded 1876, changed names multiple times, ceased 1938'),
  ('History_of_Architecture_book', 'HIST_ARCH', 'History of Architecture', 'book',
   'Single-volume treatise on architectural history, by J. A. Symonds'),
  ('Theory_of_Design_book_Jones', 'THEORY_DESIGN_J', 'Theory of Design (Jones)', 'book',
   'Single-volume book on design theory, authored by Jones'),
  ('Theory_of_Design_book_Smith', 'THEORY_DESIGN_S', 'Theory of Design (Smith)', 'book',
   'Single-volume book on design theory, authored by Smith');
```

---

### 2. `publication_titles_t`

**Purpose:** Represents specific publication titles or editions within a family. For journals, handles name changes; for books, handles distinct editions.

| Column | Type | Nullable | Key | Description |
|--------|------|----------|-----|-------------|
| `title_id` | INT(10) UNSIGNED | NO | PK, AI | Unique identifier for this title variant. |
| `family_id` | INT(10) UNSIGNED | NO | FK | **Foreign key** to `publication_families_t`. Establishes hierarchy. |
| `display_title` | VARCHAR(255) | NO | | **Title as published on the masthead or book cover.** Examples: "The American Architect and Building News", "The American Architect", "History of Architecture". |
| `title_variant` | VARCHAR(255) | YES | | **Alternative or subtitle** (if the full title has a subtitle or is known by multiple names). Example: for "The American Architect and Building News", variant might be "American Architect and Building News" (without "The"). |
| `publisher` | VARCHAR(255) | YES | | **Publisher name(s) during this title's run.** Example: "James R. Osgood & Co." or "Houghton, Osgood & Co.". Helps identify when publishers changed. |
| `city` | VARCHAR(128) | YES | | **City of publication.** Example: "Boston", "New York". Useful for cataloging and disambiguation. |
| `country` | VARCHAR(64) | YES | | **Country of publication.** Example: "USA", "UK". Most HJB content is USA. |
| `run_start_date` | DATE | YES | | **First issue/edition date** under this specific title. If a journal changed titles, this marks when the *new* title began. |
| `run_end_date` | DATE | YES | | **Last issue/edition date** under this title. Marks when the title was superseded or ceased. |
| `is_primary` | TINYINT(1) | NO | | **Boolean flag (1 or 0).** Set to 1 if this is the primary/most commonly used title for the family. Helps with display and navigation (which title to show first). Default is 1. |
| `notes` | TEXT | YES | | **Editorial notes** about this title variant. May document why this title exists, mergers with other titles, or variants to be aware of. |
| `created_at` | DATETIME | NO | | Timestamp when inserted. |
| `updated_at` | DATETIME | NO | | Timestamp of last update. |

**Indexes:**
- PRIMARY: `title_id`
- FOREIGN KEY: `family_id`
- COMPOSITE: `run_start_date`, `run_end_date` (for date range queries)

**Examples:**

```sql
-- Multiple titles in the American Architect family
INSERT INTO publication_titles_t 
  (family_id, display_title, publisher, city, run_start_date, run_end_date, is_primary)
VALUES
  (1, 'The American Architect and Building News', 'James R. Osgood & Co.', 'Boston', 
   '1876-01-01', '1878-03-30', 1),
  (1, 'The American Architect and Building News', 'Houghton, Osgood & Co.', 'Boston', 
   '1878-04-06', '1880-05-01', 1),
  (1, 'The American Architect', 'The Swetland Publishing Co.', 'New York', 
   '1909-01-06', '1910-11-30', 1);

-- Distinct editions of a book
INSERT INTO publication_titles_t 
  (family_id, display_title, publisher, city, run_start_date, run_end_date, is_primary)
VALUES
  (5, 'History of Architecture', 'Smith & Company', 'Boston', 
   '1890-01-01', '1890-12-31', 1),
  (5, 'History of Architecture (Revised Edition)', 'Smith & Company', 'Boston', 
   '1900-01-01', '1900-12-31', 0);
```

---

### 3. `issues_t`

**Purpose:** Represents individual journal issues or book editions. The bridge between titles and physical containers.

| Column | Type | Nullable | Key | Description |
|--------|------|----------|-----|-------------|
| `issue_id` | INT(10) UNSIGNED | NO | PK, AI | Unique identifier. |
| `title_id` | INT(10) UNSIGNED | NO | FK | **Foreign key** to `publication_titles_t`. Links to the specific title variant. |
| `family_id` | INT(10) UNSIGNED | NO | FK | **Foreign key** to `publication_families_t`. Denormalized for query performance (avoids JOIN to titles in many queries). |
| `volume_label` | VARCHAR(64) | YES | | **Volume number as published**, e.g., "27", "Vol. 27", "Volume IV". Human-readable label from source. |
| `volume_sort` | INT(11) | YES | | **Numeric sort key for volume.** Allows queries like "ORDER BY volume_sort ASC". Example: if volume_label is "27", volume_sort is 27; if "Vol. IV", volume_sort is 4. |
| `issue_label` | VARCHAR(64) | YES | | **Issue or number designation**, e.g., "793", "No. 1", "Issue 12". Label from source. |
| `issue_sort` | INT(11) | YES | | **Numeric sort key for issue within volume.** Example: if issue_label is "No. 1", issue_sort is 1. |
| `part_label` | VARCHAR(64) | YES | | **For multi-part issues.** If an issue was published in multiple parts, this labels the part. Example: "Part 1", "Part 2", "First Half". |
| `edition_label` | VARCHAR(64) | YES | | **For books: edition designation**, e.g., "1st ed", "2nd ed", "Revised edition". Distinguishes reprints or updates. |
| `edition_sort` | INT(11) | YES | | **Numeric sort for editions**, e.g., 1 for 1st edition, 2 for 2nd edition. Enables sorting multiple editions. |
| `issue_date_start` | DATE | YES | | **Cover date or publication start date.** For journals, the date on the issue cover. For books, publication date. If range (e.g., a quarterly spanning Jan–Mar), this is the start. |
| `issue_date_end` | DATE | YES | | **End date if the issue spans a range.** For a monthly issue, same as start. For a quarterly (Jan–Mar), this is March 31. For uncertain dates, may be set to a best-guess end of period. |
| `year_published` | YEAR(4) | YES | | **Publication year.** MySQL YEAR type (stores 0000–9999). Extracted/indexed separately for range queries. |
| `is_book_edition` | TINYINT(1) | NO | | **Boolean flag (0 or 1).** Set to 1 if this record represents a book edition (vs. a journal issue). Determines processing logic and presentation. |
| `is_special_issue` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 for special, themed, or out-of-sequence issues (e.g., "Christmas Special", "Anniversary Issue"). Affects sorting and display. |
| `is_supplement` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 if this is a supplement to another issue (e.g., index, extra advertising section bound separately). |
| `title_on_masthead` | VARCHAR(255) | YES | | **Actual text printed on the issue's cover/masthead.** May differ from `display_title` in `publication_titles_t` due to OCR errors or formatting. Used for validation/QA. |
| `canonical_issue_key` | VARCHAR(255) | YES | UNIQUE | **Derived unique key for deduplication.** A hash or concatenation of (family_id, volume, issue, edition, year) to detect if we have multiple scans of the same logical issue. Used to prevent duplicate processing. |
| `total_pages` | INT(11) | YES | | **Expected page count.** Helps validate that all pages were ingested and processed. |
| `notes` | TEXT | YES | | **Editorial or operational notes.** May document issues encountered, missing pages, OCR problems, or special handling. |
| `created_at` | DATETIME | NO | | Timestamp when inserted. |
| `updated_at` | DATETIME | NO | | Timestamp of last update. |

**Indexes:**
- PRIMARY: `issue_id`
- UNIQUE: `canonical_issue_key` (deduplication)
- COMPOSITE: `title_id, volume_sort, issue_sort` (for ordered browsing)
- SIMPLE: `family_id`, `year_published`

**Examples:**

```sql
INSERT INTO issues_t 
  (title_id, family_id, volume_label, volume_sort, issue_label, issue_sort,
   issue_date_start, year_published, is_book_edition, total_pages, canonical_issue_key)
VALUES
  (1, 1, '27', 27, '793', 793, '1890-01-10', 1890, 0, 24, 
   'AMER_ARCH_27_793_1890'),
  (1, 1, '27', 27, '794', 794, '1890-01-17', 1890, 0, 20, 
   'AMER_ARCH_27_794_1890'),
  (5, 5, NULL, NULL, NULL, NULL, '1890-01-01', 1890, 1, 412, 
   'HIST_ARCH_ED1_1890');
```

---

### 4. `containers_t`

**Purpose:** Represents a physical source file or archive (PDF, JP2 bundle, set of images, etc.) from an external source like Internet Archive or HathiTrust.

| Column | Type | Nullable | Key | Description |
|--------|------|----------|-----|-------------|
| `container_id` | INT(10) UNSIGNED | NO | PK, AI | Unique identifier. |
| `source_system` | VARCHAR(64) | NO | | **Source system identifier**: `"ia"` (Internet Archive), `"hathitrust"`, `"local"`, `"usmodernist"`, etc. Determines how to validate and process the data. |
| `source_identifier` | VARCHAR(255) | NO | | **Unique ID from the source system.** For IA, this is the IA identifier (e.g., `"loc_booksandmags_14093893"`). For HathiTrust, the Hathi ID. For local scans, a local path or naming scheme. UNIQUE with `source_system`. |
| `source_url` | VARCHAR(512) | YES | | **Original source URL.** Allows re-fetching if needed. Example: `"https://archive.org/details/amarch_v27_1890_01"`. May be NULL for local scans. |
| `family_id` | INT(10) UNSIGNED | YES | FK | **Foreign key** to `publication_families_t`. Links the container to a family if known at ingestion time. May be NULL if unmapped initially. |
| `title_id` | INT(10) UNSIGNED | YES | FK | **Foreign key** to `publication_titles_t`. Links to a specific title if known. May be NULL. |
| `container_label` | VARCHAR(255) | YES | | **Human-readable label** for the container. Example: `"American Architect Vol 27 1890 Jan-Apr"`. Used in logs and UI. |
| `container_type` | VARCHAR(64) | YES | | **Physical type**: `"bound_volume"`, `"microfilm"`, `"pdf"`, `"image_archive"`, etc. Indicates how pages are organized. |
| `volume_label` | VARCHAR(64) | YES | | **Volume number** if applicable. May redundantly match `issues_t.volume_label` for validation. |
| `date_start` | DATE | YES | | **Earliest date covered** by this container (if spanning multiple issues). |
| `date_end` | DATE | YES | | **Latest date covered.** |
| `total_pages` | INT(11) | YES | | **Total page count** in this container. For a JP2 archive, this is the number of JP2 images. |
| `has_jp2` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 if JP2 image files are present (IA sources). |
| `has_djvu_xml` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 if DjVu XML (IA OCR) is present. |
| `has_hocr` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 if hOCR format OCR is present (IA). |
| `has_alto` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 if ALTO XML (HathiTrust OCR) is present. |
| `has_mets` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 if METS XML (structural metadata) is present (HathiTrust). |
| `has_pdf` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 if a PDF version is available. |
| `has_scandata` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 if IA scandata.xml (page structure metadata) is present. |
| `raw_input_path` | VARCHAR(512) | YES | | **Path in the Raw_Input layer** on NAS where original files are stored. Example: `"\\RaneyHQ\Michael\02_Projects\Historical_Journals_And_Books\Raw_Input\0110_Internet_Archive\SIM\American_Architect\1890\loc_booksandmags_14093893"`. |
| `working_path` | VARCHAR(512) | YES | | **Path in Working_Files** for intermediate processing. May be NULL if not yet processed. |
| `reference_path` | VARCHAR(512) | YES | | **Path in Reference_Library** for curated output. Populated after Stage 3 (canonicalization) completes. |
| `download_status` | ENUM('pending', 'in_progress', 'complete', 'failed') | NO | | **Stage 1 download status.** `pending` = awaiting download; `in_progress` = currently downloading; `complete` = successfully downloaded; `failed` = download failed (needs retry or manual attention). |
| `validation_status` | ENUM('pending', 'passed', 'failed') | NO | | **Stage 1 validation status.** Indicates whether file integrity checks passed. |
| `downloaded_at` | DATETIME | YES | | **Timestamp when download completed.** NULL if not yet downloaded. |
| `validated_at` | DATETIME | YES | | **Timestamp when validation completed.** |
| `notes` | TEXT | YES | | **Operational notes.** May document errors, missing files, special handling, or deviations from expected structure. |
| `created_at` | DATETIME | NO | | Timestamp when record created. |
| `updated_at` | DATETIME | NO | | Timestamp of last update. |

**Indexes:**
- PRIMARY: `container_id`
- UNIQUE: `(source_system, source_identifier)`
- SIMPLE: `family_id`, `title_id`, `source_system`, `download_status`
- COMPOSITE: `date_start, date_end`

**Examples:**

```sql
INSERT INTO containers_t
  (source_system, source_identifier, source_url, family_id, container_label, 
   container_type, total_pages, has_jp2, has_hocr, has_pdf, has_scandata, 
   raw_input_path, download_status, validation_status)
VALUES
  ('ia', 'loc_booksandmags_14093893', 'https://archive.org/details/amarch_v27_1890_01', 
   1, 'American Architect Vol 27 1890 Jan-Apr', 'image_archive', 96, 1, 1, 1, 1,
   '\\RaneyHQ\Michael\02_Projects\Historical_Journals_And_Books\Raw_Input\0110_Internet_Archive\SIM\American_Architect\1890\loc_booksandmags_14093893',
   'complete', 'passed');
```

---

### 5. `issue_containers_t`

**Purpose:** Maps (joins) issues to containers, handling the case where one issue spans multiple containers or one container has multiple issues.

| Column | Type | Nullable | Key | Description |
|--------|------|----------|-----|-------------|
| `issue_container_id` | INT(10) UNSIGNED | NO | PK, AI | Unique identifier. |
| `issue_id` | INT(10) UNSIGNED | NO | FK | **Foreign key** to `issues_t`. The issue/edition being referenced. |
| `container_id` | INT(10) UNSIGNED | NO | FK | **Foreign key** to `containers_t`. The source container. |
| `start_page_in_container` | INT(11) | YES | | **First page of this issue** within the container (1-based or 0-based depending on convention; be consistent). For a container with just one issue, this is typically 1 (or 0). |
| `end_page_in_container` | INT(11) | YES | | **Last page of this issue** in the container. Helps with page range extraction. |
| `is_preferred` | TINYINT(1) | NO | | **Boolean flag (0 or 1).** Set to 1 if this is the **preferred source** for this issue among multiple containers. Used when deduplicating (if same issue comes from two sources, mark one as preferred). Only one container per issue should be marked preferred. |
| `is_complete` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 if all pages of the issue are present in this container. Set to 0 if pages are missing or incomplete. |
| `ocr_quality_score` | DECIMAL(3,2) | YES | | **OCR confidence score (0.00–1.00)** for this issue in this container. Average or aggregate from all pages. Helps decide which source to use if multiple available. |
| `coverage_notes` | TEXT | YES | | **Operational notes** about coverage, missing pages, or quality issues specific to this issue–container pair. |
| `created_at` | DATETIME | NO | | Timestamp when inserted. |

**Indexes:**
- PRIMARY: `issue_container_id`
- UNIQUE: `(issue_id, container_id)` (prevent duplicate mappings)

**Examples:**

```sql
INSERT INTO issue_containers_t
  (issue_id, container_id, is_preferred, is_complete, ocr_quality_score)
VALUES
  (1, 1, 1, 1, 0.92),  -- Issue 1 comes from container 1, preferred source, complete
  (1, 2, 0, 1, 0.88);  -- Issue 1 also found in container 2 (HathiTrust), not preferred
```

---

### 6. `pages_t`

**Purpose:** Individual pages within a container, with OCR text and metadata.

| Column | Type | Nullable | Key | Description |
|--------|------|----------|-----|-------------|
| `page_id` | INT(10) UNSIGNED | NO | PK, AI | Unique identifier. |
| `container_id` | INT(10) UNSIGNED | NO | FK | **Foreign key** to `containers_t`. Which container this page belongs to. |
| `issue_id` | INT(10) UNSIGNED | YES | FK | **Foreign key** to `issues_t`. Denormalized for performance; may be NULL initially and filled during processing. |
| `page_index` | INT(11) | NO | | **0-based sequential index** within the container. First page is 0, second is 1, etc. Used for consistent ordering. |
| `page_number_printed` | VARCHAR(32) | YES | | **Page number as printed on the page itself.** May be "1", "i", "Cover", "128", etc. Different from `page_index` (which is positional). |
| `page_label` | VARCHAR(64) | YES | | **Label from scandata or METS metadata.** Examples: "Cover", "i", "ii", "1", "2". Helps identify special pages. |
| `page_type` | ENUM('content', 'cover', 'index', 'toc', 'advertisement', 'plate', 'blank', 'other') | NO | | **Classification of page content.** Used for processing logic (e.g., don't segment blank pages; handle advertisements differently). |
| `is_cover` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 if this is a cover page. Redundant with `page_type = 'cover'` but allows indexed lookups. |
| `is_plate` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 if this is an illustration plate or special image page. |
| `is_blank` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 if page is blank or nearly blank. Allows filtering in OCR processing. |
| `is_supplement` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 if part of a supplement (e.g., bound-in advertising section). |
| `has_ocr` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 if OCR text is present. Helps track processing. |
| `ocr_source` | VARCHAR(32) | YES | | **Which OCR source was used.** Example: `"ia_hocr"`, `"ia_djvu"`, `"tesseract"`, `"hathi_alto"`. Documents the origin of the text for quality assessment. |
| `ocr_confidence` | DECIMAL(3,2) | YES | | **Overall OCR confidence (0.00–1.00)** for this page. Average of word-level confidences if available. |
| `ocr_word_count` | INT(11) | YES | | **Number of words** recognized by OCR. Helps detect if OCR mostly failed. |
| `ocr_char_count` | INT(11) | YES | | **Number of characters** in OCR text. Useful for validation. |
| `ocr_text` | MEDIUMTEXT | YES | | **Plain text extracted from OCR.** This is the searchable content. Stored here for full-text indexing and search. For large pages, may be truncated or stored separately and referenced. |
| `image_width` | INT(11) | YES | | **Width in pixels** of the source image. Helps detect low-resolution scans. |
| `image_height` | INT(11) | YES | | **Height in pixels.** |
| `image_dpi` | INT(11) | YES | | **Resolution of image in DPI.** Typical values 300–600. Low DPI (< 200) may indicate poor quality. |
| `image_sha256` | CHAR(64) | YES | | **SHA-256 hash** of source image file. Used for duplicate detection (if two sources have identical images, hash will match). |
| `image_file_path` | VARCHAR(512) | YES | | **Path to the page image file** (JP2, TIFF, PNG, etc.) in storage. May be on NAS or reference folder. |
| `ocr_file_path` | VARCHAR(512) | YES | | **Path to OCR source file** (HOCR, ALTO, etc.). Allows re-extracting if needed. |
| `notes` | TEXT | YES | | **Operational notes.** May flag pages with poor OCR, unusual formats, or missing data. |
| `created_at` | DATETIME | NO | | Timestamp when inserted. |
| `updated_at` | DATETIME | NO | | Timestamp of last update. |

**Indexes:**
- PRIMARY: `page_id`
- COMPOSITE: `(container_id, page_index)` (for efficient page sequencing)
- SIMPLE: `issue_id`, `page_type`
- FULLTEXT (optional): `ocr_text` (for search)

**Examples:**

```sql
INSERT INTO pages_t
  (container_id, issue_id, page_index, page_number_printed, page_label, page_type,
   has_ocr, ocr_source, ocr_confidence, ocr_word_count, ocr_text, image_dpi)
VALUES
  (1, 1, 0, 'Cover', 'Cover', 'cover', 1, 'ia_hocr', 0.95, 150, 
   'American Architect Vol 27 No 793 January 10 1890', 300),
  (1, 1, 1, '1', '1', 'content', 1, 'ia_hocr', 0.92, 1200, 
   'ARCHITECTURAL PROGRESS IN THE CITIES...', 300),
  (1, 1, 2, '2', '2', 'content', 1, 'ia_hocr', 0.88, 800, 
   'Design principles for residential...', 300);
```

---

### 7. `works_t`

**Purpose:** Canonical record for unique intellectual content (articles, advertisements, chapters, etc.).

| Column | Type | Nullable | Key | Description |
|--------|------|----------|-----|-------------|
| `work_id` | INT(10) UNSIGNED | NO | PK, AI | Unique identifier. |
| `work_type` | ENUM('article', 'advertisement', 'chapter', 'section', 'index', 'toc', 'editorial', 'review', 'letter', 'notice', 'other') | NO | | **Type of work.** Determines segmentation, templates, and processing logic. Examples: `article` for journal article, `chapter` for book section, `advertisement` for ad. |
| `title` | VARCHAR(512) | YES | | **Title or heading** of the work. For articles: article title. For ads: advertiser name or product. For chapters: chapter title. May be extracted via OCR and manual correction. |
| `subtitle` | VARCHAR(512) | YES | | **Subtitle or secondary heading.** Used if the work has both title and subtitle. |
| `author` | VARCHAR(255) | YES | | **Primary author name(s).** Extracted from byline or metadata if available. May be NULL for unsigned articles. Free-form text; future expansion to separate author table possible. |
| `additional_authors` | TEXT | YES | | **Other authors or contributors.** Stored as JSON or delimited text for extensibility. Example: `["Jane Smith", "John Doe"]` or `"Jane Smith; John Doe"`. |
| `subject` | VARCHAR(255) | YES | | **Primary subject or category.** Used for browsing/tagging. Example: "Architecture", "Bridge Design", "Material Science". |
| `keywords` | TEXT | YES | | **Search keywords.** Stored as JSON array or pipe-delimited list. Populated manually or via NLP. |
| `canonical_text` | MEDIUMTEXT | YES | | **Best/merged OCR text** for this work. Selected from all occurrences after Stage 3 deduplication. This is the "authoritative" version published to the wiki. |
| `canonical_text_source` | VARCHAR(255) | YES | | **Which occurrence provided the canonical text.** References an occurrence ID or container/issue combo for traceability. Helps identify if text was corrected or merged from multiple sources. |
| `word_count` | INT(11) | YES | | **Word count** of canonical text. Used for statistics and search. |
| `has_images` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 if this work has associated images (illustrations, photographs, diagrams). |
| `image_count` | INT(11) | YES | | **Number of images** associated with this work. Helps track what to publish. |
| `text_quality_score` | DECIMAL(3,2) | YES | | **Overall text quality (0.00–1.00)** based on OCR confidence and manual review. High score = high quality. Used for sorting and filtering. |
| `completeness_score` | DECIMAL(3,2) | YES | | **Completeness (0.00–1.00)** indicating how much of the original work is captured. 1.0 = complete; 0.7 = some pages/sections missing. |
| `first_occurrence_date` | DATE | YES | | **Earliest known publication date.** For an article that appears in Jan 1890 and is reprinted in Feb 1890, this is Jan 1890. Used to identify the "original" publication. |
| `occurrence_count` | INT(11) | NO | | **Number of occurrences** of this work across issues/editions. For unique articles, typically 1. For ads or reprints, may be higher. |
| `dedup_fingerprint` | CHAR(64) | YES | | **SHA-256 fingerprint** of the canonical text (or a normalized version thereof). Used for duplicate detection: if two works have the same fingerprint, they're duplicates. |
| `dedup_status` | ENUM('pending', 'unique', 'duplicate_of', 'canonical') | NO | | **Deduplication status.** `pending` = not yet checked; `unique` = is not a duplicate; `duplicate_of` = this is a duplicate (see `canonical_work_id`); `canonical` = is the canonical version others link to. |
| `canonical_work_id` | INT(10) UNSIGNED | YES | FK (self) | **Self-referencing foreign key.** If `dedup_status = 'duplicate_of'`, this points to the canonical `work_id`. If `dedup_status = 'canonical'`, this is NULL (or self-references). Used to consolidate duplicates. |
| `notes` | TEXT | YES | | **Editorial notes.** May document merges, manual corrections, or QA findings. |
| `created_at` | DATETIME | NO | | Timestamp when inserted. |
| `updated_at` | DATETIME | NO | | Timestamp of last update. |

**Indexes:**
- PRIMARY: `work_id`
- SIMPLE: `work_type`, `dedup_status`, `canonical_work_id`
- COMPOSITE: `title(255)` (for title-based search)
- FULLTEXT: `canonical_text` (for content search)

**Examples:**

```sql
INSERT INTO works_t
  (work_type, title, author, canonical_text, text_quality_score, occurrence_count, dedup_status)
VALUES
  ('article', 'Architectural Progress in the Cities', 'John Smith', 
   'Recent developments in urban architecture...', 0.94, 1, 'canonical'),
  ('advertisement', 'ACME Marble Company', NULL, 
   'Superior marble for your architectural projects...', 0.88, 12, 'canonical');
```

---

### 8. `work_occurrences_t`

**Purpose:** Records each appearance of a work (article, ad, chapter) within a specific issue/edition and container.

| Column | Type | Nullable | Key | Description |
|--------|------|----------|-----|-------------|
| `occurrence_id` | INT(10) UNSIGNED | NO | PK, AI | Unique identifier. |
| `work_id` | INT(10) UNSIGNED | NO | FK | **Foreign key** to `works_t`. Which work this is an instance of. |
| `issue_id` | INT(10) UNSIGNED | NO | FK | **Foreign key** to `issues_t`. Which issue/edition this occurrence is in. |
| `container_id` | INT(10) UNSIGNED | NO | FK | **Foreign key** to `containers_t`. Which source container it comes from. |
| `start_page_id` | INT(10) UNSIGNED | YES | FK | **Foreign key** to `pages_t`. First page of this occurrence. |
| `end_page_id` | INT(10) UNSIGNED | YES | FK | **Foreign key** to `pages_t`. Last page of this occurrence. |
| `page_range_label` | VARCHAR(64) | YES | | **Human-readable page range.** Example: `"pp. 15–23"` or `"pages 15-23"`. Useful for citation and display. |
| `title_variant` | VARCHAR(512) | YES | | **Title as it appears in this specific occurrence.** May differ slightly from `works_t.title` due to OCR variations, formatting, or intentional changes (e.g., short title vs. full title). |
| `ocr_text` | MEDIUMTEXT | YES | | **OCR text specific to this occurrence.** The raw extraction from this issue's pages before merging into canonical. Stored for comparison and if canonical text needs to be revisited. |
| `ocr_quality_score` | DECIMAL(3,2) | YES | | **OCR quality (0.00–1.00)** for this specific occurrence. Used to help decide which occurrence is most canonical. |
| `is_canonical` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 if this is the occurrence chosen as the canonical/authoritative source. Exactly one occurrence per work (or maybe none if canonical was manually created) should have this flag set. |
| `text_similarity_to_canonical` | DECIMAL(3,2) | YES | | **Similarity score (0.00–1.00)** comparing this occurrence's text to the canonical text.** 1.0 = identical; 0.8 = very similar (maybe a few OCR differences); 0.5 = significantly different (reprint with edits?). Helps validate deduplication. |
| `has_images` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 if this occurrence has images. |
| `image_references` | TEXT | YES | | **JSON array or list of image file paths/IDs** associated with this occurrence. Example: `["/images/page_15_fig_1.jpg", "/images/page_16_fig_2.jpg"]`. |
| `notes` | TEXT | YES | | **Operational notes.** May document why this occurrence was or wasn't chosen as canonical, or note variants. |
| `created_at` | DATETIME | NO | | Timestamp when inserted. |
| `updated_at` | DATETIME | NO | | Timestamp of last update. |

**Indexes:**
- PRIMARY: `occurrence_id`
- UNIQUE: `(work_id, issue_id, start_page_id)` (prevent duplicate occurrence records)
- SIMPLE: `work_id`, `issue_id`, `container_id`, `is_canonical`

**Examples:**

```sql
INSERT INTO work_occurrences_t
  (work_id, issue_id, container_id, start_page_id, end_page_id, 
   page_range_label, ocr_text, ocr_quality_score, is_canonical)
VALUES
  (1, 1, 1, 2, 4, 'pp. 1–3', 'ARCHITECTURAL PROGRESS...', 0.94, 1),
  (2, 1, 1, 5, 5, 'p. 4', 'ACME Marble Company...', 0.88, 1);
```

---

### 9. `processing_status_t`

**Purpose:** Tracks which processing stages have been completed for each container, and records errors if any.

| Column | Type | Nullable | Key | Description |
|--------|------|----------|-----|-------------|
| `status_id` | INT(10) UNSIGNED | NO | PK, AI | Unique identifier. |
| `container_id` | INT(10) UNSIGNED | NO | FK | **Foreign key** to `containers_t` (1:1 relationship). |
| `stage1_ingestion_complete` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 when Stage 1 (download & validation) is done. |
| `stage1_completed_at` | DATETIME | YES | | **Timestamp** when Stage 1 completed. |
| `stage2_ocr_complete` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 when Stage 2 OCR is done. |
| `stage2_completed_at` | DATETIME | YES | | **Timestamp** when Stage 2 OCR completed. |
| `stage2_segmentation_complete` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 when segmentation (same stage) is done. |
| `stage2_segmentation_at` | DATETIME | YES | | **Timestamp** when segmentation completed. |
| `stage3_canonicalization_complete` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 when Stage 3 (deduplication, canonical selection) is done. |
| `stage3_completed_at` | DATETIME | YES | | **Timestamp** when Stage 3 completed. |
| `stage4_publication_complete` | TINYINT(1) | NO | | **Boolean flag.** Set to 1 when Stage 4 (export to wiki) is done. |
| `stage4_completed_at` | DATETIME | YES | | **Timestamp** when Stage 4 completed. |
| `pipeline_status` | ENUM('pending', 'in_progress', 'complete', 'failed', 'skipped') | NO | | **Overall pipeline status.** `pending` = not yet started; `in_progress` = currently processing; `complete` = all stages done; `failed` = error encountered (check `last_error_*`); `skipped` = intentionally not processed. |
| `last_error_stage` | VARCHAR(32) | YES | | **Which stage had the last error.** Example: `"stage2_ocr"`. NULL if no error. |
| `last_error_message` | TEXT | YES | | **Error message or stack trace.** Helps debugging. |
| `last_error_at` | DATETIME | YES | | **Timestamp** when last error occurred. |
| `retry_count` | INT(11) | NO | | **Number of retries** attempted for this container. Incremented each time a failed task is retried. |
| `updated_at` | DATETIME | NO | | Timestamp of last update. |

**Examples:**

```sql
INSERT INTO processing_status_t
  (container_id, stage1_ingestion_complete, stage2_ocr_complete, pipeline_status)
VALUES
  (1, 1, 1, 'in_progress');

UPDATE processing_status_t
SET stage3_canonicalization_complete = 1, 
    stage3_completed_at = NOW(),
    pipeline_status = 'complete'
WHERE container_id = 1;
```

---

### 10. `schema_version_t`

**Purpose:** Tracks database migrations to ensure code and schema stay in sync.

| Column | Type | Nullable | Key | Description |
|--------|------|----------|-----|-------------|
| `version_id` | INT(10) UNSIGNED | NO | PK, AI | Unique identifier. |
| `version_number` | INT(11) | NO | UNIQUE | **Migration version number.** Typically 1, 2, 3, etc. Incremented with each schema change. |
| `migration_name` | VARCHAR(255) | NO | | **Descriptive name** of the migration. Example: `"001_initial_schema"`, `"002_add_dedup_fields"`. |
| `applied_at` | DATETIME | NO | | **Timestamp** when migration was applied. |

**Example:**

```sql
INSERT INTO schema_version_t (version_number, migration_name, applied_at)
VALUES (1, '001_initial_schema', '2026-01-20 10:51:21');
```

---

### 11. `task_executions_t`

**Purpose:** Log of watcher task executions for monitoring and debugging.

| Column | Type | Nullable | Key | Description |
|--------|------|----------|-----|-------------|
| `execution_id` | INT(10) UNSIGNED | NO | PK, AI | Unique identifier. |
| `task_id` | VARCHAR(255) | NO | | **Task ID** from the flag file (e.g., `"20260119-211500-ocr-sim_architect_1890Jan"`). |
| `task_type` | VARCHAR(64) | NO | | **Type of task** (e.g., `"download"`, `"ocr"`, `"export"`). |
| `watcher_id` | VARCHAR(64) | NO | | **ID of the watcher** that executed it. Helps identify if OrionMX or OrionMega. |
| `hostname` | VARCHAR(128) | YES | | **Hostname** of the executing machine. |
| `status` | ENUM('completed', 'failed') | YES | | **Final status** of execution. |
| `started_utc` | DATETIME | YES | | **Execution start time (UTC).** |
| `ended_utc` | DATETIME | YES | | **Execution end time (UTC).** |
| `duration_seconds` | INT(10) UNSIGNED | YES | | **Duration in seconds.** |
| `exit_code` | INT(11) | YES | | **Exit code** (0 = success, non-zero = error). |
| `error_type` | VARCHAR(128) | YES | | **Error type** (e.g., `"FileNotFoundError"`, `"TimeoutError"`). |
| `error_message` | TEXT | YES | | **Error message/stack trace.** |
| `outputs` | JSON | YES | | **Task output** as JSON. May include file paths, counts, etc. |
| `metrics` | JSON | YES | | **Performance metrics** as JSON (e.g., `{"pages_processed": 24, "avg_ocr_confidence": 0.92}`). |
| `created_at` | DATETIME | NO | | Timestamp when record created. |

---

## Data Integrity Rules

### Foreign Key Constraints

All foreign keys are defined with `ON DELETE CASCADE` or `ON DELETE SET NULL` as appropriate:

- **Cascading deletes:** If a family is deleted, all titles, issues, containers under it are deleted.
- **Set NULL:** If a title is deleted, issues linked to it have `title_id` set to NULL (they can be re-linked or deleted manually).

### Unique Constraints

1. **`publication_families_t.family_root`** — No two families can have the same `family_root`.
2. **`containers_t.(source_system, source_identifier)`** — No duplicate source files for the same system.
3. **`issues_t.canonical_issue_key`** — No duplicate logical issues (deduplication).
4. **`work_occurrences_t.(work_id, issue_id, start_page_id)`** — No duplicate occurrence records.

### Validation Rules

1. **Date ranges:** For all date fields, `start_date ≤ end_date` (if both present).
2. **Page numbers:** `page_index` should be sequential within a container (gaps allowed but unusual).
3. **Deduplication:** A work with `dedup_status = 'duplicate_of'` must have `canonical_work_id != NULL` and `canonical_work_id != work_id`.
4. **Canonical occurrence:** A work should have exactly 0 or 1 occurrence with `is_canonical = 1`.
5. **Scores:** All score fields (0.00–1.00) must be DECIMAL(3,2) with constraints 0 ≤ score ≤ 1.

---

## Common Queries

### Find all issues in a publication family

```sql
SELECT i.* 
FROM issues_t i
WHERE i.family_id = (SELECT family_id FROM publication_families_t 
                      WHERE family_root = 'American_Architect_family')
ORDER BY i.year_published, i.volume_sort, i.issue_sort;
```

### Find all works in an issue

```sql
SELECT w.*, occ.page_range_label
FROM works_t w
JOIN work_occurrences_t occ ON w.work_id = occ.work_id
WHERE occ.issue_id = ?
ORDER BY occ.start_page_id;
```

### Find duplicate works (same work in multiple issues)

```sql
SELECT w.work_id, w.title, COUNT(occ.occurrence_id) as occurrence_count
FROM works_t w
JOIN work_occurrences_t occ ON w.work_id = occ.work_id
WHERE w.dedup_status = 'canonical'
GROUP BY w.work_id
HAVING occurrence_count > 1
ORDER BY occurrence_count DESC;
```

### Find works with poor OCR quality

```sql
SELECT w.work_id, w.title, AVG(occ.ocr_quality_score) as avg_quality
FROM works_t w
JOIN work_occurrences_t occ ON w.work_id = occ.work_id
GROUP BY w.work_id
HAVING avg_quality < 0.70
ORDER BY avg_quality ASC;
```

### Find containers pending download

```sql
SELECT c.container_id, c.source_system, c.source_identifier, c.source_url
FROM containers_t c
WHERE c.download_status = 'pending'
ORDER BY c.created_at;
```

### Find issues with multiple source containers (potential duplicates)

```sql
SELECT i.issue_id, i.year_published, i.volume_label, i.issue_label, 
       COUNT(ic.container_id) as container_count
FROM issues_t i
JOIN issue_containers_t ic ON i.issue_id = ic.issue_id
GROUP BY i.issue_id
HAVING container_count > 1
ORDER BY i.year_published DESC;
```

### Full-text search: find articles mentioning "bridge design"

```sql
SELECT w.work_id, w.title, w.author, MATCH(w.canonical_text) AGAINST('bridge design') as relevance
FROM works_t w
WHERE MATCH(w.canonical_text) AGAINST('bridge design' IN BOOLEAN MODE)
ORDER BY relevance DESC;
```

---

## Operational Notes

### Denormalization Strategy

Several fields are **intentionally denormalized** to improve query performance and reduce complex JOINs:

- **`issues_t.family_id`** — Copied from `publication_titles_t.family_id`. Avoids JOIN through titles when you want to filter by family.
- **`containers_t.family_id`** and **`containers_t.title_id`** — Allows direct linking of sources without always going through issues.
- **`pages_t.issue_id`** — Helps with page queries filtered by issue without needing `issue_containers_t`.

### Handling Multi-Volume Books

For a book with 2 volumes (e.g., a 2-volume set from 1890):

1. Create ONE `issues_t` record with `is_book_edition = 1` (e.g., volume = "1-2" or "Complete edition").
2. Create TWO `containers_t` records, one for each physical volume scan.
3. Create TWO `issue_containers_t` mappings (both containers link to the single issue).
4. When creating `pages_t`, mark `container_id` correctly so pages are grouped by volume.
5. When storing works (chapters), occurrences will reference the same issue but different containers/pages.

### Handling Reprints & Serials

For a work that appears in multiple issues (e.g., a multi-part article or advertisement):

1. Create ONE `works_t` record.
2. Create multiple `work_occurrences_t` records, one per issue.
3. Mark the highest-quality occurrence as `is_canonical = 1`.
4. Ensure `occurrence_count` in `works_t` matches the number of occurrences.

### Processing Pipeline States

The `processing_status_t` table drives automation:

- **Stage 1 (Ingestion):** Container downloaded, validated, files located in Raw_Input.
- **Stage 2 (OCR & Segmentation):** Pages extracted, OCR performed, Works created, Occurrences mapped.
- **Stage 3 (Canonicalization):** Duplicates identified, canonical versions selected, Reference files prepared.
- **Stage 4 (Publication):** Wiki pages generated and uploaded, MediaWiki database updated.

A watcher task queries containers with `stage1_ingestion_complete = 1` and `stage2_ocr_complete = 0` to find the next batch to process.

### Handling Multi-Issue Containers

A **multi-issue container** is a single physical file (PDF, image archive, bound volume scan) that contains multiple journal issues or book sections. This is common in historical archival sources.

#### Common Scenarios

1. **Bound Volume with Multiple Issues:** A single PDF or image set containing 4-6 monthly issues of a journal, bound together physically.
   - Example: American Architect Vol 27 (Jan-Apr 1890) as one IA item with ~96 pages covering 4 issues
   
2. **Supplementary Pages Separated:** The last issue of a volume contains advertising/trade supplement pages for all issues in that volume, physically separated from the main content.
   - Example: American Architect Vol 27 Issue 4 has main pages 1-20, then pages 21-96 contain trade supplements indexed by issue

3. **Index or Cross-Reference Sections:** An index covering an entire volume, appended to the final issue.

#### Detection & Registration Strategy

**Manual Review Approach:**
- Examine the container's metadata (IA scandata.xml, METS files, PDF bookmarks)
- Review marginal markings, headers, and page breaks to identify issue boundaries
- Look for dates, issue numbers, or table of contents indicators
- Document findings in `containers_t.notes`

**Database Registration:**
Do **not** split the physical container. Instead:
1. Create one `containers_t` record representing the physical source
2. Create individual `issues_t` records for each logical issue within the container
3. Use `issue_containers_t` to map each issue to its page range within the container
4. Set `start_page_in_container` and `end_page_in_container` to define where each issue begins/ends

#### Example: American Architect Vol 27 (Jan-Apr 1890)

**Container Registration:**
```sql
-- One physical container
INSERT INTO containers_t
  (source_system, source_identifier, source_url, family_id, container_label, 
   container_type, total_pages, date_start, date_end, notes)
VALUES
  ('ia', 'loc_booksandmags_14093893', 'https://archive.org/details/amarch_v27_1890_01', 
   1, 'American Architect Vol 27 1890 Jan-Apr', 'bound_volume', 96, 
   '1890-01-01', '1890-04-30',
   'Bound volume containing 4 monthly issues. Page 1-24: Jan issue. Pages 25-48: Feb issue. Pages 49-72: Mar issue. Pages 73-96: Apr issue.');
```

**Issue Registration:**
```sql
-- Four separate issues
INSERT INTO issues_t
  (title_id, family_id, volume_label, volume_sort, issue_label, issue_sort, issue_date_start, year_published, canonical_issue_key)
VALUES
  (1, 1, '27', 27, '793', 793, '1890-01-10', 1890, 'AMER_ARCH_27_793_1890'),
  (1, 1, '27', 27, '794', 794, '1890-01-17', 1890, 'AMER_ARCH_27_794_1890'),
  (1, 1, '27', 27, '795', 795, '1890-02-07', 1890, 'AMER_ARCH_27_795_1890'),
  (1, 1, '27', 27, '796', 796, '1890-03-07', 1890, 'AMER_ARCH_27_796_1890');
```

**Mapping Issues to Container:**
```sql
-- Map each issue to its page range in the container
INSERT INTO issue_containers_t
  (issue_id, container_id, start_page_in_container, end_page_in_container, is_preferred, is_complete, ocr_quality_score)
VALUES
  (1, 1, 1, 24, 1, 1, 0.92),   -- Jan issue
  (2, 1, 25, 48, 1, 1, 0.91),  -- Feb issue
  (3, 1, 49, 72, 1, 1, 0.90),  -- Mar issue
  (4, 1, 73, 96, 1, 1, 0.89);  -- Apr issue
```

#### Handling Separated Supplements

For cases where supplement pages are physically separated but logically belong to specific issues:

**Option 1: Register as Part of the Main Container**
If supplements are physically appended to the last issue but belong to all issues:
- Keep the entire container as one unit
- Map the main content pages to issues normally
- Add notes in `issues_t.notes` documenting supplement location
- Add notes in `issue_containers_t.coverage_notes` for the final issue noting "Includes trade supplements for entire volume, pages X-Y"

**Option 2: Create a Secondary Container for Supplements Only**
If supplements are truly separate and might be processed differently:
```sql
-- Secondary container for supplements
INSERT INTO containers_t
  (source_system, source_identifier, source_url, family_id, container_label, 
   container_type, total_pages, notes)
VALUES
  ('ia', 'loc_booksandmags_14093893_supplements', 
   'https://archive.org/details/amarch_v27_1890_01', 
   1, 'American Architect Vol 27 Trade Supplements', 'supplement_archive', 76,
   'Advertising/trade supplements extracted from final issue of volume. Contains indices for all 4 issues of volume 27.');
```

Then create mappings to associate supplements with each issue:
```sql
-- Map each issue to its corresponding supplement pages
INSERT INTO issue_containers_t
  (issue_id, container_id, start_page_in_container, end_page_in_container, is_preferred, coverage_notes)
VALUES
  (1, 2, 1, 18, 0, 'Trade supplement pages for Jan issue (Jan Architects)'),
  (2, 2, 19, 35, 0, 'Trade supplement pages for Feb issue'),
  (3, 2, 36, 52, 0, 'Trade supplement pages for Mar issue'),
  (4, 2, 53, 76, 0, 'Trade supplement pages for Apr issue + volume index');
```

#### Processing Implications

- **Stage 1 (Ingestion):** Register all issues and map to page ranges in `issue_containers_t`
- **Stage 2 (OCR & Segmentation):** Process container once; use page mappings to extract per-issue content
- **Stage 3 (Canonicalization):** Works are segmented per issue and deduplicated normally
- **Stage 4 (Publication):** Each issue publishes independently; supplement pages can be re-associated with their parent issues

#### Key Principles

1. **One Physical Container = One `containers_t` Record**
   - Don't split the source file
   - Keep metadata at container level

2. **Multiple Issues = Multiple `issues_t` Records**
   - Create separate logical records for each issue
   - Each issue gets its own metadata and dates

3. **Page Ranges = `issue_containers_t` Mappings**
   - Use `start_page_in_container` and `end_page_in_container` to define boundaries
   - This is the critical link between physical and logical organization

4. **Supplements = Optional Secondary Container**
   - Only if they warrant separate processing or storage
   - Otherwise, keep together and document in notes

5. **Documentation = `notes` Fields**
   - Record how you identified issue boundaries
   - Document any assumptions or uncertainties
   - Note unusual structures (e.g., "supplements at end", "partial issue")

#### Notes During Manual Review

When you manually review a multi-issue container, document in `containers_t.notes`:

```
Page breaks and headers identified:
- Pages 1-24: Issue 793 (Vol 27, Jan 10, 1890) - marked "793" at header
- Pages 25-48: Issue 794 (Vol 27, Jan 17, 1890) - marked "794" at header
- Pages 49-72: Issue 795 (Vol 27, Feb 7, 1890) - marked "795" at header
- Pages 73-96: Issue 796 (Vol 27, Mar 7, 1890) - marked "796" at header
- Supplements: None in this container
```

This creates a clear audit trail for future reference and helps during Stage 2 processing when extracting pages by issue.

### Error Recovery

When a task fails:

1. Update `processing_status_t.last_error_stage`, `last_error_message`, `last_error_at`.
2. Set `pipeline_status = 'failed'`.
3. Increment `retry_count`.
4. The operator reviews the error and decides:
   - **Retry**: Re-enqueue task; system will try again (up to max retries).
   - **Manual fix**: Fix underlying issue (e.g., re-download, correct metadata), then retry.
   - **Skip**: Set `pipeline_status = 'skipped'` and move on.

---

## Example: Complete Workflow

### Scenario: Ingest "American Architect Vol 27 Jan 1890"

**Step 1: Family exists**
```sql
-- family_id = 1, family_root = 'American_Architect_family'
```

**Step 2: Create title** (if new)
```sql
INSERT INTO publication_titles_t 
VALUES (NEW_ID, 1, 'The American Architect and Building News', ..., 1);
```

**Step 3: Create issue**
```sql
INSERT INTO issues_t
VALUES (NEW_ID, title_id, 1, '27', 27, '793', 793, NULL, NULL, NULL,
        '1890-01-10', '1890-01-10', 1890, 0, 0, 0, ..., 'AMER_ARCH_27_793_1890');
```

**Step 4: Create container** (from IA)
```sql
INSERT INTO containers_t
VALUES (NEW_ID, 'ia', 'loc_booksandmags_14093893', 'https://...', 1, NULL, 
        'American Architect Vol 27...', 'image_archive', '27', '1890-01-01', '1890-04-30', 96,
        1, 1, 1, 0, 0, 1, 1, '/Raw_Input/.../loc_booksandmags_14093893', NULL, NULL,
        'complete', 'passed', NOW(), NOW(), NULL, NOW(), NOW());
```

**Step 5: Map issue to container**
```sql
INSERT INTO issue_containers_t
VALUES (NEW_ID, issue_id, container_id, 1, 96, 1, 1, 0.92, NULL, NOW());
```

**Step 6: Create pages** (loop through JP2 files)
```sql
INSERT INTO pages_t
VALUES (NEW_ID, container_id, issue_id, 0, 'Cover', 'Cover', 'cover', 1, 0, 0, 0, 
        1, 'ia_hocr', 0.95, 150, 'text...', 2550, 3300, 300, 'sha256...', 
        '/path/to/page_0.jpg', '/path/to/page_0.hocr', NULL, NOW(), NOW());
-- repeat for pages 1, 2, ..., 95
```

**Step 7: Create works** (after segmentation in Stage 2)
```sql
INSERT INTO works_t
VALUES (NEW_ID, 'article', 'Architectural Progress in the Cities', NULL, 'John Smith', 
        NULL, 'Architecture', NULL, 'text...', 'container_1', 1200, 0, 0, 0.94, 1.00,
        '1890-01-10', 1, NULL, 'canonical', NULL, NULL, NOW(), NOW());
```

**Step 8: Create occurrences** (link works to issue/pages)
```sql
INSERT INTO work_occurrences_t
VALUES (NEW_ID, work_id, issue_id, container_id, start_page_id, end_page_id, 'pp. 1–3',
        'Architectural Progress...', 'text...', 0.94, 1, 1.00, 0, NULL, NULL, NOW(), NOW());
```

**Step 9: Mark processing complete**
```sql
UPDATE processing_status_t
SET stage1_ingestion_complete = 1, stage1_completed_at = NOW(),
    stage2_ocr_complete = 1, stage2_completed_at = NOW(),
    stage3_canonicalization_complete = 1, stage3_completed_at = NOW(),
    stage4_publication_complete = 1, stage4_completed_at = NOW(),
    pipeline_status = 'complete'
WHERE container_id = container_id;
```

---

## Glossary

| Term | Definition |
|------|-----------|
| **Family** | Top-level grouping of publications (journals, book series, single books). |
| **Title** | Specific name variant of a publication (journal title changed names; book has editions). |
| **Issue/Edition** | Individual journal issue or book edition. Logical publishing unit. |
| **Container** | Physical source file or archive (PDF, JP2 bundle, etc.) from external source. |
| **Page** | Individual page within a container. Has OCR text and metadata. |
| **Work** | Unique intellectual content (article, chapter, advertisement, etc.). |
| **Occurrence** | Specific appearance of a Work within an Issue/Container. Same work = multiple occurrences. |
| **Canonical** | Authoritative/best version selected during Stage 3 deduplication. |
| **Deduplication** | Process of identifying and consolidating identical works. |

---

**End of Document**

---

**Document Version History:**
- v1.0 (2026-01-23): Initial comprehensive schema reference with all fields, examples, and operational guidance.

