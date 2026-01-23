#!/usr/bin/env python3
"""
HJB NAS MCP (Model Context Protocol Server)

Exposes the HJB NAS directory structure and file operations.
Allows Claude to browse, inspect, and read files from the NAS.

Usage:
    python hjb_nas_mcp.py
"""

import json
import os
import stat
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# NAS Configuration
NAS_ROOT = os.getenv('HJB_NAS_ROOT', r'\\RaneyHQ\Michael\02_Projects\Historical_Journals_And_Books')
MAX_FILE_SIZE = int(os.getenv('HJB_MAX_FILE_SIZE', 1024 * 1024))  # 1MB default
MAX_ITEMS_IN_LIST = int(os.getenv('HJB_MAX_ITEMS_IN_LIST', 100))


class HJBNASMCP:
    """NAS operations handler for HJB project."""

    def __init__(self):
        self.nas_root = Path(NAS_ROOT)
        if not self.nas_root.exists():
            print(f"WARNING: NAS root not accessible: {self.nas_root}")

    def _safe_path(self, relative_path: str) -> Optional[Path]:
        """Resolve a relative path safely (prevent directory traversal)."""
        try:
            resolved = (self.nas_root / relative_path).resolve()
            resolved.relative_to(self.nas_root.resolve())
            return resolved
        except (ValueError, OSError):
            return None

    def list_directory(self, path: str = "") -> Dict[str, Any]:
        """List contents of a directory."""
        target_path = self._safe_path(path)
        
        if not target_path:
            return {
                "success": False,
                "path": path,
                "items": [],
                "error": "Invalid path or path traversal detected"
            }
        
        if not target_path.exists():
            return {
                "success": False,
                "path": path,
                "items": [],
                "error": f"Path does not exist: {path}"
            }
        
        if not target_path.is_dir():
            return {
                "success": False,
                "path": path,
                "items": [],
                "error": f"Path is not a directory: {path}"
            }
        
        try:
            items = []
            for entry in sorted(target_path.iterdir()):
                try:
                    rel_path = str(entry.relative_to(self.nas_root))
                    # Single stat call for all metadata
                    st = entry.stat()
                    is_dir = stat.S_ISDIR(st.st_mode)

                    item = {
                        "name": entry.name,
                        "type": "dir" if is_dir else "file",
                        "path": rel_path,
                        "modified": datetime.fromtimestamp(st.st_mtime).isoformat()
                    }

                    if not is_dir:
                        item["size"] = st.st_size

                    items.append(item)

                    if len(items) >= MAX_ITEMS_IN_LIST:
                        items.append({
                            "name": "... (truncated)",
                            "type": "notice",
                            "message": f"Listing limited to {MAX_ITEMS_IN_LIST} items"
                        })
                        break

                except (OSError, ValueError):
                    continue
            
            return {
                "success": True,
                "path": path,
                "items": items,
                "error": None
            }
        
        except Exception as e:
            return {
                "success": False,
                "path": path,
                "items": [],
                "error": str(e)
            }

    def read_file(self, path: str) -> Dict[str, Any]:
        """Read file contents (text files only, up to MAX_FILE_SIZE)."""
        target_path = self._safe_path(path)
        
        if not target_path:
            return {
                "success": False,
                "path": path,
                "error": "Invalid path or path traversal detected"
            }
        
        if not target_path.exists():
            return {
                "success": False,
                "path": path,
                "error": f"File not found: {path}"
            }
        
        if not target_path.is_file():
            return {
                "success": False,
                "path": path,
                "error": f"Path is not a file: {path}"
            }
        
        try:
            size = target_path.stat().st_size
            
            if size > MAX_FILE_SIZE:
                return {
                    "success": False,
                    "path": path,
                    "size": size,
                    "error": f"File too large ({size} bytes > {MAX_FILE_SIZE} limit)"
                }
            
            with open(target_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            return {
                "success": True,
                "path": path,
                "size": size,
                "content": content,
                "truncated": False,
                "error": None
            }
        
        except Exception as e:
            return {
                "success": False,
                "path": path,
                "error": str(e)
            }

    def read_json_file(self, path: str) -> Dict[str, Any]:
        """Read and parse a JSON file."""
        file_result = self.read_file(path)
        
        if not file_result.get('success'):
            return file_result
        
        try:
            content = json.loads(file_result['content'])
            return {
                "success": True,
                "path": path,
                "data": content,
                "error": None
            }
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "path": path,
                "error": f"Invalid JSON at line {e.lineno}, column {e.colno}: {e.msg}"
            }

    def get_file_info(self, path: str) -> Dict[str, Any]:
        """Get metadata about a file or directory."""
        target_path = self._safe_path(path)
        
        if not target_path:
            return {
                "success": False,
                "path": path,
                "error": "Invalid path or path traversal detected"
            }
        
        if not target_path.exists():
            return {
                "success": False,
                "path": path,
                "error": "Path does not exist"
            }
        
        try:
            stat = target_path.stat()
            info = {
                "success": True,
                "path": path,
                "name": target_path.name,
                "type": "directory" if target_path.is_dir() else "file",
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "is_dir": target_path.is_dir(),
                "is_file": target_path.is_file(),
            }
            
            if target_path.is_dir():
                try:
                    # Use generator with sum for efficient counting without building list
                    info['item_count'] = sum(1 for _ in target_path.iterdir())
                except OSError:
                    pass
            
            return info
        
        except Exception as e:
            return {
                "success": False,
                "path": path,
                "error": str(e)
            }

    def find_files(self, pattern: str, search_path: str = "", max_results: int = 50) -> Dict[str, Any]:
        """Search for files matching a pattern (glob-style)."""
        start_path = self._safe_path(search_path)
        
        if not start_path:
            return {
                "success": False,
                "error": "Invalid search path"
            }
        
        if not start_path.exists():
            return {
                "success": False,
                "error": f"Search path not found: {search_path}"
            }
        
        try:
            results = []
            for match in start_path.glob(pattern):
                rel_path = str(match.relative_to(self.nas_root))
                # Single stat call to determine type and size
                try:
                    st = match.stat()
                    is_dir = stat.S_ISDIR(st.st_mode)
                    results.append({
                        "path": rel_path,
                        "name": match.name,
                        "type": "directory" if is_dir else "file",
                        "size": None if is_dir else st.st_size
                    })
                except OSError:
                    # Skip files we can't stat
                    continue

                if len(results) >= max_results:
                    break
            
            return {
                "success": True,
                "pattern": pattern,
                "search_path": search_path,
                "results": results,
                "count": len(results),
                "truncated": len(results) >= max_results
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def list_flag_tasks(self, status: str = None) -> Dict[str, Any]:
        """List task flag files from Working_Files/0200_STATE/flags."""
        flags_path = self._safe_path("Working_Files/0200_STATE/flags")
        
        if not flags_path or not flags_path.exists():
            return {
                "success": False,
                "error": "Flags directory not found"
            }
        
        tasks = {}
        statuses = [status] if status else ["pending", "processing", "completed", "failed"]
        
        for s in statuses:
            status_dir = flags_path / s
            if not status_dir.exists():
                continue
            
            tasks[s] = []
            for flag_file in status_dir.glob("*.json"):
                try:
                    with open(flag_file, 'r') as f:
                        flag_data = json.load(f)
                    
                    tasks[s].append({
                        "file": flag_file.name,
                        "task_id": flag_data.get('task_id'),
                        "task_type": flag_data.get('task_type'),
                        "status": flag_data.get('status'),
                        "created_at": flag_data.get('created_at'),
                        "error": flag_data.get('error'),
                    })
                except:
                    pass
        
        return {
            "success": True,
            "tasks": tasks
        }

    def get_watcher_heartbeat(self) -> Dict[str, Any]:
        """Get the watcher heartbeat status."""
        heartbeat_path = self._safe_path("Working_Files/0200_STATE/watcher_heartbeat.json")
        
        if not heartbeat_path or not heartbeat_path.exists():
            return {
                "success": False,
                "status": "unknown",
                "error": "Heartbeat file not found"
            }
        
        return self.read_json_file("Working_Files/0200_STATE/watcher_heartbeat.json")


# Initialize the MCP server
app = Server("hjb-nas")
nas = HJBNASMCP()


@app.list_tools()
async def list_tools() -> list[Tool]:
    """Define available tools for Claude."""
    return [
        Tool(
            name="list_directory",
            description="List contents of a directory on the HJB NAS",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from NAS root (empty string for root)"
                    }
                }
            }
        ),
        Tool(
            name="read_file",
            description="Read the contents of a text file from the NAS",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file from NAS root"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="read_json_file",
            description="Read and parse a JSON file from the NAS",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the JSON file from NAS root"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="get_file_info",
            description="Get metadata about a file or directory",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from NAS root"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="find_files",
            description="Search for files matching a glob pattern",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g., '*.json', '**/*.log')"
                    },
                    "search_path": {
                        "type": "string",
                        "description": "Starting path for search (empty for root)"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return"
                    }
                },
                "required": ["pattern"]
            }
        ),
        Tool(
            name="list_flag_tasks",
            description="List task flag files from the state directory",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status: pending, processing, completed, failed, or null for all"
                    }
                }
            }
        ),
        Tool(
            name="get_watcher_heartbeat",
            description="Get the watcher heartbeat status",
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
        if name == "list_directory":
            result = nas.list_directory(arguments.get('path', ''))
        elif name == "read_file":
            result = nas.read_file(arguments.get('path'))
        elif name == "read_json_file":
            result = nas.read_json_file(arguments.get('path'))
        elif name == "get_file_info":
            result = nas.get_file_info(arguments.get('path'))
        elif name == "find_files":
            result = nas.find_files(
                arguments.get('pattern'),
                arguments.get('search_path', ''),
                arguments.get('max_results', 50)
            )
        elif name == "list_flag_tasks":
            result = nas.list_flag_tasks(arguments.get('status'))
        elif name == "get_watcher_heartbeat":
            result = nas.get_watcher_heartbeat()
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
    asyncio.run(main())
