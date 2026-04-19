"""Tests for the Qdrant adapter — feature flag + graceful degradation."""
from __future__ import annotations

from app.db import qdrant as qdb


def test_collection_name_stable():
    name = qdb._collection_name("abc-123-def")
    assert name == "ait_kb_abc123def"


def test_is_qdrant_available_default_false():
    # Without init_qdrant() being called with a real server, flag stays False
    qdb._available = False
    assert qdb.is_qdrant_available() is False


def test_upsert_noop_when_unavailable():
    qdb._available = False
    ok = qdb.upsert_chunk("p1", "id1", [0.0] * 4, {"content": "x"})
    assert ok is False


def test_search_returns_empty_when_unavailable():
    qdb._available = False
    assert qdb.search("p1", [0.0] * 4, limit=5) == []


def test_ensure_collection_no_raise_when_unavailable():
    qdb._available = False
    # Must not raise
    qdb.ensure_collection("p1")
