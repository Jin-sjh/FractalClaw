"""Shared tool placeholder handler."""

from __future__ import annotations

from typing import Any, Callable


def create_placeholder_handler(tool_name: str) -> Callable:
    """Create a placeholder handler for unregistered tools.

    Returns an async function that clearly reports the tool is not available,
    preventing LLM from mistaking it for a successful execution.
    """

    async def placeholder(**kwargs: Any) -> str:
        return (
            f"[ERROR] Tool '{tool_name}' is not available. "
            f"No real implementation exists for this tool. "
            f"The requested operation was NOT executed. "
            f"Args received: {kwargs}"
        )

    return placeholder
