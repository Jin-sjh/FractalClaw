"""Agent workspace management utilities."""

from __future__ import annotations

import asyncio
import json
import shutil
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import yaml

if TYPE_CHECKING:
    from ..agent import Agent, SubAgentRequirement


@dataclass
class AgentWorkspaceConfig:
    """Metadata for an agent workspace."""

    agent_id: str
    agent_name: str
    agent_role: str
    workspace_path: Path
    parent_workspace: Optional[Path] = None
    depth: int = 0


@dataclass
class WorkDocument:
    """Structured task requirements stored in the workspace."""

    task_requirement: str
    acceptance_criteria: str = ""
    parent_task: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class LogEntry:
    """A single execution log entry."""

    timestamp: str
    agent_name: str
    agent_id: str
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    tool_output: Optional[str] = None
    agent_state: str = ""
    message: str = ""


class LogBuffer:
    """日志缓冲区，用于批量写入日志以提高性能"""
    
    def __init__(
        self,
        max_size: int = 100,
        flush_interval: float = 5.0,
    ):
        self.max_size = max_size
        self.flush_interval = flush_interval
        self._buffer: deque[dict[str, Any]] = deque()
        self._lock = asyncio.Lock()
        self._last_flush: Optional[float] = None
    
    def add(self, entry: dict[str, Any]) -> bool:
        """添加日志条目到缓冲区，返回是否需要刷新"""
        self._buffer.append(entry)
        return len(self._buffer) >= self.max_size
    
    def should_flush(self) -> bool:
        """检查是否应该刷新缓冲区"""
        if len(self._buffer) >= self.max_size:
            return True
        if self._last_flush is None:
            return False
        return (datetime.now().timestamp() - self._last_flush) >= self.flush_interval
    
    def get_and_clear(self) -> list[dict[str, Any]]:
        """获取并清空缓冲区"""
        entries = list(self._buffer)
        self._buffer.clear()
        self._last_flush = datetime.now().timestamp()
        return entries
    
    def __len__(self) -> int:
        return len(self._buffer)


