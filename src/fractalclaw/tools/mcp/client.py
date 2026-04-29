"""MCP client manager for connecting to MCP servers."""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from fractalclaw.tools.mcp.config import McpConfig
from fractalclaw.tools.mcp.types import (
    McpConnectionError,
    McpConnectionStatus,
    McpExecutionError,
    McpPromptInfo,
    McpResourceInfo,
    McpServerStatus,
    McpToolCallResult,
    McpToolInfo,
)


@dataclass
class MockSession:
    """Mock session for testing without real MCP connections."""

    tools: list[dict[str, Any]] = field(default_factory=list)
    resources: list[dict[str, Any]] = field(default_factory=list)
    prompts: list[dict[str, Any]] = field(default_factory=list)


class McpClientManager:
    """Manager for MCP server connections and tool execution.

    This class provides:
    - Connection management for multiple MCP servers
    - Tool discovery and execution
    - Resource and prompt access
    - Status tracking

    Example:
        config = McpConfig.from_file("mcp.json")
        manager = McpClientManager(config)

        await manager.connect_all()
        tools = manager.list_tools()

        result = await manager.call_tool("my_server", "read", {"path": "/tmp/test.txt"})
    """

    def __init__(self, config: Optional[McpConfig] = None):
        self.config = config or McpConfig()
        self._sessions: dict[str, Any] = {}
        self._statuses: dict[str, McpServerStatus] = {}
        self._use_mock = True

    async def connect_all(self) -> dict[str, bool]:
        """Connect to all configured MCP servers.

        Returns:
            Dictionary mapping server names to connection success
        """
        results: dict[str, bool] = {}

        for name in self.config.servers:
            try:
                success = await self.connect(name)
                results[name] = success
            except Exception:
                results[name] = False

        return results

    async def connect(self, server_name: str) -> bool:
        """Connect to a specific MCP server.

        Args:
            server_name: Name of the server to connect to

        Returns:
            True if connection successful

        Raises:
            McpConnectionError: If connection fails
        """
        config = self.config.get_server(server_name)
        if config is None:
            raise McpConnectionError(f"Server '{server_name}' not found in config", server_name)

        self._update_status(server_name, McpConnectionStatus.CONNECTING)

        try:
            if self._use_mock:
                session = MockSession()
                self._sessions[server_name] = session
                self._discover_capabilities_mock(server_name, session)
            else:
                await self._connect_real(server_name, config)

            self._update_status(server_name, McpConnectionStatus.CONNECTED, connected_at=time.time())
            return True

        except Exception as e:
            self._update_status(server_name, McpConnectionStatus.ERROR, error=str(e))
            raise McpConnectionError(str(e), server_name)

    async def _connect_real(self, server_name: str, config: Any) -> None:
        """Connect to a real MCP server."""
        pass

    def _discover_capabilities_mock(self, server_name: str, session: MockSession) -> None:
        """Discover capabilities from mock session."""
        status = self._statuses.get(server_name)
        if status:
            status.tools = [
                McpToolInfo(
                    server_name=server_name,
                    tool_name=tool.get("name", "unknown"),
                    description=tool.get("description", ""),
                    input_schema=tool.get("input_schema", {}),
                )
                for tool in session.tools
            ]
            status.resources = [
                McpResourceInfo(
                    server_name=server_name,
                    uri=res.get("uri", ""),
                    name=res.get("name", ""),
                    description=res.get("description"),
                    mime_type=res.get("mime_type"),
                )
                for res in session.resources
            ]
            status.prompts = [
                McpPromptInfo(
                    server_name=server_name,
                    name=prompt.get("name", ""),
                    description=prompt.get("description"),
                    arguments=prompt.get("arguments", []),
                )
                for prompt in session.prompts
            ]

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        for server_name in list(self._sessions.keys()):
            await self.disconnect(server_name)

    async def disconnect(self, server_name: str) -> None:
        """Disconnect from a specific MCP server.

        Args:
            server_name: Name of the server to disconnect
        """
        if server_name in self._sessions:
            del self._sessions[server_name]

        self._update_status(server_name, McpConnectionStatus.DISCONNECTED)

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> McpToolCallResult:
        """Call a tool on an MCP server.

        Args:
            server_name: Name of the MCP server
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            McpToolCallResult with output or error

        Raises:
            McpConnectionError: If not connected to server
            McpExecutionError: If tool execution fails
        """
        if server_name not in self._sessions:
            raise McpConnectionError(f"Not connected to server '{server_name}'", server_name)

        try:
            if self._use_mock:
                return McpToolCallResult(
                    success=True,
                    output=f"Mock result for {tool_name} with args: {json.dumps(arguments)}",
                )
            else:
                return await self._call_tool_real(server_name, tool_name, arguments)

        except Exception as e:
            return McpToolCallResult(
                success=False,
                output="",
                error=str(e),
            )

    async def _call_tool_real(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> McpToolCallResult:
        """Call a tool on a real MCP server."""
        return McpToolCallResult(success=False, output="", error="Real MCP not implemented")

    def list_tools(self) -> list[McpToolInfo]:
        """List all tools from all connected servers.

        Returns:
            List of all available MCP tools
        """
        tools: list[McpToolInfo] = []
        for status in self._statuses.values():
            if status.status == McpConnectionStatus.CONNECTED:
                tools.extend(status.tools)
        return tools

    def list_tools_for_server(self, server_name: str) -> list[McpToolInfo]:
        """List tools for a specific server.

        Args:
            server_name: Name of the server

        Returns:
            List of tools for that server
        """
        status = self._statuses.get(server_name)
        if status and status.status == McpConnectionStatus.CONNECTED:
            return status.tools
        return []

    def list_resources(self) -> list[McpResourceInfo]:
        """List all resources from all connected servers.

        Returns:
            List of all available MCP resources
        """
        resources: list[McpResourceInfo] = []
        for status in self._statuses.values():
            if status.status == McpConnectionStatus.CONNECTED:
                resources.extend(status.resources)
        return resources

    def list_prompts(self) -> list[McpPromptInfo]:
        """List all prompts from all connected servers.

        Returns:
            List of all available MCP prompts
        """
        prompts: list[McpPromptInfo] = []
        for status in self._statuses.values():
            if status.status == McpConnectionStatus.CONNECTED:
                prompts.extend(status.prompts)
        return prompts

    def get_status(self, server_name: str) -> Optional[McpServerStatus]:
        """Get the status of a specific server.

        Args:
            server_name: Name of the server

        Returns:
            Server status or None if not found
        """
        return self._statuses.get(server_name)

    def get_all_statuses(self) -> dict[str, McpServerStatus]:
        """Get statuses of all servers.

        Returns:
            Dictionary of server name to status
        """
        return dict(self._statuses)

    def _update_status(
        self,
        server_name: str,
        status: McpConnectionStatus,
        error: Optional[str] = None,
        connected_at: Optional[float] = None,
    ) -> None:
        """Update the status of a server."""
        current = self._statuses.get(server_name)
        if current:
            current.status = status
            if error:
                current.error = error
            if connected_at:
                current.connected_at = connected_at
        else:
            self._statuses[server_name] = McpServerStatus(
                name=server_name,
                status=status,
                error=error,
                connected_at=connected_at,
            )

    def is_connected(self, server_name: str) -> bool:
        """Check if a server is connected.

        Args:
            server_name: Name of the server

        Returns:
            True if connected
        """
        status = self._statuses.get(server_name)
        return status is not None and status.status == McpConnectionStatus.CONNECTED

    def register_mock_tools(self, server_name: str, tools: list[dict[str, Any]]) -> None:
        """Register mock tools for testing.

        Args:
            server_name: Name of the server
            tools: List of tool definitions
        """
        if server_name not in self._sessions:
            self._sessions[server_name] = MockSession()
            self._update_status(server_name, McpConnectionStatus.CONNECTED, connected_at=time.time())

        session = self._sessions[server_name]
        if isinstance(session, MockSession):
            session.tools = tools
            self._discover_capabilities_mock(server_name, session)
