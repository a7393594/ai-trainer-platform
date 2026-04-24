"""Verify a provider API key by making a tiny, cheap test call through LiteLLM."""
from __future__ import annotations

import logging

import litellm

logger = logging.getLogger(__name__)

# Cheapest non-free model per provider; 1-token ping.
PROVIDER_TEST_MODELS: dict[str, str] = {
    # Non-reasoning classic chat models — reasoning/thinking models consume the
    # 1-token budget on hidden reasoning and return "output limit reached" errors.
    "openai": "gpt-4o-mini",
    "google": "gemini/gemini-2.0-flash",
    "groq": "groq/llama-3.1-8b-instant",
    "deepseek": "deepseek/deepseek-chat",
    "openrouter": "openrouter/meta-llama/llama-3.3-70b-instruct:free",
}


def _is_auth_failure(err_msg: str) -> bool:
    """True if the error message looks like an auth/permission failure (key is invalid).

    Non-auth runtime errors (rate limit / context length / output limit / reasoning
    token budget) are treated as passes — the API accepted our credentials, it just
    can't fulfill the 1-token ping request right now. That still proves the key works.
    """
    lo = err_msg.lower()
    # Runtime-level failures where the API ACCEPTED credentials but couldn't complete:
    # quota, rate-limit, too-small max_tokens on reasoning models, too-long context, etc.
    # Treat all as "key verified".
    soft_pass_markers = (
        # Rate limiting
        "ratelimit", "rate_limit", "rate limit", "quota", "429", "too many request",
        # Output / max_tokens exhaustion (reasoning models consume budget on hidden tokens)
        "max_tokens", "max tokens", "output limit", "output_limit_reached",
        "could not finish the message",
        # Context length
        "context length", "context_length_exceeded", "context window", "maximum context length",
        # finish_reason length
        "finish_reason", "finish reason",
    )
    if any(s in lo for s in soft_pass_markers):
        return False
    # Clear auth signals
    if any(s in lo for s in (
        "401", "403",
        "invalid api key", "invalid_api_key", "incorrect api key",
        "authentication", "authenticationerror",
        "unauthorized", "permission", "forbidden",
        "api key not valid", "missing api key",
    )):
        return True
    # Unknown error → treat as failure to be safe (don't false-positive verify)
    return True


async def test_call(provider: str, api_key: str, timeout: float = 10.0) -> tuple[bool, str | None, str]:
    """Return (ok, error_msg, model_used).

    Verified = either a 2xx response, OR a non-auth error (e.g., rate limit) that
    still proves the key was accepted. Only auth/permission failures count as unverified.
    """
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
        if len(msg) > 500:
            msg = msg[:500]
        if _is_auth_failure(msg):
            logger.info("provider key verify failed (auth) provider=%s: %s", provider, msg)
            return False, msg, model
        # Non-auth error → key IS working, just hit a runtime issue. Mark verified.
        logger.info("provider key verify soft-pass provider=%s (non-auth err): %s", provider, msg)
        return True, f"通過（但伺服器回 {msg[:200]}）", model
