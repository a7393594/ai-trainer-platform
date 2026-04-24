"""
Intent Classifier — 意圖分類器

支援兩段式匹配：
  1. Keyword / fuzzy 比對（快速、零成本、離線）
  2. Embedding 語意比對（使用 capability_rules.trigger_embedding）

  回傳最高分的 rule。未超過門檻時回 general。

升級重點：
  - 結合 keyword + semantic embedding
  - 可設 mode="keyword" | "semantic" | "hybrid"（預設 hybrid）
  - 支援非同步 classify_async（semantic 需要 embedding）
"""
from __future__ import annotations

import math
import re
from typing import Iterable

from app.db import crud


DEFAULT_THRESHOLD = 0.3
SEMANTIC_WEIGHT = 0.6
KEYWORD_WEIGHT = 0.4


def _cosine(a: Iterable[float], b: Iterable[float]) -> float:
    ax = list(a or [])
    bx = list(b or [])
    if not ax or not bx or len(ax) != len(bx):
        return 0.0
    dot = sum(x * y for x, y in zip(ax, bx))
    na = math.sqrt(sum(x * x for x in ax))
    nb = math.sqrt(sum(y * y for y in bx))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class IntentClassifier:
    """Classify user intent against capability rules (keyword + embedding)."""

    # --------------------------
    # 同步入口（keyword-only，零外部呼叫）
    # --------------------------

    def classify(self, message: str, project_id: str, threshold: float = DEFAULT_THRESHOLD) -> dict:
        rules = crud.list_capability_rules(project_id)
        if not rules:
            return self._empty()

        msg_lower = message.lower().strip()
        best, score, kws = None, 0.0, []
        for rule in rules:
            s, m = self._score_keyword(msg_lower, rule)
            s += (rule.get("priority", 0) or 0) * 0.01
            if s > score:
                best, score, kws = rule, s, m

        if best and score >= threshold:
            return {
                "type": "capability_rule",
                "rule": best,
                "confidence": min(score, 1.0),
                "matched_keywords": kws,
                "method": "keyword",
            }
        return self._empty()

    # --------------------------
    # 非同步入口（hybrid，含 semantic）
    # --------------------------

    async def classify_async(
        self,
        message: str,
        project_id: str,
        mode: str = "hybrid",
        threshold: float = DEFAULT_THRESHOLD,
    ) -> dict:
        rules = crud.list_capability_rules(project_id)
        if not rules:
            return self._empty()

        msg_lower = message.lower().strip()
        msg_embedding = await self._embed(message, project_id=project_id) if mode in ("semantic", "hybrid") else None

        best, best_score, best_keywords, best_method = None, 0.0, [], "keyword"
        for rule in rules:
            kw_score, matched = self._score_keyword(msg_lower, rule)
            sem_score = 0.0
            if msg_embedding is not None:
                sem_score = self._score_semantic(msg_embedding, rule)

            if mode == "semantic":
                score = sem_score
                method = "semantic"
            elif mode == "keyword":
                score = kw_score
                method = "keyword"
            else:  # hybrid
                # 當 embedding 不可用（或 rule 沒存 embedding），降級為純 keyword，
                # 避免權重切分壓低分數而錯失明顯命中。
                if msg_embedding is None or not rule.get("trigger_embedding"):
                    score = kw_score
                    method = "keyword"
                else:
                    score = kw_score * KEYWORD_WEIGHT + sem_score * SEMANTIC_WEIGHT
                    method = "hybrid"

            score += (rule.get("priority", 0) or 0) * 0.01
            if score > best_score:
                best, best_score, best_keywords, best_method = rule, score, matched, method

        if best and best_score >= threshold:
            return {
                "type": "capability_rule",
                "rule": best,
                "confidence": min(best_score, 1.0),
                "matched_keywords": best_keywords,
                "method": best_method,
            }
        return self._empty()

    def classify_batch(self, messages: list[str], project_id: str) -> list[dict]:
        return [self.classify(m, project_id) for m in messages]

    # --------------------------
    # 內部
    # --------------------------

    @staticmethod
    def _empty() -> dict:
        return {
            "type": "general",
            "rule": None,
            "confidence": 0,
            "matched_keywords": [],
            "method": "none",
        }

    def _score_keyword(self, message: str, rule: dict) -> tuple[float, list[str]]:
        score = 0.0
        matched: list[str] = []

        keywords = rule.get("trigger_keywords", []) or []
        if keywords:
            hits = 0
            for kw in keywords:
                kw_l = (kw or "").lower().strip()
                if kw_l and kw_l in message:
                    hits += 1
                    matched.append(kw)
            score += (hits / len(keywords)) * 0.7

        trigger = (rule.get("trigger_description") or "").lower()
        if trigger:
            trigger_words = set(re.findall(r"\w+", trigger))
            msg_words = set(re.findall(r"\w+", message))
            if trigger_words:
                overlap = len(trigger_words & msg_words)
                score += (overlap / len(trigger_words)) * 0.3
        return score, matched

    @staticmethod
    def _score_semantic(msg_embedding: list[float], rule: dict) -> float:
        trigger_emb = rule.get("trigger_embedding")
        if not trigger_emb:
            return 0.0
        return max(0.0, _cosine(msg_embedding, trigger_emb))

    async def _embed(self, text: str, project_id: str | None = None) -> list[float] | None:
        """取得文字的 embedding；失敗回 None 讓流程降級為 keyword-only。"""
        try:
            from app.core.llm_router.router import get_embedding

            return await get_embedding(text, project_id=project_id, endpoint="intent_classify")
        except Exception:
            return None


intent_classifier = IntentClassifier()
