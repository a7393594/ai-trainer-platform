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
    # Fernet master key for encrypting per-tenant provider API keys at rest.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Comma-separated list supports rotation (first = write key, rest = legacy read keys).
    provider_keys_secret: Optional[str] = None

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

    # Stripe (optional — plan upgrade checkout)
    stripe_secret_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    stripe_price_pro: Optional[str] = None
    stripe_price_enterprise: Optional[str] = None
    billing_success_url: str = "http://localhost:3000/billing/success"
    billing_cancel_url: str = "http://localhost:3000/billing/cancel"

    # CORS — comma-separated list for internal /api/v1 routes
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:3003,https://frontend-gray-three-14.vercel.app"

    # ── DAG Executor 替代 orchestrator 於生產 /chat ──────────────
    # True(預設，2026-04):/chat + /chat/stream 都走 chat_adapter.process_via_dag()
    #   由 DAG Executor 驅動，支援 analyze_intent + 人格混合 + progress SSE 事件
    # False:退回 AgentOrchestrator.process() 舊路徑（無 analyze_intent、無進度事件）
    # 這個預設在 V3 DAG + Prompt Library 成熟後翻成 True；要退回 legacy 請設 env var=false
    use_dag_executor_for_chat: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
