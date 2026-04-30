"""Fractal tree data structure for monitoring visualization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .events import EventType, FractalEvent


@dataclass
class FractalTreeNode:
    """A node in the fractal agent tree."""

    agent_id: str
    agent_name: str
    agent_role: str
    parent_id: Optional[str] = None
    depth: int = 0
    state: str = "idle"
    branch_path: str = "root"
    children: list[FractalTreeNode] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def is_root(self) -> bool:
        return self.parent_id is None

    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0

    def add_child(self, node: FractalTreeNode) -> None:
        """Add a child node."""
        node.parent_id = self.agent_id
        node.depth = self.depth + 1
        self.children.append(node)

    def find_node(self, agent_id: str) -> Optional[FractalTreeNode]:
        """Find a node by agent ID."""
        if self.agent_id == agent_id:
            return self
        for child in self.children:
            found = child.find_node(agent_id)
            if found:
                return found
        return None

    def update_state(self, state: str) -> None:
        """Update the node state."""
        self.state = state
        self.updated_at = __import__("datetime").datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "state": self.state,
            "branch_path": self.branch_path,
            "children": [child.to_dict() for child in self.children],
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def get_tree_lines(
        self,
        prefix: str = "",
        is_last: bool = True,
        use_fractal_symbols: bool = True,
    ) -> list[str]:
        """Generate ASCII tree lines with fractal symbols."""
        symbols = {
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

        if use_fractal_symbols:
            role_symbol = symbols.get(self.agent_role, "●")
            state_symbol = symbols.get(self.state, "○")
            if self.agent_role == "root":
                node_symbol = role_symbol
            elif self.state in ("executing", "delegating"):
                node_symbol = state_symbol
            else:
                node_symbol = role_symbol
        else:
            node_symbol = "├─" if not is_last else "└─"

        state_color_map = {
            "idle": "white",
            "planning": "yellow",
            "thinking": "cyan",
            "executing": "green",
            "delegating": "magenta",
            "error": "red",
            "stopped": "dim red",
        }

        state_display = f"[{state_color_map.get(self.state, 'white')}]{self.state}[/{state_color_map.get(self.state, 'white')}]"
        line = f"{prefix}{node_symbol} {self.agent_name} ({state_display})"

        lines = [line]

        child_prefix = prefix + ("    " if is_last else "│   ")
        for i, child in enumerate(self.children):
            is_last_child = i == len(self.children) - 1
            lines.extend(child.get_tree_lines(child_prefix, is_last_child, use_fractal_symbols))

        return lines


class FractalTree:
    """Manages the fractal agent tree for visualization."""

    def __init__(self):
        self._root: Optional[FractalTreeNode] = None
        self._nodes: dict[str, FractalTreeNode] = {}
        self._task_id: Optional[str] = None

    @property
    def root(self) -> Optional[FractalTreeNode]:
        return self._root

    def set_task(self, task_id: str) -> None:
        """Set the current task ID."""
        self._task_id = task_id
        self._root = None
        self._nodes.clear()

    def add_node(self, node: FractalTreeNode) -> None:
        """Add a node to the tree."""
        self._nodes[node.agent_id] = node

        if node.parent_id is None:
            self._root = node
        elif node.parent_id in self._nodes:
            self._nodes[node.parent_id].add_child(node)

    def update_node_state(self, agent_id: str, state: str) -> bool:
        """Update a node's state."""
        node = self._nodes.get(agent_id)
        if node:
            node.update_state(state)
            return True
        return False

    def find_node(self, agent_id: str) -> Optional[FractalTreeNode]:
        """Find a node by agent ID."""
        return self._nodes.get(agent_id)

    def apply_event(self, event: FractalEvent) -> None:
        """Apply a fractal event to update the tree."""
        if event.event_type == EventType.AGENT_SPAWNED:
            node = FractalTreeNode(
                agent_id=event.agent_id or "",
                agent_name=event.agent_name or "Unknown",
                agent_role=event.agent_role or "worker",
                parent_id=event.parent_agent_id,
                depth=event.depth,
                state=event.state or "idle",
                branch_path=event.branch_path,
                created_at=event.timestamp,
            )
            self.add_node(node)

        elif event.event_type == EventType.AGENT_STATE_CHANGED:
            if event.agent_id:
                self.update_node_state(event.agent_id, event.state or "idle")

        elif event.event_type == EventType.TASK_STARTED:
            if event.task_id:
                self.set_task(event.task_id)

    def get_stats(self) -> dict[str, Any]:
        """Get tree statistics."""
        if not self._root:
            return {
                "total_agents": 0,
                "max_depth": 0,
                "leaf_count": 0,
                "active_count": 0,
            }

        total = len(self._nodes)
        max_depth = max(n.depth for n in self._nodes.values()) if self._nodes else 0
        leaf_count = sum(1 for n in self._nodes.values() if n.is_leaf)
        active_count = sum(
            1 for n in self._nodes.values()
            if n.state in ("executing", "delegating", "planning", "thinking")
        )

        return {
            "total_agents": total,
            "max_depth": max_depth,
            "leaf_count": leaf_count,
            "active_count": active_count,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self._task_id,
            "root": self._root.to_dict() if self._root else None,
            "stats": self.get_stats(),
        }

    def render_tree(self, use_fractal_symbols: bool = True) -> str:
        """Render the tree as a string."""
        if not self._root:
            return "No active agents."

        lines = self._root.get_tree_lines(use_fractal_symbols=use_fractal_symbols)
        return "\n".join(lines)
