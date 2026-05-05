"""Base Agent module - the core abstraction for all agents in FractalClaw."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional
import uuid

from fractalclaw.common.types import TaskComplexity
from fractalclaw.llm import LLMConfig, LLMEngine, LLMResponse
from fractalclaw.memory import MemoryConfig, MemoryManager, MemoryType
from fractalclaw.monitor import EventType, emit_agent_event, emit_event
from fractalclaw.plan import Plan, PlanConfig, PlanManager, Task, TaskPriority, TaskStatus, TaskType
from fractalclaw.tools import ToolCall, ToolConfig, ToolManager
from .execution import DelegationGovernance, PlanExecutionEngine
from .loader import WorkflowConfig, WorkflowStep
from .tree import AgentTree

if TYPE_CHECKING:
    from .factory import AgentFactory
    from ..scheduler.agent_workspace import AgentWorkspaceManager


class AgentState(Enum):
    IDLE = "idle"
    PLANNING = "planning"
    THINKING = "thinking"
    EXECUTING = "executing"
    DELEGATING = "delegating"
    ERROR = "error"
    STOPPED = "stopped"


class AgentRole(Enum):
    ROOT = "root"
    COORDINATOR = "coordinator"
    WORKER = "worker"
    SPECIALIST = "specialist"


@dataclass
class ErrorReport:
    error_type: str
    message: str
    recoverable: bool = True
    retry_recommended: bool = False
    replan_recommended: bool = False
    propagate: bool = False
    suggestion: str = ""


class ErrorClassifier:
    RETRYABLE_PATTERNS = ["timeout", "connection", "network", "rate_limit", "429", "503"]
    REPLAN_PATTERNS = ["invalid", "not found", "does not exist", "permission denied", "access denied"]
    PROPAGATE_PATTERNS = ["out of memory", "fatal", "critical", "unrecoverable"]

    @classmethod
    def classify(cls, error: str) -> ErrorReport:
        error_lower = error.lower()
        for pattern in cls.PROPAGATE_PATTERNS:
            if pattern in error_lower:
                return ErrorReport(
                    error_type="unrecoverable",
                    message=error,
                    recoverable=False,
                    propagate=True,
                    suggestion="Fatal error, propagate to parent",
                )
        for pattern in cls.RETRYABLE_PATTERNS:
            if pattern in error_lower:
                return ErrorReport(
                    error_type="transient",
                    message=error,
                    recoverable=True,
                    retry_recommended=True,
                    suggestion="Retry with backoff",
                )
        for pattern in cls.REPLAN_PATTERNS:
            if pattern in error_lower:
                return ErrorReport(
                    error_type="structural",
                    message=error,
                    recoverable=True,
                    replan_recommended=True,
                    suggestion="Replan with adjusted approach",
                )
        return ErrorReport(
            error_type="unknown",
            message=error,
            recoverable=True,
            replan_recommended=True,
            suggestion="Default to replan attempt",
        )


@dataclass
class AgentProfile:
    name: str = "default"
    tools: list[str] = field(default_factory=lambda: ["read", "write", "edit", "bash", "search"])
    model_preference: str = "balanced"
    can_delegate: bool = True
    max_iterations: int = 10
    enable_reflection: bool = True
    enable_planning: bool = True

    @classmethod
    def from_role(cls, role: AgentRole) -> "AgentProfile":
        mapping = {
            AgentRole.ROOT: cls.root(),
            AgentRole.COORDINATOR: cls.coordinator(),
            AgentRole.WORKER: cls.worker(),
            AgentRole.SPECIALIST: cls.specialist(),
        }
        return mapping.get(role, cls.worker())

    @classmethod
    def root(cls) -> "AgentProfile":
        return cls(
            name="root",
            tools=["read", "write", "edit", "search", "find_files", "bash", "tavily_search", "llm_generate"],
            model_preference="strong",
            can_delegate=True,
            max_iterations=10,
        )

    @classmethod
    def coordinator(cls) -> "AgentProfile":
        return cls(
            name="coordinator",
            tools=["read", "write", "edit", "search", "find_files", "bash", "tavily_search", "llm_generate"],
            model_preference="strong",
            can_delegate=True,
            max_iterations=10,
        )

    @classmethod
    def worker(cls) -> "AgentProfile":
        return cls(
            name="worker",
            tools=["read", "write", "edit", "bash", "search", "find_files"],
            model_preference="balanced",
            can_delegate=True,
            max_iterations=10,
        )

    @classmethod
    def specialist(cls) -> "AgentProfile":
        return cls(
            name="specialist",
            tools=["read", "write", "edit", "bash", "search", "find_files"],
            model_preference="balanced",
            can_delegate=True,
            max_iterations=10,
        )


@dataclass
class SubAgentRequirement:
    agent_name: str
    agent_type: str
    task_description: str
    required_tools: list[str] = field(default_factory=list)
    expected_output: str = ""
    parallel_safe: bool = False
    write_scope: list[str] = field(default_factory=list)
    read_scope: list[str] = field(default_factory=list)
    delegation_allowed: bool = True
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlanResult:
    plan: Optional[Plan] = None
    complexity: TaskComplexity = TaskComplexity.SIMPLE
    needs_subagents: bool = False
    subagent_requirements: list[SubAgentRequirement] = field(default_factory=list)
    self_execution_steps: list[str] = field(default_factory=list)
    reasoning: str = ""


@dataclass
class AgentConfig:
    name: str = "Agent"
    description: str = ""
    role: AgentRole = AgentRole.WORKER
    profile: Optional[AgentProfile] = None
    llm_config: Optional[LLMConfig] = None
    memory_config: Optional[MemoryConfig] = None
    tool_config: Optional[ToolConfig] = None
    plan_config: Optional[PlanConfig] = None
    max_iterations: int = 10
    enable_planning: bool = True
    enable_reflection: bool = True
    system_prompt: Optional[str] = None
    workflow: Optional[WorkflowConfig] = None

    def get_profile(self) -> AgentProfile:
        if self.profile is not None:
            return self.profile
        return AgentProfile.from_role(self.role)


@dataclass
class DelegationContext:
    depth: int = 0
    branch_path: str = "root"
    seen_fingerprints: frozenset[str] = frozenset()
    delegation_budget: int = 20
    branch_budget: int = 6
    max_depth: int = 5
    governance_rejections: int = 0

    def child_context(self, fingerprint: str, task_id: str) -> "DelegationContext":
        return DelegationContext(
            depth=self.depth + 1,
            branch_path=f"{self.branch_path}/{task_id}",
            seen_fingerprints=self.seen_fingerprints | {fingerprint},
            delegation_budget=self.delegation_budget - 1,
            branch_budget=self.branch_budget - 1,
            max_depth=self.max_depth,
            governance_rejections=self.governance_rejections,
        )

    def can_delegate(self) -> tuple[bool, str]:
        if self.depth >= self.max_depth:
            return False, "max_depth_reached"
        if self.delegation_budget <= 0:
            return False, "delegation_budget_exhausted"
        if self.branch_budget <= 0:
            return False, "branch_budget_exhausted"
        return True, "allowed"

    def is_duplicate(self, fingerprint: str) -> bool:
        return fingerprint in self.seen_fingerprints

    def with_rejection(self) -> "DelegationContext":
        return DelegationContext(
            depth=self.depth,
            branch_path=self.branch_path,
            seen_fingerprints=self.seen_fingerprints,
            delegation_budget=self.delegation_budget,
            branch_budget=self.branch_budget,
            max_depth=self.max_depth,
            governance_rejections=self.governance_rejections + 1,
        )

    def with_reserved(self, fingerprint: str, branch_path: str) -> "DelegationContext":
        return DelegationContext(
            depth=self.depth,
            branch_path=self.branch_path,
            seen_fingerprints=self.seen_fingerprints | {fingerprint},
            delegation_budget=self.delegation_budget - 1,
            branch_budget=self.branch_budget - 1,
            max_depth=self.max_depth,
            governance_rejections=self.governance_rejections,
        )


@dataclass
class AgentContext:
    task: str
    parent_id: Optional[str] = None
    depth: int = 0
    plan_id: Optional[str] = None
    task_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    delegation_ctx: Optional[DelegationContext] = None


@dataclass
class AgentResult:
    success: bool
    output: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    subtask_results: list["AgentResult"] = field(default_factory=list)
    iterations: int = 0
    plan: Optional[Plan] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class Agent(ABC):
    """Agent 抽象基类，定义 Agent 的核心接口和行为模式。"""

    def __init__(
        self,
        config: AgentConfig,
        llm_engine: Optional[LLMEngine] = None,
        memory_manager: Optional[MemoryManager] = None,
        tool_manager: Optional[ToolManager] = None,
        plan_manager: Optional[PlanManager] = None,
    ):
        self.config = config
        self._id = f"agent_{uuid.uuid4().hex[:8]}"
        self._state = AgentState.IDLE
        self._iteration = 0
        self._current_plan: Optional[Plan] = None
        self._last_plan_result: Optional[PlanResult] = None
        
        self._workspace_path: Optional[Path] = None
        self._workspace_manager: Optional["AgentWorkspaceManager"] = None
        self._factory: Optional["AgentFactory"] = None

        self._llm = llm_engine or LLMEngine(config.llm_config or LLMConfig())
        self._memory = memory_manager or MemoryManager(config.memory_config or MemoryConfig())
        self._tools = tool_manager or ToolManager(config.tool_config or ToolConfig())
        self._planner = plan_manager or PlanManager(config.plan_config or PlanConfig())
        self._tree = AgentTree(self)
        self._delegation_ctx = DelegationContext(
            max_depth=config.plan_config.max_depth if config.plan_config else 5,
            delegation_budget=config.plan_config.max_total_delegations if config.plan_config else 20,
            branch_budget=config.plan_config.max_branch_delegations if config.plan_config else 6,
        )
        self._governance = DelegationGovernance(self._planner.config)
        self._plan_executor = PlanExecutionEngine(self._planner.config, self._governance)

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def state(self) -> AgentState:
        return self._state

    def _transition_state(self, new_state: AgentState) -> None:
        old_state = self._state
        self._state = new_state
        if self._workspace_manager:
            self._workspace_manager.log_state_change(
                self._workspace_path, self, old_state.value, self._state.value
            )
        emit_agent_event(
            EventType.AGENT_STATE_CHANGED,
            self,
            message=f"State changed: {old_state.value} -> {new_state.value}",
            metadata={"old_state": old_state.value, "new_state": new_state.value},
        )

    @property
    def llm(self) -> LLMEngine:
        return self._llm

    @property
    def memory(self) -> MemoryManager:
        return self._memory

    @property
    def tools(self) -> ToolManager:
        return self._tools

    @property
    def planner(self) -> PlanManager:
        return self._planner

    @property
    def tree(self) -> AgentTree:
        return self._tree

    @property
    def workspace_path(self) -> Optional[Path]:
        """获取Agent的工作空间路径"""
        return self._workspace_path

    def set_workspace(self, path: Path, manager: "AgentWorkspaceManager") -> None:
        """设置Agent的工作空间"""
        self._workspace_path = path
        self._workspace_manager = manager
        self._memory.bind_agent(self._id, self.config.name, path)
        self._tools._workspace_path = str(path)

        workspace_hint = (
            f"\n\n## 工作空间\n"
            f"你的工作空间目录为: {path}\n"
            f"所有文件操作（读取、写入、搜索等）应使用相对于此工作空间的路径。\n"
            f"例如：写入文件时使用 'backend/main.py' 而非绝对路径，"
            f"系统会自动将其解析为 {path / 'backend/main.py'}。\n"
            f"执行命令时，默认工作目录也是此工作空间。\n\n"
            f"## ⚠️ 严禁行为\n"
            f"- 禁止启动任何长驻进程或开发服务器，例如：\n"
            f"  uvicorn、npm run dev、yarn start/dev、flask run、gunicorn、\n"
            f"  webpack --watch、vite、next dev、python -m http.server 等。\n"
            f"  这类命令会永久阻塞 bash 工具并导致超时。\n"
            f"- 你的职责是生成所有必要的文件。服务器的启动由用户在任务完成后手动执行。\n"
            f"- 如果需要验证代码语法，可以使用 python -c 'import ast; ast.parse(open(\"file.py\").read())' 等非阻塞命令。"
        )
        if self.config.system_prompt:
            self.config.system_prompt += workspace_hint
        else:
            self.config.system_prompt = workspace_hint

    def add_child(self, agent: "Agent") -> None:
        self._tree.add_child(agent)

    def remove_child(self, agent_id: str) -> bool:
        return self._tree.remove_child_by_id(agent_id)

    def get_children(self) -> list["Agent"]:
        return self._tree.children

    def get_parent(self) -> Optional["Agent"]:
        return self._tree.parent

    def set_system_prompt(self, prompt: str) -> None:
        self._llm.set_system_prompt(prompt)

    def bind_factory(self, factory: "AgentFactory") -> None:
        self._factory = factory

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Any,
        required: Optional[list[str]] = None,
    ) -> None:
        from fractalclaw.tools.base import BaseTool, ToolParameters, ToolResult
        from fractalclaw.tools.context import ToolContext
        from pydantic import Field, create_model
        
        fields = {}
        for param_name, param_info in parameters.get('properties', {}).items():
            param_type = str
            if param_info.get('type') == 'integer':
                param_type = int
            elif param_info.get('type') == 'number':
                param_type = float
            elif param_info.get('type') == 'boolean':
                param_type = bool
            elif param_info.get('type') == 'array':
                param_type = list
            
            is_required = param_name in (required or [])
            default = ... if is_required else None
            fields[param_name] = (
                param_type,
                Field(default=default, description=param_info.get('description', ''))
            )
        
        DynamicParameters = create_model(
            f'{name.capitalize()}Parameters',
            __base__=ToolParameters,
            **fields
        )
        
        def create_tool_class(tool_name: str, tool_description: str, tool_handler: Any):
            class DynamicTool(BaseTool):
                name = tool_name
                description = tool_description
                parameters_model = DynamicParameters
                
                async def execute(self, params: ToolParameters, ctx: ToolContext):
                    import inspect
                    kwargs = params.model_dump()
                    if inspect.iscoroutinefunction(tool_handler):
                        result = await tool_handler(**kwargs)
                    else:
                        result = tool_handler(**kwargs)
                    
                    if isinstance(result, ToolResult):
                        return result
                    return ToolResult(
                        title=f"{tool_name} result",
                        output=str(result) if result else "Success"
                    )
            
            return DynamicTool
        
        tool_class = create_tool_class(name, description, handler)
        tool_instance = tool_class()
        self._tools.register_tool(tool_instance)

    def register_tool_instance(self, tool: Any) -> None:
        self._tools.register_tool(tool)

    async def _create_subagent(
        self,
        requirement: SubAgentRequirement,
        depth: int,
    ) -> "Agent":
        """根据需求动态创建子Agent"""
        if self._factory and self._workspace_manager and self._workspace_path:
            artifacts = await self._factory.create_runtime_child(self, requirement, depth)
            child = artifacts.agent

            from ..scheduler.agent_workspace import WorkDocument

            self._workspace_manager.setup_agent_files(
                child.workspace_path,
                child,
                WorkDocument(
                    task_requirement=requirement.task_description,
                    acceptance_criteria=requirement.expected_output,
                    parent_task=self.config.description,
                ),
                existing_config_path=artifacts.config_path,
            )
        else:
            config = AgentConfig(
                name=requirement.agent_name,
                description=requirement.task_description,
                role=AgentRole.WORKER,
                max_iterations=10,
                enable_planning=False,
                llm_config=self.config.llm_config,
                memory_config=self.config.memory_config,
                tool_config=self.config.tool_config,
                plan_config=self.config.plan_config,
            )

            child = BaseAgent(config)
            if self._factory:
                child.bind_factory(self._factory)
            if self.llm and getattr(self.llm, "_provider", None):
                child.llm.set_provider(getattr(self.llm, "_provider"))

            if self._workspace_manager:
                child_workspace = await self._workspace_manager.create_agent_workspace(
                    child,
                    parent_workspace=self._workspace_path,
                )
                child.set_workspace(child_workspace, self._workspace_manager)
        
        if self._memory.sharing and child._workspace_path:
            await self._memory.sharing.parent_to_child(
                parent_agent_id=self._id,
                child_agent_id=child._id,
                child_workspace=child._workspace_path,
                task_context=requirement.task_description,
                knowledge=self._extract_relevant_knowledge(requirement),
                constraints=self._extract_constraints(requirement),
            )

        child._delegation_ctx = self._delegation_ctx

        if child.get_parent() is None:
            self.add_child(child)

        emit_agent_event(
            EventType.AGENT_SPAWNED,
            child,
            message=f"Created subagent: {child.name} for task: {requirement.task_description[:50]}",
            metadata={
                "requirement_agent_type": requirement.agent_type,
                "requirement_task": requirement.task_description,
                "parent_agent_id": self._id,
            },
        )

        if self._workspace_manager:
            await self._workspace_manager.log_agent_creation(
                parent_workspace=self._workspace_path,
                parent_agent=self,
                child_agent=child,
                requirement=requirement
            )

        return child
    
    def _get_tool_handler(self, tool_name: str) -> Optional[Callable]:
        tool = self._tools.get_tool(tool_name)
        if tool:
            async def execute_tool(**kwargs):
                result = await self._tools.execute(tool_name, kwargs)
                return result.result if result.result else result.error or ""

            return execute_tool

        return None

    def _plan_from_workflow(self, context: AgentContext) -> PlanResult:
        workflow = self.config.workflow
        self_execution_steps = [
            f"[Step {s.step}] {s.name}: {s.action}"
            for s in workflow.steps
        ]

        root_task = Task(
            id="root",
            name=context.task[:50],
            description=context.task,
            task_type=TaskType.COMPOSITE,
        )
        for i, step in enumerate(workflow.steps):
            subtask = self._planner.create_task(
                name=step.name,
                description=f"[Step {step.step}] {step.name}: {step.action}",
                task_type=TaskType.ATOMIC,
                priority=TaskPriority(i + 1),
            )
            subtask.metadata["workflow_step"] = True
            subtask.metadata["step_number"] = step.step
            subtask.metadata["action"] = step.action
            subtask.metadata["description"] = step.description
            root_task.subtasks.append(subtask)

        plan = Plan(
            id=self._planner._generate_plan_id(),
            name=f"Workflow: {workflow.name}",
            description=context.task,
            root_task=root_task,
        )

        return PlanResult(
            plan=plan,
            complexity=TaskComplexity.MEDIUM,
            needs_subagents=False,
            self_execution_steps=self_execution_steps,
            reasoning=f"Using predefined workflow '{workflow.name}' with {len(workflow.steps)} steps",
        )

    def _reset_recursive_runtime(self) -> None:
        self._delegation_ctx = DelegationContext(
            max_depth=self._planner.config.max_depth,
            delegation_budget=self._planner.config.max_total_delegations,
            branch_budget=self._planner.config.max_branch_delegations,
        )


    # ── Two-phase planning ────────────────────────────────────────────────────

    async def _plan_phase1(self, context: AgentContext) -> dict:
        """Phase 1: ask the LLM only whether to delegate and, if so, list agents.

        Returns a lightweight dict:
          {
            "needs_subagents": bool,
            "agents": [                      # only present when needs_subagents=true
              {"name": str, "role": str, "task": str},
              ...
            ],
            "reasoning": str
          }

        The LLM is NOT asked to produce subtasks, dependencies, or any structural
        fields — those are derived in code during phase 2.  This keeps the output
        small and reliable.
        """
        from fractalclaw.llm.response_parser import extract_json_from_llm_response

        prompt = f"""You are a planning assistant. Analyse the task below and decide
