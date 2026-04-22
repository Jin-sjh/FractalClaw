"""Search tool for FractalClaw."""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Optional

from pydantic import Field

from fractalclaw.tools.base import BaseTool, ToolParameters, ToolResult
from fractalclaw.tools.context import ToolContext
from fractalclaw.tools.output import OutputHandler
from fractalclaw.tools.permission import PermissionRequest


class SearchParameters(ToolParameters):
    """Parameters for the search tool."""

    pattern: str = Field(description="The search pattern (regex or glob)")
    path: str = Field(default=".", description="The directory to search in")
    file_pattern: Optional[str] = Field(default="*", description="Glob pattern for files to search")
    case_sensitive: Optional[bool] = Field(default=False, description="Case sensitive search")
    use_regex: Optional[bool] = Field(default=True, description="Use regex pattern (vs glob)")
    max_results: Optional[int] = Field(default=100, description="Maximum number of results")


class SearchTool(BaseTool):
    """Tool for searching files and content.

    This tool searches for patterns in files within a directory.
    It supports both regex and glob patterns.
    """

    name = "search"
    description = "Search for a pattern in files within a directory."
    parameters_model = SearchParameters
    category = "search"
    tags = ["search", "find", "grep", "pattern"]

    async def execute(self, params: SearchParameters, ctx: ToolContext) -> ToolResult:
        """Execute the search tool.

        Args:
            params: Validated parameters
            ctx: Execution context

        Returns:
            ToolResult with search results
        """
        await ctx.ask_permission(PermissionRequest.for_file_read(params.path))

        search_path = Path(params.path)

        if not search_path.exists():
            return ToolResult.error(
                title="search",
                error_message=f"Path not found: {params.path}",
            )

        results: list[str] = []
        files_searched = 0
        files_with_matches = 0

        try:
            if params.use_regex:
                flags = 0 if params.case_sensitive else re.IGNORECASE
                pattern = re.compile(params.pattern, flags)
            else:
                pattern = None

            for root, _dirs, files in os.walk(search_path):
                for filename in files:
                    if not fnmatch.fnmatch(filename, params.file_pattern):
                        continue

                    file_path = Path(root) / filename

                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                        files_searched += 1

                        lines = content.split("\n")
                        file_has_match = False

                        for line_num, line in enumerate(lines, 1):
                            matched = False

                            if params.use_regex and pattern:
                                matched = bool(pattern.search(line))
                            elif not params.use_regex:
                                search_str = params.pattern if params.case_sensitive else params.pattern.lower()
                                line_str = line if params.case_sensitive else line.lower()
                                matched = search_str in line_str

                            if matched and not file_has_match:
                                files_with_matches += 1
                                file_has_match = True

                            if matched:
                                rel_path = file_path.relative_to(search_path)
                                results.append(f"{rel_path}:{line_num}: {line.strip()[:200]}")

                                if len(results) >= params.max_results:
                                    break

                        if len(results) >= params.max_results:
                            break

                    except Exception:
                        continue

                if len(results) >= params.max_results:
                    break

            output = "\n".join(results) if results else "No matches found"

            truncated = OutputHandler.truncate(output)

            return ToolResult(
                title=f"search: {params.pattern}",
                output=truncated.content,
                metadata={
                    "pattern": params.pattern,
                    "path": str(search_path.absolute()),
                    "files_searched": files_searched,
                    "files_with_matches": files_with_matches,
                    "results_count": len(results),
                    "truncated": truncated.truncated,
                    "use_regex": params.use_regex,
                },
            )

        except re.error as e:
            return ToolResult.error(
                title="search",
                error_message=f"Invalid regex pattern: {e}",
            )
        except Exception as e:
            return ToolResult.error(
                title="search",
                error_message=f"Search failed: {e}",
            )


class FindFilesParameters(ToolParameters):
    """Parameters for the find files tool."""

    pattern: str = Field(description="Glob pattern for file names")
    path: str = Field(default=".", description="The directory to search in")
    max_depth: Optional[int] = Field(default=None, description="Maximum search depth")


class FindFilesTool(BaseTool):
    """Tool for finding files by name pattern.

    This tool finds files matching a glob pattern.
    """

    name = "find_files"
    description = "Find files matching a glob pattern."
    parameters_model = FindFilesParameters
    category = "search"
    tags = ["find", "files", "glob"]

    async def execute(self, params: FindFilesParameters, ctx: ToolContext) -> ToolResult:
        """Execute the find files tool.

        Args:
            params: Validated parameters
            ctx: Execution context

        Returns:
            ToolResult with found files
        """
        await ctx.ask_permission(PermissionRequest.for_file_read(params.path))

        search_path = Path(params.path)

        if not search_path.exists():
            return ToolResult.error(
                title="find_files",
                error_message=f"Path not found: {params.path}",
            )

        results: list[str] = []
        current_depth = 0

        try:
            for root, dirs, files in os.walk(search_path):
                rel_root = Path(root).relative_to(search_path)
                current_depth = len(rel_root.parts) if str(rel_root) != "." else 0

                if params.max_depth is not None and current_depth > params.max_depth:
                    dirs.clear()
                    continue

                for filename in files:
                    if fnmatch.fnmatch(filename, params.pattern):
                        rel_path = rel_root / filename if str(rel_root) != "." else Path(filename)
                        results.append(str(rel_path))

            output = "\n".join(results) if results else "No files found"

            return ToolResult(
                title=f"find: {params.pattern}",
                output=output,
                metadata={
                    "pattern": params.pattern,
                    "path": str(search_path.absolute()),
                    "files_found": len(results),
                    "max_depth": params.max_depth,
                },
            )

        except Exception as e:
            return ToolResult.error(
                title="find_files",
                error_message=f"Find failed: {e}",
            )
