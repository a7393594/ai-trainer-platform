"""
Supabase 連線管理
"""
from supabase import create_client, Client
from app.config import settings

_client: Client | None = None


def init_supabase() -> Client:
    global _client
    _client = create_client(settings.supabase_url, settings.supabase_service_key)
    print("[OK] Supabase connected")
    return _client


def get_supabase() -> Client:
    if _client is None:
        return init_supabase()
    return _client