whether it should be split across multiple specialised agents.

Task:
{context.task}

Context:
- Your profile: {self.config.get_profile().name}
- Current delegation depth: {context.depth} / {self._planner.config.max_depth}
- Existing child agents: {[c.name for c in self._tree.children]}

Rules:
- Answer needs_subagents=true when the task clearly involves multiple independent
  work streams that benefit from parallel or specialised execution (e.g. a
  frontend component AND a backend API AND a database schema).
- Answer needs_subagents=false when the task is a single coherent unit of work.
- Do NOT produce subtasks, dependencies, or JSON schemas — only the agent list.

Respond with ONLY this JSON (no markdown fences):
{{
  "needs_subagents": true | false,
  "reasoning": "one sentence explaining your decision",
  "agents": [
    {{
      "name": "ShortCamelCaseName",
      "role": "one-word specialist role, e.g. frontend_developer",
      "task": "concise description of what this agent must do"
    }}
  ]
}}

If needs_subagents is false, set "agents" to [].
"""
        response = await self._llm.chat(prompt)
        data = extract_json_from_llm_response(response.content) or {}
        return {
            "needs_subagents": bool(data.get("needs_subagents", False)),
            "agents": data.get("agents") or [],
            "reasoning": data.get("reasoning", ""),
        }

    def _plan_phase2_build(
        self,
        context: AgentContext,
        phase1: dict,
    ) -> PlanResult:
        """Phase 2: convert the phase-1 agent list into a full PlanResult in code.

        No LLM call is made here.  The structural fields (subtasks, requirements,
        dependency wiring) are constructed deterministically from the agent list
        returned by phase 1.
        """
        agents = phase1.get("agents") or []
        reasoning = phase1.get("reasoning", "")

        if not agents:
            return PlanResult(
                complexity=TaskComplexity.SIMPLE,
                needs_subagents=False,
                self_execution_steps=[context.task],
                reasoning=reasoning,
            )

        requirements: list[SubAgentRequirement] = []
        root_task = Task(
            id="root",
            name=context.task[:50],
            description=context.task,
            task_type=TaskType.COMPOSITE,
        )

        for agent_spec in agents:
            name = str(agent_spec.get("name") or "").strip()
            role = str(agent_spec.get("role") or "worker").strip()
            task_desc = str(agent_spec.get("task") or context.task).strip()

            if not name:
                continue

            req = SubAgentRequirement(
                agent_name=name,
                agent_type=role,
                task_description=task_desc,
                required_tools=[],
                expected_output=f"Completed work by {name}",
                parallel_safe=True,
                write_scope=[],
                read_scope=[],
                delegation_allowed=True,
            )
            requirements.append(req)

            subtask = self._planner.create_task(
                name=name,
                description=task_desc,
                task_type=TaskType.ATOMIC,
                priority=TaskPriority.MEDIUM,
                dependencies=[],
            )
            subtask.assigned_agent = name
            subtask.metadata["parallel_safe"] = True
            subtask.metadata["write_scope"] = []
            subtask.metadata["read_scope"] = []
            subtask.metadata["delegation_allowed"] = True
            root_task.subtasks.append(subtask)

        if not requirements:
            return PlanResult(
                complexity=TaskComplexity.SIMPLE,
                needs_subagents=False,
                self_execution_steps=[context.task],
                reasoning=f"[PHASE2_EMPTY] {reasoning}",
            )

        plan = Plan(
            id=self._planner._generate_plan_id(),
            name=f"Plan for: {context.task[:30]}",
            description=context.task,
            root_task=root_task,
        )

        return PlanResult(
            plan=plan,
            complexity=TaskComplexity.COMPLEX,
            needs_subagents=True,
            subagent_requirements=requirements,
            self_execution_steps=[],
            reasoning=f"[TWO_PHASE] {reasoning}",
        )

    # ── End two-phase planning ────────────────────────────────────────────────

    def _finalize_plan_result(
        self,
        plan_result: PlanResult,
        context: AgentContext,
    ) -> PlanResult:
        finalized = self._governance.prepare_plan_result(self, plan_result, context)
        self._last_plan_result = finalized
        self._current_plan = finalized.plan if finalized.plan else None
        return finalized

    def _build_failure_context(self, result: AgentResult) -> str:
        import json

        failures = []
        for subtask_result in result.subtask_results:
            failures.append(
                {
                    "task_id": subtask_result.metadata.get("task_id"),
                    "task_description": subtask_result.metadata.get("task_description"),
                    "success": subtask_result.success,
                    "error": subtask_result.error,
                    "output_summary": subtask_result.output[:500],
                    "model": subtask_result.metadata.get("selected_model"),
                    "tools": subtask_result.metadata.get("used_tools", []),
                    "branch_path": subtask_result.metadata.get("branch_path"),
                    "depth": subtask_result.metadata.get("depth"),
                    "governance_reason": subtask_result.metadata.get("governance_reason"),
                    "parallel_wave": subtask_result.metadata.get("parallel_wave"),
                }
            )

        failed_tools = []
        for tc in result.tool_calls:
            if tc.error:
                failed_tools.append({"tool": tc.name, "error": tc.error})

        context = {"subtask_failures": failures}
        if failed_tools:
            context["failed_tool_calls"] = failed_tools
        return json.dumps(context, ensure_ascii=False, indent=2)

    def _collect_execution_summary(self, subtask_results: list[AgentResult]) -> dict[str, Any]:
        return {
            "local_execution_tasks": sum(
                1 for result in subtask_results
                if result.metadata.get("execution_mode") == "self"
            ),
            "delegated_tasks": sum(
                1 for result in subtask_results
                if result.metadata.get("execution_mode") == "delegated"
            ),
            "parallel_executed_tasks": sum(
                1 for result in subtask_results
                if result.metadata.get("executed_in_parallel")
            ),
            "child_failures": sum(1 for result in subtask_results if not result.success),
            "governance_rejections": self._delegation_ctx.governance_rejections,
            "replan_count": self._replan_count,
        }

    def _log_delegation_event(self, payload: dict[str, Any]) -> None:
        if not self._workspace_manager or not self._workspace_path:
            return
        self._workspace_manager.log_delegation_event(self._workspace_path, payload)

    async def _plan(self, context: AgentContext) -> PlanResult:
        """规划阶段：两阶段规划。

        Phase 1 (LLM, lightweight): decide whether to delegate and list agents.
        Phase 2 (code, deterministic): convert the agent list into a full PlanResult.
        """
        if self.config.workflow:
            return self._plan_from_workflow(context)
        if context.depth >= self._planner.config.max_depth:
            return PlanResult(
                complexity=TaskComplexity.SIMPLE,
                needs_subagents=False,
                self_execution_steps=[context.task],
                reasoning="Maximum delegation depth reached; executing locally.",
            )

        emit_agent_event(
            EventType.PLAN_CREATED,
            self,
            message="Starting planning phase",
            metadata={"task": context.task[:100], "depth": context.depth},
        )

        self._transition_state(AgentState.PLANNING)

        # ── Phase 1: lightweight LLM call ─────────────────────────────────────
        phase1 = await self._plan_phase1(context)

        # ── Phase 2: deterministic plan construction ──────────────────────────
        if phase1["needs_subagents"] and phase1["agents"]:
            plan_result = self._plan_phase2_build(context, phase1)
        else:
            # Single-agent path: ask LLM for self-execution steps only.
            plan_result = await self._plan_self_execution(context, phase1["reasoning"])
        # ── End two-phase planning ────────────────────────────────────────────

        original_needs_subagents = plan_result.needs_subagents
        plan_result = self._finalize_plan_result(plan_result, context)

        if plan_result.needs_subagents != original_needs_subagents:
            emit_agent_event(
                EventType.DELEGATION_DOWNGRADED,
                self,
                message=f"Plan downgraded: needs_subagents changed from {original_needs_subagents} to {plan_result.needs_subagents}",
                metadata={
                    "original_needs_subagents": original_needs_subagents,
                    "final_needs_subagents": plan_result.needs_subagents,
                    "reasoning": plan_result.reasoning,
                },
            )

        emit_agent_event(
            EventType.PLAN_RESULT,
            self,
            message=f"Plan completed: complexity={plan_result.complexity.value}, needs_subagents={plan_result.needs_subagents}",
            metadata={
                "complexity": plan_result.complexity.value,
                "needs_subagents": plan_result.needs_subagents,
                "reasoning": plan_result.reasoning,
                "subagent_count": len(plan_result.subagent_requirements) if plan_result.subagent_requirements else 0,
                "self_execution_steps": plan_result.self_execution_steps,
            },
        )

        if plan_result.plan:
            await self._memory.add(
                f"Plan created: {plan_result.plan.name}",
                MemoryType.WORKING,
                {
                    "plan_id": plan_result.plan.id,
                    "complexity": plan_result.complexity.value,
                    "needs_subagents": plan_result.needs_subagents,
                },
            )

        self._state = AgentState.THINKING

        if self._workspace_manager:
            self._workspace_manager.log_state_change(
                self._workspace_path, self, AgentState.PLANNING.value, self._state.value
            )

        return plan_result

    async def _plan_self_execution(
        self, context: AgentContext, phase1_reasoning: str
    ) -> PlanResult:
        """Single-agent path: ask LLM for self-execution steps only."""
        from fractalclaw.llm.response_parser import extract_json_from_llm_response

        prompt = f"""You will execute the following task yourself (no sub-agents).
