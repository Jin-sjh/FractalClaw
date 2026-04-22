"""Scheduler module - manages task projects and orchestrates agent execution."""

from __future__ import annotations

import json
import os
import shutil
import uuid
import yaml
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from ..agent import Agent, AgentConfig, AgentContext, AgentResult, BaseAgent, AgentRole
from ..llm import LLMConfig, LLMEngine
from ..memory import MemoryConfig, MemoryManager
from ..plan import Plan, PlanManager
from ..tools import ToolManager
from .agent_workspace import AgentWorkspaceManager, WorkDocument

if TYPE_CHECKING:
    from ..agent.factory import AgentFactory
    from ..agent import SubAgentRequirement


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4


@dataclass
class TaskProject:
    id: str
    name: str
    description: str
    instruction: str
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    workspace_path: str = ""
    result: Optional[str] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["priority"] = self.priority.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskProject":
        data = data.copy()
        data["status"] = TaskStatus(data.get("status", "pending"))
        data["priority"] = TaskPriority(data.get("priority", 2))
        return cls(**data)


@dataclass
class SchedulerConfig:
    workspace_root: str = ""
    max_concurrent_tasks: int = 5
    auto_cleanup_days: int = 30
    enable_logging: bool = True
    log_level: str = "INFO"


class Scheduler:
    """任务调度器，管理项目任务的生命周期和Agent执行。"""

    def __init__(
        self,
        config: Optional[SchedulerConfig] = None,
        agent_factory: Optional["AgentFactory"] = None,
    ):
        self.config = config or SchedulerConfig()
        self._tasks: dict[str, TaskProject] = {}
        self._agents: dict[str, Agent] = {}
        self._agent_factory = agent_factory

        if not self.config.workspace_root:
            self.config.workspace_root = self._get_default_workspace()

        self._ensure_workspace_exists()
        self._workspace_manager = AgentWorkspaceManager(Path(self.config.workspace_root))
        if self._agent_factory:
            self._agent_factory.set_workspace_manager(self._workspace_manager)

    def set_agent_factory(self, agent_factory: "AgentFactory") -> None:
        self._agent_factory = agent_factory
        self._agent_factory.set_workspace_manager(self._workspace_manager)

    def _get_default_workspace(self) -> str:
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent.parent
        workspace_path = project_root / "workspace"
        return str(workspace_path)

    def _ensure_workspace_exists(self) -> None:
        workspace_path = Path(self.config.workspace_root)
        workspace_path.mkdir(parents=True, exist_ok=True)

    def _get_or_create_date_folder(self) -> Path:
        """获取或创建当日日期文件夹"""
        date_str = datetime.now().strftime("%Y%m%d")
        date_folder = Path(self.config.workspace_root) / date_str
        date_folder.mkdir(parents=True, exist_ok=True)
        return date_folder

    def _generate_product_uuid(self) -> str:
        """生成Product格式的UUID"""
        return str(uuid.uuid4())

    def _generate_task_id(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_uuid = uuid.uuid4().hex[:8]
        return f"task_{timestamp}_{short_uuid}"

    def _sanitize_name(self, name: str) -> str:
        invalid_chars = '<>:"/\\|?*'
        sanitized = "".join(c if c not in invalid_chars else "_" for c in name)
        return sanitized.strip()[:50]

    def create_project(
        self,
        instruction: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        priority: TaskPriority = TaskPriority.MEDIUM,
        metadata: Optional[dict[str, Any]] = None,
    ) -> TaskProject:
        """创建新的项目任务，并在workspace中创建对应文件夹。
        
        文件夹结构：
        workspace/
        └── YYYYMMDD/              # 日期文件夹
            └── task_{uuid}_{name}/ # 任务文件夹
        """
        task_uuid = self._generate_product_uuid()
        task_id = f"task_{task_uuid[:8]}"

        original_instruction = instruction
        
        if not name:
            name = self._extract_task_name(instruction) or f"Task_{task_id}"

        if not description:
            description = instruction[:100] + "..." if len(instruction) > 100 else instruction

        project_name = self._sanitize_name(name)
        
        date_folder = self._get_or_create_date_folder()
        project_folder_name = f"{task_id}_{project_name}"
        project_folder = date_folder / project_folder_name
        project_folder.mkdir(parents=True, exist_ok=True)

        self._create_project_structure(project_folder)

        task_metadata = metadata or {}
        task_metadata["original_instruction"] = original_instruction

        task = TaskProject(
            id=task_id,
            name=project_name,
            description=description,
            instruction=instruction,
            status=TaskStatus.PENDING,
            priority=priority,
            workspace_path=str(project_folder),
            metadata=task_metadata,
        )

        self._save_task_metadata(task)
        self._tasks[task_id] = task

        return task

    def _extract_task_name(self, instruction: str) -> Optional[str]:
        """从指令中提取任务名称"""
        import re
        
        instruction = instruction.strip()
        
        patterns = [
            r"^(?:请|帮我|帮我)?(.{2,20})(?:到|写入|保存|创建)",
            r"^(?:写|创建|生成|制作)(.{2,20})",
            r"^(.{2,20})(?:文件|文档|代码)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, instruction)
            if match:
                name = match.group(1).strip()
                name = re.sub(r'[^\w\u4e00-\u9fff]', '', name)
                if name and len(name) >= 2:
                    return name[:30]
        
        if len(instruction) <= 30:
            return instruction
        
        return None

    def _create_project_structure(self, project_path: Path) -> None:
        """创建项目文件夹的标准结构（简化版，按需创建子目录）。"""
        (project_path / "output").mkdir(exist_ok=True)

    def _save_task_metadata(self, task: TaskProject) -> None:
        """保存任务元数据到 memory/semantic/task_metadata.yaml"""
        memory_path = Path(task.workspace_path) / "memory" / "semantic"
        memory_path.mkdir(parents=True, exist_ok=True)
        
        metadata_path = memory_path / "task_metadata.yaml"
        
        metadata = {
            "id": task.id,
            "name": task.name,
            "description": task.description,
            "instruction": task.instruction,
            "status": task.status.value,
            "priority": task.priority.value if hasattr(task.priority, 'value') else task.priority,
            "timestamps": {
                "created": task.created_at,
                "updated": task.updated_at,
                "started": task.started_at,
                "completed": task.completed_at,
            },
            "result": {
                "status": "success" if task.result and not task.error else "failed" if task.error else None,
                "output": task.result,
                "error": task.error,
            },
            "metadata": task.metadata,
        }
        
        with open(metadata_path, 'w', encoding='utf-8') as f:
            yaml.dump(metadata, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def _update_task_metadata(self, task: TaskProject) -> None:
        """更新任务元数据。"""
        task.updated_at = datetime.now().isoformat()
        self._save_task_metadata(task)

    def get_task(self, task_id: str) -> Optional[TaskProject]:
        """获取指定任务。"""
        if task_id in self._tasks:
            return self._tasks[task_id]

        task = self._load_task_from_disk(task_id)
        if task:
            self._tasks[task_id] = task
        return task

    def _load_task_from_disk(self, task_id: str) -> Optional[TaskProject]:
        """从磁盘加载任务元数据。"""
        workspace_path = Path(self.config.workspace_root)

        for date_folder in workspace_path.iterdir():
            if not date_folder.is_dir():
                continue
            
            if not date_folder.name.isdigit() or len(date_folder.name) != 8:
                continue
            
            for task_folder in date_folder.iterdir():
                if task_folder.is_dir() and task_folder.name.startswith(task_id):
                    metadata_path = task_folder / "memory" / "semantic" / "task_metadata.yaml"
                    if metadata_path.exists():
                        with open(metadata_path, "r", encoding="utf-8") as f:
                            data = yaml.safe_load(f)
                        
                        task = TaskProject(
                            id=data["id"],
                            name=data["name"],
                            description=data["description"],
                            instruction=data.get("instruction", ""),
                            status=TaskStatus(data["status"]),
                            priority=TaskPriority(data["priority"]) if "priority" in data else TaskPriority.MEDIUM,
                            workspace_path=str(task_folder),
                            created_at=data["timestamps"].get("created"),
                            updated_at=data["timestamps"].get("updated"),
                            started_at=data["timestamps"].get("started"),
                            completed_at=data["timestamps"].get("completed"),
                            result=data.get("result", {}).get("output"),
                            error=data.get("result", {}).get("error"),
                            metadata=data.get("metadata", {}),
                        )
                        return task

        return None

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None,
    ) -> list[TaskProject]:
        """列出所有任务，可按状态和优先级过滤。"""
        self._sync_tasks_from_disk()

        tasks = list(self._tasks.values())

        if status:
            tasks = [t for t in tasks if t.status == status]
        if priority:
            tasks = [t for t in tasks if t.priority == priority]

        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks

    def _sync_tasks_from_disk(self) -> None:
        """从磁盘同步所有任务。"""
        workspace_path = Path(self.config.workspace_root)

        if not workspace_path.exists():
            return

        for date_folder in workspace_path.iterdir():
            if not date_folder.is_dir():
                continue
            
            if not date_folder.name.isdigit() or len(date_folder.name) != 8:
                continue
            
            for task_folder in date_folder.iterdir():
                if task_folder.is_dir():
                    metadata_path = task_folder / "memory" / "semantic" / "task_metadata.yaml"
                    if metadata_path.exists():
                        with open(metadata_path, "r", encoding="utf-8") as f:
                            data = yaml.safe_load(f)
                        
                        task = TaskProject(
                            id=data["id"],
                            name=data["name"],
                            description=data["description"],
                            instruction=data.get("instruction", ""),
                            status=TaskStatus(data["status"]),
                            priority=TaskPriority(data["priority"]) if "priority" in data else TaskPriority.MEDIUM,
                            workspace_path=str(task_folder),
                            created_at=data["timestamps"].get("created"),
                            updated_at=data["timestamps"].get("updated"),
                            started_at=data["timestamps"].get("started"),
                            completed_at=data["timestamps"].get("completed"),
                            result=data.get("result", {}).get("output"),
                            error=data.get("result", {}).get("error"),
                            metadata=data.get("metadata", {}),
                        )
                        if task.id not in self._tasks:
                            self._tasks[task.id] = task

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        result: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Optional[TaskProject]:
        """更新任务状态。"""
        task = self.get_task(task_id)
        if not task:
            return None

        task.status = status
        task.updated_at = datetime.now().isoformat()

        if status == TaskStatus.RUNNING:
            task.started_at = datetime.now().isoformat()
        elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            task.completed_at = datetime.now().isoformat()

        if result is not None:
            task.result = result
        if error is not None:
            task.error = error

        self._update_task_metadata(task)
        return task

    def delete_task(self, task_id: str, keep_files: bool = False) -> bool:
        """删除任务及其文件。"""
        task = self.get_task(task_id)
        if not task:
            return False

        if not keep_files:
            workspace_path = Path(task.workspace_path)
            if workspace_path.exists():
                shutil.rmtree(workspace_path)

        if task_id in self._tasks:
            del self._tasks[task_id]

        return True

    def cleanup_old_tasks(self, days: Optional[int] = None) -> int:
        """清理过期的已完成任务。"""
        days = days or self.config.auto_cleanup_days
        cutoff = datetime.now().timestamp() - (days * 24 * 60 * 60)
        cleaned = 0

        for task in list(self._tasks.values()):
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                if task.completed_at:
                    completed_time = datetime.fromisoformat(task.completed_at).timestamp()
                    if completed_time < cutoff:
                        self.delete_task(task.id)
                        cleaned += 1

        return cleaned

    async def execute_task(
        self,
        task_id: str,
        agent_config: Optional[AgentConfig] = None,
        existing_config_path: Optional[Path] = None,
    ) -> AgentResult:
        """执行指定任务。"""
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        self.update_task_status(task_id, TaskStatus.RUNNING)

        config = agent_config or AgentConfig(
            name=f"Agent_{task_id}",
            description=task.description,
            role=AgentRole.ROOT,
        )

        if self._agent_factory and existing_config_path and existing_config_path.exists():
            with open(existing_config_path, "r", encoding="utf-8") as f:
                config_dict = yaml.safe_load(f) or {}
            config_dict["role"] = config.role.value
            agent = self._agent_factory.create_from_dict(config_dict)
        elif self._agent_factory:
            agent = self._agent_factory.create_from_config(config)
        else:
            agent = BaseAgent(config)
        self._agents[task_id] = agent

        workspace_path = Path(task.workspace_path)
        agent.set_workspace(workspace_path, self._workspace_manager)

        work_doc = WorkDocument(
            task_requirement=task.instruction,
            acceptance_criteria=task.metadata.get("acceptance_criteria", ""),
            parent_task=None,
        )
        self._workspace_manager.setup_agent_files(
            workspace_path,
            agent,
            work_doc,
            existing_config_path=existing_config_path,
        )

        context = AgentContext(
            task=task.instruction,
            metadata={
                "task_id": task_id,
                "workspace_path": task.workspace_path,
                **task.metadata,
            },
        )

        try:
            result = await agent.run(context)

            if result.success:
                self.update_task_status(
                    task_id,
                    TaskStatus.COMPLETED,
                    result=result.output,
                )
                self._save_execution_result(task, result)
                self._workspace_manager.update_work_document_result(
                    workspace_path, result.output, True
                )
            else:
                self.update_task_status(
                    task_id,
                    TaskStatus.FAILED,
                    error=result.error or "Execution failed",
                )
                self._workspace_manager.update_work_document_result(
                    workspace_path, result.error or "Execution failed", False
                )

            return result

        except Exception as e:
            self.update_task_status(task_id, TaskStatus.FAILED, error=str(e))
            self._workspace_manager.update_work_document_result(
                workspace_path, str(e), False
            )
            raise

        finally:
            if task_id in self._agents:
                del self._agents[task_id]

    def _save_execution_result(self, task: TaskProject, result: AgentResult) -> None:
        """保存执行结果到项目文件夹。"""
        output_path = Path(task.workspace_path) / "output"
        output_path.mkdir(exist_ok=True)

        result_file = output_path / "result.json"
        result_data = {
            "success": result.success,
            "output": result.output,
            "iterations": result.iterations,
            "tool_calls": [
                {
                    "name": tc.name,
                    "arguments": tc.arguments,
                    "result": str(tc.result) if tc.result else None,
                }
                for tc in result.tool_calls
            ],
            "metadata": result.metadata,
        }

        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(result_data, f, indent=2, ensure_ascii=False)

        if result.output:
            output_text = output_path / "output.txt"
            output_text.write_text(result.output, encoding="utf-8")

    def cancel_task(self, task_id: str) -> bool:
        """取消正在执行的任务。"""
        task = self.get_task(task_id)
        if not task:
            return False

        if task.status == TaskStatus.RUNNING:
            if task_id in self._agents:
                agent = self._agents[task_id]
                if hasattr(agent, "stop"):
                    import asyncio
                    asyncio.create_task(agent.stop())

        self.update_task_status(task_id, TaskStatus.CANCELLED)
        return True

    def get_task_logs(self, task_id: str) -> Optional[str]:
        """获取任务执行日志。"""
        task = self.get_task(task_id)
        if not task:
            return None

        log_path = Path(task.workspace_path) / "logs" / "execution.log"
        if log_path.exists():
            return log_path.read_text(encoding="utf-8")

        return None

    def get_statistics(self) -> dict[str, Any]:
        """获取调度器统计信息。"""
        self._sync_tasks_from_disk()

        stats = {
            "total_tasks": len(self._tasks),
            "by_status": {},
            "by_priority": {},
            "workspace_path": self.config.workspace_root,
        }

        for status in TaskStatus:
            stats["by_status"][status.value] = sum(
                1 for t in self._tasks.values() if t.status == status
            )

        for priority in TaskPriority:
            stats["by_priority"][priority.name] = sum(
                1 for t in self._tasks.values() if t.priority == priority
            )

        return stats
