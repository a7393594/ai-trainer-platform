"""
AI Trainer Platform — AI 引擎入口
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.v1 import router as api_v1_router
from app.api.v1.embed import router as embed_router
from app.api.v1.management import router as management_router
from app.api.v1.pipeline import router as pipeline_router
from app.api.v1.public import router as public_router
from app.api.v1.referee import router as referee_router
from app.db.supabase import init_supabase
from app.db.qdrant import init_qdrant
from app.core.llm_router.router import init_llm_router

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


@app.get("/health")
async def health_check():
    return {"status": "ok", "environment": settings.environment}


# 掛載 API 路由
app.include_router(api_v1_router, prefix="/api/v1")
app.include_router(management_router, prefix="/api/v1", tags=["management"])
app.include_router(pipeline_router, prefix="/api/v1")
app.include_router(referee_router, prefix="/api/v1")
app.include_router(embed_router, prefix="/embed", tags=["embed"])
app.include_router(public_router, prefix="/public/v1", tags=["public-api"])