List the concrete steps you will take.

Task: {context.task}
Available tools: {[t.name for t in self._tools.list_tools() if t.is_available()]}

Respond with ONLY this JSON (no markdown fences):
{{
  "complexity": "simple" | "moderate" | "complex",
  "steps": ["step 1", "step 2", ...]
}}
"""
        response = await self._llm.chat(prompt)
        data = extract_json_from_llm_response(response.content) or {}

        complexity_str = data.get("complexity", "moderate")
        try:
            complexity = TaskComplexity(complexity_str)
        except ValueError:
            complexity = TaskComplexity.MEDIUM

        steps = data.get("steps") or [context.task]

        return PlanResult(
            complexity=complexity,
            needs_subagents=False,
            self_execution_steps=steps,
            reasoning=phase1_reasoning,
        )

    async def _execute_plan(self, context: AgentContext) -> list[AgentResult]:
        """执行计划：按 wave 调度 ready leaf subtasks。"""
        if not self._current_plan:
            return []
        return await self._plan_executor.execute(self, self._current_plan, context)

    async def _execute_subtask(self, task: Task, context: AgentContext) -> AgentResult:
        self._transition_state(AgentState.DELEGATING)

        child = None
        requirement = None
        if task.assigned_agent:
            child = self._tree.get_child_by_name(task.assigned_agent) or self._tree.get_child(task.assigned_agent)

        if not child and task.assigned_agent:
            requirement = self._find_subagent_requirement(task.assigned_agent)
            if requirement:
                child = await self._resolve_child_via_governance(task, requirement, context)
            else:
                task.metadata["delegation_skipped"] = "missing_requirement"
                task.metadata["governance_reason"] = "missing_requirement"

        if child:
            return await self._execute_delegated_task(child, task, context)

        return await self._execute_self_fallback(task, context)

    async def _resolve_child_via_governance(
        self, task: Task, requirement: SubAgentRequirement, context: AgentContext
    ) -> Optional["Agent"]:
        decision = self._governance.evaluate_requirement(
            self, requirement, context, task, context.depth + 1,
        )
        task.metadata["fingerprint"] = decision.fingerprint
        task.metadata["branch_path"] = decision.branch_path

        if not decision.allowed:
            self._delegation_ctx = self._delegation_ctx.with_rejection()
            task.metadata["delegation_skipped"] = decision.reason_code
            task.metadata["governance_reason"] = decision.reason_code
            emit_agent_event(
                EventType.DELEGATION_REJECTED,
                self,
                message=f"Delegation rejected: {decision.reason}",
                metadata={
                    "task_id": task.id,
                    "assigned_agent": task.assigned_agent,
                    "reason_code": decision.reason_code,
                    "reason": decision.reason,
                    "branch_path": decision.branch_path,
                    "wave_id": task.metadata.get("parallel_wave"),
                },
            )
            self._log_delegation_event({
                "event": "delegation_rejected",
                "task_id": task.id,
                "assigned_agent": task.assigned_agent,
                "agent_type": requirement.agent_type,
                "fingerprint": decision.fingerprint,
                "branch_path": decision.branch_path,
                "reason_code": decision.reason_code,
                "reason": decision.reason,
                "wave_id": task.metadata.get("parallel_wave"),
            })
            return None

        self._governance.reserve_requirement(self, decision)
        requirement.parameters = {
            **requirement.parameters,
            "lineage": {
                "parent_agent_id": self._id,
                "branch_path": decision.branch_path,
                "wave_id": task.metadata.get("parallel_wave"),
                "task_id": task.id,
            },
        }

        self._transition_state(AgentState.PLANNING)

        try:
            child = await self._create_subagent(requirement, context.depth + 1)
        except Exception as exc:
            self._transition_state(AgentState.THINKING)
            error_text = f"Child creation failed: {exc}"
            task.metadata["failure_reason"] = error_text
            task.output_data["error"] = error_text
            self._log_delegation_event({
                "event": "delegation_creation_failed",
                "task_id": task.id,
                "assigned_agent": task.assigned_agent,
                "agent_type": requirement.agent_type,
                "fingerprint": decision.fingerprint,
                "branch_path": decision.branch_path,
                "reason_code": "child_creation_failed",
                "reason": error_text,
                "wave_id": task.metadata.get("parallel_wave"),
            })
            return None

        self._transition_state(AgentState.DELEGATING)
        emit_agent_event(
            EventType.DELEGATION_CREATED,
            self,
            message=f"Delegation created: {child.name} for task {task.id}",
            metadata={
                "task_id": task.id,
                "child_agent_id": child.id,
                "child_agent_name": child.name,
                "agent_type": requirement.agent_type,
                "branch_path": decision.branch_path,
                "wave_id": task.metadata.get("parallel_wave"),
            },
        )
        self._log_delegation_event({
            "event": "delegation_created",
            "task_id": task.id,
            "assigned_agent": child.name,
            "agent_type": requirement.agent_type,
            "fingerprint": decision.fingerprint,
            "branch_path": decision.branch_path,
            "selected_model": child.config.llm_config.model if child.config.llm_config else None,
            "wave_id": task.metadata.get("parallel_wave"),
        })
        return child

    async def _execute_delegated_task(
        self, child: "Agent", task: Task, context: AgentContext
    ) -> AgentResult:
        child._delegation_ctx = self._delegation_ctx
        sub_ctx = AgentContext(
            task=task.description,
            parent_id=self._id,
            depth=context.depth + 1,
            task_id=task.id,
            metadata={
                "input": task.input_data,
                "branch_path": task.metadata.get("branch_path") or context.metadata.get("branch_path", "root"),
                "parallel_wave": task.metadata.get("parallel_wave"),
            },
        )

        if self._workspace_manager:
            self._workspace_manager.log_subtask_delegation(
                self._workspace_path, self, child, task.description
            )

        try:
            result = await child.run(sub_ctx)
        except Exception as exc:
            result = AgentResult(
                success=False,
                output=f"Delegated child execution failed for task {task.id}",
                iterations=1,
                metadata={},
                error=str(exc),
            )

        result.metadata.setdefault("task_id", task.id)
        result.metadata.setdefault("task_description", task.description)
        result.metadata.setdefault("execution_mode", "delegated")
        result.metadata["child_agent_id"] = child.id
        result.metadata["child_agent_name"] = child.name
        result.metadata["branch_path"] = task.metadata.get("branch_path")
        result.metadata["depth"] = context.depth + 1
        result.metadata["selected_model"] = (
            child.config.llm_config.model if child.config.llm_config else None
        )
        result.metadata["used_tools"] = [tool.name for tool in child.tools.list_tools()]
        result.metadata["governance_reason"] = task.metadata.get("governance_reason")
        task.metadata["assigned_agent_id"] = child.id
        task.metadata["assigned_agent_name"] = child.name

        if not result.success:
            failure_reason = result.error or "Delegated child execution failed"
            task.metadata["failure_reason"] = failure_reason
            task.output_data["error"] = failure_reason
            task.output_data["child_result_summary"] = result.output[:500]
            result.metadata["failure_reason"] = failure_reason

        if self._memory.sharing and self._workspace_path and child._workspace_path:
            await self._memory.sharing.child_to_parent(
                child_agent_id=child._id,
                parent_agent_id=self._id,
                child_workspace=child._workspace_path,
                parent_workspace=self._workspace_path,
                result=result.output if result.success else None,
                errors=result.error,
            )

        self._transition_state(AgentState.THINKING)

        emit_agent_event(
            EventType.DELEGATION_RESULT,
            self,
            message=f"Delegation result from {child.name}: {'success' if result.success else 'failed'}",
            metadata={
                "task_id": task.id,
                "child_agent_id": child.id,
                "child_agent_name": child.name,
                "success": result.success,
                "error": result.error,
                "branch_path": task.metadata.get("branch_path"),
                "wave_id": task.metadata.get("parallel_wave"),
            },
        )

        self._log_delegation_event({
            "event": "delegation_result",
            "task_id": task.id,
            "assigned_agent": child.name,
            "branch_path": task.metadata.get("branch_path"),
            "wave_id": task.metadata.get("parallel_wave"),
            "selected_model": result.metadata.get("selected_model"),
            "success": result.success,
            "reason_code": task.metadata.get("governance_reason"),
            "error": result.error,
        })
        return result

    async def _execute_self_fallback(self, task: Task, context: AgentContext) -> AgentResult:
        self._transition_state(AgentState.THINKING)

        try:
            response = await self._llm.chat(task.description)
            return AgentResult(
                success=True,
                output=response.content,
                iterations=1,
                metadata={
                    "task_id": task.id,
                    "task_description": task.description,
                    "execution_mode": "self",
                    "branch_path": task.metadata.get("branch_path"),
                    "depth": context.depth,
                    "selected_model": self.config.llm_config.model if self.config.llm_config else None,
                    "used_tools": [tool.name for tool in self.tools.list_tools()],
                    "governance_reason": task.metadata.get("governance_reason"),
                },
            )
        except Exception as exc:
            error_text = str(exc)
            task.metadata["failure_reason"] = error_text
            task.output_data["error"] = error_text
            return AgentResult(
                success=False,
                output="",
                iterations=1,
                metadata={
                    "task_id": task.id,
                    "task_description": task.description,
                    "execution_mode": "self",
                    "branch_path": task.metadata.get("branch_path"),
                    "depth": context.depth,
                    "failure_reason": error_text,
                    "governance_reason": task.metadata.get("governance_reason"),
                },
                error=error_text,
            )

    def _find_subagent_requirement(self, agent_name: str) -> Optional[SubAgentRequirement]:
        """查找子Agent需求"""
        if self._last_plan_result:
            for req in self._last_plan_result.subagent_requirements:
                if req.agent_name == agent_name:
                    return req
        return None

    def _extract_relevant_knowledge(self, requirement: SubAgentRequirement) -> Optional[str]:
        """从记忆中提取与子Agent任务相关的知识"""
        knowledge_parts = []
        for entry in self._memory.get_working_memory():
            if entry.memory_type == MemoryType.WORKING:
                knowledge_parts.append(entry.content)
        return "\n".join(knowledge_parts) if knowledge_parts else None

    def _extract_constraints(self, requirement: SubAgentRequirement) -> Optional[str]:
        """提取对子Agent的约束和注意事项"""
        parts = []
        if requirement.expected_output:
            parts.append(f"期望输出: {requirement.expected_output}")
        if requirement.parameters:
            for k, v in requirement.parameters.items():
                parts.append(f"{k}: {v}")
        return "\n".join(parts) if parts else None

    async def _think(self, context: AgentContext) -> LLMResponse:
        """思考阶段：调用 LLM 进行推理决策。"""
        self._state = AgentState.THINKING
        await self._memory.add(f"Task: {context.task}", MemoryType.WORKING)
        tools = self._tools.get_tool_schemas()
        return await self._llm.chat(context.task, tools=tools if tools else None)

    async def _act(self, tool_calls: list[dict[str, Any]]) -> list[ToolCall]:
        import json

        self._transition_state(AgentState.EXECUTING)

        results: list[ToolCall] = []

        for tc in tool_calls:
            name = tc.get("function", {}).get("name", "")
            args = tc.get("function", {}).get("arguments", {})
            call_id = tc.get("id", "")

            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}

            emit_agent_event(
                EventType.TOOL_CALLED,
                self,
                tool_name=name,
                message=f"Tool called: {name}",
                metadata={"tool_args": args, "call_id": call_id},
            )

            result = await self._tools.execute(name, args)
            results.append(result)
            self._llm.add_tool_result(call_id, name, str(result.result))

            emit_agent_event(
                EventType.TOOL_RESULT,
                self,
                tool_name=name,
                message=f"Tool result: {name}",
                metadata={
                    "success": result.success if hasattr(result, "success") else True,
                    "result_preview": str(result.result)[:200] if result.result else "",
                },
            )

            if self._workspace_manager:
                self._workspace_manager.log_tool_call(
                    self._workspace_path, self, name, args, result.result
                )

        self._state = AgentState.THINKING

        if self._workspace_manager:
            self._workspace_manager.log_state_change(
                self._workspace_path, self, AgentState.EXECUTING.value, self._state.value
            )

        return results

    async def _reflect(self, result: AgentResult) -> Optional[str]:
        """反思阶段：总结执行过程。"""
        if not self.config.enable_reflection:
            return None

        prompt = f"""Task completed with {'success' if result.success else 'failure'}.
