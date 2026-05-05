"""FractalClaw Monitor - Real-time TUI monitoring panel with fractal tree visualization."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich import box

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

cyber_theme = Theme({
    "info": "dim cyan",
    "warning": "color(141)",
    "error": "bold red",
    "success": "bold green",
    "agent": "bold color(141)",
    "tool": "bold yellow",
    "result": "bold green",
    "message": "bold bright_magenta",
    "timestamp": "dim white",
    "fractal_root": "bold bright_magenta",
    "fractal_coord": "bold cyan",
    "fractal_worker": "bold green",
    "fractal_specialist": "bold yellow",
    "fractal_idle": "dim white",
    "fractal_planning": "bold yellow",
    "fractal_thinking": "bold cyan",
    "fractal_executing": "bold bright_green",
    "fractal_delegating": "bold bright_magenta",
    "fractal_error": "bold red",
    "fractal_stopped": "dim red",
})

console = Console(theme=cyber_theme)

WORKSPACE_PATH = PROJECT_ROOT / "workspace"

# Fractal symbols for different states
FRACTAL_SYMBOLS = {
    "root": "◈",
    "coordinator": "◇",
    "worker": "●",
    "specialist": "◆",
    "idle": "○",
    "planning": "◐",
    "thinking": "◑",
    "executing": "◉",
    "delegating": "◎",
    "error": "✕",
    "stopped": "⊘",
}

STATE_COLORS = {
    "idle": "fractal_idle",
    "planning": "fractal_planning",
    "thinking": "fractal_thinking",
    "executing": "fractal_executing",
    "delegating": "fractal_delegating",
    "error": "fractal_error",
    "stopped": "fractal_stopped",
}

ROLE_COLORS = {
    "root": "fractal_root",
    "coordinator": "fractal_coord",
    "worker": "fractal_worker",
    "specialist": "fractal_specialist",
}


class FractalTreeMonitor:
    """Real-time fractal tree monitor for FractalClaw."""

    def __init__(self):
        self.agents: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.max_events = 1000   # 内存缓冲区上限，足够容纳长时间任务的事件
        self.total_events_seen = 0  # 累计读取的事件总数（不受缓冲区限制）
        self.current_task_id: Optional[str] = None
        self.event_file: Optional[Path] = None
        self.last_position = 0

    def set_task(self, task_id: str) -> None:
        """Set the current task to monitor."""
        self.current_task_id = task_id
        self.agents.clear()
        self.events.clear()
        self.total_events_seen = 0
        monitor_dir = WORKSPACE_PATH / ".monitor"
        self.event_file = monitor_dir / f"{task_id}_events.jsonl"
        self.last_position = 0

    def auto_detect_task(self) -> Optional[str]:
        """Auto-detect the most recent active task."""
        if not WORKSPACE_PATH.exists():
            return None

        # First check .monitor directory for event files
        monitor_dir = WORKSPACE_PATH / ".monitor"
        if monitor_dir.exists():
            event_files = sorted(
                monitor_dir.glob("*_events.jsonl"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if event_files:
                return event_files[0].stem.replace("_events", "")

        # Fallback: find most recent task folder
        date_folders = sorted(
            [d for d in WORKSPACE_PATH.iterdir() if d.is_dir() and d.name.isdigit()],
            key=lambda x: x.name,
            reverse=True,
        )

        for date_folder in date_folders:
            task_folders = sorted(
                [t for t in date_folder.iterdir() if t.is_dir()],
                key=lambda x: x.stat().st_mtime,
                reverse=True,
            )
            if task_folders:
                return task_folders[0].name.split("_")[1] if len(task_folders[0].name.split("_")) > 1 else task_folders[0].name

        return None

    def read_new_events(self) -> list[dict[str, Any]]:
        """Read new events from the event file."""
        if not self.event_file or not self.event_file.exists():
            return []

        events = []
        try:
            with open(self.event_file, "r", encoding="utf-8") as f:
                f.seek(self.last_position)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        events.append(data)
                    except json.JSONDecodeError:
                        continue
                self.last_position = f.tell()
        except Exception:
            pass

        return events

    def process_event(self, event: dict[str, Any]) -> None:
        """Process a single event and update the tree state."""
        event_type = event.get("event_type", "")
        agent_id = event.get("agent_id")
        agent_name = event.get("agent_name", "Unknown")
        agent_role = event.get("agent_role", "worker")
        parent_id = event.get("parent_agent_id")
        state = event.get("state", "idle")
        depth = event.get("depth", 0)
        branch_path = event.get("branch_path", "root")

        # Create or update agent node for any event with agent_id
        if agent_id:
            if agent_id not in self.agents:
                # Agent doesn't exist yet - create it
                self.agents[agent_id] = {
                    "id": agent_id,
                    "name": agent_name,
                    "role": agent_role,
                    "parent_id": parent_id,
                    "state": state,
                    "depth": depth,
                    "branch_path": branch_path,
                    "children": [],
                    "created_at": event.get("timestamp", ""),
                }
                # Register as child of parent
                if parent_id and parent_id in self.agents:
                    if agent_id not in self.agents[parent_id]["children"]:
                        self.agents[parent_id]["children"].append(agent_id)
            else:
                # Agent exists - update state
                self.agents[agent_id]["state"] = state

        # Add to event log
        self.events.append(event)
        self.total_events_seen += 1
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]

    def build_tree(self) -> Optional[dict[str, Any]]:
        """Build the tree structure from agents."""
        roots = [a for a in self.agents.values() if a["parent_id"] is None]
        if not roots:
            # If no root found but agents exist, pick the one with smallest depth
            if self.agents:
                min_depth_agent = min(self.agents.values(), key=lambda a: a["depth"])
                return min_depth_agent
            return None
        return roots[0]

    def render_tree_node(self, agent_id: str, prefix: str = "", is_last: bool = True) -> Text:
        """Render a tree node with fractal symbols."""
        agent = self.agents.get(agent_id)
        if not agent:
            return Text("")

        role = agent.get("role", "worker")
        state = agent.get("state", "idle")
        name = agent.get("name", "Unknown")
        depth = agent.get("depth", 0)

        # Choose symbol based on role and state
        if role == "root":
            symbol = FRACTAL_SYMBOLS["root"]
        elif role == "coordinator":
            symbol = FRACTAL_SYMBOLS["coordinator"]
        elif role == "specialist":
            symbol = FRACTAL_SYMBOLS["specialist"]
        elif state in ("executing", "delegating"):
            symbol = FRACTAL_SYMBOLS.get(state, FRACTAL_SYMBOLS["worker"])
        else:
            symbol = FRACTAL_SYMBOLS.get(state, FRACTAL_SYMBOLS["idle"])

        # Build indentation
        indent = "    " if is_last else "│   "
        connector = "└── " if is_last else "├── "
        line_prefix = prefix + connector

        # Color based on state
        state_color = STATE_COLORS.get(state, "white")
        role_color = ROLE_COLORS.get(role, "white")

        text = Text()
        text.append(line_prefix, style="dim")
        text.append(f"{symbol} ", style=role_color)
        text.append(f"{name}", style="bold white")
        text.append(f" [{state}]", style=state_color)

        if depth > 0:
            text.append(f" d={depth}", style="dim")

        return text

    def render_tree_lines(self, agent_id: str, prefix: str = "", is_last: bool = True) -> list[Text]:
        """Recursively render tree lines."""
        lines = []
        node_text = self.render_tree_node(agent_id, prefix, is_last)
        if node_text:
            lines.append(node_text)

        agent = self.agents.get(agent_id)
        if agent:
            children = agent.get("children", [])
            child_prefix = prefix + ("    " if is_last else "│   ")
            for i, child_id in enumerate(children):
                is_last_child = i == len(children) - 1
                lines.extend(self.render_tree_lines(child_id, child_prefix, is_last_child))

        return lines

    def get_fractal_tree_panel(self) -> Panel:
        """Generate the fractal tree panel."""
        root = self.build_tree()

        if not root:
            return Panel(
                Align.center(Text("⏳ Waiting for agents...", style="dim")),
                title="[bold bright_magenta]◈ Fractal Tree[/bold bright_magenta]",
                border_style="bright_magenta",
                box=box.ROUNDED,
            )

        tree_text = Text()
        lines = self.render_tree_lines(root["id"], "", True)
        for i, line in enumerate(lines):
            tree_text.append(line)
            if i < len(lines) - 1:
                tree_text.append("\n")

        # Add stats
        stats = self.get_stats()
        stats_text = Text(
            f"\n[ Agents: {stats['total']} | Depth: {stats['max_depth']} | Active: {stats['active']} ]",
            style="dim cyan",
        )
        tree_text.append(stats_text)

        return Panel(
            tree_text,
            title="[bold bright_magenta]◈ Fractal Tree[/bold bright_magenta]",
            border_style="bright_magenta",
            box=box.ROUNDED,
        )

    def get_event_log_panel(self) -> Panel:
        """Generate the event log panel."""
        if not self.events:
            return Panel(
                Align.center(Text("No events yet...", style="dim")),
                title="[bold cyan]◉ Event Stream[/bold cyan]",
                border_style="cyan",
                box=box.ROUNDED,
            )

        event_text = Text()
        recent_events = self.events[-20:]

        for i, event in enumerate(recent_events):
            timestamp = event.get("timestamp", "")
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    ts = dt.strftime("%H:%M:%S")
                except Exception:
                    ts = timestamp[:8]
            else:
                ts = "--:--:--"

            event_type = event.get("event_type", "unknown")
            agent_name = event.get("agent_name", "-")
            message = event.get("message", "")

            # Color by event type
            event_colors = {
                "agent_spawned": "bright_green",
                "agent_state_changed": "yellow",
                "wave_started": "cyan",
                "wave_finished": "blue",
                "tool_called": "yellow",
                "tool_result": "green",
                "delegation_created": "bright_magenta",
                "delegation_rejected": "red",
                "delegation_result": "green" if event.get("metadata", {}).get("success") else "red",
                "task_started": "bold cyan",
                "task_completed": "bold green",
                "task_failed": "bold red",
                "plan_created": "yellow",
                "replan_triggered": "bright_red",
            }
            color = event_colors.get(event_type, "white")

            line = Text()
            line.append(f"[{ts}] ", style="dim")
            line.append(f"{event_type:20s}", style=color)
            if agent_name and agent_name != "-":
                line.append(f" {agent_name:15s}", style="bright_magenta")
            if message:
                line.append(f" | {message[:50]}", style="white")
            line.append("\n")
            event_text.append(line)

        return Panel(
            event_text,
            title="[bold cyan]◉ Event Stream[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED,
            height=25,
        )

    def get_stats(self) -> dict[str, int]:
        """Get agent statistics."""
        total = len(self.agents)
        max_depth = max((a["depth"] for a in self.agents.values()), default=0)
        active = sum(
            1 for a in self.agents.values()
            if a["state"] in ("executing", "delegating", "planning", "thinking")
        )
        return {"total": total, "max_depth": max_depth, "active": active}

    def get_status_bar(self) -> Text:
        """Generate the status bar."""
        stats = self.get_stats()
        status = Text()
        status.append("  FractalClaw Monitor ", style="bold bright_magenta")
        status.append("│ ", style="dim")
        status.append(f"Task: {self.current_task_id or 'None'} ", style="cyan")
        status.append("│ ", style="dim")
        status.append(f"Agents: {stats['total']} ", style="green")
        status.append("│ ", style="dim")
        status.append(f"Active: {stats['active']} ", style="yellow" if stats['active'] > 0 else "dim")
        status.append("│ ", style="dim")
        status.append(f"Depth: {stats['max_depth']} ", style="cyan")
        status.append("│ ", style="dim")
        status.append(f"Events: {self.total_events_seen} ", style="dim")
        if self.total_events_seen > len(self.events):
            status.append(f"(showing last {len(self.events)}) ", style="dim")
        return status

    def update(self) -> Layout:
        """Update and return the full layout."""
        # Dynamic re-detection: check if a newer task has started
        latest_task_id = self.auto_detect_task()
        if latest_task_id and latest_task_id != self.current_task_id:
            self.set_task(latest_task_id)

        # Read new events
        new_events = self.read_new_events()
        for event in new_events:
            self.process_event(event)

        # Build layout
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=1),
        )
        layout["main"].split_row(
            Layout(name="tree", ratio=2),
            Layout(name="events", ratio=3),
        )

        # Header
        header_text = Text()
        header_text.append("\n  ")
        header_text.append("◈", style="bold bright_magenta")
        header_text.append(" FractalClaw ", style="bold white")
        header_text.append("Live Monitor ", style="dim")
        header_text.append("◈", style="bold bright_magenta")
        header_text.append("\n")
        layout["header"].update(
            Panel(header_text, border_style="bright_magenta", box=box.ROUNDED, padding=(0, 1))
        )

        # Tree panel
        layout["tree"].update(self.get_fractal_tree_panel())

        # Events panel
        layout["events"].update(self.get_event_log_panel())

        # Footer
        layout["footer"].update(self.get_status_bar())

        return layout


def get_latest_event_file() -> Optional[Path]:
    """Get the most recent event file."""
    monitor_dir = WORKSPACE_PATH / ".monitor"
    if not monitor_dir.exists():
        return None

    event_files = sorted(
        monitor_dir.glob("*_events.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    return event_files[0] if event_files else None


def main():
    """Main entry point for the monitor."""
    import argparse

    parser = argparse.ArgumentParser(description="FractalClaw Monitor")
    parser.add_argument("--task", help="Specific task ID to monitor")
    parser.add_argument("--tasks", action="store_true", help="Show task list")
    parser.add_argument("--tree", action="store_true", help="Show static agent tree")
    parser.add_argument("--refresh", type=float, default=0.5, help="Refresh interval in seconds")
    args = parser.parse_args()

    if args.tasks:
        show_task_list()
        return

    if args.tree:
        show_static_tree()
        return

    monitor = FractalTreeMonitor()

    if args.task:
        monitor.set_task(args.task)
    else:
        # Auto-detect task
        task_id = monitor.auto_detect_task()
        if task_id:
            monitor.set_task(task_id)
        else:
            console.print("[warning]⏳ No active tasks found. Waiting...[/warning]")
            console.print("[info]Run 'fractal run' or 'fractal task <instruction>' in another terminal.[/info]")
            # Wait for a task to start
            while not task_id:
                time.sleep(2)
                task_id = monitor.auto_detect_task()
            monitor.set_task(task_id)
            console.clear()

    console.print("[bold bright_magenta]◈ FractalClaw Monitor Started[/bold bright_magenta]")
    console.print(f"[dim]Monitoring task: {monitor.current_task_id}[/dim]\n")

    try:
        with Live(monitor.update(), refresh_per_second=2, screen=True) as live:
            while True:
                time.sleep(args.refresh)
                live.update(monitor.update())
    except KeyboardInterrupt:
        console.print("\n[warning]✦ Monitor stopped.[/warning]")


def show_task_list() -> None:
    """Display the list of tasks."""
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

            metadata_file = task_folder / "memory" / "semantic" / "task_metadata.yaml"
            if metadata_file.exists():
                try:
                    import yaml
                    with open(metadata_file, "r", encoding="utf-8") as f:
                        metadata = yaml.safe_load(f)

                    status = metadata.get("status", "unknown")
                    status_color = {
                        "pending": "yellow",
                        "running": "cyan",
                        "completed": "green",
                        "failed": "red",
                        "cancelled": "dim",
                    }.get(status, "white")

                    table.add_row(
                        task_folder.name[:30],
                        f"[{status_color}]{status}[/{status_color}]",
                        metadata.get("timestamps", {}).get("created", "")[:19],
                    )
                except Exception:
                    pass

    console.print(table)


def show_static_tree() -> None:
    """Display a static agent tree example."""
    console.print("\n[bold color(141)]Agent 树结构示例:[/bold color(141)]")
    console.print("  ◈ RootAgent (planning)")
    console.print("  ├── ◇ CoordinatorAgent")
    console.print("  │   ├── ● WorkerAgent-1 (executing)")
    console.print("  │   ├── ● WorkerAgent-2 (thinking)")
    console.print("  │   └── ○ WorkerAgent-3 (idle)")
    console.print("  └── ◆ SpecialistAgent (delegating)")
    console.print("      └── ○ SubWorker (idle)")
    console.print("\n[dim]符号说明:[/dim]")
    console.print("  ◈ 根节点  ◇ 协调器  ◆ 专家  ● 执行中  ○ 空闲  ✕ 错误")


if __name__ == "__main__":
    main()
