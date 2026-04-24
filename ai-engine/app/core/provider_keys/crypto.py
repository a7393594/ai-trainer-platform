"""Fernet-based symmetric encryption for provider API keys stored at rest.

The master key comes from env var ``PROVIDER_KEYS_SECRET``. To rotate, set the
value to a comma-separated list where the first entry is the new write key and
the remaining entries are legacy read keys — existing ciphertexts written with
the older keys stay readable until next write re-encrypts them with the new one.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, MultiFernet, InvalidToken

from app.config import settings


class ProviderKeysSecretMissing(RuntimeError):
    pass


class ProviderKeysDecryptError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _get_fernet() -> MultiFernet:
    raw = (settings.provider_keys_secret or "").strip()
    if not raw:
        raise ProviderKeysSecretMissing(
            "PROVIDER_KEYS_SECRET env var is not set. "
            "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
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
    """Return True if PROVIDER_KEYS_SECRET is set — callers use this to gate features."""
    return bool((settings.provider_keys_secret or "").strip())


def reset_cache_for_tests() -> None:
    _get_fernet.cache_clear()
