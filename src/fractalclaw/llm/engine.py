"""LLM Engine for Agent communication with language models."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable, Optional

logger = logging.getLogger(__name__)


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
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    stream: bool = True
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout: float = 60.0
    max_retries: int = 3
    retry_delay: float = 1.0


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
    ):
        self.config = config
        self._provider = provider
        self._context: list[Message] = []
        self._system_prompt: Optional[str] = None
        self._on_token: Optional[Callable[[str], None]] = None
        self._on_tool_call: Optional[Callable[[dict[str, Any]], None]] = None

    def set_provider(self, provider: LLMProvider) -> None:
        self._provider = provider

    def set_system_prompt(self, prompt: str) -> None:
        self._system_prompt = prompt

    def set_callbacks(
        self,
        on_token: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> None:
        self._on_token = on_token
        self._on_tool_call = on_tool_call

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
    ) -> LLMResponse:
        if not self._provider:
            raise RuntimeError("LLM provider not set")

        self.add_user_message(user_input)
        messages = self.get_context()

        if self.config.stream:
            return await self._stream_and_collect(messages, tools)
        else:
            return await self._complete(messages, tools)

    async def _complete(
        self,
        messages: list[Message],
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> LLMResponse:
        assert self._provider is not None
        response = await self._provider.complete(messages, self.config, tools)

        self.add_assistant_message(response.content, response.tool_calls)

        if response.tool_calls and self._on_tool_call:
            for tool_call in response.tool_calls:
                self._on_tool_call(tool_call)

        return response

    async def _stream_and_collect(
        self,
        messages: list[Message],
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> LLMResponse:
        assert self._provider is not None
        content_chunks: list[str] = []

        async for chunk in self._provider.stream(messages, self.config, tools):
            content_chunks.append(chunk)
            if self._on_token:
                self._on_token(chunk)

        full_content = "".join(content_chunks)
        self.add_assistant_message(full_content)

        return LLMResponse(
            content=full_content,
            model=self.config.model,
            usage={},
            finish_reason="stop",
        )

    async def stream(
        self,
        user_input: str,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AsyncIterator[str]:
        if not self._provider:
            raise RuntimeError("LLM provider not set")

        self.add_user_message(user_input)
        messages = self.get_context()

        assert self._provider is not None
        content_chunks: list[str] = []

        async for chunk in self._provider.stream(messages, self.config, tools):
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
