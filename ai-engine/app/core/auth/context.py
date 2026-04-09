"""
Auth Context + FastAPI dependencies for embed/API authentication
"""
import asyncio
import fnmatch
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import Header, HTTPException, Query, Request

from app.core.auth.embed_token import hash_token
from app.db import crud_auth


@dataclass
class AuthContext:
    tenant_id: str
    project_id: str
    credential_type: str  # 'embed' | 'api_key'
    credential_id: str
    scopes: list[str] = field(default_factory=list)
    origin: Optional[str] = None
    ip: Optional[str] = None


def _origin_host(origin: str) -> Optional[str]:
    """Extract host from an origin or referer URL."""
    if not origin:
        return None
    try:
        parsed = urlparse(origin)
        return parsed.hostname
    except Exception:
        return None


def _origin_allowed(origin: Optional[str], allowed_origins: list[str]) -> bool:
    """
    Check if origin matches allowlist.
    - Empty list = allow all (MVP only — tighten in Phase 2)
    - Supports wildcards like "*.example.com"
    """
    if not allowed_origins:
        return True  # MVP: no restriction
    if not origin:
        return False

    host = _origin_host(origin)
    if not host:
        return False

    for allowed in allowed_origins:
        allowed = allowed.strip().lower()
        if not allowed:
            continue
        # support full origin or just domain
        allowed_host = _origin_host(allowed) or allowed
        if fnmatch.fnmatch(host, allowed_host):
            return True
    return False


def require_embed_auth(scope: str):
    """
    FastAPI dependency factory: validates embed token and returns AuthContext.

    Token sources (in priority order):
    1. X-Embed-Token header
    2. Authorization: Bearer <token>
    3. ?token= query param (used by iframe src URL)

    Args:
        scope: required scope for this endpoint (e.g. "chat", "widget")
    """
    async def _dep(
        request: Request,
        x_embed_token: Optional[str] = Header(default=None, alias="X-Embed-Token"),
        authorization: Optional[str] = Header(default=None),
        token: Optional[str] = Query(default=None),
    ) -> AuthContext:
        # 1. Resolve token
        raw_token = x_embed_token
        if not raw_token and authorization and authorization.lower().startswith("bearer "):
            raw_token = authorization.split(" ", 1)[1].strip()
        if not raw_token:
            raw_token = token

        if not raw_token:
            raise HTTPException(status_code=401, detail="Missing embed token")

        # 2. Look up by hash
        token_hash = hash_token(raw_token)
        row = crud_auth.get_embed_token_by_hash(token_hash)
        if not row:
            raise HTTPException(status_code=401, detail="Invalid embed token")

        # 3. Check revoked
        if row.get("revoked_at"):
            raise HTTPException(status_code=401, detail="Token revoked")

        # 4. Check expiry
        expires_at = row.get("expires_at")
        if expires_at:
            if isinstance(expires_at, str):
                exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            else:
                exp = expires_at
            if exp < datetime.now(timezone.utc):
                raise HTTPException(status_code=401, detail="Token expired")

        # 5. Origin check
        origin = request.headers.get("origin") or request.headers.get("referer")
        allowed = row.get("allowed_origins") or []
        if not _origin_allowed(origin, allowed):
            raise HTTPException(
                status_code=403,
                detail=f"Origin not allowed: {origin}",
            )

        # 6. Scope check
        scopes = row.get("scopes") or []
        if scope not in scopes:
            raise HTTPException(
                status_code=403,
                detail=f"Token missing required scope: {scope}",
            )

        # 7. Async touch last_used_at (fire-and-forget)
        try:
            asyncio.create_task(
                asyncio.to_thread(crud_auth.touch_embed_token, row["id"])
            )
        except Exception:
            pass

        return AuthContext(
            tenant_id=row["tenant_id"],
            project_id=row["project_id"],
            credential_type="embed",
            credential_id=row["id"],
            scopes=scopes,
            origin=origin,
            ip=request.client.host if request.client else None,
        )

    return _dep
