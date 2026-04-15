"""Tavily search tool for FractalClaw."""

import os
from typing import Any, Optional

from pydantic import Field

from fractalclaw.tools.base import BaseTool, ToolParameters, ToolResult
from fractalclaw.tools.context import ToolContext


class TavilySearchParameters(ToolParameters):
    """Parameters for the Tavily search tool."""

    query: str = Field(description="The search query")
    search_depth: Optional[str] = Field(
        default="basic",
        description="Search depth: 'basic' or 'advanced'",
    )
    include_domains: Optional[list[str]] = Field(
        default=None,
        description="List of domains to include in search",
    )
    exclude_domains: Optional[list[str]] = Field(
        default=None,
        description="List of domains to exclude from search",
    )
    include_answer: Optional[bool] = Field(
        default=False,
        description="Include a short answer to the query",
    )
    include_raw_content: Optional[bool] = Field(
        default=False,
        description="Include raw content of search results",
    )
    max_results: Optional[int] = Field(
        default=5,
        description="Maximum number of search results",
    )


class TavilySearchTool(BaseTool):
    """Tool for searching the web using Tavily API.

    This tool uses Tavily's search API to perform web searches
    with advanced filtering and content extraction capabilities.
    """

    name = "tavily_search"
    description = "Search the web using Tavily API for comprehensive results."
    parameters_model = TavilySearchParameters
    category = "search"
    tags = ["search", "web", "tavily", "internet"]
    version = "1.0.0"

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Tavily search tool.

        Args:
            api_key: Tavily API key. If not provided, will look for TAVILY_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        self._client: Any = None

    def _get_client(self) -> Any:
        """Get or create Tavily client lazily."""
        if self._client is None:
            try:
                from tavily import TavilyClient

                if not self.api_key:
                    raise ValueError(
                        "Tavily API key not found. Please set TAVILY_API_KEY environment variable "
                        "or pass api_key parameter."
                    )
                self._client = TavilyClient(api_key=self.api_key)
            except ImportError as e:
                raise ImportError(
                    "tavily-python is not installed. Please install it with: pip install tavily-python"
                ) from e
        return self._client

    async def execute(self, params: TavilySearchParameters, ctx: ToolContext) -> ToolResult:  # type: ignore[override]
        """Execute the Tavily search tool.

        Args:
            params: Validated parameters
            ctx: Execution context

        Returns:
            ToolResult with search results
        """
        try:
            client = self._get_client()

            search_kwargs: dict[str, Any] = {
                "query": params.query,
                "search_depth": params.search_depth,
                "include_answer": params.include_answer,
                "include_raw_content": params.include_raw_content,
                "max_results": params.max_results,
            }

            if params.include_domains:
                search_kwargs["include_domains"] = params.include_domains
            if params.exclude_domains:
                search_kwargs["exclude_domains"] = params.exclude_domains

            response = client.search(**search_kwargs)

            output_parts = []

            if params.include_answer and response.get("answer"):
                output_parts.append(f"Answer: {response['answer']}\n")

            results = response.get("results", [])
            if results:
                output_parts.append(f"Found {len(results)} results:\n")
                for i, result in enumerate(results, 1):
                    title = result.get("title", "No title")
                    url = result.get("url", "")
                    content = result.get("content", "")
                    score = result.get("score", 0)

                    output_parts.append(f"{i}. {title}")
                    output_parts.append(f"   URL: {url}")
                    output_parts.append(f"   Score: {score:.2f}")
                    output_parts.append(f"   {content[:200]}...")
                    if params.include_raw_content and result.get("raw_content"):
                        raw_content = result["raw_content"]
                        output_parts.append(f"   Raw content length: {len(raw_content)} chars")
                    output_parts.append("")
            else:
                output_parts.append("No results found.")

            output = "\n".join(output_parts)

            return ToolResult(
                title=f"tavily_search: {params.query}",
                output=output,
                metadata={
                    "query": params.query,
                    "search_depth": params.search_depth,
                    "results_count": len(results),
                    "include_answer": params.include_answer,
                    "max_results": params.max_results,
                },
            )

        except ValueError as e:
            return ToolResult.error(
                title="tavily_search",
                error_message=str(e),
            )
        except ImportError as e:
            return ToolResult.error(
                title="tavily_search",
                error_message=str(e),
            )
        except Exception as e:
            return ToolResult.error(
                title="tavily_search",
                error_message=f"Search failed: {e}",
            )
