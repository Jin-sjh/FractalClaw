"""LLM 任务分析器"""

from __future__ import annotations

import hashlib

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from .model_selector import TaskProfile


@dataclass
class AnalysisResult:
    """分析结果"""
    task_profile: TaskProfile
    confidence: float
    reasoning: str
    raw_response: str
    processing_time: float
    cached: bool = False


@dataclass
class AnalysisCache:
    """分析结果缓存"""
    max_size: int = 100
    _cache: dict[str, tuple[AnalysisResult, datetime]] = field(default_factory=dict)
    
    def get(self, key: str) -> Optional[AnalysisResult]:
        """获取缓存"""
        if key in self._cache:
            result, timestamp = self._cache[key]
            if (datetime.now() - timestamp).seconds < 3600:
                result.cached = True
                return result
            else:
                del self._cache[key]
        return None
    
    def set(self, key: str, result: AnalysisResult) -> None:
        """设置缓存"""
        if len(self._cache) >= self.max_size:
            oldest_key = min(
                self._cache.keys(),
                key=lambda k: self._cache[k][1]
            )
            del self._cache[oldest_key]
        
        self._cache[key] = (result, datetime.now())


TASK_ANALYSIS_PROMPT = """你是一个专业的任务分析助手。请分析以下用户请求，提取任务特征。

## 用户请求
{user_input}

## 上下文信息（可选）
{context}

## 分析要求
请仔细分析用户请求，判断以下特征：

### 1. 任务复杂度 (complexity)
- **simple**: 简单的查询、翻译、格式转换等，通常只需单步操作
- **medium**: 需要一定推理、分析、或多个步骤的任务
- **complex**: 需要深度推理、复杂编程、多系统协调的任务

### 2. 任务类型 (task_type)
- **code**: 编程、代码生成、代码审查、调试
- **research**: 研究、分析、总结、信息检索
- **coordinate**: 协调多个任务或系统
- **test**: 测试、验证、质量检查
- **data**: 数据处理、分析、可视化
- **chat**: 日常对话、问答、创意写作
- **general**: 通用任务

### 3. 任务重要性 (importance)
- **low**: 普通查询、非关键任务
- **medium**: 常规工作任务
- **high**: 关键任务、生产环境、重要决策

### 4. 特殊需求
- **requires_multimodal**: 是否需要处理图像、音频等多模态内容
- **requires_code**: 是否涉及代码生成或分析
- **requires_reasoning**: 是否需要深度推理
- **requires_fast_response**: 是否需要快速响应（如实时对话）

### 5. 其他
- **budget_sensitive**: 是否对成本敏感
- **estimated_tokens**: 预估的 token 数量

## 输出格式
请以 JSON 格式输出分析结果：
```json
{
    "complexity": "simple|medium|complex",
    "task_type": "code|research|coordinate|test|data|chat|general",
    "importance": "low|medium|high",
    "requires_multimodal": true/false,
    "requires_code": true/false,
    "requires_reasoning": true/false,
    "requires_fast_response": true/false,
    "budget_sensitive": true/false,
    "estimated_tokens": 数字,
    "reasoning": "简要说明你的分析依据"
}
```

请只输出 JSON，不要有其他内容。"""


class TaskAnalyzer:
    """LLM 任务分析器"""
    
    DEFAULT_MODEL = ""
    
    def __init__(
        self,
        llm_provider: Any,
        model: Optional[str] = None,
        enable_cache: bool = True,
        fallback_on_error: bool = True
    ):
        self._provider = llm_provider
        self._model = model or self.DEFAULT_MODEL
        self._enable_cache = enable_cache
        self._fallback_on_error = fallback_on_error
        self._cache = AnalysisCache() if enable_cache else None
    
    async def analyze(
        self,
        user_input: str,
        context: Optional[dict[str, Any]] = None
    ) -> AnalysisResult:
        """分析用户输入，提取任务特征"""
        start_time = time.time()
        
        cache_key = self._generate_cache_key(user_input, context)
        if self._enable_cache and self._cache:
            cached = self._cache.get(cache_key)
            if cached:
                return cached
        
        try:
            prompt = self._build_prompt(user_input, context)
            response = await self._call_llm(prompt)
            task_profile, confidence, reasoning = self._parse_response(response)
            
            result = AnalysisResult(
                task_profile=task_profile,
                confidence=confidence,
                reasoning=reasoning,
                raw_response=response,
                processing_time=time.time() - start_time
            )
            
            if self._enable_cache and self._cache:
                self._cache.set(cache_key, result)
            
            return result
            
        except Exception as e:
            if self._fallback_on_error:
                return self._fallback_analyze(user_input, context, str(e))
            raise
    
    def _generate_cache_key(self, user_input: str, context: Optional[dict[str, Any]] = None) -> str:
        """生成缓存键"""
        content = user_input + str(context or "")
        return hashlib.md5(content.encode()).hexdigest()
    
    def _build_prompt(self, user_input: str, context: Optional[dict[str, Any]] = None) -> str:
        """构建分析提示词"""
        context_str = json.dumps(context, ensure_ascii=False) if context else "无"
        return TASK_ANALYSIS_PROMPT.format(
            user_input=user_input,
            context=context_str
        )
    
    async def _call_llm(self, prompt: str) -> str:
        """调用 LLM"""
        from .engine import LLMConfig, Message, MessageRole
        
        config = LLMConfig(
            model=self._model,
            temperature=0.3,
            max_tokens=500
        )
        
        messages = [Message(role=MessageRole.USER, content=prompt)]
        response = await self._provider.complete(messages, config)
        
        return str(response.content)
    
    def _parse_response(
        self,
        response: str
    ) -> tuple[TaskProfile, float, str]:
        """解析 LLM 响应"""
        json_str = self._extract_json(response)
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            raise ValueError(f"无法解析 LLM 响应: {response[:100]}")
        
        required_fields = ["complexity", "task_type", "importance"]
        for field_name in required_fields:
            if field_name not in data:
                raise ValueError(f"缺少必需字段: {field_name}")
        
        task_profile = TaskProfile.from_analysis(data)
        confidence = self._calculate_confidence(data)
        reasoning = data.get("reasoning", "")
        
        return task_profile, confidence, reasoning
    
    def _extract_json(self, text: str) -> str:
        from .response_parser import extract_json_from_llm_response

        result = extract_json_from_llm_response(text)
        if result is not None:
            return json.dumps(result)
        return text
    
    def _calculate_confidence(self, data: dict[str, Any]) -> float:
        """计算分析置信度"""
        confidence = 1.0
        
        if not data.get("reasoning"):
            confidence -= 0.2
        
        expected_fields = [
            "complexity", "task_type", "importance",
            "requires_code", "requires_reasoning"
        ]
        missing = sum(1 for f in expected_fields if f not in data)
        confidence -= missing * 0.1
        
        return max(0.0, min(1.0, confidence))
    
    def _fallback_analyze(
        self,
        user_input: str,
        context: Optional[dict[str, Any]],
        error: str
    ) -> AnalysisResult:
        from .task_classifier import classify_by_keywords, classification_to_analysis_dict

        result = classify_by_keywords(user_input)
        analysis = classification_to_analysis_dict(result)

        return AnalysisResult(
            task_profile=TaskProfile.from_analysis(analysis),
            confidence=0.5,
            reasoning=f"基于关键词的规则分析（LLM 分析失败: {error}）",
            raw_response="",
            processing_time=0.0
        )
