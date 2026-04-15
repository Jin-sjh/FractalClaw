import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import SessionSummary


class DailyLogManager:
    def __init__(self, memory_base_path: Path):
        self._base_path = memory_base_path

    def _get_daily_log_path(self, date: str) -> Path:
        return self._base_path / "episodic" / "daily" / f"{date}.md"

    async def append_session_summary(self, summary: SessionSummary) -> None:
        date_str = summary.started_at.strftime("%Y-%m-%d")
        log_path = self._get_daily_log_path(date_str)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        if not log_path.exists():
            self._create_log_file(log_path, date_str)

        session_block = self._format_session_block(summary)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(session_block)

        self._update_log_metadata(log_path)

    def _create_log_file(self, path: Path, date: str) -> None:
        content = f"""---
date: {date}
created: {datetime.now().isoformat()}
updated: {datetime.now().isoformat()}
session_count: 0
task_count: 0
---

# {date} 日志

"""
        path.write_text(content, encoding="utf-8")

    def _format_session_block(self, summary: SessionSummary) -> str:
        status_icon = "[OK]" if summary.result_status == "success" else "[FAIL]"
        time_range = f"{summary.started_at.strftime('%H:%M')}-{summary.completed_at.strftime('%H:%M')}"
        
        if summary.task_id:
            return f"""
## Task: {summary.task_id} - {summary.task[:50]}

### Session ({time_range})

**任务**: {summary.task}
**结果**: {status_icon} {summary.result_status} - {summary.result_summary}
**详情**: {summary.session_file_path}
"""
        else:
            return f"""
## Session ({time_range})

**任务**: {summary.task}
**结果**: {status_icon} {summary.result_status} - {summary.result_summary}
**详情**: {summary.session_file_path}
"""

    def _update_log_metadata(self, path: Path) -> None:
        content = path.read_text(encoding="utf-8")
        content = re.sub(
            r"session_count: (\d+)",
            lambda m: f"session_count: {int(m.group(1)) + 1}",
            content,
        )
        content = re.sub(
            r"updated: [^\n]+",
            f"updated: {datetime.now().isoformat()}",
            content,
        )
        path.write_text(content, encoding="utf-8")

    def get_daily_log(self, date: str) -> Optional[str]:
        log_path = self._get_daily_log_path(date)
        if log_path.exists():
            return log_path.read_text(encoding="utf-8")
        return None

    def list_dates(self) -> list[str]:
        daily_dir = self._get_daily_log_path("").parent
        if not daily_dir.exists():
            return []
        return sorted([f.stem for f in daily_dir.glob("*.md")])

    def get_recent_logs(self, days: int = 7) -> list[str]:
        dates = self.list_dates()
        recent_dates = dates[-days:] if len(dates) > days else dates
        logs = []
        for date in recent_dates:
            log = self.get_daily_log(date)
            if log:
                logs.append(log)
        return logs
