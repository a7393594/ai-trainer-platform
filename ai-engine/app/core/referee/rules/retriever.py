"""
Rule Retriever — RAG 混合搜尋引擎
語意搜尋(pgvector) + 關鍵字搜尋(PostgreSQL full-text),加權融合。
"""
from typing import Optional
from app.db.supabase import get_supabase
from app.core.llm_router.router import get_embedding


async def hybrid_search(
    query: str,
    top_k: int = 5,
    game_type: str = None,
    semantic_weight: float = 0.5,
    keyword_weight: float = 0.5,
) -> list[dict]:
    """混合搜尋規則條文。

    1. 語意搜尋:把 query 向量化,在 pkr_rules.embedding 上做 cosine similarity
    2. 關鍵字搜尋:用 PostgreSQL ILIKE 做關鍵字比對(簡化版 BM25)
    3. 融合排序:兩邊都回前 top_k*2,按加權分數合併去重

    回傳: [{rule_id, rule_code, title, rule_text, source_name, priority, score, requires_judgment}]
    """
    sb = get_supabase()

    # 1. 語意搜尋
    semantic_results = []
    try:
        query_embedding = await get_embedding(query)
        semantic_results = (
            sb.rpc("match_pkr_rules", {
                "query_embedding": query_embedding,
                "match_threshold": 0.3,
                "match_count": top_k * 3,
            }).execute()
        ).data or []
    except Exception:
        pass  # 語意搜尋失敗時退化為純關鍵字

    # 2. 關鍵字搜尋(ILIKE — 對撲克專有名詞至關重要)
    keywords = query.lower().split()
    keyword_results = []
    keyword_hit_count: dict[str, int] = {}  # 每條規則被幾個關鍵字命中
    for kw in keywords[:5]:
        if len(kw) < 2:
            continue
        rows = (
            sb.table("pkr_rules")
            .select("id, rule_code, title, rule_text, source_id, requires_judgment, topic_tags")
            .ilike("rule_text", f"%{kw}%")
            .limit(top_k * 3)
            .execute()
        ).data or []
        for r in rows:
            keyword_hit_count[r["id"]] = keyword_hit_count.get(r["id"], 0) + 1
        keyword_results.extend(rows)

    # 同時搜 title
    for kw in keywords[:5]:
        if len(kw) < 2:
            continue
        rows = (
            sb.table("pkr_rules")
            .select("id, rule_code, title, rule_text, source_id, requires_judgment, topic_tags")
            .ilike("title", f"%{kw}%")
            .limit(top_k)
            .execute()
        ).data or []
        for r in rows:
            keyword_hit_count[r["id"]] = keyword_hit_count.get(r["id"], 0) + 2  # title 命中加倍
        keyword_results.extend(rows)

    # 3. 融合去重(關鍵字權重提高到 60% — 規格書建議 50-60%)
    scored: dict[str, dict] = {}

    for i, r in enumerate(semantic_results):
        rid = r.get("id", str(i))
        sim = r.get("similarity", 0.5)
        score = semantic_weight * sim
        scored[rid] = {**r, "score": score}

    for r in keyword_results:
        rid = r["id"]
        hits = keyword_hit_count.get(rid, 1)
        kw_score = keyword_weight * (0.3 + 0.2 * min(hits, 5))  # 多關鍵字命中加分
        if rid in scored:
            scored[rid]["score"] += kw_score
            # 補全欄位(語意搜尋可能缺 topic_tags 等)
            for k in ["topic_tags", "requires_judgment"]:
                if k not in scored[rid] and k in r:
                    scored[rid][k] = r[k]
        else:
            scored[rid] = {**r, "score": kw_score}

    # 按分數排序,取 top_k
    ranked = sorted(scored.values(), key=lambda x: x["score"], reverse=True)[:top_k]

    # 補充 source 資訊
    for r in ranked:
        if "source_id" in r and r["source_id"]:
            source = (
                sb.table("pkr_rule_sources")
                .select("name, priority")
                .eq("id", r["source_id"])
                .execute()
            ).data
            if source:
                r["source_name"] = source[0]["name"]
                r["priority"] = source[0]["priority"]

    return ranked


async def search_by_topic(topic: str, top_k: int = 5) -> list[dict]:
    """按 topic_tag 精確搜尋。"""
    sb = get_supabase()
    return (
        sb.table("pkr_rules")
        .select("*, pkr_rule_sources(name, priority)")
        .contains("topic_tags", [topic])
        .order("rule_code")
        .limit(top_k)
        .execute()
    ).data or []
