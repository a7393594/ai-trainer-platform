"""
應用程式設定 — 從環境變數讀取所有設定
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_service_key: str

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None
    # Vector backend: "pgvector" (Supabase) or "qdrant"
    vector_backend: str = "pgvector"

    # LLM API Keys
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None

    # Embedding
    embedding_model: str = "text-embedding-3-small"
    embedding_provider: str = "openai"

    # 加密
    encryption_key: str = ""

    # LangFuse
    langfuse_public_key: Optional[str] = None
    langfuse_secret_key: Optional[str] = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # 環境
    environment: str = "development"
    log_level: str = "debug"

    # ── Poker Referee AI 設定 ──────────────────
    referee_primary_model: str = "claude-opus-4-6"
    referee_backup_model: str = "gpt-5.4"
    referee_triage_model: str = "claude-haiku-4-5-20251001"
    referee_auto_decide_threshold: float = 0.85
    referee_human_confirm_threshold: float = 0.60
    referee_enable_dual_model: bool = True
    referee_enable_triple_model: bool = False
    referee_voting_temperature: float = 0.3
    referee_consistency_samples: int = 3

    # CORS — comma-separated list for internal /api/v1 routes
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:3003,https://frontend-gray-three-14.vercel.app"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
