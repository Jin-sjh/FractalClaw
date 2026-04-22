"""Output handling utilities for FractalClaw tools system."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Optional

from fractalclaw.tools.base import ToolResult


@dataclass
class TruncatedOutput:
    """Result of output truncation."""

    content: str
    truncated: bool
    original_length: int
    truncated_length: int
    full_output_path: Optional[str] = None


@dataclass
class OutputConfig:
    """Configuration for output handling."""

    max_output_length: int = 10000
    truncation_message: str = "\n... [Output truncated. Full output saved to: {path}]"
    output_dir: Optional[str] = None
    save_full_output: bool = True


class OutputHandler:
    """Handler for tool output processing including truncation and formatting.

    This class provides utilities for:
    - Truncating long outputs to manageable sizes
    - Saving full outputs to files
    - Formatting outputs for display

    Example:
        result = OutputHandler.truncate(long_output, max_length=5000)
        if result.truncated:
            print(f"Output truncated, full version at: {result.full_output_path}")
        print(result.content)
    """

    DEFAULT_MAX_LENGTH: ClassVar[int] = 10000
    DEFAULT_TRUNCATION_MESSAGE: ClassVar[str] = (
        "\n... [Output truncated. Full output saved to: {path}]"
    )

    _config: ClassVar[OutputConfig] = OutputConfig()

    @classmethod
    def configure(cls, config: OutputConfig) -> None:
        """Configure the output handler globally."""
        cls._config = config

    @classmethod
    def truncate(
        cls,
        output: str,
        max_length: Optional[int] = None,
        call_id: Optional[str] = None,
    ) -> TruncatedOutput:
        """Truncate output if it exceeds max length.

        Args:
            output: The output string to potentially truncate
            max_length: Maximum allowed length (uses config default if not specified)
            call_id: Optional call ID for generating output file name

        Returns:
            TruncatedOutput with content and truncation info
        """
        max_len = max_length or cls._config.max_output_length
        original_length = len(output)

        if original_length <= max_len:
            return TruncatedOutput(
                content=output,
                truncated=False,
                original_length=original_length,
                truncated_length=original_length,
            )

        truncated_content = output[:max_len]
        full_output_path: Optional[str] = None

        if cls._config.save_full_output:
            full_output_path = cls.save_full_output(output, call_id)
            truncation_msg = cls._config.truncation_message.format(path=full_output_path)
            truncated_content = truncated_content.rstrip() + truncation_msg

        return TruncatedOutput(
            content=truncated_content,
            truncated=True,
            original_length=original_length,
            truncated_length=len(truncated_content),
            full_output_path=full_output_path,
        )

    @classmethod
    def save_full_output(cls, output: str, call_id: Optional[str] = None) -> str:
        """Save full output to a file.

        Args:
            output: The full output string
            call_id: Optional call ID for file naming

        Returns:
            Path to the saved file
        """
        output_dir = cls._config.output_dir or os.path.join(tempfile.gettempdir(), "fractalclaw")

        Path(output_dir).mkdir(parents=True, exist_ok=True)

        filename = f"output_{call_id or 'unknown'}.txt"
        file_path = os.path.join(output_dir, filename)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(output)

        return file_path

    @classmethod
    def truncate_result(
        cls,
        result: ToolResult,
        max_length: Optional[int] = None,
        call_id: Optional[str] = None,
    ) -> ToolResult:
        """Truncate a ToolResult's output if needed.

        Args:
            result: The ToolResult to potentially truncate
            max_length: Maximum allowed length
            call_id: Optional call ID for output file naming

        Returns:
            New ToolResult with truncated output if needed
        """
        truncated = cls.truncate(result.output, max_length, call_id)

        if not truncated.truncated:
            return result

        return ToolResult.truncated(
            title=result.title,
            output=truncated.content,
            full_output_path=truncated.full_output_path,
            **result.metadata,
        )

    @classmethod
    def format_with_line_numbers(
        cls,
        content: str,
        start_line: int = 1,
        line_format: str = "{line_num:6d}→{line_content}",
    ) -> str:
        """Format content with line numbers.

        Args:
            content: The content to format
            start_line: Starting line number
            line_format: Format string for each line

        Returns:
            Formatted content with line numbers
        """
        lines = content.split("\n")
        formatted_lines = []

        for i, line in enumerate(lines):
            line_num = start_line + i
            formatted_lines.append(line_format.format(line_num=line_num, line_content=line))

        return "\n".join(formatted_lines)

    @classmethod
    def format_json_output(cls, data: Any, indent: int = 2) -> str:
        """Format JSON data for output.

        Args:
            data: The data to format as JSON
            indent: Indentation level

        Returns:
            Formatted JSON string
        """
        import json

        return json.dumps(data, indent=indent, ensure_ascii=False, default=str)

    @classmethod
    def format_table(
        cls,
        headers: list[str],
        rows: list[list[Any]],
        column_widths: Optional[list[int]] = None,
    ) -> str:
        """Format data as a table.

        Args:
            headers: Table headers
            rows: Table rows
            column_widths: Optional column widths (auto-calculated if not provided)

        Returns:
            Formatted table string
        """
        if not column_widths:
            column_widths = []
            for i, header in enumerate(headers):
                max_width = len(str(header))
                for row in rows:
                    if i < len(row):
                        max_width = max(max_width, len(str(row[i])))
                column_widths.append(max_width)

        def format_row(cells: list[Any]) -> str:
            formatted_cells = []
            for i, cell in enumerate(cells):
                width = column_widths[i] if i < len(column_widths) else 10
                formatted_cells.append(str(cell).ljust(width))
            return " | ".join(formatted_cells)

        lines = []
        lines.append(format_row(headers))
        lines.append("-" * len(lines[0]))

        for row in rows:
            lines.append(format_row(row))

        return "\n".join(lines)

    @classmethod
    def format_error(cls, error: Exception, include_traceback: bool = False) -> str:
        """Format an error for output.

        Args:
            error: The exception to format
            include_traceback: Whether to include traceback

        Returns:
            Formatted error string
        """
        import traceback

        lines = [f"Error: {type(error).__name__}: {str(error)}"]

        if include_traceback:
            lines.append("\nTraceback:")
            lines.extend(traceback.format_tb(error.__traceback__))

        return "\n".join(lines)
