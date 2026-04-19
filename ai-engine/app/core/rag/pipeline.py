"""
RAG Pipeline — 文件切塊、embedding 入庫、向量搜尋

後端抽象：
  - pgvector  : Supabase `ait_knowledge_embeddings` + RPC `ait_search_knowledge`
  - qdrant    : 每專案獨立 collection `ait_kb_{project_id}`

由 `settings.vector_backend` 控制：
  - 寫入：雙寫（pgvector 為主，Qdrant 可用時同步寫入）
  - 查詢：依 backend 選擇，主要後端失敗時 fallback 到另一個，最後 fallback 到 keyword
"""
from __future__ import annotations

from typing import Optional

from app.config import settings
from app.db import crud, qdrant as qdrant_db
from app.db.supabase import get_supabase


class RAGPipeline:

    # --------------------------
    # 切塊
    # --------------------------

    def chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
        if len(text) <= chunk_size:
            return [text]
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk.strip())
            start = end - overlap
        return chunks

    # --------------------------
    # 上傳
    # --------------------------

    async def upload_document(
        self, project_id: str, title: str, content: str, source_type: str = "upload"
    ) -> dict:
        doc = crud.create_knowledge_doc(project_id, title, source_type, content)
        chunks = self.chunk_text(content)

        for i, chunk_text in enumerate(chunks):
            crud.create_knowledge_chunk(
                doc_id=doc["id"],
                content=chunk_text,
                chunk_index=i,
                qdrant_point_id=f"{doc['id']}_{i}",
            )

        try:
            await self._create_embeddings(project_id, doc["id"], chunks)
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] embedding creation failed: {e}")

        crud.update_doc_status(doc["id"], "ready", len(chunks))
        doc["status"] = "ready"
        doc["chunk_count"] = len(chunks)
        return doc

    # --------------------------
    # 搜尋（依 backend 分派，失敗 fallback）
    # --------------------------

    async def search(self, project_id: str, query: str, top_k: int = 5) -> list[dict]:
        backend = (settings.vector_backend or "pgvector").lower()

        # 先走主要 backend
        if backend == "qdrant" and qdrant_db.is_qdrant_available():
            results = await self._qdrant_search(project_id, query, top_k)
            if results:
                return results

        # pgvector（或 qdrant 失敗後的 fallback）
        try:
            results = await self._pgvector_search(project_id, query, top_k)
            if results:
                return results
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] pgvector search failed: {e}")

        # 最終 fallback：keyword search
        return crud.search_knowledge_chunks(project_id, query, limit=top_k)

    # --------------------------
    # Embedding 寫入（雙寫）
    # --------------------------

    async def _create_embeddings(self, project_id: str, doc_id: str, chunks: list[str]) -> None:
        import litellm  # lazy

        use_qdrant = qdrant_db.is_qdrant_available()
        if use_qdrant:
            qdrant_db.ensure_collection(project_id)

        db = get_supabase()
        for i, chunk in enumerate(chunks):
            resp = await litellm.aembedding(model=settings.embedding_model, input=[chunk])
            embedding = resp.data[0]["embedding"]

            # 1) pgvector
            try:
                chunk_records = (
                    db.table("ait_knowledge_chunks")
                    .select("id")
                    .eq("doc_id", doc_id)
                    .eq("chunk_index", i)
                    .execute()
                )
                if chunk_records.data:
                    chunk_id = chunk_records.data[0]["id"]
                    db.table("ait_knowledge_embeddings").insert({
                        "chunk_id": chunk_id,
                        "project_id": project_id,
                        "content": chunk,
                        "embedding": embedding,
                    }).execute()
            except Exception as e:  # noqa: BLE001
                print(f"[WARN] pgvector insert failed: {e}")

            # 2) Qdrant（若啟用且可用）
            if use_qdrant:
                qdrant_db.upsert_chunk(
                    project_id=project_id,
                    point_id=f"{doc_id}_{i}",
                    embedding=embedding,
                    payload={"content": chunk, "doc_id": doc_id, "chunk_index": i},
                )

    # --------------------------
    # 後端搜尋實作
    # --------------------------

    async def _pgvector_search(self, project_id: str, query: str, top_k: int) -> list[dict]:
        import litellm  # lazy

        resp = await litellm.aembedding(model=settings.embedding_model, input=[query])
        query_embedding = resp.data[0]["embedding"]
        db = get_supabase()
        result = db.rpc(
            "ait_search_knowledge",
            {"p_project_id": project_id, "p_query_embedding": query_embedding, "p_limit": top_k},
        ).execute()
        return [{"content": r["content"], "similarity": r["similarity"]} for r in result.data]

    async def _qdrant_search(self, project_id: str, query: str, top_k: int) -> list[dict]:
        import litellm  # lazy

        resp = await litellm.aembedding(model=settings.embedding_model, input=[query])
        query_embedding = resp.data[0]["embedding"]
        return qdrant_db.search(project_id, query_embedding, limit=top_k)


rag_pipeline = RAGPipeline()
