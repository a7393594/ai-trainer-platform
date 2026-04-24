"""API endpoints for managing per-tenant provider API keys.

Mounted at /api/v1/provider-keys. Plaintext keys are accepted on PUT only
and never returned — callers see at most the last 4 chars.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.provider_keys import crypto, service, verifier
from app.db import crud

router = APIRouter()
logger = logging.getLogger(__name__)


class SetKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=1, max_length=500)


def _resolve_tenant(tenant_id: Optional[str], email: Optional[str]) -> str:
    """Resolve tenant_id from explicit param, or look up the demo/auth user by email."""
    if tenant_id:
        return tenant_id
    lookup_email = email or "demo@ai-trainer.dev"
    user = crud.get_user_by_email(lookup_email)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return user["tenant_id"]


def _require_crypto() -> None:
    if not crypto.is_configured():
        raise HTTPException(
            status_code=503,
            detail="PROVIDER_KEYS_SECRET not set on server — ask the admin to configure it",
        )


@router.get("/provider-keys")
async def list_provider_keys(
    tenant_id: Optional[str] = Query(default=None),
    email: Optional[str] = Query(default=None),
):
    """List all 5 provider slots for a tenant (set or not)."""
    tid = _resolve_tenant(tenant_id, email)
    return {"keys": service.list_keys(tid)}


@router.put("/provider-keys/{provider}")
async def set_provider_key(
    provider: str,
    body: SetKeyRequest,
    tenant_id: Optional[str] = Query(default=None),
    email: Optional[str] = Query(default=None),
):
    """Upsert key + auto-verify. Returns the verification result."""
    _require_crypto()
    if provider not in service.ALLOWED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"invalid provider: {provider}")

    tid = _resolve_tenant(tenant_id, email)
    try:
        saved = service.set_key(tid, provider, body.api_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except crypto.ProviderKeysSecretMissing:
        raise HTTPException(status_code=503, detail="crypto not configured")

    # Verify inline so UI gets immediate result
    ok, err, model = await verifier.test_call(provider, body.api_key)
    service.mark_verified(tid, provider, ok=ok, model=model, error=err)

    # Re-read to get canonical row (verified_at, etc.)
    rows = service.list_keys(tid)
    row = next((r for r in rows if r["provider"] == provider), None)
    return {
        "provider": provider,
        "last4": saved["last4"],
        "verified": ok,
        "verified_at": row.get("verified_at") if row else None,
        "last_error": row.get("last_error") if row else err,
        "last_verified_model": row.get("last_verified_model") if row else None,
    }


@router.post("/provider-keys/{provider}/verify")
async def verify_provider_key(
    provider: str,
    tenant_id: Optional[str] = Query(default=None),
    email: Optional[str] = Query(default=None),
):
    """Re-run the verification test against the stored key."""
    _require_crypto()
    if provider not in service.ALLOWED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"invalid provider: {provider}")

    tid = _resolve_tenant(tenant_id, email)
    plaintext = service.get_key(tid, provider)
    if not plaintext:
        raise HTTPException(status_code=404, detail="no key stored for this provider")

    ok, err, model = await verifier.test_call(provider, plaintext)
    service.mark_verified(tid, provider, ok=ok, model=model, error=err)
    return {
        "provider": provider,
        "verified": ok,
        "last_error": err,
        "last_verified_model": model if ok else None,
    }


@router.delete("/provider-keys/{provider}")
async def delete_provider_key(
    provider: str,
    tenant_id: Optional[str] = Query(default=None),
    email: Optional[str] = Query(default=None),
):
    if provider not in service.ALLOWED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"invalid provider: {provider}")
    tid = _resolve_tenant(tenant_id, email)
    service.delete_key(tid, provider)
    return {"deleted": True, "provider": provider}
