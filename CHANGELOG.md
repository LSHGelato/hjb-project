# Changelog

All notable changes to the Historical Journals & Books (HJB) Project codebase
are documented in this file.

The format follows **Keep a Changelog** (https://keepachangelog.com/)
and adheres to **Semantic Versioning** (https://semver.org/).

---

## [Unreleased]

### Added

- New supervisor trigger `ops_update_deps_watcher.flag` for pulling code + installing dependencies + restarting watcher
- `internetarchive` package (v1.10.0) to requirements for IA downloads in stage1.ia_download
- `Install-Requirements()` function in supervisor for robustly installing from requirements.txt

#### Database & Schema (HJB-SCHEMA)
- Publication families table (`publication_families_t`) with `family_root`, `family_code`, `display_name` for grouping related journals/books across naming changes
- Publication titles table (`publication_titles_t`) with publisher, location, run dates, and variant names
- Issues/editions table (`issues_t`) unified for both journals and books, supporting volume numbers and edition information
- Containers table (`containers_t`) mapping physical scanning units (PDFs, scans) to their sources (IA, HathiTrust, local)
- Pages table (`pages_t`) for individual page tracking with OCR text and confidence scoring
- Works table (`works_t`) for unique content pieces (articles, advertisements, chapters, indices)
- Work occurrences table (`work_occurrences_t`) mapping works to their physical instances and page ranges
- Database schema migrations system with versioning for reproducible deployments
- SQL migration files in `database/migrations/` tracked in GitHub

#### File Organization (HJB-STORAGE)
- Unified NAS folder structure under single project root: `\\RaneyHQ\Michael\02_Projects\Historical_Journals_And_Books\`
- Raw_Input layer (Stage 1): immutable source files from IA, HathiTrust, USModernist, university collections, local scans
- Working_Files layer (Stages 2-3): transient processing files organized by pipeline stage (0210_Preprocessing through 0290_Archive)
- Reference_Library layer: curated master files post-QC, organized by publication family and volume
- State directory (0200_STATE) with atomic flag file protocol for task queue and heartbeat monitoring
- Folder structure creation checklist and validation procedures

#### Watcher Enhancements (HJB-STAGE2)
- Opportunistic mode (`--opportunistic`) for OrionMega: 10-second poll interval with intelligent idle detection
- One-task-and-exit mode (`--one-task-and-exit`) for controlled task processing and wrapper orchestration
- `is_orionmx_busy()` function: monitors `flags/processing` to check if OrionMX watchers are actively processing before claiming tasks
- Heartbeat field `"opportunistic"` indicating mode status
- Task result and error JSONs now include `started_utc`, `ended_utc`, and `duration_seconds` for operational visibility
- Standardized heartbeat naming: always includes watcher_id (e.g., `watcher_heartbeat_orionmx_1.json`, `watcher_heartbeat_orionmega_1.json`)
- `run_once()` now returns `bool` indicating whether a task was processed, enabling wrapper control flow

#### Wrapper Improvements (HJB-OPS)
- Complete rewrite of `run_watcher_orionmega.ps1` with true idle detection
- Windows API integration (`GetLastInputInfo`) for detecting actual user activity (keyboard/mouse)
- 5-minute grace period confirmation with dual-check to prevent false starts on quick breaks
- Continuous task loop while machine is locked: spawn watcher → wait for completion → check idle → repeat
- Automatic exit detection when user returns (idle < 60 seconds)
- Per-task timeout (1 hour) with automatic process termination if exceeded
- Timestamped logging to Task Scheduler console for debugging and monitoring

#### Configuration & Documentation
- Comprehensive config.yaml structure with NAS paths, scratch disk locations, and task definitions
- Script path analysis documentation showing how watcher and wrapper interact with config
- Opportunistic watcher implementation summary with deployment and debugging guides
- Commit message templates following Conventional Commits (HJB scope prefixes established)
- Folder structure specification document with creation checklist

### Changed

- requirements.txt now includes internetarchive and click (transitive dependency)
- Supervisor supports three trigger modes: update (git only), update_deps (git + pip), restart (no changes)

#### Heartbeat Standardization
- Removed special case for `orionmx_1` heartbeat; all watchers now use consistent `watcher_heartbeat_<watcher_id>.json` naming
- Applies to both watcher and supervisor heartbeats for clarity in multi-watcher scenarios

#### Task Execution Tracking
- Result/error JSONs now capture full task lifecycle with start/end times for better operational metrics
- Enables analysis of task duration for scheduling and resource planning

#### Database Design
- Tables use `_t` suffix convention throughout (e.g., `publication_families_t`, `issues_t`) for clarity in discussions
- Unified schema accommodates both journals and books through shared entity structure
- Works & occurrences model separates intellectual content from physical instances

### Fixed

- Missing internetarchive package was blocking stage1.ia_download task handler

#### Configuration Path Resolution
- Clarified that watcher and supervisor both resolve `state_root` from config, supporting both `cfg.paths.state_root` and `cfg.state_root` styles
- Derived paths (`flags_root`, `logs_root`) consistently derived from `state_root` if not explicitly specified

#### Script Heartbeat Naming
- Previous inconsistency (special case for `orionmx_1`) replaced with uniform naming across all watcher IDs
- No code changes needed in watcher; heartbeat naming logic already supported correct structure

### Removed

#### Legacy Configuration Assumptions
- Removed assumption that `OrionMX` heartbeat would be stored without watcher_id suffix
- Eliminated split across `01_Research`, `02_Projects`, `05_Reference` top-level folders in favor of unified project root

---

## [2.4.0] — 2026-01-08

### Added
- GitHub integration section formalized in Blueprint v2.4
- Watcher-based orchestration model documentation
- OrionMega opportunistic processing architecture
- Multi-watcher atomic task-claiming protocol
- Deployment model based on manual `git pull` to OrionMX
- Minimal Success v0 watcher (heartbeat + no-op task claiming)

### Changed
- Clarified OrionMX operational status (always online, not remotely accessible)
- Expanded scalability and monitoring guidance
- Clarified local setup expectations to require venv-based execution for watchers

### Fixed
- Corrected earlier ambiguity around processing machine availability

### Removed
- Assumptions of linear "Stage 1 then Stage 2" project completion

---

## Versioning Policy

- **MAJOR** version increments indicate architectural or data-model changes
  requiring coordinated migration (e.g., schema or workflow redesign).
- **MINOR** version increments add functionality without breaking compatibility.
- **PATCH** versions are reserved for bug fixes and operational corrections.

Every release merged into `main` must:
1. Be deployable to both OrionMX and OrionMega
2. Have an entry in this changelog
3. Preserve backward compatibility unless explicitly documented
4. Follow Conventional Commits format with HJB scope prefixes:
   - `HJB-SCHEMA`: Database schema and migrations
   - `HJB-STORAGE`: NAS folder structure and file organization
   - `HJB-STAGE[1-4]`: Pipeline stage implementations
   - `HJB-OPS`: Operational scripts (watcher, supervisor, deployment)
   - `HJB-CONFIG`: Configuration and environment setup

---

## Historical Context

The project was restructured between v2.4.0 (2026-01-08) and current unreleased version to:
1. Implement actual database schema (previously blueprint-only)
2. Establish unified NAS folder structure (replaces scattered `01_Research`/`02_Projects`/`05_Reference`)
3. Build true opportunistic mode for OrionMega with idle detection
4. Standardize heartbeat and task result tracking across multi-watcher architecture
5. Create comprehensive documentation for deployment and operations

All changes maintain backward compatibility at the watcher protocol level while significantly enhancing operational visibility and automated task coordination.
