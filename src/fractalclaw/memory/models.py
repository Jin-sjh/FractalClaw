from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class MemoryType(Enum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


class MemoryScope(Enum):
    TASK = "task"
    GLOBAL = "global"


class SharingDirection(Enum):
    PARENT_TO_CHILD = "parent_to_child"
    CHILD_TO_PARENT = "child_to_parent"


@dataclass
class MemoryEntry:
    id: str
    content: str
    memory_type: MemoryType
    embedding: Optional[list[float]] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    accessed_at: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    importance: float = 0.5
    title: Optional[str] = None
    file_path: Optional[Path] = None
    tags: list[str] = field(default_factory=list)
    source_agent_id: Optional[str] = None
    scope: MemoryScope = MemoryScope.TASK

    def to_markdown(self) -> str:
        import json

        fm = [
            f"id: {self.id}",
            f"type: {self.memory_type.value}",
            f"scope: {self.scope.value}",
            f"created: {self.created_at.isoformat()}",
            f"importance: {self.importance}",
        ]
        if self.tags:
            fm.append(f"tags: {json.dumps(self.tags, ensure_ascii=False)}")
        if self.source_agent_id:
            fm.append(f"source_agent: {self.source_agent_id}")
        for k, v in self.metadata.items():
            if isinstance(v, (str, int, float, bool)):
                fm.append(f"{k}: {v}")
            else:
                fm.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
        title = self.title or self.id
        return f"---\n{chr(10).join(fm)}\n---\n\n# {title}\n\n{self.content}"

    @classmethod
    def from_markdown(cls, content: str, file_path: Optional[Path] = None) -> "MemoryEntry":
        import yaml

        if not content.startswith("---"):
            raise ValueError("Missing frontmatter")
        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ValueError("Incomplete frontmatter")
        fm = yaml.safe_load(parts[1]) or {}
        body = parts[2].strip()
        lines = body.split("\n")
        title = None
        content_lines = []
        for line in lines:
            if line.startswith("# ") and title is None:
                title = line[2:].strip()
            else:
                content_lines.append(line)
        return cls(
            id=fm.get("id", ""),
            content="\n".join(content_lines).strip(),
            memory_type=MemoryType(fm.get("type", "semantic")),
            title=title,
            file_path=file_path,
            metadata={
                k: v
                for k, v in fm.items()
                if k
                not in [
                    "id",
                    "type",
                    "scope",
                    "created",
                    "importance",
                    "tags",
                    "source_agent",
                ]
            },
            created_at=(
                datetime.fromisoformat(fm["created"]) if fm.get("created") else datetime.now()
            ),
            importance=fm.get("importance", 0.5),
            tags=fm.get("tags", []),
            source_agent_id=fm.get("source_agent"),
            scope=MemoryScope(fm.get("scope", "task")),
        )


@dataclass
class MemoryConfig:
    max_working_entries: int = 10
    embedding_model: str = "text-embedding-ada-002"
    similarity_threshold: float = 0.7
    enable_persistence: bool = True
    enable_session_save: bool = True
    enable_daily_log: bool = True
    enable_working_memory: bool = True
    heartbeat_interval_hours: int = 24
    global_memory_path: Optional[str] = None


@dataclass
class SharedMemoryPacket:
    direction: SharingDirection
    from_agent_id: str
    to_agent_id: str
    task_context: Optional[str] = None
    knowledge: Optional[str] = None
    constraints: Optional[str] = None
    result: Optional[str] = None
    discoveries: Optional[str] = None
    errors: Optional[str] = None

    def to_markdown(self) -> str:
        fm = [
            f"direction: {self.direction.value}",
            f"from_agent: {self.from_agent_id}",
            f"to_agent: {self.to_agent_id}",
            f"created: {datetime.now().isoformat()}",
        ]
        sections = []
        if self.task_context:
            sections.append(f"## 任务上下文\n\n{self.task_context}")
        if self.knowledge:
            sections.append(f"## 相关知识\n\n{self.knowledge}")
        if self.constraints:
            sections.append(f"## 约束和注意事项\n\n{self.constraints}")
        if self.result:
            sections.append(f"## 执行结果\n\n{self.result}")
        if self.discoveries:
            sections.append(f"## 新发现/知识\n\n{self.discoveries}")
        if self.errors:
            sections.append(f"## 错误和问题\n\n{self.errors}")
        direction_label = (
            "父→子" if self.direction == SharingDirection.PARENT_TO_CHILD else "子→父"
        )
        title = f"{direction_label}记忆传递: {self.from_agent_id} → {self.to_agent_id}"
        return f"---\n{chr(10).join(fm)}\n---\n\n# {title}\n\n{chr(10).join(sections)}"


@dataclass
class MemoryIndex:
    entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=datetime.now)

    def add_entry(self, entry: MemoryEntry) -> None:
        self.entries[entry.id] = {
            "title": entry.title or entry.id,
            "type": entry.memory_type.value,
            "scope": entry.scope.value,
            "file_path": str(entry.file_path) if entry.file_path else None,
            "importance": entry.importance,
            "tags": entry.tags,
        }
        self.last_updated = datetime.now()

    def remove_entry(self, entry_id: str) -> None:
        self.entries.pop(entry_id, None)
        self.last_updated = datetime.now()

    def to_markdown(self) -> str:
        lines = [
            "# Memory Index",
            "",
            f"Last Updated: {self.last_updated.isoformat()}",
            "",
        ]
        by_type: dict[str, list] = {}
        for eid, edata in self.entries.items():
            t = edata.get("type", "unknown")
            by_type.setdefault(t, []).append({"id": eid, **edata})
        for t in sorted(by_type):
            lines.append(f"## {t.upper()}")
            lines.append("")
            for e in sorted(by_type[t], key=lambda x: x.get("importance", 0), reverse=True):
                fp = e.get("file_path", "")
                title = e.get("title", e["id"])
                imp = e.get("importance", 0.5)
                if fp:
                    lines.append(f"- [{title}]({fp}) (importance: {imp:.2f})")
                else:
                    lines.append(f"- {title} (importance: {imp:.2f})")
            lines.append("")
        return "\n".join(lines)


@dataclass
class SessionSummary:
    session_id: str
    task: str
    task_id: Optional[str] = None
    result_status: str = "success"
    result_summary: str = ""
    session_file_path: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime = field(default_factory=datetime.now)
