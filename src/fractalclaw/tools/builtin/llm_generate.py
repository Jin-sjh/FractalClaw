"""LLM Generate Tool - 调用 LLM 生成内容的基础工具"""

from typing import Any, Optional

from pydantic import Field

from fractalclaw.tools.base import BaseTool, ToolParameters, ToolResult


class LLMGenerateParameters(ToolParameters):
    prompt: str = Field(description="提示词内容")
    system_prompt: Optional[str] = Field(default=None, description="系统提示词")
    model: Optional[str] = Field(default=None, description="模型名称，不指定则使用默认模型")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="温度参数")
    max_tokens: int = Field(default=2048, ge=1, le=32768, description="最大生成 token 数")
    response_format: Optional[str] = Field(default=None, description="响应格式，如 'json'")


class LLMGenerateTool(BaseTool):
    name = "llm_generate"
    description = "调用 LLM 生成内容，用于 AI 辅助生成任务"
    parameters_model = LLMGenerateParameters
    category = "llm"
    tags = ["llm", "generate", "ai"]

    def __init__(self, llm_provider: Any = None, default_model: str = "gpt-4"):
        self._llm_provider = llm_provider
        self._default_model = default_model

    def set_provider(self, provider: Any) -> None:
        self._llm_provider = provider

    async def execute(self, params: LLMGenerateParameters, ctx: Any) -> ToolResult:
        if not self._llm_provider:
            return ToolResult.error(
                title="LLM Generate Error",
                error_message="LLM provider not configured"
            )

        try:
            from fractalclaw.llm.engine import LLMConfig, LLMEngine, Message, MessageRole

            model = params.model or self._default_model
            config = LLMConfig(
                model=model,
                temperature=params.temperature,
                max_tokens=params.max_tokens,
                stream=False
            )

            engine = LLMEngine(config=config, provider=self._llm_provider)

            if params.system_prompt:
                engine.set_system_prompt(params.system_prompt)

            messages = []
            if params.system_prompt:
                messages.append(Message(role=MessageRole.SYSTEM, content=params.system_prompt))
            messages.append(Message(role=MessageRole.USER, content=params.prompt))

            response = await self._llm_provider.complete(messages, config)

            return ToolResult(
                title="LLM Generated Content",
                output=response.content,
                metadata={
                    "model": response.model,
                    "usage": response.usage,
                    "finish_reason": response.finish_reason
                }
            )

        except Exception as e:
            return ToolResult.error(
                title="LLM Generate Error",
                error_message=str(e)
            )
