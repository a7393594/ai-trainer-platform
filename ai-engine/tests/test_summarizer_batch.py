"""Tests for batch summarization runner."""
from __future__ import annotations

import pytest

from app.core.summarizer.service import ConversationSummarizer


class _FakeChoice:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class _FakeResp:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


def _fake_db(sessions):
    class _Chain:
        def __init__(self, data):
            self._d = data
        def select(self, *_a): return self
        def eq(self, *_a): return self
        def order(self, *_a, **_kw): return self
        def limit(self, *_a): return self
        def execute(self):
            return type("R", (), {"data": self._d})()

    class _Client:
        def table(self, _name):
            return _Chain(sessions)

    return _Client()


@pytest.mark.asyncio
async def test_batch_summarize_skips_already_summarized(monkeypatch):
    svc = ConversationSummarizer()
    sessions = [{"id": "s1"}, {"id": "s2"}]
    monkeypatch.setattr("app.core.summarizer.service.get_supabase", lambda: _fake_db(sessions))

    msg_map = {
        "s1": [{"role": "system", "metadata": {"summary": True}, "content": "x"}],  # already summarized
        "s2": [{"role": "user", "content": "hi"}] * 30,
    }
    monkeypatch.setattr("app.db.crud.list_messages", lambda sid: msg_map.get(sid, []))
    monkeypatch.setattr("app.db.crud.get_session", lambda sid: {"id": sid})

    async def fake_chat(**_kw):
        return _FakeResp("bullet summary")

    monkeypatch.setattr("app.core.summarizer.service.chat_completion", fake_chat)

    saved = []
    monkeypatch.setattr(
        "app.db.crud.create_message",
        lambda session_id, role, content, metadata=None: saved.append(session_id) or {"id": f"m-{session_id}"},
    )

    result = await svc.batch_summarize_project("p1", threshold=5, persist=True)
    assert result["total"] == 2
    assert result["summarized"] == 1  # only s2
    assert result["skipped"] == 1  # s1 skipped
    assert saved == ["s2"]


@pytest.mark.asyncio
async def test_batch_summarize_counts_errors(monkeypatch):
    svc = ConversationSummarizer()
    sessions = [{"id": "s1"}]
    monkeypatch.setattr("app.core.summarizer.service.get_supabase", lambda: _fake_db(sessions))

    def boom(_sid):
        raise RuntimeError("db down")

    monkeypatch.setattr("app.db.crud.list_messages", boom)

    result = await svc.batch_summarize_project("p1", skip_already_summarized=True)
    assert result["errors"] == 1
    assert result["summarized"] == 0
