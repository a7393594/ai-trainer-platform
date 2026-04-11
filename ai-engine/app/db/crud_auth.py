"""
CRUD for auth tables: ait_embed_tokens
"""
from datetime import datetime, timezone
from typing import Optional

from app.db.supabase import get_supabase

T_EMBED_TOKENS = "ait_embed_tokens"


def create_embed_token(
    tenant_id: str,
    project_id: str,
    name: str,
    token_hash: str,
    token_prefix: str,
    allowed_origins: Optional[list[str]] = None,
    scopes: Optional[list[str]] = None,
    expires_at: Optional[str] = None,
    created_by: Optional[str] = None,
    additional_project_ids: Optional[list[str]] = None,
) -> dict:
    """Insert a new embed token. Caller must have already generated + hashed."""
    data: dict = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "name": name,
        "token_hash": token_hash,
        "token_prefix": token_prefix,
        "allowed_origins": allowed_origins or [],
        "scopes": scopes or ["chat", "widget"],
        "additional_project_ids": additional_project_ids or [],
    }
    if expires_at:
        data["expires_at"] = expires_at
    if created_by:
        data["created_by"] = created_by

    result = get_supabase().table(T_EMBED_TOKENS).insert(data).execute()
    return result.data[0]


def get_embed_token_by_hash(token_hash: str) -> Optional[dict]:
    """Lookup token by sha256 hash. Returns None if not found or revoked."""
    result = (
        get_supabase()
        .table(T_EMBED_TOKENS)
        .select("*")
        .eq("token_hash", token_hash)
        .is_("revoked_at", "null")
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def list_embed_tokens(
    tenant_id: str,
    project_id: Optional[str] = None,
    include_revoked: bool = False,
) -> list[dict]:
    """List embed tokens for a tenant. Excludes token_hash from response."""
    query = (
        get_supabase()
        .table(T_EMBED_TOKENS)
        .select("id,tenant_id,project_id,additional_project_ids,token_prefix,name,allowed_origins,scopes,expires_at,revoked_at,last_used_at,created_by,created_at")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
    )
    if project_id:
        query = query.eq("project_id", project_id)
    if not include_revoked:
        query = query.is_("revoked_at", "null")
    return query.execute().data


def get_embed_token(token_id: str) -> Optional[dict]:
    """Get a single token by id (metadata only, no hash)."""
    result = (
        get_supabase()
        .table(T_EMBED_TOKENS)
        .select("id,tenant_id,project_id,additional_project_ids,token_prefix,name,allowed_origins,scopes,expires_at,revoked_at,last_used_at,created_by,created_at")
        .eq("id", token_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def revoke_embed_token(token_id: str) -> dict:
    """Soft-delete by setting revoked_at."""
    now = datetime.now(timezone.utc).isoformat()
    result = (
        get_supabase()
        .table(T_EMBED_TOKENS)
        .update({"revoked_at": now})
        .eq("id", token_id)
        .execute()
    )
    return result.data[0] if result.data else {}


def touch_embed_token(token_id: str) -> None:
    """Update last_used_at. Fire-and-forget, no return."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        (
            get_supabase()
            .table(T_EMBED_TOKENS)
            .update({"last_used_at": now})
            .eq("id", token_id)
            .execute()
        )
    except Exception:
        pass


# ============================================
# API Keys (ait_api_keys)
# ============================================

T_API_KEYS = "ait_api_keys"

_API_KEY_SELECT = "id,tenant_id,project_id,key_prefix,name,scopes,allowed_ips,max_rpm,max_rpd,expires_at,revoked_at,last_used_at,created_by,created_at"


def create_api_key(
    tenant_id: str,
    project_id: str,
    name: str,
    key_hash: str,
    key_prefix: str,
    scopes: Optional[list[str]] = None,
    allowed_ips: Optional[list[str]] = None,
    max_rpm: int = 60,
    max_rpd: int = 20000,
    expires_at: Optional[str] = None,
    created_by: Optional[str] = None,
) -> dict:
    data: dict = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "name": name,
        "key_hash": key_hash,
        "key_prefix": key_prefix,
        "scopes": scopes or ["chat:read", "chat:write"],
        "allowed_ips": allowed_ips or [],
        "max_rpm": max_rpm,
        "max_rpd": max_rpd,
    }
    if expires_at:
        data["expires_at"] = expires_at
    if created_by:
        data["created_by"] = created_by
    result = get_supabase().table(T_API_KEYS).insert(data).execute()
    return result.data[0]


def get_api_key_by_hash(key_hash: str) -> Optional[dict]:
    result = (
        get_supabase()
        .table(T_API_KEYS)
        .select("*")
        .eq("key_hash", key_hash)
        .is_("revoked_at", "null")
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def list_api_keys(
    tenant_id: str,
    project_id: Optional[str] = None,
    include_revoked: bool = False,
) -> list[dict]:
    query = (
        get_supabase()
        .table(T_API_KEYS)
        .select(_API_KEY_SELECT)
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
    )
    if project_id:
        query = query.eq("project_id", project_id)
    if not include_revoked:
        query = query.is_("revoked_at", "null")
    return query.execute().data


def get_api_key(key_id: str) -> Optional[dict]:
    result = (
        get_supabase()
        .table(T_API_KEYS)
        .select(_API_KEY_SELECT)
        .eq("id", key_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def revoke_api_key(key_id: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    result = (
        get_supabase()
        .table(T_API_KEYS)
        .update({"revoked_at": now})
        .eq("id", key_id)
        .execute()
    )
    return result.data[0] if result.data else {}


def touch_api_key(key_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    try:
        get_supabase().table(T_API_KEYS).update({"last_used_at": now}).eq("id", key_id).execute()
    except Exception:
        pass
