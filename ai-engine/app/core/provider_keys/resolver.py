"""Resolve the right API key for a (tenant, provider) pair at call time.

Precedence: per-tenant DB key > server env var. Anthropic is env-only by design
(keeps the Claude path stable and independent of tenant state).
"""
from __future__ import annotations

from typing import Optional

from app.config import settings
from app.core.provider_keys import crypto, service


ENV_KEY_BY_PROVIDER: dict[str, str] = {
    "anthropic": "anthropic_api_key",
    "openai": "openai_api_key",
    "google": "google_api_key",
    "groq": "groq_api_key",
    "deepseek": "deepseek_api_key",
    "openrouter": "openrouter_api_key",
}


def parse_provider(model: str) -> str:
    """Infer provider from LiteLLM-style model string.

    Examples:
      "claude-sonnet-4-6"                  -> anthropic
      "gpt-5.4-nano" / "o1-mini"           -> openai
      "gemini/gemini-3.1-pro"              -> google
      "groq/llama-3.3-70b-versatile"       -> groq
      "deepseek/deepseek-chat"             -> deepseek
      "openrouter/meta-llama/..."          -> openrouter
    """
    if not model:
        return ""
    m = model.lower()
    # Check provider prefix first (most reliable)
    if m.startswith("anthropic/") or m.startswith("claude"):
        return "anthropic"
    if m.startswith("openai/") or m.startswith("gpt-") or m.startswith("o1") or m.startswith("o3") or m.startswith("chatgpt"):
        return "openai"
    if m.startswith("gemini/") or m.startswith("gemini-") or m.startswith("google/"):
        return "google"
    if m.startswith("groq/"):
        return "groq"
    if m.startswith("deepseek/"):
        return "deepseek"
    if m.startswith("openrouter/"):
        return "openrouter"
    return ""


def resolve_api_key(tenant_id: Optional[str], provider: str) -> Optional[str]:
    """Return the API key string to pass to LiteLLM, or None if unavailable."""
    if not provider:
        return None

    # Anthropic is env-only
    if provider == "anthropic":
        return settings.anthropic_api_key or None

    # Per-tenant DB key wins if crypto is configured
    if tenant_id and crypto.is_configured():
        try:
            db_key = service.get_key(tenant_id, provider)
            if db_key:
                return db_key
        except Exception:
            # Never fail the request because of a lookup glitch; fall through to env
            pass

    # Fall back to server env var
    attr = ENV_KEY_BY_PROVIDER.get(provider)
    if attr:
        return getattr(settings, attr, None) or None
    return None
