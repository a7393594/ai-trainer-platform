"""
Qdrant 向量資料庫連線管理（Phase 2）
"""

_client = None


def init_qdrant():
    try:
        from qdrant_client import QdrantClient
        from app.config import settings
        global _client
        _client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )
        print("Qdrant connected")
    except ImportError:
        print("qdrant-client not installed (Phase 2)")
    except Exception as e:
        print(f"Qdrant connection failed: {e}")


def get_qdrant():
    if _client is None:
        raise RuntimeError("Qdrant not initialized (Phase 2)")
    return _client
