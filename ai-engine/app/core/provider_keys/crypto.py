"""Fernet-based symmetric encryption for provider API keys stored at rest.

Master key resolution order:
  1. env var ``PROVIDER_KEYS_SECRET`` (preferred — highest separation from data)
  2. Supabase table ``ait_system_config`` row with key='provider_keys_secret'
     (fallback, auto-provisioned so the app works without env var plumbing)

Both support a comma-separated list for rotation — first entry is the new
write key, the rest are legacy read keys kept around until data is re-encrypted.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from cryptography.fernet import Fernet, MultiFernet, InvalidToken

from app.config import settings

logger = logging.getLogger(__name__)


class ProviderKeysSecretMissing(RuntimeError):
    pass


class ProviderKeysDecryptError(RuntimeError):
    pass


def _read_secret_from_db() -> str | None:
    """Read master key from ait_system_config. Returns None if table or row missing."""
    try:
        from app.db.supabase import get_supabase
        res = (
            get_supabase()
            .table("ait_system_config")
            .select("value")
            .eq("key", "provider_keys_secret")
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if rows:
            return rows[0].get("value")
    except Exception as e:
        logger.warning("cannot read provider_keys_secret from DB: %s", e)
    return None


def _resolve_secret() -> str:
    env = (settings.provider_keys_secret or "").strip()
    if env:
        return env
    db_val = _read_secret_from_db()
    if db_val:
        return db_val.strip()
    raise ProviderKeysSecretMissing(
        "No master key found. Either set PROVIDER_KEYS_SECRET env var or "
        "insert a row into ait_system_config (key='provider_keys_secret')."
    )


@lru_cache(maxsize=1)
def _get_fernet() -> MultiFernet:
    raw = _resolve_secret()
    keys = [k.strip().encode() for k in raw.split(",") if k.strip()]
    fernets = [Fernet(k) for k in keys]
    return MultiFernet(fernets)


def encrypt(plaintext: str) -> bytes:
    if not plaintext:
        raise ValueError("empty plaintext")
    return _get_fernet().encrypt(plaintext.encode("utf-8"))


def decrypt(ciphertext: bytes) -> str:
    try:
        return _get_fernet().decrypt(ciphertext).decode("utf-8")
    except InvalidToken as e:
        raise ProviderKeysDecryptError("invalid token — master key rotated or data corrupted") from e


def last4(plaintext: str) -> str:
    """Last 4 chars of the plaintext, safe for display."""
    if not plaintext:
        return ""
    return plaintext[-4:] if len(plaintext) >= 4 else plaintext


def is_configured() -> bool:
    """Return True if a master key is available (env var OR DB fallback)."""
    if (settings.provider_keys_secret or "").strip():
        return True
    return bool(_read_secret_from_db())


def reset_cache_for_tests() -> None:
    _get_fernet.cache_clear()
