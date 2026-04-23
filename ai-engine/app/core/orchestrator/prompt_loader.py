"""Active prompt（含 A/B 變體）+ RAG 搜尋。

從 agent.py 抽出成獨立模組，DAG 的 compose_prompt / load_knowledge 節點
直接呼叫這裡，保證與 orchestrator 的行為一致。
"""
from typing import Optional

from app.db import crud


async def load_active_prompt(
    project_id: str,
    session_id: Optional[str] = None,
    prompt_override: Optional[str] = None,
) -> Optional[str]:
    """載入專案目前使用的系統提示詞。

    優先序：
      1) prompt_override（Lab 實驗用 — 最高優先）
      2) A/B test 變體
      3) 專案 active prompt
    """
    if prompt_override:
        return prompt_override
    if session_id:
        try:
            from app.core.ab_test.service import ab_test_service

            variant = await ab_test_service.pick_variant(project_id, session_id)
            if variant and variant.get("prompt_version_id"):
                pv = crud.get_prompt_version(variant["prompt_version_id"])
                if pv and pv.get("content"):
                    return pv["content"]
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] ab_test lookup failed: {e}")
    prompt = crud.get_active_prompt(project_id)
    return prompt["content"] if prompt else None


async def search_knowledge(query: str, project_id: str) -> Optional[str]:
    """從知識庫搜尋相關內容（走 rag_pipeline：依 vector_backend 選 Qdrant / pgvector / keyword）。"""
    try:
        from app.core.rag.pipeline import rag_pipeline

        rag_results = await rag_pipeline.search(project_id, query, top_k=5)
        if rag_results:
            parts = [r["content"] for r in rag_results if r.get("content")]
            if parts:
                return "\n\n---\n\n".join(parts)
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] rag_pipeline.search failed, falling back to keyword: {e}")

    try:
        results = crud.search_knowledge_chunks(project_id, query, limit=5)
        if results:
            context_parts = [r["content"] for r in results]
            return "\n\n---\n\n".join(context_parts)
    except Exception:
        pass
    return None
