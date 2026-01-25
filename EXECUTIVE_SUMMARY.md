# Hybrid Schema Decision - Executive Summary

**Status:** Architectural decision required before Stage 2b segmentation  
**Decision Owner:** Michael Raney  
**Analysis Requested:** Claude Thinking or Opus 4.5  
**Timeline:** Decision needed by EOD Friday to proceed Monday

---

## The Core Decision

**Question:** Should we use a **hybrid architecture** (database + filesystem page packs) instead of **pure database** approach for OCR and images in Stage 2?

**Current state:** Pure DB. Storing OCR text blobs in `pages_t`, not extracting images, no page packs.

**Proposed state:** Hybrid. Lightweight DB (metadata + pointers); full OCR payloads + extracted images in filesystem bundles (page packs).

---

## Why Now?

**Issue discovered:** We need to link images to works, but:
- No plan for extracting JP2s
- No way to store/reference images
- No way to do reproducible/auditable segmentation
- No way to do A/B testing

**Classic problem:** Building tight coupling (text in DB) when we should build loose coupling (files on filesystem, DB as index).

---

## Proposed Solution (One-Page)

### What Changes

**Database:**
- Create `page_assets_t`: pointers to OCR files + image files (+ hashes for auditing)
- Create `page_pack_manifests_t`: documents what's in each page pack (auditability)
- Modify `pages_t`: remove MEDIUMTEXT blob; add lightweight snippet + spread tracking
- Modify `work_occurrences_t`: populate `image_references` with extracted image paths

**Filesystem (NAS):**
- Extract JP2s → JPEG, store in `0220_Page_Packs/[container_id]/images/`
- Copy OCR payloads → `0220_Page_Packs/[container_id]/ocr/`
- Generate manifest → `0220_Page_Packs/[container_id]/manifest.json`

**Scripts:**
- Refactor `extract_pages_from_containers.py`: extract images + create page packs + populate `page_assets_t`
- Build new `segment_from_page_packs.py`: reads page packs (not DB), outputs work boundaries + image references

### Key Benefits

| Benefit | Why It Matters |
|---------|----------------|
| **Rich OCR data** | DjVu XML has coordinates, confidence. Enables layout-aware segmentation. |
| **Images linked to works** | Can extract image references from page packs → populate `work_occurrences_t.image_references`. Wiki can fetch images. |
| **Reproducible** | Manifest documents exact inputs for each segmentation run. Can reproduce/audit. |
| **A/B testable** | Create alternate page pack (different OCR source) without touching DB. Compare outputs cleanly. |
| **Manual QA natural** | Page pack = self-contained issue bundle. Operator can review images + boundaries together. |
| **DB stays lean** | Pointers + metadata only. Heavy files on NAS with fast local I/O. |

### Key Costs

| Cost | Magnitude | Mitigated By |
|------|-----------|--------------|
| **Schema changes** | 3 new/modified tables | Well-defined migrations; backward compatible |
| **Extract time** | ~90 min for 53 containers | One-time cost; parallelizable |
| **Filesystem overhead** | ~1 GB for page packs | Acceptable; NAS has TB capacity |
| **Code refactoring** | Rewrite stage 2a/2b scripts | Clear specification; should be ~300-400 LOC |

---

## Critical Questions for Analysis

When you review this, please address:

1. **Schema correctness:** Are the three new/modified tables sufficient? Missing anything?

2. **Manifest design:** Is the JSON structure right? Too verbose? Missing fields?

3. **Image format:** JPEG at quality 90, 300 DPI—good choice? Or optimize differently?

4. **Segmentation interface:** Should `segment_from_page_packs.py` read files or pull from DB? Trade-offs?

5. **Operator workflow:** How to make manual QA (marking spreads, fixing boundaries) smooth? Need UI tool?

6. **Extensibility:** Does this support future ML (ad fingerprinting, text similarity, layout classification)?

7. **Storage footprint:** ~1 GB for 1,200 page packs acceptable? Or need compression strategy?

8. **Alternative considered:** Would anything simpler work? (e.g., keep text in DB, just extract images separately?)

---

## Implementation Roadmap

```
Week of Jan 27:
├─ Mon: Get decision + feedback from analysis
├─ Tue-Wed: Apply schema migrations + refactor scripts
├─ Thu: Backfill containers 1-53 (one-time data setup)
└─ Fri: Build segmentation script

Week of Feb 3:
├─ Mon-Tue: Test segmentation on Container 1 (Issue 1)
├─ Wed: Operator manual QA on Container 1
├─ Thu-Fri: Scale to containers 2-53 (batch loop)

Week of Feb 10:
└─ Complete all 53 containers; move to Stage 3 (deduplication)
```

---

## Files Included

1. **HYBRID_SCHEMA_DECISION_PACKAGE.md** — Full technical specification (tables, fields, workflows, unknown decisions)
2. **HYBRID_SCHEMA_DIAGRAMS.md** — Visual architecture, data flows, process flows, schema evolution
3. **This file (EXECUTIVE_SUMMARY.md)** — One-page overview + critical questions

---

## My Recommendation

**Go with hybrid.** The proposed approach is architecturally sound:

✓ Clean separation of concerns (files = inputs, DB = state)  
✓ Enables rich segmentation (images + structured OCR)  
✓ Supports future extensibility (ML, dedup, refinement)  
✓ Manageable implementation (~1 week of development)  
✓ One-time setup cost; benefits compound over 53+ containers

The pure DB approach works short-term but hits walls fast when you need:
- Multiple OCR sources to compare
- Image-aware processing
- Audit trails / reproducibility
- Manual QA substrate

Better to invest now than refactor later.

---

## Next Steps

1. **Decision:** Review + provide feedback on the three documents
2. **Refinement:** Clarify unknowns (see critical questions above)
3. **Approval:** Michael signs off on architecture
4. **Implementation:** I build migrations + refactor scripts
5. **Execution:** Run backfill, test segmentation, scale

---

**Prepared:** Claude  
**For:** Michael Raney  
**Format:** Ready for deep analysis by Claude Thinking or Opus 4.5
