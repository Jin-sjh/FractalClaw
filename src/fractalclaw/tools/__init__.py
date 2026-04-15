"""Tools module for FractalClaw - comprehensive tools system.

This module provides:
- BaseTool: Abstract base class for defining tools
- ToolManager: Execution management with permissions and output handling
- ToolRegistry: Unified tool registration and discovery
- Skills: Markdown-based skill definitions
- MCP: Model Context Protocol integration
- Builtin tools: File operations, search, etc.
"""

from fractalclaw.tools.base import (
    BaseTool,
    ToolExecutionError,
    ToolInfo,
    ToolNotFoundError,
    ToolParameters,
    ToolResult,
    ToolValidationError,
)
from fractalclaw.tools.context import ToolContext, ToolContextBuilder
from fractalclaw.tools.manager import ToolCall, ToolConfig, ToolManager, ToolStatus
from fractalclaw.tools.output import OutputConfig, OutputHandler, TruncatedOutput
from fractalclaw.tools.permission import (
    PermissionConfig,
    PermissionDeniedError,
    PermissionManager,
    PermissionRequest,
    PermissionResult,
    PermissionType,
)
from fractalclaw.tools.registry import RegistryStats, ToolRegistry, create_registry_with_builtin_tools

__all__ = [
    "BaseTool",
    "ToolParameters",
    "ToolResult",
    "ToolInfo",
    "ToolNotFoundError",
    "ToolExecutionError",
    "ToolValidationError",
    "ToolContext",
    "ToolContextBuilder",
    "ToolManager",
    "ToolConfig",
    "ToolCall",
    "ToolStatus",
    "ToolRegistry",
    "RegistryStats",
    "create_registry_with_builtin_tools",
    "OutputHandler",
    "OutputConfig",
    "TruncatedOutput",
    "PermissionManager",
    "PermissionConfig",
    "PermissionRequest",
    "PermissionResult",
    "PermissionType",
    "PermissionDeniedError",
]
