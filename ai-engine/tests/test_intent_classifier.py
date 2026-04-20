"""Tests for Intent Classifier — keyword, semantic, hybrid modes."""
from __future__ import annotations

import pytest

from app.core.intent.classifier import IntentClassifier, _cosine


# ---------- cosine ----------

def test_cosine_identical_vectors():
    assert _cosine([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)


def test_cosine_orthogonal():
    assert _cosine([1, 0], [0, 1]) == 0.0


def test_cosine_handles_mismatched_lengths():
    assert _cosine([1, 2], [1, 2, 3]) == 0.0


def test_cosine_handles_empty():
    assert _cosine([], [1, 2]) == 0.0


# ---------- keyword scoring ----------

@pytest.fixture
def clf():
    return IntentClassifier()


def test_classify_no_rules_returns_general(clf, monkeypatch):
    monkeypatch.setattr("app.db.crud.list_capability_rules", lambda _p: [])
    r = clf.classify("anything", "p1")
    assert r["type"] == "general"


def test_classify_keyword_match(clf, monkeypatch):
    rules = [{
        "id": "r1",
        "trigger_keywords": ["退款", "refund"],
        "trigger_description": "處理退款請求",
        "priority": 0,
    }]
    monkeypatch.setattr("app.db.crud.list_capability_rules", lambda _p: rules)
    r = clf.classify("我想申請退款", "p1")
    assert r["type"] == "capability_rule"
    assert "退款" in r["matched_keywords"]


def test_classify_below_threshold_returns_general(clf, monkeypatch):
    rules = [{
        "id": "r1",
        "trigger_keywords": ["a", "b", "c", "d"],
        "trigger_description": "something unrelated",
        "priority": 0,
    }]
    monkeypatch.setattr("app.db.crud.list_capability_rules", lambda _p: rules)
    r = clf.classify("hello world", "p1")
    assert r["type"] == "general"


# ---------- semantic / hybrid ----------

@pytest.mark.asyncio
async def test_classify_async_semantic(clf, monkeypatch):
    rules = [{
        "id": "r1",
        "trigger_keywords": [],
        "trigger_description": "處理退款",
        "trigger_embedding": [1.0, 0.0, 0.0],
        "priority": 0,
    }]
    monkeypatch.setattr("app.db.crud.list_capability_rules", lambda _p: rules)

    async def fake_embed(_text):
        return [0.99, 0.01, 0.0]
    monkeypatch.setattr(clf, "_embed", fake_embed)

    r = await clf.classify_async("我要退款", "p1", mode="semantic")
    assert r["type"] == "capability_rule"
    assert r["method"] == "semantic"
    assert r["confidence"] > 0.9


@pytest.mark.asyncio
async def test_classify_async_hybrid_falls_back_when_embed_fails(clf, monkeypatch):
    rules = [{
        "id": "r1",
        "trigger_keywords": ["退款"],
        "trigger_description": "退款",
        "trigger_embedding": None,
        "priority": 0,
    }]
    monkeypatch.setattr("app.db.crud.list_capability_rules", lambda _p: rules)

    async def failing_embed(_text):
        return None
    monkeypatch.setattr(clf, "_embed", failing_embed)

    r = await clf.classify_async("我想退款", "p1", mode="hybrid")
    # 即便 embedding 失敗也應靠關鍵字命中
    assert r["type"] == "capability_rule"


@pytest.mark.asyncio
async def test_classify_async_keyword_mode_ignores_embedding(clf, monkeypatch):
    rules = [{
        "id": "r1",
        "trigger_keywords": ["退款"],
        "trigger_description": "退款",
        "trigger_embedding": [1.0, 0.0],
        "priority": 0,
    }]
    monkeypatch.setattr("app.db.crud.list_capability_rules", lambda _p: rules)

    called = {"n": 0}

    async def fake_embed(_text):
        called["n"] += 1
        return [1.0, 0.0]

    monkeypatch.setattr(clf, "_embed", fake_embed)
    r = await clf.classify_async("退款請", "p1", mode="keyword")
    assert r["method"] == "keyword"
    assert called["n"] == 0  # keyword 模式不應呼叫 embed
