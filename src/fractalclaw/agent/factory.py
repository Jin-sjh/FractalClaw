"""Agent factory and runtime composition helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from fractalclaw.llm import LLMConfig, ModelSelector, SelectionResult, SmartModelSelector, TaskProfile
from fractalclaw.memory import MemoryConfig
from fractalclaw.plan import PlanConfig
from fractalclaw.tools import ToolConfig
from fractalclaw.tools.base import BaseTool
from fractalclaw.tools.builtin import get_builtin_tools

from .base import Agent, AgentConfig, AgentRole, BaseAgent, SubAgentRequirement
from .loader import (
    AgentConfigData,
    ConfigLoader,
    GlobalSettings,
    WorkflowConfig,
    WorkflowStep,
)


@dataclass
class RuntimeChildArtifacts:
    agent: Agent
    config: dict[str, Any]
    config_path: Path
    model_selection: Optional[SelectionResult] = None


class AgentFactory:
    """Unified runtime entry for static, root, and dynamic child agents."""

    BUILTIN_TOOL_ALIASES: dict[str, str] = {
        "read_file": "read",
        "write_file": "write",
        "edit_file": "edit",
        "execute_code": "bash",
        "python": "bash",
        "web_search": "tavily_search",
        "web_search_skill": "tavily_search",
        "find": "find_files",
    }

    ROLE_DEFAULT_TOOLS: dict[AgentRole, list[str]] = {
        AgentRole.ROOT: [
            "read",
            "write",
            "edit",
            "search",
            "find_files",
            "bash",
            "tavily_search",
            "llm_generate",
        ],
        AgentRole.COORDINATOR: [
            "read",
            "write",
            "edit",
            "search",
            "find_files",
            "bash",
            "tavily_search",
            "llm_generate",
        ],
        AgentRole.WORKER: ["read", "write", "edit", "bash", "search", "find_files"],
        AgentRole.SPECIALIST: ["read", "write", "edit", "bash", "search", "find_files"],
    }

    RUNTIME_TYPE_TOOLS: dict[str, list[str]] = {
        "coder": ["read", "write", "edit", "bash", "search", "find_files"],
        "code": ["read", "write", "edit", "bash", "search", "find_files"],
        "developer": ["read", "write", "edit", "bash", "search", "find_files"],
        "researcher": ["read", "search", "find_files", "tavily_search", "llm_generate"],
        "research": ["read", "search", "find_files", "tavily_search", "llm_generate"],
        "analyst": ["read", "search", "find_files", "tavily_search", "llm_generate"],
        "coordinator": ["read", "write", "edit", "search", "find_files", "bash", "llm_generate"],
    }

    def __init__(
        self,
        config_dir: Path = None,
        llm_provider: Any = None,
        workspace_manager: Any = None,
    ):
        self.loader = ConfigLoader(config_dir)
        self._agents: dict[str, Agent] = {}
        self._tool_handlers: dict[str, Callable] = {}
        self._llm_provider = llm_provider
        self._workspace_manager = workspace_manager
        self._model_selector = ModelSelector()
        self._smart_model_selector = SmartModelSelector(llm_provider=llm_provider)

        models_path = self.loader.config_dir / "models.yaml"
        if models_path.exists():
            registry = self._model_selector.registry
            if not registry.list_all():
                registry.load_from_yaml(models_path)

    def register_tool_handler(self, name: str, handler: Callable) -> None:
        """Register a custom tool handler."""
        self._tool_handlers[name] = handler

    def set_llm_provider(self, provider: Any) -> None:
        self._llm_provider = provider
        self._smart_model_selector = SmartModelSelector(
            registry=self._model_selector.registry,
            llm_provider=provider,
        )

    def set_workspace_manager(self, workspace_manager: Any) -> None:
        self._workspace_manager = workspace_manager

    def create(self, agent_id: str) -> Agent:
        """Create an agent from a persisted YAML config."""
        if agent_id in self._agents:
            return self._agents[agent_id]

        config_data = self.loader.load(agent_id)
        agent = self._build_agent(config_data, cache_key=agent_id)

        if config_data.children:
            for child_id in config_data.children:
                child = self.create(child_id)
                agent.add_child(child)

        return agent

    def create_from_config(
        self,
        config: AgentConfig,
        tool_defs: Optional[list[dict[str, Any]]] = None,
        cache_key: Optional[str] = None,
    ) -> Agent:
        """Create an agent from an in-memory AgentConfig."""
        normalized_config = AgentConfig(
            name=config.name,
            description=config.description,
            role=config.role,
            llm_config=config.llm_config or self._build_llm_config({}),
            memory_config=config.memory_config or self._build_memory_config(),
            tool_config=config.tool_config or self._build_tool_config(),
            plan_config=config.plan_config or self._build_plan_config(),
            max_iterations=config.max_iterations,
            enable_planning=config.enable_planning,
            enable_reflection=config.enable_reflection,
            system_prompt=config.system_prompt,
            workflow=config.workflow,
        )
        agent = BaseAgent(normalized_config)
        return self._configure_agent(agent, tool_defs or [], cache_key=cache_key)

    def _build_agent(
        self,
        data: AgentConfigData,
        cache_key: Optional[str] = None,
    ) -> Agent:
        """Build an agent instance from loader config data."""
        behavior = data.behavior

        config = AgentConfig(
            name=data.name,
            description=data.description,
            role=AgentRole(data.role),
            max_iterations=behavior.get("max_iterations", 10),
            enable_planning=behavior.get("enable_planning", True),
            enable_reflection=behavior.get("enable_reflection", True),
            system_prompt=data.system_prompt,
            llm_config=self._build_llm_config(data.llm),
            memory_config=self._build_memory_config(),
            tool_config=self._build_tool_config(),
            plan_config=self._build_plan_config(),
            workflow=data.workflow,
        )

        agent = BaseAgent(config)
        agent._max_replan_attempts = behavior.get("max_replan_attempts", 3)
        return self._configure_agent(agent, data.tools, cache_key=cache_key)

    def _configure_agent(
        self,
        agent: Agent,
        tool_defs: list[dict[str, Any]],
        cache_key: Optional[str] = None,
    ) -> Agent:
        agent.bind_factory(self)
        if self._llm_provider:
            agent.llm.set_provider(self._llm_provider)

        self._register_tools(agent, tool_defs)

        if cache_key:
            self._agents[cache_key] = agent
        return agent

    def _build_llm_config(self, llm_data: dict[str, Any]) -> LLMConfig:
        """Build LLM config from merged YAML data."""
        return LLMConfig(
            model=llm_data.get("model", "gpt-4"),
            temperature=llm_data.get("temperature", 0.7),
            max_tokens=llm_data.get("max_tokens", 4096),
            top_p=llm_data.get("top_p", 1.0),
            stream=llm_data.get("stream", True),
            timeout=llm_data.get("timeout", 60.0),
        )

    def _build_memory_config(self) -> MemoryConfig:
        """Build memory config from global settings."""
        settings = self.loader.load_settings()
        memory_settings = settings.memory
        return MemoryConfig(
            max_working_entries=memory_settings.get("max_working_entries", 10),
            enable_persistence=memory_settings.get("enable_persistence", True),
            enable_session_save=memory_settings.get("enable_session_save", True),
            enable_daily_log=memory_settings.get("enable_daily_log", True),
            enable_working_memory=memory_settings.get("enable_working_memory", True),
            heartbeat_interval_hours=memory_settings.get("heartbeat_interval_hours", 24),
        )

    def _build_tool_config(self) -> ToolConfig:
        """Build tool config from global settings."""
        settings = self.loader.load_settings()
        tool_settings = settings.tools
        return ToolConfig(
            max_concurrent_calls=tool_settings.get("max_concurrent_calls", 5),
            default_timeout=tool_settings.get("default_timeout", 30.0),
            enable_approval=tool_settings.get("enable_approval", False),
        )

    def _build_plan_config(self) -> PlanConfig:
        """Build plan config from global settings."""
        settings = self.loader.load_settings()
        planning_settings = settings.planning
        return PlanConfig(
            max_depth=planning_settings.get("max_depth", 5),
            max_subtasks=planning_settings.get("max_subtasks", 10),
            enable_parallel=planning_settings.get("enable_parallel", True),
            max_parallel_subtasks=planning_settings.get("max_parallel_subtasks", 3),
            max_total_delegations=planning_settings.get("max_total_delegations", 20),
            max_branch_delegations=planning_settings.get("max_branch_delegations", 6),
            fail_fast_on_parallel_error=planning_settings.get("fail_fast_on_parallel_error", False),
        )

    def _register_tools(
        self,
        agent: Agent,
        tool_defs: list[dict[str, Any]],
    ) -> None:
        declared_tools = tool_defs or self._default_tool_defs_for_role(agent.config.role)
        for tool_def in declared_tools:
            self._attach_tool_definition(agent, tool_def)

    def _default_tool_defs_for_role(self, role: AgentRole) -> list[dict[str, Any]]:
        return [{"name": tool_name} for tool_name in self.ROLE_DEFAULT_TOOLS.get(role, [])]

    def _attach_tool_definition(
        self,
        agent: Agent,
        tool_def: dict[str, Any],
    ) -> None:
        requested_name = tool_def.get("name")
        if not requested_name:
            return
        if agent.tools.get_tool(requested_name) is not None:
            return

        builtin_tool = self._make_builtin_tool(requested_name, tool_def.get("description"))
        if builtin_tool is not None:
            agent.register_tool_instance(builtin_tool)
            return

        handler = self._get_tool_handler(requested_name)
        agent.register_tool(
            name=requested_name,
            description=tool_def.get("description", f"Tool: {requested_name}"),
            parameters=tool_def.get("parameters", {}),
            handler=handler,
            required=tool_def.get("parameters", {}).get("required", []),
        )

    def _make_builtin_tool(
        self,
        requested_name: str,
        description: Optional[str] = None,
    ) -> Optional[BaseTool]:
        canonical_name = self.BUILTIN_TOOL_ALIASES.get(requested_name, requested_name)
        tavily_api_key = os.getenv("TAVILY_API_KEY")
        builtin_map = {
            tool.name: tool
            for tool in get_builtin_tools(
                llm_provider=self._llm_provider,
                tavily_api_key=tavily_api_key,
            )
        }
        tool = builtin_map.get(canonical_name)
        if tool is None:
            return None
        if requested_name == canonical_name and not description:
            return tool
        return self._alias_tool(tool, requested_name, description)

    def _alias_tool(
        self,
        tool: BaseTool,
        alias_name: str,
        description: Optional[str] = None,
    ) -> BaseTool:
        alias_description = description or tool.description
        base_tool = tool

        class AliasedTool(BaseTool):
            name = alias_name
            description = alias_description
            parameters_model = base_tool.parameters_model
            category = base_tool.category
            tags = base_tool.tags
            version = base_tool.version

            async def execute(self, params, ctx):
                return await base_tool.execute(params, ctx)

        return AliasedTool()

    def _get_tool_handler(self, name: str) -> Callable:
        """Get a custom tool handler or a placeholder."""
        if name in self._tool_handlers:
            return self._tool_handlers[name]

        async def placeholder(**kwargs) -> str:
            return f"Tool '{name}' executed with args: {kwargs}"

        return placeholder

    def list_available(self) -> list[str]:
        """List available persisted agent ids."""
        return self.loader.list_agents()

    def get_settings(self) -> GlobalSettings:
        """Get global settings."""
        return self.loader.load_settings()

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get a previously created agent."""
        return self._agents.get(agent_id)

    def clear_agents(self) -> None:
        """Clear cached agents."""
        self._agents.clear()

    def reload(self, agent_id: str) -> Agent:
        """Reload a static agent config and rebuild the agent."""
        if agent_id in self._agents:
            del self._agents[agent_id]
        self.loader.reload(agent_id)
        return self.create(agent_id)

    def create_from_dict(
        self,
        config_dict: dict[str, Any],
        cache_key: Optional[str] = None,
    ) -> Agent:
        """Create an agent from a raw config dict."""
        workflow_data = config_dict.get("workflow")
        workflow = None
        if workflow_data:
            steps = [
                WorkflowStep(
                    step=s.get("step", i + 1),
                    name=s.get("name", ""),
                    description=s.get("description", ""),
                    action=s.get("action", ""),
                )
                for i, s in enumerate(workflow_data.get("steps", []))
            ]
            workflow = WorkflowConfig(
                name=workflow_data.get("name", ""),
                steps=steps,
            )

        config_data = AgentConfigData(
            name=config_dict.get("name", "Agent"),
            description=config_dict.get("description", ""),
            role=config_dict.get("role", "worker"),
            llm=config_dict.get("llm", {}),
            behavior=config_dict.get("behavior", {}),
            system_prompt=config_dict.get("system_prompt", ""),
            tools=config_dict.get("tools", []),
            parent=config_dict.get("parent", ""),
            children=config_dict.get("children", []),
            workflow=workflow,
        )

        config_data = self.loader._merge_global_settings(config_data)
        return self._build_agent(config_data, cache_key=cache_key)

    async def create_runtime_child(
        self,
        parent_agent: Agent,
        requirement: SubAgentRequirement,
        depth: int,
    ) -> RuntimeChildArtifacts:
        """Create a runtime child agent and persist its generated config."""
        if self._workspace_manager is None:
            raise RuntimeError("Workspace manager is required for runtime child agents")
        if parent_agent.workspace_path is None:
            raise RuntimeError("Parent agent must be bound to a workspace before delegating")

        config_dict, selection = self._build_runtime_child_config(parent_agent, requirement, depth)
        child = self.create_from_dict(config_dict)
        child_workspace = await self._workspace_manager.create_agent_workspace(
            child,
            parent_workspace=parent_agent.workspace_path,
        )
        child.set_workspace(child_workspace, self._workspace_manager)

        config_path = child_workspace / "runtime_agent.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_dict, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        self._agents[child.id] = child
        return RuntimeChildArtifacts(
            agent=child,
            config=config_dict,
            config_path=config_path,
            model_selection=selection,
        )

    def _build_runtime_child_config(
        self,
        parent_agent: Agent,
        requirement: SubAgentRequirement,
        depth: int,
    ) -> tuple[dict[str, Any], Optional[SelectionResult]]:
        role = self._infer_role(requirement.agent_type)
        tool_names = self._resolve_runtime_tools(requirement, role)
        task_profile = self._build_task_profile(requirement, role)
        llm_data, selection = self._select_llm_for_runtime_child(parent_agent, role, task_profile)
        behavior = self._build_runtime_behavior(role, task_profile, depth)
        lineage = requirement.parameters.get("lineage", {})

        config = {
            "name": requirement.agent_name,
            "description": requirement.task_description,
            "role": role.value,
            "llm": llm_data,
            "behavior": behavior,
            "system_prompt": self._build_runtime_system_prompt(requirement, role),
            "tools": [{"name": tool_name} for tool_name in tool_names],
            "metadata": {
                "runtime_generated": True,
                "agent_type": requirement.agent_type,
                "expected_output": requirement.expected_output,
                "parameters": requirement.parameters,
                "parent_agent": parent_agent.name,
                "lineage": {
                    "parent_agent_id": lineage.get("parent_agent_id", parent_agent.id),
                    "branch_path": lineage.get("branch_path", "root"),
                    "wave_id": lineage.get("wave_id"),
                    "task_id": lineage.get("task_id"),
                },
                "model_selection": {
                    "model": llm_data.get("model"),
                    "reason": (
                        selection.reason
                        if selection
                        else llm_data.get("selection_reason", "inherited_parent_model")
                    ),
                },
            },
        }
        return config, selection

    def _infer_role(self, agent_type: str) -> AgentRole:
        agent_type_lower = agent_type.lower()
        if "coord" in agent_type_lower:
            return AgentRole.COORDINATOR
        if any(token in agent_type_lower for token in ["code", "coder", "research", "analyst", "special"]):
            return AgentRole.SPECIALIST
        return AgentRole.WORKER

    def _resolve_runtime_tools(
        self,
        requirement: SubAgentRequirement,
        role: AgentRole,
    ) -> list[str]:
        requested = [
            self.BUILTIN_TOOL_ALIASES.get(tool_name, tool_name)
            for tool_name in requirement.required_tools
        ]
        if requested:
            return list(dict.fromkeys(requested))

        agent_type_lower = requirement.agent_type.lower()
        for key, tools in self.RUNTIME_TYPE_TOOLS.items():
            if key in agent_type_lower:
                return tools.copy()
        return self.ROLE_DEFAULT_TOOLS.get(role, ["read", "write", "edit", "bash"]).copy()

    def _build_task_profile(
        self,
        requirement: SubAgentRequirement,
        role: AgentRole,
    ) -> TaskProfile:
        text = " ".join(
            [
                requirement.agent_type,
                requirement.task_description,
                requirement.expected_output,
                " ".join(requirement.required_tools),
            ]
        ).lower()
        analysis: dict[str, Any] = {
            "complexity": "medium",
            "task_type": "general",
            "importance": "medium",
            "requires_multimodal": False,
            "requires_code": False,
            "requires_reasoning": False,
            "requires_fast_response": False,
            "budget_sensitive": True,
            "estimated_tokens": 1200,
        }

        if any(token in text for token in ["code", "coder", "debug", "python", "script"]):
            analysis["task_type"] = "code"
            analysis["requires_code"] = True
        elif any(token in text for token in ["research", "analy", "search", "report"]):
            analysis["task_type"] = "research"
            analysis["requires_reasoning"] = True
        elif role == AgentRole.COORDINATOR:
            analysis["task_type"] = "coordinate"
            analysis["requires_reasoning"] = True

        if any(token in text for token in ["simple", "quick", "minor", "small"]):
            analysis["complexity"] = "simple"
            analysis["estimated_tokens"] = 800
        elif any(token in text for token in ["complex", "deep", "multi", "recursive"]):
            analysis["complexity"] = "complex"
            analysis["estimated_tokens"] = 3000

        if analysis["task_type"] in {"research", "coordinate"}:
            if analysis["complexity"] == "simple":
                analysis["complexity"] = "medium"
            analysis["budget_sensitive"] = False
        if requirement.expected_output:
            analysis["importance"] = "high"

        return TaskProfile.from_analysis(analysis)

    def _select_llm_for_runtime_child(
        self,
        parent_agent: Agent,
        role: AgentRole,
        task_profile: TaskProfile,
    ) -> tuple[dict[str, Any], Optional[SelectionResult]]:
        parent_llm = parent_agent.config.llm_config or self._build_llm_config({})
        selection: Optional[SelectionResult]

        try:
            selection = self._smart_model_selector.select(task_profile)
        except Exception:
            selection = None

        chosen_model = selection.model.name if selection else parent_llm.model
        if role == AgentRole.COORDINATOR:
            chosen_model = parent_llm.model

        temperature = 0.2 if task_profile.requires_code else 0.4 if task_profile.requires_reasoning else 0.6
        llm_data = {
            "model": chosen_model,
            "temperature": temperature,
            "max_tokens": min(parent_llm.max_tokens, 4096),
            "stream": False,
        }
        if selection:
            llm_data["selection_reason"] = selection.reason

        return llm_data, selection

    def _build_runtime_behavior(
        self,
        role: AgentRole,
        task_profile: TaskProfile,
        depth: int,
    ) -> dict[str, Any]:
        planning_enabled = depth < self._build_plan_config().max_depth and role != AgentRole.WORKER
        if role == AgentRole.SPECIALIST and task_profile.complexity.value == "complex":
            planning_enabled = True

        return {
            "max_iterations": 8 if task_profile.complexity.value == "simple" else 12,
            "enable_planning": planning_enabled,
            "enable_reflection": True,
            "max_replan_attempts": 2,
        }

    def _build_runtime_system_prompt(
        self,
        requirement: SubAgentRequirement,
        role: AgentRole,
    ) -> str:
        expected_output = requirement.expected_output or "Provide a concrete execution result."
        return "\n".join(
            [
                f"You are {requirement.agent_name}, a {role.value} agent in FractalClaw's recursive execution tree.",
                "You must execute work with tools when tools are available.",
                "If the task is still too complex and planning is enabled, decompose it into smaller delegated tasks.",
                f"Primary task: {requirement.task_description}",
                f"Expected output: {expected_output}",
            ]
        )
