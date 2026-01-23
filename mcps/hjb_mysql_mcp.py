#!/usr/bin/env python3
"""
HJB MySQL MCP (Model Context Protocol Server)

Exposes the HJB MySQL database via MCP.
Allows Claude to query and manage HJB data.

Usage:
    python hjb_mysql_mcp.py
"""

import json
import logging
import os
import asyncio
from typing import Any, Dict, List
import mysql.connector
from mysql.connector import Error as MySQLError
from mysql.connector.pooling import MySQLConnectionPool

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Configure logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Database Configuration
DB_CONFIG = {
    'host': os.getenv('HJB_MYSQL_HOST', '162.144.14.243'),
    'port': int(os.getenv('HJB_MYSQL_PORT', '3306')),
    'user': os.getenv('HJB_MYSQL_USER', 'raneywor_hjb_app'),
    'password': os.getenv('HJB_MYSQL_PASSWORD', ''),
    'database': os.getenv('HJB_MYSQL_DATABASE', 'raneywor_hjbproject'),
}

# Connection pool configuration
POOL_NAME = "hjb_mysql_pool"
POOL_SIZE = 5


class HJBMySQLMCP:
    """MySQL operations handler for HJB database with connection pooling."""

    def __init__(self):
        self.pool = None
        self._init_pool()

    def _init_pool(self) -> bool:
        """Initialize connection pool."""
        try:
            self.pool = MySQLConnectionPool(
                pool_name=POOL_NAME,
                pool_size=POOL_SIZE,
                pool_reset_session=True,
                **DB_CONFIG
            )
            log.info(f"Connection pool '{POOL_NAME}' initialized with size {POOL_SIZE}")
            return True
        except MySQLError as e:
            log.error(f"Failed to initialize connection pool: {e}")
            return False

    def _get_connection(self):
        """Get a connection from the pool."""
        if not self.pool:
            self._init_pool()
        return self.pool.get_connection()

    def query(self, sql: str, params: List[Any] = None) -> Dict[str, Any]:
        """Execute a SELECT query using a pooled connection."""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)

            rows = cursor.fetchall()
            return {
                "success": True,
                "rows": rows,
                "count": len(rows),
                "error": None
            }
        except MySQLError as e:
            log.error(f"Query error: {e}")
            return {
                "success": False,
                "rows": [],
                "count": 0,
                "error": str(e)
            }
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()  # Returns connection to pool

    def execute(self, sql: str, params: List[Any] = None) -> Dict[str, Any]:
        """Execute an INSERT/UPDATE/DELETE query using a pooled connection."""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)

            conn.commit()
            return {
                "success": True,
                "rows_affected": cursor.rowcount,
                "last_insert_id": cursor.lastrowid,
                "error": None
            }
        except MySQLError as e:
            log.error(f"Execute error: {e}")
            if conn:
                conn.rollback()
            return {
                "success": False,
                "rows_affected": 0,
                "last_insert_id": None,
                "error": str(e)
            }
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()  # Returns connection to pool

    def list_publication_families(self) -> Dict[str, Any]:
        """List all publication families with specific columns."""
        sql = """
            SELECT family_id, family_root, family_code, display_name, family_type
            FROM publication_families_t
            ORDER BY display_name ASC
        """
        return self.query(sql)

    def get_family_by_code(self, family_code: str) -> Dict[str, Any]:
        """Get a family by its code with specific columns."""
        sql = """
            SELECT family_id, family_root, family_code, display_name, family_type, notes
            FROM publication_families_t
            WHERE family_code = %s
        """
        return self.query(sql, [family_code])

    def list_issues(self, family_id: int = None) -> Dict[str, Any]:
        """List issues, optionally filtered by family."""
        if family_id:
            sql = """
                SELECT i.*, pt.display_title
                FROM issues_t i
                JOIN publication_titles_t pt ON i.title_id = pt.title_id
                WHERE pt.family_id = %s
                ORDER BY i.issue_date DESC
            """
            return self.query(sql, [family_id])
        else:
            sql = """
                SELECT i.*, pt.display_title
                FROM issues_t i
                JOIN publication_titles_t pt ON i.title_id = pt.title_id
                ORDER BY i.issue_date DESC
                LIMIT 50
            """
            return self.query(sql)

    def list_works(self, family_id: int = None, work_type: str = None) -> Dict[str, Any]:
        """List works, optionally filtered with specific columns."""
        # Build query conditionally without WHERE 1=1 anti-pattern
        conditions = []
        params = []

        if family_id:
            conditions.append("family_id = %s")
            params.append(family_id)
        if work_type:
            conditions.append("work_type = %s")
            params.append(work_type)

        sql = "SELECT work_id, work_type, title, author, created_at FROM works_t"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY created_at DESC LIMIT 100"

        return self.query(sql, params) if params else self.query(sql)

    def get_work_occurrences(self, work_id: int) -> Dict[str, Any]:
        """Get all occurrences of a specific work with specific columns."""
        sql = """
            SELECT wo.occurrence_id, wo.work_id, wo.issue_id, wo.container_id,
                   wo.start_page_id, wo.end_page_id, wo.is_canonical,
                   i.volume_label, i.issue_label, i.issue_date_start,
                   c.source_system, c.source_identifier
            FROM work_occurrences_t wo
            JOIN issues_t i ON wo.issue_id = i.issue_id
            JOIN containers_t c ON wo.container_id = c.container_id
            WHERE wo.work_id = %s
            ORDER BY i.issue_date_start ASC
        """
        return self.query(sql, [work_id])

    def get_pipeline_stats(self) -> Dict[str, Any]:
        """Get high-level pipeline statistics using single combined query."""
        # Combine multiple COUNT queries into one for efficiency
        sql = """
            SELECT
                (SELECT COUNT(*) FROM publication_families_t) as total_families,
                (SELECT COUNT(*) FROM issues_t) as total_issues,
                (SELECT COUNT(*) FROM works_t) as total_works,
                (SELECT COUNT(*) FROM containers_t) as total_containers
        """
        result = self.query(sql)

        if not result['success'] or not result['rows']:
            return {"success": False, "error": result.get('error', 'Unknown error')}

        stats = result['rows'][0]

        # Get works by type (still separate query due to GROUP BY)
        type_result = self.query("SELECT work_type, COUNT(*) as count FROM works_t GROUP BY work_type")
        stats['works_by_type'] = {
            row['work_type']: row['count'] for row in type_result['rows']
        } if type_result['rows'] else {}

        return {
            "success": True,
            "stats": stats
        }

    def disconnect(self):
        """Close connection pool (no-op for pooled connections, they auto-return)."""
        # Connection pool handles cleanup automatically
        # Individual connections are returned to pool when closed
        log.info("MCP disconnect called - pool connections auto-managed")


