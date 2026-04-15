"""模型配置数据结构"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import yaml
from pathlib import Path


class ModelTag(Enum):
    """模型标签"""
    TEXT = "text"
    MULTIMODAL = "multimodal"
    COST_EFFECTIVE = "cost_effective"
    HIGH_CAPACITY = "high_capacity"
    FAST = "fast"
    REASONING = "reasoning"
    CODE = "code"
    CHAT = "chat"
    EMBEDDING = "embedding"


@dataclass
class PricingInfo:
    """定价信息"""
    input_price_per_1k: float
    output_price_per_1k: float
    currency: str = "USD"
    
    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """估算成本"""
        input_cost = (input_tokens / 1000) * self.input_price_per_1k
        output_cost = (output_tokens / 1000) * self.output_price_per_1k
        return input_cost + output_cost


@dataclass
class ModelCapabilities:
    """模型能力评分 (1-10)"""
    reasoning: int = 5
    coding: int = 5
    creativity: int = 5
    analysis: int = 5
    instruction_following: int = 5
    
    def get_average(self) -> float:
        """获取平均能力评分"""
        return (
            self.reasoning + self.coding + self.creativity + 
            self.analysis + self.instruction_following
        ) / 5
    
    def get_capability_score(self, capability: str) -> int:
        """获取特定能力评分"""
        return getattr(self, capability, 5)


@dataclass
class ModelProfile:
    """模型配置"""
    id: str
    name: str
    provider: str
    tags: list[ModelTag] = field(default_factory=list)
    api_config: dict[str, Any] = field(default_factory=dict)
    api_key_env: Optional[str] = None
    pricing: Optional[PricingInfo] = None
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    context_window: int = 4096
    max_output_tokens: int = 2048
    description: str = ""
    enabled: bool = True
    
    def has_tag(self, tag: ModelTag) -> bool:
        """检查是否具有某个标签"""
        return tag in self.tags
    
    def has_any_tag(self, tags: list[ModelTag]) -> bool:
        """检查是否具有任意一个标签"""
        return any(tag in self.tags for tag in tags)
    
    def has_all_tags(self, tags: list[ModelTag]) -> bool:
        """检查是否具有所有标签"""
        return all(tag in self.tags for tag in tags)
    
    def is_configured(self) -> bool:
        """检查模型是否已配置（有对应的 API Key）"""
        if not self.enabled:
            return False
        if self.api_key_env:
            import os
            return bool(os.getenv(self.api_key_env))
        return True
    
    def get_cost_effectiveness_score(self) -> float:
        """获取性价比评分"""
        if not self.pricing:
            return 0.0
        
        avg_capability = self.capabilities.get_average()
        avg_price = (
            self.pricing.input_price_per_1k + self.pricing.output_price_per_1k
        ) / 2
        
        if avg_price == 0:
            return float('inf')
        
        return avg_capability / avg_price
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "tags": [tag.value for tag in self.tags],
            "api_config": self.api_config,
            "api_key_env": self.api_key_env,
            "pricing": {
                "input_price_per_1k": self.pricing.input_price_per_1k if self.pricing else 0,
                "output_price_per_1k": self.pricing.output_price_per_1k if self.pricing else 0,
                "currency": self.pricing.currency if self.pricing else "USD"
            },
            "capabilities": {
                "reasoning": self.capabilities.reasoning,
                "coding": self.capabilities.coding,
                "creativity": self.capabilities.creativity,
                "analysis": self.capabilities.analysis,
                "instruction_following": self.capabilities.instruction_following
            },
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "description": self.description,
            "enabled": self.enabled
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelProfile":
        """从字典创建"""
        tags = [ModelTag(tag) for tag in data.get("tags", [])]
        
        pricing_data = data.get("pricing", {})
        pricing = None
        if pricing_data:
            pricing = PricingInfo(
                input_price_per_1k=pricing_data.get("input_price_per_1k", 0),
                output_price_per_1k=pricing_data.get("output_price_per_1k", 0),
                currency=pricing_data.get("currency", "USD")
            )
        
        capabilities_data = data.get("capabilities", {})
        capabilities = ModelCapabilities(
            reasoning=capabilities_data.get("reasoning", 5),
            coding=capabilities_data.get("coding", 5),
            creativity=capabilities_data.get("creativity", 5),
            analysis=capabilities_data.get("analysis", 5),
            instruction_following=capabilities_data.get("instruction_following", 5)
        )
        
        return cls(
            id=data["id"],
            name=data["name"],
            provider=data["provider"],
            tags=tags,
            api_config=data.get("api_config", {}),
            api_key_env=data.get("api_key_env"),
            pricing=pricing,
            capabilities=capabilities,
            context_window=data.get("context_window", 4096),
            max_output_tokens=data.get("max_output_tokens", 2048),
            description=data.get("description", ""),
            enabled=data.get("enabled", True)
        )


class ModelRegistry:
    """模型注册表"""
    
    def __init__(self):
        self._models: dict[str, ModelProfile] = {}
        self._tag_index: dict[ModelTag, list[str]] = {tag: [] for tag in ModelTag}
    
    def register(self, model: ModelProfile) -> None:
        """注册模型"""
        self._models[model.id] = model
        
        for tag in model.tags:
            if model.id not in self._tag_index[tag]:
                self._tag_index[tag].append(model.id)
    
    def unregister(self, model_id: str) -> bool:
        """注销模型"""
        if model_id not in self._models:
            return False
        
        model = self._models[model_id]
        
        for tag in model.tags:
            if model_id in self._tag_index[tag]:
                self._tag_index[tag].remove(model_id)
        
        del self._models[model_id]
        return True
    
    def get(self, model_id: str) -> Optional[ModelProfile]:
        """获取模型"""
        return self._models.get(model_id)
    
    def get_by_name(self, name: str) -> Optional[ModelProfile]:
        """通过名称获取模型"""
        for model in self._models.values():
            if model.name == name:
                return model
        return None
    
    def list_all(self) -> list[ModelProfile]:
        """列出所有模型"""
        return list(self._models.values())
    
    def list_enabled(self) -> list[ModelProfile]:
        """列出所有启用的模型"""
        return [m for m in self._models.values() if m.enabled]
    
    def list_configured(self) -> list[ModelProfile]:
        """列出所有已配置的模型（有 API Key 且启用）"""
        return [m for m in self._models.values() if m.is_configured()]
    
    def list_by_tag(self, tag: ModelTag) -> list[ModelProfile]:
        """按标签列出模型"""
        return [
            self._models[model_id] 
            for model_id in self._tag_index[tag] 
            if model_id in self._models and self._models[model_id].enabled
        ]
    
    def list_by_tags(self, tags: list[ModelTag], match_all: bool = False) -> list[ModelProfile]:
        """按多个标签列出模型"""
        models = self.list_enabled()
        
        if match_all:
            return [m for m in models if m.has_all_tags(tags)]
        else:
            return [m for m in models if m.has_any_tag(tags)]
    
    def load_from_yaml(self, path: Path) -> int:
        """从YAML文件加载模型配置"""
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        count = 0
        for model_data in data.get("models", []):
            try:
                model = ModelProfile.from_dict(model_data)
                self.register(model)
                count += 1
            except Exception as e:
                print(f"加载模型配置失败: {model_data.get('id', 'unknown')}, 错误: {e}")
        
        return count
    
    def save_to_yaml(self, path: Path) -> None:
        """保存模型配置到YAML文件"""
        data = {
            "models": [model.to_dict() for model in self._models.values()]
        }
        
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    
    def get_cheapest(self, tags: list[ModelTag] = None) -> Optional[ModelProfile]:
        """获取最便宜的模型"""
        models = self.list_by_tags(tags) if tags else self.list_enabled()
        
        if not models:
            return None
        
        return min(
            models,
            key=lambda m: (
                m.pricing.input_price_per_1k + m.pricing.output_price_per_1k
            ) / 2 if m.pricing else float('inf')
        )
    
    def get_most_capable(self, capability: str = None) -> Optional[ModelProfile]:
        """获取能力最强的模型"""
        models = self.list_enabled()
        
        if not models:
            return None
        
        if capability:
            return max(models, key=lambda m: m.capabilities.get_capability_score(capability))
        else:
            return max(models, key=lambda m: m.capabilities.get_average())
    
    def get_best_value(self, tags: list[ModelTag] = None) -> Optional[ModelProfile]:
        """获取性价比最高的模型"""
        models = self.list_by_tags(tags) if tags else self.list_enabled()
        
        if not models:
            return None
        
        return max(models, key=lambda m: m.get_cost_effectiveness_score())


_default_registry: Optional[ModelRegistry] = None


def get_default_registry() -> ModelRegistry:
    """获取默认注册表"""
    global _default_registry
    if _default_registry is None:
        _default_registry = ModelRegistry()
    return _default_registry


def set_default_registry(registry: ModelRegistry) -> None:
    """设置默认注册表"""
    global _default_registry
    _default_registry = registry
