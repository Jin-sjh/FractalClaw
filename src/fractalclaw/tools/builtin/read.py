"""File reading tool for FractalClaw."""

import os
from pathlib import Path
from typing import Optional

from pydantic import Field

from fractalclaw.tools.base import BaseTool, ToolParameters, ToolResult
from fractalclaw.tools.context import ToolContext
from fractalclaw.tools.output import OutputHandler
from fractalclaw.tools.permission import PermissionRequest


class ReadParameters(ToolParameters):
    """Parameters for the read tool."""

    file_path: str = Field(description="The absolute path to the file to read")
    offset: Optional[int] = Field(default=None, description="Starting line number (1-based)")
    limit: Optional[int] = Field(default=None, description="Maximum number of lines to read")


class ReadTool(BaseTool):
    """Tool for reading file contents.

    This tool reads the contents of a file and returns them with line numbers.
    It supports reading specific line ranges and handles large files by truncating output.
    """

    name = "read"
    description = "Read the contents of a file. Returns file content with line numbers."
    parameters_model = ReadParameters
    category = "filesystem"
    tags = ["file", "read", "content"]

    DEFAULT_LIMIT = 2000

    async def execute(self, params: ReadParameters, ctx: ToolContext) -> ToolResult:
        """Execute the read tool.

        Args:
            params: Validated parameters
            ctx: Execution context

        Returns:
            ToolResult with file contents
        """
        await ctx.ask_permission(PermissionRequest.for_file_read(params.file_path))

        path = Path(params.file_path)

        if not path.exists():
            return ToolResult.error(
                title=path.name,
                error_message=f"File not found: {params.file_path}",
            )

        if not path.is_file():
            return ToolResult.error(
                title=path.name,
                error_message=f"Path is not a file: {params.file_path}",
            )

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = path.read_text(encoding="latin-1")
            except Exception as e:
                return ToolResult.error(
                    title=path.name,
                    error_message=f"Failed to read file: {e}",
                )
        except PermissionError:
            return ToolResult.error(
                title=path.name,
                error_message=f"Permission denied: {params.file_path}",
            )
        except Exception as e:
            return ToolResult.error(
                title=path.name,
                error_message=f"Failed to read file: {e}",
            )

        lines = content.split("\n")
        total_lines = len(lines)

        offset = params.offset or 1
        limit = params.limit or self.DEFAULT_LIMIT

        if offset < 1:
            offset = 1
        if offset > total_lines:
            return ToolResult(
                title=path.name,
                output="",
                metadata={"total_lines": total_lines, "offset": offset, "limit": limit},
            )

        end_line = min(offset + limit - 1, total_lines)
        selected_lines = lines[offset - 1 : end_line]

        formatted_output = OutputHandler.format_with_line_numbers(
            "\n".join(selected_lines),
            start_line=offset,
        )

        truncated = end_line < total_lines

        return ToolResult(
            title=path.name,
            output=formatted_output,
            metadata={
                "total_lines": total_lines,
                "lines_shown": len(selected_lines),
                "offset": offset,
                "limit": limit,
                "truncated": truncated,
                "file_size": os.path.getsize(path),
            },
        )
