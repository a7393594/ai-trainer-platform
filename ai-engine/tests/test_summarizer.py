"""Tests for ConversationSummarizer."""
from __future__ import annotations

import pytest

from app.core.summarizer.service import ConversationSummarizer


class _FakeChoice:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class _FakeResp:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


@pytest.fixture
def svc():
    return ConversationSummarizer()


@pytest.mark.asyncio
async def test_session_not_found(svc, monkeypatch):
    monkeypatch.setattr("app.db.crud.get_session", lambda _s: None)
    result = await svc.summarize_session("nope")
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_empty_session_short_circuits(svc, monkeypatch):
    monkeypatch.setattr("app.db.crud.get_session", lambda _s: {"id": "s1"})
    monkeypatch.setattr("app.db.crud.list_messages", lambda _s: [])
    result = await svc.summarize_session("s1")
    assert result["status"] == "empty"
    assert result["summary"] == ""


@pytest.mark.asyncio
async def test_below_threshold_returns_null_summary(svc, monkeypatch):
    msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    monkeypatch.setattr("app.db.crud.get_session", lambda _s: {"id": "s1"})
    monkeypatch.setattr("app.db.crud.list_messages", lambda _s: msgs)
    result = await svc.summarize_session("s1", threshold=5)
    assert result["status"] == "below_threshold"
    assert result["message_count"] == 2
    assert result["summary"] is None


@pytest.mark.asyncio
async def test_above_threshold_calls_llm_and_returns_summary(svc, monkeypatch):
    msgs = [
        {"role": "user", "content": f"Q{i}"} if i % 2 == 0 else {"role": "assistant", "content": f"A{i}"}
        for i in range(10)
    ]
    monkeypatch.setattr("app.db.crud.get_session", lambda _s: {"id": "s1"})
    monkeypatch.setattr("app.db.crud.list_messages", lambda _s: msgs)

    captured = {}

    async def fake_chat(**kw):
        captured.update(kw)
        return _FakeResp("- summary point 1\n- point 2")

    monkeypatch.setattr("app.core.summarizer.service.chat_completion", fake_chat)

    result = await svc.summarize_session("s1", threshold=5, persist=False)
    assert result["status"] == "summarized"
    assert result["message_count"] == 10
    assert "point 1" in result["summary"]
    assert result["persisted_message_id"] is None
    # prompt should mention 繁體中文 to keep locale
    assert "繁體中文" in captured["messages"][0]["content"]


@pytest.mark.asyncio
async def test_persist_writes_system_message(svc, monkeypatch):
    msgs = [
        {"role": "user", "content": "x"},
        {"role": "assistant", "content": "y"},
    ] * 10  # 20 messages → above default threshold
    monkeypatch.setattr("app.db.crud.get_session", lambda _s: {"id": "s1"})
    monkeypatch.setattr("app.db.crud.list_messages", lambda _s: msgs)

    async def fake_chat(**_kw):
        return _FakeResp("summary")

    monkeypatch.setattr("app.core.summarizer.service.chat_completion", fake_chat)

    created = {}

    def fake_create(session_id, role, content, metadata=None):
        created.update(session_id=session_id, role=role, content=content, metadata=metadata)
        return {"id": "m1", **created}

    monkeypatch.setattr("app.db.crud.create_message", fake_create)

    result = await svc.summarize_session("s1", threshold=5, persist=True)
    assert result["persisted_message_id"] == "m1"
    assert created["role"] == "system"
    assert created["metadata"]["summary"] is True
