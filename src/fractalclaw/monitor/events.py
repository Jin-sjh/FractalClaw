"""Event collection system for FractalClaw monitoring."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class EventType(Enum):
    """Types of monitoring events."""

    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"

    AGENT_SPAWNED = "agent_spawned"
    AGENT_STATE_CHANGED = "agent_state_changed"
    AGENT_DESTROYED = "agent_destroyed"

    WAVE_STARTED = "wave_started"
    WAVE_FINISHED = "wave_finished"

    TOOL_CALLED = "tool_called"
    TOOL_RESULT = "tool_result"

    DELEGATION_DECISION = "delegation_decision"
    DELEGATION_CREATED = "delegation_created"
    DELEGATION_REJECTED = "delegation_rejected"
    DELEGATION_RESULT = "delegation_result"

    PLAN_CREATED = "plan_created"
    REPLAN_TRIGGERED = "replan_triggered"

    ITERATION_COMPLETED = "iteration_completed"


@dataclass
class FractalEvent:
    """A structured event for monitoring visualization."""

    event_type: EventType
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:8]}")
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    agent_role: Optional[str] = None
    parent_agent_id: Optional[str] = None
    depth: int = 0
    branch_path: str = "root"
    state: Optional[str] = None
    tool_name: Optional[str] = None
    wave_id: Optional[str] = None
    success: Optional[bool] = None
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["event_type"] = self.event_type.value
        return data

    def to_jsonl(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False) + "\n"


class EventCollector:
    """Collects and persists fractal events for monitoring."""

    def __init__(
        self,
        workspace_root: Path,
        buffer_size: int = 1,
        flush_interval: float = 0.5,
    ):
        self.workspace_root = Path(workspace_root)
        self._buffer: list[FractalEvent] = []
        self._buffer_size = buffer_size
        self._flush_interval = flush_interval
        self._lock = threading.Lock()
        self._task: Optional[asyncio.Task] = None
        self._shutdown = False
        self._event_file: Optional[Path] = None
        self._callbacks: list[callable] = []

    def add_callback(self, callback: callable) -> None:
        """Add a callback to be called on every event."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: callable) -> None:
        """Remove a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def set_task(self, task_id: str) -> None:
        """Set the current task and create event file."""
        monitor_dir = self.workspace_root / ".monitor"
        monitor_dir.mkdir(parents=True, exist_ok=True)
        self._event_file = monitor_dir / f"{task_id}_events.jsonl"

    def emit(self, event: FractalEvent) -> None:
        """Emit an event to the collector."""
        with self._lock:
            self._buffer.append(event)
            needs_flush = len(self._buffer) >= self._buffer_size

        for callback in self._callbacks:
            try:
                callback(event)
            except Exception:
                pass

        if needs_flush:
            self._flush_sync()

    def emit_from_agent(
        self,
        event_type: EventType,
        agent: Any,
        **kwargs: Any,
    ) -> None:
        """Convenience method to emit an event from an agent."""
        from fractalclaw.agent import Agent

        if not isinstance(agent, Agent):
            self.emit(
                FractalEvent(
                    event_type=event_type,
                    message=kwargs.get("message", ""),
                    metadata=kwargs.get("metadata", {}),
                )
            )
            return

        parent = agent.get_parent()
        event = FractalEvent(
            event_type=event_type,
            agent_id=agent.id,
            agent_name=agent.name,
            agent_role=agent.config.role.value if agent.config.role else None,
            parent_agent_id=parent.id if parent else None,
            depth=agent.tree.depth,
            state=agent.state.value if agent.state else None,
            **kwargs,
        )
        self.emit(event)

    def _flush_sync(self) -> None:
        """Synchronous flush of buffered events."""
        if not self._event_file:
            return

        with self._lock:
            events = self._buffer[:]
            self._buffer.clear()

        if not events:
            return

        lines = [e.to_jsonl() for e in events]
        try:
            with open(self._event_file, "a", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception:
            pass

    async def flush(self) -> None:
        """Async flush of buffered events."""
        self._flush_sync()

    async def start_auto_flush(self) -> None:
        """Start automatic periodic flushing."""
        while not self._shutdown:
            await asyncio.sleep(self._flush_interval)
            await self.flush()

    def stop(self) -> None:
        """Stop the collector and flush remaining events."""
        self._shutdown = True
        self._flush_sync()

    def read_events(self, task_id: Optional[str] = None) -> list[FractalEvent]:
        """Read all events from the event file."""
        if task_id:
            event_file = self.workspace_root / ".monitor" / f"{task_id}_events.jsonl"
        else:
            event_file = self._event_file

        if not event_file or not event_file.exists():
            return []

        events = []
        try:
            with open(event_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        data["event_type"] = EventType(data["event_type"])
                        events.append(FractalEvent(**data))
                    except (json.JSONDecodeError, ValueError):
                        continue
        except Exception:
            pass

        return events


# Global event collector instance
_global_collector: Optional[EventCollector] = None
_global_lock = threading.Lock()


def get_event_collector() -> Optional[EventCollector]:
    """Get the global event collector."""
    return _global_collector


def set_event_collector(collector: EventCollector) -> None:
    """Set the global event collector."""
    global _global_collector
    with _global_lock:
        _global_collector = collector


def emit_event(event: FractalEvent) -> None:
    """Emit an event to the global collector."""
    collector = get_event_collector()
    if collector:
        collector.emit(event)


def emit_agent_event(
    event_type: EventType,
    agent: Any,
    **kwargs: Any,
) -> None:
    """Emit an agent event to the global collector."""
    collector = get_event_collector()
    if collector:
        collector.emit_from_agent(event_type, agent, **kwargs)
