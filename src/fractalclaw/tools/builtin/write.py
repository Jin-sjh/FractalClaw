"""File writing tool for FractalClaw."""

import os
from pathlib import Path
from typing import Optional

from pydantic import Field

from fractalclaw.tools.base import BaseTool, ToolParameters, ToolResult
from fractalclaw.tools.context import ToolContext
from fractalclaw.tools.permission import PermissionRequest


class WriteParameters(ToolParameters):
    """Parameters for the write tool."""

    file_path: str = Field(description="The absolute path to the file to write")
    content: str = Field(description="The content to write to the file")
    mode: Optional[str] = Field(
        default="write",
        description="Write mode: 'write' to overwrite, 'append' to append",
    )
    create_dirs: Optional[bool] = Field(
        default=True,
        description="Whether to create parent directories if they don't exist",
    )


class WriteTool(BaseTool):
    """Tool for writing content to files.

    This tool writes content to a file, with options to overwrite or append.
    It can also create parent directories if needed.
    """

    name = "write"
    description = "Write content to a file. Can overwrite or append to existing files."
    parameters_model = WriteParameters
    category = "filesystem"
    tags = ["file", "write", "content"]

    async def execute(self, params: WriteParameters, ctx: ToolContext) -> ToolResult:
        """Execute the write tool.

        Args:
            params: Validated parameters
            ctx: Execution context

        Returns:
            ToolResult with write status
        """
        await ctx.ask_permission(PermissionRequest.for_file_write(params.file_path))

        path = Path(params.file_path)

        if params.create_dirs:
            path.parent.mkdir(parents=True, exist_ok=True)

        mode = "a" if params.mode == "append" else "w"

        try:
            with open(path, mode, encoding="utf-8") as f:
                f.write(params.content)

            file_size = os.path.getsize(path)

            return ToolResult(
                title=path.name,
                output=f"Successfully wrote {len(params.content)} characters to {params.file_path}",
                metadata={
                    "file_path": str(path.absolute()),
                    "bytes_written": len(params.content.encode("utf-8")),
                    "file_size": file_size,
                    "mode": params.mode,
                },
            )

        except PermissionError:
            return ToolResult.error(
                title=path.name,
                error_message=f"Permission denied: {params.file_path}",
            )
        except Exception as e:
            return ToolResult.error(
                title=path.name,
                error_message=f"Failed to write file: {e}",
            )


class EditParameters(ToolParameters):
    """Parameters for the edit tool."""

    file_path: str = Field(description="The absolute path to the file to edit")
    old_content: str = Field(description="The content to find and replace")
    new_content: str = Field(description="The new content to replace with")
    replace_all: Optional[bool] = Field(
        default=False,
        description="Whether to replace all occurrences",
    )


class EditTool(BaseTool):
    """Tool for editing files by replacing content.

    This tool finds and replaces content in a file.
    """

    name = "edit"
    description = "Edit a file by finding and replacing content."
    parameters_model = EditParameters
    category = "filesystem"
    tags = ["file", "edit", "replace"]

    async def execute(self, params: EditParameters, ctx: ToolContext) -> ToolResult:
        """Execute the edit tool.

        Args:
            params: Validated parameters
            ctx: Execution context

        Returns:
            ToolResult with edit status
        """
        await ctx.ask_permission(PermissionRequest.for_file_write(params.file_path))

        path = Path(params.file_path)

        if not path.exists():
            return ToolResult.error(
                title=path.name,
                error_message=f"File not found: {params.file_path}",
            )

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            return ToolResult.error(
                title=path.name,
                error_message=f"Failed to read file: {e}",
            )

        if params.old_content not in content:
            return ToolResult.error(
                title=path.name,
                error_message="Content to replace not found in file",
            )

        if params.replace_all:
            new_content = content.replace(params.old_content, params.new_content)
            count = content.count(params.old_content)
        else:
            new_content = content.replace(params.old_content, params.new_content, 1)
            count = 1

        try:
            path.write_text(new_content, encoding="utf-8")
        except Exception as e:
            return ToolResult.error(
                title=path.name,
                error_message=f"Failed to write file: {e}",
            )

        return ToolResult(
            title=path.name,
            output=f"Successfully replaced {count} occurrence(s) in {params.file_path}",
            metadata={
                "file_path": str(path.absolute()),
                "replacements": count,
                "replace_all": params.replace_all,
            },
        )
