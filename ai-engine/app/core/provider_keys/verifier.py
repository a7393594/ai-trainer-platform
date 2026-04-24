"""Verify a provider API key by making a tiny, cheap test call through LiteLLM."""
from __future__ import annotations

import logging

import litellm

logger = logging.getLogger(__name__)

# Cheapest non-free model per provider; 1-token ping.
PROVIDER_TEST_MODELS: dict[str, str] = {
    "openai": "gpt-5.4-nano",
    # gemini-1.5-flash is stable (non-preview), widely available on free tier
    "google": "gemini/gemini-1.5-flash",
    "groq": "groq/llama-3.1-8b-instant",
    "deepseek": "deepseek/deepseek-chat",
    "openrouter": "openrouter/meta-llama/llama-3.3-70b-instruct:free",
}


async def test_call(provider: str, api_key: str, timeout: float = 10.0) -> tuple[bool, str | None, str]:
    """Return (ok, error_msg, model_used). Any 2xx response counts as success."""
    model = PROVIDER_TEST_MODELS.get(provider)
    if not model:
        return False, f"no test model configured for provider={provider}", ""
    try:
        await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            api_key=api_key,
            timeout=timeout,
        )
        return True, None, model
    except Exception as e:
        msg = str(e)
        # Trim overly long provider errors
        if len(msg) > 500:
            msg = msg[:500]
        logger.info("provider key verify failed provider=%s: %s", provider, msg)
        return False, msg, model
