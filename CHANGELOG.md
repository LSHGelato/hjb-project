# Changelog

All notable changes to the Historical Journals & Books (HJB) Project codebase
are documented in this file.

The format follows **Keep a Changelog** (https://keepachangelog.com/)
and adheres to **Semantic Versioning** (https://semver.org/).

---

## [Unreleased]

### Added
- Standardized Python runtime on Python 3.12 with project-local virtual environments
- Introduced `requirements.in` and pinned `requirements.txt` for reproducible dependency installs
- Documented venv and dependency management strategy
- Initial GitHub repository structure aligned with Blueprint v2.4
- Baseline documentation (README.md)
- Configuration template (`config/config.example.yaml`)
- Standardized `.gitignore` for data-safe operation
- Changelog scaffolding

### Changed
- Clarified local setup expectations to require venv-based execution for watchers

---

## [2.4.0] — 2026-01-08

### Added
- GitHub integration section formalized in Blueprint v2.4
- Watcher-based orchestration model documentation
- OrionMega opportunistic processing architecture
- Multi-watcher atomic task-claiming protocol
- Deployment model based on manual `git pull` to OrionMX

### Changed
- Clarified OrionMX operational status (always online, not remotely accessible)
- Expanded scalability and monitoring guidance

### Fixed
- Corrected earlier ambiguity around processing machine availability

### Removed
- Assumptions of linear “Stage 1 then Stage 2” project completion

---

## Versioning Policy

- **MAJOR** version increments indicate architectural or data-model changes
  requiring coordinated migration (e.g., schema or workflow redesign).
- **MINOR** version increments add functionality without breaking compatibility.
- **PATCH** versions are reserved for bug fixes and operational corrections.

Every release merged into `main` must:
1. Be deployable to OrionMX
2. Have an entry in this changelog
3. Preserve backward compatibility unless explicitly documented
# Changelog

All notable changes to the Historical Journals & Books (HJB) Project codebase
are documented in this file.

The format follows **Keep a Changelog** (https://keepachangelog.com/)
and adheres to **Semantic Versioning** (https://semver.org/).

---

## [Unreleased]

### Added
- Standardized Python runtime on Python 3.12 with project-local virtual environments
- Introduced `requirements.in` and pinned `requirements.txt` for reproducible dependency installs
- Documented venv and dependency management strategy
- Initial GitHub repository structure aligned with Blueprint v2.4
- Baseline documentation (README.md)
- Configuration template (`config/config.example.yaml`)
- Standardized `.gitignore` for data-safe operation
- Changelog scaffolding
- Minimal Success v0 watcher (heartbeat + no-op task claiming)

### Changed
- Clarified local setup expectations to require venv-based execution for watchers

---

## [2.4.0] — 2026-01-08

### Added
- GitHub integration section formalized in Blueprint v2.4
- Watcher-based orchestration model documentation
- OrionMega opportunistic processing architecture
- Multi-watcher atomic task-claiming protocol
- Deployment model based on manual `git pull` to OrionMX

### Changed
- Clarified OrionMX operational status (always online, not remotely accessible)
- Expanded scalability and monitoring guidance

### Fixed
- Corrected earlier ambiguity around processing machine availability

### Removed
- Assumptions of linear “Stage 1 then Stage 2” project completion

---

## Versioning Policy

- **MAJOR** version increments indicate architectural or data-model changes
  requiring coordinated migration (e.g., schema or workflow redesign).
- **MINOR** version increments add functionality without breaking compatibility.
- **PATCH** versions are reserved for bug fixes and operational corrections.

Every release merged into `main` must:
1. Be deployable to OrionMX
2. Have an entry in this changelog
3. Preserve backward compatibility unless explicitly documented
