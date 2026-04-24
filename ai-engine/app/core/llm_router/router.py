"""
LLM Router — 多模型切換器 + 成本追蹤
透過 LiteLLM 統一介面呼叫任何 LLM（Claude / GPT / Gemini / Llama ...）
"""
import asyncio
import time
from collections import deque
from typing import Deque, Optional, Tuple
import litellm
from app.config import settings

from app.core.llm_router.models import get_model_pricing

MODEL_PRICING = get_model_pricing()


# ---------------------------------------------------------------------------
# Sliding-window token bucket — 防止觸及 Anthropic 30K tokens/min rate limit
# 超標時排隊等待，而非直接回傳 rate_limit_error 給前端。
# ---------------------------------------------------------------------------

class _TokenRateLimiter:
    """Per-process sliding-window token bucket. Thread-safe via asyncio.Lock."""

    def __init__(self, tpm_limit: int = 27_000, window_sec: int = 60) -> None:
        self._limit = tpm_limit          # 27K < 30K，留 3K buffer
        self._window_sec = window_sec
        self._lock = asyncio.Lock()
        self._entries: Deque[Tuple[float, int]] = deque()

    def _prune(self, now: float) -> int:
        cutoff = now - self._window_sec
        while self._entries and self._entries[0][0] < cutoff:
            self._entries.popleft()
        return sum(t for _, t in self._entries)

    async def acquire(self, tokens: int) -> None:
        """等到 window 內有足夠 quota 才回傳，不超時不失敗。"""
        while True:
            async with self._lock:
                now = time.time()
                used = self._prune(now)
                if used + tokens <= self._limit:
                    self._entries.append((now, tokens))
                    return
                # 計算需等多久直到最舊的 entry 滑出 window
                oldest_ts = self._entries[0][0]
                wait = self._window_sec - (now - oldest_ts) + 0.5
            await asyncio.sleep(max(wait, 1.0))


_rate_limiter = _TokenRateLimiter(tpm_limit=27_000)


