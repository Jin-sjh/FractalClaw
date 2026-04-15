"""Parser for SKILL.md files."""

import re
from pathlib import Path
from typing import Any, Optional

from fractalclaw.tools.skills.types import SkillEntry, SkillMetadata


class SkillParseError(Exception):
    """Raised when parsing a SKILL.md file fails."""

    def __init__(self, file_path: str, message: str):
        self.file_path = file_path
        self.message = message
        super().__init__(f"Failed to parse {file_path}: {message}")


def parse_yaml_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from markdown content.

    Args:
        content: The markdown content with potential frontmatter

    Returns:
        Tuple of (frontmatter_dict, remaining_content)
    """
    frontmatter_pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    match = frontmatter_pattern.match(content)

    if not match:
        return {}, content

    frontmatter_str = match.group(1)
    remaining = content[match.end() :]

    frontmatter: dict[str, Any] = {}
    current_key: Optional[str] = None
    current_list: Optional[list[Any]] = None
    indent_stack: list[tuple[str, Any]] = []

    for line in frontmatter_str.split("\n"):
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip())
        line = line.strip()

        if ":" in line and not line.startswith("-"):
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()

            while indent_stack and indent_stack[-1][0] >= indent:
                indent_stack.pop()

            if value:
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                frontmatter[key] = value
                current_key = key
                current_list = None
            else:
                frontmatter[key] = {}
                indent_stack.append((indent + 2, frontmatter[key]))
                current_key = key
                current_list = None

        elif line.startswith("- "):
            value = line[2:].strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]

            if current_key and current_key not in frontmatter:
                frontmatter[current_key] = []
                current_list = frontmatter[current_key]
            elif current_key and isinstance(frontmatter.get(current_key), list):
                current_list = frontmatter[current_key]
            elif current_list is not None:
                pass
            else:
                continue

            if current_list is not None:
                current_list.append(value)

    return frontmatter, remaining


def parse_skill_file(file_path: str) -> SkillEntry:
    """Parse a SKILL.md file into a SkillEntry.

    Args:
        file_path: Path to the SKILL.md file

    Returns:
        Parsed SkillEntry

    Raises:
        SkillParseError: If parsing fails
    """
    path = Path(file_path)
    if not path.exists():
        raise SkillParseError(file_path, "File does not exist")

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        raise SkillParseError(file_path, f"Failed to read file: {e}")

    frontmatter, body = parse_yaml_frontmatter(content)

    name = frontmatter.get("name")
    if not name:
        name = path.parent.name

    description = frontmatter.get("description", "")

    metadata_dict = frontmatter.get("metadata", {})
    if isinstance(metadata_dict, str):
        metadata_dict = {}

    metadata = SkillMetadata.from_dict(metadata_dict)

    return SkillEntry(
        name=name,
        description=description,
        content=body.strip(),
        file_path=str(path.absolute()),
        metadata=metadata,
    )


def parse_skill_content(content: str, file_path: str = "<string>") -> SkillEntry:
    """Parse skill content from a string.

    Args:
        content: The SKILL.md content
        file_path: Optional file path for reference

    Returns:
        Parsed SkillEntry
    """
    frontmatter, body = parse_yaml_frontmatter(content)

    name = frontmatter.get("name", "unknown")
    description = frontmatter.get("description", "")

    metadata_dict = frontmatter.get("metadata", {})
    if isinstance(metadata_dict, str):
        metadata_dict = {}

    metadata = SkillMetadata.from_dict(metadata_dict)

    return SkillEntry(
        name=name,
        description=description,
        content=body.strip(),
        file_path=file_path,
        metadata=metadata,
    )
