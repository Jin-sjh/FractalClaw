"""Shell command execution tool for FractalClaw."""

from __future__ import annotations

import asyncio
import os
import platform
from pathlib import Path
from typing import Dict, Optional

from pydantic import Field

from fractalclaw.tools.base import BaseTool, ToolParameters, ToolResult
from fractalclaw.tools.context import ToolContext
from fractalclaw.tools.output import OutputHandler
from fractalclaw.tools.permission import PermissionRequest


class BashParameters(ToolParameters):
    """Parameters for the bash tool."""

    command: str = Field(description="The command to execute")
    timeout: Optional[int] = Field(default=30, description="Timeout in seconds")
    cwd: Optional[str] = Field(default=None, description="Working directory for command execution")
    env: Optional[Dict[str, str]] = Field(default=None, description="Environment variables")


class BashTool(BaseTool):
    """Tool for executing shell commands.

    This tool executes shell commands with configurable timeout and working directory.
    It captures both stdout and stderr.
    """

    name = "bash"
    description = "Execute a shell command and return the output."
    parameters_model = BashParameters
    category = "execution"
    tags = ["shell", "command", "execute"]

    DEFAULT_TIMEOUT = 30
    MAX_OUTPUT_LENGTH = 50000

    async def execute(self, params: BashParameters, ctx: ToolContext) -> ToolResult:
        """Execute the bash tool.

        Args:
            params: Validated parameters
            ctx: Execution context

        Returns:
            ToolResult with command output
        """
        await ctx.ask_permission(PermissionRequest.for_bash_command(params.command))

        timeout = params.timeout or self.DEFAULT_TIMEOUT
        cwd = params.cwd

        if cwd:
            cwd_path = Path(cwd)
            if not cwd_path.exists():
                return ToolResult.error(
                    title="bash",
                    error_message=f"Working directory does not exist: {cwd}",
                )
            cwd = str(cwd_path.absolute())

        env = os.environ.copy()
        if params.env:
            env.update(params.env)

        try:
            process = await asyncio.create_subprocess_shell(
                params.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult.error(
                    title="bash",
                    error_message=f"Command timed out after {timeout} seconds",
                )

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            output_parts = []
            if stdout_str.strip():
                output_parts.append(f"stdout:\n{stdout_str}")
            if stderr_str.strip():
                output_parts.append(f"stderr:\n{stderr_str}")

            combined_output = "\n\n".join(output_parts) if output_parts else "(no output)"

            truncated = OutputHandler.truncate(combined_output, self.MAX_OUTPUT_LENGTH)

            return ToolResult(
                title=params.command[:50],
                output=truncated.content,
                metadata={
                    "exit_code": process.returncode,
                    "truncated": truncated.truncated,
                    "timeout": timeout,
                    "cwd": cwd or os.getcwd(),
                },
            )

        except Exception as e:
            return ToolResult.error(
                title="bash",
                error_message=f"Failed to execute command: {e}",
            )


class ListDirectoryParameters(ToolParameters):
    """Parameters for the list directory tool."""

    path: str = Field(description="The directory path to list")
    show_hidden: Optional[bool] = Field(default=False, description="Show hidden files")
    recursive: Optional[bool] = Field(default=False, description="List recursively")


class ListDirectoryTool(BaseTool):
    """Tool for listing directory contents.

    This tool lists the contents of a directory with optional recursion.
    """

    name = "list_directory"
    description = "List the contents of a directory."
    parameters_model = ListDirectoryParameters
    category = "filesystem"
    tags = ["directory", "list", "files"]

    async def execute(self, params: ListDirectoryParameters, ctx: ToolContext) -> ToolResult:
        """Execute the list directory tool.

        Args:
            params: Validated parameters
            ctx: Execution context

        Returns:
            ToolResult with directory listing
        """
        await ctx.ask_permission(PermissionRequest.for_file_read(params.path))

        path = Path(params.path)

        if not path.exists():
            return ToolResult.error(
                title=path.name,
                error_message=f"Directory not found: {params.path}",
            )

        if not path.is_dir():
            return ToolResult.error(
                title=path.name,
                error_message=f"Path is not a directory: {params.path}",
            )

        try:
            entries = []

            if params.recursive:
                for root, dirs, files in os.walk(path):
                    root_path = Path(root)
                    rel_root = root_path.relative_to(path)

                    if not params.show_hidden:
                        dirs[:] = [d for d in dirs if not d.startswith(".")]

                    for d in sorted(dirs):
                        if params.show_hidden or not d.startswith("."):
                            entries.append(f"{rel_root / d}/")

                    for f in sorted(files):
                        if params.show_hidden or not f.startswith("."):
                            entries.append(str(rel_root / f))
            else:
                for item in sorted(path.iterdir()):
                    if params.show_hidden or not item.name.startswith("."):
                        if item.is_dir():
                            entries.append(f"{item.name}/")
                        else:
                            entries.append(item.name)

            output = "\n".join(entries) if entries else "(empty directory)"

            return ToolResult(
                title=path.name,
                output=output,
                metadata={
                    "path": str(path.absolute()),
                    "count": len(entries),
                    "recursive": params.recursive,
                    "show_hidden": params.show_hidden,
                },
            )

        except PermissionError:
            return ToolResult.error(
                title=path.name,
                error_message=f"Permission denied: {params.path}",
            )
        except Exception as e:
            return ToolResult.error(
                title=path.name,
                error_message=f"Failed to list directory: {e}",
            )
