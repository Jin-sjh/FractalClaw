from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Any


@dataclass
class SessionMessage:
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    tool_result: Optional[str] = None


class SessionManager:
    def __init__(self, workspace_path: Path, agent_id: str, agent_name: str):
        self._workspace_path = workspace_path
        self._agent_id = agent_id
        self._agent_name = agent_name
        self._messages: list[SessionMessage] = []
        self._session_file: Optional[Path] = None
        self._started_at = datetime.now()
        self._task: Optional[str] = None

    def start(self, task: Optional[str] = None) -> None:
        self._task = task
        date_str = self._started_at.strftime("%Y-%m-%d")
        sessions_dir = self._workspace_path / "memory" / "episodic" / "sessions" / date_str
        sessions_dir.mkdir(parents=True, exist_ok=True)
        time_str = self._started_at.strftime("%H%M%S")
        self._session_file = (
            sessions_dir / f"session_{self._agent_id}_{time_str}.md"
        )
        header = self._build_header()
        self._session_file.write_text(header, encoding="utf-8")

    def _build_header(self) -> str:
        task_line = f"\n**任务**: {self._task}" if self._task else ""
        return (
            f"---\n"
            f"agent_id: {self._agent_id}\n"
            f"agent_name: {self._agent_name}\n"
            f"started: {self._started_at.isoformat()}\n"
            f"---\n\n"
            f"# 会话记录: {self._agent_name}\n\n"
            f"**开始时间**: {self._started_at.strftime('%Y-%m-%d %H:%M:%S')}{task_line}\n\n"
            f"---\n"
        )

    def add_message(self, role: str, content: str) -> None:
        msg = SessionMessage(role=role, content=content)
        self._messages.append(msg)
        self._append_to_file(msg)

    def add_tool_call(self, tool_name: str, args: dict, result: str) -> None:
        msg = SessionMessage(
            role="tool",
            content=result,
            tool_name=tool_name,
            tool_args=args,
            tool_result=result,
        )
        self._messages.append(msg)
        self._append_to_file(msg)

    def _append_to_file(self, msg: SessionMessage) -> None:
        if not self._session_file:
            return
        role_emoji = {"user": "👤", "assistant": "🤖", "system": "⚙️", "tool": "🔧"}
        emoji = role_emoji.get(msg.role, "💬")
        ts = msg.timestamp.strftime("%H:%M:%S")
        block = f"\n## {emoji} {msg.role.capitalize()} [{ts}]\n\n{msg.content}\n"
        if msg.tool_name:
            block += f"\n> 🔧 **Tool**: `{msg.tool_name}`\n"
            if msg.tool_args:
                block += f"> **Args**: `{json.dumps(msg.tool_args, ensure_ascii=False)}`\n"
        with open(self._session_file, "a", encoding="utf-8") as f:
            f.write(block)

    def finish(self, result_summary: Optional[str] = None, result_status: str = "success") -> dict[str, Any]:
        if not self._session_file:
            return {}
        completed_at = datetime.now()
        footer = f"\n---\n\n**结束时间**: {completed_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
        if result_summary:
            footer += f"\n## 执行摘要\n\n{result_summary}\n"
        with open(self._session_file, "a", encoding="utf-8") as f:
            f.write(footer)
        return {
            "session_id": self._agent_id,
            "task": self._task or "",
            "result_status": result_status,
            "result_summary": result_summary or "",
            "session_file_path": str(self._session_file.relative_to(self._workspace_path)),
            "started_at": self._started_at,
            "completed_at": completed_at,
        }
