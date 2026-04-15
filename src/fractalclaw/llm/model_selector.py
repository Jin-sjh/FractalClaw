"""模型选择器"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING

from .model_profile import (
    ModelProfile,
    ModelRegistry,
    ModelTag,
    get_default_registry
)

if TYPE_CHECKING:
    from .task_analyzer import TaskAnalyzer
    from .weight_calculator import DynamicWeightCalculator, WeightConfig


class TaskComplexity(Enum):
    """任务复杂度"""
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


class TaskType(Enum):
    """任务类型"""
    CODE = "code"
    RESEARCH = "research"
    COORDINATE = "coordinate"
    TEST = "test"
    DATA = "data"
    CHAT = "chat"
    GENERAL = "general"


class TaskImportance(Enum):
    """任务重要性"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class TaskProfile:
    """任务特征"""
    complexity: TaskComplexity = TaskComplexity.MEDIUM
    task_type: TaskType = TaskType.GENERAL
    importance: TaskImportance = TaskImportance.MEDIUM
    requires_multimodal: bool = False
    requires_code: bool = False
    requires_reasoning: bool = False
    requires_fast_response: bool = False
    budget_sensitive: bool = False
    estimated_tokens: int = 1000
    custom_requirements: dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_analysis(cls, analysis: dict[str, Any]) -> "TaskProfile":
        """从分析结果创建"""
        complexity_map = {
            "simple": TaskComplexity.SIMPLE,
            "medium": TaskComplexity.MEDIUM,
            "complex": TaskComplexity.COMPLEX
        }
        
        task_type_map = {
            "code": TaskType.CODE,
            "research": TaskType.RESEARCH,
            "coordinate": TaskType.COORDINATE,
            "test": TaskType.TEST,
            "data": TaskType.DATA,
            "chat": TaskType.CHAT,
            "general": TaskType.GENERAL
        }
        
        importance_map = {
            "low": TaskImportance.LOW,
            "medium": TaskImportance.MEDIUM,
            "high": TaskImportance.HIGH
        }
        
        return cls(
            complexity=complexity_map.get(analysis.get("complexity", "medium"), TaskComplexity.MEDIUM),
            task_type=task_type_map.get(analysis.get("task_type", "general"), TaskType.GENERAL),
            importance=importance_map.get(analysis.get("importance", "medium"), TaskImportance.MEDIUM),
            requires_multimodal=analysis.get("requires_multimodal", False),
            requires_code=analysis.get("requires_code", False),
            requires_reasoning=analysis.get("requires_reasoning", False),
            requires_fast_response=analysis.get("requires_fast_response", False),
            budget_sensitive=analysis.get("budget_sensitive", False),
            estimated_tokens=analysis.get("estimated_tokens", 1000),
            custom_requirements=analysis.get("custom_requirements", {})
        )


@dataclass
class SelectionResult:
    """选择结果"""
    model: ModelProfile
    score: float
    reason: str
    estimated_cost: Optional[float] = None
    alternatives: list[ModelProfile] = field(default_factory=list)


