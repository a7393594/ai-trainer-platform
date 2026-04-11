"""
Management API — dashboard-only endpoints for managing embed tokens / API keys.

Note: In MVP these endpoints are NOT yet protected by dashboard auth.
They use the tenant inferred from a passed-in project_id (assumed via demo context).
Phase 2+ will add proper Supabase JWT auth.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.auth.embed_token import generate_token
from app.core.auth.api_key import generate_api_key
from app.db import crud, crud_auth, crud_usage

router = APIRouter()


class CreateEmbedTokenRequest(BaseModel):
    project_id: str
    name: str = Field(..., min_length=1, max_length=100)
    allowed_origins: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=lambda: ["chat", "widget"])
    expires_at: Optional[str] = None  # ISO format
    additional_project_ids: list[str] = Field(default_factory=list)


class CreateEmbedTokenResponse(BaseModel):
    id: str
    token: str  # Plain token — shown ONCE
    token_prefix: str
    name: str
    project_id: str
    additional_project_ids: list[str]
    allowed_origins: list[str]
    scopes: list[str]
    created_at: str
    warning: str = "Save this token now — it will not be shown again."


@router.post("/embed-tokens", response_model=CreateEmbedTokenResponse)
async def create_embed_token(req: CreateEmbedTokenRequest):
    """Create a new embed token. Returns plaintext token ONCE."""
    # Look up primary project to get tenant_id
    project = crud.get_project(req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    tenant_id = project["tenant_id"]

    # Validate additional projects all belong to the same tenant
    clean_additional: list[str] = []
    for pid in req.additional_project_ids:
        if pid == req.project_id:
            continue  # dedupe primary
        p = crud.get_project(pid)
        if not p:
            raise HTTPException(status_code=404, detail=f"Additional project {pid} not found")
        if p["tenant_id"] != tenant_id:
            raise HTTPException(
                status_code=403,
                detail=f"Project {pid} belongs to a different tenant",
            )
        clean_additional.append(pid)

    # Generate + hash
    plain_token, token_hash, display_prefix = generate_token()

    # Insert
    row = crud_auth.create_embed_token(
        tenant_id=tenant_id,
        project_id=req.project_id,
        name=req.name,
        token_hash=token_hash,
        token_prefix=display_prefix,
        allowed_origins=req.allowed_origins,
        scopes=req.scopes,
        expires_at=req.expires_at,
        additional_project_ids=clean_additional,
    )

    return CreateEmbedTokenResponse(
        id=row["id"],
        token=plain_token,
        token_prefix=display_prefix,
        name=row["name"],
        project_id=row["project_id"],
        additional_project_ids=row.get("additional_project_ids") or [],
        allowed_origins=row.get("allowed_origins") or [],
        scopes=row.get("scopes") or [],
        created_at=row["created_at"],
    )


@router.get("/embed-tokens")
async def list_embed_tokens(
    project_id: Optional[str] = None,
    include_revoked: bool = False,
):
    """List embed tokens. If project_id given, filter by it."""
    if project_id:
        project = crud.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        tenant_id = project["tenant_id"]
    else:
        # MVP: fall back to demo tenant
        demo = crud.get_user_by_email("demo@ai-trainer.dev")
        if not demo:
            raise HTTPException(status_code=404, detail="No tenant context")
        tenant_id = demo["tenant_id"]

    tokens = crud_auth.list_embed_tokens(
        tenant_id=tenant_id,
        project_id=project_id,
        include_revoked=include_revoked,
    )
    return {"tokens": tokens}


@router.delete("/embed-tokens/{token_id}")
async def revoke_embed_token(token_id: str):
    """Revoke (soft-delete) an embed token."""
    existing = crud_auth.get_embed_token(token_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Token not found")
    if existing.get("revoked_at"):
        raise HTTPException(status_code=400, detail="Token already revoked")

    crud_auth.revoke_embed_token(token_id)
    return {"status": "revoked", "id": token_id}


@router.get("/embed-tokens/{token_id}/usage")
async def get_embed_token_usage(
    token_id: str,
    days: int = 7,
):
    """Get usage stats for an embed token over the last N days."""
    token = crud_auth.get_embed_token(token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    summary = crud_usage.get_usage_summary(token_id, days=days)
    by_day = crud_usage.get_usage_by_day(token_id, days=days)
    return {
        "token_id": token_id,
        "days": days,
        **summary,
        "by_day": by_day,
    }


@router.get("/tenant-projects")
async def list_tenant_projects(tenant_id: Optional[str] = None):
    """List all projects for a tenant. Used by dashboard Integrations page
    to populate the multi-project picker when creating an embed token.

    MVP: if tenant_id is not provided, fall back to demo tenant.
    """
    if not tenant_id:
        demo = crud.get_user_by_email("demo@ai-trainer.dev")
        if not demo:
            raise HTTPException(status_code=404, detail="No tenant context")
        tenant_id = demo["tenant_id"]

    projects = crud.list_projects(tenant_id)
    return {
        "tenant_id": tenant_id,
        "projects": [
            {
                "id": p["id"],
                "name": p.get("name"),
                "description": p.get("description"),
            }
            for p in projects
        ],
    }


# ============================================
# API Keys CRUD
# ============================================


class CreateApiKeyRequest(BaseModel):
    project_id: str
    name: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = Field(default_factory=lambda: ["chat:read", "chat:write"])
    allowed_ips: list[str] = Field(default_factory=list)
    max_rpm: int = 60
    max_rpd: int = 20000
    expires_at: Optional[str] = None


class CreateApiKeyResponse(BaseModel):
    id: str
    key: str  # Plain key — shown ONCE
    key_prefix: str
    name: str
    project_id: str
    scopes: list[str]
    allowed_ips: list[str]
    created_at: str
    warning: str = "Save this API key now — it will not be shown again."


@router.post("/api-keys", response_model=CreateApiKeyResponse)
async def create_api_key_endpoint(req: CreateApiKeyRequest):
    """Create a new API key. Returns plaintext key ONCE."""
    project = crud.get_project(req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    plain_key, key_hash, display_prefix = generate_api_key()

    row = crud_auth.create_api_key(
        tenant_id=project["tenant_id"],
        project_id=req.project_id,
        name=req.name,
        key_hash=key_hash,
        key_prefix=display_prefix,
        scopes=req.scopes,
        allowed_ips=req.allowed_ips,
        max_rpm=req.max_rpm,
        max_rpd=req.max_rpd,
        expires_at=req.expires_at,
    )

    return CreateApiKeyResponse(
        id=row["id"],
        key=plain_key,
        key_prefix=display_prefix,
        name=row["name"],
        project_id=row["project_id"],
        scopes=row.get("scopes") or [],
        allowed_ips=row.get("allowed_ips") or [],
        created_at=row["created_at"],
    )


@router.get("/api-keys")
async def list_api_keys_endpoint(
    project_id: Optional[str] = None,
    include_revoked: bool = False,
):
    """List API keys."""
    if project_id:
        project = crud.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        tenant_id = project["tenant_id"]
    else:
        demo = crud.get_user_by_email("demo@ai-trainer.dev")
        if not demo:
            raise HTTPException(status_code=404, detail="No tenant context")
        tenant_id = demo["tenant_id"]

    keys = crud_auth.list_api_keys(
        tenant_id=tenant_id,
        project_id=project_id,
        include_revoked=include_revoked,
    )
    return {"keys": keys}


@router.delete("/api-keys/{key_id}")
async def revoke_api_key_endpoint(key_id: str):
    """Revoke an API key."""
    existing = crud_auth.get_api_key(key_id)
    if not existing:
        raise HTTPException(status_code=404, detail="API key not found")
    if existing.get("revoked_at"):
        raise HTTPException(status_code=400, detail="API key already revoked")

    crud_auth.revoke_api_key(key_id)
    return {"status": "revoked", "id": key_id}


@router.get("/api-keys/{key_id}/usage")
async def get_api_key_usage(key_id: str, days: int = 7):
    """Get usage stats for an API key."""
    key = crud_auth.get_api_key(key_id)
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")

    summary = crud_usage.get_usage_summary(key_id, days=days)
    by_day = crud_usage.get_usage_by_day(key_id, days=days)
    return {"key_id": key_id, "days": days, **summary, "by_day": by_day}
