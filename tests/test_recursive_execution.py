"""Tests for governance-first recursive execution."""

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
import sys
import types
from typing import Optional

from fractalclaw.agent.base import (
    AgentConfig,
    AgentContext,
    AgentResult,
    AgentRole,
    BaseAgent,
    PlanResult,
    SubAgentRequirement,
)
from fractalclaw.plan import Plan, PlanConfig, Task, TaskPriority, TaskType
from fractalclaw.scheduler import Scheduler, SchedulerConfig
from fractalclaw.scheduler.agent_workspace import AgentWorkspaceManager


def _make_task(
    task_id: str,
    description: str,
    *,
    assigned_agent: Optional[str] = None,
    priority: TaskPriority = TaskPriority.MEDIUM,
    parallel_safe: bool = False,
    write_scope: Optional[list[str]] = None,
) -> Task:
    task = Task(
        id=task_id,
        name=task_id,
        description=description,
        task_type=TaskType.ATOMIC,
        priority=priority,
    )
    task.assigned_agent = assigned_agent
    task.metadata["parallel_safe"] = parallel_safe
    task.metadata["write_scope"] = list(write_scope or [])
    task.metadata["read_scope"] = []
    task.metadata["delegation_allowed"] = True
    return task


def test_governance_rejects_duplicate_fingerprint():
    agent = BaseAgent(
        AgentConfig(
            name="Parent",
            description="parent task",
            role=AgentRole.COORDINATOR,
            plan_config=PlanConfig(),
        )
    )
    context = AgentContext(task="parent task", metadata={"branch_path": "root"})
    task = _make_task("task_1", "implement subtask", assigned_agent="Child")
    task.metadata["branch_path"] = "root/task_1"

    requirement = SubAgentRequirement(
        agent_name="Child",
        agent_type="coder",
        task_description="Implement a smaller coding task",
        expected_output="Patch and summary",
    )

    first = agent._governance.evaluate_requirement(agent, requirement, context, task, depth=1)
    assert first.allowed is True

    agent._governance.reserve_requirement(agent, first)
    second = agent._governance.evaluate_requirement(agent, requirement, context, task, depth=1)

    assert second.allowed is False
    assert second.reason_code == "duplicate_fingerprint"


def test_prepare_plan_result_collapses_no_benefit_split():
    agent = BaseAgent(
        AgentConfig(
            name="Parent",
            description="top-level task",
            role=AgentRole.COORDINATOR,
            plan_config=PlanConfig(),
        )
    )
    context = AgentContext(task="top-level task", metadata={"branch_path": "root"})
    root = Task(
        id="root",
        name="root",
        description="top-level task",
        task_type=TaskType.COMPOSITE,
    )
    root.subtasks.append(
        _make_task("task_1", "top-level task", assigned_agent="Child")
    )
    plan = Plan(id="plan_1", name="plan", description="demo", root_task=root)
    plan_result = PlanResult(
        plan=plan,
        needs_subagents=True,
        subagent_requirements=[
            SubAgentRequirement(
                agent_name="Child",
                agent_type="worker",
                task_description="top-level task",
            )
        ],
    )

    prepared = agent._governance.prepare_plan_result(agent, plan_result, context)

    assert prepared.needs_subagents is False
    assert prepared.plan is None
    assert prepared.self_execution_steps == ["top-level task"]


def test_wave_planning_serializes_scope_conflicts():
    config = PlanConfig(enable_parallel=True, max_parallel_subtasks=3)
    agent = BaseAgent(
        AgentConfig(
            name="Parent",
            description="parallel test",
            role=AgentRole.COORDINATOR,
            plan_config=config,
        )
    )
    context = AgentContext(task="parallel test", metadata={"branch_path": "root"})
    first = _make_task("task_1", "write file a", parallel_safe=True, write_scope=["file:a"])
    second = _make_task("task_2", "write file a again", parallel_safe=True, write_scope=["file:a"])
    third = _make_task("task_3", "unsafe task", parallel_safe=False)

    wave = agent._governance.plan_wave(agent, [first, second, third], context, wave_index=1)

    assert [task.id for task in wave.parallel_tasks] == ["task_1"]
    assert [task.id for task in wave.serial_tasks] == ["task_2", "task_3"]
    assert second.metadata["governance_reason"] == "write_scope_conflict"
    assert third.metadata["governance_reason"] == "parallel_disabled"


