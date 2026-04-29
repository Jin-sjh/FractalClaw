"""Rule-based task classification utilities.

Consolidates keyword-based task type / complexity / importance analysis
that was previously duplicated across config_generator, model_selector,
task_analyzer, and factory modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ClassificationResult:
    task_type: str
    complexity: str
    importance: str
    requires_code: bool = False
    requires_reasoning: bool = False
    requires_fast_response: bool = False
    requires_multimodal: bool = False
    budget_sensitive: bool = False
    estimated_tokens: int = 1000


KEYWORD_TASK_TYPE: dict[str, list[str]] = {
    "reasoning": [
        "协调", "管理", "分配", "规划", "推理", "分析", "统筹",
        "coordinate", "manage", "orchestrate", "reasoning", "plan",
        "分解", "决策", "逻辑",
    ],
    "code": [
        "代码", "编程", "开发", "coder", "code", "program",
        "debug", "编写代码", "代码审查", "python", "script",
        "测试", "验证", "test", "verify", "单元测试",
    ],
    "research": [
        "研究", "搜索", "分析", "research", "search", "analyze",
        "调研", "报告", "查询", "获取", "查找", "检索",
        "数据处理", "数据分析", "数据可视化", "data",
    ],
    "chat": [
        "对话", "聊天", "chat", "conversation", "问答", "talk",
        "简单", "快速", "格式转换",
    ],
    "writing": [
        "写作", "创作", "写文章", "撰写", "writing", "creative",
        "文案", "内容生成", "故事", "诗歌", "翻译",
    ],
}

KEYWORD_COMPLEXITY: dict[str, list[str]] = {
    "simple": [
        "简单", "基础", "快速", "简单任务", "simple", "basic", "quick",
        "minor", "small",
    ],
    "complex": [
        "复杂", "高级", "深度", "复杂任务", "complex", "comprehensive",
        "advanced", "deep", "专家", "multi", "recursive",
    ],
}

KEYWORD_IMPORTANCE: dict[str, list[str]] = {
    "high": ["重要", "关键", "核心", "critical", "important", "key", "核心任务"],
    "low": ["次要", "辅助", "optional", "辅助任务"],
}


def classify_by_keywords(
    text: str, *, is_coordinator: bool = False
) -> ClassificationResult:
    lower = text.lower()

    scores: dict[str, float] = {}
    for category, keywords in KEYWORD_TASK_TYPE.items():
        score = 0.0
        for kw in keywords:
            if kw in lower:
                score += len(kw)
        if score > 0:
            scores[category] = score

    if scores:
        sorted_types = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        task_type = sorted_types[0][0]
    else:
        task_type = "general"

    requires_code = task_type == "code"
    requires_reasoning = task_type in ("research", "reasoning")
    requires_fast_response = task_type == "chat"

    if is_coordinator and task_type == "general":
        task_type = "reasoning"
        requires_reasoning = True

    complexity = "medium"
    estimated_tokens = 1000
    for level, keywords in KEYWORD_COMPLEXITY.items():
        if any(kw in lower for kw in keywords):
            complexity = level
            break

    if complexity == "simple":
        estimated_tokens = 800
    elif complexity == "complex":
        estimated_tokens = 3000

    importance = "medium"
    for level, keywords in KEYWORD_IMPORTANCE.items():
        if any(kw in lower for kw in keywords):
            importance = level
            break

    return ClassificationResult(
        task_type=task_type,
        complexity=complexity,
        importance=importance,
        requires_code=requires_code,
        requires_reasoning=requires_reasoning,
        requires_fast_response=requires_fast_response,
        requires_multimodal=False,
        budget_sensitive=False,
        estimated_tokens=estimated_tokens,
    )


def classification_to_analysis_dict(
    result: ClassificationResult,
) -> dict[str, Any]:
    return {
        "complexity": result.complexity,
        "task_type": result.task_type,
        "importance": result.importance,
        "requires_code": result.requires_code,
        "requires_reasoning": result.requires_reasoning,
        "requires_fast_response": result.requires_fast_response,
        "requires_multimodal": result.requires_multimodal,
        "budget_sensitive": result.budget_sensitive,
        "estimated_tokens": result.estimated_tokens,
    }
