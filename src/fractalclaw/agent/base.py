"""Base Agent module - the core abstraction for all agents in FractalClaw."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional
import uuid

from fractalclaw.llm import LLMConfig, LLMEngine, LLMResponse
from fractalclaw.memory import MemoryConfig, MemoryManager, MemoryType
from fractalclaw.plan import Plan, PlanConfig, PlanManager, Task, TaskPriority, TaskStatus, TaskType
from fractalclaw.tools import ToolCall, ToolConfig, ToolManager
from .loader import WorkflowConfig, WorkflowStep
from .tree import AgentTree

if TYPE_CHECKING:
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


class TaskComplexity(Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


@dataclass
class SubAgentRequirement:
    agent_name: str
    agent_type: str
    task_description: str
    required_tools: list[str] = field(default_factory=list)
    expected_output: str = ""
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
    llm_config: Optional[LLMConfig] = None
    memory_config: Optional[MemoryConfig] = None
    tool_config: Optional[ToolConfig] = None
    plan_config: Optional[PlanConfig] = None
    max_iterations: int = 10
    enable_planning: bool = True
    enable_reflection: bool = True
    system_prompt: Optional[str] = None
    workflow: Optional[WorkflowConfig] = None


@dataclass
class AgentContext:
    task: str
    parent_id: Optional[str] = None
    depth: int = 0
    plan_id: Optional[str] = None
    task_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


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

        self._llm = llm_engine or LLMEngine(config.llm_config or LLMConfig())
        self._memory = memory_manager or MemoryManager(config.memory_config or MemoryConfig())
        self._tools = tool_manager or ToolManager(config.tool_config or ToolConfig())
        self._planner = plan_manager or PlanManager(config.plan_config or PlanConfig())
        self._tree = AgentTree(self)

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def state(self) -> AgentState:
        return self._state

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

    async def _create_subagent(
        self, 
        requirement: SubAgentRequirement
    ) -> "Agent":
        """根据需求动态创建子Agent"""
        config = AgentConfig(
            name=requirement.agent_name,
            description=requirement.task_description,
            role=AgentRole.WORKER,
            max_iterations=10,
            enable_planning=False,
            llm_config=self.config.llm_config,
            memory_config=self.config.memory_config,
        )
        
        child = BaseAgent(config)
        
        for tool_name in requirement.required_tools:
            handler = self._get_tool_handler(tool_name)
            child.register_tool(
                name=tool_name,
                description=f"Tool: {tool_name}",
                parameters={},
                handler=handler
            )
        
        if self._workspace_manager:
            child_workspace = await self._workspace_manager.create_agent_workspace(
                child, 
                parent_workspace=self._workspace_path
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
        
        self.add_child(child)
        
        if self._workspace_manager:
            await self._workspace_manager.log_agent_creation(
                parent_workspace=self._workspace_path,
                parent_agent=self,
                child_agent=child,
                requirement=requirement
            )
        
        return child
    
    def _get_tool_handler(self, tool_name: str) -> Callable:
        """获取工具处理器"""
        tool = self._tools.get_tool(tool_name)
        if tool:
            return tool.handler
        
        async def placeholder(**kwargs) -> str:
            return f"Tool '{tool_name}' executed with args: {kwargs}"
        return placeholder

    def _plan_from_workflow(self, context: AgentContext) -> PlanResult:
        """根据配置中的workflow直接生成PlanResult，跳过LLM规划。"""
        workflow = self.config.workflow
        self_execution_steps = [
            f"[Step {s.step}] {s.name}: {s.action}"
            for s in workflow.steps
        ]

        return PlanResult(
            plan=None,
            complexity=TaskComplexity.MODERATE,
            needs_subagents=False,
            self_execution_steps=self_execution_steps,
            reasoning=f"Using predefined workflow '{workflow.name}' with {len(workflow.steps)} steps",
        )

    async def _plan(self, context: AgentContext) -> PlanResult:
        """规划阶段：分析任务复杂度，创建执行计划。"""
        if self.config.workflow:
            return self._plan_from_workflow(context)

        old_state = self._state
        self._state = AgentState.PLANNING
        
        if self._workspace_manager:
            self._workspace_manager.log_state_change(
                self._workspace_path, self, old_state.value, self._state.value
            )

        prompt = f"""Analyze the following task and create an execution plan.

Task: {context.task}
Context:
- Agent Role: {self.config.role.value}
- Available Tools: {[t.name for t in self._tools.list_tools()]}
- Child Agents: {[c.name for c in self._tree.children]}

You MUST respond with a JSON structure containing:
1. "complexity": "simple" | "moderate" | "complex"
   - simple: single step task, can be completed directly
   - moderate: multiple steps but can be handled by this agent
   - complex: requires multiple specialized agents working together

2. "needs_subagents": true | false
   - true if task needs to be delegated to child agents
   - false if this agent can handle it alone

3. "reasoning": brief explanation of your analysis

