"""MCP (Model Context Protocol) module for FractalClaw."""

from fractalclaw.tools.mcp.client import McpClientManager
from fractalclaw.tools.mcp.config import (
    McpConfig,
    load_mcp_config,
    resolve_http_config,
    resolve_stdio_config,
)
from fractalclaw.tools.mcp.types import (
    McpConnectionError,
    McpConnectionStatus,
    McpError,
    McpExecutionError,
    McpHttpConfig,
    McpPromptInfo,
    McpResourceInfo,
    McpServerConfig,
    McpServerStatus,
    McpStdioConfig,
    McpToolCallResult,
    McpToolInfo,
    McpToolNotFoundError,
)

__all__ = [
    "McpClientManager",
    "McpConfig",
    "McpConnectionError",
    "McpConnectionStatus",
    "McpError",
    "McpExecutionError",
    "McpHttpConfig",
    "McpPromptInfo",
    "McpResourceInfo",
    "McpServerConfig",
    "McpServerStatus",
    "McpStdioConfig",
    "McpToolCallResult",
    "McpToolInfo",
    "McpToolNotFoundError",
    "load_mcp_config",
    "resolve_http_config",
    "resolve_stdio_config",
]
