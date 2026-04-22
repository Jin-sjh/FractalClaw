"""动态权重计算器"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional

from .model_selector import TaskComplexity, TaskImportance, TaskProfile, TaskType


@dataclass
class WeightConfig:
    """权重配置"""
    capability: float
    cost: float
    tag_match: float
    
    def normalize(self) -> "WeightConfig":
        """归一化权重，确保总和为 1.0"""
        total = self.capability + self.cost + self.tag_match
        if total == 0:
            return WeightConfig(0/3, 1/3, 1/3)
        return WeightConfig(
            self.capability / total,
            self.cost / total,
            self.tag_match / total
        )
    
    def to_dict(self) -> dict[str, float]:
        return {
            "capability": self.capability,
            "cost": self.cost,
            "tag_match": self.tag_match
        }


@dataclass
class WeightRule:
    """权重规则定义"""
    name: str
    condition: Callable[[TaskProfile], bool]
    weights: WeightConfig
    priority: int = 0
    description: str = ""


DEFAULT_WEIGHT_RULES: list[WeightRule] = [
    WeightRule(
        name="high_importance",
        condition=lambda p: p.importance == TaskImportance.HIGH,
        weights=WeightConfig(capability=0.65, cost=0.10, tag_match=0.25),
        priority=10,
        description="高重要性任务优先选择能力强的模型"
    ),
    WeightRule(
        name="complex_task",
        condition=lambda p: p.complexity == TaskComplexity.COMPLEX,
        weights=WeightConfig(capability=0.60, cost=0.15, tag_match=0.25),
        priority=8,
        description="复杂任务需要更强的推理能力"
    ),
    WeightRule(
        name="simple_task",
        condition=lambda p: p.complexity == TaskComplexity.SIMPLE,
        weights=WeightConfig(capability=0.25, cost=0.55, tag_match=0.20),
        priority=5,
        description="简单任务优先选择性价比高的模型"
    ),
    WeightRule(
        name="fast_response",
        condition=lambda p: p.requires_fast_response,
        weights=WeightConfig(capability=0.25, cost=0.20, tag_match=0.55),
        priority=15,
        description="需要快速响应时优先选择速度快的模型"
    ),
    WeightRule(
        name="budget_sensitive",
        condition=lambda p: p.budget_sensitive,
        weights=WeightConfig(capability=0.25, cost=0.60, tag_match=0.15),
        priority=12,
        description="预算敏感时优先选择便宜的模型"
    ),
    WeightRule(
        name="code_task",
        condition=lambda p: p.task_type == TaskType.CODE or p.requires_code,
        weights=WeightConfig(capability=0.55, cost=0.20, tag_match=0.25),
        priority=6,
        description="代码任务需要较强的编程能力"
    ),
    WeightRule(
        name="research_task",
        condition=lambda p: p.task_type == TaskType.RESEARCH or p.requires_reasoning,
        weights=WeightConfig(capability=0.60, cost=0.15, tag_match=0.25),
        priority=6,
        description="研究任务需要较强的推理能力"
    ),
    WeightRule(
        name="chat_task",
        condition=lambda p: p.task_type == TaskType.CHAT,
        weights=WeightConfig(capability=0.35, cost=0.35, tag_match=0.30),
        priority=4,
        description="聊天任务平衡能力和成本"
    ),
]


class DynamicWeightCalculator:
    """动态权重计算器"""
    
    DEFAULT_WEIGHTS = WeightConfig(capability=0.50, cost=0.20, tag_match=0.30)
    
    def __init__(
        self,
        rules: Optional[list[WeightRule]] = None,
        merge_strategy: Literal["override", "average", "weighted"] = "weighted"
    ):
        self._rules = sorted(
            rules or DEFAULT_WEIGHT_RULES,
            key=lambda r: r.priority,
            reverse=True
        )
        self._merge_strategy = merge_strategy
    
    def calculate(self, task_profile: TaskProfile) -> WeightConfig:
        """根据任务特征计算权重"""
        matched_rules = [
            rule for rule in self._rules
            if rule.condition(task_profile)
        ]
        
        if not matched_rules:
            return self.DEFAULT_WEIGHTS
        
        if self._merge_strategy == "override":
            return matched_rules[0].weights.normalize()
        elif self._merge_strategy == "average":
            return self._average_weights(matched_rules)
        else:
            return self._weighted_average(matched_rules)
    
    def _average_weights(self, rules: list[WeightRule]) -> WeightConfig:
        """简单平均合并"""
        n = len(rules)
        total_cap = sum(r.weights.capability for r in rules)
        total_cost = sum(r.weights.cost for r in rules)
        total_tag = sum(r.weights.tag_match for r in rules)
        
        return WeightConfig(
            total_cap / n, total_cost / n, total_tag / n
        ).normalize()
    
    def _weighted_average(self, rules: list[WeightRule]) -> WeightConfig:
        """按优先级加权平均"""
        total_priority = sum(r.priority for r in rules)
        if total_priority == 0:
            return self._average_weights(rules)
        
        weighted_cap = sum(
            r.weights.capability * r.priority for r in rules
        ) / total_priority
        weighted_cost = sum(
            r.weights.cost * r.priority for r in rules
        ) / total_priority
        weighted_tag = sum(
            r.weights.tag_match * r.priority for r in rules
        ) / total_priority
        
        return WeightConfig(
            weighted_cap, weighted_cost, weighted_tag
        ).normalize()
    
    def add_rule(self, rule: WeightRule) -> None:
        """添加新规则"""
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)
    
    def remove_rule(self, name: str) -> bool:
        """移除规则"""
        for i, rule in enumerate(self._rules):
            if rule.name == name:
                self._rules.pop(i)
                return True
        return False
    
    def explain(self, task_profile: TaskProfile) -> dict[str, Any]:
        """解释权重计算过程"""
        matched = [
            {
                "name": r.name,
                "priority": r.priority,
                "weights": r.weights.to_dict(),
                "description": r.description
            }
            for r in self._rules if r.condition(task_profile)
        ]
        
        final = self.calculate(task_profile)
        
        return {
            "matched_rules": matched,
            "final_weights": final.to_dict(),
            "merge_strategy": self._merge_strategy
        }
