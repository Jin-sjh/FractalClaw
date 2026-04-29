"""FractalClaw CLI - Command Line Interface."""

import os
import sys
import asyncio
from pathlib import Path
from typing import Optional

if sys.platform == 'win32':
    import locale
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')

import typer
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.status import Status
from rich.table import Table
from dotenv import set_key, load_dotenv, unset_key

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

app = typer.Typer(help="FractalClaw - 分形智能体框架")
console = Console()

cyber_style = questionary.Style([
    ('qmark', 'fg:#C792EA bold'),
    ('question', 'fg:#82AAFF bold'),
    ('answer', 'fg:#C3E88D bold'),
    ('pointer', 'fg:#89DDFF bold'),
    ('highlighted', 'fg:#FFCB6B bold'),
    ('selected', 'fg:#82AAFF'),
    ('instruction', 'fg:#676E95'),
])

ENV_PATH = PROJECT_ROOT / ".env"


@app.command("config")
def config_wizard():
    """配置向导 - 设置API Key和模型"""
    console.clear()
    console.print(Panel(
        "🚀 Welcome to [bold #C792EA]FractalClaw[/bold #C792EA]...\n\n⚙️ [dim]请完成模型配置，我们将把密钥安全固化在本地。[/dim]",
        title="[bold white]⚡ FractalClaw Config[/bold white]",
        border_style="#C792EA"
    ))

    provider_raw = questionary.select(
        "选择你的模型提供商 (Provider):",
        choices=[
            "openai",
            "anthropic",
            "aliyun (openai compatible)",
            "tencent (openai compatible)",
            "z.ai (openai compatible)",
            "other (openai compatible)",
            "ollama"
        ],
        style=cyber_style,
        instruction="(按上下键选择，回车确认)"
    ).ask()

    if not provider_raw:
        console.print("[dim #C792EA]✦ 录入中断，FractalClaw 配置已取消。[/dim #C792EA]")
        return

    provider = provider_raw.split(" ")[0].strip()
    is_openai_compatible = "openai" in provider_raw.lower()

    model_name = questionary.text(
        "输入指定的模型型号 (如 gpt-4, qwen-max, glm-4 等):",
        style=cyber_style
    ).ask()

    if model_name is None:
        console.print("[dim #8d52ff]✦   录入中断，FractalClaw 配置已取消。[/dim #8d52ff]")
        return

    api_key = ""
    env_key = ""
    if provider != "ollama":
        if is_openai_compatible:
            env_key = "OPENAI_API_KEY"
        elif provider == "anthropic":
            env_key = "ANTHROPIC_API_KEY"

        api_key = questionary.password(
            f"输入你的 {env_key} (对应 {provider_raw}):",
            style=cyber_style
        ).ask()

        if api_key is None:
            console.print("[dim #8d52ff]✦   录入中断，FractalClaw 配置已取消。[/dim #8d52ff]")
            return

    base_url = ""
    if provider in ["openai", "anthropic"]:
        base_url = questionary.text(
            f"输入 {provider} 代理 Base URL (直连请直接回车跳过):",
            style=cyber_style
        ).ask()
    elif provider == "ollama":
        base_url = questionary.text(
            "输入 Ollama Base URL (默认 http://localhost:11434，直接回车跳过):",
            style=cyber_style
        ).ask()
    else:
        base_url = questionary.text(
            "输入兼容 Base URL (不填直接回车将使用官方默认地址):",
            style=cyber_style
        ).ask()

    if base_url is None:
        console.print("[dim #8d52ff]✦   录入中断，FractalClaw 配置已取消。[/dim #8d52ff]")
        return

    console.print("\n[dim]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/dim]")

    with Status(f"[bold #82AAFF]正在连接 {provider.upper()} 引擎并发送探测包...[/bold #82AAFF]", spinner="dots", spinner_style="#89DDFF"):
        try:
            if env_key and api_key:
                os.environ[env_key] = api_key
            if base_url:
                if is_openai_compatible:
                    os.environ["OPENAI_API_BASE"] = base_url
                else:
                    os.environ[f"{provider.upper()}_BASE_URL"] = base_url

            from fractalclaw.llm import LLMConfig, LLMEngine, OpenAICompatibleProvider
            from fractalclaw.agent import AgentContext

            llm_config = LLMConfig(
                model=model_name,
                api_key=api_key,
                base_url=base_url if base_url else None
            )

            if provider != "ollama":
                test_provider = OpenAICompatibleProvider(
                    api_key=api_key,
                    base_url=base_url or "https://api.openai.com/v1",
                    model=model_name
                )
                llm = LLMEngine(llm_config)
                llm.set_provider(test_provider)

            console.print(" [bold #C3E88D][ ✓ 配置成功!][/bold #C3E88D]")
        except Exception as e:
            console.print(f" [bold #FF5372][ ✗ 配置失败!][/bold #FF5372]  无法连接到模型，请检查 Key、Base URL、模型型号 或 网络！\n[dim]错误信息: {str(e)}[/dim]")
            return

    if not ENV_PATH.exists():
        ENV_PATH.touch()

    import logging
    logging.getLogger("dotenv.main").setLevel(logging.ERROR)

    unset_key(str(ENV_PATH), "OPENAI_API_BASE")
    unset_key(str(ENV_PATH), "ANTHROPIC_BASE_URL")
    unset_key(str(ENV_PATH), "OLLAMA_BASE_URL")

    if env_key and api_key:
        set_key(str(ENV_PATH), env_key, api_key)

    if base_url:
        if is_openai_compatible:
            set_key(str(ENV_PATH), "OPENAI_API_BASE", base_url)
        else:
            set_key(str(ENV_PATH), f"{provider.upper()}_BASE_URL", base_url)

    set_key(str(ENV_PATH), "DEFAULT_PROVIDER", provider)
    set_key(str(ENV_PATH), "DEFAULT_MODEL", model_name)

    console.print(Panel(
        "🎯 [bold]任务类型模型配置[/bold]（可选）\n\n"
        "为不同类型的任务指定不同的模型，系统会自动根据任务类型选择合适的模型。\n"
        "格式: [dim]provider/model_name[/dim]，如 [dim]deepseek/deepseek-coder[/dim]\n"
        "直接回车跳过则使用上面的默认模型。",
        border_style="#82AAFF"
    ))

    task_type_configs = {
        "MODEL_REASONING": ("深度推理/规划", "需要强推理能力，如 deepseek/deepseek-chat"),
        "MODEL_CODE": ("代码/测试", "需要强代码能力，如 deepseek/deepseek-coder"),
        "MODEL_RESEARCH": ("研究/分析", "需要强分析能力，如 openai/gpt-4"),
        "MODEL_CHAT": ("对话/问答", "需要快速响应，如 openai/gpt-3.5-turbo"),
        "MODEL_WRITING": ("写作/创作", "需要强创造力，如 anthropic/claude-3-sonnet"),
    }

    for env_key, (label, hint) in task_type_configs.items():
        model_config = questionary.text(
            f"{label} ({hint}):",
            style=cyber_style,
        ).ask()

        if model_config is None:
            break

        if model_config.strip():
            set_key(str(ENV_PATH), env_key, model_config.strip())

    console.print(Panel(
        f"配置已保存至 [#82AAFF]{ENV_PATH}[/#82AAFF]\n"
        f"当前默认提供商: [#C792EA]{provider}[/#C792EA] | 模型: [#C792EA]{model_name}[/#C792EA]\n\n"
        f"👉 输入 [bold #89DDFF]fractalclaw run[/bold #89DDFF] 即可启动系统！",
        border_style="#82AAFF"
    ))


