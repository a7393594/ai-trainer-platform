"""
LLM Router — 多模型切換器
透過 LiteLLM 統一介面呼叫任何 LLM（Claude / GPT / Gemini / Llama ...）
"""
import litellm
from typing import Optional
from app.config import settings


def init_llm_router():
    """初始化 LLM 環境變數，LiteLLM 會自動讀取"""
    if settings.openai_api_key:
        litellm.openai_key = settings.openai_api_key
    if settings.anthropic_api_key:
        litellm.anthropic_key = settings.anthropic_api_key
    if settings.google_api_key:
        litellm.google_key = settings.google_api_key

    # 開啟成本追蹤
    litellm.success_callback = ["langfuse"] if settings.langfuse_public_key else []
    print("[OK] LLM Router initialized")


async def chat_completion(
    messages: list[dict],
    model: str = "claude-sonnet-4-20250514",
    temperature: float = 0.7,
    max_tokens: int = 2000,
    tools: Optional[list[dict]] = None,
    tenant_id: Optional[str] = None,
) -> dict:
    """
    統一的 LLM 呼叫介面

    Args:
        messages: 對話歷史 [{"role": "user", "content": "..."}]
        model: 模型名稱（LiteLLM 格式，例如 "gpt-4o", "claude-sonnet-4-20250514"）
        temperature: 創意度（0=確定性高, 1=更有創意）
        max_tokens: 最大回覆長度
        tools: Function calling 工具定義（給 Agent 用）
        tenant_id: 租戶 ID（用於成本追蹤）

    Returns:
        LLM 回覆的完整結構
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

    response = await litellm.acompletion(**kwargs)
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
    """
    取得文字的 Embedding 向量

    Args:
        text: 要轉成向量的文字

    Returns:
        向量（list of floats）
    """
    response = await litellm.aembedding(
        model=f"{settings.embedding_provider}/{settings.embedding_model}",
        input=[text],
    )
    return response.data[0]["embedding"]
