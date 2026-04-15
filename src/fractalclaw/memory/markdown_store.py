import re
import shutil
from pathlib import Path
from typing import Optional
from datetime import datetime

from .models import MemoryEntry, MemoryType, MemoryScope, MemoryIndex
from .store import MemoryStore


class MarkdownStore(MemoryStore):
    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self._index: Optional[MemoryIndex] = None

    async def initialize(self) -> None:
        self._create_directory_structure()
        await self._load_or_create_index()

    def _create_directory_structure(self) -> None:
        for d in [
            self.base_path / "semantic",
            self.base_path / "episodic",
            self.base_path / "episodic" / "daily",
            self.base_path / "episodic" / "sessions",
            self.base_path / "shared",
            self.base_path / "shared" / "from_children",
        ]:
            d.mkdir(parents=True, exist_ok=True)

    async def _load_or_create_index(self) -> None:
        index_file = self.base_path / "INDEX.md"
        if index_file.exists():
            content = index_file.read_text(encoding="utf-8")
            self._index = self._parse_index(content)
        else:
            self._index = MemoryIndex()
            await self._save_index()

    def _parse_index(self, content: str) -> MemoryIndex:
        index = MemoryIndex()
        current_type = None
        for line in content.split("\n"):
            if line.startswith("## "):
                current_type = line[3:].lower()
            elif line.startswith("- [") and current_type:
                m = re.match(r"- \[([^\]]+)\]\(([^)]+)\).*importance:\s*([\d.]+)", line)
                if m:
                    title, path, imp = m.groups()
                    index.entries[Path(path).stem] = {
                        "title": title,
                        "type": current_type,
                        "file_path": path,
                        "importance": float(imp),
                    }
        return index

    async def _save_index(self) -> None:
        (self.base_path / "INDEX.md").write_text(
            self._index.to_markdown(), encoding="utf-8"
        )

    def _get_file_path(self, entry: MemoryEntry) -> Path:
        if entry.file_path:
            return self.base_path / entry.file_path
        type_dirs = {
            MemoryType.SEMANTIC: "memory/semantic",
            MemoryType.EPISODIC: "memory/episodic/sessions",
        }
        dir_name = type_dirs.get(entry.memory_type, "memory/semantic")
        if entry.memory_type == MemoryType.EPISODIC:
            date_dir = entry.created_at.strftime("%Y-%m-%d")
            dir_path = self.base_path / dir_name / date_dir
            dir_path.mkdir(parents=True, exist_ok=True)
        else:
            dir_path = self.base_path / dir_name
        safe = re.sub(r'[<>:"/\\|?*]', "_", entry.title or entry.id)[:100]
        return dir_path / f"{safe}.md"

    async def store(self, entry: MemoryEntry) -> str:
        file_path = self._get_file_path(entry)
        entry.file_path = file_path.relative_to(self.base_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(entry.to_markdown(), encoding="utf-8")
        self._index.add_entry(entry)
        await self._save_index()
        return entry.id

    async def retrieve(self, entry_id: str) -> Optional[MemoryEntry]:
        edata = self._index.entries.get(entry_id)
        if not edata or not edata.get("file_path"):
            return None
        full = self.base_path / edata["file_path"]
        if not full.exists():
            return None
        entry = MemoryEntry.from_markdown(
            full.read_text(encoding="utf-8"), Path(edata["file_path"])
        )
        entry.accessed_at = datetime.now()
        entry.access_count += 1
        return entry

    async def search(
        self,
        query: str,
        memory_type: Optional[MemoryType] = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        results = []
        ql = query.lower()
        for eid, edata in self._index.entries.items():
            if memory_type and edata.get("type") != memory_type.value:
                continue
            if ql in edata.get("title", "").lower():
                e = await self.retrieve(eid)
                if e:
                    results.append(e)
                continue
            fp = edata.get("file_path")
            if fp and (self.base_path / fp).exists():
                c = (self.base_path / fp).read_text(encoding="utf-8")
                if ql in c.lower():
                    e = await self.retrieve(eid)
                    if e:
                        results.append(e)
        results.sort(key=lambda x: x.importance, reverse=True)
        return results[:limit]

    async def delete(self, entry_id: str) -> bool:
        edata = self._index.entries.get(entry_id)
        if not edata:
            return False
        fp = edata.get("file_path")
        if fp and (self.base_path / fp).exists():
            (self.base_path / fp).unlink()
        self._index.remove_entry(entry_id)
        await self._save_index()
        return True

    async def clear(self, memory_type: Optional[MemoryType] = None) -> None:
        if memory_type is None:
            for sd in ["semantic", "episodic"]:
                p = self.base_path / sd
                if p.exists():
                    shutil.rmtree(p)
                    p.mkdir(parents=True, exist_ok=True)
            self._index = MemoryIndex()
        else:
            td = {
                MemoryType.SEMANTIC: "semantic",
                MemoryType.EPISODIC: "episodic",
            }
            p = self.base_path / td.get(memory_type, "semantic")
            if p.exists():
                shutil.rmtree(p)
                p.mkdir(parents=True, exist_ok=True)
            to_rm = [
                eid
                for eid, ed in self._index.entries.items()
                if ed.get("type") == memory_type.value
            ]
            for eid in to_rm:
                self._index.remove_entry(eid)
        await self._save_index()
