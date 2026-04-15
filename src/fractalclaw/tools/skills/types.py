"""Skills type definitions for FractalClaw."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class SkillInstallKind(str, Enum):
    """Types of skill installation methods."""

    BREW = "brew"
    NODE = "node"
    GO = "go"
    UV = "uv"
    DOWNLOAD = "download"
    PIP = "pip"


@dataclass
class SkillInstallSpec:
    """Specification for installing a skill's dependencies."""

    id: Optional[str] = None
    kind: SkillInstallKind = SkillInstallKind.PIP
    label: Optional[str] = None
    bins: list[str] = field(default_factory=list)
    formula: Optional[str] = None
    package: Optional[str] = None
    url: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillInstallSpec":
        """Create from a dictionary."""
        kind_str = data.get("kind", "pip")
        try:
            kind = SkillInstallKind(kind_str)
        except ValueError:
            kind = SkillInstallKind.PIP

        return cls(
            id=data.get("id"),
            kind=kind,
            label=data.get("label"),
            bins=data.get("bins", []),
            formula=data.get("formula"),
            package=data.get("package"),
            url=data.get("url"),
        )


@dataclass
class SkillRequires:
    """Requirements for a skill."""

    bins: list[str] = field(default_factory=list)
    any_bins: list[str] = field(default_factory=list)
    env: list[str] = field(default_factory=list)
    config: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "SkillRequires":
        """Create from a dictionary."""
        if data is None:
            return cls()
        return cls(
            bins=data.get("bins", []),
            any_bins=data.get("anyBins", []),
            env=data.get("env", []),
            config=data.get("config", []),
        )


@dataclass
class SkillMetadata:
    """Metadata for a skill."""

    emoji: Optional[str] = None
    homepage: Optional[str] = None
    os: list[str] = field(default_factory=list)
    requires: Optional[SkillRequires] = None
    install: list[SkillInstallSpec] = field(default_factory=list)
    always: bool = False
    skill_key: Optional[str] = None
    primary_env: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "SkillMetadata":
        """Create from a dictionary."""
        if data is None:
            return cls()

        install_specs = []
        for install_data in data.get("install", []):
            install_specs.append(SkillInstallSpec.from_dict(install_data))

        return cls(
            emoji=data.get("emoji"),
            homepage=data.get("homepage"),
            os=data.get("os", []),
            requires=SkillRequires.from_dict(data.get("requires")),
            install=install_specs,
            always=data.get("always", False),
            skill_key=data.get("skillKey"),
            primary_env=data.get("primaryEnv"),
        )


@dataclass
class SkillEntry:
    """A skill entry loaded from a SKILL.md file."""

    name: str
    description: str
    content: str
    file_path: str
    metadata: SkillMetadata = field(default_factory=SkillMetadata)

    @property
    def directory(self) -> str:
        """Get the directory containing the skill file."""
        return str(Path(self.file_path).parent)

    def to_prompt(self) -> str:
        """Convert skill to a prompt for LLM consumption."""
        lines = [
            f"# Skill: {self.name}",
            "",
            f"**Description:** {self.description}",
            "",
        ]

        if self.metadata.emoji:
            lines.insert(0, f"{self.metadata.emoji} ")

        lines.append("## Content")
        lines.append("")
        lines.append(self.content)

        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"SkillEntry(name={self.name!r}, file_path={self.file_path!r})"


@dataclass
class SkillRegistry:
    """Registry for managing skills."""

    _skills: dict[str, SkillEntry] = field(default_factory=dict)

    def register(self, skill: SkillEntry) -> None:
        """Register a skill."""
        self._skills[skill.name] = skill

    def unregister(self, name: str) -> bool:
        """Unregister a skill."""
        if name in self._skills:
            del self._skills[name]
            return True
        return False

    def get(self, name: str) -> Optional[SkillEntry]:
        """Get a skill by name."""
        return self._skills.get(name)

    def list_all(self) -> list[SkillEntry]:
        """List all registered skills."""
        return list(self._skills.values())

    def get_all_prompts(self) -> str:
        """Get all skills as a combined prompt."""
        prompts = [skill.to_prompt() for skill in self._skills.values()]
        return "\n\n---\n\n".join(prompts)
