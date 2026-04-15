from pathlib import Path
from typing import Optional

from .models import SharedMemoryPacket, SharingDirection


class MemorySharing:
    def __init__(self, workspace_path: Path):
        self._workspace_path = workspace_path

    async def parent_to_child(
        self,
        parent_agent_id: str,
        child_agent_id: str,
        child_workspace: Path,
        task_context: Optional[str] = None,
        knowledge: Optional[str] = None,
        constraints: Optional[str] = None,
    ) -> None:
        packet = SharedMemoryPacket(
            direction=SharingDirection.PARENT_TO_CHILD,
            from_agent_id=parent_agent_id,
            to_agent_id=child_agent_id,
            task_context=task_context,
            knowledge=knowledge,
            constraints=constraints,
        )
        shared_dir = child_workspace / "memory" / "shared"
        shared_dir.mkdir(parents=True, exist_ok=True)
        file_path = shared_dir / "from_parent.md"
        file_path.write_text(packet.to_markdown(), encoding="utf-8")

    async def child_to_parent(
        self,
        child_agent_id: str,
        parent_agent_id: str,
        child_workspace: Path,
        parent_workspace: Path,
        result: Optional[str] = None,
        discoveries: Optional[str] = None,
        errors: Optional[str] = None,
    ) -> None:
        packet = SharedMemoryPacket(
            direction=SharingDirection.CHILD_TO_PARENT,
            from_agent_id=child_agent_id,
            to_agent_id=parent_agent_id,
            result=result,
            discoveries=discoveries,
            errors=errors,
        )
        shared_dir = parent_workspace / "memory" / "shared" / "from_children"
        shared_dir.mkdir(parents=True, exist_ok=True)
        file_path = shared_dir / f"{child_agent_id}_feedback.md"
        file_path.write_text(packet.to_markdown(), encoding="utf-8")

    async def read_from_parent(
        self, workspace_path: Path
    ) -> Optional[SharedMemoryPacket]:
        file_path = workspace_path / "memory" / "shared" / "from_parent.md"
        if not file_path.exists():
            return None
        content = file_path.read_text(encoding="utf-8")
        return self._parse_packet(content)

    async def read_child_feedback(
        self,
        workspace_path: Path,
        child_agent_id: Optional[str] = None,
    ) -> list[SharedMemoryPacket]:
        feedback_dir = workspace_path / "memory" / "shared" / "from_children"
        if not feedback_dir.exists():
            return []
        packets = []
        for f in feedback_dir.glob("*.md"):
            if child_agent_id and not f.name.startswith(child_agent_id):
                continue
            content = f.read_text(encoding="utf-8")
            packets.append(self._parse_packet(content))
        return packets

    def _parse_packet(self, content: str) -> SharedMemoryPacket:
        import yaml

        if not content.startswith("---"):
            return SharedMemoryPacket(
                direction=SharingDirection.PARENT_TO_CHILD,
                from_agent_id="unknown",
                to_agent_id="unknown",
            )
        parts = content.split("---", 2)
        fm = yaml.safe_load(parts[1]) or {}
        body = parts[2].strip() if len(parts) > 2 else ""
        packet = SharedMemoryPacket(
            direction=SharingDirection(fm.get("direction", "parent_to_child")),
            from_agent_id=fm.get("from_agent", ""),
            to_agent_id=fm.get("to_agent", ""),
        )
        sections = body.split("## ")
        for section in sections:
            if not section.strip():
                continue
            lines = section.strip().split("\n", 1)
            header = lines[0].strip()
            content_text = lines[1].strip() if len(lines) > 1 else ""
            if "任务上下文" in header:
                packet.task_context = content_text
            elif "相关知识" in header:
                packet.knowledge = content_text
            elif "约束和注意事项" in header:
                packet.constraints = content_text
            elif "执行结果" in header:
                packet.result = content_text
            elif "新发现" in header or "知识" in header:
                packet.discoveries = content_text
            elif "错误" in header or "问题" in header:
                packet.errors = content_text
        return packet
