"""
Bug Condition Exploration Test — Agent Output Aggregation
=========================================================

Task 5.1: 探索性测试（验证缺陷存在）

**Validates: Requirements 1.1, 1.2, 1.3 (bugfix.md)**

Bug Condition (isBugCondition):
  "subtask_results = await self._execute_plan(context)" IN execution_flow
  AND "result = AgentResult(...)" IN execution_flow
  AND "_aggregate_child_outputs" NOT IN execution_flow

This test is designed to FAIL on unfixed code (before _aggregate_child_outputs
was added), thereby proving the bug exists.
On fixed code, all tests should PASS.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as st
    _HYPOTHESIS_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    _HYPOTHESIS_AVAILABLE = False
    # Provide stubs so the file still imports cleanly
    def given(*a, **kw):
        return lambda f: pytest.mark.skip(reason="hypothesis unavailable")(f)
    def settings(*a, **kw):
        return lambda f: f
    class HealthCheck:
        too_slow = None
        function_scoped_fixture = None
    class st:
        @staticmethod
        def lists(*a, **kw): return None
        @staticmethod
        def fixed_dictionaries(*a, **kw): return None
        @staticmethod
        def text(*a, **kw): return None
        @staticmethod
        def one_of(*a, **kw): return None
        @staticmethod
        def just(*a, **kw): return None
        @staticmethod
        def dictionaries(*a, **kw): return None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent_config(name: str = "TestAgent", role: str = "root"):
    from fractalclaw.agent.base import AgentConfig, AgentRole
    from fractalclaw.llm import LLMConfig
    return AgentConfig(
        name=name,
        description="test agent",
        role=AgentRole(role),
        llm_config=LLMConfig(model="gpt-4o-mini", stream=False),
        enable_planning=False,
        enable_reflection=False,
    )


def _make_base_agent(name: str = "ParentAgent", role: str = "root") -> "BaseAgent":
    """Create a BaseAgent without LLM/memory/tools initialization."""
    from fractalclaw.agent.base import BaseAgent
    from fractalclaw.llm import LLMEngine, LLMConfig
    from fractalclaw.memory import MemoryManager, MemoryConfig
    from fractalclaw.tools import ToolManager, ToolConfig
    from fractalclaw.plan import PlanManager, PlanConfig

    config = _make_agent_config(name, role)
    agent = BaseAgent.__new__(BaseAgent)
    agent.config = config
    agent._id = f"agent_{name.lower()}"
    from fractalclaw.agent.base import AgentState
    agent._state = AgentState.IDLE
    agent._iteration = 0
    agent._current_plan = None
    agent._last_plan_result = None
    agent._workspace_path = None
    agent._workspace_manager = None
    agent._factory = None
    agent._llm = MagicMock()
    agent._memory = MagicMock()
    agent._memory.initialize = AsyncMock()
    agent._memory.start_session = AsyncMock()
    agent._memory.end_session = AsyncMock()
    agent._memory.add = AsyncMock()
    agent._memory.sharing = None
    agent._tools = MagicMock()
    agent._tools.list_tools = MagicMock(return_value=[])
    agent._tools.get_tool_schemas = MagicMock(return_value=[])
    agent._planner = MagicMock()
    agent._planner.config = MagicMock()
    agent._planner.config.max_depth = 5
    from fractalclaw.agent.tree import AgentTree
    agent._tree = AgentTree(agent)
    agent._delegation_runtime = {
        "fingerprints": set(),
        "delegation_count": 0,
        "branch_delegation_counts": {},
        "governance_rejections": 0,
    }
    from fractalclaw.agent.execution import DelegationGovernance, PlanExecutionEngine
    from fractalclaw.plan import PlanConfig
    plan_config = PlanConfig()
    agent._governance = DelegationGovernance(plan_config)
    agent._plan_executor = PlanExecutionEngine(plan_config, agent._governance)
    agent._max_replan_attempts = 3
    agent._replan_count = 0
    return agent


def _make_child_agent_with_workspace(
    name: str,
    workspace_root: Path,
    files: dict[str, str],
) -> "BaseAgent":
    """Create a child agent with a workspace containing specified files."""
    child = _make_base_agent(name, "worker")
    child_ws = workspace_root / f"agents/agent_{name}"
    child_ws.mkdir(parents=True, exist_ok=True)
    child._workspace_path = child_ws

    # Write project files
    for rel_path, content in files.items():
        file_path = child_ws / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    # Write framework internal files (should be excluded from aggregation)
    (child_ws / "agent_config.yaml").write_text("name: test", encoding="utf-8")
    (child_ws / "runtime_agent.yaml").write_text("role: worker", encoding="utf-8")
    (child_ws / "execution.log").write_text("log content", encoding="utf-8")
    (child_ws / "memory").mkdir(exist_ok=True)
    (child_ws / "memory" / "INDEX.md").write_text("# Memory Index", encoding="utf-8")
    (child_ws / "output").mkdir(exist_ok=True)

    return child


# ---------------------------------------------------------------------------
# Test 1: Method existence check (bug condition exploration)
# ---------------------------------------------------------------------------

class TestMethodExistence:
    """Assert BaseAgent has the required aggregation methods."""

    def test_has_aggregate_child_outputs(self):
        """BaseAgent MUST have _aggregate_child_outputs method.

        EXPECTED TO FAIL on unfixed code — proves the method is missing.
        Validates: Requirements 1.1, 1.2 (bugfix.md)
        """
        from fractalclaw.agent.base import BaseAgent
        agent = _make_base_agent()
        assert hasattr(agent, "_aggregate_child_outputs"), (
            "BaseAgent is missing '_aggregate_child_outputs' method. "
            "This confirms the bug: child agent file outputs are never aggregated."
        )

    def test_has_write_aggregation_report(self):
        """BaseAgent MUST have _write_aggregation_report method.

        EXPECTED TO FAIL on unfixed code.
        Validates: Requirement 2.5 (bugfix.md)
        """
        from fractalclaw.agent.base import BaseAgent
        agent = _make_base_agent()
        assert hasattr(agent, "_write_aggregation_report"), (
            "BaseAgent is missing '_write_aggregation_report' method."
        )

    def test_has_resolve_file_conflict(self):
        """BaseAgent MUST have _resolve_file_conflict method.

        EXPECTED TO FAIL on unfixed code.
        Validates: Requirement 2.3 (bugfix.md)
        """
        from fractalclaw.agent.base import BaseAgent
        agent = _make_base_agent()
        assert hasattr(agent, "_resolve_file_conflict"), (
            "BaseAgent is missing '_resolve_file_conflict' method."
        )

    def test_framework_exclude_constants_exist(self):
        """Framework exclude constants MUST be defined in base module.

        EXPECTED TO FAIL on unfixed code.
        """
        import fractalclaw.agent.base as base_module
        assert hasattr(base_module, "_FRAMEWORK_EXCLUDE_DIRS"), (
            "base module is missing '_FRAMEWORK_EXCLUDE_DIRS' constant."
        )
        assert hasattr(base_module, "_FRAMEWORK_EXCLUDE_FILES"), (
            "base module is missing '_FRAMEWORK_EXCLUDE_FILES' constant."
        )
        assert hasattr(base_module, "_FRAMEWORK_EXCLUDE_EXTENSIONS"), (
            "base module is missing '_FRAMEWORK_EXCLUDE_EXTENSIONS' constant."
        )


# ---------------------------------------------------------------------------
# Test 2: _aggregate_child_outputs unit tests
# ---------------------------------------------------------------------------

class TestAggregateChildOutputs:
    """Unit tests for _aggregate_child_outputs method."""

    @pytest.mark.asyncio
    async def test_returns_empty_report_when_no_workspace(self):
        """Returns empty report when workspace_path is None.

        Validates: Requirement 1.2 (bugfix.md) — preservation of no-op behavior
        """
        agent = _make_base_agent()
        agent._workspace_path = None

        from fractalclaw.agent.base import AgentContext
        ctx = AgentContext(task="test task")
        report = await agent._aggregate_child_outputs([], ctx)

        assert report["aggregated_files"] == []
        assert report["conflicts"] == []
        assert report["skipped_files"] == []
        assert report["summary"]["total_aggregated"] == 0

    @pytest.mark.asyncio
    async def test_returns_empty_report_when_no_children(self):
        """Returns empty report when agent has no children.

        Validates: Requirement 1.1 (bugfix.md)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = _make_base_agent()
            agent._workspace_path = Path(tmpdir)
            agent._workspace_manager = MagicMock()

            from fractalclaw.agent.base import AgentContext
            ctx = AgentContext(task="test task")
            report = await agent._aggregate_child_outputs([], ctx)

            assert report["aggregated_files"] == []
            assert report["summary"]["total_aggregated"] == 0

    @pytest.mark.asyncio
    async def test_copies_project_files_from_child(self):
        """Project files from child workspace are copied to parent workspace.

        Validates: Requirements 2.1, 2.2, 2.4 (bugfix.md)
        EXPECTED TO FAIL on unfixed code — _aggregate_child_outputs doesn't exist.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            parent_ws = Path(tmpdir) / "parent"
            parent_ws.mkdir()

            agent = _make_base_agent("ParentAgent")
            agent._workspace_path = parent_ws
            agent._workspace_manager = MagicMock()

            # Create child agent with project files
            child = _make_child_agent_with_workspace(
                "BackendDev",
                parent_ws,
                {
                    "backend/main.py": "from fastapi import FastAPI\napp = FastAPI()",
                    "backend/models.py": "from pydantic import BaseModel",
                    "backend/requirements.txt": "fastapi\nuvicorn",
                },
            )
            agent._tree.add_child(child)

            from fractalclaw.agent.base import AgentContext
            ctx = AgentContext(task="build backend")
            report = await agent._aggregate_child_outputs([], ctx)

            # Project files should be copied to parent workspace
            assert (parent_ws / "backend" / "main.py").exists(), (
                "BUG CONFIRMED: backend/main.py was not aggregated to parent workspace.\n"
                f"Report: {report}"
            )
            assert (parent_ws / "backend" / "models.py").exists(), (
                "BUG CONFIRMED: backend/models.py was not aggregated to parent workspace."
            )
            assert (parent_ws / "backend" / "requirements.txt").exists(), (
                "BUG CONFIRMED: backend/requirements.txt was not aggregated to parent workspace."
            )

            # Aggregation report should record the files
            assert report["summary"]["total_aggregated"] >= 3, (
                f"Expected at least 3 aggregated files, got {report['summary']['total_aggregated']}"
            )

    @pytest.mark.asyncio
    async def test_excludes_framework_internal_files(self):
        """Framework internal files are NOT copied to parent workspace.

        Validates: Requirement 1.4 (tasks.md) — framework file filtering
        EXPECTED TO FAIL on unfixed code.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            parent_ws = Path(tmpdir) / "parent"
            parent_ws.mkdir()

            agent = _make_base_agent("ParentAgent")
            agent._workspace_path = parent_ws
            agent._workspace_manager = MagicMock()

            child = _make_child_agent_with_workspace(
                "WorkerAgent",
                parent_ws,
                {"src/app.py": "print('hello')"},
            )
            agent._tree.add_child(child)

            from fractalclaw.agent.base import AgentContext
            ctx = AgentContext(task="test")
            await agent._aggregate_child_outputs([], ctx)

            # Framework internal files must NOT be in parent workspace
            assert not (parent_ws / "agent_config.yaml").exists(), (
                "agent_config.yaml should NOT be aggregated (framework internal file)"
            )
            assert not (parent_ws / "runtime_agent.yaml").exists(), (
                "runtime_agent.yaml should NOT be aggregated (framework internal file)"
            )
            assert not (parent_ws / "execution.log").exists(), (
                "execution.log should NOT be aggregated (framework internal file)"
            )
            assert not (parent_ws / "memory").exists(), (
                "memory/ directory should NOT be aggregated (framework internal dir)"
            )

    @pytest.mark.asyncio
    async def test_aggregates_multiple_children(self):
        """Files from multiple child agents are all aggregated.

        Validates: Requirements 2.1, 2.4 (bugfix.md)
        EXPECTED TO FAIL on unfixed code.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            parent_ws = Path(tmpdir) / "parent"
            parent_ws.mkdir()

            agent = _make_base_agent("RootAgent")
            agent._workspace_path = parent_ws
            agent._workspace_manager = MagicMock()

            # Frontend child
            frontend_child = _make_child_agent_with_workspace(
                "FrontendDev",
                parent_ws,
                {
                    "frontend/src/App.js": "export default function App() {}",
                    "frontend/package.json": '{"dependencies": {"react": "^18.0.0"}}',
                },
            )
            # Backend child
            backend_child = _make_child_agent_with_workspace(
                "BackendDev",
                parent_ws,
                {
                    "backend/main.py": "from fastapi import FastAPI",
                    "backend/requirements.txt": "fastapi\nuvicorn",
                },
            )
            agent._tree.add_child(frontend_child)
            agent._tree.add_child(backend_child)

            from fractalclaw.agent.base import AgentContext
            ctx = AgentContext(task="build fullstack app")
            report = await agent._aggregate_child_outputs([], ctx)

            # Both frontend and backend files should be in parent workspace
            assert (parent_ws / "frontend" / "src" / "App.js").exists(), (
                "BUG CONFIRMED: frontend/src/App.js not aggregated from FrontendDev child"
            )
            assert (parent_ws / "backend" / "main.py").exists(), (
                "BUG CONFIRMED: backend/main.py not aggregated from BackendDev child"
            )
            assert report["summary"]["total_aggregated"] >= 4


# ---------------------------------------------------------------------------
# Test 3: File conflict handling
# ---------------------------------------------------------------------------

class TestFileConflictHandling:
    """Tests for _resolve_file_conflict method."""

    def test_requirements_txt_merge(self):
        """requirements.txt from multiple agents are merged and deduplicated.

        Validates: Requirement 2.1 (tasks.md)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            agent = _make_base_agent()

            # Existing requirements.txt
            dst = tmpdir / "requirements.txt"
            dst.write_text("fastapi\nuvicorn\npydantic\n", encoding="utf-8")

            # Incoming requirements.txt with overlap
            src = tmpdir / "src_requirements.txt"
            src.write_text("fastapi\nsqlalchemy\naiohttp\n", encoding="utf-8")

            report = {"conflicts": [], "aggregated_files": [], "skipped_files": []}
            result = agent._resolve_file_conflict(src, dst, Path("requirements.txt"), "BackendDev", report)

            assert result is True
            merged_content = dst.read_text(encoding="utf-8")
            merged_lines = [l for l in merged_content.splitlines() if l.strip()]

            # All unique deps should be present
            assert "fastapi" in merged_lines
            assert "uvicorn" in merged_lines
            assert "pydantic" in merged_lines
            assert "sqlalchemy" in merged_lines
            assert "aiohttp" in merged_lines

            # No duplicates
            assert len(merged_lines) == len(set(merged_lines)), (
                f"Duplicate lines found in merged requirements.txt: {merged_lines}"
            )

            # Conflict recorded
            assert len(report["conflicts"]) == 1
            assert report["conflicts"][0]["resolution"] == "merged_requirements"

    def test_package_json_merge(self):
        """package.json dependencies from multiple agents are merged.

        Validates: Requirement 2.2 (tasks.md)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            agent = _make_base_agent()

            existing = {
                "name": "todo-app",
                "dependencies": {"react": "^18.0.0", "axios": "^1.0.0"},
                "devDependencies": {"jest": "^29.0.0"},
            }
            dst = tmpdir / "package.json"
            dst.write_text(json.dumps(existing, indent=2), encoding="utf-8")

            incoming = {
                "name": "todo-app",
                "dependencies": {"react-router-dom": "^6.0.0", "axios": "^1.5.0"},
                "devDependencies": {"eslint": "^8.0.0"},
            }
            src = tmpdir / "src_package.json"
            src.write_text(json.dumps(incoming, indent=2), encoding="utf-8")

            report = {"conflicts": [], "aggregated_files": [], "skipped_files": []}
            result = agent._resolve_file_conflict(src, dst, Path("package.json"), "FrontendDev", report)

            assert result is True
            merged = json.loads(dst.read_text(encoding="utf-8"))

            # All dependencies should be present
            assert "react" in merged["dependencies"]
            assert "axios" in merged["dependencies"]
            assert "react-router-dom" in merged["dependencies"]
            assert "jest" in merged["devDependencies"]
            assert "eslint" in merged["devDependencies"]

            # Conflict recorded
            assert len(report["conflicts"]) == 1
            assert report["conflicts"][0]["resolution"] == "merged_package_json"

    def test_generic_conflict_keeps_newest(self):
        """Generic file conflict keeps the newest version.

        Validates: Requirement 2.3 (tasks.md)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            agent = _make_base_agent()

            dst = tmpdir / "main.py"
            dst.write_text("# old version", encoding="utf-8")

            src = tmpdir / "src_main.py"
            src.write_text("# new version", encoding="utf-8")

            # Make src newer than dst
            import time
            time.sleep(0.01)
            src.touch()

            report = {"conflicts": [], "aggregated_files": [], "skipped_files": []}
            result = agent._resolve_file_conflict(src, dst, Path("main.py"), "BackendDev", report)

            assert result is True
            # Newer file (src) should win
            assert dst.read_text(encoding="utf-8") == "# new version"
            assert report["conflicts"][0]["resolution"] == "kept_newest_incoming"


