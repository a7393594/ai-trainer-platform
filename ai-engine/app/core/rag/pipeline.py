"""
RAG Pipeline -- Knowledge upload, chunking, and search
Uses Supabase pgvector for vector search with keyword fallback
"""
from typing import Optional
from app.db import crud
from app.db.supabase import get_supabase


class RAGPipeline:

    def chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
        """Split text into overlapping chunks"""
        if len(text) <= chunk_size:
            return [text]
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk.strip())
            start = end - overlap
        return chunks

    async def upload_document(
        self, project_id: str, title: str, content: str, source_type: str = "upload"
    ) -> dict:
        """Upload document: save, chunk, store"""
        # 1. Save doc record
        doc = crud.create_knowledge_doc(project_id, title, source_type, content)

        # 2. Chunk content
        chunks = self.chunk_text(content)

        # 3. Save chunks
        for i, chunk_text in enumerate(chunks):
            crud.create_knowledge_chunk(
                doc_id=doc["id"],
                content=chunk_text,
                chunk_index=i,
                qdrant_point_id=f"{doc['id']}_{i}",
            )

        # 4. Try to create embeddings (requires OpenAI key)
        try:
            await self._create_embeddings(project_id, doc["id"], chunks)
        except Exception:
            pass  # Embeddings optional, keyword search fallback

        # 5. Update doc status
        crud.update_doc_status(doc["id"], "ready", len(chunks))
        doc["status"] = "ready"
        doc["chunk_count"] = len(chunks)
        return doc

    async def search(self, project_id: str, query: str, top_k: int = 5) -> list[dict]:
        """Search knowledge base — vector search with keyword fallback"""
        # Try vector search first
        try:
            results = await self._vector_search(project_id, query, top_k)
            if results:
                return results
        except Exception:
            pass

        # Keyword fallback
        return crud.search_knowledge_chunks(project_id, query, limit=top_k)

    async def _create_embeddings(self, project_id: str, doc_id: str, chunks: list[str]):
        """Create embeddings for chunks using LiteLLM"""
        import litellm
        for i, chunk in enumerate(chunks):
            response = await litellm.aembedding(
                model="text-embedding-3-small",
                input=[chunk],
            )
            embedding = response.data[0]["embedding"]

            # Get chunk record
            db = get_supabase()
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

    async def _vector_search(self, project_id: str, query: str, top_k: int) -> list[dict]:
        """Vector similarity search using pgvector"""
        import litellm
        response = await litellm.aembedding(
            model="text-embedding-3-small",
            input=[query],
        )
        query_embedding = response.data[0]["embedding"]

        db = get_supabase()
        result = db.rpc("ait_search_knowledge", {
            "p_project_id": project_id,
            "p_query_embedding": query_embedding,
            "p_limit": top_k,
        }).execute()

        return [{"content": r["content"], "similarity": r["similarity"]} for r in result.data]


rag_pipeline = RAGPipeline()
