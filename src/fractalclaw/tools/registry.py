"""Tool registry for managing tool registration and discovery."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional, Union

from fractalclaw.tools.base import BaseTool, ToolInfo, ToolNotFoundError

if TYPE_CHECKING:
    from fractalclaw.tools.skills.types import SkillEntry
    from fractalclaw.tools.mcp.types import McpToolInfo


@dataclass
class RegistryStats:
    """Statistics about the tool registry."""

    total_tools: int = 0
    native_tools: int = 0
    mcp_tools: int = 0
    skills: int = 0
    categories: dict[str, int] = field(default_factory=dict)


class ToolRegistry:
    """Unified registry for all tool types.

    This registry manages:
    - Native tools (BaseTool subclasses)
    - MCP tools (remote tools via Model Context Protocol)
    - Skills (knowledge-based tool guidance)

    Example:
        registry = ToolRegistry()
        registry.register_tool(ReadTool())
        registry.register_mcp_tool(mcp_tool)

        tool = registry.get_tool("read")
        schemas = registry.get_all_schemas()
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._mcp_tools: dict[str, "McpToolInfo"] = {}
        self._skills: dict[str, "SkillEntry"] = {}
        self._tool_aliases: dict[str, str] = {}

    def register_tool(self, tool: BaseTool) -> None:
        """Register a native tool.

        Args:
            tool: The tool instance to register

        Raises:
            ValueError: If a tool with the same name already exists
        """
        name = tool.name
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered")
        self._tools[name] = tool

    def register_tool_with_alias(self, tool: BaseTool, aliases: list[str]) -> None:
        """Register a tool with additional aliases.

        Args:
            tool: The tool instance to register
            aliases: List of alternative names for the tool
        """
        self.register_tool(tool)
        for alias in aliases:
            self._tool_aliases[alias] = tool.name

    def unregister_tool(self, name: str) -> bool:
        """Unregister a tool by name.

        Args:
            name: The tool name to unregister

        Returns:
            True if the tool was unregistered, False if not found
        """
        if name in self._tools:
            del self._tools[name]
            aliases_to_remove = [a for a, t in self._tool_aliases.items() if t == name]
            for alias in aliases_to_remove:
                del self._tool_aliases[alias]
            return True
        return False

    def register_mcp_tool(self, tool: "McpToolInfo") -> None:
        """Register an MCP tool.

        Args:
            tool: The MCP tool info to register
        """
        key = f"{tool.server_name}.{tool.tool_name}"
        self._mcp_tools[key] = tool
        if tool.tool_name not in self._tools and tool.tool_name not in self._mcp_tools:
            self._tool_aliases[tool.tool_name] = key

    def unregister_mcp_tool(self, server_name: str, tool_name: str) -> bool:
        """Unregister an MCP tool.

        Args:
            server_name: The MCP server name
            tool_name: The tool name

        Returns:
            True if the tool was unregistered
        """
        key = f"{server_name}.{tool_name}"
        if key in self._mcp_tools:
            del self._mcp_tools[key]
            if self._tool_aliases.get(tool_name) == key:
                del self._tool_aliases[tool_name]
            return True
        return False

    def register_skill(self, skill: "SkillEntry") -> None:
        """Register a skill.

        Args:
            skill: The skill entry to register
        """
        self._skills[skill.name] = skill

    def unregister_skill(self, name: str) -> bool:
        """Unregister a skill.

        Args:
            name: The skill name

        Returns:
            True if the skill was unregistered
        """
        if name in self._skills:
            del self._skills[name]
            return True
        return False

    def get_tool(self, name: str) -> Optional[Union[BaseTool, "McpToolInfo"]]:
        """Get a tool by name or alias.

        Args:
            name: The tool name or alias

        Returns:
            The tool if found, None otherwise
        """
        if name in self._tools:
            return self._tools[name]

        if name in self._tool_aliases:
            resolved_name = self._tool_aliases[name]
            if resolved_name in self._tools:
                return self._tools[resolved_name]
            if resolved_name in self._mcp_tools:
                return self._mcp_tools[resolved_name]

        if name in self._mcp_tools:
            return self._mcp_tools[name]

        return None

    def get_tool_or_raise(self, name: str) -> Union[BaseTool, "McpToolInfo"]:
        """Get a tool by name, raising an error if not found.

        Args:
            name: The tool name

        Returns:
            The tool

        Raises:
            ToolNotFoundError: If the tool is not found
        """
        tool = self.get_tool(name)
        if tool is None:
            raise ToolNotFoundError(name)
        return tool

    def get_skill(self, name: str) -> Optional["SkillEntry"]:
        """Get a skill by name.

        Args:
            name: The skill name

        Returns:
            The skill if found, None otherwise
        """
        return self._skills.get(name)

    def list_tools(self) -> list[Union[BaseTool, "McpToolInfo"]]:
        """List all registered tools.

        Returns:
            List of all tools
        """
        tools: list[Union[BaseTool, "McpToolInfo"]] = list(self._tools.values())
        tools.extend(self._mcp_tools.values())
        return tools

    def list_native_tools(self) -> list[BaseTool]:
        """List all native tools.

        Returns:
            List of native tools
        """
        return list(self._tools.values())

    def list_mcp_tools(self) -> list["McpToolInfo"]:
        """List all MCP tools.

        Returns:
            List of MCP tools
        """
        return list(self._mcp_tools.values())

    def list_skills(self) -> list["SkillEntry"]:
        """List all registered skills.

        Returns:
            List of skills
        """
        return list(self._skills.values())

    def get_all_schemas(self) -> list[dict[str, Any]]:
        """Get JSON schemas for all tools.

        Returns:
            List of tool schemas in Anthropic format
        """
        schemas = []
        for tool in self._tools.values():
            schemas.append(tool.to_schema())
        for tool in self._mcp_tools.values():
            schemas.append(tool.to_schema())
        return schemas

    def get_tool_infos(self) -> list[ToolInfo]:
        """Get detailed info for all tools.

        Returns:
            List of ToolInfo objects
        """
        infos = []
        for tool in self._tools.values():
            infos.append(tool.to_info())
        for tool in self._mcp_tools.values():
            infos.append(tool.to_info())
        return infos

    def get_stats(self) -> RegistryStats:
        """Get registry statistics.

        Returns:
            RegistryStats with counts and categories
        """
        categories: dict[str, int] = {}
        for tool in self._tools.values():
            cat = tool.category
            categories[cat] = categories.get(cat, 0) + 1

        return RegistryStats(
            total_tools=len(self._tools) + len(self._mcp_tools),
            native_tools=len(self._tools),
            mcp_tools=len(self._mcp_tools),
            skills=len(self._skills),
            categories=categories,
        )

    def clear(self) -> None:
        """Clear all registered tools, MCP tools, and skills."""
        self._tools.clear()
        self._mcp_tools.clear()
        self._skills.clear()
        self._tool_aliases.clear()

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered.

        Args:
            name: The tool name

        Returns:
            True if the tool exists
        """
        return self.get_tool(name) is not None

    def has_skill(self, name: str) -> bool:
        """Check if a skill is registered.

        Args:
            name: The skill name

        Returns:
            True if the skill exists
        """
        return name in self._skills

    def get_tools_by_category(self, category: str) -> list[BaseTool]:
        """Get all tools in a category.

        Args:
            category: The category name

        Returns:
            List of tools in the category
        """
        return [t for t in self._tools.values() if t.category == category]

    def get_tools_by_tag(self, tag: str) -> list[BaseTool]:
        """Get all tools with a specific tag.

        Args:
            tag: The tag to search for

        Returns:
            List of tools with the tag
        """
        return [t for t in self._tools.values() if tag in t.tags]


def create_registry_with_builtin_tools() -> ToolRegistry:
    """Create a registry pre-populated with builtin tools.

    Returns:
        ToolRegistry with builtin tools registered
    """
    registry = ToolRegistry()

    try:
        from fractalclaw.tools.builtin import get_builtin_tools

        for tool in get_builtin_tools():
            registry.register_tool(tool)
    except ImportError:
        pass

    return registry
