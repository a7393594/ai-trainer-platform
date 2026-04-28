"""In-memory KBIndex 實作 — hybrid search（keyword + semantic）。

設計：
- load() 一次把所有 markdown KB 條目讀進記憶體 + 預算 embedding
- search() 同時做 keyword（aliases / tags）跟 semantic（cosine on definition+core_concept）
  最後 weighted merge → top_k
- get_embedding 失敗時自動退回 keyword-only，不 crash

注意：
- 這個 index 跟既有 `crud.search_knowledge_chunks` 是兩套 KB（前者來自 markdown，
  後者是 DB 表）。
- 全域單例 `kb_retriever`：第一次 search 會 lazy load。
"""
from __future__ import annotations

import math
from typing import Optional

from app.core.llm_router.router import get_embedding

from .adapter_md import load_all_entries
from .interface import KnowledgeRetriever
from .schema import Content, KBChunk, KBEntry


class InMemoryKBIndex:
    """全 in-memory KB index，支援 hybrid search。"""

    def __init__(self) -> None:
        self.entries: dict[str, KBEntry] = {}
        self.by_category: dict[str, list[str]] = {}
        self.by_level: dict[int, list[str]] = {}
        self.by_tag: dict[str, list[str]] = {}
        self.by_alias: dict[str, list[str]] = {}  # alias_lower → [ids]
        self.embeddings: dict[str, list[float]] = {}
        self._loaded = False

    async def load(self) -> None:
        """從 markdown 檔讀進來、建 index、算 embedding。"""
        if self._loaded:
            return

        for entry in load_all_entries():
            self.entries[entry.id] = entry
            self.by_category.setdefault(entry.category, []).append(entry.id)
            self.by_level.setdefault(entry.prerequisite_level, []).append(entry.id)

            for tag in entry.tags:
                self.by_tag.setdefault(tag.lower(), []).append(entry.id)

            if entry.aliases:
                # 收 zh-tw + en 的 aliases，全部 lowercase 進 lookup
                for alias in (entry.aliases.zh_tw or []) + (entry.aliases.en or []):
                    if not alias:
                        continue
                    self.by_alias.setdefault(alias.lower(), []).append(entry.id)

            # 標題本身也算 alias（讓 semantic-fail 時 keyword 仍能命中）
            if entry.title.zh_tw:
                self.by_alias.setdefault(entry.title.zh_tw.lower(), []).append(entry.id)
            if entry.title.en:
                self.by_alias.setdefault(entry.title.en.lower(), []).append(entry.id)

            # embedding（definition + core_concept，截斷至 2000 字以避免過長）
            content = entry.primary_content()
            if content:
                text = (content.definition + " " + content.core_concept)[:2000]
                try:
                    emb = await get_embedding(text)
                    self.embeddings[entry.id] = emb
                except Exception as e:
                    print(f"[kb_retriever] embedding failed for {entry.id}: {e}")

        self._loaded = True
        print(f"[kb_retriever] loaded {len(self.entries)} entries, {len(self.embeddings)} embeddings")

    async def search(
        self,
        query: str,
        *,
        level_max: int = 2,
        top_k: int = 5,
    ) -> list[KBChunk]:
        """Hybrid search：keyword + semantic merge。"""
        await self.load()
        if not self.entries:
            return []

        # ─── Keyword pass ──────────────────────────────
        kw_scores: dict[str, float] = {}
        q_lower = query.lower()

        # alias hit (含 title)：權重 0.7
        for alias, ids in self.by_alias.items():
            if alias and alias in q_lower:
                for eid in ids:
                    if self.entries[eid].prerequisite_level <= level_max:
                        kw_scores[eid] = kw_scores.get(eid, 0.0) + 0.7

        # tag hit：權重 0.3
        for tag, ids in self.by_tag.items():
            if tag and tag in q_lower:
                for eid in ids:
                    if self.entries[eid].prerequisite_level <= level_max:
                        kw_scores[eid] = kw_scores.get(eid, 0.0) + 0.3

        # ─── Semantic pass ─────────────────────────────
        sem_scores: dict[str, float] = {}
        if self.embeddings:
            try:
                q_emb = await get_embedding(query)
                for eid, emb in self.embeddings.items():
                    if self.entries[eid].prerequisite_level > level_max:
                        continue
                    sem_scores[eid] = _cosine(q_emb, emb)
            except Exception as e:
                # semantic 失敗就純靠 keyword
                print(f"[kb_retriever] semantic search failed: {e}")

        # ─── Hybrid merge ──────────────────────────────
        # keyword 0.4 + semantic 0.6（semantic 比較有泛化能力）
        all_ids = set(kw_scores) | set(sem_scores)
        merged: list[tuple[str, float]] = [
            (eid, kw_scores.get(eid, 0.0) * 0.4 + sem_scores.get(eid, 0.0) * 0.6)
            for eid in all_ids
        ]
        # 過濾零分（純為 negative semantic 場景，但保險）
        merged = [(eid, score) for eid, score in merged if score > 0]
        merged.sort(key=lambda x: -x[1])

        results: list[KBChunk] = []
        for eid, score in merged[:top_k]:
            entry = self.entries[eid]
            results.append(self._to_chunk(entry, score))
        return results

    def _to_chunk(self, entry: KBEntry, score: float) -> KBChunk:
        """把 KBEntry 轉成給 LLM 用的 KBChunk。"""
        content = entry.primary_content()
        text_parts: list[str] = [f"# {entry.primary_title}"]

        if content:
            text_parts.append(f"定義：{content.definition}")
            # core_concept 截 500 字以控制 prompt size
            text_parts.append(f"核心：{content.core_concept[:500]}")
            if content.examples:
                ex = content.examples[0]
                text_parts.append(f"範例：{ex.title} — {ex.description[:300]}")

        return KBChunk(
            id=entry.id,
            citation=f"kb://{entry.id}",
            level=entry.prerequisite_level,
            title=entry.primary_title,
            content_text="\n".join(text_parts),
            full_url=f"/kb/entry/{entry.id}",
        )

    def list_entries(self) -> list[str]:
        return list(self.entries.keys())

    def get_entry(self, entry_id: str) -> Optional[dict]:
        e = self.entries.get(entry_id)
        return e.model_dump(by_alias=True) if e else None


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity；長度不一或全零回 0。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# ── 全域單例（進程級） ─────────────────────────
# 第一次 search 會 lazy load，後續 reuse
kb_retriever: KnowledgeRetriever = InMemoryKBIndex()
