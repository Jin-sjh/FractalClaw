import re
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .daily_log import DailyLogManager


class WorkingMemoryManager:
    def __init__(self, memory_base_path: Path):
        self._base_path = memory_base_path
        self._working_memory_path = memory_base_path / "working_memory.md"

    async def initialize(self) -> None:
        if not self._working_memory_path.exists():
            self._create_working_memory_file()

    def _create_working_memory_file(self) -> None:
        content = f"""---
type: working_memory
last_heartbeat: {datetime.now().isoformat()}
heartbeat_interval_hours: 24
---

# 工作记忆

"""
        self._working_memory_path.write_text(content, encoding="utf-8")

    async def generate_daily_summary(self, daily_log_path: Path) -> str:
        if not daily_log_path.exists():
            return ""
        content = daily_log_path.read_text(encoding="utf-8")
        session_count_match = re.search(r"session_count: (\d+)", content)
        session_count = int(session_count_match.group(1)) if session_count_match else 0
        success_count = content.count("✅")
        fail_count = content.count("❌")
        task_matches = re.findall(r"\*\*任务\*\*: ([^\n]+)", content)
        result_matches = re.findall(r"\*\*结果\*\*: [^\n]+ - ([^\n]+)", content)
        summary_parts = [f"{session_count}个session，{success_count}成功{fail_count}失败"]
        if task_matches and result_matches:
            main_tasks = [f"{t}({r})" for t, r in zip(task_matches[:3], result_matches[:3])]
            summary_parts.append("主要完成：" + "、".join(main_tasks))
        return "。".join(summary_parts) + "。"

    async def append_to_working_memory(self, date: str, summary: str, daily_log_relative_path: str) -> None:
        if not self._working_memory_path.exists():
            await self.initialize()
        entry = f"\n## {date}\n\n{daily_log_relative_path}：{summary}\n"
        with open(self._working_memory_path, "a", encoding="utf-8") as f:
            f.write(entry)
        self._update_heartbeat_time()

    def _update_heartbeat_time(self) -> None:
        content = self._working_memory_path.read_text(encoding="utf-8")
        content = re.sub(
            r"last_heartbeat: [^\n]+",
            f"last_heartbeat: {datetime.now().isoformat()}",
            content,
        )
        self._working_memory_path.write_text(content, encoding="utf-8")

    async def heartbeat(self, daily_log_manager: "DailyLogManager") -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        daily_log_path = daily_log_manager._get_daily_log_path(today)
        if not daily_log_path.exists():
            return
        summary = await self.generate_daily_summary(daily_log_path)
        if summary:
            relative_path = f"content/memory/daily/{today}.md"
            await self.append_to_working_memory(today, summary, relative_path)

    def read_working_memory(self, days: Optional[int] = None) -> str:
        if not self._working_memory_path.exists():
            return ""
        content = self._working_memory_path.read_text(encoding="utf-8")
        if days is None:
            return content
        sections = re.split(r"\n## \d{4}-\d{2}-\d{2}\n", content)
        if len(sections) <= 1:
            return content
        dates = re.findall(r"\n## (\d{4}-\d{2}-\d{2})\n", content)
        recent_dates = dates[-days:] if len(dates) > days else dates
        result = sections[0]
        for date in recent_dates:
            pattern = rf"\n## {date}\n.*?(?=\n## \d{{4}}-\d{{2}}-\d{{2}}\n|$)"
            match = re.search(pattern, content, re.DOTALL)
            if match:
                result += match.group(0)
        return result

    async def progressive_disclose(self, date: str, level: int = 1, daily_log_manager: Optional["DailyLogManager"] = None) -> str:
        if level == 1:
            content = self._working_memory_path.read_text(encoding="utf-8")
            pattern = rf"\n## {date}\n(.*?)(?=\n## \d{{4}}-\d{{2}}-\d{{2}}\n|$)"
            match = re.search(pattern, content, re.DOTALL)
            if match:
                return match.group(1).strip()
            return ""
        elif level == 2:
            if daily_log_manager:
                return daily_log_manager.get_daily_log(date) or ""
            return ""
        elif level == 3:
            if daily_log_manager:
                log_content = daily_log_manager.get_daily_log(date)
                if log_content:
                    detail_paths = re.findall(r"\*\*详情\*\*: ([^\n]+)", log_content)
                    full_content = log_content
                    for path in detail_paths:
                        full_path = self._base_path.parent / path
                        if full_path.exists():
                            full_content += f"\n\n---\n\n# 完整对话: {path}\n\n"
                            full_content += full_path.read_text(encoding="utf-8")
                    return full_content
            return ""
        return ""