def _show_boot_error():
    console.print(Panel(
        "[bold #FFCB6B]FractalClaw未完成配置![/bold #FFCB6B]\n\n"
        "[#C792EA]检测到 API Key、模型或Baseurl缺失。请重新执行以下命令完成配置：[/#C792EA]\n"
        "[bold #89DDFF]fractalclaw config[/bold #89DDFF]",
        title="[bold #FF5372]⚠️ Boot Sequence Failed[/bold #FF5372]",
        border_style="#FF5372"
    ))


@app.command("run")
def run_agent():
    """启动 FractalClaw 交互式会话"""
    load_dotenv(ENV_PATH)
    provider = os.getenv("DEFAULT_PROVIDER")
    model = os.getenv("DEFAULT_MODEL")

    if not provider or not model:
        _show_boot_error()
        raise typer.Exit(1)

    if provider != "ollama":
        if provider in ["openai", "aliyun", "z.ai", "tencent", "other"]:
            if not os.getenv("OPENAI_API_KEY"):
                _show_boot_error()
                raise typer.Exit(1)
        elif provider == "anthropic":
            if not os.getenv("ANTHROPIC_API_KEY"):
                _show_boot_error()
                raise typer.Exit(1)

    from entry.main import FractalClawApp
    asyncio.run(FractalClawApp().run())


