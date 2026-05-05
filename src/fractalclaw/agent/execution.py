"""Recursive governance and wave-based plan execution helpers."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from fractalclaw.monitor import EventType, emit_agent_event
from fractalclaw.plan import Plan, PlanConfig, Task, TaskPriority, TaskStatus

if TYPE_CHECKING:
    from .base import Agent, AgentContext, AgentResult, PlanResult, SubAgentRequirement


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


@dataclass
class GovernanceDecision:
    allowed: bool
    reason_code: str = "allowed"
    reason: str = ""
    fingerprint: str = ""
    branch_path: str = ""


@dataclass
class ExecutionWavePlan:
    wave_id: str
    parallel_tasks: list[Task] = field(default_factory=list)
    serial_tasks: list[Task] = field(default_factory=list)


class DelegationGovernance:
    """Deterministic governance rules for recursive delegation."""

    def __init__(self, config: PlanConfig):
        self.config = config

    def build_branch_path(self, context: "AgentContext", task: Optional[Task] = None) -> str:
        base_path = str(context.metadata.get("branch_path") or "root")
        if task is None:
            return base_path
        if base_path.endswith(task.id):
            return base_path
        return f"{base_path}/{task.id}"

    def build_requirement_fingerprint(
        self,
        requirement: "SubAgentRequirement",
        branch_path: str,
    ) -> str:
        payload = "|".join(
            [
                branch_path,
                _normalize_text(requirement.agent_type),
                _normalize_text(requirement.task_description),
                _normalize_text(requirement.expected_output),
                ",".join(sorted(requirement.required_tools)),
            ]
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    def prepare_plan_result(
        self,
        agent: "Agent",
        plan_result: "PlanResult",
        context: "AgentContext",
    ) -> "PlanResult":
        if not plan_result.plan or not plan_result.needs_subagents:
            return plan_result

        plan = plan_result.plan
        if len(plan.root_task.subtasks) > self.config.max_subtasks:
            plan.root_task.subtasks = plan.root_task.subtasks[: self.config.max_subtasks]

        requirements_by_name = {
            requirement.agent_name: requirement
            for requirement in plan_result.subagent_requirements
            if requirement.agent_name
        }

        filtered_subtasks: list[Task] = []
        filtered_requirements: list["SubAgentRequirement"] = []

        for task in plan.root_task.subtasks:
            branch_path = self.build_branch_path(context, task)
            task.metadata.setdefault("parallel_safe", False)
            task.metadata.setdefault("write_scope", [])
            task.metadata.setdefault("read_scope", [])
            task.metadata.setdefault("delegation_allowed", True)
            task.metadata["branch_path"] = branch_path

            requirement = requirements_by_name.get(task.assigned_agent or "")
            if requirement is None:
                task.metadata["governance_reason"] = "missing_requirement"
                continue

            requirement.parallel_safe = bool(requirement.parallel_safe)
            requirement.write_scope = list(requirement.write_scope or [])
            requirement.read_scope = list(requirement.read_scope or [])
            requirement.delegation_allowed = bool(requirement.delegation_allowed)

            task.metadata["parallel_safe"] = bool(
                task.metadata.get("parallel_safe", requirement.parallel_safe)
            )
            task.metadata["write_scope"] = list(
                task.metadata.get("write_scope") or requirement.write_scope
            )
            task.metadata["read_scope"] = list(
                task.metadata.get("read_scope") or requirement.read_scope
            )
            task.metadata["delegation_allowed"] = bool(
                task.metadata.get("delegation_allowed", requirement.delegation_allowed)
            )
            filtered_subtasks.append(task)
            filtered_requirements.append(requirement)

        unique_requirements: list["SubAgentRequirement"] = []
        seen_names: set[str] = set()
        for requirement in filtered_requirements:
            if requirement.agent_name in seen_names:
                continue
            seen_names.add(requirement.agent_name)
            unique_requirements.append(requirement)

        plan.root_task.subtasks = filtered_subtasks
        plan_result.subagent_requirements = unique_requirements

        if not filtered_subtasks or not unique_requirements:
            plan_result.plan = None
            plan_result.needs_subagents = False
            plan_result.self_execution_steps = plan_result.self_execution_steps or [context.task]
            plan_result.reasoning = (
                f"[DELEGATION_DOWNGRADED] {plan_result.reasoning or ''} "
                f"Reason: no valid subtasks or requirements after governance filtering "
                f"(filtered_subtasks={len(filtered_subtasks)}, unique_requirements={len(unique_requirements)})"
            ).strip()
            return plan_result

        if (
            len(unique_requirements) == 1
            and len(filtered_subtasks) == 1
            and not unique_requirements[0].required_tools
            and not unique_requirements[0].expected_output.strip()
            and _normalize_text(unique_requirements[0].task_description) == _normalize_text(context.task)
        ):
            _should_exempt = self._should_exempt_no_benefit_split(agent, context, plan_result)
            if not _should_exempt:
                filtered_subtasks[0].metadata["governance_reason"] = "no_benefit_split"
                plan_result.plan = None
                plan_result.needs_subagents = False
                plan_result.self_execution_steps = plan_result.self_execution_steps or [context.task]
                plan_result.reasoning = (
                    f"[DELEGATION_DOWNGRADED] {plan_result.reasoning or ''} "
                    f"Reason: no_benefit_split - single subagent with no tools/expected_output "
                    f"that duplicates the parent task"
                ).strip()

        return plan_result

    def _should_exempt_no_benefit_split(
        self,
        agent: "Agent",
        context: "AgentContext",
        plan_result: "PlanResult",
    ) -> bool:
        _delegation_keywords = [
            "fullstack", "full_stack", "full stack",
            "app", "application", "system", "project", "platform",
            "developer", "builder", "creator", "generator",
            "模块", "module", "系统", "应用", "项目",
            "前端", "后端", "frontend", "backend", "database",
            "api", "组件", "component", "服务", "service",
        ]
        _task_text = (context.task + " " + (plan_result.reasoning or "")).lower()
        _has_keyword = any(kw in _task_text for kw in _delegation_keywords)

        _agent_config = getattr(getattr(agent, 'config', None), 'get_profile', None)
        _profile_name = _agent_config().name if callable(_agent_config) else None
        _is_root_or_coordinator = _profile_name in ("root", "coordinator") if _profile_name else False

        _is_multi_file = getattr(plan_result, 'estimated_files', 0) >= 2
        _has_modules = getattr(plan_result, 'has_multiple_modules', False)
        _many_tool_types = len(getattr(plan_result, 'required_tool_types', set())) >= 3
        _long_task = len(context.task) > 100

        return (
            _has_keyword
            or _is_root_or_coordinator
            or _is_multi_file
            or _has_modules
            or _many_tool_types
            or _long_task
        )

    def evaluate_requirement(
        self,
        agent: "Agent",
        requirement: "SubAgentRequirement",
        context: "AgentContext",
        task: Task,
        depth: int,
    ) -> GovernanceDecision:
        branch_path = str(task.metadata.get("branch_path") or self.build_branch_path(context, task))
        parent_text = _normalize_text(task.description or context.task)
        child_text = _normalize_text(requirement.task_description)
        fingerprint = self.build_requirement_fingerprint(requirement, branch_path)
        delegation_ctx = getattr(agent, "_delegation_ctx", None)

        if not requirement.delegation_allowed:
            return GovernanceDecision(False, "delegation_disabled", "Delegation disabled by plan.", fingerprint, branch_path)
        if depth > self.config.max_depth:
            return GovernanceDecision(False, "max_depth_reached", "Maximum delegation depth reached.", fingerprint, branch_path)

        if delegation_ctx is not None:
            can_del, reason = delegation_ctx.can_delegate()
            if not can_del:
                return GovernanceDecision(False, reason, f"Delegation budget exhausted: {reason}", fingerprint, branch_path)
            if delegation_ctx.is_duplicate(fingerprint):
                return GovernanceDecision(False, "duplicate_fingerprint", "Delegated task was already attempted in this branch.", fingerprint, branch_path)

        if not child_text:
            return GovernanceDecision(False, "empty_split", "Delegated task description is empty.", fingerprint, branch_path)
        if (
            child_text == parent_text
            and not requirement.required_tools
            and not requirement.expected_output.strip()
        ):
            return GovernanceDecision(False, "empty_split", "Delegated task does not shrink the parent task.", fingerprint, branch_path)

        return GovernanceDecision(True, fingerprint=fingerprint, branch_path=branch_path)

    def reserve_requirement(
        self,
        agent: "Agent",
        decision: GovernanceDecision,
    ) -> None:
        if not decision.allowed:
            return

        delegation_ctx = getattr(agent, "_delegation_ctx", None)
        if delegation_ctx is not None:
            agent._delegation_ctx = delegation_ctx.with_reserved(
                decision.fingerprint, decision.branch_path
            )

    def plan_wave(
        self,
        agent: "Agent",
        tasks: list[Task],
        context: "AgentContext",
        wave_index: int,
    ) -> ExecutionWavePlan:
        wave = ExecutionWavePlan(wave_id=f"wave_{wave_index}")
        if not tasks:
            return wave

        ordered = sorted(tasks, key=lambda task: task.priority.value, reverse=True)
        if not self.config.enable_parallel:
            wave.serial_tasks.extend(ordered)
            return wave

        active_scopes: set[str] = set()
        for task in ordered:
            task.metadata.setdefault("branch_path", self.build_branch_path(context, task))
            parallel_safe = bool(task.metadata.get("parallel_safe", False))
            write_scope = set(task.metadata.get("write_scope") or [])

            if not parallel_safe:
                task.metadata.setdefault("governance_reason", "parallel_disabled")
                wave.serial_tasks.append(task)
                continue

            if len(wave.parallel_tasks) >= self.config.max_parallel_subtasks:
                task.metadata.setdefault("governance_reason", "max_parallel_subtasks_reached")
                wave.serial_tasks.append(task)
                continue

            if write_scope and active_scopes.intersection(write_scope):
                task.metadata.setdefault("governance_reason", "write_scope_conflict")
                wave.serial_tasks.append(task)
                continue

            wave.parallel_tasks.append(task)
            active_scopes.update(write_scope)

        return wave

    def should_replan_after_failure(
        self,
        results: list["AgentResult"],
    ) -> bool:
        return any(not result.success for result in results)


class PlanExecutionEngine:
    """Execute a plan in ready-task waves."""

    def __init__(self, config: PlanConfig, governance: DelegationGovernance):
        self.config = config
        self.governance = governance

    async def execute(
        self,
        agent: "Agent",
        plan: Plan,
        context: "AgentContext",
    ) -> list["AgentResult"]:
        results: list["AgentResult"] = []
        completed: set[str] = set()
        failed: set[str] = set()
        wave_index = 0

        while True:
            ready = plan.get_ready_tasks(completed)
            if not ready:
                break

            wave_index += 1
            wave = self.governance.plan_wave(agent, ready, context, wave_index)
            emit_agent_event(
                EventType.WAVE_STARTED,
                agent,
                message=f"Wave {wave.wave_id} started with {len(wave.parallel_tasks)} parallel, {len(wave.serial_tasks)} serial tasks",
                metadata={
                    "wave_id": wave.wave_id,
                    "parallel_count": len(wave.parallel_tasks),
                    "serial_count": len(wave.serial_tasks),
                    "ready_task_ids": [task.id for task in ready],
                },
            )
            self._log_wave(
                agent,
                plan,
                wave,
                "started",
                {"ready_task_ids": [task.id for task in ready]},
            )
            wave_results: list["AgentResult"] = []

            if wave.parallel_tasks:
                parallel_results = await self._execute_parallel_batch(agent, plan, wave, context)
                wave_results.extend(parallel_results)
                results.extend(parallel_results)

            wave_failed = self.governance.should_replan_after_failure(wave_results)

            if not wave_failed:
                for task in wave.serial_tasks:
                    result = await self._execute_task(agent, plan, task, wave.wave_id, context)
                    wave_results.append(result)
                    results.append(result)
                    if not result.success:
                        wave_failed = True
                        break

            emit_agent_event(
                EventType.WAVE_FINISHED,
                agent,
                message=f"Wave {wave.wave_id} finished: {'failed' if wave_failed else 'success'}",
                metadata={
                    "wave_id": wave.wave_id,
                    "failed": wave_failed,
                    "completed_task_ids": [result.metadata.get("task_id") for result in wave_results],
                    "failed_task_ids": [
                        result.metadata.get("task_id") for result in wave_results if not result.success
                    ],
                },
            )
            self._log_wave(
                agent,
                plan,
                wave,
                "finished",
                {
                    "failed": wave_failed,
                    "completed_task_ids": [result.metadata.get("task_id") for result in wave_results],
                    "failed_task_ids": [
                        result.metadata.get("task_id") for result in wave_results if not result.success
                    ],
                },
            )

            for result in wave_results:
                task_id = result.metadata.get("task_id")
                if not task_id:
                    continue
                if result.success:
                    completed.add(task_id)
                else:
                    failed.add(task_id)

            if wave_failed:
                break

        return results

    async def _execute_parallel_batch(
        self,
        agent: "Agent",
        plan: Plan,
        wave: ExecutionWavePlan,
        context: "AgentContext",
    ) -> list["AgentResult"]:
        if self.config.fail_fast_on_parallel_error:
            return await self._execute_parallel_batch_fail_fast(agent, plan, wave, context)

        semaphore = asyncio.Semaphore(self.config.max_parallel_subtasks)

        async def _run(task: Task) -> "AgentResult":
            async with semaphore:
                return await self._execute_task(agent, plan, task, wave.wave_id, context, True)

        return list(await asyncio.gather(*[_run(task) for task in wave.parallel_tasks]))

    async def _execute_parallel_batch_fail_fast(
        self,
        agent: "Agent",
        plan: Plan,
        wave: ExecutionWavePlan,
        context: "AgentContext",
    ) -> list["AgentResult"]:
        results: list["AgentResult"] = []
        pending_tasks = list(wave.parallel_tasks)
        running: set[asyncio.Task["AgentResult"]] = set()

        def _launch(task: Task) -> asyncio.Task["AgentResult"]:
            return asyncio.create_task(
                self._execute_task(agent, plan, task, wave.wave_id, context, True)
            )

        while pending_tasks and len(running) < self.config.max_parallel_subtasks:
            running.add(_launch(pending_tasks.pop(0)))

        while running:
            done, running = await asyncio.wait(
                running,
                return_when=asyncio.FIRST_COMPLETED,
            )
            stop_launching = False
            for completed_task in done:
                result = await completed_task
                results.append(result)
                if not result.success:
                    stop_launching = True

            if stop_launching:
                break

            while pending_tasks and len(running) < self.config.max_parallel_subtasks:
                running.add(_launch(pending_tasks.pop(0)))

        if running:
            trailing = await asyncio.gather(*running)
            results.extend(trailing)

        return results

    async def _execute_task(
        self,
        agent: "Agent",
        plan: Plan,
        task: Task,
        wave_id: str,
        context: "AgentContext",
        executed_in_parallel: bool = False,
    ) -> "AgentResult":
        task.metadata["parallel_wave"] = wave_id
        plan.update_task_status(task.id, TaskStatus.RUNNING)
        result = await agent._execute_subtask(task, context)
        result.metadata.setdefault("task_id", task.id)
        result.metadata["parallel_wave"] = wave_id
        result.metadata["executed_in_parallel"] = executed_in_parallel
        task.output_data["result"] = result.output
        task.metadata["success"] = result.success

        if result.success:
            plan.update_task_status(task.id, TaskStatus.COMPLETED)
        else:
            task.error = result.error or result.metadata.get("failure_reason") or "Task execution failed"
            task.output_data["error"] = task.error
            task.output_data["child_result_summary"] = result.output[:500]
            task.metadata["failure_reason"] = task.error
            plan.update_task_status(task.id, TaskStatus.FAILED)

        return result

    def _log_wave(
        self,
        agent: "Agent",
        plan: Plan,
        wave: ExecutionWavePlan,
        status: str,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        if not getattr(agent, "_workspace_manager", None) or not getattr(agent, "_workspace_path", None):
            return

        payload = {
            "wave_id": wave.wave_id,
            "status": status,
            "plan_id": plan.id,
            "parallel_task_ids": [task.id for task in wave.parallel_tasks],
            "serial_task_ids": [task.id for task in wave.serial_tasks],
            "parallelism": len(wave.parallel_tasks),
        }
        if extra:
            payload.update(extra)
        agent._workspace_manager.log_execution_wave(agent._workspace_path, payload)
