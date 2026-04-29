"""Canonical type definitions shared across modules.

This module provides the single source of truth for enums and types
that were previously duplicated across agent, llm, plan, and scheduler.
"""

from __future__ import annotations

from enum import Enum


class TaskComplexity(Enum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


class TaskStructure(Enum):
    ATOMIC = "atomic"
    COMPOSITE = "composite"
    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"


class TaskDomain(Enum):
    CODE = "code"
    RESEARCH = "research"
    REASONING = "reasoning"
    CHAT = "chat"
    WRITING = "writing"
    GENERAL = "general"

    @classmethod
    def from_legacy(cls, value: str) -> "TaskDomain":
        """兼容旧的任务类型名称。"""
        legacy_map = {
            "coordinate": cls.REASONING,
            "test": cls.CODE,
            "data": cls.RESEARCH,
        }
        return legacy_map.get(value, cls(value))


class TaskStatus(Enum):
    PENDING = "pending"
    PLANNED = "planned"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class TaskPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class TaskImportance(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