Output: {result.output}
Iterations: {result.iterations}
Tool calls: {len(result.tool_calls)}
Subtask results: {len(result.subtask_results)}

Reflect: 1) Was the goal achieved? 2) What could be improved? 3) Any follow-up actions?"""

        response = await self._llm.chat(prompt)
        return response.content

    async def _evaluate_execution(self, result: AgentResult, context: AgentContext) -> tuple[bool, str]:
        """评估执行结果是否达到目标。"""
        if not result.tool_calls and not result.subtask_results:
            execution_mode = result.metadata.get("execution_mode")
            if execution_mode in {"self", "workflow"} and result.success and result.output.strip():
                return True, "Accepted direct execution result without tool calls."
            return False, "No tool calls were made. The task requires actual execution via tools, not just text output."

        # ── Network/proxy error detection ─────────────────────────────────────
        # If ALL failures are network/proxy errors, treat the non-network work
        # as successful and skip the failed installs rather than triggering a
        # replan loop that will just retry the same broken network command.
        _network_error_indicators = [
            "ProxyError", "Cannot connect to proxy", "ConnectionError",
            "No matching distribution found", "Could not find a version",
            "pip install", "connection broken",
        ]
        _write_success_count = sum(
            1 for tc in result.tool_calls
            if tc.name in ("write", "write_file") and not tc.error
        )
        _network_fail_count = sum(
            1 for tc in result.tool_calls
            if (
                (tc.error and any(ind in str(tc.error) for ind in _network_error_indicators))
                or (tc.result and any(ind in str(tc.result) for ind in _network_error_indicators))
            )
        )
        # Count failures broadly: explicit tc.error OR result containing error indicators
        _total_fails = sum(
            1 for tc in result.tool_calls
            if tc.error
            or (tc.result and any(ind in str(tc.result) for ind in _network_error_indicators))
        )
        if _network_fail_count > 0 and _network_fail_count == _total_fails and _write_success_count > 0:
            return True, (
                f"Network/proxy errors prevented package installation "
                f"({_network_fail_count} install command(s) failed), but "
                f"{_write_success_count} file(s) were written successfully. "
                f"Treating as success — user should install dependencies manually."
            )
        # ── End network error detection ───────────────────────────────────────

        # ── Long-running server/process timeout detection ─────────────────────
        # Commands like "uvicorn", "npm run dev", "yarn start", "flask run" are
        # long-running processes that will always time out in a bash tool.
        # If the ONLY failures are these server-start commands, treat the task as
        # successful — the files were created; the user starts the server manually.
        _server_start_indicators = [
            "uvicorn", "npm run dev", "npm start", "yarn start", "yarn dev",
            "flask run", "gunicorn", "node server", "python -m http.server",
            "webpack --watch", "vite", "next dev",
        ]
        _server_timeout_fail_count = sum(
            1 for tc in result.tool_calls
            if tc.name == "bash"
            and "timed out" in (tc.error or "").lower()
            and any(ind in (tc.result.metadata.get("command", "") if tc.result and hasattr(tc.result, "metadata") else "")
                    or ind in str(tc.result or "")
                    for ind in _server_start_indicators)
        )
        # Also catch via tool args stored in the log
        _server_timeout_fail_count_v2 = sum(
            1 for tc in result.tool_calls
            if tc.name == "bash"
            and "timed out" in str(tc.error or "").lower()
            and any(ind in str(getattr(tc, "args", {}) or {}) for ind in _server_start_indicators)
        )
        _server_timeout_count = max(_server_timeout_fail_count, _server_timeout_fail_count_v2)
        _non_server_fails = sum(
            1 for tc in result.tool_calls
            if tc.error and "timed out" not in str(tc.error).lower()
        )
        if _server_timeout_count > 0 and _non_server_fails == 0 and _write_success_count > 0:
            return True, (
                f"Server start command(s) timed out ({_server_timeout_count} command(s)), "
                f"but this is expected — long-running servers cannot be started inside a bash tool. "
                f"{_write_success_count} file(s) were written successfully. "
                f"Treating as success — user should start the server manually."
            )
        # ── End server timeout detection ──────────────────────────────────────

        failed_tool_summary = []
        for tc in result.tool_calls:
            if tc.result and hasattr(tc.result, "metadata") and tc.result.metadata.get("error"):
                error_msg = tc.result.metadata.get("error_message", "Unknown error")
                failed_tool_summary.append(f"- {tc.name}: {error_msg}")
            elif tc.error:
                failed_tool_summary.append(f"- {tc.name}: {tc.error}")

        tool_summary_section = ""
        if failed_tool_summary:
            tool_summary_section = f"\n\nFailed Tool Calls:\n" + "\n".join(failed_tool_summary)

        prompt = f"""Evaluate whether the task execution achieved its goal.

