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
Reads from environment variables or config.yaml:
  - HJB_DB_HOST
  - HJB_DB_USER
  - HJB_DB_PASSWORD (required)
  - HJB_DB_NAME

Usage:
  from hjb_db import insert_container, get_container_by_source

Dependencies:
  pip install mysql-connector-python PyYAML
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import mysql.connector
from mysql.connector import Error as MySQLError
import yaml


# ============================================================================
# Configuration Loading
# ============================================================================

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
            return val.strip()
        
        val = db_cfg.get(cfg_key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        
        val = cfg.get(cfg_key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        
        return default
    
    host = pick("HJB_DB_HOST", "host", "localhost")
    user = pick("HJB_DB_USER", "user", "root")
    password = pick("HJB_DB_PASSWORD", "password", "")
    database = pick("HJB_DB_NAME", "database", "raneywor_historicaljournals")
    port = pick("HJB_DB_PORT", "port", "3306")
    
    if not password:
        raise ValueError(
            "Database password required. Set HJB_DB_PASSWORD environment variable "
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
        print("✓ Database connection successful")
    else:
        print("✗ Database connection failed")
        sys.exit(1)
