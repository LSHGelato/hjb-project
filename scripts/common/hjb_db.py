#!/usr/bin/env python3
"""
HJB Database Module

Purpose:
- Database connection management
- Basic CRUD operations for core entities
- Migration utilities
- Query helpers

Configuration:
Reads from environment variables or config.yaml:
  - HJB_DB_HOST (default: from config)
  - HJB_DB_USER (default: from config)
  - HJB_DB_PASSWORD (required)
  - HJB_DB_NAME (default: from config or raneywor_historicaljournals)

Usage:
  from hjb_db import get_connection, insert_container, get_family_by_root

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
    """
    Load config.yaml (or config.example.yaml fallback).
    Returns the config dict.
    """
    # Find repo root (scripts/common/ -> repo root is 2 levels up)
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parents[1]  # Adjust based on where this file lives
    
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
    """
    Get database configuration from environment or config file.
    
    Priority: Environment variables > config.yaml
    
    Returns dict with keys: host, user, password, database, port
    """
    cfg = load_config()
    db_cfg = cfg.get("database", {})
    
    # Fallback chain: env var > config.database.X > config.X > hardcoded default
    def pick(env_key: str, cfg_key: str, default: str = "") -> str:
        val = os.environ.get(env_key)
        if val:
            return val.strip()
        
        # Check database.X
        val = db_cfg.get(cfg_key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        
        # Check top-level X
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
    """
    Context manager for database connections.
    
    Usage:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM publication_families")
            rows = cursor.fetchall()
    """
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
    """
    Execute a single query and optionally fetch results.
    
    Args:
        query: SQL query string
        params: Optional tuple of parameters for parameterized query
        fetch: If True, return fetchall() results
    
    Returns:
        If fetch=True: list of dicts (rows)
        If fetch=False: lastrowid (for INSERT) or rowcount (for UPDATE/DELETE)
    """
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
# Schema & Migration Utilities
# ============================================================================

def get_schema_version() -> int:
    """
    Get current schema version from database.
    Returns 0 if schema_version_t table doesn't exist.
    """
    try:
        result = execute_query(
            "SELECT MAX(version_number) as ver FROM schema_version_t",
            fetch=True
        )
        if result and result[0]["ver"] is not None:
            return int(result[0]["ver"])
        return 0
    except MySQLError:
        return 0


def apply_migration(migration_path: Path) -> None:
    """
    Apply a SQL migration file.
    
    Args:
        migration_path: Path to .sql migration file
    """
    if not migration_path.is_file():
        raise FileNotFoundError(f"Migration file not found: {migration_path}")
    
    sql_text = migration_path.read_text(encoding="utf-8")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Execute all statements in migration
        # Note: This is simplified; production might use mysqldump or similar
        for statement in sql_text.split(";"):
            stmt = statement.strip()
            if stmt and not stmt.startswith("--"):
                cursor.execute(stmt)
        
        conn.commit()
        cursor.close()
    
    print(f"Applied migration: {migration_path.name}")


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
    """
    Insert a publication family.
    
    Returns: family_id
    """
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
    """
    Insert a publication title.
    
    Returns: title_id
    """
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
# Containers
# ============================================================================

def insert_container(
    source_system: str,
    source_identifier: str,
    source_url: Optional[str] = None,
    family_id: Optional[int] = None,
    title_id: Optional[int] = None,
    container_label: Optional[str] = None,
    total_pages: Optional[int] = None,
    has_jp2: bool = False,
    has_hocr: bool = False,
    has_djvu_xml: bool = False,
    has_pdf: bool = False,
    raw_input_path: Optional[str] = None,
) -> int:
    """
    Insert a container record.
    
    Returns: container_id
    """
    query = """
        INSERT INTO containers_t 
        (source_system, source_identifier, source_url, family_id, title_id,
         container_label, total_pages, has_jp2, has_hocr, has_djvu_xml, has_pdf,
         raw_input_path, downloaded_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
    """
    return execute_query(
        query,
        (source_system, source_identifier, source_url, family_id, title_id,
         container_label, total_pages, has_jp2, has_hocr, has_djvu_xml, has_pdf,
         raw_input_path)
    )


def get_container_by_source(source_system: str, source_identifier: str) -> Optional[Dict[str, Any]]:
    """Get container by source. Returns dict or None."""
    result = execute_query(
        "SELECT * FROM containers_t WHERE source_system = %s AND source_identifier = %s",
        (source_system, source_identifier),
        fetch=True
    )
    return result[0] if result else None


def update_container_validation(container_id: int, status: str) -> None:
    """Update container validation status."""
    execute_query(
        "UPDATE containers_t SET validation_status = %s, validated_at = NOW() WHERE container_id = %s",
        (status, container_id)
    )


# ============================================================================
# Issues
# ============================================================================

def insert_issue(
    title_id: int,
    family_id: int,
    volume_label: Optional[str] = None,
    issue_label: Optional[str] = None,
    issue_date_start: Optional[date] = None,
    year_published: Optional[int] = None,
    is_book_edition: bool = False,
    canonical_issue_key: Optional[str] = None,
) -> int:
    """
    Insert an issue/edition record.
    
    Returns: issue_id
    """
    query = """
        INSERT INTO issues_t 
        (title_id, family_id, volume_label, issue_label, issue_date_start,
         year_published, is_book_edition, canonical_issue_key)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    return execute_query(
        query,
        (title_id, family_id, volume_label, issue_label, issue_date_start,
         year_published, is_book_edition, canonical_issue_key)
    )


# ============================================================================
# Pages
# ============================================================================

def insert_page(
    container_id: int,
    page_index: int,
    issue_id: Optional[int] = None,
    page_label: Optional[str] = None,
    page_type: str = "content",
    has_ocr: bool = False,
    ocr_source: Optional[str] = None,
    ocr_text: Optional[str] = None,
    image_file_path: Optional[str] = None,
) -> int:
    """
    Insert a page record.
    
    Returns: page_id
    """
    query = """
        INSERT INTO pages_t 
        (container_id, issue_id, page_index, page_label, page_type,
         has_ocr, ocr_source, ocr_text, image_file_path)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    return execute_query(
        query,
        (container_id, issue_id, page_index, page_label, page_type,
         has_ocr, ocr_source, ocr_text, image_file_path)
    )


# ============================================================================
# Works & Occurrences
# ============================================================================

def insert_work(
    work_type: str,
    title: Optional[str] = None,
    author: Optional[str] = None,
    canonical_text: Optional[str] = None,
) -> int:
    """
    Insert a work record.
    
    Returns: work_id
    """
    query = """
        INSERT INTO works_t 
        (work_type, title, author, canonical_text, dedup_status)
        VALUES (%s, %s, %s, %s, 'pending')
    """
    return execute_query(query, (work_type, title, author, canonical_text))


def insert_work_occurrence(
    work_id: int,
    issue_id: int,
    container_id: int,
    start_page_id: Optional[int] = None,
    end_page_id: Optional[int] = None,
    ocr_text: Optional[str] = None,
    is_canonical: bool = False,
) -> int:
    """
    Insert a work occurrence.
    
    Returns: occurrence_id
    """
    query = """
        INSERT INTO work_occurrences_t 
        (work_id, issue_id, container_id, start_page_id, end_page_id,
         ocr_text, is_canonical)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    return execute_query(
        query,
        (work_id, issue_id, container_id, start_page_id, end_page_id,
         ocr_text, is_canonical)
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
    if complete:
        query = f"""
            UPDATE processing_status_t 
            SET {stage}_complete = 1, {stage}_completed_at = NOW()
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
    # Simple test
    print("Testing database connection...")
    if test_connection():
        print("✓ Database connection successful")
        print(f"✓ Current schema version: {get_schema_version()}")
    else:
        print("✗ Database connection failed")
        sys.exit(1)
