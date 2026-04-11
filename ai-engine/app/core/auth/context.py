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
    project_id: str  # primary project (backward compat)
    credential_type: str  # 'embed' | 'api_key'
    credential_id: str
    scopes: list[str] = field(default_factory=list)
    origin: Optional[str] = None
    ip: Optional[str] = None
    allowed_project_ids: list[str] = field(default_factory=list)  # [project_id] + additional
    max_rpm: int = 30   # requests per minute (from token config)
    max_rpd: int = 5000  # requests per day (from token config)

    def can_access_project(self, pid: str) -> bool:
        return pid in self.allowed_project_ids


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

        primary_pid = row["project_id"]
        additional = row.get("additional_project_ids") or []
        # primary first, then unique additions
        allowed = [primary_pid] + [p for p in additional if p and p != primary_pid]

        return AuthContext(
            tenant_id=row["tenant_id"],
            project_id=primary_pid,
            credential_type="embed",
            credential_id=row["id"],
            scopes=scopes,
            origin=origin,
            ip=request.client.host if request.client else None,
            allowed_project_ids=allowed,
            max_rpm=row.get("max_rpm") or 30,
            max_rpd=row.get("max_rpd") or 5000,
        )

    return _dep


def _ip_allowed(client_ip: str | None, allowed_ips: list[str]) -> bool:
    """Check if client IP matches the allowlist. Empty list = allow all."""
    if not allowed_ips:
        return True
    if not client_ip:
        return False
    return client_ip in allowed_ips


def require_api_key_auth(scope: str):
    """
    FastAPI dependency factory: validates API key and returns AuthContext.

    Token source: X-API-Key header only (server-to-server, no query param).
    Checks IP allowlist instead of origin.
    """
    async def _dep(
        request: Request,
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
        authorization: Optional[str] = Header(default=None),
    ) -> AuthContext:
        # 1. Resolve key
        raw_key = x_api_key
        if not raw_key and authorization and authorization.lower().startswith("bearer "):
            raw_key = authorization.split(" ", 1)[1].strip()

        if not raw_key:
            raise HTTPException(status_code=401, detail="Missing API key")

        # 2. Look up by hash
        from app.core.auth.embed_token import hash_token as _hash
        key_hash = _hash(raw_key)
        row = crud_auth.get_api_key_by_hash(key_hash)
        if not row:
            raise HTTPException(status_code=401, detail="Invalid API key")

        # 3. Check revoked
        if row.get("revoked_at"):
            raise HTTPException(status_code=401, detail="API key revoked")

        # 4. Check expiry
        expires_at = row.get("expires_at")
        if expires_at:
            if isinstance(expires_at, str):
                exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            else:
                exp = expires_at
            if exp < datetime.now(timezone.utc):
                raise HTTPException(status_code=401, detail="API key expired")

        # 5. IP allowlist check (instead of origin check for embed)
        client_ip = request.client.host if request.client else None
        allowed_ips = row.get("allowed_ips") or []
        if not _ip_allowed(client_ip, allowed_ips):
            raise HTTPException(
                status_code=403,
                detail=f"IP not allowed: {client_ip}",
            )

        # 6. Scope check
        scopes = row.get("scopes") or []
        if scope not in scopes:
            raise HTTPException(
                status_code=403,
                detail=f"API key missing required scope: {scope}",
            )

        # 7. Async touch last_used_at
        try:
            asyncio.create_task(
                asyncio.to_thread(crud_auth.touch_api_key, row["id"])
            )
        except Exception:
            pass

        return AuthContext(
            tenant_id=row["tenant_id"],
            project_id=row["project_id"],
            credential_type="api_key",
            credential_id=row["id"],
            scopes=scopes,
            origin=None,
            ip=client_ip,
            allowed_project_ids=[row["project_id"]],
            max_rpm=row.get("max_rpm") or 60,
            max_rpd=row.get("max_rpd") or 20000,
        )

    return _dep
