"""
API Key generation for server-to-server integrations.
Prefix: sk_live_
Reuses hash_token from embed_token.py.
"""
import secrets
from app.core.auth.embed_token import hash_token

SK_PREFIX = "sk_live_"
SK_RANDOM_LEN = 32


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.
    Returns: (plain_key, key_hash, display_prefix)
    """
    random_part = secrets.token_urlsafe(SK_RANDOM_LEN)[:SK_RANDOM_LEN]
    plain = f"{SK_PREFIX}{random_part}"
    key_hash = hash_token(plain)
    display_prefix = plain[:12] + "..."
    return plain, key_hash, display_prefix
