"""Plan Manager for task decomposition and planning."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


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


class TaskType(Enum):
    ATOMIC = "atomic"
    COMPOSITE = "composite"
    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"


@dataclass
class Task:
    id: str
    name: str
    description: str
    task_type: TaskType = TaskType.ATOMIC
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    dependencies: list[str] = field(default_factory=list)
    subtasks: list["Task"] = field(default_factory=list)
    parent_id: Optional[str] = None
    assigned_agent: Optional[str] = None
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    estimated_duration: Optional[float] = None
    actual_duration: Optional[float] = None
    retry_count: int = 0
    max_retries: int = 3
    error: Optional[str] = None

    def is_ready(self, completed_tasks: set[str]) -> bool:
        return all(dep in completed_tasks for dep in self.dependencies)

    def is_leaf(self) -> bool:
        return len(self.subtasks) == 0

    def get_all_subtask_ids(self) -> set[str]:
        ids = {self.id}
        for subtask in self.subtasks:
            ids.update(subtask.get_all_subtask_ids())
        return ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "task_type": self.task_type.value,
            "status": self.status.value,
            "priority": self.priority.value,
            "dependencies": self.dependencies,
            "parent_id": self.parent_id,
            "assigned_agent": self.assigned_agent,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "metadata": self.metadata,
        }


@dataclass
class Plan:
    id: str
    name: str
    description: str
    root_task: Task
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_task_by_id(self, task_id: str) -> Optional[Task]:
        return self._find_task(self.root_task, task_id)

    def _find_task(self, task: Task, task_id: str) -> Optional[Task]:
        if task.id == task_id:
            return task
        for subtask in task.subtasks:
            found = self._find_task(subtask, task_id)
            if found:
                return found
        return None

    def get_all_tasks(self) -> list[Task]:
        tasks: list[Task] = []
        self._collect_tasks(self.root_task, tasks)
        return tasks

    def _collect_tasks(self, task: Task, tasks: list[Task]) -> None:
        tasks.append(task)
        for subtask in task.subtasks:
            self._collect_tasks(subtask, tasks)

    def get_leaf_tasks(self) -> list[Task]:
        tasks: list[Task] = []
        self._collect_leaf_tasks(self.root_task, tasks)
        return tasks

    def _collect_leaf_tasks(self, task: Task, tasks: list[Task]) -> None:
        if task.is_leaf():
            tasks.append(task)
        else:
            for subtask in task.subtasks:
                self._collect_leaf_tasks(subtask, tasks)

    def get_ready_tasks(self, completed_tasks: set[str]) -> list[Task]:
        ready: list[Task] = []
        for task in self.get_all_tasks():
            if task.status == TaskStatus.PENDING and task.is_ready(completed_tasks):
                ready.append(task)
        return ready

    def get_progress(self) -> dict[str, Any]:
        all_tasks = self.get_all_tasks()
        total = len(all_tasks)
        completed = sum(1 for t in all_tasks if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in all_tasks if t.status == TaskStatus.FAILED)
        running = sum(1 for t in all_tasks if t.status == TaskStatus.RUNNING)
        pending = sum(1 for t in all_tasks if t.status == TaskStatus.PENDING)

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "pending": pending,
            "progress_percent": (completed / total * 100) if total > 0 else 0,
        }

    def update_task_status(self, task_id: str, status: TaskStatus) -> bool:
        task = self.get_task_by_id(task_id)
        if task:
            task.status = status
            if status == TaskStatus.RUNNING:
                task.started_at = datetime.now()
            elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                task.completed_at = datetime.now()
                if task.started_at:
                    task.actual_duration = (
                        task.completed_at - task.started_at
                    ).total_seconds()
            self.updated_at = datetime.now()
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "root_task": self.root_task.to_dict(),
            "progress": self.get_progress(),
            "metadata": self.metadata,
        }


@dataclass
class PlanConfig:
    max_depth: int = 5
    max_subtasks: int = 10
    enable_parallel: bool = True
    enable_estimation: bool = True
    decomposition_strategy: str = "auto"
    min_task_granularity: str = "medium"


class Planner(ABC):
    @abstractmethod
    async def decompose(
        self,
        task: Task,
        context: dict[str, Any],
    ) -> Task:
        pass

    @abstractmethod
    async def create_plan(
        self,
        goal: str,
        context: dict[str, Any],
    ) -> Plan:
        pass

    @abstractmethod
    async def refine_plan(
        self,
        plan: Plan,
        feedback: dict[str, Any],
    ) -> Plan:
        pass


class PlanManager:
    def __init__(self, config: Optional[PlanConfig] = None):
        self.config = config or PlanConfig()
        self._planner: Optional[Planner] = None
        self._plans: dict[str, Plan] = {}
        self._task_counter = 0
        self._plan_counter = 0

    def set_planner(self, planner: Planner) -> None:
        self._planner = planner

    def _generate_task_id(self) -> str:
        self._task_counter += 1
        return f"task_{self._task_counter}"

    def _generate_plan_id(self) -> str:
        self._plan_counter += 1
        return f"plan_{self._plan_counter}"

    def create_task(
        self,
        name: str,
        description: str,
        task_type: TaskType = TaskType.ATOMIC,
        priority: TaskPriority = TaskPriority.MEDIUM,
        dependencies: Optional[list[str]] = None,
        input_data: Optional[dict[str, Any]] = None,
    ) -> Task:
        return Task(
            id=self._generate_task_id(),
            name=name,
            description=description,
            task_type=task_type,
            priority=priority,
            dependencies=dependencies or [],
            input_data=input_data or {},
        )

    async def create_plan(
        self,
        goal: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Plan:
        if not self._planner:
            raise RuntimeError("Planner not set")

        plan = await self._planner.create_plan(goal, context or {})
        self._plans[plan.id] = plan
        return plan

    async def decompose_task(
        self,
        task: Task,
        context: Optional[dict[str, Any]] = None,
    ) -> Task:
        if not self._planner:
            raise RuntimeError("Planner not set")

        return await self._planner.decompose(task, context or {})

    async def refine_plan(
        self,
        plan_id: str,
        feedback: dict[str, Any],
    ) -> Plan:
        if not self._planner:
            raise RuntimeError("Planner not set")

        plan = self._plans.get(plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")

        refined = await self._planner.refine_plan(plan, feedback)
        self._plans[plan_id] = refined
        return refined

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        return self._plans.get(plan_id)

    def get_next_ready_tasks(
        self,
        plan_id: str,
        completed_tasks: set[str],
    ) -> list[Task]:
        plan = self._plans.get(plan_id)
        if not plan:
            return []
        return plan.get_ready_tasks(completed_tasks)

    def update_task_status(
        self,
        plan_id: str,
        task_id: str,
        status: TaskStatus,
    ) -> bool:
        plan = self._plans.get(plan_id)
        if not plan:
            return False
        return plan.update_task_status(task_id, status)

    def get_execution_order(self, plan_id: str) -> list[list[Task]]:
        plan = self._plans.get(plan_id)
        if not plan:
            return []

        all_tasks = plan.get_all_tasks()
        completed: set[str] = set()
        order: list[list[Task]] = []

        while len(completed) < len(all_tasks):
            ready = [
                t for t in all_tasks
                if t.id not in completed and t.is_ready(completed)
            ]
            if not ready:
                break
            order.append(ready)
            completed.update(t.id for t in ready)

        return order

    def validate_plan(self, plan: Plan) -> tuple[bool, list[str]]:
        errors: list[str] = []
        all_tasks = plan.get_all_tasks()
        task_ids = {t.id for t in all_tasks}

        for task in all_tasks:
            for dep in task.dependencies:
                if dep not in task_ids:
                    errors.append(f"Task {task.id} has invalid dependency: {dep}")

        if self._has_circular_dependency(plan):
            errors.append("Plan has circular dependencies")

        depth = self._get_max_depth(plan.root_task)
        if depth > self.config.max_depth:
            errors.append(f"Plan depth {depth} exceeds max {self.config.max_depth}")

        return len(errors) == 0, errors

    def _has_circular_dependency(self, plan: Plan) -> bool:
        all_tasks = plan.get_all_tasks()
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def has_cycle(task_id: str, task_map: dict[str, Task]) -> bool:
            visited.add(task_id)
            rec_stack.add(task_id)

            task = task_map.get(task_id)
            if task:
                for dep in task.dependencies:
                    if dep not in visited:
                        if has_cycle(dep, task_map):
                            return True
                    elif dep in rec_stack:
                        return True

            rec_stack.remove(task_id)
            return False

        task_map = {t.id: t for t in all_tasks}
        for task in all_tasks:
            if task.id not in visited:
                if has_cycle(task.id, task_map):
                    return True
        return False

    def _get_max_depth(self, task: Task, current_depth: int = 1) -> int:
        if not task.subtasks:
            return current_depth
        return max(
            self._get_max_depth(st, current_depth + 1)
            for st in task.subtasks
        )

    def clear_plans(self) -> None:
        self._plans.clear()