Original Task: {context.task}
Execution Result:
- Success: {result.success}
- Output: {result.output[:500]}
- Iterations: {result.iterations}
- Tool calls made: {len(result.tool_calls)}
- Failed tool calls: {len(failed_tool_summary)}
- Subtask results: {len(result.subtask_results)}
{tool_summary_section}

IMPORTANT: The task is only achieved if actual operations were performed (e.g., files created, commands executed). Simply providing instructions or guidance without executing tools does NOT count as achieving the goal. If any critical tool call failed (e.g., install timeout, command error), the goal is NOT achieved.

Respond with a JSON:
{{
    "goal_achieved": true | false,
    "evaluation": "detailed evaluation of the execution",
    "issues": ["issue1", "issue2"]
}}"""

        response = await self._llm.chat(prompt)
        from fractalclaw.llm.response_parser import extract_json_from_llm_response

        data = extract_json_from_llm_response(response.content)
        if data:
            return data.get("goal_achieved", False), data.get("evaluation", "")

        if failed_tool_summary:
            return False, f"Could not parse evaluation, but {len(failed_tool_summary)} tool call(s) failed: " + "; ".join(failed_tool_summary[:3])

        return result.success, "Could not parse evaluation, using success flag"

    async def _replan(
        self,
        context: AgentContext,
        previous_result: AgentResult,
        reflection: str,
        evaluation: str,
    ) -> PlanResult:
        """结合反思结果重新规划。"""
        emit_agent_event(
            EventType.REPLAN_TRIGGERED,
            self,
            message=f"Replanning triggered (attempt {self._replan_count + 1})",
            metadata={
                "replan_count": self._replan_count + 1,
                "previous_success": previous_result.success,
                "evaluation": evaluation[:200],
            },
        )
        self._state = AgentState.PLANNING

        prompt = f"""The previous execution plan did not achieve the goal. Create an improved plan.

