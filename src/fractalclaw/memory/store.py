from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .models import MemoryEntry, MemoryType


class MemoryStore(ABC):
    @abstractmethod
    async def store(self, entry: MemoryEntry) -> str:
        pass

    @abstractmethod
    async def retrieve(self, entry_id: str) -> Optional[MemoryEntry]:
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        memory_type: Optional[MemoryType] = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        pass

    @abstractmethod
    async def delete(self, entry_id: str) -> bool:
        pass

    @abstractmethod
    async def clear(self, memory_type: Optional[MemoryType] = None) -> None:
        pass
