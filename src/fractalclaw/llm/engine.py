"""LLM Engine for Agent communication with language models."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable, Optional

logger = logging.getLogger(__name__)


class LLMErrorType(Enum):
    """LLM 错误类型枚举"""
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    AUTH_ERROR = "auth_error"
    MODEL_ERROR = "model_error"
    STREAM_ERROR = "stream_error"
    UNKNOWN = "unknown"


class LLMException(Exception):
    """LLM 异常基类"""
    def __init__(self, message: str, error_type: LLMErrorType = LLMErrorType.UNKNOWN, retryable: bool = False):
        super().__init__(message)
        self.error_type = error_type
        self.retryable = retryable


class CircuitBreaker:
    """熔断器实现"""
    
    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half_open"
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._state = self.STATE_CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
    
    @property
    def state(self) -> str:
        if self._state == self.STATE_OPEN:
            if self._last_failure_time and (time.time() - self._last_failure_time) >= self.recovery_timeout:
                self._state = self.STATE_HALF_OPEN
                self._half_open_calls = 0
        return self._state
    
    def can_execute(self) -> bool:
        state = self.state
        if state == self.STATE_CLOSED:
            return True
        if state == self.STATE_HALF_OPEN:
            return self._half_open_calls < self.half_open_max_calls
        return False
    
    def record_success(self) -> None:
        if self._state == self.STATE_HALF_OPEN:
            self._state = self.STATE_CLOSED
            self._failure_count = 0
            logger.info("Circuit breaker recovered, state changed to CLOSED")
    
    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        
        if self._state == self.STATE_HALF_OPEN:
            self._state = self.STATE_OPEN
            logger.warning("Circuit breaker opened from HALF_OPEN state")
        elif self._failure_count >= self.failure_threshold:
            self._state = self.STATE_OPEN
            logger.warning(f"Circuit breaker opened after {self._failure_count} failures")


class MessageRole(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    role: MessageRole
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMConfig:
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    stream: bool = True
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout: float = 60.0
    max_retries: int = 3
    retry_delay: float = 1.0
    response_format: Optional[dict[str, Any]] = None


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict[str, int]
    finish_reason: str
    tool_calls: Optional[list[dict[str, Any]]] = None
    raw_response: Optional[dict[str, Any]] = None


class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        config: LLMConfig,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> LLMResponse:
        pass

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        config: LLMConfig,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AsyncIterator[str]:
        pass


class LLMEngine:
    def __init__(
        self,
        config: LLMConfig,
        provider: Optional[LLMProvider] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ):
        self.config = config
        self._provider = provider
        self._provider_pool: Optional[Any] = None
        self._context: list[Message] = []
        self._system_prompt: Optional[str] = None
        self._on_token: Optional[Callable[[str], None]] = None
        self._on_tool_call: Optional[Callable[[dict[str, Any]], None]] = None
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._on_error: Optional[Callable[[LLMException], None]] = None

    def set_provider(self, provider: LLMProvider) -> None:
        self._provider = provider

    def set_provider_pool(self, pool: Any) -> None:
        """设置 Provider 池，支持多 Provider 路由。"""
        self._provider_pool = pool

    def _resolve_provider(self, provider_name: Optional[str] = None) -> LLMProvider:
        """解析当前配置对应的 provider。

        如果指定了 provider_name 且有 provider_pool，则从池中获取对应 provider。
        否则使用默认 provider。
        """
        if provider_name and self._provider_pool:
            provider = self._provider_pool.get_provider(provider_name)
            if provider:
                return provider
            logger.warning("Provider %s 不可用，使用默认 provider", provider_name)
        if self._provider:
            return self._provider
        raise RuntimeError("LLM provider not set")

    def set_system_prompt(self, prompt: str) -> None:
        self._system_prompt = prompt

    def set_callbacks(
        self,
        on_token: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[dict[str, Any]], None]] = None,
        on_error: Optional[Callable[[LLMException], None]] = None,
    ) -> None:
        self._on_token = on_token
        self._on_tool_call = on_tool_call
        self._on_error = on_error
    
    def _classify_error(self, error: Exception) -> LLMException:
        """根据异常特征分类错误类型"""
        error_str = str(error).lower()
        
        if "timeout" in error_str or "timed out" in error_str:
            return LLMException(str(error), LLMErrorType.TIMEOUT, retryable=True)
        if "429" in error_str or "rate" in error_str or "overload" in error_str:
            return LLMException(str(error), LLMErrorType.RATE_LIMIT, retryable=True)
        if "401" in error_str or "403" in error_str or "auth" in error_str or "unauthorized" in error_str:
            return LLMException(str(error), LLMErrorType.AUTH_ERROR, retryable=False)
        if "connection" in error_str or "network" in error_str or "dns" in error_str:
            return LLMException(str(error), LLMErrorType.NETWORK_ERROR, retryable=True)
        if "model" in error_str or "not found" in error_str:
            return LLMException(str(error), LLMErrorType.MODEL_ERROR, retryable=False)
        
        return LLMException(str(error), LLMErrorType.UNKNOWN, retryable=True)

    def add_message(self, message: Message) -> None:
        self._context.append(message)

    def add_user_message(self, content: str) -> None:
        self.add_message(Message(role=MessageRole.USER, content=content))

    def add_assistant_message(
        self,
        content: str,
        tool_calls: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        if not content and not tool_calls:
            return
        
        if not content and tool_calls:
            content = ""
        self.add_message(
            Message(role=MessageRole.ASSISTANT, content=content, tool_calls=tool_calls)
        )

    def add_tool_result(
        self,
        tool_call_id: str,
        name: str,
        content: str,
    ) -> None:
        self.add_message(
            Message(
                role=MessageRole.TOOL,
                content=content,
                name=name,
                tool_call_id=tool_call_id,
            )
        )

    def get_context(self) -> list[Message]:
        messages = []
        if self._system_prompt:
            messages.append(Message(role=MessageRole.SYSTEM, content=self._system_prompt))
        messages.extend(self._context)
        return messages

    def clear_context(self) -> None:
        self._context.clear()

    async def chat(
        self,
        user_input: str,
        tools: Optional[list[dict[str, Any]]] = None,
        provider_name: Optional[str] = None,
    ) -> LLMResponse:
        provider = self._resolve_provider(provider_name)

        self.add_user_message(user_input)
        messages = self.get_context()

        if tools:
            return await self._complete(messages, tools, provider)
        elif self.config.stream:
            return await self._stream_and_collect(messages, tools, provider)
        else:
            return await self._complete(messages, tools, provider)

    async def _complete(
        self,
        messages: list[Message],
        tools: Optional[list[dict[str, Any]]] = None,
        provider: Optional[LLMProvider] = None,
    ) -> LLMResponse:
        provider = provider or self._provider
        if not provider:
            raise RuntimeError("LLM provider not set")
        
        if not self._circuit_breaker.can_execute():
            raise LLMException(
                "Circuit breaker is open, requests are blocked",
                LLMErrorType.RATE_LIMIT,
                retryable=False
            )
        
        try:
            response = await provider.complete(messages, self.config, tools)
            self._circuit_breaker.record_success()

            self.add_assistant_message(response.content, response.tool_calls)

            if response.tool_calls and self._on_tool_call:
                for tool_call in response.tool_calls:
                    self._on_tool_call(tool_call)

            return response
        except Exception as e:
            self._circuit_breaker.record_failure()
            llm_error = self._classify_error(e)
            if self._on_error:
                self._on_error(llm_error)
            raise llm_error from e

    async def _stream_and_collect(
        self,
        messages: list[Message],
        tools: Optional[list[dict[str, Any]]] = None,
        provider: Optional[LLMProvider] = None,
    ) -> LLMResponse:
        provider = provider or self._provider
        if not provider:
            raise RuntimeError("LLM provider not set")
        
        if not self._circuit_breaker.can_execute():
            raise LLMException(
                "Circuit breaker is open, requests are blocked",
                LLMErrorType.RATE_LIMIT,
                retryable=False
            )
        
        content_chunks: list[str] = []
        last_exception: Optional[Exception] = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                async for chunk in provider.stream(messages, self.config, tools):
                    content_chunks.append(chunk)
                    if self._on_token:
                        self._on_token(chunk)
                
                self._circuit_breaker.record_success()
                full_content = "".join(content_chunks)
                self.add_assistant_message(full_content)

                return LLMResponse(
                    content=full_content,
                    model=self.config.model,
                    usage={},
                    finish_reason="stop",
                )
            except Exception as e:
                last_exception = e
                llm_error = self._classify_error(e)
                
                if self._on_error:
                    self._on_error(llm_error)
                
                if not llm_error.retryable or attempt >= self.config.max_retries:
                    self._circuit_breaker.record_failure()
                    raise llm_error from e
                
                wait_time = self.config.retry_delay * (2 ** attempt)
                logger.warning(
                    f"Stream error ({llm_error.error_type.value}), "
                    f"retrying in {wait_time}s (attempt {attempt + 1}/{self.config.max_retries})"
                )
                await asyncio.sleep(wait_time)
        
        self._circuit_breaker.record_failure()
        raise self._classify_error(last_exception) if last_exception else LLMException("Unknown error")

    async def stream(
        self,
        user_input: str,
        tools: Optional[list[dict[str, Any]]] = None,
        provider_name: Optional[str] = None,
    ) -> AsyncIterator[str]:
        provider = self._resolve_provider(provider_name)

        self.add_user_message(user_input)
        messages = self.get_context()

        content_chunks: list[str] = []

        async for chunk in provider.stream(messages, self.config, tools):
            content_chunks.append(chunk)
            if self._on_token:
                self._on_token(chunk)
            yield chunk

        full_content = "".join(content_chunks)
        self.add_assistant_message(full_content)

    def get_token_count(self, text: str) -> int:
        return len(text) // 4

    def should_compress_context(self, max_tokens: int = 8000) -> bool:
        total_tokens = sum(
            self.get_token_count(msg.content) for msg in self._context
        )
        return total_tokens > max_tokens


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: Optional[str] = None,
    ):
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError(
                "openai package is required. Install it with: pip install openai"
            )
        
        if base_url and not base_url.rstrip('/').endswith('/v1'):
            base_url = base_url.rstrip('/') + '/v1'
        
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._default_model = model

    def _messages_to_openai_format(
        self,
        messages: list[Message],
    ) -> list[dict[str, Any]]:
        openai_messages: list[dict[str, Any]] = []

        for msg in messages:
            openai_msg: dict[str, Any] = {"role": msg.role.value}

            if msg.content is not None:
                openai_msg["content"] = msg.content
            elif msg.role == MessageRole.ASSISTANT and msg.tool_calls:
                openai_msg["content"] = ""

            if msg.name:
                openai_msg["name"] = msg.name

            if msg.tool_call_id:
                openai_msg["tool_call_id"] = msg.tool_call_id

            if msg.tool_calls:
                openai_msg["tool_calls"] = msg.tool_calls

            openai_messages.append(openai_msg)

        return openai_messages

    def _parse_tool_calls(
        self,
        response_tool_calls: Optional[list[Any]],
    ) -> Optional[list[dict[str, Any]]]:
        if not response_tool_calls:
            return None

        tool_calls = []
        for tc in response_tool_calls:
            tool_calls.append({
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            })
        return tool_calls

    async def complete(
        self,
        messages: list[Message],
        config: LLMConfig,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> LLMResponse:
        model = config.model or self._default_model
        if not model:
            raise ValueError("Model must be specified in config or provider")

        openai_messages = self._messages_to_openai_format(messages)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": openai_messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
        }

        if tools:
            kwargs["tools"] = tools

        if config.response_format:
            kwargs["response_format"] = config.response_format

        last_exception = None
        for attempt in range(config.max_retries + 1):
            try:
                response = await self._client.chat.completions.create(**kwargs)

                choice = response.choices[0]

                tool_calls = self._parse_tool_calls(choice.message.tool_calls)

                usage = {}
                if response.usage:
                    usage = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                    }

                return LLMResponse(
                    content=choice.message.content or "",
                    model=response.model,
                    usage=usage,
                    finish_reason=choice.finish_reason or "stop",
                    tool_calls=tool_calls,
                    raw_response=response.model_dump() if hasattr(response, "model_dump") else None,
                )
            except Exception as e:
                last_exception = e
                error_str = str(e)
                is_rate_limit = "429" in error_str or "rate" in error_str.lower() or "overload" in error_str.lower()
                
                if is_rate_limit and attempt < config.max_retries:
                    wait_time = config.retry_delay * (2 ** attempt)
                    logger.warning(f"Rate limit hit (429), retrying in {wait_time}s (attempt {attempt + 1}/{config.max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    raise
        
        raise last_exception

    async def stream(
        self,
        messages: list[Message],
        config: LLMConfig,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AsyncIterator[str]:
        model = config.model or self._default_model
        if not model:
            raise ValueError("Model must be specified in config or provider")

        openai_messages = self._messages_to_openai_format(messages)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": openai_messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
            "stream": True,
        }

        if tools:
            kwargs["tools"] = tools

        last_exception = None
        for attempt in range(config.max_retries + 1):
            try:
                stream = await self._client.chat.completions.create(**kwargs)

                async for chunk in stream:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            yield delta.content
                return
            except Exception as e:
                last_exception = e
                error_str = str(e)
                is_rate_limit = "429" in error_str or "rate" in error_str.lower() or "overload" in error_str.lower()
                
                if is_rate_limit and attempt < config.max_retries:
                    wait_time = config.retry_delay * (2 ** attempt)
                    logger.warning(f"Rate limit hit (429) in stream, retrying in {wait_time}s (attempt {attempt + 1}/{config.max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    raise
        
        raise last_exception