Original Task: {context.task}

Previous Execution:
- Success: {previous_result.success}
- Output: {previous_result.output}
- Iterations: {previous_result.iterations}
- Tool calls: {len(previous_result.tool_calls)}

Reflection: {reflection}

Evaluation: {evaluation}

Structured Failure Context:
{self._build_failure_context(previous_result)}

Context:
- Agent Role: {self.config.role.value}
- Available Tools: {[t.name for t in self._tools.list_tools() if t.is_available()]}
- Child Agents: {[c.name for c in self._tree.children]}

IMPORTANT RULES FOR REPLANNING:
1. If a tool failed due to missing dependencies or API keys, DO NOT use that tool again. Choose a different tool instead.
2. If tavily_search failed, try llm_generate (for known content), bash+curl, or other available tools.
3. If a tool returned an error, the new plan must use a DIFFERENT approach or tool.
4. Do NOT repeat the same failed approach.
5. NETWORK/PROXY ERRORS: If any tool failed with a network or proxy error (ProxyError, ConnectionError,
   "Cannot connect to proxy", "No such file or directory" in proxy context, pip install timeout/failure),
   this is an ENVIRONMENT LIMITATION — do NOT retry the same network command.
   Instead, SKIP the installation/network step entirely and proceed with writing files only.
   Assume the user will install dependencies manually.
6. ENVIRONMENT COMMANDS: If bash commands like "pwd", "ls", "ls -la" failed with "not recognized",
   this is a Windows environment. Do NOT use Unix commands. Use the "write" tool to create files directly
   instead of using bash for file operations.
7. LONG-RUNNING SERVER COMMANDS: NEVER start a development server or long-running process as part of
   a task (e.g., uvicorn, npm run dev, yarn start, flask run, gunicorn, webpack --watch, vite, next dev).
   These commands block indefinitely and will always time out. The task is complete once the files are
   written. Leave server startup to the user. If a previous attempt timed out on a server command,
   do NOT retry it — mark the task as done.