@app.command("task")
def execute_task(
    instruction: str = typer.Argument(..., help="任务描述"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="模型提供商"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="模型名称"),
):
    """直接执行单个任务"""
    load_dotenv(ENV_PATH)

    actual_provider = provider or os.getenv("DEFAULT_PROVIDER")
    actual_model = model or os.getenv("DEFAULT_MODEL")

    if not actual_provider or not actual_model:
        _show_boot_error()
        raise typer.Exit(1)

    console.print(f"[bold #82AAFF]✦ 执行任务:[/bold #82AAFF] {instruction}")

    async def run_task():
        from entry.main import FractalClawApp
        app_instance = FractalClawApp()
        await app_instance.initialize()
        result = await app_instance.process_user_input(instruction)
        return result

    result = asyncio.run(run_task())

    if result.success:
        console.print(f"\n[bold #C3E88D]✦ 任务完成![/bold #C3E88D]")
        if result.output:
            console.print(Panel(result.output[:1000], title="输出结果", border_style="#82AAFF"))
    else:
        console.print(f"\n[bold red]✦ 任务失败:[/bold red] {result.error}")


@app.command("list")
def list_agents():
    """列出所有可用的Agent"""
    from fractalclaw.agent.loader import ConfigLoader

    loader = ConfigLoader(PROJECT_ROOT / "configs")

    agents = loader.list_agents()

    table = Table(title="可用 Agent 列表", border_style="#C792EA")
    table.add_column("Agent ID", style="#82AAFF")
    table.add_column("名称", style="#C792EA")
    table.add_column("角色", style="white")
    table.add_column("描述", style="dim")

    for agent_id in agents:
        try:
            config = loader.load(agent_id)
            table.add_row(
                agent_id,
                config.name,
                config.role,
                config.description[:50] + "..." if len(config.description) > 50 else config.description
            )
        except Exception:
            table.add_row(agent_id, "-", "-", "-")

    console.print(table)

    basic_agents_dir = PROJECT_ROOT / "configs" / "basic_agents"
    if basic_agents_dir.exists():
        console.print("\n[bold #C792EA]基础 Agent:[/bold #C792EA]")
        for yaml_file in basic_agents_dir.glob("*.yaml"):
            console.print(f"  - {yaml_file.stem}")


@app.command("monitor")
def run_monitor():
    """启动监控面板"""
    try:
        from entry.monitor import main as monitor_main
        monitor_main()
    except ImportError as e:
        console.print(f"[bold red]启动失败：找不到监视器模块！[/bold red]\n[dim]请确保 monitor.py 和 cli.py 在同一目录下。\n报错信息: {e}[/dim]")


@app.command("workspace")
def workspace_info():
    """显示工作空间信息"""
    workspace_path = PROJECT_ROOT / "workspace"

    if not workspace_path.exists():
        console.print("[dim #82AAFF]工作空间尚未创建。运行任务后将自动生成。[/dim #82AAFF]")
        return

    console.print(f"[bold #C792EA]工作空间路径:[/bold #C792EA] {workspace_path}")

    table = Table(title="任务列表", border_style="#C792EA")
    table.add_column("日期", style="#82AAFF")
    table.add_column("任务数量", style="white")

    for date_folder in sorted(workspace_path.iterdir(), reverse=True):
        if date_folder.is_dir() and date_folder.name.isdigit():
            task_count = len(list(date_folder.iterdir()))
            table.add_row(date_folder.name, str(task_count))

    console.print(table)


def main():
    app()


if __name__ == "__main__":
    main()
