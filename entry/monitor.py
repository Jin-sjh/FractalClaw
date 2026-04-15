"""FractalClaw Monitor - Real-time monitoring panel."""

import time
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.theme import Theme
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich import box
from rich.table import Table
from rich.live import Live
from rich.layout import Layout

PROJECT_ROOT = Path(__file__).resolve().parent.parent

cyber_theme = Theme({
    "info": "dim cyan",
    "warning": "color(141)",
    "error": "bold red",
    "success": "bold green",
    "agent": "bold color(141)",
    "tool": "bold yellow",
    "result": "bold green",
    "message": "bold bright_magenta",
    "timestamp": "dim white"
})

console = Console(theme=cyber_theme)

WORKSPACE_PATH = PROJECT_ROOT / "workspace"


def get_latest_task_log() -> Optional[Path]:
    """获取最新任务的日志文件"""
    if not WORKSPACE_PATH.exists():
        return None

    date_folders = sorted(
        [d for d in WORKSPACE_PATH.iterdir() if d.is_dir() and d.name.isdigit()],
        key=lambda x: x.name,
        reverse=True
    )

    if not date_folders:
        return None

    for date_folder in date_folders:
        task_folders = sorted(
            [t for t in date_folder.iterdir() if t.is_dir()],
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )

        for task_folder in task_folders:
            log_file = task_folder / "logs" / "execution.log"
            if log_file.exists():
                return log_file

    return None


def print_header():
    """渲染监控面板头部"""

    monster = (
        "  ▄█▄▄█▄  \n"
        " ▀██████▀ \n"
        " ██▄██▄██ \n"
        "  ▀    ▀  "
    )

    content = Text(justify="center")
    content.append("\n  Live Stream  \n\n", style="bold white italic")
    content.append(monster + "\n\n", style="color(141)")
    content.append("   What is FractalClaw doing?    \n", style="dim white italic")

    panel = Panel(
        Align.center(content),
        title="[bold color(141)] FractalClaw Monitor [/bold color(141)]",
        title_align="left",
        border_style="color(141)",
        box=box.ROUNDED,
        width=42,
        padding=0
    )

    console.print(Align.center(panel))
    console.print()


def tail_f(filepath: Path):
    """文件末尾监听"""
    if not filepath.exists():
        console.print(f"[warning]⏳ 等待日志文件生成...[/warning]")
        while not filepath.exists():
            time.sleep(0.5)

    with open(filepath, 'r', encoding='utf-8') as f:
        f.seek(0, 2)
        print_header()
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue
            yield line


def render_event(line: str):
    """解析并渲染监控日志"""
    try:
        data = json.loads(line.strip())
        
        timestamp = data.get("timestamp", "")
        agent_name = data.get("agent_name", "Unknown")
        agent_id = data.get("agent_id", "")
        agent_state = data.get("agent_state", "")
        tool_name = data.get("tool_name")
        tool_args = data.get("tool_args")
        tool_output = data.get("tool_output")
        message = data.get("message", "")

        try:
            if timestamp.endswith('Z'):
                timestamp = timestamp[:-1] + '+00:00'
            dt_local = datetime.fromisoformat(timestamp).astimezone()
            ts = dt_local.strftime("%H:%M:%S")
        except Exception:
            ts = timestamp.split("T")[-1][:8] if "T" in timestamp else timestamp[:8]

        prefix = f"[timestamp][ {ts} ][/timestamp]"

        if tool_name:
            args_str = ""
            if tool_args:
                try:
                    args_str = json.dumps(tool_args, ensure_ascii=False, indent=2)
                except Exception:
                    args_str = str(tool_args)
            
            content = f"[bold white] ● 工具调用: [/bold white][bold color(141)]{tool_name}[/bold color(141)]"
            if args_str:
                content += f"\n参数:\n{args_str[:300]}"
            
            console.print(Panel(
                content,
                title=f"✦ 工具执行 [ {ts} ]",
                title_align="left",
                border_style="color(141)",
                width=60
            ))

            if tool_output:
                display_output = tool_output[:300] + "..." if len(str(tool_output)) > 300 else tool_output
                console.print(Panel(
                    f"[bold white] ● 执行结果: [/bold white]\n{display_output}",
                    title=f"✦ 结果回传 [ {ts} ]",
                    title_align="left",
                    border_style="cyan",
                    width=60
                ))

        elif agent_state:
            state_colors = {
                "idle": "dim white",
                "planning": "bold yellow",
                "thinking": "bold cyan",
                "executing": "bold green",
                "delegating": "bold magenta",
                "error": "bold red",
                "stopped": "dim red"
            }
            state_color = state_colors.get(agent_state, "white")
            
            console.print(f"{prefix}[agent]{agent_name}[/agent] 状态: [{state_color}]{agent_state}[/{state_color}]")

        elif message:
            console.print(f"{prefix}[info]{message}[/info]")

    except json.JSONDecodeError:
        pass
    except Exception:
        pass


def show_task_list():
    """显示任务列表"""
    if not WORKSPACE_PATH.exists():
        console.print("[warning]工作空间尚未创建[/warning]")
        return

    table = Table(title="任务状态", border_style="color(141)")
    table.add_column("任务ID", style="cyan")
    table.add_column("状态", style="white")
    table.add_column("创建时间", style="dim")

    for date_folder in sorted(WORKSPACE_PATH.iterdir(), reverse=True):
        if not date_folder.is_dir() or not date_folder.name.isdigit():
            continue

        for task_folder in date_folder.iterdir():
            if not task_folder.is_dir():
                continue

            metadata_file = task_folder / "task_metadata.json"
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    
                    status = metadata.get("status", "unknown")
                    status_color = {
                        "pending": "yellow",
                        "running": "cyan",
                        "completed": "green",
                        "failed": "red",
                        "cancelled": "dim"
                    }.get(status, "white")

                    table.add_row(
                        task_folder.name[:30],
                        f"[{status_color}]{status}[/{status_color}]",
                        metadata.get("created_at", "")[:19]
                    )
                except Exception:
                    pass

    console.print(table)


def show_agent_tree():
    """显示Agent树结构"""
    console.print("\n[bold color(141)]Agent 树结构:[/bold color(141)]")
    console.print("  RootAgent")
    console.print("  ├── CoordinatorAgent (if needed)")
    console.print("  │   ├── WorkerAgent 1")
    console.print("  │   └── WorkerAgent 2")
    console.print("  └── SpecialistAgent (if needed)")


def main():
    """监控主入口"""
    import argparse

    parser = argparse.ArgumentParser(description="FractalClaw Monitor")
    parser.add_argument("--tasks", action="store_true", help="显示任务列表")
    parser.add_argument("--tree", action="store_true", help="显示Agent树")
    args = parser.parse_args()

    console.clear()

    if args.tasks:
        show_task_list()
        return

    if args.tree:
        show_agent_tree()
        return

    log_file = get_latest_task_log()

    if not log_file:
        console.print("[warning]未找到日志文件，等待任务执行...[/warning]")
        console.print("[info]提示: 运行 'fractalclaw run' 启动交互会话[/info]")
        while not log_file:
            time.sleep(1)
            log_file = get_latest_task_log()

    try:
        for line in tail_f(log_file):
            render_event(line)
    except KeyboardInterrupt:
        console.print("\n[warning]✦ 监控网络已断开。[/warning]")


if __name__ == "__main__":
    main()
