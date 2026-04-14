"""
LLM Router — 多模型切換器 + 成本追蹤
透過 LiteLLM 統一介面呼叫任何 LLM（Claude / GPT / Gemini / Llama ...）
"""
import time
import litellm
from typing import Optional
from app.config import settings

from app.core.llm_router.models import get_model_pricing

MODEL_PRICING = get_model_pricing()


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
) -> dict:
    """
    統一的 LLM 呼叫介面（含成本追蹤）
    """
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "metadata": {"tenant_id": tenant_id} if tenant_id else {},
    }

    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

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

    return response


async def stream_chat_completion(
    messages: list[dict],
    model: str = "claude-sonnet-4-20250514",
    temperature: float = 0.7,
    max_tokens: int = 2000,
    tenant_id: Optional[str] = None,
):
    """Streaming LLM call — yields content chunks"""
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "metadata": {"tenant_id": tenant_id} if tenant_id else {},
    }
    response = await litellm.acompletion(**kwargs)
    async for chunk in response:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content


async def get_embedding(text: str) -> list[float]:
    """取得文字的 Embedding 向量"""
    response = await litellm.aembedding(
        model=f"{settings.embedding_provider}/{settings.embedding_model}",
        input=[text],
    )
    return response.data[0]["embedding"]
