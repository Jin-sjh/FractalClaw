"""Agent工厂"""

from pathlib import Path
from typing import Any, Callable, Optional

from .base import Agent, AgentConfig, AgentRole, BaseAgent
from .loader import ConfigLoader, AgentConfigData, GlobalSettings
from fractalclaw.llm import LLMConfig
from fractalclaw.memory import MemoryConfig
from fractalclaw.plan import PlanConfig
from fractalclaw.tools import ToolConfig


class AgentFactory:
    """Agent工厂类"""
    
    def __init__(self, config_dir: Path = None):
        self.loader = ConfigLoader(config_dir)
        self._agents: dict[str, Agent] = {}
        self._tool_handlers: dict[str, Callable] = {}
    
    def register_tool_handler(self, name: str, handler: Callable) -> None:
        """注册工具处理器"""
        self._tool_handlers[name] = handler
    
    def create(self, agent_id: str) -> Agent:
        """创建Agent"""
        if agent_id in self._agents:
            return self._agents[agent_id]
        
        config_data = self.loader.load(agent_id)
        agent = self._build_agent(config_data)
        
        if config_data.children:
            for child_id in config_data.children:
                child = self.create(child_id)
                agent.add_child(child)
        
        self._agents[agent_id] = agent
        return agent
    
    def _build_agent(self, data: AgentConfigData) -> Agent:
        """构建Agent实例"""
        behavior = data.behavior
        
        config = AgentConfig(
            name=data.name,
            description=data.description,
            role=AgentRole(data.role),
            max_iterations=behavior.get('max_iterations', 10),
            enable_planning=behavior.get('enable_planning', True),
            enable_reflection=behavior.get('enable_reflection', True),
            system_prompt=data.system_prompt,
            llm_config=self._build_llm_config(data.llm),
            memory_config=self._build_memory_config(),
            tool_config=self._build_tool_config(),
            plan_config=self._build_plan_config(),
            workflow=data.workflow
        )
        
        agent = BaseAgent(config)
        agent._max_replan_attempts = behavior.get('max_replan_attempts', 3)
        
        if data.tools:
            for tool in data.tools:
                tool_name = tool.get('name')
                handler = self._get_tool_handler(tool_name)
                agent.register_tool(
                    name=tool_name,
                    description=tool.get('description', ''),
                    parameters=tool.get('parameters', {}),
                    handler=handler,
                    required=tool.get('parameters', {}).get('required', [])
                )
        
        return agent
    
    def _build_llm_config(self, llm_data: dict) -> LLMConfig:
        """构建LLM配置"""
        return LLMConfig(
            model=llm_data.get('model', 'gpt-4'),
            temperature=llm_data.get('temperature', 0.7),
            max_tokens=llm_data.get('max_tokens', 4096),
            top_p=llm_data.get('top_p', 1.0),
            stream=llm_data.get('stream', True),
            timeout=llm_data.get('timeout', 60.0)
        )
    
    def _build_memory_config(self) -> MemoryConfig:
        """构建记忆配置"""
        settings = self.loader.load_settings()
        memory_settings = settings.memory
        return MemoryConfig(
            max_working_entries=memory_settings.get('max_working_entries', 10),
            enable_persistence=memory_settings.get('enable_persistence', True),
            enable_session_save=memory_settings.get('enable_session_save', True),
            enable_daily_log=memory_settings.get('enable_daily_log', True),
            enable_working_memory=memory_settings.get('enable_working_memory', True),
            heartbeat_interval_hours=memory_settings.get('heartbeat_interval_hours', 24)
        )
    
    def _build_tool_config(self) -> ToolConfig:
        """构建工具配置"""
        settings = self.loader.load_settings()
        tool_settings = settings.tools
        return ToolConfig(
            max_concurrent_calls=tool_settings.get('max_concurrent_calls', 5),
            default_timeout=tool_settings.get('default_timeout', 30.0),
            enable_approval=tool_settings.get('enable_approval', False)
        )
    
    def _build_plan_config(self) -> PlanConfig:
        """构建规划配置"""
        settings = self.loader.load_settings()
        planning_settings = settings.planning
        return PlanConfig(
            max_depth=planning_settings.get('max_depth', 5),
            max_subtasks=planning_settings.get('max_subtasks', 10),
            enable_parallel=planning_settings.get('enable_parallel', True)
        )
    
    def _get_tool_handler(self, name: str) -> Callable:
        """获取工具处理器"""
        if name in self._tool_handlers:
            return self._tool_handlers[name]
        
        async def placeholder(**kwargs) -> str:
            return f"Tool '{name}' executed with args: {kwargs}"
        return placeholder
    
    def list_available(self) -> list[str]:
        """列出所有可用的Agent ID"""
        return self.loader.list_agents()
    
    def get_settings(self) -> GlobalSettings:
        """获取全局配置"""
        return self.loader.load_settings()
    
    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """获取已创建的Agent"""
        return self._agents.get(agent_id)
    
    def clear_agents(self) -> None:
        """清除已创建的Agent"""
        self._agents.clear()
    
    def reload(self, agent_id: str) -> Agent:
        """重新创建Agent"""
        if agent_id in self._agents:
            del self._agents[agent_id]
        self.loader.reload(agent_id)
        return self.create(agent_id)
    
    def create_from_dict(self, config_dict: dict) -> Agent:
        """从字典配置创建Agent"""
        from .loader import WorkflowStep

        workflow_data = config_dict.get('workflow')
        workflow = None
        if workflow_data:
            steps = [
                WorkflowStep(
                    step=s.get('step', i + 1),
                    name=s.get('name', ''),
                    description=s.get('description', ''),
                    action=s.get('action', ''),
                )
                for i, s in enumerate(workflow_data.get('steps', []))
            ]
            workflow = WorkflowConfig(
                name=workflow_data.get('name', ''),
                steps=steps,
            )

        config_data = AgentConfigData(
            name=config_dict.get('name', 'Agent'),
            description=config_dict.get('description', ''),
            role=config_dict.get('role', 'worker'),
            llm=config_dict.get('llm', {}),
            behavior=config_dict.get('behavior', {}),
            system_prompt=config_dict.get('system_prompt', ''),
            tools=config_dict.get('tools', []),
            parent=config_dict.get('parent', ''),
            children=config_dict.get('children', []),
            workflow=workflow,
        )
        
        config_data = self.loader._merge_global_settings(config_data)
        
        return self._build_agent(config_data)
