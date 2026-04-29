"""多 Provider 管理器 - 按需创建和缓存不同 provider 的实例。"""

from __future__ import annotations

import logging
import os
from typing import Optional

from .engine import OpenAICompatibleProvider

logger = logging.getLogger(__name__)


PROVIDER_CONFIG: dict[str, dict[str, Optional[str]]] = {
    "openai": {
        "api_key_env": "OPENAI_API_KEY",
        "base_url_env": "OPENAI_API_BASE",
        "default_base_url": "https://api.openai.com/v1",
    },
    "anthropic": {
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url_env": "ANTHROPIC_BASE_URL",
        "default_base_url": "https://api.anthropic.com",
    },
    "deepseek": {
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "default_base_url": "https://api.deepseek.com/v1",
    },
    "zhipu": {
        "api_key_env": "ZHIPU_API_KEY",
        "base_url_env": "ZHIPU_BASE_URL",
        "default_base_url": "https://open.bigmodel.cn/api/paas/v4",
    },
    "alibaba": {
        "api_key_env": "DASHSCOPE_API_KEY",
        "base_url_env": "DASHSCOPE_BASE_URL",
        "default_base_url": "https://dashscope.aliyuncs.com/api/v1",
    },
    "moonshot": {
        "api_key_env": "MOONSHOT_API_KEY",
        "base_url_env": "MOONSHOT_BASE_URL",
        "default_base_url": "https://api.moonshot.cn/v1",
    },
    "ollama": {
        "api_key_env": None,
        "base_url_env": "OLLAMA_BASE_URL",
        "default_base_url": "http://localhost:11434",
    },
    "other": {
        "api_key_env": "OPENAI_API_KEY",
        "base_url_env": "OPENAI_API_BASE",
        "default_base_url": None,
    },
}


class ProviderPool:
    """多 Provider 管理器 - 按需创建和缓存不同 provider 的实例。"""

    def __init__(self) -> None:
        self._providers: dict[str, OpenAICompatibleProvider] = {}

    def get_provider(self, provider_name: str) -> Optional[OpenAICompatibleProvider]:
        """获取或创建指定 provider 的实例。

        如果 provider 已缓存则直接返回，否则从环境变量读取配置创建新实例。
        """
        if provider_name in self._providers:
            return self._providers[provider_name]

        config = PROVIDER_CONFIG.get(provider_name, PROVIDER_CONFIG["other"])

        api_key: Optional[str] = None
        if config["api_key_env"]:
            api_key = os.getenv(config["api_key_env"])
        else:
            api_key = "ollama"

        if not api_key:
            logger.warning(
                "Provider %s 不可用: 环境变量 %s 未设置",
                provider_name,
                config["api_key_env"],
            )
            return None

        base_url: Optional[str] = None
        if config["base_url_env"]:
            base_url = os.getenv(config["base_url_env"])

        if not base_url:
            base_url = config["default_base_url"]

        if not base_url:
            logger.warning("Provider %s 不可用: 无法确定 base_url", provider_name)
            return None

        try:
            provider = OpenAICompatibleProvider(api_key=api_key, base_url=base_url)
            self._providers[provider_name] = provider
            logger.info("已创建 Provider: %s (base_url=%s)", provider_name, base_url)
            return provider
        except Exception as e:
            logger.error("创建 Provider %s 失败: %s", provider_name, e)
            return None

    def is_provider_available(self, provider_name: str) -> bool:
        """检查指定 provider 是否已配置（API Key 存在）。"""
        config = PROVIDER_CONFIG.get(provider_name, PROVIDER_CONFIG["other"])
        if not config["api_key_env"]:
            return True
        return bool(os.getenv(config["api_key_env"]))

    def list_available_providers(self) -> list[str]:
        """列出所有已配置（API Key 存在）的 provider 名称。"""
        return [
            name
            for name in PROVIDER_CONFIG
            if self.is_provider_available(name)
        ]

    def clear_cache(self) -> None:
        """清除缓存的 provider 实例。"""
        self._providers.clear()