# ---------------------------------------------------------------------------
# Test 4: _write_aggregation_report
# ---------------------------------------------------------------------------

class TestWriteAggregationReport:
    """Tests for _write_aggregation_report method."""

    def test_writes_report_to_output_dir(self):
        """Aggregation report is written to output/aggregation_report.json.

        Validates: Requirement 2.5 (bugfix.md)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = _make_base_agent()
            agent._workspace_path = Path(tmpdir)

            report = {
                "timestamp": "2026-05-05T14:00:00",
                "parent_workspace": tmpdir,
                "aggregated_files": [
                    {"source": "agents/child/backend/main.py", "destination": "backend/main.py",
                     "source_agent": "BackendDev", "action": "copied"}
                ],
                "conflicts": [],
                "skipped_files": [],
                "summary": {"total_aggregated": 1, "total_conflicts": 0, "total_skipped": 0},
            }

            agent._write_aggregation_report(report)

            report_path = Path(tmpdir) / "output" / "aggregation_report.json"
            assert report_path.exists(), (
                f"aggregation_report.json not found at {report_path}"
            )

            written = json.loads(report_path.read_text(encoding="utf-8"))
            assert written["summary"]["total_aggregated"] == 1
            assert len(written["aggregated_files"]) == 1
            assert written["aggregated_files"][0]["source_agent"] == "BackendDev"

    def test_does_not_raise_when_workspace_is_none(self):
        """_write_aggregation_report does not raise when workspace_path is None."""
        agent = _make_base_agent()
        agent._workspace_path = None
        # Should not raise
        agent._write_aggregation_report({"summary": {}})


# ---------------------------------------------------------------------------
# Test 5: Preservation — self-execution path unaffected
# ---------------------------------------------------------------------------

class TestPreservation:
    """Verify that the self-execution path is not affected by the fix.

    Validates: Requirements 3.4, 3.5 (bugfix.md)
    """

    @pytest.mark.asyncio
    async def test_self_execution_does_not_trigger_aggregation(self):
        """When needs_subagents=False, _aggregate_child_outputs is NOT called.

        Validates: Requirements 3.4, 3.5 (bugfix.md)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = _make_base_agent()
            agent._workspace_path = Path(tmpdir)
            agent._workspace_manager = MagicMock()

            aggregate_called = []

            original_aggregate = agent._aggregate_child_outputs

            async def spy_aggregate(subtask_results, context):
                aggregate_called.append(True)
                return await original_aggregate(subtask_results, context)

            agent._aggregate_child_outputs = spy_aggregate

            # Mock _plan to return needs_subagents=False
            from fractalclaw.agent.base import PlanResult, AgentContext
            from fractalclaw.common.types import TaskComplexity

            async def mock_plan(context):
                return PlanResult(
                    complexity=TaskComplexity.SIMPLE,
                    needs_subagents=False,
                    self_execution_steps=["do the task"],
                )

            agent._plan = mock_plan

            # Mock _execute_self to return a result
            from fractalclaw.agent.base import AgentResult

            async def mock_execute_self(plan_result, context, tool_history):
                return AgentResult(success=True, output="self executed")

            agent._execute_self = mock_execute_self

            # Mock _evaluate_execution to return success
            async def mock_evaluate(result, context):
                return True, "goal achieved"

            agent._evaluate_execution = mock_evaluate

            ctx = AgentContext(task="simple task")
            result = await agent.run(ctx)

            assert result.success is True
            assert aggregate_called == [], (
                "BUG: _aggregate_child_outputs was called during self-execution path. "
                "It should only be called when needs_subagents=True."
            )


