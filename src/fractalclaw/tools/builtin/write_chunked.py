"""Chunked file writing tool for FractalClaw - solves token limit issues."""

import os
from pathlib import Path
from typing import Optional

from pydantic import Field

from fractalclaw.tools.base import BaseTool, ToolParameters, ToolResult
from fractalclaw.tools.context import ToolContext
from fractalclaw.tools.permission import PermissionRequest


class WriteChunkedParameters(ToolParameters):
    """Parameters for the write_chunked tool."""

    file_path: str = Field(description="The absolute path to the file to write")
    content: str = Field(description="The content chunk to write to the file")
    chunk_index: int = Field(
        description="Current chunk index (0-based). First chunk should be 0."
    )
    total_chunks: int = Field(
        description="Total number of chunks expected for this file"
    )
    create_dirs: Optional[bool] = Field(
        default=True,
        description="Whether to create parent directories if they don't exist",
    )


class WriteChunkedTool(BaseTool):
    """Tool for writing large files in chunks to avoid token limits.

    This tool allows writing large files in multiple chunks, where each chunk
    is a separate tool call. The first chunk (chunk_index=0) overwrites the file,
    and subsequent chunks append to it.

    Usage:
        1. Plan the file structure and estimate total chunks needed
        2. Write first chunk: chunk_index=0 (creates/overwrites file)
        3. Write subsequent chunks: chunk_index=1,2,3... (appends)
        4. Ensure all chunks are written

    Example:
        write_chunked(file_path="App.jsx", content="import React...", chunk_index=0, total_chunks=3)
        write_chunked(file_path="App.jsx", content="function App()...", chunk_index=1, total_chunks=3)
        write_chunked(file_path="App.jsx", content="export default App", chunk_index=2, total_chunks=3)
    """

    name = "write_chunked"
    description = (
        "Write large files in chunks to avoid token limits. "
        "Use for files expected to be > 2000 characters. "
        "First chunk (index 0) creates the file, subsequent chunks append."
    )
    parameters_model = WriteChunkedParameters
    category = "filesystem"
    tags = ["file", "write", "chunked", "large-file"]

    async def execute(self, params: WriteChunkedParameters, ctx: ToolContext) -> ToolResult:
        """Execute the write_chunked tool.

        Args:
            params: Validated parameters
            ctx: Execution context

        Returns:
            ToolResult with write status
        """
        await ctx.ask_permission(PermissionRequest.for_file_write(params.file_path))

        path = Path(params.file_path)

        if params.create_dirs and params.chunk_index == 0:
            path.parent.mkdir(parents=True, exist_ok=True)

        mode = "w" if params.chunk_index == 0 else "a"

        try:
            with open(path, mode, encoding="utf-8") as f:
                f.write(params.content)

            file_size = os.path.getsize(path)
            progress = f"[{params.chunk_index + 1}/{params.total_chunks}]"

            return ToolResult(
                title=f"{path.name} (chunk {params.chunk_index + 1})",
                output=(
                    f"Chunk {progress} written to {params.file_path}. "
                    f"File size: {file_size} bytes."
                ),
                metadata={
                    "file_path": str(path.absolute()),
                    "chunk_index": params.chunk_index,
                    "total_chunks": params.total_chunks,
                    "bytes_written": len(params.content.encode("utf-8")),
                    "file_size": file_size,
                    "is_complete": params.chunk_index == params.total_chunks - 1,
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
                error_message=f"Failed to write chunk: {e}",
            )
