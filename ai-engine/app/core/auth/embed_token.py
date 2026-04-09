"""
Embed Token generation & hashing

Token format: et_live_<32-char random>
Storage: sha256(token) in ait_embed_tokens.token_hash
Display: first 12 chars used as token_prefix for UI
"""
import hashlib
import secrets


TOKEN_PREFIX = "et_live_"
TOKEN_RANDOM_LEN = 32


def generate_token() -> tuple[str, str, str]:
    """
    Generate a new embed token.

    Returns:
        (plain_token, token_hash, display_prefix)
        - plain_token: full token to return to user ONCE
        - token_hash: sha256 to store in DB
        - display_prefix: first 12 chars for UI (e.g. "et_live_a3c9")
    """
    random_part = secrets.token_urlsafe(TOKEN_RANDOM_LEN)[:TOKEN_RANDOM_LEN]
    plain = f"{TOKEN_PREFIX}{random_part}"
    token_hash = hash_token(plain)
    display_prefix = plain[:12] + "..."
    return plain, token_hash, display_prefix


def hash_token(plain_token: str) -> str:
    """SHA256 hash a token string."""
    return hashlib.sha256(plain_token.encode("utf-8")).hexdigest()