class ModelSelector:
    """模型选择器"""
    
    SELECTION_STRATEGIES = {
        "cost_first": "优先选择成本最低的模型",
        "quality_first": "优先选择能力最强的模型",
        "balanced": "平衡成本和质量",
        "fast_first": "优先选择响应最快的模型"
    }
    
    TASK_TYPE_TAG_MAPPING = {
        TaskType.CODE: [ModelTag.CODE],
        TaskType.RESEARCH: [ModelTag.REASONING],
        TaskType.COORDINATE: [ModelTag.HIGH_CAPACITY],
        TaskType.TEST: [ModelTag.CODE],
        TaskType.DATA: [ModelTag.REASONING],
        TaskType.CHAT: [ModelTag.CHAT, ModelTag.FAST],
        TaskType.GENERAL: []
    }
    
    COMPLEXITY_TAG_MAPPING = {
        TaskComplexity.SIMPLE: [ModelTag.COST_EFFECTIVE, ModelTag.FAST],
        TaskComplexity.MEDIUM: [],
        TaskComplexity.COMPLEX: [ModelTag.HIGH_CAPACITY, ModelTag.REASONING]
    }
    
    CAPABILITY_MAPPING = {
        TaskType.CODE: "coding",
        TaskType.RESEARCH: "reasoning",
        TaskType.COORDINATE: "instruction_following",
        TaskType.TEST: "coding",
        TaskType.DATA: "analysis",
        TaskType.CHAT: "creativity",
        TaskType.GENERAL: "reasoning"
    }
    
    def __init__(
        self,
        registry: ModelRegistry = None,
        default_strategy: str = "balanced"
    ):
        self.registry = registry or get_default_registry()
        self.default_strategy = default_strategy
    
    def select(
        self,
        task_profile: TaskProfile,
        strategy: str = None,
        required_tags: list[ModelTag] = None,
        excluded_model_ids: list[str] = None
    ) -> SelectionResult:
        """选择最适合的模型"""
        strategy = strategy or self.default_strategy
        excluded_model_ids = excluded_model_ids or []
        
        candidates = self._get_candidates(task_profile, required_tags, excluded_model_ids)
        
        if not candidates:
            configured = self.registry.list_configured()
            if not configured:
                raise ValueError(
                    "没有找到任何已配置的模型。\n"
                    "请确保已设置对应模型的 API Key 环境变量。\n"
                    "例如：OPENAI_API_KEY, ANTHROPIC_API_KEY, DEEPSEEK_API_KEY 等"
                )
            
            missing_requirements = []
            if task_profile.requires_multimodal:
                missing_requirements.append("多模态能力 (multimodal)")
            if task_profile.requires_code:
                missing_requirements.append("代码能力 (code)")
            if task_profile.requires_reasoning:
                missing_requirements.append("推理能力 (reasoning)")
            
            raise ValueError(
                f"已配置的模型中，没有满足任务需求的模型。\n"
                f"任务需求: {', '.join(missing_requirements) if missing_requirements else '通用'}\n"
                f"已配置的模型: {', '.join(m.id for m in configured)}\n"
                f"请配置具有所需能力的模型，或调整任务需求。"
            )
        
        scored_candidates = self._score_candidates(candidates, task_profile, strategy)
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        
        best_model = scored_candidates[0][0]
        best_score = scored_candidates[0][1]
        
        alternatives = [c[0] for c in scored_candidates[1:4]] if len(scored_candidates) > 1 else []
        
        estimated_cost = None
        if best_model.pricing:
            estimated_cost = best_model.pricing.estimate_cost(
                task_profile.estimated_tokens,
                task_profile.estimated_tokens // 2
            )
        
        reason = self._generate_selection_reason(best_model, task_profile, strategy)
        
        return SelectionResult(
            model=best_model,
            score=best_score,
            reason=reason,
            estimated_cost=estimated_cost,
            alternatives=alternatives
        )
    
    def select_for_task_type(
        self,
        task_type: TaskType,
        complexity: TaskComplexity = TaskComplexity.MEDIUM,
        budget_sensitive: bool = False
    ) -> SelectionResult:
        """根据任务类型选择模型"""
        task_profile = TaskProfile(
            complexity=complexity,
            task_type=task_type,
            budget_sensitive=budget_sensitive
        )
        
        strategy = "cost_first" if budget_sensitive else "balanced"
        return self.select(task_profile, strategy=strategy)
    
    def _get_candidates(
        self,
        task_profile: TaskProfile,
        required_tags: list[ModelTag] = None,
        excluded_model_ids: list[str] = None
    ) -> list[ModelProfile]:
        """获取候选模型（只从已配置的模型中选择）"""
        candidates = self.registry.list_configured()
        
        excluded_model_ids = excluded_model_ids or []
        candidates = [m for m in candidates if m.id not in excluded_model_ids]
        
        if task_profile.requires_multimodal:
            candidates = [m for m in candidates if m.has_tag(ModelTag.MULTIMODAL)]
        
        if task_profile.requires_code:
            candidates = [m for m in candidates if m.has_tag(ModelTag.CODE)]
        
        if task_profile.requires_reasoning:
            candidates = [m for m in candidates if m.has_tag(ModelTag.REASONING)]
        
        if task_profile.requires_fast_response:
            candidates = [m for m in candidates if m.has_tag(ModelTag.FAST)]
        
        if required_tags:
            candidates = [m for m in candidates if m.has_all_tags(required_tags)]
        
        return candidates
    
    def _score_candidates(
        self,
        candidates: list[ModelProfile],
        task_profile: TaskProfile,
        strategy: str
    ) -> list[tuple[ModelProfile, float]]:
        """对候选模型评分"""
        scored = []
        
        for model in candidates:
            score = self._calculate_score(model, task_profile, strategy)
            scored.append((model, score))
        
        return scored
    
    def _calculate_score(
        self,
        model: ModelProfile,
        task_profile: TaskProfile,
        strategy: str
    ) -> float:
        """计算模型得分"""
        capability_score = self._get_capability_score(model, task_profile)
        cost_score = self._get_cost_score(model)
        tag_match_score = self._get_tag_match_score(model, task_profile)
        
        if strategy == "cost_first":
            weights = {"capability": 0.2, "cost": 0.6, "tag_match": 0.2}
        elif strategy == "quality_first":
            weights = {"capability": 0.6, "cost": 0.1, "tag_match": 0.3}
        elif strategy == "fast_first":
            weights = {"capability": 0.3, "cost": 0.2, "tag_match": 0.5}
            if model.has_tag(ModelTag.FAST):
                tag_match_score += 0.3
        else:
            if task_profile.budget_sensitive:
                weights = {"capability": 0.3, "cost": 0.5, "tag_match": 0.2}
            else:
                weights = {"capability": 0.5, "cost": 0.2, "tag_match": 0.3}
        
        total_score = (
            capability_score * weights["capability"] +
            cost_score * weights["cost"] +
            tag_match_score * weights["tag_match"]
        )
        
        return total_score
    
    def _get_capability_score(self, model: ModelProfile, task_profile: TaskProfile) -> float:
        """获取能力评分"""
        capability_name = self.CAPABILITY_MAPPING.get(task_profile.task_type, "reasoning")
        capability_score = model.capabilities.get_capability_score(capability_name)
        
        complexity_bonus = {
            TaskComplexity.SIMPLE: 0,
            TaskComplexity.MEDIUM: 0.5,
            TaskComplexity.COMPLEX: 1.0
        }
        
        required_level = complexity_bonus.get(task_profile.complexity, 0.5)
        
        if capability_score >= 7 and task_profile.complexity == TaskComplexity.COMPLEX:
            return capability_score / 10 + 0.2
        elif capability_score >= 5 and task_profile.complexity in [TaskComplexity.SIMPLE, TaskComplexity.MEDIUM]:
            return capability_score / 10 + 0.1
        else:
            return capability_score / 10
    
    def _get_cost_score(self, model: ModelProfile) -> float:
        """获取成本评分（成本越低分数越高）"""
        if not model.pricing:
            return 0.5
        
        avg_price = (
            model.pricing.input_price_per_1k + model.pricing.output_price_per_1k
        ) / 2
        
        if avg_price == 0:
            return 1.0
        elif avg_price <= 0.001:
            return 0.9
        elif avg_price <= 0.01:
            return 0.8
        elif avg_price <= 0.05:
            return 0.6
        elif avg_price <= 0.1:
            return 0.4
        else:
            return 0.2
    
    def _get_tag_match_score(self, model: ModelProfile, task_profile: TaskProfile) -> float:
        """获取标签匹配评分"""
        score = 0.0
        
        task_tags = self.TASK_TYPE_TAG_MAPPING.get(task_profile.task_type, [])
        complexity_tags = self.COMPLEXITY_TAG_MAPPING.get(task_profile.complexity, [])
        
        all_preferred_tags = task_tags + complexity_tags
        
        if not all_preferred_tags:
            return 0.5
        
        matched_tags = sum(1 for tag in all_preferred_tags if model.has_tag(tag))
        score = matched_tags / len(all_preferred_tags)
        
        if task_profile.importance == TaskImportance.HIGH:
            if model.has_tag(ModelTag.HIGH_CAPACITY):
                score += 0.2
        
        return min(score, 1.0)
    
    def _generate_selection_reason(
        self,
        model: ModelProfile,
        task_profile: TaskProfile,
        strategy: str
    ) -> str:
        """生成选择原因说明"""
        reasons = []
        
        reasons.append(f"选择了 {model.name} ({model.provider})")
        
        if task_profile.task_type != TaskType.GENERAL:
            reasons.append(f"任务类型: {task_profile.task_type.value}")
        
        reasons.append(f"复杂度: {task_profile.complexity.value}")
        
        if strategy == "cost_first":
            reasons.append("策略: 优先成本")
        elif strategy == "quality_first":
            reasons.append("策略: 优先质量")
        elif strategy == "fast_first":
            reasons.append("策略: 优先速度")
        else:
            reasons.append("策略: 平衡成本与质量")
        
        if model.tags:
            tag_names = [tag.value for tag in model.tags[:3]]
            reasons.append(f"模型标签: {', '.join(tag_names)}")
        
        if model.pricing:
            reasons.append(
                f"定价: ${model.pricing.input_price_per_1k:.4f}/1k输入, "
                f"${model.pricing.output_price_per_1k:.4f}/1k输出"
            )
        
        return " | ".join(reasons)
    
    def get_recommendation(
        self,
        task_profile: TaskProfile,
        top_n: int = 3
    ) -> list[SelectionResult]:
        """获取推荐模型列表"""
        results = []
        
        for strategy in ["balanced", "cost_first", "quality_first"]:
            try:
                result = self.select(task_profile, strategy=strategy)
                if result.model not in [r.model for r in results]:
                    results.append(result)
            except ValueError:
                continue
        
        return results[:top_n]


