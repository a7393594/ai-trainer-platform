"""CRUD for per-tenant provider API keys. Plaintext never leaves this module."""
from __future__ import annotations

import base64
import logging
import time
from typing import Optional

from app.core.provider_keys import crypto
from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

ALLOWED_PROVIDERS = ("openai", "google", "groq", "deepseek", "openrouter")

# In-process decryption cache: (tenant_id, provider) -> (plaintext, inserted_at)
_key_cache: dict[tuple[str, str], tuple[str, float]] = {}
_KEY_CACHE_TTL = 60.0  # seconds


def _validate_provider(provider: str) -> None:
    if provider not in ALLOWED_PROVIDERS:
        raise ValueError(f"invalid provider: {provider}")


def _encode_bytea(data: bytes) -> str:
    """PostgREST expects bytea as \\x hex string on write."""
    return "\\x" + data.hex()


def _decode_bytea(raw) -> bytes:
    """PostgREST returns bytea as hex-prefixed string on read."""
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    if isinstance(raw, str):
        if raw.startswith("\\x"):
            return bytes.fromhex(raw[2:])
        # Sometimes returned as base64 by PostgREST
        try:
            return base64.b64decode(raw)
        except Exception:
            pass
    raise ValueError(f"cannot decode bytea: {type(raw)}")


def _invalidate(tenant_id: str, provider: str) -> None:
    _key_cache.pop((tenant_id, provider), None)


def set_key(tenant_id: str, provider: str, raw_key: str, created_by: Optional[str] = None) -> dict:
    """Encrypt and upsert a provider key. Clears verified_at/last_error on write."""
    _validate_provider(provider)
    raw_key = (raw_key or "").strip()
    if not raw_key:
        raise ValueError("api_key is empty")

    ciphertext = crypto.encrypt(raw_key)
    payload = {
        "tenant_id": tenant_id,
        "provider": provider,
        "encrypted_key": _encode_bytea(ciphertext),
        "key_last4": crypto.last4(raw_key),
        "verified_at": None,
        "last_error": None,
        "last_verified_model": None,
    }
    if created_by:
        payload["created_by"] = created_by

    sb = get_supabase()
    sb.table("ait_provider_keys").upsert(payload, on_conflict="tenant_id,provider").execute()
    _invalidate(tenant_id, provider)
    return {"provider": provider, "last4": payload["key_last4"]}


def get_key(tenant_id: str, provider: str) -> Optional[str]:
    """Return decrypted plaintext or None. Cached in-process for 60s."""
    _validate_provider(provider)
    now = time.time()
    cached = _key_cache.get((tenant_id, provider))
    if cached and now - cached[1] < _KEY_CACHE_TTL:
        return cached[0]

    sb = get_supabase()
    res = (
        sb.table("ait_provider_keys")
        .select("encrypted_key")
        .eq("tenant_id", tenant_id)
        .eq("provider", provider)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        return None
    try:
        plaintext = crypto.decrypt(_decode_bytea(rows[0]["encrypted_key"]))
    except crypto.ProviderKeysDecryptError as e:
        logger.warning("decrypt failed for tenant=%s provider=%s: %s", tenant_id, provider, e)
        return None
    _key_cache[(tenant_id, provider)] = (plaintext, now)
    return plaintext


def list_keys(tenant_id: str) -> list[dict]:
    """List all provider-key rows for tenant WITHOUT plaintext. Returns 5 slots padded."""
    sb = get_supabase()
    res = (
        sb.table("ait_provider_keys")
        .select("provider, key_last4, verified_at, last_error, last_verified_model, updated_at")
        .eq("tenant_id", tenant_id)
        .execute()
    )
    existing = {r["provider"]: r for r in (res.data or [])}
    result = []
    for prov in ALLOWED_PROVIDERS:
        row = existing.get(prov)
        if row:
            result.append({
                "provider": prov,
                "last4": row.get("key_last4"),
                "verified_at": row.get("verified_at"),
                "last_error": row.get("last_error"),
                "last_verified_model": row.get("last_verified_model"),
                "updated_at": row.get("updated_at"),
                "has_key": True,
            })
        else:
            result.append({
                "provider": prov,
                "last4": None,
                "verified_at": None,
                "last_error": None,
                "last_verified_model": None,
                "updated_at": None,
                "has_key": False,
            })
    return result


def delete_key(tenant_id: str, provider: str) -> None:
    _validate_provider(provider)
    sb = get_supabase()
    sb.table("ait_provider_keys").delete().eq("tenant_id", tenant_id).eq("provider", provider).execute()
    _invalidate(tenant_id, provider)


def mark_verified(
    tenant_id: str, provider: str, ok: bool, model: str, error: Optional[str] = None
) -> None:
    _validate_provider(provider)
    from datetime import datetime, timezone
    payload = {
        "verified_at": datetime.now(timezone.utc).isoformat() if ok else None,
        "last_error": None if ok else (error or "unknown error")[:500],
        "last_verified_model": model if ok else None,
    }
    sb = get_supabase()
    sb.table("ait_provider_keys").update(payload).eq("tenant_id", tenant_id).eq("provider", provider).execute()


def get_verified_providers(tenant_id: str) -> set[str]:
    """Set of providers that have a key with verified_at not null."""
    sb = get_supabase()
    res = (
        sb.table("ait_provider_keys")
        .select("provider")
        .eq("tenant_id", tenant_id)
        .not_.is_("verified_at", "null")
        .execute()
    )
    return {r["provider"] for r in (res.data or [])}
