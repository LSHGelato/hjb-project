# HJB Naming Conventions

## Publication Families (`publication_families_t.family_root`)
Suffix rules:
- Journals: `PublicationName_family` (e.g., `American_Architect_family`)
- Book series: `SeriesName_series` (e.g., `Cyclopedia_of_Architecture_Building_Construction_series`)
- Single books: `BookTitle_book` or `BookTitle_book_AuthorSurname` if collision

## Database Tables
All custom tables end with `_t` suffix:
- `publication_families_t`
- `issues_t`
- `containers_t`
- `pages_t`
- `works_t`
- etc.

## Flag Files (Task Queue)
Location: `0200_STATE/flags/pending/`
Naming: `[YYYY-MM-DD]_[task_type]_[identifier].json`
Example: `2026-01-23_download_American_Architect_1890_01.json`

## Config Keys
Environment variables: `HJB_MYSQL_PASSWORD`, `HJB_WIKI_PASSWORD`
Config file keys: `storage.working_files`, `database.host`
[add all relevant patterns]
