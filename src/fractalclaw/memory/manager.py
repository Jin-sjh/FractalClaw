from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .models import (
    MemoryEntry,
    MemoryType,
    MemoryScope,
    MemoryConfig,
    SessionSummary,
)
from .store import MemoryStore
from .markdown_store import MarkdownStore
from .session import SessionManager
from .sharing import MemorySharing
from .global_store import GlobalMemoryStore
from .daily_log import DailyLogManager
from .working_memory import WorkingMemoryManager
from .heartbeat import HeartbeatWorker


class MemoryManager:
    def __init__(
        self,
        config: Optional[MemoryConfig] = None,
        store: Optional[MemoryStore] = None,
    ):
        self.config = config or MemoryConfig()
        self._store = store
        self._working: list[MemoryEntry] = []
        self._entry_counter = 0
        self._initialized = False
        self._session: Optional[SessionManager] = None
        self._sharing: Optional[MemorySharing] = None
        self._global_store: Optional[GlobalMemoryStore] = None
        self._workspace_path: Optional[Path] = None
        self._agent_id: Optional[str] = None
        self._agent_name: Optional[str] = None
        self._task_id: Optional[str] = None
        self._working_memory: Optional[WorkingMemoryManager] = None
        self._heartbeat: Optional[HeartbeatWorker] = None
        self._daily_log_global: Optional[DailyLogManager] = None

    async def initialize(self) -> None:
        if self._initialized:
            return
        if self.config.enable_persistence and not self._store and self._workspace_path:
            memory_path = self._workspace_path / "memory"
            memory_path.mkdir(parents=True, exist_ok=True)
            self._store = MarkdownStore(memory_path)
            await self._store.initialize()
        if self._workspace_path:
            self._sharing = MemorySharing(self._workspace_path)
        self._global_store = GlobalMemoryStore()
        await self._global_store.initialize()
        if self.config.enable_working_memory:
            self._working_memory = WorkingMemoryManager(self._global_store.base_path)
            await self._working_memory.initialize()
            self._daily_log_global = DailyLogManager(self._global_store.base_path)
            if self.config.heartbeat_interval_hours > 0:
                self._heartbeat = HeartbeatWorker(
                    self._working_memory,
                    self._daily_log_global,
                    self.config.heartbeat_interval_hours,
                )
        self._initialized = True
        
        await self._update_memory_index()

    async def _update_memory_index(self) -> None:
        """更新 memory/INDEX.md"""
        if not self._workspace_path:
            return
        
        index_path = self._workspace_path / "memory" / "INDEX.md"
        
        index_content = f"""# Memory Index

Last Updated: {datetime.now().isoformat()}

## SEMANTIC

- [task_metadata](semantic/task_metadata.yaml) - 任务元数据
- [task_requirements](semantic/task_requirements.md) - 任务需求和验收

## EPISODIC

- [daily](episodic/daily/) - 日志汇总
- [sessions](episodic/sessions/) - 完整对话记录

## SHARED

- [from_parent](shared/from_parent.md) - 父Agent传递的记忆
- [from_children](shared/from_children/) - 子Agent反馈的记忆
"""
        
        index_path.write_text(index_content, encoding="utf-8")

    def bind_agent(
        self, agent_id: str, agent_name: str, workspace_path: Path
    ) -> None:
        self._agent_id = agent_id
        self._agent_name = agent_name
        self._workspace_path = workspace_path

    def set_task_id(self, task_id: str) -> None:
        self._task_id = task_id

    def set_store(self, store: MemoryStore) -> None:
        self._store = store

    async def start_session(self, task: Optional[str] = None) -> None:
        if not self._initialized:
            await self.initialize()
        if (
            self.config.enable_session_save
            and self._workspace_path
            and self._agent_id
        ):
            self._session = SessionManager(
                self._workspace_path, self._agent_id, self._agent_name or "Agent"
            )
            self._session.start(task)

    def _generate_id(self) -> str:
        self._entry_counter += 1
        return f"mem_{self._entry_counter}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    async def add(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.WORKING,
        metadata: Optional[dict[str, Any]] = None,
        importance: float = 0.5,
        title: Optional[str] = None,
        tags: Optional[list[str]] = None,
        source_agent_id: Optional[str] = None,
        scope: MemoryScope = MemoryScope.TASK,
    ) -> MemoryEntry:
        if not self._initialized:
            await self.initialize()
        entry = MemoryEntry(
            id=self._generate_id(),
            content=content,
            memory_type=memory_type,
            metadata=metadata or {},
            importance=importance,
            title=title,
            tags=tags or [],
            source_agent_id=source_agent_id or self._agent_id,
            scope=scope,
        )
        if memory_type == MemoryType.WORKING:
            self._add_to_working(entry)
        elif scope == MemoryScope.GLOBAL and self._global_store:
            await self._global_store.store(entry)
        elif self._store:
            await self._store.store(entry)
        if self._session and memory_type == MemoryType.WORKING:
            self._session.add_message("system", f"[Memory] {content[:100]}")
        return entry

    def _add_to_working(self, entry: MemoryEntry) -> None:
        self._working.append(entry)
        if len(self._working) > self.config.max_working_entries:
            self._working.pop(0)

    async def retrieve(self, entry_id: str) -> Optional[MemoryEntry]:
        for entry in self._working:
            if entry.id == entry_id:
                entry.accessed_at = datetime.now()
                entry.access_count += 1
                return entry
        if self._store:
            result = await self._store.retrieve(entry_id)
            if result:
                return result
        if self._global_store:
            return await self._global_store.retrieve(entry_id)
        return None

    async def search(
        self,
        query: str,
        memory_types: Optional[list[MemoryType]] = None,
        limit: int = 10,
        include_global: bool = True,
    ) -> list[MemoryEntry]:
        memory_types = memory_types or [MemoryType.WORKING]
        results: list[MemoryEntry] = []
        if MemoryType.WORKING in memory_types:
            results.extend(self._fuzzy_search(query, self._working))
        if MemoryType.EPISODIC in memory_types and self._store:
            results.extend(
                await self._store.search(query, MemoryType.EPISODIC, limit)
            )
        if MemoryType.SEMANTIC in memory_types and self._store:
            results.extend(
                await self._store.search(query, MemoryType.SEMANTIC, limit)
            )
        if include_global and self._global_store:
            results.extend(await self._global_store.search_global(query, limit))
        results.sort(key=lambda x: x.importance, reverse=True)
        return results[:limit]

    def _fuzzy_search(
        self,
        query: str,
        entries: list[MemoryEntry],
    ) -> list[MemoryEntry]:
        query_lower = query.lower()
        results: list[tuple[MemoryEntry, float]] = []
        for entry in entries:
            content_lower = entry.content.lower()
            if query_lower in content_lower:
                score = self._calculate_relevance(query_lower, content_lower)
                results.append((entry, score))
        results.sort(key=lambda x: x[1], reverse=True)
        return [entry for entry, _ in results]

    def _calculate_relevance(self, query: str, content: str) -> float:
        if query in content:
            return 1.0
        query_words = set(query.split())
        content_words = set(content.split())
        overlap = len(query_words & content_words)
        return overlap / max(len(query_words), 1)

    async def update_importance(
        self,
        entry_id: str,
        importance: float,
    ) -> bool:
        entry = await self.retrieve(entry_id)
        if entry:
            entry.importance = importance
            return True
        return False

    def get_working_memory(self) -> list[MemoryEntry]:
        return self._working.copy()

    async def clear(
        self,
        memory_type: Optional[MemoryType] = None,
    ) -> None:
        if memory_type is None or memory_type == MemoryType.WORKING:
            self._working.clear()
        if self._store and (
            memory_type is None or memory_type in [MemoryType.EPISODIC, MemoryType.SEMANTIC]
        ):
            await self._store.clear(memory_type)

    async def end_session(
        self,
        result_summary: Optional[str] = None,
        result_status: str = "success",
    ) -> None:
        if self._session:
            summary_data = self._session.finish(result_summary, result_status)
            if self._daily_log_global and summary_data:
                session_summary = SessionSummary(
                    session_id=summary_data["session_id"],
                    task_id=self._task_id,
                    task=summary_data["task"],
                    result_status=summary_data["result_status"],
                    result_summary=summary_data["result_summary"],
                    session_file_path=summary_data["session_file_path"],
                    started_at=summary_data["started_at"],
                    completed_at=summary_data["completed_at"],
                )
                await self._daily_log_global.append_session_summary(session_summary)
            self._session = None

    async def progressive_disclose(self, date: str, level: int = 1) -> str:
        if self._working_memory:
            return await self._working_memory.progressive_disclose(date, level, self._daily_log_global)
        return ""

    async def trigger_heartbeat(self) -> None:
        if self._heartbeat:
            await self._heartbeat.trigger_now()

    async def start_heartbeat(self) -> None:
        if self._heartbeat:
            await self._heartbeat.start()

    async def stop_heartbeat(self) -> None:
        if self._heartbeat:
            await self._heartbeat.stop()

    @property
    def sharing(self) -> Optional[MemorySharing]:
        return self._sharing

    @property
    def session(self) -> Optional[SessionManager]:
        return self._session

    @property
    def daily_log(self) -> Optional[DailyLogManager]:
        return self._daily_log_global

    @property
    def working_memory(self) -> Optional[WorkingMemoryManager]:
        return self._working_memory
