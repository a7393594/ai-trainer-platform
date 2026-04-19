"""
Qdrant 向量資料庫連線與適配層

用 feature flag (`settings.vector_backend`) 切換：
  - "pgvector" (預設) → 使用 Supabase RPC `ait_search_knowledge`
  - "qdrant"          → 使用 Qdrant HTTP client

Collection 命名：`ait_kb_{project_id}` — 每專案獨立 collection。
"""
from __future__ import annotations

from typing import Optional

_client = None
_available = False


def init_qdrant() -> None:
    """嘗試連線；失敗時不拋例外，只標記不可用（由 RAG pipeline 自動 fallback）。"""
    global _client, _available
    try:
        from qdrant_client import QdrantClient  # lazy
        from app.config import settings

        _client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
        # 對 client 做一個輕量 ping
        _client.get_collections()
        _available = True
        print("[OK] Qdrant connected")
    except ImportError:
        print("[INFO] qdrant-client not installed")
        _available = False
    except Exception as e:
        print(f"[WARN] Qdrant connection failed: {e}")
        _available = False


def get_qdrant():
    if _client is None:
        raise RuntimeError("Qdrant not initialized")
    return _client


def is_qdrant_available() -> bool:
    return _available


# --------------------------------------------
# 高階操作（給 RAG pipeline 呼叫）
# --------------------------------------------

def _collection_name(project_id: str) -> str:
    safe = str(project_id).replace("-", "").lower()
    return f"ait_kb_{safe}"


def ensure_collection(project_id: str, vector_size: int = 1536) -> None:
    """建立 collection（若不存在）。由 RAG 第一次寫入前呼叫。"""
    if not _available:
        return
    try:
        from qdrant_client.models import Distance, VectorParams  # lazy
        client = get_qdrant()
        name = _collection_name(project_id)
        existing = {c.name for c in client.get_collections().collections}
        if name not in existing:
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
    except Exception as e:
        print(f"[WARN] ensure_collection failed: {e}")


def upsert_chunk(
    project_id: str,
    point_id: str,
    embedding: list[float],
    payload: dict,
) -> bool:
    if not _available:
        return False
    try:
        from qdrant_client.models import PointStruct  # lazy
        client = get_qdrant()
        client.upsert(
            collection_name=_collection_name(project_id),
            points=[PointStruct(id=point_id, vector=embedding, payload=payload)],
        )
        return True
    except Exception as e:
        print(f"[WARN] qdrant upsert failed: {e}")
        return False


def search(project_id: str, embedding: list[float], limit: int = 5) -> list[dict]:
    if not _available:
        return []
    try:
        client = get_qdrant()
        hits = client.search(
            collection_name=_collection_name(project_id),
            query_vector=embedding,
            limit=limit,
        )
        return [
            {
                "content": (h.payload or {}).get("content", ""),
                "similarity": float(h.score or 0.0),
                "meta": h.payload or {},
            }
            for h in hits
        ]
    except Exception as e:
        print(f"[WARN] qdrant search failed: {e}")
        return []
