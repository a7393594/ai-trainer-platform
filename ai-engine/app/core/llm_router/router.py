"""
LLM Router — 多模型切換器 + 成本追蹤
透過 LiteLLM 統一介面呼叫任何 LLM（Claude / GPT / Gemini / Llama ...）
"""
import asyncio
import logging
import time
from collections import deque
from typing import Deque, Optional, Tuple
import litellm
from app.config import settings

from app.core.llm_router.models import get_model_pricing

logger = logging.getLogger(__name__)

# Embedding pricing per 1M tokens (USD). Only input is billed.
EMBEDDING_PRICING = {
    "text-embedding-3-small": 0.02,
    "text-embedding-3-large": 0.13,
    "text-embedding-ada-002": 0.10,
}

# Anthropic prompt caching multipliers applied to base input price:
#   cache write (creation) = 1.25x base input
#   cache read             = 0.10x base input
ANTHROPIC_CACHE_WRITE_MULTIPLIER = 1.25
ANTHROPIC_CACHE_READ_MULTIPLIER = 0.10


class NoProviderKeyError(Exception):
    """LiteLLM rejected the call because no usable API key for `provider`.

    Carries structured info so the FastAPI exception handler can return a 400
    with a friendly message + link to Settings → Provider API Keys.
    """

    def __init__(self, provider: str, model: str, original: str = ""):
        self.provider = provider
        self.model = model
        self.original = original
        super().__init__(f"no api key for provider={provider} model={model}: {original[:200]}")


def _looks_like_auth_error(msg: str) -> bool:
    lo = msg.lower()
    return any(s in lo for s in (
        "api_key", "api key", "x-api-key",
        "authentication", "authenticationerror",
        "401", "403",
        "invalid_api_key", "incorrect api key", "api key not valid", "missing api key",
    ))


def _inject_api_key(kwargs: dict, model: str, tenant_id: Optional[str]) -> None:
    """Resolve per-tenant key (DB > env) and set kwargs['api_key'] so LiteLLM uses it.

    Does nothing for Anthropic (LiteLLM reads litellm.anthropic_key set at init),
    and for providers with no resolvable key (LiteLLM will fall back to env var
    or error out with a clear auth message).
    """
    try:
        from app.core.provider_keys.resolver import parse_provider, resolve_api_key
    except Exception:
        return  # provider_keys module optional at import time
    provider = parse_provider(model)
    if not provider or provider == "anthropic":
        return
    key = resolve_api_key(tenant_id, provider)
    if key:
        kwargs["api_key"] = key


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


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> float:
    """Cost in USD. Reads pricing fresh each call so model edits take effect without restart.

    For Anthropic prompt caching:
      - `input_tokens` should already EXCLUDE cached portions (LiteLLM behaviour).
      - cache write tokens billed at 1.25x base input price.
      - cache read tokens billed at 0.10x base input price.
    """
    pricing = get_model_pricing().get(model, {"input": 0, "output": 0})
    base_input = pricing["input"]
    base_output = pricing["output"]
    return (
        input_tokens * base_input
        + output_tokens * base_output
        + cache_creation_input_tokens * base_input * ANTHROPIC_CACHE_WRITE_MULTIPLIER
        + cache_read_input_tokens * base_input * ANTHROPIC_CACHE_READ_MULTIPLIER
    ) / 1_000_000


def calculate_embedding_cost(model: str, input_tokens: int) -> float:
    # `model` may arrive as "openai/text-embedding-3-small" — strip provider prefix.
    bare = model.split("/", 1)[1] if "/" in model else model
    rate = EMBEDDING_PRICING.get(bare, 0)
    return (input_tokens * rate) / 1_000_000


def _extract_anthropic_cache_tokens(usage) -> tuple[int, int]:
    """Pull cache_creation_input_tokens / cache_read_input_tokens from a LiteLLM usage object.

    LiteLLM exposes these on the top-level usage object for Anthropic responses, but field
    names vary across versions. Returns (cache_creation, cache_read), defaulting to 0.
    """
    if not usage:
        return 0, 0
    cache_creation = (
        getattr(usage, "cache_creation_input_tokens", None)
        or getattr(usage, "prompt_tokens_details", None)
        and getattr(usage.prompt_tokens_details, "cached_tokens_creation", 0)
        or 0
    )
    cache_read = (
        getattr(usage, "cache_read_input_tokens", None)
        or getattr(usage, "prompt_tokens_details", None)
        and getattr(usage.prompt_tokens_details, "cached_tokens", 0)
        or 0
    )
    return int(cache_creation or 0), int(cache_read or 0)


