"""FractalClaw Main Entry - Interactive Agent Application."""

from __future__ import annotations

import os
import sys
import time
import asyncio
import random
import re
import yaml
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass

from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.styles import Style
from prompt_toolkit.application import get_app

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from fractalclaw.agent import (
    Agent,
    AgentConfig,
    AgentContext,
    AgentResult,
    AgentRole,
    AgentFactory,
)
from fractalclaw.agent.config_generator import AgentConfigGenerator
from fractalclaw.agent.loader import ConfigLoader
from fractalclaw.scheduler import Scheduler, SchedulerConfig, TaskPriority
from fractalclaw.scheduler.agent_workspace import AgentWorkspaceManager, WorkDocument
from fractalclaw.llm import LLMConfig, OpenAICompatibleProvider


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def type_line(text: str, delay: float = 0.008):
    for ch in text:
        print(ch, end='', flush=True)
        time.sleep(delay)
    print()


def print_banner():
    clear_screen()

    CYAN = '\033[38;5;51m'
    PURPLE = '\033[38;5;141m'
    SILVER = '\033[38;5;250m'
    DIM = '\033[2m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    WHITE = '\033[37m'

    logo = f"""{CYAN}{BOLD}
███████╗██████╗  █████╗  ██████╗████████╗ █████╗ ██╗     
██╔════╝██╔══██╗██╔══██╗██╔════╝╚══██╔══╝██╔══██╗██║     
█████╗  ██████╔╝███████║██║        ██║   ███████║██║     
██╔══╝  ██╔══██╗██╔══██║██║        ██║   ██╔══██║██║     
██║     ██║  ██║██║  ██║╚██████╗   ██║   ██║  ██║███████╗
╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝
{RESET}"""

    sub_title = f"{WHITE}{BOLD} 👾 Welcome to the {PURPLE}{BOLD}FractalClaw{RESET}{WHITE}{BOLD} !  {RESET}"

    quotes = [
        "Fractals: infinitely complex, infinitely beautiful.",
        "From simplicity, complexity emerges.",
        "Each part contains the whole.",
        "Self-similarity at every scale.",
        "Patterns within patterns, worlds within worlds.",
        "The fractal nature of intelligence.",
        "Divide and conquer, recursively.",
        "Agents creating agents, infinitely.",
    ]
    quote = random.choice(quotes)
    meta = f" {SILVER}✦{RESET} {CYAN}{quote}{RESET}"

    tip = (
        f"{PURPLE} ✦ {RESET}"
        f"{SILVER}{PURPLE}{BOLD}FractalClaw{RESET} 已完成启动。输入命令开始，输入 {PURPLE}/exit{RESET}{SILVER} 退出，{PURPLE}/new{RESET}{SILVER} 开启新会话。{RESET}\n"
    )

    print(logo)
    print(sub_title)
    print()
    time.sleep(0.12)
    print(meta)
    print()
    type_line(tip, delay=0.004)


def cprint(text="", end="\n"):
    print_formatted_text(ANSI(str(text)), end=end)


@dataclass
class SpinnerState:
    action_words = [
        "Thinking...",
        "Analyzing intent...",
        "Generating config...",
        "Creating workspace...",
        "Executing...",
        "Planning...",
        "Delegating...",
        "Reflecting...",
    ]
    current_words: list = None
    is_spinning: bool = False
    start_time: float = 0
    frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    is_tool_calling: bool = False
    tool_msg: str = ""
    phase: str = ""

    def __post_init__(self):
        if self.current_words is None:
            self.current_words = []


class FractalClawApp:
    """FractalClaw 主应用类"""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or self._get_default_config_path()
        self.intent_agent: Optional[Agent] = None
        self.config_generator: Optional[AgentConfigGenerator] = None
        self.scheduler: Optional[Scheduler] = None
        self.workspace_manager: Optional[AgentWorkspaceManager] = None
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.spinner = SpinnerState()
        self.llm_config: Optional[LLMConfig] = None
        self.provider: Optional[OpenAICompatibleProvider] = None
        self.agent_factory: Optional[AgentFactory] = None
        self._current_agent: Optional[Agent] = None
        self.session: Optional[PromptSession] = None
        self._pending_confirmation: bool = False
        self._confirmation_queue: asyncio.Queue = asyncio.Queue()

    def _get_default_config_path(self) -> Path:
        return PROJECT_ROOT

    async def initialize(self):
        """初始化应用"""
        env_path = self.config_path / ".env"
        load_dotenv(env_path)

        from fractalclaw.llm.provider_pool import ProviderPool
        from fractalclaw.llm.model_router import ModelRouter

        self.provider_pool = ProviderPool()
        self.model_router = ModelRouter(self.provider_pool)

        provider_name = os.getenv("DEFAULT_PROVIDER", "openai")
        from fractalclaw.llm.model_profile import get_default_model_name
        model = get_default_model_name()

        default_provider = self.provider_pool.get_provider(provider_name)
        if not default_provider:
            raise ValueError(f"无法创建 Provider: {provider_name}，请检查 API Key 配置")

        self.provider = default_provider

        self.llm_config = LLMConfig(
            model=model,
            stream=False,
        )

        self.config_generator = AgentConfigGenerator(
            config_dir=self.config_path / "configs" / "agents",
            global_settings=self._load_global_settings(),
            llm_provider=self.provider,
            model_router=self.model_router,
        )

        scheduler_config = SchedulerConfig(
            workspace_root=str(self.config_path / "workspace")
        )
        self.scheduler = Scheduler(scheduler_config)
        self.workspace_manager = self.scheduler._workspace_manager
        self.agent_factory = AgentFactory(
            config_dir=self.config_path / "configs",
            llm_provider=self.provider,
            workspace_manager=self.workspace_manager,
            model_router=self.model_router,
        )
        self.scheduler.set_agent_factory(self.agent_factory)

        intent_config = self._load_intent_agent_config()
        intent_config.llm_config = self.llm_config
        self.intent_agent = self.agent_factory.create_from_config(
            intent_config,
            cache_key="__intent_agent__",
        )

    def _load_intent_agent_config(self) -> AgentConfig:
        """加载意图识别Agent配置"""
        from fractalclaw.agent.loader import WorkflowConfig, WorkflowStep

        intent_config_path = self.config_path / "configs" / "basic_agents" / "agent_intent_recognition.yaml"
        
        if intent_config_path.exists():
            with open(intent_config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            
            workflow_data = data.get('workflow')
            workflow = None
            if workflow_data:
                steps = [
                    WorkflowStep(
                        step=s.get('step', i + 1),
                        name=s.get('name', ''),
                        description=s.get('description', ''),
                        action=s.get('action', ''),
                    )
                    for i, s in enumerate(workflow_data.get('steps', []))
                ]
                workflow = WorkflowConfig(
                    name=workflow_data.get('name', ''),
                    steps=steps,
                )

            return AgentConfig(
                name=data.get('name', 'IntentRecognitionAgent'),
                description=data.get('description', ''),
                role=AgentRole.SPECIALIST,
                system_prompt=data.get('system_prompt', ''),
                max_iterations=data.get('behavior', {}).get('max_iterations', 5),
                enable_planning=False,
                enable_reflection=False,
                workflow=workflow,
            )
        
        return AgentConfig(
            name="IntentRecognitionAgent",
            description="意图识别Agent",
            role=AgentRole.SPECIALIST,
            system_prompt="你是一个专业的意图识别助手，负责将用户输入的话语进行结构化解析。",
            max_iterations=5,
            enable_planning=False,
            enable_reflection=False,
        )

    def _load_global_settings(self) -> dict:
        """加载全局配置"""
        settings_path = self.config_path / "configs" / "settings.yaml"
        if settings_path.exists():
            with open(settings_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        return {}

    async def process_user_input(self, user_input: str) -> AgentResult:
        """处理用户输入的完整流程"""
        intent_result = await self._analyze_intent_with_confirmation(user_input)
        root_task_text = self._build_root_task_text(intent_result["requirements"])
        
        self.spinner.is_spinning = True
        self.spinner.phase = "workspace"
        self.spinner.current_words = ["Creating workspace...", "Setting up files..."]
        task = await self._create_workspace(intent_result, root_task_text)
        workspace_path = Path(task.workspace_path)
        
        self.spinner.phase = "config"
        self.spinner.current_words = ["Generating config...", "Creating Root Agent..."]
        root_agent_config, generation_result = await self._generate_root_agent(
            intent_result,
            workspace_path,
            root_task_text,
        )
        
        self.spinner.phase = "execute"
        self.spinner.current_words = ["Executing...", "Running Root Agent..."]
        result = await self._execute_root_agent(task.id, root_agent_config, workspace_path, intent_result, generation_result)
        
        return result

    async def _analyze_intent(self, user_input: str) -> dict:
        """调用意图识别Agent分析用户输入"""
        context = AgentContext(
            task=user_input,
            metadata={"phase": "intent_recognition"}
        )
        
        result = await self.intent_agent.run(context)
        
        parsed = self._parse_intent_output(result.output)
        
        return {
            "requirements": parsed.get("任务需求", [user_input]),
            "acceptance_criteria": parsed.get("验收结果", []),
            "raw_output": result.output
        }

    def _parse_intent_output(self, output: str) -> dict:
        """解析意图识别Agent的YAML输出"""
        try:
            yaml_match = re.search(r'```yaml\s*(.*?)\s*```', output, re.DOTALL)
            if yaml_match:
                yaml_content = yaml_match.group(1)
                return yaml.safe_load(yaml_content) or {}
            
            yaml_match = re.search(r'任务需求:.*?(?=验收结果:|```|$)', output, re.DOTALL)
            if yaml_match:
                return yaml.safe_load(output) or {}
        except yaml.YAMLError:
            pass
        
        requirements = []
        acc_criteria = []
        
        req_match = re.search(r'任务需求:\s*([\s\S]*?)(?=验收结果:|$)', output)
        if req_match:
            req_text = req_match.group(1)
            requirements = [r.strip().strip('-').strip() for r in req_text.strip().split('\n') if r.strip()]
        
        acc_match = re.search(r'验收结果:\s*([\s\S]*?)(?=$)', output)
        if acc_match:
            acc_text = acc_match.group(1)
            acc_criteria = [a.strip().strip('-').strip() for a in acc_text.strip().split('\n') if a.strip()]
        
        return {
            "任务需求": requirements if requirements else ["完成用户任务"],
            "验收结果": acc_criteria
        }

    def _display_intent_result(self, intent_result: dict) -> None:
        """显示意图理解结果"""
        cprint()
        cprint(f"  \033[38;5;122m{'═' * 50}\033[0m")
        cprint(f"  \033[38;5;122m📋 意图理解结果\033[0m")
        cprint(f"  \033[38;5;122m{'═' * 50}\033[0m")
        
        requirements = intent_result.get("requirements", [])
        if requirements:
            cprint(f"\n  \033[38;5;214m任务需求：\033[0m")
            for i, req in enumerate(requirements, 1):
                cprint(f"    \033[38;5;247m{i}.\033[0m {req}")
        
        acceptance = intent_result.get("acceptance_criteria", [])
        if acceptance:
            cprint(f"\n  \033[38;5;214m验收标准：\033[0m")
            for i, acc in enumerate(acceptance, 1):
                cprint(f"    \033[38;5;247m{i}.\033[0m {acc}")
        
        cprint(f"\n  \033[38;5;122m{'═' * 50}\033[0m")
        cprint()

    async def _confirm_intent(self) -> tuple[bool, Optional[str]]:
        """获取用户确认（通过队列机制，避免与 user_input_loop 的 prompt_async 冲突）
        
        Returns:
            tuple[bool, Optional[str]]: (是否确认, 补充说明)
        """
        cprint(f"  \033[38;5;51m是否正确理解了您的意图？\033[0m")
        cprint(f"  \033[38;5;242m  [Y] 确认  [n] 重新理解  [输入补充说明]\033[0m")
        
        self._pending_confirmation = True
        
        while True:
            response = await self._confirmation_queue.get()
            response = response.strip()
            
            if not response:
                cprint(f"  \033[38;5;242m请输入 Y 确认、n 重新理解、或补充说明\033[0m")
                continue
            
            self._pending_confirmation = False
            
            if response.lower() in ['y', 'yes', '是', '确认']:
                return True, None
            elif response.lower() in ['n', 'no', '否', '重新理解']:
                return False, None
            else:
                return False, response

    async def _analyze_intent_with_confirmation(self, user_input: str) -> dict:
        """带用户确认的意图分析"""
        current_input = user_input
        intent_result = None
        
        while True:
            self.spinner.phase = "intent"
            self.spinner.current_words = ["Analyzing intent...", "Parsing requirements..."]
            self.spinner.is_spinning = True
            
            intent_result = await self._analyze_intent(current_input)
            
            self.spinner.is_spinning = False
            
            self._display_intent_result(intent_result)
            
            confirmed, supplement = await self._confirm_intent()
            
            if confirmed:
                cprint(f"  \033[38;5;141m✓ 意图确认成功，开始执行任务...\033[0m\n")
                return intent_result
            
            if supplement:
                cprint(f"  \033[38;5;214m已收到补充说明，重新理解意图...\033[0m\n")
                current_input = f"{user_input}\n用户补充说明：{supplement}"
            else:
                cprint(f"  \033[38;5;214m重新理解意图...\033[0m\n")

    def _build_root_task_text(self, requirements: list[str]) -> str:
        return "\n".join(f"- {requirement}" for requirement in requirements)

    async def _generate_root_agent(
        self,
        intent_result: dict,
        workspace_path: Path,
        root_task_text: str,
    ) -> tuple[AgentConfig, Optional[Any]]:
        """根据意图分析结果生成Root Agent配置
        
        Args:
            intent_result: 意图分析结果
            workspace_path: workspace路径，配置将保存到此目录
            
        Returns:
            tuple[AgentConfig, Optional[GenerationResult]]: (Agent配置, 生成结果)
        """
        generation_result = await self.config_generator.generate_from_requirement(
            requirement=root_task_text,
            save_path=workspace_path
        )
        
        if not generation_result.success:
            return AgentConfig(
                name="RootAgent",
                description=root_task_text,
                role=AgentRole.ROOT,
                llm_config=self.llm_config,
                max_iterations=10,
                enable_planning=True,
                enable_reflection=True,
            ), generation_result
        
        config_path = workspace_path / f"{generation_result.agent_id}.yaml"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f) or {}
            return AgentConfig(
                name=config_data.get('name', 'RootAgent'),
                description=config_data.get('description', root_task_text),
                role=AgentRole.ROOT,
                llm_config=self.llm_config,
                max_iterations=config_data.get('max_iterations', 10),
                enable_planning=config_data.get('enable_planning', True),
                enable_reflection=config_data.get('enable_reflection', True),
                system_prompt=config_data.get('system_prompt', ''),
            ), generation_result
        
        return AgentConfig(
            name="RootAgent",
            description=root_task_text,
            role=AgentRole.ROOT,
            llm_config=self.llm_config,
            max_iterations=10,
            enable_planning=True,
            enable_reflection=True,
        ), generation_result

    async def _create_workspace(self, intent_result: dict, root_task_text: str):
        """创建任务工作空间"""
        requirements = intent_result["requirements"]
        acceptance = intent_result["acceptance_criteria"]
        
        task_name = self._extract_task_name(requirements)
        
        task = self.scheduler.create_project(
            instruction=root_task_text,
            name=task_name,
            metadata={
                "acceptance_criteria": "\n".join(acceptance) if acceptance else ""
            }
        )
        
        return task

    def _extract_task_name(self, requirements: list) -> str:
        """从需求中提取任务名称"""
        if not requirements:
            return "Task"
        
        first_req = requirements[0]
        name = first_req[:50]
        for char in ['"', "'", '。', '，', '！', '？', '\n']:
            name = name.replace(char, '')
        return name.strip() or "Task"

    async def _execute_root_agent(
        self,
        task_id: str,
        config: AgentConfig,
        workspace_path: Path,
        intent_result: dict,
        generation_result: Optional[Any] = None
    ) -> AgentResult:
        """执行Root Agent
        
        Args:
            config: Agent配置
            workspace_path: workspace路径
            intent_result: 意图分析结果
            generation_result: 配置生成结果（包含配置文件路径）
        """
        config_path = None
        if generation_result and generation_result.success:
            config_path = workspace_path / f"{generation_result.agent_id}.yaml"
        if not self.scheduler:
            raise RuntimeError("Scheduler is not initialized")

        result = await self.scheduler.execute_task(
            task_id,
            agent_config=config,
            existing_config_path=config_path,
        )
        self._current_agent = self.scheduler._agents.get(task_id)
        return result

    async def _handle_new_session(self) -> None:
        if self.intent_agent and hasattr(self.intent_agent, '_memory') and self.intent_agent._memory:
            await self.intent_agent._memory.end_session("User requested new session", "interrupted")
        cprint("  \033[38;5;141m✦ 新会话已开启，之前的内容已保存到日志记忆。\033[0m")

    async def run(self):
        """运行主应用"""
        print_banner()
        
        try:
            await self.initialize()
        except Exception as e:
            cprint(f"  \033[31m[ ⚠️ 初始化失败 : {e} ]\033[0m")
            return

        def get_bottom_toolbar():
            if not self.spinner.is_spinning:
                return ANSI("")
            
            elapsed = time.time() - self.spinner.start_time
            if self.spinner.is_tool_calling:
                display_msg = self.spinner.tool_msg
            else:
                idx_word = int(elapsed) % len(self.spinner.current_words) if self.spinner.current_words else 0
                display_msg = f"👾 {self.spinner.current_words[idx_word] if self.spinner.current_words else 'Processing...'}"

            idx_frame = int(elapsed * 12) % len(self.spinner.frames)
            frame = self.spinner.frames[idx_frame]

            return ANSI(f"  \033[38;5;51m{frame}\033[0m \033[38;5;250m{display_msg}\033[0m \033[38;5;141m[{elapsed:.1f}s]\033[0m")

        prompt_message = ANSI("  \033[38;5;51m❯\033[0m ")
        placeholder_text = ANSI("\033[3m\033[38;5;242minput...\033[0m")

        async def agent_worker():
            while True:
                user_input = await self.task_queue.get()
                if user_input.lower() in ["/exit", "/quit"]:
                    self.task_queue.task_done()
                    break

                if user_input.lower() == "/new":
                    await self._handle_new_session()
                    self.task_queue.task_done()
                    continue

                self.spinner.current_words = SpinnerState.action_words.copy()
                random.shuffle(self.spinner.current_words)
                
                self.spinner.start_time = time.time()
                self.spinner.is_spinning = True
                self.spinner.is_tool_calling = False

                try:
                    result = await self.process_user_input(user_input)
                    
                    self.spinner.is_spinning = False
                    
                    if result.success:
                        cprint(f"  \033[38;5;141m❯\033[0m \033[38;5;250m任务已完成！\033[0m")
                        if result.output:
                            lines = result.output.strip().split('\n')
                            for line in lines[:10]:
                                cprint(f"    {line}")
                            if len(lines) > 10:
                                cprint(f"    ... (共 {len(lines)} 行)")
                    else:
                        cprint(f"  \033[31m❯ 任务执行失败: {result.error or '未知错误'}\033[0m")

                except Exception as e:
                    self.spinner.is_spinning = False
                    cprint(f"  \033[31m[ ⚠️ 执行异常 : {e} ]\033[0m")

                self.spinner.is_spinning = False
                cprint()
                self.task_queue.task_done()

        async def user_input_loop():
            custom_style = Style.from_dict({
                'bottom-toolbar': 'bg:default fg:default noreverse',
            })
            
            self.session = PromptSession(
                bottom_toolbar=get_bottom_toolbar,
                style=custom_style,
                erase_when_done=True,
                reserve_space_for_menu=0
            )
            
            async def redraw_timer():
                while True:
                    if self.spinner.is_spinning:
                        try:
                            get_app().invalidate()
                        except Exception:
                            pass
                    await asyncio.sleep(0.08)

            redraw_task = asyncio.create_task(redraw_timer())

            while True:
                try:
                    if self._pending_confirmation:
                        prompt_msg = ANSI("  \033[38;5;51m❯ 确认\033[0m ")
                        placeholder_msg = ANSI("\033[3m\033[38;5;242m[Y]确认 [n]重新理解 [补充说明]...\033[0m")
                    else:
                        prompt_msg = prompt_message
                        placeholder_msg = placeholder_text

                    user_input = await self.session.prompt_async(prompt_msg, placeholder=placeholder_msg)

                    user_input = user_input.strip()
                    if not user_input:
                        continue

                    padded_bubble = f"  ❯ {user_input}    "
                    cprint(f"\033[48;2;38;38;38m\033[38;5;255m{padded_bubble}\033[0m\n")

                    if self._pending_confirmation:
                        await self._confirmation_queue.put(user_input)
                    else:
                        await self.task_queue.put(user_input)
                        if user_input.lower() in ["/exit", "/quit"]:
                            cprint("  \033[38;5;141m✦ 记忆已固化，FractalClaw 进入休眠。\033[0m")
                            break

                except (KeyboardInterrupt, EOFError):
                    cprint("\n  \033[38;5;141m✦ 强制中断，FractalClaw 进入休眠。\033[0m")
                    await self.task_queue.put("/exit")
                    break

            redraw_task.cancel()

        with patch_stdout():
            worker = asyncio.create_task(agent_worker())
            await user_input_loop()
            await self.task_queue.join()
            worker.cancel()


def main():
    asyncio.run(FractalClawApp().run())


if __name__ == "__main__":
    main()
