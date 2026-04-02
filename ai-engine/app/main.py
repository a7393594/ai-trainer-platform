"""
AI Trainer Platform — AI 引擎入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.v1 import router as api_v1_router
from app.db.supabase import init_supabase
from app.db.qdrant import init_qdrant
from app.core.llm_router.router import init_llm_router

app = FastAPI(
    title="AI Trainer Engine",
    description="AI Agent 訓練平台的核心引擎",
    version="0.1.0",
)

# CORS — 允許前端存取
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
