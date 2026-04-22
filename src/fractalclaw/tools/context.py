"""Tool execution context for FractalClaw tools system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from fractalclaw.tools.permission import PermissionManager, PermissionRequest, PermissionResult


@dataclass
class ToolContext:
    """Tool execution context providing session info and permission access.

    This context is passed to tool execute methods and provides:
    - Session and message identification
    - Permission checking and requesting
    - Metadata recording
    - Abort signal handling

    Example:
        async def execute(self, params: ReadParameters, ctx: ToolContext) -> ToolResult:
            # Request permission
            await ctx.ask_permission(PermissionRequest(
                permission="read",
                patterns=[params.file_path],
                always=["*"]
            ))

            # Record metadata
            ctx.metadata("Reading file", {"path": params.file_path})

            # Execute tool logic
            content = await self._read_file(params.file_path)
            return ToolResult(title="file.txt", output=content)
    """

    session_id: str
    message_id: str
    agent_name: str
    call_id: Optional[str] = None
    depth: int = 0
    parent_call_id: Optional[str] = None

    _permission_manager: Optional["PermissionManager"] = field(default=None, repr=False)
    _metadata_entries: list[dict[str, Any]] = field(default_factory=list, repr=False)
    _on_abort: Optional[Callable[[], bool]] = field(default=None, repr=False)
    _permission_callback: Optional[
        Callable[["PermissionRequest"], "PermissionResult"]
    ] = field(default=None, repr=False)

    def set_permission_manager(self, manager: "PermissionManager") -> None:
        """Set the permission manager for this context."""
        self._permission_manager = manager

    def set_permission_callback(
        self, callback: Callable[["PermissionRequest"], "PermissionResult"]
    ) -> None:
        """Set a callback for permission requests.

        This allows custom permission handling, e.g., prompting the user.
        """
        self._permission_callback = callback

    def set_abort_handler(self, handler: Callable[[], bool]) -> None:
        """Set an abort handler that returns True if execution should stop."""
        self._on_abort = handler

    async def ask_permission(self, request: "PermissionRequest") -> bool:
        """Request permission for an action.

        Args:
            request: The permission request describing the action

        Returns:
            True if permission is granted, False otherwise

        Raises:
            PermissionDeniedError: If permission is denied and strict mode is enabled
        """
        from fractalclaw.tools.permission import PermissionDeniedError

        if self._permission_callback is not None:
            result = self._permission_callback(request)
            if result.granted:
                return True
            raise PermissionDeniedError(
                request.permission, request.patterns, result.reason or "Permission denied"
            )

        if self._permission_manager is not None:
            result = await self._permission_manager.check(request)
            if result.granted:
                return True
            raise PermissionDeniedError(
                request.permission, request.patterns, result.reason or "Permission denied"
            )

        return True

    def metadata(self, title: str, data: Optional[dict[str, Any]] = None) -> None:
        """Record metadata about the tool execution.

        Args:
            title: A short title for this metadata entry
            data: Optional additional data
        """
        entry: dict[str, Any] = {"title": title}
        if data:
            entry["data"] = data
        self._metadata_entries.append(entry)

    def get_metadata(self) -> list[dict[str, Any]]:
        """Get all recorded metadata entries."""
        return self._metadata_entries.copy()

    def is_aborted(self) -> bool:
        """Check if execution should be aborted."""
        if self._on_abort is None:
            return False
        return self._on_abort()

    def create_child_context(self, call_id: str) -> "ToolContext":
        """Create a child context for nested tool calls."""
        return ToolContext(
            session_id=self.session_id,
            message_id=self.message_id,
            agent_name=self.agent_name,
            call_id=call_id,
            depth=self.depth + 1,
            parent_call_id=self.call_id,
            _permission_manager=self._permission_manager,
            _on_abort=self._on_abort,
            _permission_callback=self._permission_callback,
        )


@dataclass
class ToolContextBuilder:
    """Builder for creating ToolContext instances with fluent API."""

    _session_id: str = ""
    _message_id: str = ""
    _agent_name: str = ""
    _call_id: Optional[str] = None
    _depth: int = 0
    _parent_call_id: Optional[str] = None
    _permission_manager: Optional["PermissionManager"] = None
    _on_abort: Optional[Callable[[], bool]] = None
    _permission_callback: Optional[Callable[["PermissionRequest"], "PermissionResult"]] = None

    def session_id(self, session_id: str) -> "ToolContextBuilder":
        """Set the session ID."""
        self._session_id = session_id
        return self

    def message_id(self, message_id: str) -> "ToolContextBuilder":
        """Set the message ID."""
        self._message_id = message_id
        return self

    def agent_name(self, agent_name: str) -> "ToolContextBuilder":
        """Set the agent name."""
        self._agent_name = agent_name
        return self

    def call_id(self, call_id: str) -> "ToolContextBuilder":
        """Set the call ID."""
        self._call_id = call_id
        return self

    def depth(self, depth: int) -> "ToolContextBuilder":
        """Set the depth."""
        self._depth = depth
        return self

    def parent_call_id(self, parent_call_id: str) -> "ToolContextBuilder":
        """Set the parent call ID."""
        self._parent_call_id = parent_call_id
        return self

    def permission_manager(self, manager: "PermissionManager") -> "ToolContextBuilder":
        """Set the permission manager."""
        self._permission_manager = manager
        return self

    def abort_handler(self, handler: Callable[[], bool]) -> "ToolContextBuilder":
        """Set the abort handler."""
        self._on_abort = handler
        return self

    def permission_callback(
        self, callback: Callable[["PermissionRequest"], "PermissionResult"]
    ) -> "ToolContextBuilder":
        """Set the permission callback."""
        self._permission_callback = callback
        return self

    def build(self) -> ToolContext:
        """Build the ToolContext instance."""
        return ToolContext(
            session_id=self._session_id,
            message_id=self._message_id,
            agent_name=self._agent_name,
            call_id=self._call_id,
            depth=self._depth,
            parent_call_id=self._parent_call_id,
            _permission_manager=self._permission_manager,
            _on_abort=self._on_abort,
            _permission_callback=self._permission_callback,
        )
