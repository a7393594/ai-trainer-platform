"""
AI Trainer Platform — AI 引擎入口
"""
import json
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.v1 import router as api_v1_router
from app.api.v1.embed import router as embed_router
from app.api.v1.management import router as management_router
from app.api.v1.pipeline import router as pipeline_router
from app.api.v1.lab import router as lab_router
from app.api.v1.public import router as public_router
from app.api.v1.referee import router as referee_router
from app.api.v1.poker_coach import router as poker_coach_router
from app.api.v1.provider_keys import router as provider_keys_router
from app.core.tenant_context import set_current_tenant, reset_current_tenant
from app.core.llm_router.router import NoProviderKeyError
from app.db.supabase import init_supabase
from app.db.qdrant import init_qdrant
from app.core.llm_router.router import init_llm_router

_log = logging.getLogger(__name__)

app = FastAPI(
    title="AI Trainer Engine",
    description="AI Agent 訓練平台的核心引擎",
    version="0.2.0",
)

# CORS — split internal vs public
# MVP: keep wide open for now; Phase 2 will tighten /api/v1 to dashboard origins only
_allowed_origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]
# For MVP, also allow wildcard (embed endpoints need it)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Add security headers; /embed/* allows iframe embedding."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/embed"):
        # Allow iframe embedding from any origin for embed routes
        response.headers["Content-Security-Policy"] = "frame-ancestors *"
    else:
        # Protect dashboard / internal routes from clickjacking
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return response


@app.middleware("http")
async def tenant_resolver(request: Request, call_next):
    """Resolve tenant_id from request, store in contextvar.

    Resolution order:
      1. X-Tenant-ID header
      2. tenant_id query param
      3. POST body's tenant_id field
      4. POST body's project_id → ait_projects.tenant_id lookup
      5. None (Anthropic env-only flow still works)

    The contextvar is read by app.core.provider_keys.resolver.resolve_api_key
    when callers don't pass an explicit tenant_id, fixing the entire class of
    "OPENAI_API_KEY missing" errors that arise when 41+ chat_completion call
    sites forget to thread tenant_id through.
    """
    tenant_id = None
    try:
        # 1. Header (服務間呼叫 / debug)
        tenant_id = request.headers.get("x-tenant-id")

        # 2. Query param
        if not tenant_id:
            tenant_id = request.query_params.get("tenant_id")

        # Streaming SSE endpoints CANNOT use body sniffing + receive replay —
        # BaseHTTPMiddleware crashes Starlette's disconnect detection during
        # the long-running response with `Unexpected message received: http.request`.
        # Those endpoints (chat_adapter etc.) lookup tenant_id from project_id
        # themselves, so it's safe to skip middleware-level resolution here.
        _path = request.url.path
        _is_streaming = _path.endswith("/chat/stream") or _path.startswith("/embed/")

        # 3+4. Sniff POST body for tenant_id / project_id (only for JSON bodies)
        if not tenant_id and not _is_streaming and request.method in ("POST", "PUT", "PATCH"):
            ctype = request.headers.get("content-type", "")
            if "application/json" in ctype:
                body_bytes = await request.body()
                if body_bytes:
                    try:
                        data = json.loads(body_bytes)
                        if isinstance(data, dict):
                            tenant_id = data.get("tenant_id")
                            if not tenant_id and data.get("project_id"):
                                from app.db import crud as _crud
                                proj = _crud.get_project(data["project_id"])
                                if proj:
                                    tenant_id = proj.get("tenant_id")
                    except (ValueError, TypeError):
                        pass
                # IMPORTANT: restore the body so the endpoint can read it again.
                # Must only replay body ONCE; subsequent receive() calls (used by
                # Starlette to detect client disconnect during streaming response)
                # must fall through to the real receive — otherwise SSE endpoints
                # crash with `Unexpected message received: http.request`.
                _original_receive = request._receive  # type: ignore[attr-defined]
                _replayed = False
                async def receive():
                    nonlocal _replayed
                    if not _replayed:
                        _replayed = True
                        return {"type": "http.request", "body": body_bytes, "more_body": False}
                    return await _original_receive()
                request._receive = receive  # type: ignore[attr-defined]
    except Exception as e:
        _log.warning("tenant_resolver failed: %s", e)

    token = set_current_tenant(tenant_id)
    try:
        return await call_next(request)
    finally:
        reset_current_tenant(token)


@app.on_event("startup")
async def startup():
    """啟動時初始化所有連線"""
    init_supabase()
    try:
        init_qdrant()
    except Exception as e:
        print(f"[WARN] Qdrant not available (Phase 2): {e}")
    init_llm_router()
    print(f"[OK] AI Engine started in {settings.environment} mode")


@app.exception_handler(NoProviderKeyError)
async def no_provider_key_handler(request: Request, exc: NoProviderKeyError):
    """Translate "LLM provider has no key" into a friendly 400 the frontend can act on."""
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=400,
        content={
            "error": "no_provider_key",
            "provider": exc.provider,
            "model": exc.model,
            "message": f"請到設定頁 → Provider API Keys → {exc.provider} 配置 API key",
            "settings_url": "/settings?tab=providers",
            "detail": exc.original[:300],
        },
    )


@app.get("/health")
async def health_check():
    return {"status": "ok", "environment": settings.environment}


# 掛載 API 路由
app.include_router(api_v1_router, prefix="/api/v1")
app.include_router(management_router, prefix="/api/v1", tags=["management"])
app.include_router(pipeline_router, prefix="/api/v1")
app.include_router(lab_router, prefix="/api/v1")
app.include_router(referee_router, prefix="/api/v1")
app.include_router(poker_coach_router, prefix="/api/v1")
app.include_router(provider_keys_router, prefix="/api/v1", tags=["provider-keys"])
app.include_router(embed_router, prefix="/embed", tags=["embed"])
app.include_router(public_router, prefix="/public/v1", tags=["public-api"])
