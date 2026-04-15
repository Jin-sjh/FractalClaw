"""Agent Workspace Manager - manages agent workspace structure and files."""

import json
import yaml
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..agent import Agent, SubAgentRequirement


@dataclass
class AgentWorkspaceConfig:
    """Agent工作空间配置"""
    agent_id: str
    agent_name: str
    agent_role: str
    workspace_path: Path
    parent_workspace: Optional[Path] = None
    depth: int = 0


@dataclass
class WorkDocument:
    """work.md 文档内容"""
    task_requirement: str
    acceptance_criteria: str = ""
    parent_task: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: str
    agent_name: str
    agent_id: str
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    tool_output: Optional[str] = None
    agent_state: str = ""
    message: str = ""


class AgentWorkspaceManager:
    """Agent工作空间管理器"""
    
    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
    
    async def create_agent_workspace(
        self, 
        agent: "Agent", 
        parent_workspace: Optional[Path] = None
    ) -> Path:
        """为Agent创建工作空间文件夹"""
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
        """创建工作空间的标准结构（简化版，按需创建子目录）。"""
        (workspace_path / "output").mkdir(exist_ok=True)
    
    def setup_agent_files(
        self, 
        workspace_path: Path, 
        agent: "Agent",
        work_doc: Optional[WorkDocument] = None,
        existing_config_path: Optional[Path] = None
    ) -> None:
        """设置Agent的标准文件（配置、work.md等）
        
        Args:
            workspace_path: workspace路径
            agent: Agent实例
            work_doc: work文档内容
            existing_config_path: 已存在的配置文件路径，如果提供则跳过配置文件生成
        """
        self.write_agent_config(workspace_path, agent, existing_config_path)
        
        if work_doc:
            self.write_work_document(workspace_path, work_doc)
    
    def write_agent_config(
        self, 
        workspace_path: Path, 
        agent: "Agent",
        existing_config_path: Optional[Path] = None
    ) -> None:
        """写入Agent配置文件副本（YAML格式）
        
        Args:
            workspace_path: workspace路径
            agent: Agent实例
            existing_config_path: 已存在的配置文件路径，如果提供则跳过生成
        """
        if existing_config_path and existing_config_path.exists():
            return
        
        config_path = workspace_path / "agent_config.yaml"
        
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
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    
    def _format_tools(self, agent: "Agent") -> str:
        """格式化工具列表"""
        tools = agent.tools.list_tools()
        if not tools:
            return "无"
        
        tool_list = []
        for tool in tools:
            tool_list.append(f"- **{tool.name}**: {tool.description}")
        
        return "\n".join(tool_list)
    
    def write_work_document(self, workspace_path: Path, work_doc: WorkDocument) -> None:
        """写入任务需求到 memory/semantic/task_requirements.md"""
        memory_path = workspace_path / "memory" / "semantic"
        memory_path.mkdir(parents=True, exist_ok=True)
        
        work_path = memory_path / "task_requirements.md"
        
        work_content = f"""---
type: task_requirements
created: {work_doc.created_at}
---

# 任务需求

## 任务描述
{work_doc.task_requirement}

"""
        
        if work_doc.parent_task:
            work_content += f"""## 父任务
{work_doc.parent_task}

"""
        
        if work_doc.acceptance_criteria:
            work_content += f"""## 验收标准
{work_doc.acceptance_criteria}

"""
        
        work_path.write_text(work_content, encoding="utf-8")
    
    def update_work_document_result(
        self, 
        workspace_path: Path, 
        result: str, 
        success: bool
    ) -> None:
        """更新任务需求的验收结果"""
        work_path = workspace_path / "memory" / "semantic" / "task_requirements.md"
        
        if not work_path.exists():
            return
        
        content = work_path.read_text(encoding="utf-8")
        
        result_section = f"""
## 验收结果
- **状态**: {'成功' if success else '失败'}
- **验证时间**: {datetime.now().isoformat()}
- **说明**: {result}
"""
        
        content += result_section
        work_path.write_text(content, encoding="utf-8")
    
    def append_log(self, workspace_path: Path, log_entry: LogEntry) -> None:
        """追加日志条目"""
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
    
    def write_summary(self, workspace_path: Path, summary: str) -> None:
        """写入摘要文件"""
        summary_path = workspace_path / "summary.md"
        
        summary_content = f"""# Agent执行摘要

**生成时间**: {datetime.now().isoformat()}

{summary}
"""
        
        summary_path.write_text(summary_content, encoding="utf-8")
    
    def read_child_summaries(self, workspace_path: Path) -> list[str]:
        """读取所有子Agent的摘要"""
        agents_dir = workspace_path / "agents"
        
        if not agents_dir.exists():
            return []
        
        summaries = []
        for agent_dir in agents_dir.iterdir():
            if agent_dir.is_dir():
                summary_path = agent_dir / "summary.md"
                if summary_path.exists():
                    summaries.append(summary_path.read_text(encoding="utf-8"))
        
        return summaries
    
    async def log_agent_creation(
        self,
        parent_workspace: Path,
        parent_agent: "Agent",
        child_agent: "Agent",
        requirement: "SubAgentRequirement"
    ) -> None:
        """记录子Agent创建日志"""
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
        new_state: str
    ) -> None:
        """记录状态变化"""
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
        result: Any
    ) -> None:
        """记录工具调用"""
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
        error: Exception
    ) -> None:
        """记录错误"""
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
        task_description: str
    ) -> None:
        """记录子任务委托"""
        log_entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            agent_name=parent_agent.name,
            agent_id=parent_agent.id,
            agent_state=parent_agent.state.value,
            message=f"Delegated task to {child_agent.name} (ID: {child_agent.id}): {task_description[:100]}",
        )
        
        self.append_log(workspace_path, log_entry)
    
    def log_state_change(
        self,
        workspace_path: Path,
        agent: "Agent",
        old_state: str,
        new_state: str
    ) -> None:
        """记录状态变化"""
        log_entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            agent_name=agent.name,
            agent_id=agent.id,
            agent_state=new_state,
            message=f"State changed: {old_state} -> {new_state}",
        )
        
        self.append_log(workspace_path, log_entry)
