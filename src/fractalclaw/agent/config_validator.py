"""Agent配置验证器"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum

from ..llm import ModelRegistry, get_default_registry


class ValidationLevel(Enum):
    """验证级别"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    level: ValidationLevel
    field: str
    message: str
    suggestion: Optional[str] = None


@dataclass
class AgentConfigSchema:
    """Agent配置模式定义"""
    
    REQUIRED_FIELDS: list[str] = field(default_factory=lambda: [
        "name",
        "description",
        "role",
        "system_prompt"
    ])
    
    ROLE_VALUES: list[str] = field(default_factory=lambda: [
        "root",
        "coordinator",
        "worker",
        "specialist"
    ])
    
    LLM_FIELDS: list[str] = field(default_factory=lambda: [
        "model",
        "temperature",
        "max_tokens",
        "top_p",
        "stream",
        "timeout"
    ])
    
    BEHAVIOR_FIELDS: list[str] = field(default_factory=lambda: [
        "max_iterations",
        "enable_planning",
        "enable_reflection",
        "max_replan_attempts"
    ])
    
    TOOL_REQUIRED_FIELDS: list[str] = field(default_factory=lambda: [
        "name",
        "description",
        "parameters"
    ])
    
    UUID_PATTERN: str = r"^agent_[a-f0-9]{8}_[a-z0-9_]+$"
    
    VALID_MODEL_TAGS: list[str] = field(default_factory=lambda: [
        "text",
        "multimodal",
        "cost_effective",
        "high_capacity",
        "fast",
        "reasoning",
        "code",
        "chat",
        "embedding"
    ])


