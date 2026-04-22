"""Enhanced Tool Manager for FractalClaw tools system."""

from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from fractalclaw.tools.base import (
    BaseTool,
    ToolExecutionError,
    ToolNotFoundError,
    ToolParameters,
    ToolResult,
    ToolValidationError,
)
from fractalclaw.tools.context import ToolContext, ToolContextBuilder
from fractalclaw.tools.output import OutputHandler
from fractalclaw.tools.permission import PermissionManager, PermissionRequest
from fractalclaw.tools.registry import ToolRegistry


class ToolStatus(Enum):
    """Status of a tool call."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class ToolCall:
    """Record of a tool call execution."""

    id: str
    name: str
    arguments: dict[str, Any]
    status: ToolStatus = ToolStatus.PENDING
    result: Optional[ToolResult] = None
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolConfig:
    """Configuration for tool manager."""

    max_concurrent_calls: int = 5
    default_timeout: float = 30.0
    enable_approval: bool = False
    enable_output_truncation: bool = True
    max_output_length: int = 10000
    approval_callback: Optional[Callable[[ToolCall], bool]] = None
    on_tool_start: Optional[Callable[[ToolCall], None]] = None
    on_tool_end: Optional[Callable[[ToolCall], None]] = None
    on_tool_error: Optional[Callable[[ToolCall, Exception], None]] = None


class ToolManager:
    """Enhanced tool manager with registry, permissions, and output handling.

    This manager provides:
    - Tool registration and discovery via ToolRegistry
    - Permission-based execution control
    - Output truncation and formatting
    - Execution history tracking
    - Concurrent execution support

    Example:
        manager = ToolManager()
        manager.register_tool(ReadTool())

        result = await manager.execute("read", {"file_path": "/tmp/test.txt"})
        print(result.result.output)
    """

    def __init__(
        self,
        config: Optional[ToolConfig] = None,
        registry: Optional[ToolRegistry] = None,
        permission_manager: Optional[PermissionManager] = None,
    ):
        self.config = config or ToolConfig()
        self.registry = registry or ToolRegistry()
        self.permissions = permission_manager or PermissionManager()
        self._call_history: list[ToolCall] = []
        self._call_counter = 0

    def register_tool(self, tool: BaseTool) -> None:
        """Register a tool with the manager.

        Args:
            tool: The tool to register
        """
        self.registry.register_tool(tool)

    def unregister_tool(self, name: str) -> bool:
        """Unregister a tool.

        Args:
            name: Name of the tool to unregister

        Returns:
            True if tool was unregistered
        """
        return self.registry.unregister_tool(name)

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name.

        Args:
            name: Tool name

        Returns:
            The tool or None if not found
        """
        tool = self.registry.get_tool(name)
        return tool if isinstance(tool, BaseTool) else None

    def list_tools(self) -> list[BaseTool]:
        """List all registered tools.

        Returns:
            List of tools
        """
        return self.registry.list_native_tools()

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Get JSON schemas for all tools.

        Returns:
            List of tool schemas
        """
        return self.registry.get_all_schemas()

    def _generate_call_id(self) -> str:
        """Generate a unique call ID."""
        self._call_counter += 1
        return f"call_{self._call_counter}_{uuid.uuid4().hex[:8]}"

    def _create_context(self, call_id: str, session_id: Optional[str] = None) -> ToolContext:
        """Create execution context for a tool call."""
        return (
            ToolContextBuilder()
            .session_id(session_id or "default")
            .message_id(f"msg_{uuid.uuid4().hex[:8]}")
            .agent_name("tool_manager")
            .call_id(call_id)
            .permission_manager(self.permissions)
            .build()
        )

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        context: Optional[ToolContext] = None,
        session_id: Optional[str] = None,
    ) -> ToolCall:
        """Execute a tool by name.

        Args:
            name: Name of the tool to execute
            arguments: Arguments to pass to the tool
            context: Optional execution context
            session_id: Optional session ID for context creation

        Returns:
            ToolCall with execution results

        Raises:
            ToolNotFoundError: If tool is not found
            ToolValidationError: If arguments are invalid
            ToolExecutionError: If execution fails
        """
        tool = self.get_tool(name)
        if tool is None:
            raise ToolNotFoundError(name)

        call_id = self._generate_call_id()
        call = ToolCall(
            id=call_id,
            name=name,
            arguments=arguments,
        )

        if context is None:
            context = self._create_context(call_id, session_id)

        if self.config.enable_approval and self.config.approval_callback:
            if not self.config.approval_callback(call):
                call.status = ToolStatus.FAILED
                call.error = "Tool call not approved"
                self._call_history.append(call)
                return call

        if self.config.on_tool_start:
            self.config.on_tool_start(call)

        call.status = ToolStatus.RUNNING
        start_time = time.time()

        try:
            params = tool.parameters_model(**arguments)

            if inspect.iscoroutinefunction(tool.execute):
                result = await tool.execute(params, context)
            else:
                result = tool.execute(params, context)

            if self.config.enable_output_truncation:
                result = OutputHandler.truncate_result(
                    result,
                    self.config.max_output_length,
                    call_id,
                )

            call.result = result
            call.status = ToolStatus.SUCCESS

            if self.config.on_tool_end:
                self.config.on_tool_end(call)

        except Exception as e:
            call.status = ToolStatus.FAILED
            call.error = str(e)

            if isinstance(e, ToolValidationError):
                raise
            if isinstance(e, ToolNotFoundError):
                raise

            if self.config.on_tool_error:
                self.config.on_tool_error(call, e)

        finally:
            call.execution_time = time.time() - start_time
            self._call_history.append(call)

        return call

    async def execute_batch(
        self,
        calls: list[tuple[str, dict[str, Any]]],
        session_id: Optional[str] = None,
    ) -> list[ToolCall]:
        """Execute multiple tool calls concurrently.

        Args:
            calls: List of (tool_name, arguments) tuples
            session_id: Optional session ID

        Returns:
            List of ToolCall results
        """
        semaphore = asyncio.Semaphore(self.config.max_concurrent_calls)

        async def execute_with_semaphore(
            name: str,
            arguments: dict[str, Any],
        ) -> ToolCall:
            async with semaphore:
                return await self.execute(name, arguments, session_id=session_id)

        tasks = [
            execute_with_semaphore(name, args)
            for name, args in calls
        ]

        return await asyncio.gather(*tasks)

    def get_call_history(
        self,
        status: Optional[ToolStatus] = None,
        limit: int = 100,
    ) -> list[ToolCall]:
        """Get tool call history.

        Args:
            status: Filter by status
            limit: Maximum number of calls to return

        Returns:
            List of tool calls
        """
        history = self._call_history
        if status:
            history = [c for c in history if c.status == status]
        return history[-limit:]

    def clear_history(self) -> None:
        """Clear tool call history."""
        self._call_history.clear()

    def validate_arguments(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> tuple[bool, Optional[str]]:
        """Validate tool arguments.

        Args:
            name: Tool name
            arguments: Arguments to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        tool = self.get_tool(name)
        if tool is None:
            return False, f"Tool '{name}' not found"

        try:
            tool.parameters_model(**arguments)
            return True, None
        except Exception as e:
            return False, str(e)

    def get_stats(self) -> dict[str, Any]:
        """Get manager statistics.

        Returns:
            Dictionary with statistics
        """
        history = self._call_history
        status_counts = {}
        for call in history:
            status = call.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        total_time = sum(c.execution_time for c in history)

        return {
            "total_calls": len(history),
            "status_counts": status_counts,
            "total_execution_time": total_time,
            "average_execution_time": total_time / len(history) if history else 0,
            "registry_stats": self.registry.get_stats(),
        }