class WaveExecutionAgent(BaseAgent):
    def __init__(self, config: AgentConfig, outcomes: dict[str, tuple[bool, str, float]]):
        super().__init__(config)
        self.outcomes = outcomes
        self.started: list[str] = []
        self.active = 0
        self.max_active = 0

    async def _execute_subtask(self, task: Task, context: AgentContext) -> AgentResult:
        success, output, delay = self.outcomes[task.id]
        self.started.append(task.id)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(delay)
        self.active -= 1
        return AgentResult(
            success=success,
            output=output,
            metadata={"task_id": task.id, "task_description": task.description},
            error=None if success else output,
        )


def test_parallel_wave_failure_waits_for_started_siblings(tmp_path):
    async def _run():
        config = PlanConfig(enable_parallel=True, max_parallel_subtasks=2)
        agent = WaveExecutionAgent(
            AgentConfig(
                name="Parent",
                description="parallel execution",
                role=AgentRole.COORDINATOR,
                plan_config=config,
            ),
            outcomes={
                "task_1": (True, "ok-1", 0.05),
                "task_2": (False, "boom", 0.05),
                "task_3": (True, "should-not-run", 0.01),
            },
        )
        workspace_manager = AgentWorkspaceManager(tmp_path)
        workspace = await workspace_manager.create_agent_workspace(agent)
        agent.set_workspace(workspace, workspace_manager)

        root = Task(
            id="root",
            name="root",
            description="parallel execution",
            task_type=TaskType.COMPOSITE,
        )
        root.subtasks.extend(
            [
                _make_task("task_1", "parallel success", parallel_safe=True),
                _make_task("task_2", "parallel failure", parallel_safe=True),
                _make_task("task_3", "serial fallback", parallel_safe=False),
            ]
        )
        agent._current_plan = Plan(id="plan_1", name="plan", description="demo", root_task=root)

        results = await agent._execute_plan(AgentContext(task="parallel execution", metadata={"branch_path": "root"}))

        assert set(agent.started) == {"task_1", "task_2"}
        assert agent.max_active >= 2
        assert len(results) == 2
        assert root.subtasks[1].metadata["failure_reason"] == "boom"
        assert "task_3" not in agent.started

    asyncio.run(_run())


class ReplanOnFailureAgent(BaseAgent):
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.replanned = False

    async def _plan(self, context: AgentContext) -> PlanResult:
        root = Task(
            id="root",
            name="root",
            description=context.task,
            task_type=TaskType.COMPOSITE,
        )
        task = _make_task("task_1", "delegated failure", assigned_agent="Child")
        root.subtasks.append(task)
        self._current_plan = Plan(id="plan_1", name="plan", description=context.task, root_task=root)
        return PlanResult(
            plan=self._current_plan,
            needs_subagents=True,
            subagent_requirements=[
                SubAgentRequirement(
                    agent_name="Child",
                    agent_type="worker",
                    task_description="delegated failure",
                    expected_output="done",
                )
            ],
        )

    async def _execute_plan(self, context: AgentContext) -> list[AgentResult]:
        return [
            AgentResult(
                success=False,
                output="child failed",
                metadata={
                    "task_id": "task_1",
                    "task_description": "delegated failure",
                    "execution_mode": "delegated",
                    "selected_model": "cheap-model",
                    "used_tools": ["read"],
                    "branch_path": "root/task_1",
                    "depth": 1,
                },
                error="child failed",
            )
        ]

    async def _replan(
        self,
        context: AgentContext,
        previous_result: AgentResult,
        reflection: str,
        evaluation: str,
    ) -> PlanResult:
        self.replanned = True
        return PlanResult(
            needs_subagents=False,
            self_execution_steps=["recover locally"],
            reasoning="Fallback to local execution.",
        )

    async def _execute_self(
        self,
        plan_result: PlanResult,
        context: AgentContext,
        tool_history,
    ) -> AgentResult:
        return AgentResult(success=True, output="recovered locally", metadata={"execution_mode": "self"})

    async def _evaluate_execution(self, result: AgentResult, context: AgentContext) -> tuple[bool, str]:
        return True, "Recovered successfully."

    async def _reflect(self, result: AgentResult) -> str:
        return "reflection"