# Initialize the MCP server
app = Server("hjb-mysql")
db = HJBMySQLMCP()


@app.list_tools()
async def list_tools() -> list[Tool]:
    """Define available tools for Claude."""
    return [
        Tool(
            name="query",
            description="Execute a SELECT query on the HJB database",
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "The SQL SELECT query to execute"
                    },
                    "params": {
                        "type": "array",
                        "description": "Optional parameters for the query",
                        "items": {"type": "string"}
                    }
                },
                "required": ["sql"]
            }
        ),
        Tool(
            name="execute",
            description="Execute an INSERT/UPDATE/DELETE query on the HJB database",
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "The SQL query to execute"
                    },
                    "params": {
                        "type": "array",
                        "description": "Optional parameters for the query",
                        "items": {"type": "string"}
                    }
                },
                "required": ["sql"]
            }
        ),
        Tool(
            name="list_publication_families",
            description="List all publication families in the database",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_family_by_code",
            description="Get a publication family by its code",
            inputSchema={
                "type": "object",
                "properties": {
                    "family_code": {
                        "type": "string",
                        "description": "The family code to look up"
                    }
                },
                "required": ["family_code"]
            }
        ),
        Tool(
            name="list_issues",
            description="List issues, optionally filtered by family",
            inputSchema={
                "type": "object",
                "properties": {
                    "family_id": {
                        "type": "integer",
                        "description": "Optional family ID to filter by"
                    }
                }
            }
        ),
        Tool(
            name="list_works",
            description="List works, optionally filtered by family and type",
            inputSchema={
                "type": "object",
                "properties": {
                    "family_id": {
                        "type": "integer",
                        "description": "Optional family ID to filter by"
                    },
                    "work_type": {
                        "type": "string",
                        "description": "Optional work type to filter by"
                    }
                }
            }
        ),
        Tool(
            name="get_work_occurrences",
            description="Get all occurrences of a specific work",
            inputSchema={
                "type": "object",
                "properties": {
                    "work_id": {
                        "type": "integer",
                        "description": "The work ID to look up"
                    }
                },
                "required": ["work_id"]
            }
        ),
        Tool(
            name="get_pipeline_stats",
            description="Get high-level pipeline statistics",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls from Claude."""
    try:
        if name == "query":
            result = db.query(arguments.get('sql'), arguments.get('params'))
        elif name == "execute":
            result = db.execute(arguments.get('sql'), arguments.get('params'))
        elif name == "list_publication_families":
            result = db.list_publication_families()
        elif name == "get_family_by_code":
            result = db.get_family_by_code(arguments.get('family_code'))
        elif name == "list_issues":
            result = db.list_issues(arguments.get('family_id'))
        elif name == "list_works":
            result = db.list_works(arguments.get('family_id'), arguments.get('work_type'))
        elif name == "get_work_occurrences":
            result = db.get_work_occurrences(arguments.get('work_id'))
        elif name == "get_pipeline_stats":
            result = db.get_pipeline_stats()
        else:
            result = {"success": False, "error": f"Unknown tool: {name}"}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return [TextContent(type="text", text=json.dumps(error_result, indent=2))]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        db.disconnect()