4. If needs_subagents is true, include "subagent_requirements":
   [
     {{
       "agent_name": "name for the subagent",
       "agent_type": "specialist type (e.g., coder, researcher, analyst)",
       "task_description": "specific task for this subagent",
       "required_tools": ["tool1", "tool2"],
       "expected_output": "what this subagent should produce",
       "parameters": {{}}
     }}
   ]

5. If needs_subagents is false, include "self_execution_steps":
   ["step 1 description", "step 2 description", ...]

6. If needs_subagents is true, also include "subtasks" for the plan:
   [
     {{
       "name": "subtask name",
       "description": "detailed description",
       "type": "atomic" | "composite",
       "priority": 1-3,
       "dependencies": ["dependency_task_id"],
       "assigned_agent": "agent_name"
     }}
   ]"""

        response = await self._llm.chat(prompt)
        plan_result = await self._parse_plan_response(response.content, context)
        
        self._last_plan_result = plan_result

        if plan_result.plan:
            self._current_plan = plan_result.plan
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

    async def _parse_plan_response(self, response: str, context: AgentContext) -> PlanResult:
        """解析 LLM 返回的计划响应。"""
        import json
        import re

        match = re.search(r"\{[\s\S]*\}", response)
        if not match:
            return PlanResult(
                complexity=TaskComplexity.SIMPLE,
                needs_subagents=False,
                self_execution_steps=[context.task],
                reasoning="Failed to parse LLM response, defaulting to simple self-execution",
            )

        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            return PlanResult(
                complexity=TaskComplexity.SIMPLE,
                needs_subagents=False,
                self_execution_steps=[context.task],
                reasoning="Invalid JSON in LLM response, defaulting to simple self-execution",
            )

        complexity_str = data.get("complexity", "simple")
        try:
            complexity = TaskComplexity(complexity_str)
        except ValueError:
            complexity = TaskComplexity.SIMPLE

        needs_subagents = data.get("needs_subagents", False)
        reasoning = data.get("reasoning", "")

        subagent_requirements = []
        for req in data.get("subagent_requirements", []):
            subagent_requirements.append(
                SubAgentRequirement(
                    agent_name=req.get("agent_name", ""),
                    agent_type=req.get("agent_type", "worker"),
                    task_description=req.get("task_description", ""),
                    required_tools=req.get("required_tools", []),
                    expected_output=req.get("expected_output", ""),
                    parameters=req.get("parameters", {}),
                )
            )

        self_execution_steps = data.get("self_execution_steps", [])

        plan = None
        tasks_data = data.get("subtasks") or data.get("tasks", [])
        if tasks_data and needs_subagents:
            root_task = Task(
                id="root",
                name=context.task[:50],
                description=context.task,
                task_type=TaskType.COMPOSITE,
            )

            for i, td in enumerate(tasks_data):
                subtask = self._planner.create_task(
                    name=td.get("name", f"Subtask {i + 1}"),
                    description=td.get("description", ""),
                    task_type=TaskType(td.get("type", "atomic")),
                    priority=TaskPriority(td.get("priority", 2)),
                    dependencies=td.get("dependencies", []),
                )
                subtask.assigned_agent = td.get("assigned_agent")
                root_task.subtasks.append(subtask)

            plan = Plan(
                id=self._planner._generate_plan_id(),
                name=f"Plan for: {context.task[:30]}",
                description=context.task,
                root_task=root_task,
            )

            is_valid, errors = self._planner.validate_plan(plan)
            if not is_valid:
                plan = None

        return PlanResult(
            plan=plan,
            complexity=complexity,
            needs_subagents=needs_subagents,
            subagent_requirements=subagent_requirements,
            self_execution_steps=self_execution_steps,
            reasoning=reasoning,
        )

    async def _execute_plan(self, context: AgentContext) -> list[AgentResult]:
        """执行计划：按依赖顺序执行所有子任务。"""
        if not self._current_plan:
            return []

        results: list[AgentResult] = []
        completed: set[str] = set()
        failed: set[str] = set()

        while True:
            ready = self._current_plan.get_ready_tasks(completed | failed)
            if not ready:
                break

            for task in ready:
                self._current_plan.update_task_status(task.id, TaskStatus.RUNNING)
                result = await self._execute_subtask(task, context)
                results.append(result)

                if result.success:
                    self._current_plan.update_task_status(task.id, TaskStatus.COMPLETED)
                    completed.add(task.id)
                else:
                    self._current_plan.update_task_status(task.id, TaskStatus.FAILED)
                    failed.add(task.id)

        return results

    async def _execute_subtask(self, task: Task, context: AgentContext) -> AgentResult:
        """执行单个子任务。"""
        old_state = self._state
        self._state = AgentState.DELEGATING
        
        if self._workspace_manager:
            self._workspace_manager.log_state_change(
                self._workspace_path, self, old_state.value, self._state.value
            )

        child = None
        if task.assigned_agent:
            child = self._tree.get_child_by_name(task.assigned_agent) or self._tree.get_child(task.assigned_agent)
        
        if not child and task.assigned_agent:
            requirement = self._find_subagent_requirement(task.assigned_agent)
            if requirement:
                planning_state = self._state
                self._state = AgentState.PLANNING
                
                if self._workspace_manager:
                    self._workspace_manager.log_state_change(
                        self._workspace_path, self, planning_state.value, self._state.value
                    )
                
                child = await self._create_subagent(requirement)
                
                if self._workspace_manager:
                    self._workspace_manager.log_state_change(
                        self._workspace_path, self, AgentState.PLANNING.value, AgentState.DELEGATING.value
                    )
                
                self._state = AgentState.DELEGATING

        if child:
            sub_ctx = AgentContext(
                task=task.description,
                parent_id=self._id,
                depth=context.depth + 1,
                task_id=task.id,
                metadata={"input": task.input_data},
            )
            
            if self._workspace_manager:
                self._workspace_manager.log_subtask_delegation(
                    self._workspace_path, self, child, task.description
                )
            
            result = await child.run(sub_ctx)
            
            if self._memory.sharing and self._workspace_path and child._workspace_path:
                await self._memory.sharing.child_to_parent(
                    child_agent_id=child._id,
                    parent_agent_id=self._id,
                    child_workspace=child._workspace_path,
                    parent_workspace=self._workspace_path,
                    result=result.output if result.success else None,
                    errors=result.error,
                )
            
            self._state = AgentState.THINKING
            
            if self._workspace_manager:
                self._workspace_manager.log_state_change(
                    self._workspace_path, self, AgentState.DELEGATING.value, self._state.value
                )
            
            return result

        self._state = AgentState.THINKING
        response = await self._llm.chat(task.description)
        
        if self._workspace_manager:
            self._workspace_manager.log_state_change(
                self._workspace_path, self, AgentState.DELEGATING.value, self._state.value
            )

        return AgentResult(
            success=True,
            output=response.content,
            iterations=1,
            metadata={"task_id": task.id},
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
        """行动阶段：执行工具调用。"""
        import json

        old_state = self._state
        self._state = AgentState.EXECUTING
        
        if self._workspace_manager:
            self._workspace_manager.log_state_change(
                self._workspace_path, self, old_state.value, self._state.value
            )
        
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

            result = await self._tools.execute(name, args)
            results.append(result)
            self._llm.add_tool_result(call_id, name, str(result.result))
            
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
            return False, "No tool calls were made. The task requires actual execution via tools, not just text output."

        prompt = f"""Evaluate whether the task execution achieved its goal.