def test_child_failure_triggers_parent_replan():
    async def _run():
        agent = ReplanOnFailureAgent(
            AgentConfig(
                name="Parent",
                description="replan task",
                role=AgentRole.COORDINATOR,
                plan_config=PlanConfig(),
            )
        )

        result = await agent.run(AgentContext(task="replan task", metadata={"branch_path": "root"}))

        assert result.success is True
        assert result.output == "recovered locally"
        assert agent.replanned is True

    asyncio.run(_run())


class DirectSelfExecutionAgent(BaseAgent):
    async def _plan(self, context: AgentContext) -> PlanResult:
        return PlanResult(
            needs_subagents=False,
            self_execution_steps=["respond directly"],
            reasoning="Direct self execution.",
        )

    async def _execute_self(
        self,
        plan_result: PlanResult,
        context: AgentContext,
        tool_history,
    ) -> AgentResult:
        return AgentResult(
            success=True,
            output="analysis complete",
            metadata={"execution_mode": "self"},
        )

    async def _reflect(self, result: AgentResult) -> str:
        return "reflection"


def test_direct_self_execution_without_tools_is_accepted():
    async def _run():
        agent = DirectSelfExecutionAgent(
            AgentConfig(
                name="SelfAgent",
                description="analysis task",
                role=AgentRole.SPECIALIST,
                plan_config=PlanConfig(),
            )
        )

        result = await agent.run(AgentContext(task="analysis task", metadata={"branch_path": "root"}))

        assert result.success is True
        assert result.metadata["goal_achieved"] is True
        assert result.output == "analysis complete"

    asyncio.run(_run())


class SharedRuntimeChildAgent(BaseAgent):
    async def _plan(self, context: AgentContext) -> PlanResult:
        assert self._delegation_runtime["delegation_count"] == 1
        return PlanResult(
            needs_subagents=False,
            self_execution_steps=["continue recursively"],
        )

    async def _execute_self(
        self,
        plan_result: PlanResult,
        context: AgentContext,
        tool_history,
    ) -> AgentResult:
        return AgentResult(
            success=True,
            output="child completed",
            metadata={"execution_mode": "self"},
        )

    async def _reflect(self, result: AgentResult) -> str:
        return "reflection"


def test_child_run_preserves_shared_delegation_budget():
    async def _run():
        parent = BaseAgent(
            AgentConfig(
                name="Parent",
                description="parent task",
                role=AgentRole.COORDINATOR,
                plan_config=PlanConfig(max_total_delegations=1),
            )
        )
        parent._delegation_runtime["delegation_count"] = 1

        child = SharedRuntimeChildAgent(
            AgentConfig(
                name="Child",
                description="child task",
                role=AgentRole.SPECIALIST,
                plan_config=PlanConfig(max_total_delegations=1),
            )
        )
        child._delegation_runtime = parent._delegation_runtime

        result = await child.run(
            AgentContext(
                task="child task",
                parent_id=parent.id,
                metadata={"branch_path": "root/task_1"},
            )
        )

        assert result.success is True
        assert child._delegation_runtime["delegation_count"] == 1
        assert child._delegation_runtime is parent._delegation_runtime

    asyncio.run(_run())


class FactoryBackedAgent(BaseAgent):
    async def run(self, context: AgentContext) -> AgentResult:
        return AgentResult(success=True, output="factory path")


class StubFactory:
    def __init__(self):
        self.called = False
        self.called_from_dict = False
        self.workspace_manager = None

    def set_workspace_manager(self, workspace_manager):
        self.workspace_manager = workspace_manager

    def create_from_config(self, config):
        self.called = True
        return FactoryBackedAgent(config)

    def create_from_dict(self, config_dict):
        self.called_from_dict = True
        return FactoryBackedAgent(
            AgentConfig(
                name=config_dict.get("name", "FactoryDict"),
                description=config_dict.get("description", ""),
                role=AgentRole(config_dict.get("role", AgentRole.ROOT.value)),
            )
        )


def test_scheduler_uses_injected_factory(tmp_path):
    async def _run():
        factory = StubFactory()
        scheduler = Scheduler(
            SchedulerConfig(workspace_root=str(tmp_path)),
            agent_factory=factory,
        )
        task = scheduler.create_project("Execute through factory", name="factory")
        result = await scheduler.execute_task(task.id)

        assert result.success is True
        assert factory.called is True
        assert factory.workspace_manager is scheduler._workspace_manager

    asyncio.run(_run())


