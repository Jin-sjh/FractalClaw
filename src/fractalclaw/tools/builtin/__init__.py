"""Built-in tools for FractalClaw."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from fractalclaw.tools.base import BaseTool
from fractalclaw.tools.builtin.bash import BashTool, ListDirectoryTool
from fractalclaw.tools.builtin.read import ReadTool
from fractalclaw.tools.builtin.write import EditTool, WriteTool
from fractalclaw.tools.builtin.search import FindFilesTool, SearchTool
from fractalclaw.tools.builtin.llm_generate import LLMGenerateTool
from fractalclaw.tools.builtin.tavily_search import TavilySearchTool

if TYPE_CHECKING:
    from fractalclaw.tools.registry import ToolRegistry

__all__ = [
    "get_builtin_tools",
    "BashTool",
    "ListDirectoryTool",
    "ReadTool",
    "WriteTool",
    "EditTool",
    "SearchTool",
    "FindFilesTool",
    "LLMGenerateTool",
    "TavilySearchTool",
]

_BUILTIN_TOOLS: list[type[BaseTool]] = [
    BashTool,
    ListDirectoryTool,
    ReadTool,
    WriteTool,
    EditTool,
    SearchTool,
    FindFilesTool,
    LLMGenerateTool,
    TavilySearchTool,
]


def get_builtin_tools(llm_provider: Any = None, tavily_api_key: Optional[str] = None) -> list[BaseTool]:
    """Get instances of all built-in tools.

    Args:
        llm_provider: Optional LLM provider for tools that need it (e.g., LLMGenerateTool)
        tavily_api_key: Optional Tavily API key for TavilySearchTool

    Returns:
        List of built-in tool instances
    """
    tools = []
    for tool_class in _BUILTIN_TOOLS:
        if tool_class == LLMGenerateTool and llm_provider:
            tools.append(tool_class(llm_provider=llm_provider))
        elif tool_class == TavilySearchTool and tavily_api_key:
            tools.append(tool_class(api_key=tavily_api_key))
        else:
            tools.append(tool_class())
    return tools


def register_builtin_tools(
    registry: "ToolRegistry", llm_provider: Any = None, tavily_api_key: Optional[str] = None
) -> None:
    """Register all built-in tools with a registry.

    Args:
        registry: The tool registry to register tools with
        llm_provider: Optional LLM provider for tools that need it (e.g., LLMGenerateTool)
        tavily_api_key: Optional Tavily API key for TavilySearchTool
    """
    for tool in get_builtin_tools(llm_provider, tavily_api_key):
        registry.register_tool(tool)
