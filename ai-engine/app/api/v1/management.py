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
from app.db import crud, crud_auth

router = APIRouter()


class CreateEmbedTokenRequest(BaseModel):
    project_id: str
    name: str = Field(..., min_length=1, max_length=100)
    allowed_origins: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=lambda: ["chat", "widget"])
    expires_at: Optional[str] = None  # ISO format


class CreateEmbedTokenResponse(BaseModel):
    id: str
    token: str  # Plain token — shown ONCE
    token_prefix: str
    name: str
    project_id: str
    allowed_origins: list[str]
    scopes: list[str]
    created_at: str
    warning: str = "Save this token now — it will not be shown again."


@router.post("/embed-tokens", response_model=CreateEmbedTokenResponse)
async def create_embed_token(req: CreateEmbedTokenRequest):
    """Create a new embed token. Returns plaintext token ONCE."""
    # Look up project to get tenant_id
    project = crud.get_project(req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Generate + hash
    plain_token, token_hash, display_prefix = generate_token()

    # Insert
    row = crud_auth.create_embed_token(
        tenant_id=project["tenant_id"],
        project_id=req.project_id,
        name=req.name,
        token_hash=token_hash,
        token_prefix=display_prefix,
        allowed_origins=req.allowed_origins,
        scopes=req.scopes,
        expires_at=req.expires_at,
    )

    return CreateEmbedTokenResponse(
        id=row["id"],
        token=plain_token,
        token_prefix=display_prefix,
        name=row["name"],
        project_id=row["project_id"],
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