def test_scheduler_reuses_existing_root_config_path(tmp_path):
    async def _run():
        factory = StubFactory()
        scheduler = Scheduler(
            SchedulerConfig(workspace_root=str(tmp_path)),
            agent_factory=factory,
        )
        task = scheduler.create_project("Execute through saved config", name="factory-config")
        config_path = Path(task.workspace_path) / "root_agent.yaml"
        config_path.write_text(
            "name: RootFromFile\ndescription: Root config description\nrole: worker\n",
            encoding="utf-8",
        )

        result = await scheduler.execute_task(
            task.id,
            agent_config=AgentConfig(
                name="RootOverride",
                description="override description",
                role=AgentRole.ROOT,
            ),
            existing_config_path=config_path,
        )

        assert result.success is True
        assert factory.called_from_dict is True
        assert (Path(task.workspace_path) / "agent_config.yaml").exists()

    asyncio.run(_run())


def test_root_task_text_reused_for_workspace_instruction(tmp_path):
    async def _run():
        prompt_toolkit = types.ModuleType("prompt_toolkit")
        prompt_toolkit.PromptSession = object
        prompt_toolkit.print_formatted_text = lambda *args, **kwargs: None
        sys.modules.setdefault("prompt_toolkit", prompt_toolkit)

        patch_stdout = types.ModuleType("prompt_toolkit.patch_stdout")

        class _PatchStdout:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        patch_stdout.patch_stdout = lambda: _PatchStdout()
        sys.modules.setdefault("prompt_toolkit.patch_stdout", patch_stdout)

        formatted_text = types.ModuleType("prompt_toolkit.formatted_text")
        formatted_text.ANSI = lambda text="": text
        sys.modules.setdefault("prompt_toolkit.formatted_text", formatted_text)

        styles = types.ModuleType("prompt_toolkit.styles")
        styles.Style = type("Style", (), {"from_dict": staticmethod(lambda value: value)})
        sys.modules.setdefault("prompt_toolkit.styles", styles)

        application = types.ModuleType("prompt_toolkit.application")
        application.get_app = lambda: type("App", (), {"invalidate": lambda self: None})()
        sys.modules.setdefault("prompt_toolkit.application", application)

        main_module = importlib.import_module("entry.main")
        FractalClawApp = main_module.FractalClawApp
        app = FractalClawApp()
        app.scheduler = Scheduler(SchedulerConfig(workspace_root=str(tmp_path)))

        intent_result = {
            "requirements": ["first task", "second task"],
            "acceptance_criteria": ["done"],
        }
        root_task_text = app._build_root_task_text(intent_result["requirements"])
        task = await app._create_workspace(intent_result, root_task_text)

        assert root_task_text == "- first task\n- second task"
        assert task.instruction == root_task_text
        assert app.scheduler.get_task(task.id).instruction == root_task_text

    asyncio.run(_run())


def test_fail_fast_parallel_error_stops_queued_parallel_tasks(tmp_path):
    async def _run():
        config = PlanConfig(
            enable_parallel=True,
            max_parallel_subtasks=1,
            fail_fast_on_parallel_error=True,
        )
        agent = WaveExecutionAgent(
            AgentConfig(
                name="Parent",
                description="fail fast parallel execution",
                role=AgentRole.COORDINATOR,
                plan_config=config,
            ),
            outcomes={
                "task_1": (False, "boom", 0.01),
                "task_2": (True, "ok-2", 0.01),
                "task_3": (True, "ok-3", 0.01),
            },
        )
        workspace_manager = AgentWorkspaceManager(tmp_path)
        workspace = await workspace_manager.create_agent_workspace(agent)
        agent.set_workspace(workspace, workspace_manager)

        root = Task(
            id="root",
            name="root",
            description="fail fast parallel execution",
            task_type=TaskType.COMPOSITE,
        )
        root.subtasks.extend(
            [
                _make_task("task_1", "parallel fail", parallel_safe=True),
                _make_task("task_2", "queued parallel 2", parallel_safe=True),
                _make_task("task_3", "queued parallel 3", parallel_safe=True),
            ]
        )
        agent._current_plan = Plan(id="plan_1", name="plan", description="demo", root_task=root)

        results = await agent._execute_plan(
            AgentContext(task="fail fast parallel execution", metadata={"branch_path": "root"})
        )

        assert agent.started == ["task_1"]
        assert len(results) == 1
        assert results[0].success is False

    asyncio.run(_run())
