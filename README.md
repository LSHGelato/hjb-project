# Historical Journals & Books (HJB) Project

Authoritative codebase for the Historical Journals & Books Project (HJB): an end-to-end pipeline that ingests historical journals/books, validates and normalizes metadata, performs OCR and segmentation into discrete works (articles/ads/sections), canonicalizes duplicates, and publishes structured outputs via MySQL + MediaWiki.

This repository contains **code, configuration templates, database migrations, and documentation**. It does **not** store corpus data (JP2/PDF/OCR outputs) or authoritative media files.

## What belongs in this repository

**Include:**
- Python scripts for Stage 1–4 processing and watcher orchestration
- Database migration scripts (forward + rollback)
- MediaWiki templates and export logic
- Documentation and runbooks
- Example configuration (`config/config.example.yaml`) and schema references

**Do not include:**
- Raw downloads (JP2/PDF/HOCR/DjVu/scandata)
- Working-layer intermediates (page packs, OCR outputs, segmentation artifacts)
- Reference library masters
- Logs, caches, or database dumps
- Secrets (passwords/API keys), real `config.yaml`

## System architecture at a glance

HJB spans five components:

- **OrionMX**: primary processing computer, always online, runs watcher continuously (not remotely accessible).
- **OrionMega**: opportunistic burst processing when locked/idle (not remotely accessible).
- **RaneyHQ (NAS)**: authoritative storage + workflow hub (SMB shares); hosts flag-file task queue.
- **HostGator**: MySQL + MediaWiki (Published layer).
- **GitHub**: version control for scripts/config templates/docs only.

Data flows through the four-layer model:
**Raw → Working → Reference → Published**.

## Repository layout
```
hjb-project/
├── README.md
├── CHANGELOG.md
├── .gitignore
│
├── scripts/
│ ├── stage1/ # ingestion & validation
│ ├── stage2/ # OCR & segmentation
│ ├── stage3/ # canonicalization & deduplication
│ ├── stage4/ # publication & export
│ └── watcher/ # watcher orchestration (flag queue)
│
├── config/
│ └── config.example.yaml # template only (no secrets)
│
├── migrations/ # database migrations (forward)
│ └── rollback/ # rollback scripts
│
├── templates/ # MediaWiki templates / wikitext scaffolds
├── docs/ # implementation notes, runbooks, diagrams
└── tests/ # unit/integration tests
```

## Configuration strategy

- Copy `config/config.example.yaml` to `config/config.yaml` on each processing machine.
- `config/config.yaml` is **local-only** and must remain **gitignored**.
- Store credentials using environment variables where feasible; otherwise keep them only in `config.yaml`.

## Watcher orchestration (flag-file queue)

The watcher processes tasks defined as JSON flag files placed under:

`\\RaneyHQ\Michael\02_Projects\Historical_Journals_Pipeline\0200_STATE\flags\pending\`

It atomically claims tasks by moving them to `processing/`, then writes results to `completed/` or `failed/`.

OrionMX typically runs in continuous mode; OrionMega runs opportunistically (lock/idle triggers).

## Deployment model

This repository is deployed by a simple pull-based mechanism:

1. Merge stable changes to `main`
2. On OrionMX (and OrionMega if used):
   - `git pull origin main`
3. Restart watcher if watcher code changed

No CI/CD is required for baseline operation.

## Branching strategy

- `main`: production-ready code deployed to OrionMX
- `develop`: integration branch
- `feature/*`: feature work
- `hotfix/*`: urgent fixes to production

## Quick start (typical)

1. Clone the repo to a local path on OrionMX (example):
   - `C:\hjb-project\`
2. Create `config/config.yaml` from the template:
   - Copy `config/config.example.yaml` → `config/config.yaml`
   - Fill in environment-specific values
3. Verify NAS paths are accessible and writable
4. Start the watcher (example invocation):
   - `python scripts/watcher/hjb_watcher.py --continuous --watcher-id=orionmx_1`

## Safety and data integrity notes

- Treat RaneyHQ as authoritative storage for corpus materials and pipeline state.
- Never modify files in the Raw layer in place; write derivatives to Working.
- Keep migrations versioned and reversible; test on a non-production copy first.
- Do not commit secrets. Do not commit data.

## License

TBD. Until selected, assume internal use only.