class AgentWorkspaceManager:
    """Manage task and agent workspace structure and logs."""

    def __init__(
        self,
        workspace_root: Path,
        log_buffer_size: int = 100,
        log_flush_interval: float = 5.0,
    ):
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self._log_buffer = LogBuffer(
            max_size=log_buffer_size,
            flush_interval=log_flush_interval,
        )
        self._aiofiles_available = self._check_aiofiles()
    
    def _check_aiofiles(self) -> bool:
        """检查 aiofiles 是否可用"""
        try:
            import aiofiles
            return True
        except ImportError:
            return False

    async def create_agent_workspace(
        self,
        agent: "Agent",
        parent_workspace: Optional[Path] = None,
    ) -> Path:
        """Create a workspace for an agent."""
        agent_folder_name = f"agent_{agent.id}_{agent.name}"

        if parent_workspace:
            agents_dir = parent_workspace / "agents"
            agents_dir.mkdir(exist_ok=True)
            workspace_path = agents_dir / agent_folder_name
        else:
            workspace_path = self.workspace_root / agent_folder_name

        workspace_path.mkdir(parents=True, exist_ok=True)
        self._create_workspace_structure(workspace_path)
        return workspace_path

    def _create_workspace_structure(self, workspace_path: Path) -> None:
        """Create the minimal workspace structure used by the runtime."""
        (workspace_path / "output").mkdir(exist_ok=True)

    def setup_agent_files(
        self,
        workspace_path: Path,
        agent: "Agent",
        work_doc: Optional[WorkDocument] = None,
        existing_config_path: Optional[Path] = None,
    ) -> None:
        """Write the standard files used in an agent workspace."""
        self.write_agent_config(workspace_path, agent, existing_config_path)
        if work_doc:
            self.write_work_document(workspace_path, work_doc)

    def write_agent_config(
        self,
        workspace_path: Path,
        agent: "Agent",
        existing_config_path: Optional[Path] = None,
    ) -> None:
        """Persist the agent config into the workspace."""
        config_path = workspace_path / "agent_config.yaml"
        if existing_config_path and existing_config_path.exists():
            if existing_config_path.resolve() != config_path.resolve():
                shutil.copyfile(existing_config_path, config_path)
            return

        config_data = {
            "name": agent.name,
            "id": agent.id,
            "role": agent.config.role.value,
            "description": agent.config.description,
            "max_iterations": agent.config.max_iterations,
            "enable_planning": agent.config.enable_planning,
            "enable_reflection": agent.config.enable_reflection,
            "system_prompt": agent.config.system_prompt or "",
            "tools": [
                {"name": tool.name, "description": tool.description}
                for tool in agent.tools.list_tools()
            ],
            "created_at": datetime.now().isoformat(),
        }

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(
                config_data,
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )

    def _format_tools(self, agent: "Agent") -> str:
        """Format the agent tool list for human-readable summaries."""
        tools = agent.tools.list_tools()
        if not tools:
            return "None"

        return "\n".join(f"- **{tool.name}**: {tool.description}" for tool in tools)

    def write_work_document(self, workspace_path: Path, work_doc: WorkDocument) -> None:
        """Write task requirements into the semantic memory area."""
        memory_path = workspace_path / "memory" / "semantic"
        memory_path.mkdir(parents=True, exist_ok=True)

        work_path = memory_path / "task_requirements.md"
        work_content = f"""---
type: task_requirements
created: {work_doc.created_at}
---

# Task Requirements
## Task Description
{work_doc.task_requirement}

"""

        if work_doc.parent_task:
            work_content += f"""## Parent Task
{work_doc.parent_task}

"""

        if work_doc.acceptance_criteria:
            work_content += f"""## Acceptance Criteria
{work_doc.acceptance_criteria}

"""

        work_path.write_text(work_content, encoding="utf-8")

    def update_work_document_result(
        self,
        workspace_path: Path,
        result: str,
        success: bool,
    ) -> None:
        """Append the execution result to the task requirements document."""
        work_path = workspace_path / "memory" / "semantic" / "task_requirements.md"
        if not work_path.exists():
            return

        content = work_path.read_text(encoding="utf-8")
        result_section = f"""
## Execution Result
- **Status**: {'Success' if success else 'Failed'}
- **Verified At**: {datetime.now().isoformat()}
- **Details**: {result}
"""

        work_path.write_text(content + result_section, encoding="utf-8")

    def append_log(self, workspace_path: Path, log_entry: LogEntry) -> None:
        """Append a structured log entry."""
        log_path = workspace_path / "execution.log"
        log_data = {
            "timestamp": log_entry.timestamp,
            "agent_name": log_entry.agent_name,
            "agent_id": log_entry.agent_id,
            "tool_name": log_entry.tool_name,
            "tool_args": log_entry.tool_args,
            "tool_output": log_entry.tool_output,
            "agent_state": log_entry.agent_state,
            "message": log_entry.message,
        }

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_data, ensure_ascii=False) + "\n")

    async def async_append_log(self, workspace_path: Path, log_entry: LogEntry) -> None:
        """异步追加日志条目，支持缓冲区批量写入"""
        log_data = {
            "timestamp": log_entry.timestamp,
            "agent_name": log_entry.agent_name,
            "agent_id": log_entry.agent_id,
            "tool_name": log_entry.tool_name,
            "tool_args": log_entry.tool_args,
            "tool_output": log_entry.tool_output,
            "agent_state": log_entry.agent_state,
            "message": log_entry.message,
        }
        
        if self._log_buffer.add(log_data):
            await self._flush_log_buffer(workspace_path)
    
    async def _flush_log_buffer(self, workspace_path: Path) -> None:
        """刷新日志缓冲区到文件"""
        if len(self._log_buffer) == 0:
            return
        
        entries = self._log_buffer.get_and_clear()
        log_path = workspace_path / "execution.log"
        
        lines = [json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries]
        content = "".join(lines)
        
        if self._aiofiles_available:
            import aiofiles
            async with aiofiles.open(log_path, "a", encoding="utf-8") as f:
                await f.write(content)
        else:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(content)
    
    async def flush_logs(self, workspace_path: Path) -> None:
        """手动刷新日志缓冲区"""
        await self._flush_log_buffer(workspace_path)

    def write_summary(self, workspace_path: Path, summary: str) -> None:
        """Write a markdown summary for the workspace."""
        summary_path = workspace_path / "summary.md"
        summary_content = f"""# Agent Execution Summary

**Generated At**: {datetime.now().isoformat()}

{summary}
"""
        summary_path.write_text(summary_content, encoding="utf-8")

    def append_jsonl_event(
        self,
        workspace_path: Path,
        filename: str,
        payload: dict[str, Any],
    ) -> None:
        """Append a structured JSONL event to the workspace."""
        event_path = workspace_path / filename
        event_payload = {
            "timestamp": datetime.now().isoformat(),
            **payload,
        }
        with open(event_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_payload, ensure_ascii=False) + "\n")

    def log_delegation_event(
        self,
        workspace_path: Path,
        payload: dict[str, Any],
    ) -> None:
        """Record delegation and governance decisions for auditability."""
        self.append_jsonl_event(workspace_path, "delegation_log.jsonl", payload)

    def log_execution_wave(
        self,
        workspace_path: Path,
        payload: dict[str, Any],
    ) -> None:
        """Record wave execution details."""
        self.append_jsonl_event(workspace_path, "execution_waves.jsonl", payload)

    def read_child_summaries(self, workspace_path: Path) -> list[str]:
        """Read summary files from child agent workspaces."""
        agents_dir = workspace_path / "agents"
        if not agents_dir.exists():
            return []

        summaries = []
        for agent_dir in agents_dir.iterdir():
            if not agent_dir.is_dir():
                continue
            summary_path = agent_dir / "summary.md"
            if summary_path.exists():
                summaries.append(summary_path.read_text(encoding="utf-8"))

        return summaries

    async def log_agent_creation(
        self,
        parent_workspace: Path,
        parent_agent: "Agent",
        child_agent: "Agent",
        requirement: "SubAgentRequirement",
    ) -> None:
        """Record child-agent creation in the parent workspace log."""
        _ = requirement
        log_entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            agent_name=parent_agent.name,
            agent_id=parent_agent.id,
            agent_state=parent_agent.state.value,
            message=f"Created subagent: {child_agent.name} (ID: {child_agent.id})",
        )
        self.append_log(parent_workspace, log_entry)

    def log_state_change(
        self,
        workspace_path: Path,
        agent: "Agent",
        old_state: str,
        new_state: str,
    ) -> None:
        """Record an agent state transition."""
        log_entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            agent_name=agent.name,
            agent_id=agent.id,
            agent_state=new_state,
            message=f"State changed: {old_state} -> {new_state}",
        )
        self.append_log(workspace_path, log_entry)

    def log_tool_call(
        self,
        workspace_path: Path,
        agent: "Agent",
        tool_name: str,
        args: dict,
        result: Any,
    ) -> None:
        """Record a tool call."""
        log_entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            agent_name=agent.name,
            agent_id=agent.id,
            tool_name=tool_name,
            tool_args=args,
            tool_output=str(result),
            agent_state=agent.state.value,
            message=f"Tool call: {tool_name}",
        )
        self.append_log(workspace_path, log_entry)

    def log_error(
        self,
        workspace_path: Path,
        agent: "Agent",
        error: Exception,
    ) -> None:
        """Record an error in the execution log."""
        log_entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            agent_name=agent.name,
            agent_id=agent.id,
            agent_state=agent.state.value,
            message=f"Error: {str(error)}",
        )
        self.append_log(workspace_path, log_entry)

    def log_subtask_delegation(
        self,
        workspace_path: Path,
        parent_agent: "Agent",
        child_agent: "Agent",
        task_description: str,
    ) -> None:
        """Record delegation of a subtask to a child agent."""
        log_entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            agent_name=parent_agent.name,
            agent_id=parent_agent.id,
            agent_state=parent_agent.state.value,
            message=(
                f"Delegated task to {child_agent.name} (ID: {child_agent.id}): "
                f"{task_description[:100]}"
            ),
        )
        self.append_log(workspace_path, log_entry)
