"""基于任务类型的模型路由器。

根据 .env 中用户配置的任务类型专用模型，将任务路由到对应的 provider 和模型。
这是模型选择的主要机制，复杂的评分/权重机制仅作为降级方案。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

from .engine import OpenAICompatibleProvider
from .provider_pool import ProviderPool

logger = logging.getLogger(__name__)


@dataclass
class RoutedModel:
    """路由选中的模型。"""

    model: str
    provider: str
    provider_instance: OpenAICompatibleProvider
    task_type: str
    source: str


TASK_TYPE_ENV_KEYS: dict[str, str] = {
    "reasoning": "MODEL_REASONING",
    "code": "MODEL_CODE",
    "research": "MODEL_RESEARCH",
    "chat": "MODEL_CHAT",
    "writing": "MODEL_WRITING",
}

FALLBACK_PROVIDER_ORDER = [
    "openai",
    "deepseek",
    "anthropic",
    "zhipu",
    "alibaba",
    "moonshot",
    "ollama",
]


class ModelRouter:
    """基于任务类型的模型路由器。

    选择优先级：
    1. .env 中任务类型专用模型 (MODEL_CODE, MODEL_REASONING 等)
    2. .env 中通用默认模型 (DEFAULT_MODEL + DEFAULT_PROVIDER)
    3. ProviderPool 中第一个可用的 provider
    """

    def __init__(self, provider_pool: Optional[ProviderPool] = None) -> None:
        self._pool = provider_pool or ProviderPool()

    @property
    def pool(self) -> ProviderPool:
        return self._pool

    def route(self, task_type: str) -> Optional[RoutedModel]:
        """根据任务类型路由到对应的模型。

        Args:
            task_type: 任务类型 (reasoning/code/research/chat/writing/general)

        Returns:
            RoutedModel 或 None（如果没有任何可用模型）
        """
        env_key = TASK_TYPE_ENV_KEYS.get(task_type)
        if env_key:
            config_str = os.getenv(env_key)
            if config_str:
                routed = self._parse_and_route(config_str, task_type, "env_config")
                if routed:
                    logger.info(
                        "任务类型 %s 路由到 %s/%s (来源: env_config/%s)",
                        task_type,
                        routed.provider,
                        routed.model,
                        env_key,
                    )
                    return routed
                logger.warning(
                    "环境变量 %s=%s 配置的 provider 不可用，尝试降级",
                    env_key,
                    config_str,
                )

        default_model = os.getenv("DEFAULT_MODEL")
        default_provider = os.getenv("DEFAULT_PROVIDER", "openai")
        if default_model:
            provider = self._pool.get_provider(default_provider)
            if provider:
                logger.info(
                    "任务类型 %s 使用默认模型 %s/%s",
                    task_type,
                    default_provider,
                    default_model,
                )
                return RoutedModel(
                    model=default_model,
                    provider=default_provider,
                    provider_instance=provider,
                    task_type=task_type,
                    source="default",
                )

        for provider_name in FALLBACK_PROVIDER_ORDER:
            if self._pool.is_provider_available(provider_name):
                provider = self._pool.get_provider(provider_name)
                if provider:
                    fallback_model = getattr(provider, "_default_model", None) or ""
                    if not fallback_model:
                        fallback_model = "gpt-3.5-turbo"
                    logger.warning(
                        "任务类型 %s 降级到 %s/%s (来源: fallback)",
                        task_type,
                        provider_name,
                        fallback_model,
                    )
                    return RoutedModel(
                        model=fallback_model,
                        provider=provider_name,
                        provider_instance=provider,
                        task_type=task_type,
                        source="fallback",
                    )

        logger.error("任务类型 %s: 没有找到任何可用的模型", task_type)
        return None

    def _parse_and_route(
        self, config_str: str, task_type: str, source: str
    ) -> Optional[RoutedModel]:
        """解析 provider/model 格式并路由。

        支持两种格式：
        - "provider/model_name" (如 "deepseek/deepseek-coder")
        - "model_name" (使用 DEFAULT_PROVIDER)
        """
        config_str = config_str.strip()
        if not config_str:
            return None

        if "/" in config_str:
            parts = config_str.split("/", 1)
            provider_name = parts[0].strip()
            model_name = parts[1].strip()
        else:
            provider_name = os.getenv("DEFAULT_PROVIDER", "openai")
            model_name = config_str

        if not model_name:
            return None

        provider = self._pool.get_provider(provider_name)
        if not provider:
            return None

        return RoutedModel(
            model=model_name,
            provider=provider_name,
            provider_instance=provider,
            task_type=task_type,
            source=source,
        )

    def get_configured_task_types(self) -> dict[str, str]:
        """获取已配置的任务类型及其模型。"""
        result: dict[str, str] = {}
        for task_type, env_key in TASK_TYPE_ENV_KEYS.items():
            value = os.getenv(env_key)
            if value:
                result[task_type] = value
        return result

    def get_routing_info(self) -> dict[str, Optional[str]]:
        """获取所有任务类型的路由信息（用于调试/展示）。"""
        info: dict[str, Optional[str]] = {}
        for task_type in list(TASK_TYPE_ENV_KEYS.keys()) + ["general"]:
            routed = self.route(task_type)
            if routed:
                info[task_type] = f"{routed.provider}/{routed.model} ({routed.source})"
            else:
                info[task_type] = None
        return info
