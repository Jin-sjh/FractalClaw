"""Agent Tree module for managing parent-child agent relationships."""

from __future__ import annotations

from dataclasses import dataclass, field

from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from .base import Agent


@dataclass
class TreeStats:
    total_agents: int = 0
    max_depth: int = 0
    leaf_count: int = 0
    branch_count: int = 0


class AgentTree:
    def __init__(self, owner: "Agent"):
        self._owner = owner
        self._parent: Optional["Agent"] = None
        self._children: list["Agent"] = []

    @property
    def parent(self) -> Optional["Agent"]:
        return self._parent

    @property
    def children(self) -> list["Agent"]:
        return self._children.copy()

    @property
    def is_root(self) -> bool:
        return self._parent is None

    @property
    def is_leaf(self) -> bool:
        return len(self._children) == 0

    @property
    def depth(self) -> int:
        if self.is_root:
            return 0
        return 1 + self._parent.tree.depth

    @property
    def size(self) -> int:
        return 1 + sum(child.tree.size for child in self._children)

    def add_child(self, agent: "Agent") -> None:
        if agent.tree._parent is not None:
            agent.tree._parent.tree.remove_child(agent)
        agent.tree._parent = self._owner
        self._children.append(agent)

    def remove_child(self, agent: "Agent") -> bool:
        for i, child in enumerate(self._children):
            if child.id == agent.id:
                child.tree._parent = None
                self._children.pop(i)
                return True
        return False

    def remove_child_by_id(self, agent_id: str) -> bool:
        for i, child in enumerate(self._children):
            if child.id == agent_id:
                child.tree._parent = None
                self._children.pop(i)
                return True
        return False

    def get_child(self, agent_id: str) -> Optional["Agent"]:
        for child in self._children:
            if child.id == agent_id:
                return child
        return None

    def get_child_by_name(self, name: str) -> Optional["Agent"]:
        for child in self._children:
            if child.name == name:
                return child
        return None

    def get_children_by_role(self, role: Any) -> list["Agent"]:
        return [child for child in self._children if child.config.role == role]

    def get_siblings(self) -> list["Agent"]:
        if self._parent is None:
            return []
        return [
            child for child in self._parent.tree.children
            if child.id != self._owner.id
        ]

    def get_ancestors(self) -> list["Agent"]:
        ancestors: list["Agent"] = []
        current = self._parent
        while current is not None:
            ancestors.append(current)
            current = current.tree.parent
        return ancestors

    def get_descendants(self) -> list["Agent"]:
        descendants: list["Agent"] = []
        for child in self._children:
            descendants.append(child)
            descendants.extend(child.tree.get_descendants())
        return descendants

    def get_root(self) -> "Agent":
        if self.is_root:
            return self._owner
        return self._parent.tree.get_root()

    def find_by_id(self, agent_id: str) -> Optional["Agent"]:
        if self._owner.id == agent_id:
            return self._owner
        for child in self._children:
            found = child.tree.find_by_id(agent_id)
            if found:
                return found
        return None

    def find_by_name(self, name: str) -> Optional["Agent"]:
        if self._owner.name == name:
            return self._owner
        for child in self._children:
            found = child.tree.find_by_name(name)
            if found:
                return found
        return None

    def find_all(self, predicate: Callable[["Agent"], bool]) -> list["Agent"]:
        results: list["Agent"] = []
        if predicate(self._owner):
            results.append(self._owner)
        for child in self._children:
            results.extend(child.tree.find_all(predicate))
        return results

    def traverse_preorder(self, visitor: Callable[["Agent"], None]) -> None:
        visitor(self._owner)
        for child in self._children:
            child.tree.traverse_preorder(visitor)

    def traverse_postorder(self, visitor: Callable[["Agent"], None]) -> None:
        for child in self._children:
            child.tree.traverse_postorder(visitor)
        visitor(self._owner)

    def traverse_levelorder(self, visitor: Callable[["Agent"], None]) -> None:
        from collections import deque
        queue: deque["Agent"] = deque([self._owner])
        while queue:
            agent = queue.popleft()
            visitor(agent)
            queue.extend(agent.tree.children)

    def get_leaves(self) -> list["Agent"]:
        if self.is_leaf:
            return [self._owner]
        leaves: list["Agent"] = []
        for child in self._children:
            leaves.extend(child.tree.get_leaves())
        return leaves

    def get_stats(self) -> TreeStats:
        stats = TreeStats()
        stats.total_agents = self.size
        stats.max_depth = self._get_max_depth()
        stats.leaf_count = len(self.get_leaves())
        stats.branch_count = stats.total_agents - stats.leaf_count
        return stats

    def _get_max_depth(self, current_depth: int = 0) -> int:
        if self.is_leaf:
            return current_depth
        return max(
            child.tree._get_max_depth(current_depth + 1)
            for child in self._children
        )

    def get_path_to_root(self) -> list["Agent"]:
        path = [self._owner]
        current = self._parent
        while current is not None:
            path.append(current)
            current = current.tree.parent
        return path

    def get_distance_to(self, agent: "Agent") -> Optional[int]:
        if agent.id == self._owner.id:
            return 0

        my_path = set(a.id for a in self.get_path_to_root())
        target_path = agent.tree.get_path_to_root()

        for i, a in enumerate(target_path):
            if a.id in my_path:
                ancestor = a
                dist_to_ancestor = self.depth - ancestor.tree.depth
                dist_from_ancestor = i
                return dist_to_ancestor + dist_from_ancestor

        return None

    def clear_children(self) -> None:
        for child in self._children:
            child.tree._parent = None
        self._children.clear()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self._owner.id,
            "name": self._owner.name,
            "role": self._owner.config.role.value,
            "parent_id": self._parent.id if self._parent else None,
            "children": [child.tree.to_dict() for child in self._children],
            "depth": self.depth,
            "size": self.size,
        }