Original Task: {context.task}
Execution Result:
- Success: {result.success}
- Output: {result.output[:500]}
- Iterations: {result.iterations}
- Tool calls made: {len(result.tool_calls)}
- Subtask results: {len(result.subtask_results)}

IMPORTANT: The task is only achieved if actual operations were performed (e.g., files created, commands executed). Simply providing instructions or guidance without executing tools does NOT count as achieving the goal.

Respond with a JSON:
{{
    "goal_achieved": true | false,
    "evaluation": "detailed evaluation of the execution",
    "issues": ["issue1", "issue2"]
}}"""

        response = await self._llm.chat(prompt)
        import json
        import re

        match = re.search(r"\{[\s\S]*\}", response.content)
        if match:
            try:
                data = json.loads(match.group())
                return data.get("goal_achieved", False), data.get("evaluation", "")
            except json.JSONDecodeError:
                pass

        return result.success, "Could not parse evaluation, using success flag"

    async def _replan(
        self,
        context: AgentContext,
        previous_result: AgentResult,
        reflection: str,
        evaluation: str,
    ) -> PlanResult:
        """结合反思结果重新规划。"""
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

Context:
- Agent Role: {self.config.role.value}
- Available Tools: {[t.name for t in self._tools.list_tools()]}
- Child Agents: {[c.name for c in self._tree.children]}

Based on the above, create a NEW and IMPROVED execution plan.
You MUST respond with a JSON structure containing:
1. "complexity": "simple" | "moderate" | "complex"
2. "needs_subagents": true | false
3. "reasoning": explanation of what went wrong and how the new plan addresses it
4. "subagent_requirements" (if needs_subagents is true)
5. "self_execution_steps" (if needs_subagents is false)
6. "subtasks" (if needs_subagents is true)"""

        response = await self._llm.chat(prompt)
        plan_result = await self._parse_plan_response(response.content, context)

        if plan_result.plan:
            self._current_plan = plan_result.plan
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
                    result = AgentResult(
                        success=all(r.success for r in subtask_results),
                        output="\n".join(f"[{r.metadata.get('task_id')}] {r.output}" for r in subtask_results),
                        tool_calls=tool_history,
                        subtask_results=subtask_results,
                        iterations=self._iteration,
                        plan=plan_result.plan,
                    )
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
                    self._state = AgentState.IDLE
                    await self._memory.end_session(result.error or "Replan exhausted")
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

Available Tools: {[t.name for t in self._tools.list_tools()]}

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

        return AgentResult(
            success=True,
            output=response.content,
            tool_calls=tool_history,
            iterations=self._iteration,
            metadata={"execution_mode": "self", "complexity": plan_result.complexity.value},
        )
