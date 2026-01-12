# HJB Ingestion Policy  
**Stage 1 – Source Acquisition & Canonicalization**

**Project:** Historical Journals & Books (HJB)  
**Applies to:** Stage 1 (Raw / Research Inputs layer)  
**Status:** Draft (intended to stabilize early)  
**Owner:** Michael  

---

## 1. Purpose and Scope

This document defines the **authoritative rules** governing how source materials are acquired, placed, and recorded during **Stage 1 (Ingestion)** of the HJB pipeline.

It answers:

- What files are worth ingesting
- In what order and priority
- Where they are placed on disk
- What guarantees ingestion must provide
- What ingestion explicitly does *not* do

This policy applies to **all sources**, including:
- Internet Archive (IA)
- Local scans
- Institutional or third-party datasets
- Pre-existing files already on disk

Pre-existing files are treated as **new acquisitions** for the purposes of ingestion.

---

## 2. Guiding Principle (Non-Negotiable)

> **For each publication issue (IA identifier or equivalent), the goal is:**
>
> - **One visual ground truth**
> - **One best OCR ground truth**
> - **One authoritative page map**
>
> Everything else is temporary, redundant, or for human convenience.

Storage is cheap until it isn’t.  
The system is designed to **dedupe hard, keep only the best, and delete the rest once canonical outputs exist**.

---

## 3. Canonical File Tiers

### Tier 0 — Mandatory (Corpus does not exist without these)

These are required for an issue to be considered ingested.

#### 1. Page images (visual truth)
- **IA:** `*_jp2.zip`
- **Non-IA:** TIFF / PNG / JP2 page sets, or equivalent lossless images

**Why:**  
Pixel-accurate page images are the foundation for:
- segmentation (articles, ads, figures),
- image deduplication (ads, plates),
- fallback OCR,
- future ML work.

#### 2. Page-aware OCR text (text truth)
- **IA:** `*_djvu.xml`
- **Non-IA:** ALTO XML or equivalent structured OCR

**Why:**  
Plain text is insufficient. Page boundaries and reading order must be preserved.

#### 3. Page map / structural metadata
- **IA:** `*_scandata.xml`
- **Non-IA:** METS, ALTO structure maps, or equivalent pagination metadata

**Why:**  
This is the “spine” that reconciles:
- missing or extra pages,
- foldouts,
- front matter,
- mismatched OCR vs images.

---

### Tier 1 — Strongly Recommended

These improve validation, debugging, and human usability.

- **Reference PDF** (`*.pdf`, `*_text.pdf`, etc.)
- **HOCR** (`*_hocr.html`)

**Important:**  
PDFs and HOCR are **not canonical processing inputs**. They are support artifacts.

---

### Tier 2 — Fallback / Convenience

Used only when Tier 0 assets are missing or broken.

- `*_djvu.txt`
- IA `*_meta.json` or similar metadata blobs

---

## 4. Internet Archive (IA) Ingestion Rules

### 4.1 Required IA Files (in priority order)

For each IA identifier:

1. `*_jp2.zip`
2. `*_djvu.xml`
3. `*_scandata.xml`
4. PDF (optional but recommended)
5. HOCR (optional)

If only three files can be retrieved, they **must** be the first three.

---

### 4.2 IA Folder Placement (Operational Contract)

All IA acquisitions live under:
```
\\RaneyHQ\Michael\01_Research\Historical_Journals_Inputs\
  0110_Internet_Archive\
``` 

#### SIM collection layout (authoritative): 
``` 
SIM/
  <safe_family>/
    <YYYY>/
       <IAIdentifier>/
         <raw IA files>
``` 
- `<safe_family>` is resolved via mapping (see §6)
- `<YYYY>` is derived from identifier when parseable
- Fallback year bucket: `_unknown_year`
- Unmapped identifiers go to:
```
SIM/_unmapped/<IAIdentifier>/
```
- No files are ever modified in place after ingestion.

---

## 4.3 Pre-Existing Files on Disk

Files that already exist on local or NAS storage **must still pass through the ingestion process**.

Rules:

- Source files are selected explicitly (by identifier, path, or manifest), not assumed valid by location alone.
- Pre-existing IA files are treated **as if freshly downloaded from archive.org**.
- The same tier rules, validation checks, and placement logic apply.
- Files are copied or relocated into the canonical Inputs structure if needed.
- Provenance must indicate the true origin (e.g., “pre-existing local copy of IA item”).

Rationale:

- Ensures uniform handling of historical and newly acquired material.
- Prevents “special-case” pipelines that diverge from canonical rules.
- Allows legacy holdings to be validated, normalized, and deduplicated correctly.


---

## 5. Non-IA Sources (Local, Institutional, External)

### 5.1 Priority Rules 

Non-IA sources are evaluated using the same truth hierarchy: 
1. **High-fidelity page images**
2. **Page-aware OCR**
3. **Page maps**

A high-quality image-based PDF may be used **only when page images do not exist**, and must be rendered deterministically if converted. 

### 5.2 Folder Placement 

Non-IA sources live under their own top-level buckets: 
```
0120_USModernist/ 
0130_Local_Scans/
0140_External_Datasets/
``` 

Sub-structure may mirror IA conventions where appropriate but is not required to match exactly. 

--- 

## 6. Journal Family Resolution 

### 6.1 Purpose 

Family grouping exists to: 
- prevent directories with thousands of siblings,
- support human navigation,
- align with downstream “Work” consolidation.

### 6.2 Resolution Order 

When ingesting IA/SIM items: 
1. Explicit family override in manifest (rare)
2. Pattern match via mapping file (`config/ia_family_map.*`)
3. Fallback to `_unmapped`

Family resolution must be **deterministic and auditable**.
  
---

## 7. MySQL Integration Model (Stage 1)

### Option B (Selected)

- Ingestion **does not write to MySQL directly**
- Ingestion emits **structured result JSON**
- A follow-on task performs:
  - DB upserts
  - retries
  - reconciliation

**Rationale:** 
Ingestion must succeed even when DB connectivity is unavailable (remote work, travel, outages). 

--- 

## 8. Guarantees Provided by Ingestion 

When an ingestion task succeeds: 
- Files are placed in the correct Inputs location
- Files are unmodified from source
- Placement is deterministic and repeatable
- Provenance can be reconstructed
- Results are machine-readable (JSON)

--- 

## 9. Explicit Non-Goals of Ingestion 

Stage 1 ingestion does **not**: 
- OCR or re-OCR content
- Deduplicate across sources
- Decide canonical text/image beyond Tier classification
- Modify or normalize files
- Populate MediaWiki
- Perform page segmentation

Those belong to later stages. 

--- 

## 10. Relationship to Blueprint v2.4 
This document is a **binding interpretation** of: 
- Blueprint v2.4 §4.2 (Stage 1: Research Inputs)
- Blueprint storage philosophy (“raw is immutable”)
- Blueprint separation of Raw vs Working layers

If a conflict is discovered: 
- Blueprint defines *intent*
- This document defines *execution*

--- 

### End of Document