# ---------------------------------------------------------------------------
# Test 6: Property-Based Test — aggregation completeness
# ---------------------------------------------------------------------------

class TestAggregationProperty:
    """
    Property-Based Test: For any set of child agents with project files,
    all project files appear in the parent workspace after aggregation.

    Validates: Requirements 2.1, 2.2, 2.4 (bugfix.md)
    """

    @given(
        file_sets=st.lists(
            st.fixed_dictionaries({
                "agent_name": st.text(
                    alphabet="abcdefghijklmnopqrstuvwxyz",
                    min_size=3,
                    max_size=10,
                ),
                "files": st.dictionaries(
                    keys=st.one_of(
                        st.just("backend/main.py"),
                        st.just("backend/models.py"),
                        st.just("frontend/src/App.js"),
                        st.just("frontend/package.json"),
                        st.just("src/utils.py"),
                    ),
                    values=st.text(min_size=1, max_size=50),
                    min_size=1,
                    max_size=3,
                ),
            }),
            min_size=1,
            max_size=3,
        )
    )
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_all_project_files_aggregated(self, file_sets: list[dict]):
        """
        Property: For any set of child agents with project files,
        all project files appear in the parent workspace after aggregation.

        EXPECTED TO FAIL on unfixed code.
        """
        asyncio.run(self._run_property(file_sets))

    async def _run_property(self, file_sets: list[dict]):
        with tempfile.TemporaryDirectory() as tmpdir:
            parent_ws = Path(tmpdir) / "parent"
            parent_ws.mkdir()

            agent = _make_base_agent("RootAgent")
            agent._workspace_path = parent_ws
            agent._workspace_manager = MagicMock()

            # Track all expected files (excluding conflicts — last writer wins)
            expected_files: set[str] = set()

            for fs in file_sets:
                child = _make_child_agent_with_workspace(
                    fs["agent_name"],
                    parent_ws,
                    fs["files"],
                )
                agent._tree.add_child(child)
                for rel_path in fs["files"]:
                    expected_files.add(rel_path)

            from fractalclaw.agent.base import AgentContext
            ctx = AgentContext(task="build project")
            report = await agent._aggregate_child_outputs([], ctx)

            # Every expected project file should exist in parent workspace
            for rel_path in expected_files:
                assert (parent_ws / rel_path).exists(), (
                    f"COUNTEREXAMPLE FOUND — BUG CONFIRMED\n"
                    f"File '{rel_path}' was NOT aggregated to parent workspace.\n"
                    f"file_sets: {file_sets}\n"
                    f"Report: {report}"
                )