Based on the above, create a NEW and IMPROVED execution plan.
Respond with ONLY this JSON (no markdown fences):
{{
  "needs_subagents": true | false,
  "reasoning": "what went wrong and how the new plan addresses it",
  "agents": [
    {{
      "name": "ShortCamelCaseName",
      "role": "specialist role",
      "task": "what this agent must do"
    }}
  ]
}}
If needs_subagents is false, set "agents" to [].
"""

        from fractalclaw.llm.response_parser import extract_json_from_llm_response
        response = await self._llm.chat(prompt)
        data = extract_json_from_llm_response(response.content) or {}
        phase1 = {
            "needs_subagents": bool(data.get("needs_subagents", False)),
            "agents": data.get("agents") or [],
            "reasoning": data.get("reasoning", ""),
        }

        if phase1["needs_subagents"] and phase1["agents"]:
            plan_result = self._plan_phase2_build(context, phase1)
        else:
            plan_result = await self._plan_self_execution(context, phase1["reasoning"])

        plan_result = self._finalize_plan_result(plan_result, context)

        if plan_result.plan:
            await self._memory.add(
                f"Replan created: {plan_result.plan.name}",
                MemoryType.WORKING,
                {
                    "plan_id": plan_result.plan.id,
                    "complexity": plan_result.complexity.value,
                    "needs_subagents": plan_result.needs_subagents,
                    "previous_attempt_failed": True,
                },
            )

        self._state = AgentState.THINKING
        return plan_result

    async def _should_continue(self) -> bool:
        """判断是否应该继续执行迭代循环。"""
        if self._iteration >= self.config.max_iterations:
            return False
        last = self._llm.get_context()[-1] if self._llm.get_context() else None
        return bool(last and last.tool_calls)

    @abstractmethod
    async def run(self, context: AgentContext) -> AgentResult:
        pass

    async def run_with_memory(self, context: AgentContext) -> AgentResult:
        """带记忆检索的执行方法。"""
        memories = await self._memory.search(context.task, limit=5)
        if memories:
            context.metadata["relevant_memories"] = "\n".join(f"- {m.content}" for m in memories)

        result = await self.run(context)

        await self._memory.add(
            f"Task: {context.task}\nResult: {result.output}",
            MemoryType.SHORT_TERM,
            {"success": result.success},
            importance=0.8 if result.success else 0.3,
        )
        return result

    async def stop(self) -> None:
        self._state = AgentState.STOPPED

    async def reset(self) -> None:
        self._state = AgentState.IDLE
        self._iteration = 0
        self._current_plan = None
        self._llm.clear_context()
        await self._memory.clear(MemoryType.WORKING)

    def get_info(self) -> dict[str, Any]:
        return {
            "id": self._id,
            "name": self.config.name,
            "role": self.config.role.value,
            "state": self._state.value,
            "iteration": self._iteration,
            "children_count": len(self._tree.children),
            "tools_count": len(self._tools.list_tools()),
            "has_plan": self._current_plan is not None,
        }


# 框架内部文件过滤常量
_FRAMEWORK_EXCLUDE_DIRS = frozenset({
    "memory", "output", "agents", "__pycache__",
})

_FRAMEWORK_EXCLUDE_FILES = frozenset({
    "agent_config.yaml",
    "runtime_agent.yaml",
    "execution.log",
    "delegation_log.jsonl",
    "execution_waves.jsonl",
})

_FRAMEWORK_EXCLUDE_EXTENSIONS = frozenset({
    ".pyc", ".pyo",
})


class BaseAgent(Agent):
    """Agent 的默认实现，提供完整的 Plan-ReAct 执行循环。"""

    def __init__(self, config: AgentConfig, **kwargs):
        super().__init__(config, **kwargs)
        self._max_replan_attempts = 3
        self._replan_count = 0

    async def run(self, context: AgentContext) -> AgentResult:
        """执行 Agent 的主循环：规划 -> 执行 -> 评估 -> 反思 -> 重规划（如需要）。"""
        self._iteration = 0
        self._replan_count = 0
        if context.parent_id is None:
            self._reset_recursive_runtime()
        context.metadata.setdefault("branch_path", context.metadata.get("branch_path") or "root")
        tool_history: list[ToolCall] = []
        subtask_results: list[AgentResult] = []

        try:
            await self._memory.initialize()
            await self._memory.start_session()

            if self.config.system_prompt:
                self.set_system_prompt(self.config.system_prompt)

            if self.config.workflow:
                result = await self._run_workflow(context, tool_history)
                await self._memory.end_session(result.output[:200] if result.output else None)
                return result

            plan_result = await self._plan(context)
            context.metadata["initial_plan"] = plan_result

            while True:
                if plan_result.needs_subagents and plan_result.plan:
                    subtask_results = await self._execute_plan(context)
                    # 聚合子 Agent 的文件产出到父 Agent workspace
                    if subtask_results and self._workspace_path:
                        _aggregation_report = await self._aggregate_child_outputs(
                            subtask_results, context
                        )
                        self._write_aggregation_report(_aggregation_report)
                    else:
                        _aggregation_report = {}
                    execution_summary = self._collect_execution_summary(subtask_results)
                    first_failure = next((r for r in subtask_results if not r.success), None)
                    result = AgentResult(
                        success=all(r.success for r in subtask_results),
                        output="\n".join(f"[{r.metadata.get('task_id')}] {r.output}" for r in subtask_results),
                        tool_calls=tool_history,
                        subtask_results=subtask_results,
                        iterations=self._iteration,
                        plan=plan_result.plan,
                        metadata={
                            "execution_summary": execution_summary,
                            "aggregation_summary": _aggregation_report.get("summary", {}),
                        },
                        error=first_failure.error if first_failure else None,
                    )
                    if first_failure:
                        result.metadata["failure_context"] = self._build_failure_context(result)
                        # Check if the failure is due to network/environment issues but
                        # some subtasks succeeded. If so, treat as partial success rather
                        # than triggering a full replan that will duplicate work.
                        _success_count = sum(1 for r in subtask_results if r.success)
                        _has_network_errors = any(
                            "ProxyError" in (r.error or "")
                            or "Cannot connect to proxy" in (r.error or "")
                            or "No matching distribution" in (r.error or "")
                            for r in subtask_results if not r.success
                        )
                        if _success_count > 0 and _has_network_errors:
                            goal_achieved = True
                            evaluation = (
                                f"Partial success: {_success_count}/{len(subtask_results)} "
                                f"subtask(s) completed. Failures were due to network/environment "
                                f"issues (proxy errors, missing packages). Treating as success."
                            )
                        else:
                            goal_achieved = False
                            evaluation = "Child task failure returned to parent; replanning required."
                    else:
                        goal_achieved, evaluation = await self._evaluate_execution(result, context)
                else:
                    result = await self._execute_self(plan_result, context, tool_history)
                    goal_achieved, evaluation = await self._evaluate_execution(result, context)
                result.metadata["evaluation"] = evaluation
                result.metadata["goal_achieved"] = goal_achieved

                if goal_achieved:
                    if self.config.enable_reflection:
                        result.metadata["reflection"] = await self._reflect(result)
                    self._state = AgentState.IDLE
                    await self._memory.end_session(result.output[:200] if result.output else None)
                    return result

                if self._replan_count >= self._max_replan_attempts:
                    result.success = False
                    result.metadata["reflection"] = await self._reflect(result)
                    result.metadata["replan_exhausted"] = True
                    result.error = (
                        f"Replan exhausted after {self._max_replan_attempts} attempts. "
                        f"Last evaluation: {evaluation}. "
                        f"Available tools: {[t.name for t in self.tools.list_tools()]}"
                    )
                    self._state = AgentState.IDLE
                    await self._memory.end_session(result.error)
                    return result

                self._replan_count += 1
                reflection = await self._reflect(result) if self.config.enable_reflection else ""
                plan_result = await self._replan(context, result, reflection, evaluation)
                context.metadata[f"replan_{self._replan_count}"] = plan_result

                tool_history = []
                subtask_results = []
                self._iteration = 0

        except Exception as e:
            self._state = AgentState.ERROR
            await self._memory.end_session(f"Error: {str(e)[:200]}")
            return AgentResult(
                success=False,
                output="",
                tool_calls=tool_history,
                subtask_results=subtask_results,
                iterations=self._iteration,
                error=str(e),
            )

    async def _aggregate_child_outputs(
        self,
        subtask_results: list["AgentResult"],
        context: "AgentContext",
    ) -> dict:
        """聚合所有子 Agent workspace 中的文件产出到父 Agent workspace。

        遍历 self._tree.children，将每个子 Agent workspace 中的项目文件
        （排除框架内部文件）复制到父 Agent workspace 的对应相对路径。

        Returns:
            dict: 聚合报告，包含 aggregated_files、conflicts、skipped_files、summary
        """
        import json
        import shutil
        from datetime import datetime

        report = {
            "timestamp": datetime.now().isoformat(),
            "parent_workspace": str(self._workspace_path) if self._workspace_path else "",
            "aggregated_files": [],
            "conflicts": [],
            "skipped_files": [],
            "summary": {"total_aggregated": 0, "total_conflicts": 0, "total_skipped": 0},
        }

        if not self._workspace_path or not self._workspace_manager:
            return report

        children = self._tree.children
        if not children:
            return report

        parent_ws = self._workspace_path

        for child in children:
            child_ws = child.workspace_path
            if not child_ws or not child_ws.exists():
                continue

            # 遍历子 Agent workspace 中的所有文件
            for src_path in child_ws.rglob("*"):
                if not src_path.is_file():
                    continue

                # 计算相对于子 Agent workspace 的相对路径
                try:
                    rel_path = src_path.relative_to(child_ws)
                except ValueError:
                    continue

                # 过滤框架内部文件
                parts = rel_path.parts
                if any(part in _FRAMEWORK_EXCLUDE_DIRS for part in parts[:-1]):
                    report["skipped_files"].append({
                        "path": str(rel_path),
                        "source_agent": child.name,
                        "reason": "framework_internal_dir",
                    })
                    continue

                if rel_path.name in _FRAMEWORK_EXCLUDE_FILES:
                    report["skipped_files"].append({
                        "path": str(rel_path),
                        "source_agent": child.name,
                        "reason": "framework_internal_file",
                    })
                    continue

                if src_path.suffix in _FRAMEWORK_EXCLUDE_EXTENSIONS:
                    report["skipped_files"].append({
                        "path": str(rel_path),
                        "source_agent": child.name,
                        "reason": "framework_internal_extension",
                    })
                    continue

                dst_path = parent_ws / rel_path

                # 处理文件冲突
                if dst_path.exists():
                    conflict_resolved = self._resolve_file_conflict(
                        src_path, dst_path, rel_path, child.name, report
                    )
                    if conflict_resolved:
                        report["aggregated_files"].append({
                            "source": str(src_path.relative_to(child_ws.parent.parent) if child_ws.parent.parent.exists() else src_path),
                            "destination": str(rel_path),
                            "source_agent": child.name,
                            "action": "merged_or_replaced",
                        })
                else:
                    # 无冲突，直接复制
                    dst_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_path, dst_path)
                    report["aggregated_files"].append({
                        "source": str(rel_path),
                        "destination": str(rel_path),
                        "source_agent": child.name,
                        "action": "copied",
                    })

        report["summary"]["total_aggregated"] = len(report["aggregated_files"])
        report["summary"]["total_conflicts"] = len(report["conflicts"])
        report["summary"]["total_skipped"] = len(report["skipped_files"])

        return report

    def _resolve_file_conflict(
        self,
        src_path: "Path",
        dst_path: "Path",
        rel_path: "Path",
        source_agent_name: str,
        report: dict,
    ) -> bool:
        """处理文件冲突，返回 True 表示已处理（文件已更新），False 表示跳过。"""
        import json
        import shutil

        filename = rel_path.name

        # requirements.txt：合并依赖行，去重排序
        if filename == "requirements.txt":
            try:
                existing_lines = set(dst_path.read_text(encoding="utf-8").splitlines())
                new_lines = set(src_path.read_text(encoding="utf-8").splitlines())
                merged = sorted(existing_lines | new_lines - {""})
                dst_path.write_text("\n".join(merged) + "\n", encoding="utf-8")
                report["conflicts"].append({
                    "path": str(rel_path),
                    "sources": [dst_path.name, source_agent_name],
                    "resolution": "merged_requirements",
                })
                return True
            except Exception:
                pass

        # package.json：合并 dependencies 和 devDependencies
        if filename == "package.json":
            try:
                existing = json.loads(dst_path.read_text(encoding="utf-8"))
                incoming = json.loads(src_path.read_text(encoding="utf-8"))
                for key in ("dependencies", "devDependencies"):
                    if key in incoming:
                        existing.setdefault(key, {}).update(incoming[key])
                dst_path.write_text(
                    json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                report["conflicts"].append({
                    "path": str(rel_path),
                    "sources": [dst_path.name, source_agent_name],
                    "resolution": "merged_package_json",
                })
                return True
            except Exception:
                pass

        # 通用冲突：保留修改时间最新的版本
        import shutil as _shutil
        src_mtime = src_path.stat().st_mtime
        dst_mtime = dst_path.stat().st_mtime
        if src_mtime > dst_mtime:
            _shutil.copy2(src_path, dst_path)
            kept = source_agent_name
            resolution = "kept_newest_incoming"
        else:
            kept = "existing"
            resolution = "kept_newest_existing"

        report["conflicts"].append({
            "path": str(rel_path),
            "sources": ["existing", source_agent_name],
            "resolution": resolution,
            "kept_source": kept,
        })
        return True

    def _write_aggregation_report(self, report: dict) -> None:
        """将聚合报告写入 output/aggregation_report.json。"""
        import json

        if not self._workspace_path:
            return

        output_dir = self._workspace_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        report_path = output_dir / "aggregation_report.json"
        try:
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            # 报告写入失败不应影响主流程
            pass

    async def _run_workflow(
        self,
        context: AgentContext,
        tool_history: list[ToolCall],
    ) -> AgentResult:
        """按照预定义的workflow步骤顺序执行，不进行LLM规划和评估重规划。"""
        workflow = self.config.workflow
        self._state = AgentState.PLANNING

        if self._workspace_manager:
            self._workspace_manager.log_state_change(
                self._workspace_path, self, AgentState.IDLE.value, self._state.value
            )

        plan_result = self._plan_from_workflow(context)
        self._last_plan_result = plan_result

        await self._memory.add(
            f"Workflow plan: {workflow.name}",
            MemoryType.WORKING,
            {
                "workflow_name": workflow.name,
                "steps_count": len(workflow.steps),
            },
        )

        self._state = AgentState.THINKING

        if self._workspace_manager:
            self._workspace_manager.log_state_change(
                self._workspace_path, self, AgentState.PLANNING.value, self._state.value
            )

        context.metadata["initial_plan"] = plan_result

        step_outputs: list[str] = []
        accumulated_context = context.task

        system_prompt_section = ""
        if self.config.system_prompt:
            system_prompt_section = f"\n## 你的角色和规则\n{self.config.system_prompt}\n"

        for workflow_step in workflow.steps:
            self._state = AgentState.THINKING

            is_last_step = workflow_step.step == len(workflow.steps)
            previous_context_section = ""
            if accumulated_context != context.task:
                previous_context_section = f"\n## 前序步骤的输出\n{accumulated_context}\n"

            step_prompt = f"""{system_prompt_section}你正在执行工作流 '{workflow.name}' 的第 {workflow_step.step}/{len(workflow.steps)} 步。

