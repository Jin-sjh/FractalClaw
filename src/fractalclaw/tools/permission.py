"""Permission system for FractalClaw tools."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class PermissionType(str, Enum):
    """Types of permissions."""

    READ = "read"
    WRITE = "write"
    BASH = "bash"
    NETWORK = "network"
    MCP = "mcp"
    CUSTOM = "custom"


@dataclass
class PermissionRequest:
    """A request for permission to perform an action.

    Attributes:
        permission: The type of permission being requested
        patterns: Patterns describing what the permission applies to
        always: Patterns that should always be allowed (for "always allow" feature)
        metadata: Additional context about the request
    """

    permission: str
    patterns: list[str] = field(default_factory=list)
    always: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def for_file_read(cls, file_path: str) -> "PermissionRequest":
        """Create a permission request for reading a file."""
        return cls(permission=PermissionType.READ.value, patterns=[file_path], always=["*"])

    @classmethod
    def for_file_write(cls, file_path: str) -> "PermissionRequest":
        """Create a permission request for writing a file."""
        return cls(permission=PermissionType.WRITE.value, patterns=[file_path])

    @classmethod
    def for_bash_command(cls, command: str) -> "PermissionRequest":
        """Create a permission request for a bash command."""
        return cls(permission=PermissionType.BASH.value, patterns=[command])

    @classmethod
    def for_network_request(cls, url: str) -> "PermissionRequest":
        """Create a permission request for a network request."""
        return cls(permission=PermissionType.NETWORK.value, patterns=[url])


@dataclass
class PermissionResult:
    """Result of a permission request."""

    granted: bool
    always_allow: bool = False
    reason: Optional[str] = None
    session_only: bool = False


class PermissionDeniedError(Exception):
    """Raised when permission is denied."""

    def __init__(
        self,
        permission: str,
        patterns: list[str],
        reason: str = "Permission denied",
    ):
        self.permission = permission
        self.patterns = patterns
        self.reason = reason
        super().__init__(f"Permission denied for {permission}: {reason}")


@dataclass
class PermissionConfig:
    """Configuration for permission management."""

    strict_mode: bool = False
    auto_approve_read: bool = True
    auto_approve_patterns: list[str] = field(default_factory=lambda: ["*"])
    deny_patterns: list[str] = field(default_factory=list)
    require_approval_for: list[str] = field(default_factory=lambda: [PermissionType.WRITE.value, PermissionType.BASH.value])
    command_blacklist: list[str] = field(default_factory=lambda: [
        "rm -rf /",
        "rm -rf /*",
        "sudo rm",
        "mkfs",
        "dd if=",
        "> /dev/sd",
        "chmod 777 /",
        "chown root",
    ])
    command_whitelist: list[str] = field(default_factory=list)
    path_whitelist: list[str] = field(default_factory=list)
    path_blacklist: list[str] = field(default_factory=lambda: [
        "/etc/passwd",
        "/etc/shadow",
        "/root/.ssh",
        "~/.ssh",
    ])
    enable_command_validation: bool = True
    enable_path_validation: bool = True


class PermissionManager:
    """Manager for handling tool permissions.

    This class provides:
    - Pattern-based permission checking
    - "Always allow" functionality
    - Permission caching
    - Callback support for user prompts

    Example:
        manager = PermissionManager()
        manager.grant(PermissionType.READ.value, ["*.txt"], always=True)

        result = await manager.check(PermissionRequest.for_file_read("test.txt"))
        assert result.granted
    """

    def __init__(self, config: Optional[PermissionConfig] = None):
        self.config = config or PermissionConfig()
        self._allowed_patterns: dict[str, list[str]] = {}
        self._always_allowed: dict[str, list[str]] = {}
        self._denied_patterns: dict[str, list[str]] = {}
        self._session_allowed: dict[str, list[str]] = {}
        self._request_callback: Optional[Callable[[PermissionRequest], PermissionResult]] = None

    def set_request_callback(
        self, callback: Callable[[PermissionRequest], PermissionResult]
    ) -> None:
        """Set a callback for handling permission requests.

        The callback will be called when a permission needs user approval.

        Args:
            callback: Function that takes a PermissionRequest and returns a PermissionResult
        """
        self._request_callback = callback

    def grant(
        self,
        permission: str,
        patterns: list[str],
        always: bool = False,
        session_only: bool = False,
    ) -> None:
        """Grant permission for specific patterns.

        Args:
            permission: The permission type
            patterns: Patterns to grant permission for
            always: If True, permission persists across sessions
            session_only: If True, permission only lasts for current session
        """
        target_dict = (
            self._always_allowed if always else self._session_allowed if session_only else self._allowed_patterns
        )

        if permission not in target_dict:
            target_dict[permission] = []

        target_dict[permission].extend(patterns)

    def deny(self, permission: str, patterns: list[str]) -> None:
        """Deny permission for specific patterns.

        Args:
            permission: The permission type
            patterns: Patterns to deny permission for
        """
        if permission not in self._denied_patterns:
            self._denied_patterns[permission] = []
        self._denied_patterns[permission].extend(patterns)

    def revoke(self, permission: str, patterns: Optional[list[str]] = None) -> None:
        """Revoke previously granted permissions.

        Args:
            permission: The permission type
            patterns: Specific patterns to revoke (all if not specified)
        """
        for dict_name in ["_allowed_patterns", "_always_allowed", "_session_allowed"]:
            target = getattr(self, dict_name)
            if permission in target:
                if patterns:
                    target[permission] = [p for p in target[permission] if p not in patterns]
                else:
                    del target[permission]

    async def check(self, request: PermissionRequest) -> PermissionResult:
        """Check if a permission request should be granted.

        Args:
            request: The permission request to check

        Returns:
            PermissionResult indicating if permission is granted
        """
        permission = request.permission
        patterns = request.patterns

        for pattern in patterns:
            for deny_pattern in self._denied_patterns.get(permission, []):
                if self._match_pattern(pattern, deny_pattern):
                    return PermissionResult(
                        granted=False,
                        reason=f"Pattern '{pattern}' matches denied pattern '{deny_pattern}'",
                    )

        for pattern in patterns:
            for allowed_pattern in self._always_allowed.get(permission, []):
                if self._match_pattern(pattern, allowed_pattern):
                    return PermissionResult(granted=True, always_allow=True)

        for pattern in patterns:
            for allowed_pattern in self._session_allowed.get(permission, []):
                if self._match_pattern(pattern, allowed_pattern):
                    return PermissionResult(granted=True, session_only=True)

        for pattern in patterns:
            for allowed_pattern in self._allowed_patterns.get(permission, []):
                if self._match_pattern(pattern, allowed_pattern):
                    return PermissionResult(granted=True)

        if self.config.auto_approve_read and permission == PermissionType.READ.value:
            return PermissionResult(granted=True)

        for auto_pattern in self.config.auto_approve_patterns:
            for pattern in patterns:
                if self._match_pattern(pattern, auto_pattern):
                    return PermissionResult(granted=True)

        if permission in self.config.require_approval_for and self._request_callback:
            result = self._request_callback(request)
            if result.granted and result.always_allow:
                self.grant(permission, request.always or patterns, always=True)
            elif result.granted:
                self.grant(permission, patterns, session_only=True)
            return result

        if self.config.strict_mode:
            return PermissionResult(granted=False, reason="Strict mode: permission not explicitly granted")

        return PermissionResult(granted=True)

    async def request(self, request: PermissionRequest) -> PermissionResult:
        """Request permission, potentially prompting the user.

        This is an alias for check() but makes the intent clearer.

        Args:
            request: The permission request

        Returns:
            PermissionResult
        """
        return await self.check(request)

    def _match_pattern(self, value: str, pattern: str) -> bool:
        """Check if a value matches a pattern.

        Supports glob-style patterns with * and ?.

        Args:
            value: The value to check
            pattern: The pattern to match against

        Returns:
            True if the value matches the pattern
        """
        if pattern == "*":
            return True

        return fnmatch.fnmatch(value, pattern)

    def validate_command(self, command: str) -> tuple[bool, str]:
        """验证命令是否安全执行
        
        Args:
            command: 要执行的命令
            
        Returns:
            (是否安全, 原因)
        """
        if not self.config.enable_command_validation:
            return True, "Command validation disabled"
        
        command_lower = command.lower().strip()
        
        for blacklisted in self.config.command_blacklist:
            if blacklisted.lower() in command_lower:
                return False, f"Command matches blacklisted pattern: {blacklisted}"
        
        if self.config.command_whitelist:
            for whitelisted in self.config.command_whitelist:
                if self._match_pattern(command, whitelisted):
                    return True, "Command matches whitelist"
            return False, "Command not in whitelist"
        
        return True, "Command passed validation"

    def validate_path(self, path: str, permission_type: str = "read") -> tuple[bool, str]:
        """验证路径是否允许访问
        
        Args:
            path: 要访问的路径
            permission_type: 权限类型 (read/write)
            
        Returns:
            (是否允许, 原因)
        """
        if not self.config.enable_path_validation:
            return True, "Path validation disabled"
        
        import os
        expanded_path = os.path.expanduser(path)
        normalized_path = os.path.normpath(expanded_path)
        
        for blacklisted in self.config.path_blacklist:
            blacklisted_expanded = os.path.expanduser(blacklisted)
            if normalized_path.startswith(blacklisted_expanded) or blacklisted_expanded in normalized_path:
                return False, f"Path matches blacklisted pattern: {blacklisted}"
        
        if self.config.path_whitelist:
            for whitelisted in self.config.path_whitelist:
                whitelisted_expanded = os.path.expanduser(whitelisted)
                if normalized_path.startswith(whitelisted_expanded):
                    return True, "Path matches whitelist"
            return False, "Path not in whitelist"
        
        return True, "Path passed validation"

    def clear_session_permissions(self) -> None:
        """Clear all session-only permissions."""
        self._session_allowed.clear()

    def get_status(self) -> dict[str, Any]:
        """Get the current permission status.

        Returns:
            Dictionary with permission status information
        """
        return {
            "allowed": dict(self._allowed_patterns),
            "always_allowed": dict(self._always_allowed),
            "session_allowed": dict(self._session_allowed),
            "denied": dict(self._denied_patterns),
        }
