"""
Bug Condition Exploration Test — Intent Recognition Flow
========================================================

Task 1: 编写 Bug Condition 探索性测试（修复前运行）

**Validates: Requirements 1.1, 1.2, 1.3**

This test encodes the EXPECTED (correct) behavior of `process_user_input`.
It is designed to FAIL on the unfixed `src/fractalclaw/entry/main.py` code,
thereby proving the bug exists.

Bug Condition (isBugCondition):
  "_analyze_intent_with_confirmation" IN call_sequence
  AND "_generate_root_agent" IN call_sequence
  AND "_display_execution_plan" NOT IN call_sequence   ← bug
  AND "_confirm_execution" NOT IN call_sequence        ← bug
  AND "_execute_root_agent" IN call_sequence

Expected counterexample:
  call_sequence = [
      "_analyze_intent_with_confirmation",
      "_create_workspace",
      "_generate_root_agent",
      "_execute_root_agent",   ← jumps straight here, missing the two steps
  ]
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# Ensure src is on the path (mirrors conftest.py)
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
for p in (ROOT, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app():
    """Create a FractalClawApp instance without calling initialize()."""
    from fractalclaw.entry.main import FractalClawApp
    app = FractalClawApp.__new__(FractalClawApp)
    # Minimal attribute setup so process_user_input can run
    app.config_path = ROOT
    app.spinner = MagicMock()
    app.spinner.is_spinning = False
    app.spinner.phase = ""
    app.spinner.current_words = []
    app._conversation_history = []
    app._last_result = None
    app._last_task_text = None
    app._pending_confirmation = False
    app._confirmation_queue = asyncio.Queue()
    app.scheduler = None
    app.provider = None
    app.llm_config = None
    app.config_generator = None
    app.workspace_manager = None
    app.agent_factory = None
    app._current_agent = None
    app.session = None
    return app


def _make_mock_intent_result(requirements=None):
    return {
        "requirements": requirements or ["完成用户任务"],
        "acceptance_criteria": ["任务完成"],
        "raw_output": "mock intent output",
    }


def _make_mock_task():
    task = MagicMock()
    task.id = "mock-task-id"
    task.workspace_path = str(ROOT / "workspace" / "mock-task")
    return task


def _make_mock_agent_config():
    from fractalclaw.agent import AgentConfig, AgentRole
    from fractalclaw.llm import LLMConfig
    return AgentConfig(
        name="RootAgent",
        description="mock task",
        role=AgentRole.ROOT,
        llm_config=LLMConfig(model="gpt-4o-mini", stream=False),
    )


def _make_mock_agent_result(success=True):
    from fractalclaw.agent import AgentResult
    return AgentResult(success=success, output="mock output", error=None)


# ---------------------------------------------------------------------------
# Test 1: Method existence check
# ---------------------------------------------------------------------------

class TestMethodExistence:
    """Assert FractalClawApp has the required methods (will fail on unfixed code)."""

    def test_has_display_execution_plan(self):
        """FractalClawApp MUST have _display_execution_plan attribute.

        Validates: Requirements 1.1, 1.3
        EXPECTED TO FAIL on unfixed code — proves the method is missing.
        """
        from fractalclaw.entry.main import FractalClawApp
        app = _make_app()
        assert hasattr(app, "_display_execution_plan"), (
            "FractalClawApp is missing '_display_execution_plan' method. "
            "This confirms the bug: the method was never ported to src/fractalclaw/entry/main.py."
        )

    def test_has_confirm_execution(self):
        """FractalClawApp MUST have _confirm_execution attribute.

        Validates: Requirements 1.2, 1.3
        EXPECTED TO FAIL on unfixed code — proves the method is missing.
        """
        from fractalclaw.entry.main import FractalClawApp
        app = _make_app()
        assert hasattr(app, "_confirm_execution"), (
            "FractalClawApp is missing '_confirm_execution' method. "
            "This confirms the bug: the method was never ported to src/fractalclaw/entry/main.py."
        )


# ---------------------------------------------------------------------------
# Test 2: Call sequence validation (deterministic)
# ---------------------------------------------------------------------------

class TestCallSequence:
    """Verify the call sequence of process_user_input includes the missing steps."""

    @pytest.mark.asyncio
    @patch("fractalclaw.entry.main.cprint")
    async def test_call_sequence_includes_display_and_confirm(self, mock_cprint):
        """process_user_input call sequence MUST include _display_execution_plan and _confirm_execution.

        Validates: Requirements 1.1, 1.2, 1.3
        EXPECTED TO FAIL on unfixed code — proves the bug condition is triggered.

        Expected counterexample (unfixed code):
            call_sequence = [
                "_analyze_intent_with_confirmation",
                "_create_workspace",
                "_generate_root_agent",
                "_execute_root_agent",   ← missing _display_execution_plan and _confirm_execution
            ]
        """
        app = _make_app()
        call_sequence = []

        intent_result = _make_mock_intent_result(["帮我写一个 Python 脚本"])
        mock_task = _make_mock_task()
        mock_config = _make_mock_agent_config()
        mock_agent_result = _make_mock_agent_result(success=True)
        mock_generation_result = MagicMock()
        mock_generation_result.success = False

        async def mock_analyze_intent_with_confirmation(user_input):
            call_sequence.append("_analyze_intent_with_confirmation")
            return intent_result

        async def mock_create_workspace(intent_result, root_task_text):
            call_sequence.append("_create_workspace")
            return mock_task

        async def mock_generate_root_agent(intent_result, workspace_path, root_task_text):
            call_sequence.append("_generate_root_agent")
            return mock_config, mock_generation_result

        async def mock_execute_root_agent(task_id, config, workspace_path, intent_result, generation_result=None):
            call_sequence.append("_execute_root_agent")
            return mock_agent_result

        app._analyze_intent_with_confirmation = mock_analyze_intent_with_confirmation
        app._create_workspace = mock_create_workspace
        app._generate_root_agent = mock_generate_root_agent
        app._execute_root_agent = mock_execute_root_agent

        def mock_display_execution_plan(workspace_path, requirements):
            call_sequence.append("_display_execution_plan")

        async def mock_confirm_execution():
            call_sequence.append("_confirm_execution")
            return True

        app._display_execution_plan = mock_display_execution_plan
        app._confirm_execution = mock_confirm_execution

        # Run process_user_input
        await app.process_user_input("帮我写一个 Python 脚本")

        # Assert the expected call sequence contains the two missing steps
        assert "_display_execution_plan" in call_sequence, (
            f"BUG CONFIRMED: '_display_execution_plan' not in call sequence.\n"
            f"Actual call sequence: {call_sequence}\n"
            f"Expected sequence should include: "
            f"[..., '_generate_root_agent', '_display_execution_plan', '_confirm_execution', '_execute_root_agent']"
        )
        assert "_confirm_execution" in call_sequence, (
            f"BUG CONFIRMED: '_confirm_execution' not in call sequence.\n"
            f"Actual call sequence: {call_sequence}\n"
            f"Expected sequence should include: "
            f"[..., '_generate_root_agent', '_display_execution_plan', '_confirm_execution', '_execute_root_agent']"
        )

    @pytest.mark.asyncio
    @patch("fractalclaw.entry.main.cprint")
    async def test_display_before_execute(self, mock_cprint):
        """_display_execution_plan MUST appear after _generate_root_agent and before _execute_root_agent.

        Validates: Requirements 1.1, 1.3
        EXPECTED TO FAIL on unfixed code.
        """
        app = _make_app()
        call_sequence = []

        intent_result = _make_mock_intent_result(["删除 temp 目录下所有文件"])
        mock_task = _make_mock_task()
        mock_config = _make_mock_agent_config()
        mock_agent_result = _make_mock_agent_result(success=True)
        mock_generation_result = MagicMock()
        mock_generation_result.success = False

        async def mock_analyze_intent_with_confirmation(user_input):
            call_sequence.append("_analyze_intent_with_confirmation")
            return intent_result

        async def mock_create_workspace(intent_result, root_task_text):
            call_sequence.append("_create_workspace")
            return mock_task

        async def mock_generate_root_agent(intent_result, workspace_path, root_task_text):
            call_sequence.append("_generate_root_agent")
            return mock_config, mock_generation_result

        async def mock_execute_root_agent(task_id, config, workspace_path, intent_result, generation_result=None):
            call_sequence.append("_execute_root_agent")
            return mock_agent_result

        app._analyze_intent_with_confirmation = mock_analyze_intent_with_confirmation
        app._create_workspace = mock_create_workspace
        app._generate_root_agent = mock_generate_root_agent
        app._execute_root_agent = mock_execute_root_agent

        def mock_display_execution_plan(workspace_path, requirements):
            call_sequence.append("_display_execution_plan")

        async def mock_confirm_execution():
            call_sequence.append("_confirm_execution")
            return True

        app._display_execution_plan = mock_display_execution_plan
        app._confirm_execution = mock_confirm_execution

        await app.process_user_input("删除 temp 目录下所有文件")

        assert "_display_execution_plan" in call_sequence, (
            f"BUG CONFIRMED: '_display_execution_plan' missing from call sequence: {call_sequence}"
        )

        gen_idx = call_sequence.index("_generate_root_agent")
        exec_idx = call_sequence.index("_execute_root_agent")
        display_idx = call_sequence.index("_display_execution_plan")

        assert gen_idx < display_idx < exec_idx, (
            f"BUG CONFIRMED: '_display_execution_plan' not in correct position.\n"
            f"Expected: _generate_root_agent({gen_idx}) < _display_execution_plan({display_idx}) < _execute_root_agent({exec_idx})\n"
            f"Actual call sequence: {call_sequence}"
        )

    @pytest.mark.asyncio
    @patch("fractalclaw.entry.main.cprint")
    async def test_confirm_between_display_and_execute(self, mock_cprint):
        """_confirm_execution MUST appear after _display_execution_plan and before _execute_root_agent.

        Validates: Requirements 1.2, 1.3
        EXPECTED TO FAIL on unfixed code.
        """
        app = _make_app()
        call_sequence = []

        intent_result = _make_mock_intent_result(["用户输入包含多条需求", "需求二", "需求三"])
        mock_task = _make_mock_task()
        mock_config = _make_mock_agent_config()
        mock_agent_result = _make_mock_agent_result(success=True)
        mock_generation_result = MagicMock()
        mock_generation_result.success = False

        async def mock_analyze_intent_with_confirmation(user_input):
            call_sequence.append("_analyze_intent_with_confirmation")
            return intent_result

        async def mock_create_workspace(intent_result, root_task_text):
            call_sequence.append("_create_workspace")
            return mock_task

        async def mock_generate_root_agent(intent_result, workspace_path, root_task_text):
            call_sequence.append("_generate_root_agent")
            return mock_config, mock_generation_result

        async def mock_execute_root_agent(task_id, config, workspace_path, intent_result, generation_result=None):
            call_sequence.append("_execute_root_agent")
            return mock_agent_result

        app._analyze_intent_with_confirmation = mock_analyze_intent_with_confirmation
        app._create_workspace = mock_create_workspace
        app._generate_root_agent = mock_generate_root_agent
        app._execute_root_agent = mock_execute_root_agent

        def mock_display_execution_plan(workspace_path, requirements):
            call_sequence.append("_display_execution_plan")

        async def mock_confirm_execution():
            call_sequence.append("_confirm_execution")
            return True

        app._display_execution_plan = mock_display_execution_plan
        app._confirm_execution = mock_confirm_execution

        await app.process_user_input("用户输入包含多条需求")

        assert "_confirm_execution" in call_sequence, (
            f"BUG CONFIRMED: '_confirm_execution' missing from call sequence: {call_sequence}"
        )
        assert "_display_execution_plan" in call_sequence, (
            f"BUG CONFIRMED: '_display_execution_plan' missing from call sequence: {call_sequence}"
        )

        display_idx = call_sequence.index("_display_execution_plan")
        confirm_idx = call_sequence.index("_confirm_execution")
        exec_idx = call_sequence.index("_execute_root_agent")

        assert display_idx < confirm_idx < exec_idx, (
            f"BUG CONFIRMED: '_confirm_execution' not in correct position.\n"
            f"Expected: _display_execution_plan({display_idx}) < _confirm_execution({confirm_idx}) < _execute_root_agent({exec_idx})\n"
            f"Actual call sequence: {call_sequence}"
        )

    @pytest.mark.asyncio
    @patch("fractalclaw.entry.main.cprint")
    async def test_cancel_prevents_execute(self, mock_cprint):
        """When _confirm_execution returns False, _execute_root_agent MUST NOT be called.

        Validates: Requirements 1.2, 1.3
        EXPECTED TO FAIL on unfixed code — _confirm_execution doesn't exist, so it can't return False.
        """
        app = _make_app()
        call_sequence = []

        intent_result = _make_mock_intent_result(["危险操作：删除所有文件"])
        mock_task = _make_mock_task()
        mock_config = _make_mock_agent_config()
        mock_agent_result = _make_mock_agent_result(success=True)
        mock_generation_result = MagicMock()
        mock_generation_result.success = False

        async def mock_analyze_intent_with_confirmation(user_input):
            call_sequence.append("_analyze_intent_with_confirmation")
            return intent_result

        async def mock_create_workspace(intent_result, root_task_text):
            call_sequence.append("_create_workspace")
            return mock_task

        async def mock_generate_root_agent(intent_result, workspace_path, root_task_text):
            call_sequence.append("_generate_root_agent")
            return mock_config, mock_generation_result

        def mock_display_execution_plan(workspace_path, requirements):
            call_sequence.append("_display_execution_plan")

        async def mock_confirm_execution():
            call_sequence.append("_confirm_execution")
            return False

        async def mock_execute_root_agent(task_id, config, workspace_path, intent_result, generation_result=None):
            call_sequence.append("_execute_root_agent")
            return mock_agent_result

        app._analyze_intent_with_confirmation = mock_analyze_intent_with_confirmation
        app._create_workspace = mock_create_workspace
        app._generate_root_agent = mock_generate_root_agent
        app._display_execution_plan = mock_display_execution_plan
        app._confirm_execution = mock_confirm_execution
        app._execute_root_agent = mock_execute_root_agent

        from fractalclaw.agent import AgentResult
        result = await app.process_user_input("危险操作：删除所有文件")

        # _confirm_execution must have been called
        assert "_confirm_execution" in call_sequence, (
            f"BUG CONFIRMED: '_confirm_execution' was never called.\n"
            f"Actual call sequence: {call_sequence}"
        )

        # When user cancels, _execute_root_agent must NOT be called
        assert "_execute_root_agent" not in call_sequence, (
            f"BUG CONFIRMED: '_execute_root_agent' was called even though user cancelled.\n"
            f"Actual call sequence: {call_sequence}"
        )

        # Result should indicate cancellation
        assert result.success is False, (
            f"BUG CONFIRMED: result.success should be False when user cancels, got {result.success}"
        )
        assert result.error == "User cancelled execution", (
            f"BUG CONFIRMED: result.error should be 'User cancelled execution', got {result.error!r}"
        )


# ---------------------------------------------------------------------------
# Test 3: Property-Based Test — Scoped PBT
# ---------------------------------------------------------------------------

class TestBugConditionProperty:
    """
    Property-Based Test: Bug Condition Exploration

    Scoped PBT Approach:
    For any user input that passes intent confirmation, the actual call sequence
    of process_user_input does NOT contain _display_execution_plan and _confirm_execution.

    This property encodes the EXPECTED behavior (they SHOULD be in the sequence).
    On unfixed code, hypothesis will find that the property is violated for every input.

    **Validates: Requirements 1.1, 1.2, 1.3**
    """

    @given(
        user_input=st.text(
            alphabet=st.characters(blacklist_categories=("Cs",)),
            min_size=1,
            max_size=100,
        ).filter(lambda s: s.strip()),
        requirements=st.lists(
            st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
            min_size=1,
            max_size=5,
        ),
    )
    @settings(
        max_examples=5,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_property_call_sequence_contains_display_and_confirm(
        self, user_input: str, requirements: list[str]
    ):
        """
        Property: For any user input that passes intent confirmation,
        process_user_input's call sequence MUST contain both
        '_display_execution_plan' and '_confirm_execution'.

        **Validates: Requirements 1.1, 1.2, 1.3**

        EXPECTED TO FAIL on unfixed code — the call sequence will be:
            [_analyze_intent_with_confirmation, _create_workspace,
             _generate_root_agent, _execute_root_agent]
        missing _display_execution_plan and _confirm_execution.
        """
        asyncio.run(self._run_property(user_input, requirements))

    async def _run_property(self, user_input: str, requirements: list[str]):
        with patch("fractalclaw.entry.main.cprint"):
            app = _make_app()
            call_sequence = []

            intent_result = _make_mock_intent_result(requirements)
            mock_task = _make_mock_task()
            mock_config = _make_mock_agent_config()
            mock_agent_result = _make_mock_agent_result(success=True)
            mock_generation_result = MagicMock()
            mock_generation_result.success = False

            async def mock_analyze_intent_with_confirmation(inp):
                call_sequence.append("_analyze_intent_with_confirmation")
                return intent_result

            async def mock_create_workspace(ir, rtt):
                call_sequence.append("_create_workspace")
                return mock_task

            async def mock_generate_root_agent(ir, wp, rtt):
                call_sequence.append("_generate_root_agent")
                return mock_config, mock_generation_result

            async def mock_execute_root_agent(task_id, config, wp, ir, generation_result=None):
                call_sequence.append("_execute_root_agent")
                return mock_agent_result

            app._analyze_intent_with_confirmation = mock_analyze_intent_with_confirmation
            app._create_workspace = mock_create_workspace
            app._generate_root_agent = mock_generate_root_agent
            app._execute_root_agent = mock_execute_root_agent

            def mock_display_execution_plan(workspace_path, requirements):
                call_sequence.append("_display_execution_plan")

            async def mock_confirm_execution():
                call_sequence.append("_confirm_execution")
                return True

            app._display_execution_plan = mock_display_execution_plan
            app._confirm_execution = mock_confirm_execution

            await app.process_user_input(user_input)

            assert "_display_execution_plan" in call_sequence, (
                f"COUNTEREXAMPLE FOUND — BUG CONFIRMED\n"
                f"Input: {user_input!r}\n"
                f"Requirements: {requirements}\n"
                f"Actual call sequence: {call_sequence}\n"
                f"'_display_execution_plan' is missing from the call sequence.\n"
                f"This is the bug: process_user_input skips the execution plan display step."
            )
            assert "_confirm_execution" in call_sequence, (
                f"COUNTEREXAMPLE FOUND — BUG CONFIRMED\n"
                f"Input: {user_input!r}\n"
                f"Requirements: {requirements}\n"
                f"Actual call sequence: {call_sequence}\n"
                f"'_confirm_execution' is missing from the call sequence.\n"
                f"This is the bug: process_user_input skips the execution confirmation step."
            )