## 当前步骤
步骤名称：{workflow_step.name}
步骤描述：{workflow_step.description}
执行动作：{workflow_step.action}

## 原始任务
{context.task}
{previous_context_section}
{"## 重要：这是最后一步，请直接输出最终结果，不要包含步骤编号或前缀。" if is_last_step else "请执行当前步骤，只输出本步骤的结果。"}"""

            await self._memory.add(
                f"Workflow step {workflow_step.step}: {workflow_step.name} - {workflow_step.action}",
                MemoryType.WORKING,
            )

            if self._llm.should_compress_context():
                self._llm.clear_context()

            response = await self._llm.chat(step_prompt)
            step_output = response.content
            step_outputs.append(f"[Step {workflow_step.step}: {workflow_step.name}] {step_output}")

            accumulated_context = f"{accumulated_context}\n{step_output}"

            self._iteration += 1

            if response.tool_calls:
                tool_history.extend(await self._act(response.tool_calls))
                while await self._should_continue() and self._iteration < self.config.max_iterations:
                    self._iteration += 1
                    response = await self._llm.chat(step_prompt)
                    if response.tool_calls:
                        tool_history.extend(await self._act(response.tool_calls))
                    else:
                        break

        final_output = step_outputs[-1].split("] ", 1)[-1] if step_outputs else ""

        if self.config.enable_reflection:
            reflection = await self._reflect(AgentResult(
                success=True,
                output=final_output,
                tool_calls=tool_history,
                iterations=self._iteration,
            ))
        else:
            reflection = None

        self._state = AgentState.IDLE

        if self._workspace_manager:
            self._workspace_manager.log_state_change(
                self._workspace_path, self, AgentState.THINKING.value, self._state.value
            )

        return AgentResult(
            success=True,
            output=final_output,
            tool_calls=tool_history,
            iterations=self._iteration,
            metadata={
                "execution_mode": "workflow",
                "workflow_name": workflow.name,
                "workflow_steps": len(workflow.steps),
                "all_step_outputs": step_outputs,
                "reflection": reflection,
            },
        )

    async def _execute_self(
        self,
        plan_result: PlanResult,
        context: AgentContext,
        tool_history: list[ToolCall],
    ) -> AgentResult:
        """自己执行计划（不委托给子Agent）。"""
        self._state = AgentState.THINKING

        tools = self._tools.get_tool_schemas()

        if plan_result.self_execution_steps:
            response = None
            for i, step in enumerate(plan_result.self_execution_steps):
                step_prompt = f"""You are executing step {i+1}/{len(plan_result.self_execution_steps)} of the task.

Original Task: {context.task}

Current Step: {step}

Previous Steps Completed: {i} steps
Remaining Steps: {len(plan_result.self_execution_steps) - i - 1}

Available Tools: {[t.name for t in self._tools.list_tools() if t.is_available()]}

Execute this step using the available tools. Focus ONLY on this step.
"""
                await self._memory.add(f"Executing step {i+1}: {step}", MemoryType.WORKING)
                response = await self._llm.chat(step_prompt, tools=tools if tools else None)
                
                while self._iteration < self.config.max_iterations:
                    self._iteration += 1
                    if response.tool_calls:
                        tool_history.extend(await self._act(response.tool_calls))
                        if not await self._should_continue():
                            break
                        response = await self._llm.chat(step_prompt, tools=tools if tools else None)
                    else:
                        break
            
            if response is None:
                response = await self._think(context)
        else:
            response = await self._think(context)

        while self._iteration < self.config.max_iterations:
            self._iteration += 1

            if response.tool_calls:
                tool_history.extend(await self._act(response.tool_calls))
                if not await self._should_continue():
                    break
                response = await self._think(context)
            else:
                break

        output = response.content
        if not output or not output.strip():
            tool_output_parts = []
            for tc in tool_history:
                if tc.result and hasattr(tc.result, "output") and tc.result.output:
                    tool_output_parts.append(f"[{tc.name}] {tc.result.output}")
            if tool_output_parts:
                output = "\n\n".join(tool_output_parts)
            else:
                output = ""

        has_failed_tools = any(
            tc.result and hasattr(tc.result, "metadata") and tc.result.metadata.get("error")
            for tc in tool_history
        )

        return AgentResult(
            success=not has_failed_tools,
            output=output,
            tool_calls=tool_history,
            iterations=self._iteration,
            metadata={"execution_mode": "self", "complexity": plan_result.complexity.value},
        )
