"""Agent配置加载器"""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field


@dataclass
class GlobalSettings:
    """全局配置"""
    llm: dict[str, Any] = field(default_factory=lambda: {
        "model": "gpt-4",
        "temperature": 0.7,
        "max_tokens": 4096,
        "top_p": 1.0,
        "stream": True,
        "timeout": 60.0
    })
    behavior: dict[str, Any] = field(default_factory=lambda: {
        "max_iterations": 10,
        "enable_planning": True,
        "enable_reflection": True,
        "max_replan_attempts": 3
    })
    memory: dict[str, Any] = field(default_factory=lambda: {
        "max_short_term_entries": 100,
        "max_working_entries": 10,
        "enable_long_term": True,
        "enable_persistence": True,
        "enable_session_save": True,
    })
    planning: dict[str, Any] = field(default_factory=lambda: {
        "max_depth": 5,
        "max_subtasks": 10,
        "enable_parallel": True
    })
    tools: dict[str, Any] = field(default_factory=lambda: {
        "max_concurrent_calls": 5,
        "default_timeout": 30.0,
        "enable_approval": False
    })


@dataclass
class WorkflowStep:
    """工作流步骤"""
    step: int
    name: str
    description: str
    action: str


@dataclass
class WorkflowConfig:
    """工作流配置"""
    name: str
    steps: list[WorkflowStep] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowConfig":
        steps = [
            WorkflowStep(
                step=s.get("step", i + 1),
                name=s.get("name", ""),
                description=s.get("description", ""),
                action=s.get("action", ""),
            )
            for i, s in enumerate(data.get("steps", []))
        ]
        return cls(name=data.get("name", ""), steps=steps)


@dataclass
class AgentConfigData:
    """Agent配置数据"""
    name: str
    description: str = ""
    role: str = "worker"
    llm: dict[str, Any] = field(default_factory=dict)
    behavior: dict[str, Any] = field(default_factory=dict)
    system_prompt: str = ""
    tools: list[dict] = field(default_factory=list)
    parent: str = ""
    children: list[str] = field(default_factory=list)
    workflow: Optional[WorkflowConfig] = None
    source_path: Optional[Path] = None


class ConfigLoader:
    """配置加载器"""
    
    MAX_MERGE_DEPTH = 10
    
    def __init__(self, config_dir: Path = None):
        self.config_dir = Path(config_dir) if config_dir else Path("configs")
        self.settings: Optional[GlobalSettings] = None
        self._cache: dict[str, AgentConfigData] = {}
    
    @staticmethod
    def deep_merge(base: dict, update: dict, depth: int = 0) -> dict:
        """深度合并两个字典，update 中的值会覆盖 base 中的对应值
        
        Args:
            base: 基础字典（默认配置）
            update: 更新字典（用户配置）
            depth: 当前递归深度，用于防止无限递归
            
        Returns:
            合并后的字典
        """
        if depth > ConfigLoader.MAX_MERGE_DEPTH:
            return update.copy()
        
        result = {}
        for key in base:
            result[key] = base[key]
        
        for key, value in update.items():
            if (
                key in result 
                and isinstance(result[key], dict) 
                and isinstance(value, dict)
                and id(result[key]) != id(value)
            ):
                result[key] = ConfigLoader.deep_merge(result[key], value, depth + 1)
            else:
                result[key] = value
        
        return result
    
    def load_settings(self) -> GlobalSettings:
        """加载全局配置，使用深度合并确保用户配置与默认配置完美融合"""
        if self.settings:
            return self.settings
        
        default_settings = GlobalSettings()
        default_dict = {
            'llm': default_settings.llm,
            'behavior': default_settings.behavior,
            'memory': default_settings.memory,
            'planning': default_settings.planning,
            'tools': default_settings.tools,
        }
        
        settings_path = self.config_dir / "settings.yaml"
        if settings_path.exists():
            with open(settings_path, 'r', encoding='utf-8') as f:
                user_data = yaml.safe_load(f) or {}
            
            merged = self.deep_merge(default_dict, user_data)
        else:
            merged = default_dict
        
        self.settings = GlobalSettings(
            llm=merged.get('llm', {}),
            behavior=merged.get('behavior', {}),
            memory=merged.get('memory', {}),
            planning=merged.get('planning', {}),
            tools=merged.get('tools', {})
        )
        
        return self.settings
    
    def load(self, agent_id: str) -> AgentConfigData:
        """加载Agent配置"""
        if agent_id in self._cache:
            return self._cache[agent_id]
        
        agents_dir = self.config_dir / "agents"
        path = agents_dir / f"{agent_id}.yaml"
        
        if not path.exists():
            raise FileNotFoundError(f"Agent config not found: {path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        
        workflow_data = data.get('workflow')
        workflow = WorkflowConfig.from_dict(workflow_data) if workflow_data else None

        config = AgentConfigData(
            name=data.get('name', agent_id),
            description=data.get('description', ''),
            role=data.get('role', 'worker'),
            llm=data.get('llm', {}),
            behavior=data.get('behavior', {}),
            system_prompt=data.get('system_prompt', ''),
            tools=data.get('tools', []),
            parent=data.get('parent', ''),
            children=data.get('children', []),
            workflow=workflow,
            source_path=path
        )
        
        config = self.merge_global_settings(config)
        
        if config.parent:
            config = self._merge_parent(config)
        
        self._cache[agent_id] = config
        return config
    
    def merge_global_settings(self, config: AgentConfigData) -> AgentConfigData:
        """合并全局配置到 Agent 配置，使用深度合并
        
        Args:
            config: Agent 配置数据
            
        Returns:
            合并后的 Agent 配置数据
        """
        settings = self.load_settings()
        
        config.llm = self.deep_merge(settings.llm, config.llm)
        config.behavior = self.deep_merge(settings.behavior, config.behavior)
        
        return config
    
    def _merge_parent(self, config: AgentConfigData) -> AgentConfigData:
        """合并父配置"""
        parent_config = self.load(config.parent)
        
        return AgentConfigData(
            name=config.name,
            description=config.description or parent_config.description,
            role=config.role if config.role != "worker" else parent_config.role,
            llm=self.deep_merge(parent_config.llm, config.llm),
            behavior=self.deep_merge(parent_config.behavior, config.behavior),
            system_prompt=config.system_prompt or parent_config.system_prompt,
            tools=(parent_config.tools or []) + (config.tools or []),
            parent="",
            children=config.children or parent_config.children,
            workflow=config.workflow or parent_config.workflow,
            source_path=config.source_path
        )
    
    def list_agents(self) -> list[str]:
        """列出所有可用的Agent ID"""
        agents_dir = self.config_dir / "agents"
        if not agents_dir.exists():
            return []
        agents = []
        for path in agents_dir.glob("*.yaml"):
            agents.append(path.stem)
        return agents
    
    def clear_cache(self) -> None:
        """清除缓存"""
        self._cache.clear()
        self.settings = None
    
    def reload(self, agent_id: str) -> AgentConfigData:
        """重新加载Agent配置"""
        if agent_id in self._cache:
            del self._cache[agent_id]
        return self.load(agent_id)