def _estimate_tokens(messages: list[dict]) -> int:
    """粗估輸入 token 數（chars / 4），用於 rate limiter 預留 quota。"""
    chars = 0
    for m in messages:
        c = m.get("content", "")
        if isinstance(c, str):
            chars += len(c)
        elif isinstance(c, list):
            for block in c:
                if isinstance(block, dict):
                    chars += len(block.get("text", ""))
    return max(1, chars // 4)


def _apply_anthropic_cache(messages: list[dict], model: str) -> list[dict]:
    """為 Anthropic 模型的長 system message 加 cache_control，重複呼叫時 input cost 降 10 倍。

    Anthropic 最小 cacheable 長度約 1024 tokens（~4096 chars）。只處理 claude-* 模型。
    """
    if not model or not ("claude" in model.lower() or "anthropic" in model.lower()):
        return messages
    if not messages:
        return messages
    # 檢查第一個 system message
    first = messages[0]
    if first.get("role") != "system":
        return messages
    content = first.get("content", "")
    if not isinstance(content, str) or len(content) < 4096:
        return messages
    # 轉成帶 cache_control 的 content blocks
    new_messages = list(messages)
    new_messages[0] = {
        "role": "system",
        "content": [
            {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
        ],
    }
    return new_messages


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model, {"input": 0, "output": 0})
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


def _log_usage(project_id: Optional[str], session_id: Optional[str], model: str,
               input_tokens: int, output_tokens: int, cost: float, latency_ms: int, endpoint: str = "chat"):
    """Fire-and-forget usage logging"""
    try:
        from app.db.supabase import get_supabase
        get_supabase().table("ait_llm_usage").insert({
            "project_id": project_id or "00000000-0000-0000-0000-000000000000",
            "session_id": session_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cost_usd": round(cost, 8),
            "latency_ms": latency_ms,
            "endpoint": endpoint,
        }).execute()
    except Exception:
        pass  # non-critical


def init_llm_router():
    """初始化 LLM 環境變數，LiteLLM 會自動讀取"""
    import os

    if settings.openai_api_key:
        litellm.openai_key = settings.openai_api_key
    if settings.anthropic_api_key:
        litellm.anthropic_key = settings.anthropic_api_key
    if settings.google_api_key:
        litellm.google_key = settings.google_api_key

    # New providers
    if settings.groq_api_key:
        os.environ["GROQ_API_KEY"] = settings.groq_api_key
    if settings.deepseek_api_key:
        os.environ["DEEPSEEK_API_KEY"] = settings.deepseek_api_key
    if settings.openrouter_api_key:
        os.environ["OPENROUTER_API_KEY"] = settings.openrouter_api_key

    # 開啟成本追蹤
    litellm.success_callback = ["langfuse"] if settings.langfuse_public_key else []

    model_count = len(MODEL_PRICING)
    print(f"[OK] LLM Router initialized ({model_count} models)")


async def chat_completion(
    messages: list[dict],
    model: str = "claude-sonnet-4-20250514",
    temperature: float = 0.7,
    max_tokens: int = 2000,
    tools: Optional[list[dict]] = None,
    tenant_id: Optional[str] = None,
    project_id: Optional[str] = None,
    session_id: Optional[str] = None,
    span_label: str = "llm_call",
) -> dict:
    """
    統一的 LLM 呼叫介面（含成本追蹤 + Pipeline Studio 追蹤）
    """
    # Anthropic Prompt Caching：只對 claude-* 模型套用，把長 system message 標為 cacheable
    # 重複呼叫同 system prompt 時 input cost 降到 10%（cached read）
    effective_messages = _apply_anthropic_cache(messages, model)

    kwargs = {
        "model": model,
        "messages": effective_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "metadata": {"tenant_id": tenant_id} if tenant_id else {},
    }

    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    # 排隊等待 quota，避免 Anthropic rate_limit_error
    await _rate_limiter.acquire(_estimate_tokens(messages))

    start = time.time()
    response = await litellm.acompletion(**kwargs)
    latency = int((time.time() - start) * 1000)

    # Extract token usage
    usage = getattr(response, 'usage', None)
    input_tokens = getattr(usage, 'prompt_tokens', 0) if usage else 0
    output_tokens = getattr(usage, 'completion_tokens', 0) if usage else 0
    cost = calculate_cost(model, input_tokens, output_tokens)

    # Log usage
    if project_id:
        _log_usage(project_id, session_id, model, input_tokens, output_tokens, cost, latency)

    # Pipeline Studio tracer hook — no-op if no pipeline_run context
    try:
        from app.core.pipeline.tracer import record_llm_span
        output_text = ""
        try:
            output_text = response.choices[0].message.content or ""
        except Exception:
            pass
        tool_calls_raw = None
        try:
            tool_calls_raw = getattr(response.choices[0].message, "tool_calls", None)
        except Exception:
            pass
        record_llm_span(
            label=span_label,
            model=model,
            messages=messages,
            output_text=output_text,
            tokens_in=input_tokens,
            tokens_out=output_tokens,
            cost_usd=cost,
            latency_ms=latency,
            metadata={
                "has_tool_calls": bool(tool_calls_raw),
                "tool_call_count": len(tool_calls_raw) if tool_calls_raw else 0,
            },
        )
    except Exception:
        pass  # tracer never breaks chat

    return response


async def stream_chat_completion(
    messages: list[dict],
    model: str = "claude-sonnet-4-20250514",
    temperature: float = 0.7,
    max_tokens: int = 2000,
    tenant_id: Optional[str] = None,
    project_id: Optional[str] = None,
    session_id: Optional[str] = None,
    span_label: str = "main_model_stream",
):
    """Streaming LLM call — yields content chunks.

    收集完整文字後會補記一個 model span 到 Pipeline Studio tracer,成本由 messages 估算。
    """
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "metadata": {"tenant_id": tenant_id} if tenant_id else {},
    }
    await _rate_limiter.acquire(_estimate_tokens(messages))

    start = time.time()
    full_text = ""
    response = await litellm.acompletion(**kwargs)
    async for chunk in response:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            full_text += delta.content
            yield delta.content

    latency = int((time.time() - start) * 1000)
    # LiteLLM streaming 通常不回 usage 欄位,這裡用簡單 heuristic 估 token 數:
    # 每個字元約 0.3 tokens(粗估,用於 Pipeline Studio 顯示成本)。
    input_chars = sum(
        len(m.get("content", "")) if isinstance(m.get("content"), str) else 0
        for m in messages
    )
    input_tokens = max(1, int(input_chars * 0.3))
    output_tokens = max(1, int(len(full_text) * 0.3))
    cost = calculate_cost(model, input_tokens, output_tokens)

    if project_id:
        _log_usage(
            project_id, session_id, model,
            input_tokens, output_tokens, cost, latency,
            endpoint="chat_stream",
        )

    # Pipeline Studio tracer hook
    try:
        from app.core.pipeline.tracer import record_llm_span
        record_llm_span(
            label=span_label,
            model=model,
            messages=messages,
            output_text=full_text,
            tokens_in=input_tokens,
            tokens_out=output_tokens,
            cost_usd=cost,
            latency_ms=latency,
            metadata={"streaming": True, "token_estimate": True},
        )
    except Exception:
        pass


async def get_embedding(text: str) -> list[float]:
    """取得文字的 Embedding 向量"""
    response = await litellm.aembedding(
        model=f"{settings.embedding_provider}/{settings.embedding_model}",
        input=[text],
    )
    return response.data[0]["embedding"]
