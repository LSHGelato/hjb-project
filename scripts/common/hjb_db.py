#!/usr/bin/env python3
"""
HJB Database Module - CORRECTED TO ACTUAL SCHEMA

Purpose:
- Database connection management
- Basic CRUD operations for core entities
- Migration utilities
- Query helpers

**SCHEMA TRUTH:** Actual database schema in containers_t (verified via screenshots)
See /mnt/user-data/uploads/ for proof

Configuration:
Reads from environment variables (auto-loaded from .env) or config.yaml:
  - HJB_MYSQL_HOST
  - HJB_MYSQL_PORT
  - HJB_MYSQL_USER
  - HJB_MYSQL_PASSWORD (required)
  - HJB_MYSQL_DATABASE

Usage:
  from hjb_db import insert_container, get_container_by_source

Dependencies:
  pip install mysql-connector-python PyYAML python-dotenv
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import mysql.connector
from mysql.connector import Error as MySQLError
import yaml
from dotenv import load_dotenv

# Load .env from repo root
_repo_root = Path(__file__).resolve().parents[2]
load_dotenv(_repo_root / ".env")


# ============================================================================
# Configuration Loading
# ============================================================================

@lru_cache(maxsize=1)
def load_config() -> Dict[str, Any]:
    """Load config.yaml (or config.example.yaml fallback)."""
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parents[1]
    
    cfg_path = repo_root / "config" / "config.yaml"
    if not cfg_path.is_file():
        cfg_path = repo_root / "config" / "config.example.yaml"
    
    if not cfg_path.is_file():
        raise FileNotFoundError("Neither config/config.yaml nor config/config.example.yaml found")
    
    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    
    if not isinstance(cfg, dict):
        raise ValueError(f"Config must be a dict: {cfg_path}")
    
    return cfg


def get_db_config() -> Dict[str, str]:
    """Get database configuration from environment or config file."""
    cfg = load_config()
    db_cfg = cfg.get("database", {})
    
    def pick(env_key: str, cfg_key: str, default: str = "") -> str:
        val = os.environ.get(env_key)
        if val:
            stripped = val.strip()
            if stripped:
                return stripped

        # Check database.X
        val = db_cfg.get(cfg_key)
        if isinstance(val, str):
            stripped = val.strip()
            if stripped:
                return stripped

        # Check top-level X
        val = cfg.get(cfg_key)
        if isinstance(val, str):
            stripped = val.strip()
            if stripped:
                return stripped

        return default
    
    host = pick("HJB_MYSQL_HOST", "host", "localhost")
    user = pick("HJB_MYSQL_USER", "user", "root")
    password = pick("HJB_MYSQL_PASSWORD", "password", "")
    database = pick("HJB_MYSQL_DATABASE", "database", "raneywor_historicaljournals")
    port = pick("HJB_MYSQL_PORT", "port", "3306")

    if not password:
        raise ValueError(
            "Database password required. Set HJB_MYSQL_PASSWORD environment variable "
            "or database.password in config.yaml"
        )
    
    return {
        "host": host,
        "user": user,
        "password": password,
        "database": database,
        "port": int(port),
    }


# ============================================================================
# Connection Management
# ============================================================================

@contextmanager
def get_connection(autocommit: bool = False):
    """Context manager for database connections."""
    db_cfg = get_db_config()
    conn = None
    try:
        conn = mysql.connector.connect(
            host=db_cfg["host"],
            port=db_cfg["port"],
            user=db_cfg["user"],
            password=db_cfg["password"],
            database=db_cfg["database"],
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
            autocommit=autocommit,
        )
        yield conn
    except MySQLError as e:
        print(f"Database connection error: {e}", file=sys.stderr)
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()


def execute_query(query: str, params: Optional[tuple] = None, fetch: bool = False) -> Any:
    """Execute a single query and optionally fetch results."""
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        
        if fetch:
            results = cursor.fetchall()
            cursor.close()
            return results
        else:
            conn.commit()
            last_id = cursor.lastrowid
            row_count = cursor.rowcount
            cursor.close()
            return last_id if last_id else row_count


# ============================================================================
# Publication Families & Titles
# ============================================================================

def insert_family(
    family_root: str,
    display_name: str,
    family_code: Optional[str] = None,
    family_type: str = "journal",
    notes: Optional[str] = None,
) -> int:
    """Insert a publication family. Returns: family_id"""
    if not family_code:
        family_code = family_root.upper().replace("-", "_")[:64]
    
    query = """
        INSERT INTO publication_families_t 
        (family_root, family_code, display_name, family_type, notes)
        VALUES (%s, %s, %s, %s, %s)
    """
    return execute_query(
        query,
        (family_root, family_code, display_name, family_type, notes)
    )


def get_family_by_root(family_root: str) -> Optional[Dict[str, Any]]:
    """Get family by family_root. Returns dict or None."""
    result = execute_query(
        "SELECT * FROM publication_families_t WHERE family_root = %s",
        (family_root,),
        fetch=True
    )
    return result[0] if result else None


def insert_title(
    family_id: int,
    display_title: str,
    publisher: Optional[str] = None,
    city: Optional[str] = None,
    run_start_date: Optional[date] = None,
) -> int:
    """Insert a publication title. Returns: title_id"""
    query = """
        INSERT INTO publication_titles_t 
        (family_id, display_title, publisher, city, run_start_date)
        VALUES (%s, %s, %s, %s, %s)
    """
    return execute_query(
        query,
        (family_id, display_title, publisher, city, run_start_date)
    )


# ============================================================================
# Containers - CORRECTED TO MATCH ACTUAL SCHEMA
# ============================================================================

def insert_container(
    source_system: str,
    source_identifier: str,
    family_id: int,
    source_url: Optional[str] = None,
    title_id: Optional[int] = None,
    container_label: Optional[str] = None,
    container_type: Optional[str] = None,
    volume_label: Optional[str] = None,
    date_start: Optional[date] = None,
    date_end: Optional[date] = None,
    total_pages: Optional[int] = None,
    has_jp2: bool = False,
    has_djvu_xml: bool = False,
    has_hocr: bool = False,
    has_alto: bool = False,
    has_mets: bool = False,
    has_pdf: bool = False,
    has_scandata: bool = False,
    raw_input_path: Optional[str] = None,
) -> int:
    """
    Insert a container record.
    
    ACTUAL Schema (containers_t):
      - container_id (AUTO_INCREMENT)
      - source_system (VARCHAR 64, required)
      - source_identifier (VARCHAR 255, required)
      - source_url (VARCHAR 512, nullable)
      - family_id (INT UNSIGNED, required - FK)
      - title_id, container_label, container_type, volume_label (nullable)
      - date_start, date_end (date, nullable)
      - total_pages (INT, nullable)
      - has_jp2, has_djvu_xml, has_hocr, has_alto, has_mets, has_pdf, has_scandata (tinyint)
      - raw_input_path, working_path, reference_path (VARCHAR 512, nullable)
      - download_status, validation_status (ENUM)
      - downloaded_at, validated_at, notes, created_at, updated_at
    
    Returns: container_id
    """
    query = """
        INSERT INTO containers_t 
        (source_system, source_identifier, family_id, source_url, title_id,
         container_label, container_type, volume_label, date_start, date_end,
         total_pages, has_jp2, has_djvu_xml, has_hocr, has_alto, has_mets,
         has_pdf, has_scandata, raw_input_path, download_status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
    """
    return execute_query(
        query,
        (source_system, source_identifier, family_id, source_url, title_id,
         container_label, container_type, volume_label, date_start, date_end,
         total_pages, has_jp2, has_djvu_xml, has_hocr, has_alto, has_mets,
         has_pdf, has_scandata, raw_input_path)
    )


def get_container_by_source(source_system: str, source_identifier: str) -> Optional[Dict[str, Any]]:
    """Get container by source_system and source_identifier. Returns dict or None."""
    result = execute_query(
        "SELECT * FROM containers_t WHERE source_system = %s AND source_identifier = %s",
        (source_system, source_identifier),
        fetch=True
    )
    return result[0] if result else None


def update_container_download_status(
    container_id: int,
    status: str,
    raw_input_path: Optional[str] = None
) -> None:
    """Update container download status to 'pending', 'in_progress', 'complete', or 'failed'."""
    if raw_input_path:
        execute_query(
            "UPDATE containers_t SET download_status = %s, raw_input_path = %s, downloaded_at = NOW() WHERE container_id = %s",
            (status, raw_input_path, container_id)
        )
    else:
        execute_query(
            "UPDATE containers_t SET download_status = %s, downloaded_at = NOW() WHERE container_id = %s",
            (status, container_id)
        )


# ============================================================================
# Issues
# ============================================================================

def insert_issue(
    title_id: int,
    volume_label: Optional[str] = None,
    issue_label: Optional[str] = None,
    issue_date: Optional[date] = None,
    edition_year: Optional[int] = None,
    edition_num: Optional[str] = None,
    page_count: Optional[int] = None,
) -> int:
    """Insert an issue/edition record. Returns: issue_id"""
    query = """
        INSERT INTO issues_t 
        (title_id, volume_label, issue_label, issue_date, edition_year, edition_num, page_count)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    return execute_query(
        query,
        (title_id, volume_label, issue_label, issue_date, edition_year, edition_num, page_count)
    )


def insert_issue_container(issue_id: int, container_id: int) -> int:
    """Map issue to container. Returns: issue_container_id"""
    query = """
        INSERT INTO issue_containers_t (issue_id, container_id)
        VALUES (%s, %s)
    """
    return execute_query(query, (issue_id, container_id))


# ============================================================================
# Pages
# ============================================================================

def insert_page(
    container_id: int,
    page_num: int,
    page_type: Optional[str] = None,
    ocr_text: Optional[str] = None,
    ocr_confidence: Optional[float] = None,
) -> int:
    """Insert a page record. Returns: page_id"""
    query = """
        INSERT INTO pages_t
        (container_id, page_num, page_type, ocr_text, ocr_confidence)
        VALUES (%s, %s, %s, %s, %s)
    """
    return execute_query(
        query,
        (container_id, page_num, page_type, ocr_text, ocr_confidence)
    )


def batch_insert_pages(pages: List[Dict[str, Any]]) -> int:
    """
    Batch insert pages into pages_t.

    Args:
        pages: List of page dictionaries with fields:
            - container_id (required)
            - issue_id (required)
            - page_index (required, 0-based)
            - page_number_printed (optional)
            - page_label (optional)
            - page_type (required)
            - is_cover (required, 0 or 1)
            - is_blank (required, 0 or 1)
            - has_ocr (required, 0 or 1)
            - ocr_source (optional: 'ia_djvu' or 'ia_hocr')
            - ocr_confidence (optional: 0.00-1.00)
            - ocr_word_count (optional)
            - ocr_char_count (optional)
            - ocr_text (optional: MEDIUMTEXT)
            - is_plate (optional, default: 0)
            - is_supplement (optional, default: 0)
            - image_dpi (optional, default: 300)

    Returns:
        Number of pages inserted

    Note:
        - is_manually_verified field should be added via migration (see migration_add_is_manually_verified_to_pages_t.sql)
        - When available, is_manually_verified can be passed as a dictionary field with default 0
    """
    if not pages:
        return 0

    query = """
        INSERT INTO pages_t
        (container_id, issue_id, page_index, page_number_printed, page_label,
         page_type, is_cover, is_plate, is_blank, is_supplement, has_ocr,
         ocr_source, ocr_confidence, ocr_word_count, ocr_char_count, ocr_text, image_dpi)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    with get_connection() as conn:
        cursor = conn.cursor()

        # Prepare tuples for executemany
        values = [
            (
                p['container_id'],
                p['issue_id'],
                p['page_index'],
                p.get('page_number_printed'),
                p.get('page_label'),
                p.get('page_type', 'content'),
                p.get('is_cover', 0),
                p.get('is_plate', 0),
                p.get('is_blank', 0),
                p.get('is_supplement', 0),
                p.get('has_ocr', 0),
                p.get('ocr_source'),
                p.get('ocr_confidence'),
                p.get('ocr_word_count'),
                p.get('ocr_char_count'),
                p.get('ocr_text'),
                p.get('image_dpi', 300),
            )
            for p in pages
        ]

        cursor.executemany(query, values)
        conn.commit()
        row_count = cursor.rowcount
        cursor.close()

        return row_count


# ============================================================================
# Works & Occurrences
# ============================================================================

def insert_work(
    family_id: int,
    title: str,
    work_type: str,
    author: Optional[str] = None,
    canonical_text: Optional[str] = None,
    notes: Optional[str] = None,
) -> int:
    """Insert a work record. Returns: work_id"""
    query = """
        INSERT INTO works_t 
        (family_id, title, work_type, author, canonical_text, notes)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    return execute_query(
        query,
        (family_id, title, work_type, author, canonical_text, notes)
    )


def insert_work_occurrence(
    work_id: int,
    issue_id: int,
    container_id: int,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    occurrence_text: Optional[str] = None,
    source: Optional[str] = None,
) -> int:
    """Insert a work occurrence. Returns: occurrence_id"""
    query = """
        INSERT INTO work_occurrences_t 
        (work_id, issue_id, container_id, start_page, end_page, occurrence_text, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    return execute_query(
        query,
        (work_id, issue_id, container_id, start_page, end_page, occurrence_text, source)
    )


# ============================================================================
# Processing Status
# ============================================================================

def insert_processing_status(container_id: int) -> int:
    """
    Initialize processing status for a container.
    
    Returns: status_id
    """
    query = "INSERT INTO processing_status_t (container_id) VALUES (%s)"
    return execute_query(query, (container_id,))


# Valid stage names for update_stage_completion (prevents SQL injection)
_VALID_STAGES = frozenset({
    "stage1_ingestion",
    "stage2_ocr",
    "stage3_segmentation",
    "stage4_enrichment",
    "stage5_export",
})

# Mapping of stage names to timestamp column names in processing_status_t
# Note: Actual schema has stage2_ocr_complete paired with stage2_completed_at (not stage2_ocr_completed_at)
_STAGE_TIMESTAMP_COLUMNS = {
    "stage1_ingestion": "stage1_completed_at",
    "stage2_ocr": "stage2_completed_at",
}


def update_stage_completion(
    container_id: int,
    stage: str,
    complete: bool = True,
    error_message: Optional[str] = None
) -> None:
    """
    Update stage completion status.

    Args:
        container_id: Container ID
        stage: e.g., "stage1_ingestion", "stage2_ocr", etc.
        complete: True if stage completed successfully
        error_message: Error message if failed
    """
    # Validate stage name to prevent SQL injection
    if stage not in _VALID_STAGES:
        raise ValueError(f"Invalid stage name: {stage}. Must be one of: {', '.join(sorted(_VALID_STAGES))}")

    if complete:
        # Stage name is validated above, safe to use in query
        # Use the correct timestamp column for this stage
        timestamp_col = _STAGE_TIMESTAMP_COLUMNS.get(stage, f"{stage}_completed_at")
        query = f"""
            UPDATE processing_status_t
            SET {stage}_complete = 1, {timestamp_col} = NOW()
            WHERE container_id = %s
        """
        execute_query(query, (container_id,))
    else:
        query = """
            UPDATE processing_status_t
            SET last_error_stage = %s, last_error_message = %s,
                last_error_at = NOW(), retry_count = retry_count + 1
            WHERE container_id = %s
        """
        execute_query(query, (stage, error_message, container_id))


# ============================================================================
# Utility Functions
# ============================================================================

def test_connection() -> bool:
    """Test database connection. Returns True if successful."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
    except Exception as e:
        print(f"Connection test failed: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    print("Testing database connection...")
    if test_connection():
        print("[OK] Database connection successful")
    else:
        print("[FAIL] Database connection failed")
        sys.exit(1)
