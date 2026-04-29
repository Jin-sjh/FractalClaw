"""Agent配置生成器"""

from __future__ import annotations

import json
import uuid
import yaml
import logging
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING
from dataclasses import dataclass

from .config_validator import ConfigValidator, ValidationResult, ValidationLevel
from ..llm import (
    ModelSelector,
    ModelRegistry,
    TaskProfile,
    TaskType,
    SelectionResult,
    get_default_registry,
)
from fractalclaw.common.types import TaskComplexity, TaskDomain, TaskImportance

if TYPE_CHECKING:
    from ..llm.engine import LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    """生成结果"""
    success: bool
    agent_id: str
    config_path: Optional[Path]
    config_content: dict[str, Any]
    validation_results: list[ValidationResult]
    message: str
    model_selection: Optional[SelectionResult] = None


class AgentConfigGenerator:
    """Agent配置生成器"""
    
    ROLE_DESCRIPTIONS = {
        "root": "根Agent，负责整体任务协调和最终决策",
        "coordinator": "协调者Agent，负责分解任务和协调子Agent",
        "worker": "工作Agent，负责执行具体任务",
        "specialist": "专家Agent，在特定领域有专业能力"
    }
    
    TOOL_TEMPLATES: dict[str, dict[str, Any]] = {}

    TASK_TYPE_MAPPING = {
        "code": TaskType.CODE,
        "research": TaskType.RESEARCH,
        "reasoning": TaskType.REASONING,
        "chat": TaskType.CHAT,
        "writing": TaskType.WRITING,
        "general": TaskType.GENERAL,
        "coordinate": TaskType.REASONING,
        "test": TaskType.CODE,
        "data": TaskType.RESEARCH,
    }
    
    COMPLEXITY_INDICATORS = {
        "simple": ["简单", "基础", "快速", "简单任务", "simple", "basic", "quick"],
        "complex": ["复杂", "高级", "深度", "复杂任务", "complex", "advanced", "deep", "专家"]
    }
    
    IMPORTANCE_INDICATORS = {
        "high": ["重要", "关键", "核心", "critical", "important", "key", "核心任务"],
        "low": ["次要", "辅助", "optional", "辅助任务"]
    }
    
    def __init__(
        self,
        config_dir: Path = None,
        global_settings: dict[str, Any] = None,
        model_registry: ModelRegistry = None,
        models_config_path: Path = None,
        llm_provider: "LLMProvider" = None,
        tool_search_agent: Any = None,
        model_router: Any = None,
    ):
        from fractalclaw.tools.definitions import TOOL_TEMPLATES as _TEMPLATES
        self.TOOL_TEMPLATES = _TEMPLATES

        self.config_dir = config_dir or Path("configs/agents")
        self.global_settings = global_settings or {}
        self.validator = ConfigValidator(global_settings)
        
        self.model_registry = model_registry or get_default_registry()
        
        if models_config_path or not self.model_registry.list_all():
            config_path = models_config_path or Path("configs/models.yaml")
            if config_path.exists():
                self.model_registry.load_from_yaml(config_path)
        
        self.model_selector = ModelSelector(self.model_registry)
        self._model_router = model_router
        
        self._llm_provider = llm_provider
        self._tool_search_agent = tool_search_agent
    
    def set_llm_provider(self, provider: "LLMProvider") -> None:
        self._llm_provider = provider
    
    def set_tool_search_agent(self, agent: Any) -> None:
        self._tool_search_agent = agent
    
    def generate(
        self,
        name: str,
        description: str,
        role: str = "worker",
        capabilities: list[str] = None,
        tools: list[str] = None,
        llm_config: dict[str, Any] = None,
        parent: str = None,
        children: list[str] = None,
        save: bool = True,
        save_path: Path = None,
        task_profile: TaskProfile = None,
        auto_select_model: bool = True,
        budget_sensitive: bool = False
    ) -> GenerationResult:
        """生成Agent配置
        
        Args:
            save_path: 指定保存路径（目录），如果提供则保存到此目录而非默认的config_dir
        """
        
        agent_id = self._generate_agent_id(name)
        
        if auto_select_model and not llm_config:
            model_selection = self._select_model_for_role(role, task_profile, budget_sensitive)
            if model_selection:
                llm_config = self._build_llm_config_from_selection(model_selection)
        else:
            model_selection = None
        
        config = self._build_config(
            name=name,
            description=description,
            role=role,
            capabilities=capabilities or [],
            tools=self._merge_with_role_defaults(tools or [], role),
            llm_config=llm_config or {},
            parent=parent,
            children=children
        )
        
        validation_results = self.validator.validate(config, agent_id)
        
        errors = [r for r in validation_results if r.level == ValidationLevel.ERROR]
        
        config_path = None
        if save and not errors:
            config_path = self._save_config(agent_id, config, save_path)
            
            if parent:
                self._update_parent_children(parent, agent_id)
        
        logger.info(f"Generated agent config: {agent_id}, success={len(errors) == 0}")
        
        return GenerationResult(
            success=len(errors) == 0,
            agent_id=agent_id,
            config_path=config_path,
            config_content=config,
            validation_results=validation_results,
            message="配置生成成功" if not errors else "配置存在错误，请检查验证结果",
            model_selection=model_selection
        )
    
    async def generate_from_requirement(
        self,
        requirement: str,
        save: bool = True,
        save_path: Path = None,
        auto_select_model: bool = True,
        budget_sensitive: bool = False,
        use_ai_generation: bool = True
    ) -> GenerationResult:
        """根据需求描述生成Agent配置
        
        Args:
            requirement: 需求描述
            save: 是否保存配置
            save_path: 指定保存路径（目录），如果提供则保存到此目录而非默认的config_dir
            auto_select_model: 是否自动选择模型
            budget_sensitive: 是否对预算敏感
            use_ai_generation: 是否使用AI生成
        """
        
        if use_ai_generation and self._llm_provider:
            analysis = await self._analyze_requirement_with_llm(requirement)
        else:
            analysis = self._analyze_requirement(requirement)
        
        task_profile = TaskProfile.from_analysis(analysis)
        
        return self.generate(
            name=analysis["name"],
            description=analysis["description"],
            role=analysis["role"],
            capabilities=analysis["capabilities"],
            tools=analysis["tools"],
            llm_config=analysis.get("llm_config"),
            parent=analysis.get("parent"),
            children=analysis.get("children"),
            save=save,
            save_path=save_path,
            task_profile=task_profile,
            auto_select_model=auto_select_model,
            budget_sensitive=budget_sensitive
        )
    
    def _select_model_for_role(
        self,
        role: str,
        task_profile: TaskProfile = None,
        budget_sensitive: bool = False
    ) -> Optional[SelectionResult]:
        """根据角色选择模型
        
        优先级：
        1. ModelRouter 按任务类型路由（.env 中 MODEL_CODE 等配置）
        2. .env 中 DEFAULT_MODEL 配置
        3. ModelSelector 评分选择（降级方案）
        """
        from ..llm.model_profile import ModelProfile, ModelTag, PricingInfo
        
        task_type_str = None
        if task_profile and hasattr(task_profile.task_type, 'value'):
            task_type_str = task_profile.task_type.value
        else:
            task_type_str = self._get_task_type_for_role(role).value
        
        if self._model_router:
            routed = self._model_router.route(task_type_str)
            if routed:
                model = ModelProfile(
                    id=routed.model,
                    name=routed.model,
                    provider=routed.provider,
                    tags=[],
                    enabled=True,
                )
                return SelectionResult(
                    model=model,
                    score=1.0,
                    reason=f"任务类型 {task_type_str} 路由到 {routed.provider}/{routed.model} (来源: {routed.source})"
                )
        
        default_config = self._get_default_model_config(task_type_str)
        if default_config:
            tags = [ModelTag(tag) for tag in default_config.get("model_tags", ["text"])]
            
            pricing_data = default_config.get("pricing", {})
            pricing = PricingInfo(
                input_price_per_1k=pricing_data.get("input_price_per_1k", 0.01),
                output_price_per_1k=pricing_data.get("output_price_per_1k", 0.03),
                currency=pricing_data.get("currency", "CNY")
            ) if pricing_data else None
            
            model = ModelProfile(
                id=default_config["model_id"],
                name=default_config["model"],
                provider=default_config["provider"],
                tags=tags,
                api_config=default_config.get("api_config", {}),
                pricing=pricing,
                context_window=default_config.get("context_window", 128000),
                max_output_tokens=default_config.get("max_tokens", 4096),
                enabled=True
            )
            
            return SelectionResult(
                model=model,
                score=1.0,
                reason=default_config.get("selection_reason", "使用用户配置的默认模型")
            )
        
        if task_profile is None:
            task_type = self._get_task_type_for_role(role)
            complexity = TaskComplexity.COMPLEX if role in ["root", "coordinator"] else TaskComplexity.MEDIUM
            task_profile = TaskProfile(
                task_type=task_type,
                complexity=complexity,
                budget_sensitive=budget_sensitive
            )
        
        strategy = "cost_first" if budget_sensitive else "balanced"
        
        try:
            return self.model_selector.select(task_profile, strategy=strategy)
        except ValueError:
            return None
    
    def _get_task_type_for_role(self, role: str) -> TaskType:
        """根据角色获取任务类型"""
        role_task_mapping = {
            "root": TaskType.REASONING,
            "coordinator": TaskType.REASONING,
            "worker": TaskType.GENERAL,
            "specialist": TaskType.GENERAL
        }
        return role_task_mapping.get(role, TaskType.GENERAL)
    
    def _get_default_model_config(self, task_type: str = None) -> Optional[dict[str, Any]]:
        """从 .env 读取默认模型配置
        
        优先使用 fractalclaw config 命令配置的默认模型
        支持为不同任务类型配置不同的模型
        
        Args:
            task_type: 任务类型 (code, chat, research, coordinate, test, data, general)
        
        Returns:
            模型配置字典，None 表示没有配置默认模型
        """
        import os
        from dotenv import load_dotenv
        
        env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        
        default_model = None
        selection_reason = None
        
        TASK_TYPE_ENV_MAPPING = {
            "code": "MODEL_CODE",
            "chat": "MODEL_CHAT",
            "research": "MODEL_RESEARCH",
            "reasoning": "MODEL_REASONING",
            "writing": "MODEL_WRITING",
            "coordinate": "MODEL_REASONING",
            "test": "MODEL_CODE",
            "data": "MODEL_RESEARCH",
        }
        
        if task_type and task_type in TASK_TYPE_ENV_MAPPING:
            env_key = TASK_TYPE_ENV_MAPPING[task_type]
            default_model = os.getenv(env_key)
            if default_model:
                selection_reason = f"使用任务类型 {task_type} 专用模型: {default_model}"
        
        if not default_model:
            default_model = os.getenv("DEFAULT_MODEL")
            if default_model:
                selection_reason = f"使用通用默认模型: {default_model}"
        
        default_provider = os.getenv("DEFAULT_PROVIDER", "openai").lower()
        
        if not default_model:
            return None
        
        PROVIDER_CONFIG_MAPPING = {
            "openai": {
                "api_key_env": "OPENAI_API_KEY",
                "base_url_env": "OPENAI_API_BASE",
                "default_base_url": "https://api.openai.com/v1"
            },
            "anthropic": {
                "api_key_env": "ANTHROPIC_API_KEY",
                "base_url_env": "ANTHROPIC_BASE_URL",
                "default_base_url": "https://api.anthropic.com"
            },
            "deepseek": {
                "api_key_env": "DEEPSEEK_API_KEY",
                "base_url_env": "DEEPSEEK_BASE_URL",
                "default_base_url": "https://api.deepseek.com/v1"
            },
            "zhipu": {
                "api_key_env": "ZHIPU_API_KEY",
                "base_url_env": "ZHIPU_BASE_URL",
                "default_base_url": "https://open.bigmodel.cn/api/paas/v4"
            },
            "alibaba": {
                "api_key_env": "DASHSCOPE_API_KEY",
                "base_url_env": "DASHSCOPE_BASE_URL",
                "default_base_url": "https://dashscope.aliyuncs.com/api/v1"
            },
            "moonshot": {
                "api_key_env": "MOONSHOT_API_KEY",
                "base_url_env": "MOONSHOT_BASE_URL",
                "default_base_url": "https://api.moonshot.cn/v1"
            },
            "ollama": {
                "api_key_env": None,
                "base_url_env": "OLLAMA_BASE_URL",
                "default_base_url": "http://localhost:11434"
            },
            "other": {
                "api_key_env": "OPENAI_API_KEY",
                "base_url_env": "OPENAI_API_BASE",
                "default_base_url": None
            }
        }
        
        provider_config = PROVIDER_CONFIG_MAPPING.get(default_provider, PROVIDER_CONFIG_MAPPING["other"])
        
        api_key = None
        if provider_config["api_key_env"]:
            api_key = os.getenv(provider_config["api_key_env"])
        
        if not api_key and default_provider not in ["ollama"]:
            return None
        
        base_url = None
        if provider_config["base_url_env"]:
            base_url = os.getenv(provider_config["base_url_env"])
        
        if not base_url and provider_config["default_base_url"]:
            base_url = provider_config["default_base_url"]
        
        if not api_key and default_provider not in ["ollama"]:
            return None
        
        config = {
            "model": default_model,
            "model_id": default_model,
            "provider": default_provider
        }
        
        if base_url:
            config["api_config"] = {"base_url": base_url}
        
        config["context_window"] = 128000
        config["max_tokens"] = 4096
        
        config["pricing"] = {
            "input_price_per_1k": 0.01,
            "output_price_per_1k": 0.03,
            "currency": "CNY"
        }
        
        config["model_tags"] = ["text", "reasoning"]
        config["selection_reason"] = f"{selection_reason} (provider: {default_provider})"
        
        return config
    
    def _build_llm_config_from_selection(self, selection: SelectionResult) -> dict[str, Any]:
        """从选择结果构建LLM配置
        
        支持环境变量覆盖 base_url
        """
        import os
        from dotenv import load_dotenv
        
        model = selection.model
        
        config = {
            "model": model.name,
            "model_id": model.id,
            "provider": model.provider
        }
        
        env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        
        PROVIDER_BASE_URL_ENV = {
            "openai": "OPENAI_API_BASE",
            "anthropic": "ANTHROPIC_BASE_URL",
            "deepseek": "DEEPSEEK_BASE_URL",
            "zhipu": "ZHIPU_BASE_URL",
            "alibaba": "DASHSCOPE_BASE_URL",
            "moonshot": "MOONSHOT_BASE_URL",
            "ollama": "OLLAMA_BASE_URL",
        }
        
        env_base_url = None
        base_url_env = PROVIDER_BASE_URL_ENV.get(model.provider.lower())
        if base_url_env:
            env_base_url = os.getenv(base_url_env)
        
        if not env_base_url:
            env_base_url = os.getenv("OPENAI_API_BASE")
        
        if env_base_url:
            config["api_config"] = {"base_url": env_base_url}
        elif model.api_config:
            config["api_config"] = model.api_config
        
        config["context_window"] = model.context_window
        config["max_tokens"] = model.max_output_tokens
        
        if model.pricing:
            config["pricing"] = {
                "input_price_per_1k": model.pricing.input_price_per_1k,
                "output_price_per_1k": model.pricing.output_price_per_1k,
                "currency": model.pricing.currency
            }
        
        config["model_tags"] = [tag.value for tag in model.tags]
        config["selection_reason"] = selection.reason
        
        return config
    
    def _generate_agent_id(self, name: str) -> str:
        """生成Agent ID"""
        short_uuid = uuid.uuid4().hex[:8]
        name_slug = name.lower().replace(" ", "_").replace("-", "_")
        name_slug = "".join(c for c in name_slug if c.isascii() and (c.isalnum() or c == "_"))
        if not name_slug or not name_slug[0].isalpha():
            name_slug = "agent"
        return f"agent_{short_uuid}_{name_slug}"
    
    def _build_config(
        self,
        name: str,
        description: str,
        role: str,
        capabilities: list[str],
        tools: list[str],
        llm_config: dict[str, Any],
        parent: str = None,
        children: list[str] = None
    ) -> dict[str, Any]:
        """构建配置字典"""
        
        config = {
            "name": name,
            "description": description,
            "role": role
        }
        
        if parent:
            config["parent"] = parent
        
        if llm_config:
            config["llm"] = llm_config
        
        system_prompt = self._generate_system_prompt(name, description, role, capabilities)
        config["system_prompt"] = system_prompt
        
        if tools:
            config["tools"] = self._build_tools(tools)
        
        if children:
            config["children"] = children
        
        return config
    
    def _generate_system_prompt(
        self,
        name: str,
        description: str,
        role: str,
        capabilities: list[str]
    ) -> str:
        """生成系统提示词"""
        
        role_desc = self.ROLE_DESCRIPTIONS.get(role, "")
        
        prompt_parts = [
            f"你是{name}，{role_desc}",
            f"",
            f"## 角色定位",
            f"{role_desc}",
        ]
        
        if capabilities:
            prompt_parts.append("")
            prompt_parts.append("## 核心能力")
            for cap in capabilities:
                prompt_parts.append(f"- {cap}")
        
        prompt_parts.extend([
            "",
            "## 工作原则",
            "1. 你必须通过调用工具来执行实际操作，绝不能只给出操作指导或步骤说明",
            "2. 当任务涉及文件操作时，必须使用 write/edit/read 等文件工具来完成",
            "3. 当任务涉及命令执行时，必须使用 bash 工具来执行命令",
            "4. 认真分析任务需求，准确理解用户意图",
            "5. 制定合理的执行计划，按步骤调用工具完成",
            "6. 及时反馈执行结果，包括工具调用的返回信息",
            "",
            "## ⚠️ 严禁行为",
            "- 禁止只输出操作步骤或指导说明而不实际执行",
            "- 禁止让用户手动执行操作",
            "- 禁止用文字描述代替工具调用",
            "- 所有实际操作必须通过工具调用完成",
            "",
            "## 任务理解指南",
            "当收到用户任务时，请按以下步骤理解：",
            "1. **识别核心动作**：用户想要做什么？（如：写入、创建、查询、修改等）",
            "2. **识别目标对象**：操作的对象是什么？（如：文件、数据、系统等）",
            "3. **识别具体内容**：需要处理的具体内容是什么？",
            "4. **识别目标位置**：结果需要保存到哪里？（如：桌面、特定目录等）",
            "5. **识别约束条件**：有什么格式、大小、时间等限制？",
            "",
            "## 常见任务类型示例",
            "- \"写长恨歌到桌面上\" → 调用 write 工具，将长恨歌内容写入桌面文件",
            "- \"查询今天的天气\" → 调用 bash 工具执行天气查询命令",
            "- \"帮我分析这段代码\" → 调用 read 工具读取代码，分析后给出结论",
        ])
        
        return "\n".join(prompt_parts)
    
    def _merge_with_role_defaults(self, tools: list[str], role: str) -> list[str]:
        from fractalclaw.tools.definitions import ROLE_DEFAULT_TOOLS

        role_defaults = ROLE_DEFAULT_TOOLS.get(role, [])
        merged = list(dict.fromkeys(tools + role_defaults))
        return merged

    def _build_tools(self, tool_names: list[str]) -> list[dict]:
        """构建工具配置"""
        tools = []
        for name in tool_names:
            if name in self.TOOL_TEMPLATES:
                tools.append(self.TOOL_TEMPLATES[name])
            else:
                tools.append({
                    "name": name,
                    "description": f"工具: {name}",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                })
        return tools
    
    def _analyze_requirement(self, requirement: str) -> dict[str, Any]:
        from fractalclaw.llm.task_classifier import classify_by_keywords

        classification = classify_by_keywords(requirement)

        TASK_TYPE_ROLE_MAP = {
            "code": ("specialist", ["read", "write", "bash"], ["代码编写", "代码审查", "调试排错"]),
            "research": ("specialist", ["tavily_search", "llm_generate", "read"], ["信息搜索", "数据分析", "报告撰写"]),
            "reasoning": ("coordinator", [], ["任务分解", "资源协调", "结果整合"]),
            "chat": ("worker", [], ["对话理解", "信息提供", "问题解答"]),
            "writing": ("specialist", ["llm_generate", "read", "write"], ["内容创作", "文案撰写", "翻译"]),
        }

        role = "worker"
        tools: list[str] = []
        capabilities: list[str] = []

        mapping = TASK_TYPE_ROLE_MAP.get(classification.task_type)
        if mapping:
            role, tools, capabilities = mapping

        complexity = self._analyze_complexity(requirement)
        importance = self._analyze_importance(requirement)
        requires_multimodal = self._check_multimodal_requirement(requirement)
        requires_code = classification.task_type == "code" or "代码" in requirement
        requires_reasoning = classification.task_type in ["research", "reasoning"] or "推理" in requirement

        name = self._extract_name(requirement) or "Agent"
        description = requirement[:200] if len(requirement) > 200 else requirement

        return {
            "name": name,
            "description": description,
            "role": role,
            "capabilities": list(set(capabilities)),
            "tools": list(set(tools)),
            "complexity": complexity,
            "task_type": classification.task_type,
            "importance": importance,
            "requires_multimodal": requires_multimodal,
            "requires_code": requires_code,
            "requires_reasoning": requires_reasoning,
            "budget_sensitive": False
        }
    
    def _analyze_complexity(self, requirement: str) -> str:
        """分析任务复杂度"""
        requirement_lower = requirement.lower()
        
        for indicator in self.COMPLEXITY_INDICATORS["complex"]:
            if indicator in requirement_lower:
                return "complex"
        
        for indicator in self.COMPLEXITY_INDICATORS["simple"]:
            if indicator in requirement_lower:
                return "simple"
        
        if len(requirement) > 200:
            return "complex"
        elif len(requirement) < 50:
            return "simple"
        
        return "medium"
    
    def _analyze_importance(self, requirement: str) -> str:
        """分析任务重要性"""
        requirement_lower = requirement.lower()
        
        for indicator in self.IMPORTANCE_INDICATORS["high"]:
            if indicator in requirement_lower:
                return "high"
        
        for indicator in self.IMPORTANCE_INDICATORS["low"]:
            if indicator in requirement_lower:
                return "low"
        
        return "medium"
    
    def _check_multimodal_requirement(self, requirement: str) -> bool:
        """检查是否需要多模态能力"""
        multimodal_keywords = ["图片", "图像", "视频", "音频", "image", "video", "audio", "视觉", "多模态"]
        requirement_lower = requirement.lower()
        return any(kw in requirement_lower for kw in multimodal_keywords)
    
    def _extract_name(self, requirement: str) -> Optional[str]:
        """从需求中提取名称"""
        import re
        
        patterns = [
            r"创建[一个]?(\w+)Agent",
            r"设计[一个]?(\w+)Agent",
            r"需要[一个]?(\w+)Agent",
            r"(\w+)助手",
            r"(\w+)专家"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, requirement)
            if match:
                return match.group(1) + "Agent"
        
        return None
    
    def _save_config(self, agent_id: str, config: dict, save_path: Path = None) -> Path:
        """保存配置文件
        
        Args:
            agent_id: Agent ID
            config: 配置字典
            save_path: 指定保存目录，如果提供则保存到此目录而非默认的config_dir
            
        Returns:
            保存的文件路径
        """
        target_dir = save_path if save_path else self.config_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        
        path = target_dir / f"{agent_id}.yaml"
        
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        
        return path
    
    def list_tool_templates(self) -> dict[str, dict]:
        """列出可用的工具模板"""
        return self.TOOL_TEMPLATES.copy()
    
    def get_missing_required_config(self, config: dict) -> dict[str, list[str]]:
        """获取缺失的必要配置"""
        return self.validator.get_missing_fields(config)
    
    def get_available_models(self) -> list[dict[str, Any]]:
        """获取可用模型列表（只返回已配置 API Key 的模型）"""
        models = self.model_registry.list_configured()
        return [
            {
                "id": m.id,
                "name": m.name,
                "provider": m.provider,
                "tags": [t.value for t in m.tags],
                "description": m.description
            }
            for m in models
        ]
    
    def recommend_models(
        self,
        task_type: str = None,
        complexity: str = None,
        budget_sensitive: bool = False
    ) -> list[SelectionResult]:
        """推荐模型"""
        task_profile = TaskProfile(
            task_type=self.TASK_TYPE_MAPPING.get(task_type, TaskType.GENERAL),
            complexity=TaskComplexity(complexity) if complexity else TaskComplexity.MEDIUM,
            budget_sensitive=budget_sensitive
        )
        
        return self.model_selector.get_recommendation(task_profile)
    
    async def _analyze_requirement_with_llm(self, requirement: str) -> dict[str, Any]:
        if not self._llm_provider:
            logger.warning("LLM provider not set, falling back to keyword analysis")
            return self._analyze_requirement(requirement)

        from fractalclaw.tools.definitions import ROLE_DEFAULT_TOOLS

        all_tools = sorted(set(
            ROLE_DEFAULT_TOOLS.get("specialist", [])
            + ROLE_DEFAULT_TOOLS.get("root", [])
            + ["tavily_search", "llm_generate"]
        ))
        available_tools_desc = "\n".join(f"  - {t}" for t in all_tools)

        prompt = f"""分析以下 Agent 需求描述，生成结构化的配置信息。

需求描述：
{requirement}

可用工具列表：
{available_tools_desc}

角色类型说明：
- worker: 执行具体任务的通用 Agent
- specialist: 在特定领域有专业能力的 Agent
- coordinator: 负责任务分解和协调的 Agent

工具选择原则：
- 涉及文件读写 → 选择 read, write, edit
- 涉及命令执行 → 选择 bash
- 涉及网络搜索 → 选择 tavily_search
- 涉及文本生成/总结/分析 → 选择 llm_generate
- 涉及文件查找 → 选择 search, find_files
- 不确定时多选，宁可多给工具也不要遗漏

请严格按照以下 JSON 格式返回（不要添加任何注释或额外文字）：
{{"name": "英文名称", "description": "功能描述", "role": "worker或specialist或coordinator", "capabilities": ["能力1", "能力2"], "task_type": "code或research或coordinate或test或data或chat或general", "complexity": "simple或medium或complex", "importance": "low或medium或high", "tools": ["工具名"]}}"""

        try:
            from ..llm.engine import LLMConfig, Message, MessageRole
            from ..llm.response_parser import extract_json_from_llm_response

            default_model_config = self._get_default_model_config()
            from ..llm.model_profile import get_default_model_name
            model_name = default_model_config.get("model", get_default_model_name()) if default_model_config else get_default_model_name()
            config = LLMConfig(
                model=model_name,
                temperature=0.3,
                max_tokens=1024,
                stream=False,
                response_format={"type": "json_object"},
            )
            messages = [Message(role=MessageRole.USER, content=prompt)]

            response = await self._llm_provider.complete(messages, config)

            raw_content = response.content.strip()
            logger.debug(f"LLM raw response for requirement analysis: {raw_content[:500]}")

            result = extract_json_from_llm_response(raw_content)
            if result is None:
                raise ValueError(f"Failed to parse LLM response as JSON. Raw response: {raw_content[:300]}")

            result.setdefault("tools", [])
            result.setdefault("requires_multimodal", self._check_multimodal_requirement(requirement))
            result.setdefault("requires_code", result.get("task_type") == "code")
            result.setdefault("requires_reasoning", result.get("task_type") in ["research", "reasoning"])
            result.setdefault("budget_sensitive", False)

            logger.info(f"LLM analysis result: {result}")
            return result

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}, falling back to keyword analysis")
            return self._analyze_requirement(requirement)
    
    async def _generate_system_prompt_with_llm(
        self,
        name: str,
        description: str,
        role: str,
        capabilities: list[str],
        task_type: str = None
    ) -> str:
        """使用 LLM 生成系统提示词"""
        
        if not self._llm_provider:
            logger.warning("LLM provider not set, falling back to template generation")
            return self._generate_system_prompt(name, description, role, capabilities)
        
        role_desc = self.ROLE_DESCRIPTIONS.get(role, "")
        
        prompt = f"""为以下 Agent 生成系统提示词（system_prompt）。

Agent 信息：
- 名称：{name}
- 描述：{description}
- 角色：{role}（{role_desc}）
- 核心能力：{', '.join(capabilities) if capabilities else '无'}
- 任务类型：{task_type or 'general'}

请生成一个完整的系统提示词，包含以下部分：
1. 角色定位：明确 Agent 的身份和职责
2. 核心能力：列出 Agent 的主要能力
3. 工作原则：定义 Agent 的工作方式和原则
4. 注意事项：使用 Agent 时需要注意的事项

直接返回提示词内容，不要包含其他说明。"""

        try:
            from ..llm.engine import LLMConfig, Message, MessageRole

            default_model_config = self._get_default_model_config(task_type)
            from ..llm.model_profile import get_default_model_name
            model_name = default_model_config.get("model", get_default_model_name()) if default_model_config else get_default_model_name()
            config = LLMConfig(model=model_name, temperature=0.7, max_tokens=2048, stream=False)
            messages = [Message(role=MessageRole.USER, content=prompt)]

            response = await self._llm_provider.complete(messages, config)
            
            logger.info(f"LLM generated system_prompt for {name}")
            return response.content.strip()
            
        except Exception as e:
            logger.error(f"LLM system_prompt generation failed: {e}, falling back to template")
            return self._generate_system_prompt(name, description, role, capabilities)
    
    def _update_parent_children(self, parent_id: str, child_id: str) -> None:
        """更新父 Agent 的 children 字段"""
        
        parent_path = self.config_dir / f"{parent_id}.yaml"
        
        if not parent_path.exists():
            logger.warning(f"Parent config not found: {parent_id}")
            return
        
        try:
            with open(parent_path, 'r', encoding='utf-8') as f:
                parent_config = yaml.safe_load(f)
            
            if parent_config is None:
                parent_config = {}
            
            children = parent_config.get("children", [])
            
            if child_id not in children:
                children.append(child_id)
                parent_config["children"] = children
                
                with open(parent_path, 'w', encoding='utf-8') as f:
                    yaml.dump(parent_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
                
                logger.info(f"Updated parent {parent_id} children: added {child_id}")
            else:
                logger.debug(f"Child {child_id} already in parent {parent_id}")
                
        except Exception as e:
            logger.error(f"Failed to update parent children: {e}")
    
    async def _retrieve_tools_from_agent(self, requirement: str, capabilities: list[str]) -> list[dict]:
        """通过 ToolSearchAgent 检索工具"""
        
        if not self._tool_search_agent:
            logger.warning("ToolSearchAgent not set, falling back to template tools")
            return []
        
        try:
            tool_query = f"需要以下能力的工具：{', '.join(capabilities)}"
            
            if hasattr(self._tool_search_agent, 'search'):
                result = await self._tool_search_agent.search(tool_query)
            elif hasattr(self._tool_search_agent, 'search_tools'):
                result = await self._tool_search_agent.search_tools(tool_query)
            else:
                logger.warning("ToolSearchAgent has no search method")
                return []
            
            tools = []
            if isinstance(result, dict) and "tools" in result:
                for tool_info in result["tools"]:
                    if isinstance(tool_info, dict) and "tool_id" in tool_info:
                        tools.append({"tool_id": tool_info["tool_id"]})
            elif isinstance(result, list):
                for tool_info in result:
                    if isinstance(tool_info, dict) and "tool_id" in tool_info:
                        tools.append({"tool_id": tool_info["tool_id"]})
            
            logger.info(f"Retrieved {len(tools)} tools from ToolSearchAgent")
            return tools
            
        except Exception as e:
            logger.error(f"ToolSearchAgent search failed: {e}")
            return []
