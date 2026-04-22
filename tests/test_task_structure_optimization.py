"""Tests for workspace structure and delegation safeguards."""

import asyncio

from fractalclaw.agent.base import AgentConfig, AgentContext, AgentResult, AgentRole, BaseAgent, PlanResult, SubAgentRequirement
from fractalclaw.plan import Plan, Task, TaskPriority, TaskType
from fractalclaw.scheduler.agent_workspace import AgentWorkspaceManager, WorkDocument


class StaticChildAgent(BaseAgent):
    async def run(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            success=True,
            output=f"done:{context.task}",
            metadata={"task_id": context.task_id},
        )


class SharedRuntimeStaticChildAgent(BaseAgent):
    async def run(self, context: AgentContext) -> AgentResult:
        assert self._delegation_runtime["delegation_count"] == 3
        return AgentResult(
            success=True,
            output=f"runtime:{context.task}",
            metadata={"task_id": context.task_id},
        )


def test_workspace_manager_copies_existing_config(tmp_path):
    workspace_manager = AgentWorkspaceManager(tmp_path)
    workspace_path = tmp_path / "task"
    workspace_path.mkdir()

    existing = workspace_path / "runtime_agent.yaml"
    existing.write_text("name: RuntimeChild\nrole: specialist\n", encoding="utf-8")

    agent = BaseAgent(
        AgentConfig(
            name="RuntimeChild",
            description="child",
            role=AgentRole.SPECIALIST,
        )
    )

    workspace_manager.setup_agent_files(
        workspace_path,
        agent,
        WorkDocument(task_requirement="implement child task", acceptance_criteria="return summary"),
        existing_config_path=existing,
    )

    copied = workspace_path / "agent_config.yaml"
    task_doc = workspace_path / "memory" / "semantic" / "task_requirements.md"

    assert copied.exists()
    assert copied.read_text(encoding="utf-8") == existing.read_text(encoding="utf-8")
    assert task_doc.exists()


def test_plan_ready_tasks_only_returns_leaf_nodes():
    root = Task(
        id="root",
        name="root",
        description="root",
        task_type=TaskType.COMPOSITE,
    )
    child = Task(
        id="child",
        name="child",
        description="child",
        task_type=TaskType.COMPOSITE,
    )
    leaf = Task(
        id="leaf",
        name="leaf",
        description="leaf",
        task_type=TaskType.ATOMIC,
    )
    child.subtasks.append(leaf)
    root.subtasks.append(child)

    plan = Plan(id="plan_1", name="demo", description="demo", root_task=root)
    ready = plan.get_ready_tasks(set())

    assert [task.id for task in ready] == ["leaf"]


def test_execute_subtask_creates_and_uses_child_agent(tmp_path):
    async def _run():
        workspace_manager = AgentWorkspaceManager(tmp_path)
        parent = BaseAgent(
            AgentConfig(
                name="Parent",
                description="delegate work",
                role=AgentRole.COORDINATOR,
            )
        )
        parent_workspace = await workspace_manager.create_agent_workspace(parent)
        parent.set_workspace(parent_workspace, workspace_manager)

        requirement = SubAgentRequirement(
            agent_name="ChildWorker",
            agent_type="worker",
            task_description="Handle delegated leaf task",
            expected_output="completed leaf task",
        )
        parent._last_plan_result = PlanResult(
            needs_subagents=True,
            subagent_requirements=[requirement],
        )

        child = StaticChildAgent(
            AgentConfig(
                name="ChildWorker",
                description="child",
                role=AgentRole.WORKER,
            )
        )
        child_workspace = await workspace_manager.create_agent_workspace(child, parent_workspace=parent_workspace)
        child.set_workspace(child_workspace, workspace_manager)

        async def _create_subagent(req, depth):
            assert req.agent_name == "ChildWorker"
            assert depth == 1
            return child

        parent._create_subagent = _create_subagent

        task = parent.planner.create_task(
            name="delegated",
            description="do delegated work",
            task_type=TaskType.ATOMIC,
            priority=TaskPriority.MEDIUM,
        )
        task.assigned_agent = "ChildWorker"

        result = await parent._execute_subtask(task, AgentContext(task="top-level task"))

        assert result.success is True
        assert result.output == "done:do delegated work"
        assert task.metadata["assigned_agent_id"] == child.id
        assert task.metadata["assigned_agent_name"] == child.name

    asyncio.run(_run())


def test_existing_child_uses_parent_shared_runtime(tmp_path):
    async def _run():
        workspace_manager = AgentWorkspaceManager(tmp_path)
        parent = BaseAgent(
            AgentConfig(
                name="Parent",
                description="delegate work",
                role=AgentRole.COORDINATOR,
            )
        )
        parent._delegation_runtime["delegation_count"] = 3
        parent_workspace = await workspace_manager.create_agent_workspace(parent)
        parent.set_workspace(parent_workspace, workspace_manager)

        child = SharedRuntimeStaticChildAgent(
            AgentConfig(
                name="StaticChild",
                description="child",
                role=AgentRole.WORKER,
            )
        )
        child._delegation_runtime["delegation_count"] = 0
        child_workspace = await workspace_manager.create_agent_workspace(child, parent_workspace=parent_workspace)
        child.set_workspace(child_workspace, workspace_manager)
        parent.add_child(child)

        task = parent.planner.create_task(
            name="delegated",
            description="use static child",
            task_type=TaskType.ATOMIC,
            priority=TaskPriority.MEDIUM,
        )
        task.assigned_agent = "StaticChild"

        result = await parent._execute_subtask(task, AgentContext(task="top-level task"))

        assert result.success is True
        assert child._delegation_runtime is parent._delegation_runtime

    asyncio.run(_run())
