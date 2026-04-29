"""Centralized tool mapping definitions.

Consolidates tool aliases, role-based defaults, runtime type mappings,
and tool templates that were previously scattered across factory.py
and config_generator.py.
"""

from __future__ import annotations

from typing import Any

BUILTIN_TOOL_ALIASES: dict[str, str] = {
    "read_file": "read",
    "write_file": "write",
    "edit_file": "edit",
    "python": "bash",
    "web_search": "tavily_search",
    "web_search_skill": "tavily_search",
    "find": "find_files",
}

ROLE_DEFAULT_TOOLS: dict[str, list[str]] = {
    "root": [
        "read",
        "write",
        "edit",
        "search",
        "find_files",
        "bash",
        "tavily_search",
        "llm_generate",
    ],
    "coordinator": [
        "read",
        "write",
        "edit",
        "search",
        "find_files",
        "bash",
        "tavily_search",
        "llm_generate",
    ],
    "worker": ["read", "write", "edit", "bash", "search", "find_files"],
    "specialist": ["read", "write", "edit", "bash", "search", "find_files"],
}

RUNTIME_TYPE_TOOLS: dict[str, list[str]] = {
    "coder": ["read", "write", "edit", "bash", "search", "find_files"],
    "code": ["read", "write", "edit", "bash", "search", "find_files"],
    "developer": ["read", "write", "edit", "bash", "search", "find_files"],
    "researcher": ["read", "search", "find_files", "tavily_search", "llm_generate"],
    "research": ["read", "search", "find_files", "tavily_search", "llm_generate"],
    "analyst": ["read", "search", "find_files", "tavily_search", "llm_generate"],
    "coordinator": ["read", "write", "edit", "search", "find_files", "bash", "llm_generate"],
}

TOOL_TEMPLATES: dict[str, dict[str, Any]] = {
    "read_file": {
        "name": "read_file",
        "description": "读取文件内容",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"}
            },
            "required": ["path"]
        }
    },
    "write_file": {
        "name": "write_file",
        "description": "写入文件内容",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "文件内容"}
            },
            "required": ["path", "content"]
        }
    },
    "execute_code": {
        "name": "execute_code",
        "description": "执行代码",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "要执行的代码"},
                "language": {"type": "string", "description": "编程语言", "default": "python"}
            },
            "required": ["code"]
        }
    },
    "web_search": {
        "name": "web_search",
        "description": "网络搜索",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询"}
            },
            "required": ["query"]
        }
    },
}
