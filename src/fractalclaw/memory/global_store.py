from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import MemoryEntry, MemoryType, MemoryScope
from .markdown_store import MarkdownStore


class GlobalMemoryStore(MarkdownStore):
    def __init__(self, content_path: Optional[Path] = None):
        if content_path is None:
            current_file = Path(__file__).resolve()
            content_path = current_file.parent.parent / "content"
        base_path = content_path / "memory"
        super().__init__(base_path)

    def _create_directory_structure(self) -> None:
        for d in [
            self.base_path / "semantic",
            self.base_path / "episodic",
            self.base_path / "episodic" / "daily",
            self.base_path / "episodic" / "sessions",
            self.base_path / "shared",
        ]:
            d.mkdir(parents=True, exist_ok=True)

    async def add_global_knowledge(
        self,
        title: str,
        content: str,
        memory_type: MemoryType = MemoryType.SEMANTIC,
        tags: Optional[list[str]] = None,
        source_agent_id: Optional[str] = None,
    ) -> MemoryEntry:
        entry = MemoryEntry(
            id=f"global_{datetime.now().strftime('%Y%m%d%H%M%S')}_{abs(hash(title)) % 10000:04d}",
            content=content,
            memory_type=memory_type,
            title=title,
            tags=tags or [],
            source_agent_id=source_agent_id,
            scope=MemoryScope.GLOBAL,
        )
        await self.store(entry)
        return entry

    async def search_global(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        return await self.search(query, limit=limit)
