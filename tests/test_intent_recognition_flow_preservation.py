"""
Preservation Property Tests — Intent Recognition Flow
======================================================

Task 2: 编写保留性属性测试（修复前运行，验证基线行为）

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

Property 2: Preservation — 非执行确认阶段的已有行为不变

These tests capture the OBSERVED behavior of the unfixed code.
They MUST PASS on the unfixed code, establishing a baseline.
After the fix, they MUST STILL PASS, confirming no regression.

Observed behaviors preserved:
  1. _analyze_intent_with_confirmation is always called with context_aware_input
  2. _confirm_intent is called after intent recognition, handling y/n/supplement
  3. Supplement construction: current_input = f"{user_input}\n用户补充说明：{supplement}"
  4. After user confirms intent, _execute_root_agent is called with correct args
  5. /new and /exit commands bypass process_user_input
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
for p in (ROOT, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _make_app():
    from fractalclaw.entry.main import FractalClawApp
    app = FractalClawApp.__new__(FractalClawApp)
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
    app.intent_agent = None
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


def _make_mock_generation_result(success=False):
    mock = MagicMock()
    mock.success = success
    return mock


# ---------------------------------------------------------------------------
# Preservation 3.1: _analyze_intent_with_confirmation always called with context_aware_input
# ---------------------------------------------------------------------------

class TestPreservationAnalyzeIntent:
    """Property: _analyze_intent_with_confirmation is always called with context_aware_input."""

    @pytest.mark.asyncio
    @patch("fractalclaw.entry.main.cprint")
    async def test_analyze_called_with_context_aware_input_no_history(self, mock_cprint):
        app = _make_app()
        app._conversation_history = []

        received_inputs = []

        intent_result = _make_mock_intent_result(["测试需求"])
        mock_task = _make_mock_task()
        mock_config = _make_mock_agent_config()
        mock_agent_result = _make_mock_agent_result()
        mock_gen_result = _make_mock_generation_result()

        async def mock_analyze_intent_with_confirmation(user_input):
            received_inputs.append(user_input)
            return intent_result

        async def mock_create_workspace(ir, rtt):
            return mock_task

        async def mock_generate_root_agent(ir, wp, rtt):
            return mock_config, mock_gen_result

        async def mock_execute_root_agent(task_id, config, wp, ir, generation_result=None):
            return mock_agent_result

        app._analyze_intent_with_confirmation = mock_analyze_intent_with_confirmation
        app._create_workspace = mock_create_workspace
        app._generate_root_agent = mock_generate_root_agent
        app._execute_root_agent = mock_execute_root_agent
        app._display_execution_plan = MagicMock()
        app._confirm_execution = AsyncMock(return_value=True)

        user_input = "帮我写一个脚本"
        await app.process_user_input(user_input)

        assert len(received_inputs) == 1
        assert received_inputs[0] == user_input

    @pytest.mark.asyncio
    @patch("fractalclaw.entry.main.cprint")
    async def test_analyze_called_with_context_aware_input_with_history(self, mock_cprint):
        app = _make_app()
        app._conversation_history = [
            {"role": "user", "content": "之前的问题"},
            {"role": "assistant", "content": "之前的回答"},
        ]
        app._last_result = _make_mock_agent_result(success=True)

        received_inputs = []

        intent_result = _make_mock_intent_result(["后续需求"])
        mock_task = _make_mock_task()
        mock_config = _make_mock_agent_config()
        mock_agent_result = _make_mock_agent_result()
        mock_gen_result = _make_mock_generation_result()

        async def mock_analyze_intent_with_confirmation(user_input):
            received_inputs.append(user_input)
            return intent_result

        async def mock_create_workspace(ir, rtt):
            return mock_task

        async def mock_generate_root_agent(ir, wp, rtt):
            return mock_config, mock_gen_result

        async def mock_execute_root_agent(task_id, config, wp, ir, generation_result=None):
            return mock_agent_result

        app._analyze_intent_with_confirmation = mock_analyze_intent_with_confirmation
        app._create_workspace = mock_create_workspace
        app._generate_root_agent = mock_generate_root_agent
        app._execute_root_agent = mock_execute_root_agent
        app._display_execution_plan = MagicMock()
        app._confirm_execution = AsyncMock(return_value=True)

        user_input = "继续上次的任务"
        await app.process_user_input(user_input)

        assert len(received_inputs) == 1
        context_input = received_inputs[0]
        assert "[对话历史上下文]" in context_input
        assert user_input in context_input
        assert "之前的问题" in context_input

    @pytest.mark.asyncio
    @patch("fractalclaw.entry.main.cprint")
    async def test_analyze_always_first_step(self, mock_cprint):
        app = _make_app()
        call_sequence = []

        intent_result = _make_mock_intent_result(["需求"])
        mock_task = _make_mock_task()
        mock_config = _make_mock_agent_config()
        mock_agent_result = _make_mock_agent_result()
        mock_gen_result = _make_mock_generation_result()

        async def mock_analyze_intent_with_confirmation(user_input):
            call_sequence.append("_analyze_intent_with_confirmation")
            return intent_result

        async def mock_create_workspace(ir, rtt):
            call_sequence.append("_create_workspace")
            return mock_task

        async def mock_generate_root_agent(ir, wp, rtt):
            call_sequence.append("_generate_root_agent")
            return mock_config, mock_gen_result

        async def mock_execute_root_agent(task_id, config, wp, ir, generation_result=None):
            call_sequence.append("_execute_root_agent")
            return mock_agent_result

        app._analyze_intent_with_confirmation = mock_analyze_intent_with_confirmation
        app._create_workspace = mock_create_workspace
        app._generate_root_agent = mock_generate_root_agent
        app._execute_root_agent = mock_execute_root_agent
        app._display_execution_plan = MagicMock()
        app._confirm_execution = AsyncMock(return_value=True)

        await app.process_user_input("任意输入")

        assert call_sequence[0] == "_analyze_intent_with_confirmation"


# ---------------------------------------------------------------------------
# Preservation 3.2: _confirm_intent call and return value handling
# ---------------------------------------------------------------------------

class TestPreservationConfirmIntent:
    """Property: _confirm_intent is called after intent recognition, handling y/n/supplement."""

    @pytest.mark.asyncio
    @patch("fractalclaw.entry.main.cprint")
    async def test_confirm_intent_user_says_no_re_analyzes(self, mock_cprint):
        app = _make_app()

        analyze_inputs = []
        call_count = 0

        async def mock_analyze_intent(user_input):
            nonlocal call_count
            call_count += 1
            analyze_inputs.append(user_input)
            return _make_mock_intent_result([f"需求{call_count}"])

        app._analyze_intent = mock_analyze_intent
        app._display_intent_result = MagicMock()

        confirmation_responses = iter(["n", "y"])

        async def mock_confirm_intent():
            resp = next(confirmation_responses)
            if resp.lower() in ['y', 'yes', '是', '确认']:
                return True, None
            elif resp.lower() in ['n', 'no', '否', '重新理解']:
                return False, None
            else:
                return False, resp

        app._confirm_intent = mock_confirm_intent

        result = await app._analyze_intent_with_confirmation("原始输入")

        assert call_count == 2

    @pytest.mark.asyncio
    @patch("fractalclaw.entry.main.cprint")
    async def test_confirm_intent_supplement_re_analyzes(self, mock_cprint):
        app = _make_app()

        analyze_inputs = []
        call_count = 0

        async def mock_analyze_intent(user_input):
            nonlocal call_count
            call_count += 1
            analyze_inputs.append(user_input)
            return _make_mock_intent_result([f"需求{call_count}"])

        app._analyze_intent = mock_analyze_intent
        app._display_intent_result = MagicMock()

        confirmation_responses = iter(["补充说明内容", "y"])

        async def mock_confirm_intent():
            resp = next(confirmation_responses)
            if resp.lower() in ['y', 'yes', '是', '确认']:
                return True, None
            elif resp.lower() in ['n', 'no', '否', '重新理解']:
                return False, None
            else:
                return False, resp

        app._confirm_intent = mock_confirm_intent

        result = await app._analyze_intent_with_confirmation("原始输入")

        assert call_count == 2
        second_input = analyze_inputs[1]
        assert "用户补充说明：补充说明内容" in second_input
        assert "原始输入" in second_input


# ---------------------------------------------------------------------------
# Preservation 3.3: Supplement construction format
# ---------------------------------------------------------------------------

class TestPreservationSupplementFormat:
    """Property: current_input construction format is preserved."""

    @pytest.mark.asyncio
    @patch("fractalclaw.entry.main.cprint")
    async def test_supplement_format(self, mock_cprint):
        app = _make_app()

        analyze_inputs = []

        async def mock_analyze_intent(user_input):
            analyze_inputs.append(user_input)
            return _make_mock_intent_result(["需求"])

        app._analyze_intent = mock_analyze_intent
        app._display_intent_result = MagicMock()

        async def mock_confirm_intent():
            if len(analyze_inputs) == 1:
                return False, "我的补充"
            return True, None

        app._confirm_intent = mock_confirm_intent

        await app._analyze_intent_with_confirmation("原始问题")

        second_input = analyze_inputs[1]
        assert second_input == "原始问题\n用户补充说明：我的补充"

    @pytest.mark.asyncio
    @patch("fractalclaw.entry.main.cprint")
    async def test_supplement_format_with_special_chars(self, mock_cprint):
        app = _make_app()

        analyze_inputs = []

        async def mock_analyze_intent(user_input):
            analyze_inputs.append(user_input)
            return _make_mock_intent_result(["需求"])

        app._analyze_intent = mock_analyze_intent
        app._display_intent_result = MagicMock()

        supplement_text = "需要处理特殊字符 <>&\"'"

        async def mock_confirm_intent():
            if len(analyze_inputs) == 1:
                return False, supplement_text
            return True, None

        app._confirm_intent = mock_confirm_intent

        original_input = "原始问题"
        await app._analyze_intent_with_confirmation(original_input)

        second_input = analyze_inputs[1]
        expected = f"{original_input}\n用户补充说明：{supplement_text}"
        assert second_input == expected


# ---------------------------------------------------------------------------
# Preservation 3.4: _execute_root_agent call argument structure
# ---------------------------------------------------------------------------

class TestPreservationExecuteRootAgent:
    """Property: After user confirms intent, _execute_root_agent is called with correct args."""

    @pytest.mark.asyncio
    @patch("fractalclaw.entry.main.cprint")
    async def test_execute_root_agent_args(self, mock_cprint):
        app = _make_app()

        intent_result = _make_mock_intent_result(["需求A", "需求B"])
        mock_task = _make_mock_task()
        mock_config = _make_mock_agent_config()
        mock_agent_result = _make_mock_agent_result(success=True)
        mock_gen_result = _make_mock_generation_result(success=True)

        execute_args = {}

        async def mock_analyze_intent_with_confirmation(user_input):
            return intent_result

        async def mock_create_workspace(ir, rtt):
            return mock_task

        async def mock_generate_root_agent(ir, wp, rtt):
            return mock_config, mock_gen_result

        async def mock_execute_root_agent(task_id, config, workspace_path, ir, generation_result=None):
            execute_args["task_id"] = task_id
            execute_args["config"] = config
            execute_args["workspace_path"] = workspace_path
            execute_args["intent_result"] = ir
            execute_args["generation_result"] = generation_result
            return mock_agent_result

        app._analyze_intent_with_confirmation = mock_analyze_intent_with_confirmation
        app._create_workspace = mock_create_workspace
        app._generate_root_agent = mock_generate_root_agent
        app._execute_root_agent = mock_execute_root_agent
        app._display_execution_plan = MagicMock()
        app._confirm_execution = AsyncMock(return_value=True)

        await app.process_user_input("测试任务")

        assert execute_args["task_id"] == "mock-task-id"
        assert execute_args["config"] is mock_config
        assert execute_args["workspace_path"] == Path(mock_task.workspace_path)
        assert execute_args["intent_result"] is intent_result
        assert execute_args["generation_result"] is mock_gen_result

    @pytest.mark.asyncio
    @patch("fractalclaw.entry.main.cprint")
    async def test_execute_root_agent_returns_result(self, mock_cprint):
        app = _make_app()

        intent_result = _make_mock_intent_result(["需求"])
        mock_task = _make_mock_task()
        mock_config = _make_mock_agent_config()
        mock_agent_result = _make_mock_agent_result(success=True)
        mock_gen_result = _make_mock_generation_result()

        async def mock_analyze_intent_with_confirmation(user_input):
            return intent_result

        async def mock_create_workspace(ir, rtt):
            return mock_task

        async def mock_generate_root_agent(ir, wp, rtt):
            return mock_config, mock_gen_result

        async def mock_execute_root_agent(task_id, config, wp, ir, generation_result=None):
            return mock_agent_result

        app._analyze_intent_with_confirmation = mock_analyze_intent_with_confirmation
        app._create_workspace = mock_create_workspace
        app._generate_root_agent = mock_generate_root_agent
        app._execute_root_agent = mock_execute_root_agent
        app._display_execution_plan = MagicMock()
        app._confirm_execution = AsyncMock(return_value=True)

        result = await app.process_user_input("测试任务")

        assert result.success is True
        assert result.output == "mock output"

    @pytest.mark.asyncio
    @patch("fractalclaw.entry.main.cprint")
    async def test_create_workspace_receives_intent_and_task_text(self, mock_cprint):
        app = _make_app()

        intent_result = _make_mock_intent_result(["需求1", "需求2"])
        mock_task = _make_mock_task()
        mock_config = _make_mock_agent_config()
        mock_agent_result = _make_mock_agent_result()
        mock_gen_result = _make_mock_generation_result()

        create_args = {}

        async def mock_analyze_intent_with_confirmation(user_input):
            return intent_result

        async def mock_create_workspace(ir, rtt):
            create_args["intent_result"] = ir
            create_args["root_task_text"] = rtt
            return mock_task

        async def mock_generate_root_agent(ir, wp, rtt):
            return mock_config, mock_gen_result

        async def mock_execute_root_agent(task_id, config, wp, ir, generation_result=None):
            return mock_agent_result

        app._analyze_intent_with_confirmation = mock_analyze_intent_with_confirmation
        app._create_workspace = mock_create_workspace
        app._generate_root_agent = mock_generate_root_agent
        app._execute_root_agent = mock_execute_root_agent
        app._display_execution_plan = MagicMock()
        app._confirm_execution = AsyncMock(return_value=True)

        await app.process_user_input("测试")

        assert create_args["intent_result"] is intent_result
        assert "- 需求1" in create_args["root_task_text"]
        assert "- 需求2" in create_args["root_task_text"]

    @pytest.mark.asyncio
    @patch("fractalclaw.entry.main.cprint")
    async def test_generate_root_agent_receives_correct_args(self, mock_cprint):
        app = _make_app()

        intent_result = _make_mock_intent_result(["需求"])
        mock_task = _make_mock_task()
        mock_config = _make_mock_agent_config()
        mock_agent_result = _make_mock_agent_result()
        mock_gen_result = _make_mock_generation_result()

        gen_args = {}

        async def mock_analyze_intent_with_confirmation(user_input):
            return intent_result

        async def mock_create_workspace(ir, rtt):
            return mock_task

        async def mock_generate_root_agent(ir, wp, rtt):
            gen_args["intent_result"] = ir
            gen_args["workspace_path"] = wp
            gen_args["root_task_text"] = rtt
            return mock_config, mock_gen_result

        async def mock_execute_root_agent(task_id, config, wp, ir, generation_result=None):
            return mock_agent_result

        app._analyze_intent_with_confirmation = mock_analyze_intent_with_confirmation
        app._create_workspace = mock_create_workspace
        app._generate_root_agent = mock_generate_root_agent
        app._execute_root_agent = mock_execute_root_agent
        app._display_execution_plan = MagicMock()
        app._confirm_execution = AsyncMock(return_value=True)

        await app.process_user_input("测试")

        assert gen_args["intent_result"] is intent_result
        assert gen_args["workspace_path"] == Path(mock_task.workspace_path)


# ---------------------------------------------------------------------------
# Preservation 3.5: /new and /exit commands bypass process_user_input
# ---------------------------------------------------------------------------

class TestPreservationSessionCommands:
    """Property: /new and /exit commands do not go through process_user_input."""

    def test_new_command_not_routed_to_process(self):
        from fractalclaw.entry.main import FractalClawApp
        app = _make_app()

        processed_inputs = []

        async def tracking_process(user_input):
            processed_inputs.append(user_input)
            return _make_mock_agent_result()

        app.process_user_input = tracking_process

        assert "/new" not in processed_inputs
        assert "/exit" not in processed_inputs

    @pytest.mark.asyncio
    @patch("fractalclaw.entry.main.cprint")
    async def test_handle_new_session_does_not_error(self, mock_cprint):
        app = _make_app()
        app.intent_agent = None

        await app._handle_new_session()

        mock_cprint.assert_called()


# ---------------------------------------------------------------------------
# Preservation: _build_context_aware_input behavior
# ---------------------------------------------------------------------------

class TestPreservationContextAwareInput:
    """Property: _build_context_aware_input format is preserved."""

    def test_no_history_returns_raw_input(self):
        app = _make_app()
        app._conversation_history = []

        result = app._build_context_aware_input("测试输入")

        assert result == "测试输入"

    def test_with_history_includes_context(self):
        app = _make_app()
        app._conversation_history = [
            {"role": "user", "content": "用户问题"},
            {"role": "assistant", "content": "助手回答"},
        ]
        app._last_result = None

        result = app._build_context_aware_input("新输入")

        assert "[对话历史上下文]" in result
        assert "用户: 用户问题" in result
        assert "助手: 助手回答" in result
        assert "[用户新输入]: 新输入" in result

    def test_with_failed_last_result_and_history(self):
        app = _make_app()
        app._conversation_history = [
            {"role": "user", "content": "历史问题"},
        ]
        app._last_result = _make_mock_agent_result(success=False)
        app._last_result.error = "执行出错"

        result = app._build_context_aware_input("重试")

        assert "[上一轮任务执行结果: 失败(执行出错)]" in result

    def test_history_truncated_to_last_6(self):
        app = _make_app()
        app._conversation_history = [
            {"role": "user", "content": f"问题{i}"} for i in range(10)
        ]
        app._last_result = None

        result = app._build_context_aware_input("新输入")

        assert "问题9" in result
        assert "问题4" in result
        assert "问题3" not in result


# ---------------------------------------------------------------------------
# Preservation: _build_root_task_text format
# ---------------------------------------------------------------------------

class TestPreservationBuildRootTaskText:
    """Property: _build_root_task_text format is preserved."""

    def test_single_requirement(self):
        app = _make_app()
        result = app._build_root_task_text(["完成功能A"])
        assert result == "- 完成功能A"

    def test_multiple_requirements(self):
        app = _make_app()
        result = app._build_root_task_text(["需求1", "需求2", "需求3"])
        assert result == "- 需求1\n- 需求2\n- 需求3"

    def test_empty_requirements(self):
        app = _make_app()
        result = app._build_root_task_text([])
        assert result == ""


# ---------------------------------------------------------------------------
# Preservation: _extract_task_name behavior
# ---------------------------------------------------------------------------

class TestPreservationExtractTaskName:
    """Property: _extract_task_name behavior is preserved."""

    def test_first_requirement_used(self):
        app = _make_app()
        result = app._extract_task_name(["第一个需求", "第二个需求"])
        assert result == "第一个需求"

    def test_truncated_to_50_chars(self):
        app = _make_app()
        long_req = "A" * 100
        result = app._extract_task_name([long_req])
        assert len(result) == 50

    def test_special_chars_removed(self):
        app = _make_app()
        result = app._extract_task_name(['测试"需求\'包含。特殊，字符！'])
        assert '"' not in result
        assert "'" not in result
        assert "。" not in result

    def test_empty_requirements(self):
        app = _make_app()
        result = app._extract_task_name([])
        assert result == "Task"

    def test_whitespace_only(self):
        app = _make_app()
        result = app._extract_task_name(["   "])
        assert result == "Task"
