"""Recursive governance and wave-based plan execution helpers."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

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
            return plan_result

        if (
            len(unique_requirements) == 1
            and len(filtered_subtasks) == 1
            and not unique_requirements[0].required_tools
            and not unique_requirements[0].expected_output.strip()
            and _normalize_text(unique_requirements[0].task_description) == _normalize_text(context.task)
        ):
            filtered_subtasks[0].metadata["governance_reason"] = "no_benefit_split"
            plan_result.plan = None
            plan_result.needs_subagents = False
            plan_result.self_execution_steps = plan_result.self_execution_steps or [context.task]

        return plan_result

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
        runtime = getattr(agent, "_delegation_runtime", {})

        if not requirement.delegation_allowed:
            return GovernanceDecision(False, "delegation_disabled", "Delegation disabled by plan.", fingerprint, branch_path)
        if depth > self.config.max_depth:
            return GovernanceDecision(False, "max_depth_reached", "Maximum delegation depth reached.", fingerprint, branch_path)
        if runtime.get("delegation_count", 0) >= self.config.max_total_delegations:
            return GovernanceDecision(False, "max_total_delegations_reached", "Maximum total delegations reached.", fingerprint, branch_path)
        if runtime.get("branch_delegation_counts", {}).get(branch_path, 0) >= self.config.max_branch_delegations:
            return GovernanceDecision(False, "max_branch_delegations_reached", "Maximum branch delegations reached.", fingerprint, branch_path)
        if not child_text:
            return GovernanceDecision(False, "empty_split", "Delegated task description is empty.", fingerprint, branch_path)
        if (
            child_text == parent_text
            and not requirement.required_tools
            and not requirement.expected_output.strip()
        ):
            return GovernanceDecision(False, "empty_split", "Delegated task does not shrink the parent task.", fingerprint, branch_path)
        if fingerprint in runtime.get("fingerprints", set()):
            return GovernanceDecision(False, "duplicate_fingerprint", "Delegated task was already attempted in this branch.", fingerprint, branch_path)

        return GovernanceDecision(True, fingerprint=fingerprint, branch_path=branch_path)

    def reserve_requirement(
        self,
        agent: "Agent",
        decision: GovernanceDecision,
    ) -> None:
        if not decision.allowed:
            return

        runtime = getattr(agent, "_delegation_runtime", None)
        if runtime is None:
            runtime = {
                "fingerprints": set(),
                "delegation_count": 0,
                "branch_delegation_counts": {},
                "governance_rejections": 0,
            }
            agent._delegation_runtime = runtime

        runtime["fingerprints"].add(decision.fingerprint)
        runtime["delegation_count"] += 1
        runtime["branch_delegation_counts"][decision.branch_path] = (
            runtime["branch_delegation_counts"].get(decision.branch_path, 0) + 1
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