def _log_usage(
    project_id: Optional[str],
    session_id: Optional[str],
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost: float,
    latency_ms: int,
    endpoint: str = "chat",
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
):
    """Insert one row into ait_llm_usage. Logs (but doesn't raise) on failure."""
    try:
        from app.db.supabase import get_supabase
        get_supabase().table("ait_llm_usage").insert({
            "project_id": project_id or "00000000-0000-0000-0000-000000000000",
            "session_id": session_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens + cache_creation_input_tokens + cache_read_input_tokens,
            "cost_usd": round(cost, 8),
            "latency_ms": latency_ms,
            "endpoint": endpoint,
            "cache_creation_input_tokens": cache_creation_input_tokens,
            "cache_read_input_tokens": cache_read_input_tokens,
        }).execute()
    except Exception as e:
        logger.warning(
            "ait_llm_usage insert failed (model=%s, endpoint=%s, cost=%.6f): %s",
            model, endpoint, cost, e,
        )


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

    model_count = len(get_model_pricing())
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

    _inject_api_key(kwargs, model, tenant_id)

    # 排隊等待 quota，避免 Anthropic rate_limit_error
    await _rate_limiter.acquire(_estimate_tokens(messages))

    start = time.time()
    try:
        response = await litellm.acompletion(**kwargs)
    except Exception as e:
        # Detect auth-failure → translate to friendly NoProviderKeyError so the
        # FastAPI handler can return a 400 with a "configure key in Settings" link.
        from app.core.provider_keys.resolver import parse_provider as _pp
        provider = _pp(model)
        if provider and provider != "anthropic" and _looks_like_auth_error(str(e)):
            raise NoProviderKeyError(provider=provider, model=model, original=str(e)) from e
        raise
    latency = int((time.time() - start) * 1000)

    # Extract token usage. For Anthropic, prompt_tokens already EXCLUDES cached tokens
    # (which are reported separately as cache_creation_input_tokens / cache_read_input_tokens).
    usage = getattr(response, 'usage', None)
    input_tokens = getattr(usage, 'prompt_tokens', 0) if usage else 0
    output_tokens = getattr(usage, 'completion_tokens', 0) if usage else 0
    cache_creation, cache_read = _extract_anthropic_cache_tokens(usage)
    cost = calculate_cost(model, input_tokens, output_tokens, cache_creation, cache_read)

    if project_id:
        _log_usage(
            project_id, session_id, model, input_tokens, output_tokens, cost, latency,
            cache_creation_input_tokens=cache_creation,
            cache_read_input_tokens=cache_read,
        )

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
    # 套用 Anthropic prompt caching（與非 streaming 路徑一致）
    effective_messages = _apply_anthropic_cache(messages, model)

    kwargs = {
        "model": model,
        "messages": effective_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        # 要求最後一個 chunk 帶 usage（OpenAI/Anthropic 都支援；LiteLLM 統一轉發）
        "stream_options": {"include_usage": True},
        "metadata": {"tenant_id": tenant_id} if tenant_id else {},
    }
    _inject_api_key(kwargs, model, tenant_id)
    await _rate_limiter.acquire(_estimate_tokens(messages))

    start = time.time()
    full_text = ""
    final_usage = None
    try:
        response = await litellm.acompletion(**kwargs)
    except Exception as e:
        from app.core.provider_keys.resolver import parse_provider as _pp
        provider = _pp(model)
        if provider and provider != "anthropic" and _looks_like_auth_error(str(e)):
            raise NoProviderKeyError(provider=provider, model=model, original=str(e)) from e
        raise
    async for chunk in response:
        # usage 通常只在最後一個 chunk 出現，可能 choices=[]
        chunk_usage = getattr(chunk, "usage", None)
        if chunk_usage is not None:
            final_usage = chunk_usage
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        delta = choices[0].delta
        if delta and delta.content:
            full_text += delta.content
            yield delta.content

    latency = int((time.time() - start) * 1000)

    if final_usage is not None:
        input_tokens = int(getattr(final_usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(final_usage, "completion_tokens", 0) or 0)
        cache_creation, cache_read = _extract_anthropic_cache_tokens(final_usage)
        token_estimate = False
    else:
        # Provider 沒回 usage（少見，但 fallback 仍要存在）。
        # 改用 LiteLLM 內建的 token_counter 取代 chars*0.3 — 對中文也準確。
        try:
            input_tokens = litellm.token_counter(model=model, messages=messages)
            output_tokens = litellm.token_counter(model=model, text=full_text)
        except Exception:
            input_tokens = max(1, sum(len(str(m.get("content", ""))) for m in messages) // 4)
            output_tokens = max(1, len(full_text) // 4)
        cache_creation, cache_read = 0, 0
        token_estimate = True

    cost = calculate_cost(model, input_tokens, output_tokens, cache_creation, cache_read)

    if project_id:
        _log_usage(
            project_id, session_id, model,
            input_tokens, output_tokens, cost, latency,
            endpoint="chat_stream",
            cache_creation_input_tokens=cache_creation,
            cache_read_input_tokens=cache_read,
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
            metadata={"streaming": True, "token_estimate": token_estimate},
        )
    except Exception:
        pass


async def get_embedding(
    text: str,
    project_id: Optional[str] = None,
    session_id: Optional[str] = None,
    endpoint: str = "embedding",
    tenant_id: Optional[str] = None,
) -> list[float]:
    """取得文字的 Embedding 向量，並記錄成本到 ait_llm_usage。"""
    model = f"{settings.embedding_provider}/{settings.embedding_model}"
    start = time.time()
    emb_kwargs: dict = {"model": model, "input": [text]}
    _inject_api_key(emb_kwargs, model, tenant_id)
    response = await litellm.aembedding(**emb_kwargs)
    latency = int((time.time() - start) * 1000)

    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
    cost = calculate_embedding_cost(model, input_tokens)

    if project_id:
        _log_usage(
            project_id, session_id, model,
            input_tokens=input_tokens,
            output_tokens=0,
            cost=cost,
            latency_ms=latency,
            endpoint=endpoint,
        )

    return response.data[0]["embedding"]