class ConfigValidator:
    """配置验证器"""
    
    COST_WARNING_THRESHOLDS = {
        "input_price_per_1k": 0.05,
        "output_price_per_1k": 0.1
    }
    
    def __init__(
        self,
        global_settings: dict[str, Any] = None,
        model_registry: ModelRegistry = None
    ):
        self.schema = AgentConfigSchema()
        self.global_settings = global_settings or {}
        self.model_registry = model_registry or get_default_registry()
    
    def validate(self, config: dict[str, Any], agent_id: str = None) -> list[ValidationResult]:
        """验证Agent配置"""
        results = []
        
        results.extend(self._validate_required_fields(config))
        results.extend(self._validate_role(config))
        results.extend(self._validate_llm_config(config))
        results.extend(self._validate_behavior_config(config))
        results.extend(self._validate_system_prompt(config))
        results.extend(self._validate_tools(config))
        results.extend(self._validate_children(config))
        results.extend(self._validate_model_tags(config))
        results.extend(self._validate_cost(config))
        
        if agent_id:
            results.extend(self._validate_agent_id(agent_id))
        
        return results
    
    def _validate_required_fields(self, config: dict) -> list[ValidationResult]:
        """验证必填字段"""
        results = []
        
        for field_name in self.schema.REQUIRED_FIELDS:
            if field_name not in config or not config[field_name]:
                results.append(ValidationResult(
                    is_valid=False,
                    level=ValidationLevel.ERROR,
                    field=field_name,
                    message=f"必填字段 '{field_name}' 缺失或为空",
                    suggestion=f"请添加 '{field_name}' 字段"
                ))
        
        return results
    
    def _validate_role(self, config: dict) -> list[ValidationResult]:
        """验证角色字段"""
        results = []
        
        if "role" in config:
            role = config["role"]
            if role not in self.schema.ROLE_VALUES:
                results.append(ValidationResult(
                    is_valid=False,
                    level=ValidationLevel.ERROR,
                    field="role",
                    message=f"无效的角色值: {role}",
                    suggestion=f"角色必须是以下之一: {', '.join(self.schema.ROLE_VALUES)}"
                ))
        
        return results
    
    def _validate_llm_config(self, config: dict) -> list[ValidationResult]:
        """验证LLM配置"""
        results = []
        
        if "llm" not in config:
            results.append(ValidationResult(
                is_valid=False,
                level=ValidationLevel.WARNING,
                field="llm",
                message="未配置LLM参数，将使用全局配置",
                suggestion="建议根据Agent特性配置LLM参数"
            ))
            return results
        
        llm_config = config["llm"]
        global_llm = self.global_settings.get("llm", {})
        
        for field_name in self.schema.LLM_FIELDS:
            if field_name not in llm_config and field_name not in global_llm:
                if field_name == "model":
                    results.append(ValidationResult(
                        is_valid=False,
                        level=ValidationLevel.ERROR,
                        field=f"llm.{field_name}",
                        message=f"LLM配置缺少 '{field_name}' 字段",
                        suggestion="必须指定模型名称"
                    ))
        
        if "temperature" in llm_config:
            temp = llm_config["temperature"]
            if not 0 <= temp <= 2:
                results.append(ValidationResult(
                    is_valid=False,
                    level=ValidationLevel.ERROR,
                    field="llm.temperature",
                    message=f"temperature值 {temp} 超出有效范围 [0, 2]",
                    suggestion="temperature应在0到2之间"
                ))
        
        if "model_id" in llm_config:
            model = self.model_registry.get(llm_config["model_id"])
            if not model:
                results.append(ValidationResult(
                    is_valid=False,
                    level=ValidationLevel.WARNING,
                    field="llm.model_id",
                    message=f"模型ID '{llm_config['model_id']}' 未在模型注册表中找到",
                    suggestion="请检查模型ID是否正确，或添加模型配置"
                ))
        
        return results
    
    def _validate_behavior_config(self, config: dict) -> list[ValidationResult]:
        """验证行为配置"""
        results = []
        
        if "behavior" not in config:
            results.append(ValidationResult(
                is_valid=False,
                level=ValidationLevel.WARNING,
                field="behavior",
                message="未配置行为参数，将使用全局配置",
                suggestion="建议根据Agent特性配置行为参数"
            ))
            return results
        
        behavior_config = config["behavior"]
        global_behavior = self.global_settings.get("behavior", {})
        
        for field_name in self.schema.BEHAVIOR_FIELDS:
            if field_name not in behavior_config and field_name not in global_behavior:
                results.append(ValidationResult(
                    is_valid=False,
                    level=ValidationLevel.WARNING,
                    field=f"behavior.{field_name}",
                    message=f"行为配置缺少 '{field_name}' 字段",
                    suggestion=f"建议配置 '{field_name}'"
                ))
        
        if "max_iterations" in behavior_config:
            max_iter = behavior_config["max_iterations"]
            if max_iter < 1:
                results.append(ValidationResult(
                    is_valid=False,
                    level=ValidationLevel.ERROR,
                    field="behavior.max_iterations",
                    message=f"max_iterations值 {max_iter} 必须大于0",
                    suggestion="max_iterations应至少为1"
                ))
        
        return results
    
    def _validate_system_prompt(self, config: dict) -> list[ValidationResult]:
        """验证系统提示词"""
        results = []
        
        if "system_prompt" in config:
            prompt = config["system_prompt"]
            if len(prompt) < 50:
                results.append(ValidationResult(
                    is_valid=False,
                    level=ValidationLevel.WARNING,
                    field="system_prompt",
                    message="系统提示词过短，可能无法充分描述Agent能力",
                    suggestion="建议系统提示词至少50个字符，详细描述Agent的能力和职责"
                ))
        
        return results
    
    def _validate_tools(self, config: dict) -> list[ValidationResult]:
        """验证工具配置"""
        results = []
        
        if "tools" not in config or not config["tools"]:
            if config.get("role") in ["worker", "specialist"]:
                results.append(ValidationResult(
                    is_valid=False,
                    level=ValidationLevel.WARNING,
                    field="tools",
                    message="Worker或Specialist角色建议配置至少一个工具",
                    suggestion="请为Agent配置必要的工具"
                ))
            return results
        
        for i, tool in enumerate(config["tools"]):
            for field_name in self.schema.TOOL_REQUIRED_FIELDS:
                if field_name not in tool:
                    results.append(ValidationResult(
                        is_valid=False,
                        level=ValidationLevel.ERROR,
                        field=f"tools[{i}].{field_name}",
                        message=f"工具 {i} 缺少必填字段 '{field_name}'",
                        suggestion=f"请为工具添加 '{field_name}' 字段"
                    ))
            
            if "parameters" in tool:
                params = tool["parameters"]
                if "type" not in params:
                    results.append(ValidationResult(
                        is_valid=False,
                        level=ValidationLevel.ERROR,
                        field=f"tools[{i}].parameters",
                        message=f"工具 {i} 的参数缺少 'type' 字段",
                        suggestion="参数应包含 'type: object'"
                    ))
        
        return results
    
    def _validate_children(self, config: dict) -> list[ValidationResult]:
        """验证子Agent配置"""
        results = []
        
        if "children" in config:
            role = config.get("role")
            if role not in ["root", "coordinator"]:
                results.append(ValidationResult(
                    is_valid=False,
                    level=ValidationLevel.WARNING,
                    field="children",
                    message=f"角色 '{role}' 通常不需要子Agent",
                    suggestion="只有root或coordinator角色通常需要配置子Agent"
                ))
        
        return results
    
    def _validate_agent_id(self, agent_id: str) -> list[ValidationResult]:
        """验证Agent ID格式"""
        results = []
        
        if not re.match(self.schema.UUID_PATTERN, agent_id):
            results.append(ValidationResult(
                is_valid=False,
                level=ValidationLevel.ERROR,
                field="agent_id",
                message=f"Agent ID格式无效: {agent_id}",
                suggestion="格式应为: agent_{uuid}_{name}，例如: agent_a1b2c3d4_coder"
            ))
        
        return results
    
    def _validate_model_tags(self, config: dict) -> list[ValidationResult]:
        """验证模型标签"""
        results = []
        
        llm_config = config.get("llm", {})
        model_tags = llm_config.get("model_tags", [])
        
        if not model_tags:
            return results
        
        for tag in model_tags:
            if tag not in self.schema.VALID_MODEL_TAGS:
                results.append(ValidationResult(
                    is_valid=False,
                    level=ValidationLevel.WARNING,
                    field="llm.model_tags",
                    message=f"未知的模型标签: {tag}",
                    suggestion=f"有效标签: {', '.join(self.schema.VALID_MODEL_TAGS)}"
                ))
        
        return results
    
    def _validate_cost(self, config: dict) -> list[ValidationResult]:
        """验证成本配置并提供警告"""
        results = []
        
        llm_config = config.get("llm", {})
        pricing = llm_config.get("pricing", {})
        
        if not pricing:
            return results
        
        input_price = pricing.get("input_price_per_1k", 0)
        output_price = pricing.get("output_price_per_1k", 0)
        
        if input_price > self.COST_WARNING_THRESHOLDS["input_price_per_1k"]:
            results.append(ValidationResult(
                is_valid=True,
                level=ValidationLevel.WARNING,
                field="llm.pricing.input_price_per_1k",
                message=f"输入价格较高 (${input_price:.4f}/1k tokens)，建议评估是否需要如此昂贵的模型",
                suggestion="考虑使用性价比更高的模型，或在预算敏感场景下选择成本更低的替代方案"
            ))
        
        if output_price > self.COST_WARNING_THRESHOLDS["output_price_per_1k"]:
            results.append(ValidationResult(
                is_valid=True,
                level=ValidationLevel.WARNING,
                field="llm.pricing.output_price_per_1k",
                message=f"输出价格较高 (${output_price:.4f}/1k tokens)，可能产生较高成本",
                suggestion="考虑优化输出长度或选择输出价格更低的模型"
            ))
        
        role = config.get("role", "")
        model_tags = llm_config.get("model_tags", [])
        
        if role in ["worker"] and "high_capacity" in model_tags:
            results.append(ValidationResult(
                is_valid=True,
                level=ValidationLevel.INFO,
                field="llm.model_tags",
                message="Worker角色使用了高能力模型，可能存在成本优化空间",
                suggestion="对于简单任务，考虑使用性价比更高的模型"
            ))
        
        return results
    
    def get_missing_fields(self, config: dict) -> dict[str, list[str]]:
        """获取缺失的字段"""
        missing = {
            "required": [],
            "llm": [],
            "behavior": [],
            "tools": []
        }
        
        for field_name in self.schema.REQUIRED_FIELDS:
            if field_name not in config or not config[field_name]:
                missing["required"].append(field_name)
        
        if "llm" in config:
            global_llm = self.global_settings.get("llm", {})
            for field_name in self.schema.LLM_FIELDS:
                if field_name not in config["llm"] and field_name not in global_llm:
                    missing["llm"].append(field_name)
        
        if "behavior" in config:
            global_behavior = self.global_settings.get("behavior", {})
            for field_name in self.schema.BEHAVIOR_FIELDS:
                if field_name not in config["behavior"] and field_name not in global_behavior:
                    missing["behavior"].append(field_name)
        
        return missing
    
    def get_config_template(self, role: str = "worker") -> dict[str, Any]:
        """获取配置模板"""
        template = {
            "name": "",
            "description": "",
            "role": role,
            "llm": {},
            "behavior": {},
            "system_prompt": "",
            "tools": [],
            "children": []
        }
        
        if role in ["root", "coordinator"]:
            template["children"] = []
        
        return template
    
    def estimate_cost(
        self,
        config: dict[str, Any],
        estimated_input_tokens: int = 1000,
        estimated_output_tokens: int = 500
    ) -> Optional[dict[str, Any]]:
        """估算配置成本"""
        llm_config = config.get("llm", {})
        pricing = llm_config.get("pricing", {})
        
        if not pricing:
            return None
        
        input_price = pricing.get("input_price_per_1k", 0)
        output_price = pricing.get("output_price_per_1k", 0)
        currency = pricing.get("currency", "USD")
        
        input_cost = (estimated_input_tokens / 1000) * input_price
        output_cost = (estimated_output_tokens / 1000) * output_price
        total_cost = input_cost + output_cost
        
        return {
            "input_tokens": estimated_input_tokens,
            "output_tokens": estimated_output_tokens,
            "input_cost": input_cost,
            "output_cost": output_cost,
            "total_cost": total_cost,
            "currency": currency,
            "model": llm_config.get("model", "unknown")
        }
