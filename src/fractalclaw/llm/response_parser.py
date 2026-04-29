"""LLM response parsing utilities."""

from __future__ import annotations

import json
import re
from typing import Any, Optional


def _strip_json_comments(text: str) -> str:
    """Remove single-line // comments from JSON text."""
    return re.sub(r'//[^\n]*', '', text)


def _fix_json_trailing_commas(text: str) -> str:
    """Remove trailing commas before } or ] in JSON text."""
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*]', ']', text)
    return text


def _try_parse_json(text: str) -> Optional[dict[str, Any]]:
    """Try to parse JSON with common LLM output fixes applied."""
    for fixer in [lambda t: t, _strip_json_comments, _fix_json_trailing_commas,
                  lambda t: _fix_json_trailing_commas(_strip_json_comments(t))]:
        try:
            result = json.loads(fixer(text))
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def extract_json_from_llm_response(text: str) -> Optional[dict[str, Any]]:
    """Extract and parse JSON from an LLM response string.

    Handles common LLM output patterns:
    - Raw JSON objects
    - JSON wrapped in markdown code blocks (```json ... ```)
    - JSON embedded within surrounding text
    - JSON with trailing commas or // comments

    Returns parsed dict on success, None on failure.
    """
    text = text.strip()

    if text.startswith("{") and text.endswith("}"):
        result = _try_parse_json(text)
        if result is not None:
            return result

    code_block_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, re.DOTALL)
    if code_block_match:
        result = _try_parse_json(code_block_match.group(1))
        if result is not None:
            return result

    greedy_match = re.search(r"\{[\s\S]*\}", text)
    if greedy_match:
        result = _try_parse_json(greedy_match.group())
        if result is not None:
            return result

    return None
