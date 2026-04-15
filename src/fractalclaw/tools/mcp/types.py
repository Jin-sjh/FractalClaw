"""MCP (Model Context Protocol) type definitions."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Literal, Optional, Union


class McpConnectionStatus(str, Enum):
    """MCP connection status."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class McpStdioConfig:
    """Configuration for MCP stdio transport."""

    type: Literal["stdio"] = "stdio"
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type,
            "command": self.command,
            "args": self.args,
            "env": self.env,
            "cwd": self.cwd,
        }


@dataclass
class McpHttpConfig:
    """Configuration for MCP HTTP transport."""

    type: Literal["http"] = "http"
    url: str = ""
    headers: Optional[dict[str, str]] = None
    timeout: float = 30.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type,
            "url": self.url,
            "headers": self.headers,
            "timeout": self.timeout,
        }


McpServerConfig = Union[McpStdioConfig, McpHttpConfig]


@dataclass
class McpToolInfo:
    """Information about an MCP tool."""

    server_name: str
    tool_name: str
    description: str
    input_schema: dict[str, Any]

    @property
    def full_name(self) -> str:
        """Get the full tool name including server prefix."""
        return f"{self.server_name}.{self.tool_name}"

    def to_schema(self) -> dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.tool_name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def to_info(self) -> dict[str, Any]:
        """Get detailed info dictionary."""
        return {
            "server_name": self.server_name,
            "tool_name": self.tool_name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


@dataclass
class McpResourceInfo:
    """Information about an MCP resource."""

    server_name: str
    uri: str
    name: str
    description: Optional[str] = None
    mime_type: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "server_name": self.server_name,
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mime_type": self.mime_type,
        }


@dataclass
class McpPromptInfo:
    """Information about an MCP prompt template."""

    server_name: str
    name: str
    description: Optional[str] = None
    arguments: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "server_name": self.server_name,
            "name": self.name,
            "description": self.description,
            "arguments": self.arguments,
        }


@dataclass
class McpServerStatus:
    """Status of an MCP server connection."""

    name: str
    status: McpConnectionStatus
    tools: list[McpToolInfo] = field(default_factory=list)
    resources: list[McpResourceInfo] = field(default_factory=list)
    prompts: list[McpPromptInfo] = field(default_factory=list)
    error: Optional[str] = None
    connected_at: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "status": self.status.value,
            "tools_count": len(self.tools),
            "resources_count": len(self.resources),
            "prompts_count": len(self.prompts),
            "error": self.error,
            "connected_at": self.connected_at,
        }


@dataclass
class McpToolCallResult:
    """Result of an MCP tool call."""

    success: bool
    output: str
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class McpError(Exception):
    """Base exception for MCP errors."""

    def __init__(self, message: str, server_name: Optional[str] = None):
        self.server_name = server_name
        super().__init__(f"MCP Error [{server_name}]: {message}" if server_name else f"MCP Error: {message}")


class McpConnectionError(McpError):
    """Raised when MCP connection fails."""

    pass


class McpToolNotFoundError(McpError):
    """Raised when an MCP tool is not found."""

    def __init__(self, tool_name: str, server_name: Optional[str] = None):
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' not found", server_name)


class McpExecutionError(McpError):
    """Raised when MCP tool execution fails."""

    def __init__(self, tool_name: str, message: str, server_name: Optional[str] = None):
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' execution failed: {message}", server_name)
