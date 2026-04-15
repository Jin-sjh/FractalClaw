import asyncio
from datetime import datetime
from typing import Optional

from .daily_log import DailyLogManager
from .working_memory import WorkingMemoryManager


class HeartbeatWorker:
    def __init__(
        self,
        working_memory_manager: WorkingMemoryManager,
        daily_log_manager: DailyLogManager,
        interval_hours: int = 24,
    ):
        self._working_memory = working_memory_manager
        self._daily_log = daily_log_manager
        self._interval_hours = interval_hours
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while self._running:
            await asyncio.sleep(self._interval_hours * 3600)
            await self._trigger_heartbeat()

    async def _trigger_heartbeat(self) -> None:
        await self._working_memory.heartbeat(self._daily_log)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def trigger_now(self) -> None:
        await self._trigger_heartbeat()

    @property
    def last_heartbeat(self) -> Optional[datetime]:
        return getattr(self._working_memory, "_last_heartbeat", None)