class SmartModelSelector:
    """智能模型选择器 - 整合动态权重和任务分析"""
    
    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        llm_provider: Any = None,
        weight_calculator: Optional["DynamicWeightCalculator"] = None,
        task_analyzer: Optional["TaskAnalyzer"] = None,
        enable_llm_analysis: bool = True
    ):
        self._registry = registry or get_default_registry()
        self._llm_provider = llm_provider
        self._weight_calculator = weight_calculator
        self._task_analyzer = task_analyzer
        self._enable_llm_analysis = enable_llm_analysis
        
        if self._weight_calculator is None:
            from .weight_calculator import DynamicWeightCalculator
            self._weight_calculator = DynamicWeightCalculator()
        
        if enable_llm_analysis and llm_provider and self._task_analyzer is None:
            from .task_analyzer import TaskAnalyzer
            self._task_analyzer = TaskAnalyzer(llm_provider)
    
    @property
    def registry(self) -> ModelRegistry:
        return self._registry
    
    @property
    def weight_calculator(self):
        return self._weight_calculator
    
    @property
    def task_analyzer(self):
        return self._task_analyzer
    
    async def select_smart(
        self,
        user_input: str,
        context: dict = None,
        strategy: str = None
    ) -> SelectionResult:
        """
        智能选择模型
        
        Args:
            user_input: 用户输入
            context: 可选上下文
            strategy: 可选的策略覆盖
            
        Returns:
            SelectionResult: 选择结果
        """
        if self._task_analyzer:
            analysis = await self._task_analyzer.analyze(user_input, context)
            task_profile = analysis.task_profile
        else:
            task_profile = self._rule_based_analyze(user_input)
        
        candidates = self._get_candidates(task_profile)
        
        if not candidates:
            raise ValueError("没有找到符合条件的模型")
        
        from .weight_calculator import WeightConfig
        weights = self._weight_calculator.calculate(task_profile)
        
        scored = self._score_candidates(candidates, task_profile, weights)
        scored.sort(key=lambda x: x[1], reverse=True)
        
        best_model = scored[0][0]
        best_score = scored[0][1]
        
        alternatives = [c[0] for c in scored[1:4]] if len(scored) > 1 else []
        
        estimated_cost = None
        if best_model.pricing:
            estimated_cost = best_model.pricing.estimate_cost(
                task_profile.estimated_tokens,
                task_profile.estimated_tokens // 2
            )
        
        reason = self._generate_reason(task_profile, weights, best_model)
        
        return SelectionResult(
            model=best_model,
            score=best_score,
            reason=reason,
            estimated_cost=estimated_cost,
            alternatives=alternatives
        )
    
    def select(
        self,
        task_profile: TaskProfile,
        strategy: str = None,
        required_tags: list[ModelTag] = None,
        excluded_model_ids: list[str] = None
    ) -> SelectionResult:
        """
        选择最适合的模型（兼容原有接口）
        
        Args:
            task_profile: 任务特征
            strategy: 可选的策略覆盖
            required_tags: 必需标签
            excluded_model_ids: 排除的模型ID列表
            
        Returns:
            SelectionResult: 选择结果
        """
        from .weight_calculator import WeightConfig
        
        candidates = self._get_candidates(task_profile, required_tags, excluded_model_ids)
        
        if not candidates:
            raise ValueError("没有找到符合条件的模型")
        
        weights = self._weight_calculator.calculate(task_profile)
        
        scored = self._score_candidates(candidates, task_profile, weights)
        scored.sort(key=lambda x: x[1], reverse=True)
        
        best_model = scored[0][0]
        best_score = scored[0][1]
        
        alternatives = [c[0] for c in scored[1:4]] if len(scored) > 1 else []
        
        estimated_cost = None
        if best_model.pricing:
            estimated_cost = best_model.pricing.estimate_cost(
                task_profile.estimated_tokens,
                task_profile.estimated_tokens // 2
            )
        
        reason = self._generate_reason(task_profile, weights, best_model)
        
        return SelectionResult(
            model=best_model,
            score=best_score,
            reason=reason,
            estimated_cost=estimated_cost,
            alternatives=alternatives
        )
    
    def _get_candidates(
        self,
        task_profile: TaskProfile,
        required_tags: list[ModelTag] = None,
        excluded_model_ids: list[str] = None
    ) -> list[ModelProfile]:
        """获取候选模型（只从已配置的模型中选择）"""
        candidates = self._registry.list_configured()
        
        excluded_model_ids = excluded_model_ids or []
        candidates = [m for m in candidates if m.id not in excluded_model_ids]
        
        if task_profile.requires_multimodal:
            candidates = [m for m in candidates if m.has_tag(ModelTag.MULTIMODAL)]
        
        if task_profile.requires_code:
            candidates = [m for m in candidates if m.has_tag(ModelTag.CODE)]
        
        if task_profile.requires_reasoning:
            candidates = [m for m in candidates if m.has_tag(ModelTag.REASONING)]
        
        if task_profile.requires_fast_response:
            candidates = [m for m in candidates if m.has_tag(ModelTag.FAST)]
        
        if required_tags:
            candidates = [m for m in candidates if m.has_all_tags(required_tags)]
        
        return candidates
    
    def _score_candidates(
        self,
        candidates: list[ModelProfile],
        task_profile: TaskProfile,
        weights: "WeightConfig"
    ) -> list[tuple[ModelProfile, float]]:
        """评分候选模型"""
        from .weight_calculator import WeightConfig
        
        if isinstance(weights, WeightConfig):
            w = weights
        else:
            w = WeightConfig(
                capability=weights.get("capability", 0.5),
                cost=weights.get("cost", 0.2),
                tag_match=weights.get("tag_match", 0.3)
            )
        
        scored = []
        
        for model in candidates:
            score = self._calculate_score(model, task_profile, w)
            scored.append((model, score))
        
        return scored
    
    def _calculate_score(
        self,
        model: ModelProfile,
        task_profile: TaskProfile,
        weights: "WeightConfig"
    ) -> float:
        """计算模型得分"""
        from .weight_calculator import WeightConfig
        
        if isinstance(weights, WeightConfig):
            w = weights
        else:
            w = WeightConfig(
                capability=weights.get("capability", 0.5),
                cost=weights.get("cost", 0.2),
                tag_match=weights.get("tag_match", 0.3)
            )
        
        capability_score = self._get_capability_score(model, task_profile)
        cost_score = self._get_cost_score(model)
        tag_match_score = self._get_tag_match_score(model, task_profile)
        
        total_score = (
            capability_score * w.capability +
            cost_score * w.cost +
            tag_match_score * w.tag_match
        )
        
        return total_score
    
    def _get_capability_score(self, model: ModelProfile, task_profile: TaskProfile) -> float:
        """获取能力评分"""
        capability_name = ModelSelector.CAPABILITY_MAPPING.get(
            task_profile.task_type, "reasoning"
        )
        capability_score = model.capabilities.get_capability_score(capability_name)
        
        complexity_bonus = {
            TaskComplexity.SIMPLE: 0,
            TaskComplexity.MEDIUM: 0.5,
            TaskComplexity.COMPLEX: 1.0
        }
        
        required_level = complexity_bonus.get(task_profile.complexity, 0.5)
        
        if capability_score >= 7 and task_profile.complexity == TaskComplexity.COMPLEX:
            return capability_score / 10 + 0.2
        elif capability_score >= 5 and task_profile.complexity in [TaskComplexity.SIMPLE, TaskComplexity.MEDIUM]:
            return capability_score / 10 + 0.1
        else:
            return capability_score / 10
    
    def _get_cost_score(self, model: ModelProfile) -> float:
        """获取成本评分（成本越低分数越高）"""
        if not model.pricing:
            return 0.5
        
        avg_price = (
            model.pricing.input_price_per_1k + model.pricing.output_price_per_1k
        ) / 2
        
        if avg_price == 0:
            return 1.0
        elif avg_price <= 0.001:
            return 0.9
        elif avg_price <= 0.01:
            return 0.8
        elif avg_price <= 0.05:
            return 0.6
        elif avg_price <= 0.1:
            return 0.4
        else:
            return 0.2
    
    def _get_tag_match_score(self, model: ModelProfile, task_profile: TaskProfile) -> float:
        """获取标签匹配评分"""
        task_tags = ModelSelector.TASK_TYPE_TAG_MAPPING.get(task_profile.task_type, [])
        complexity_tags = ModelSelector.COMPLEXITY_TAG_MAPPING.get(task_profile.complexity, [])
        
        all_preferred_tags = task_tags + complexity_tags
        
        if not all_preferred_tags:
            return 0.5
        
        matched_tags = sum(1 for tag in all_preferred_tags if model.has_tag(tag))
        score = matched_tags / len(all_preferred_tags)
        
        if task_profile.importance == TaskImportance.HIGH:
            if model.has_tag(ModelTag.HIGH_CAPACITY):
                score += 0.2
        
        return min(score, 1.0)
    
    def _rule_based_analyze(self, user_input: str) -> TaskProfile:
        """基于规则的任务分析（回退方案）"""
        text = user_input.lower()
        
        analysis = {
            "complexity": "medium",
            "task_type": "general",
            "importance": "medium"
        }
        
        if any(kw in text for kw in ["代码", "编程", "code", "debug"]):
            analysis["task_type"] = "code"
            analysis["requires_code"] = True
        elif any(kw in text for kw in ["研究", "分析", "research"]):
            analysis["task_type"] = "research"
        
        if any(kw in text for kw in ["复杂", "comprehensive"]):
            analysis["complexity"] = "complex"
        elif any(kw in text for kw in ["简单", "quick", "fast"]):
            analysis["complexity"] = "simple"
        
        return TaskProfile.from_analysis(analysis)
    
    def _generate_reason(
        self,
        task_profile: TaskProfile,
        weights: "WeightConfig",
        model: ModelProfile
    ) -> str:
        """生成选择原因说明"""
        from .weight_calculator import WeightConfig
        
        if isinstance(weights, WeightConfig):
            w = weights
        else:
            w = WeightConfig(
                capability=weights.get("capability", 0.5),
                cost=weights.get("cost", 0.2),
                tag_match=weights.get("tag_match", 0.3)
            )
        
        weight_explanation = self._weight_calculator.explain(task_profile)
        
        reasons = [
            f"选择了 {model.name} ({model.provider})",
            f"任务类型: {task_profile.task_type.value}",
            f"复杂度: {task_profile.complexity.value}",
            f"权重配置: 能力={w.capability:.2f}, 成本={w.cost:.2f}, 标签={w.tag_match:.2f}"
        ]
        
        if weight_explanation["matched_rules"]:
            rule_names = [r["name"] for r in weight_explanation["matched_rules"]]
            reasons.append(f"匹配规则: {', '.join(rule_names)}")
        
        return " | ".join(reasons)
    
    def get_recommendation(
        self,
        task_profile: TaskProfile,
        top_n: int = 3
    ) -> list[SelectionResult]:
        """获取推荐模型列表"""
        results = []
        
        for strategy in ["balanced", "cost_first", "quality_first"]:
            try:
                result = self.select(task_profile)
                if result.model not in [r.model for r in results]:
                    results.append(result)
            except ValueError:
                continue
        
        return results[:top_n]
