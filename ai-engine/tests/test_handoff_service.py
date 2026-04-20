"""Tests for Hand-off Service."""
from __future__ import annotations

import pytest

from app.core.handoff.service import HandoffService


@pytest.fixture
def svc():
    return HandoffService()


@pytest.mark.asyncio
async def test_request_returns_error_when_session_missing(svc, monkeypatch):
    monkeypatch.setattr("app.db.crud.get_session", lambda _s: None)
    result = await svc.request("bad", "refund")
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_request_creates_system_message_with_handoff_meta(svc, monkeypatch):
    created = {}

    monkeypatch.setattr(
        "app.db.crud.get_session",
        lambda _s: {"id": "s1", "project_id": "p1"},
    )
    monkeypatch.setattr(
        "app.db.crud.get_project",
        lambda _p: {"id": "p1", "tenant_id": "t1"},
    )
    monkeypatch.setattr(
        "app.db.crud.get_tenant",
        lambda _t: {"id": "t1", "settings": {}},  # no webhook
    )

    def fake_create_message(session_id, role, content, metadata=None):
        created["session_id"] = session_id
        created["role"] = role
        created["content"] = content
        created["metadata"] = metadata or {}
        return {"id": "m1", **created}

    monkeypatch.setattr("app.db.crud.create_message", fake_create_message)

    result = await svc.request("s1", "user angry", urgency="high")
    assert result["status"] == "handoff_requested"
    assert result["urgency"] == "high"
    assert result["notified"] is False
    assert created["role"] == "system"
    assert "[HANDOFF]" in created["content"]
    assert created["metadata"]["handoff"]["status"] == "pending"
    assert created["metadata"]["handoff"]["urgency"] == "high"


@pytest.mark.asyncio
async def test_request_clamps_unknown_urgency(svc, monkeypatch):
    monkeypatch.setattr("app.db.crud.get_session", lambda _s: {"id": "s1", "project_id": "p1"})
    monkeypatch.setattr("app.db.crud.get_project", lambda _p: {"id": "p1", "tenant_id": "t1"})
    monkeypatch.setattr("app.db.crud.get_tenant", lambda _t: {"id": "t1", "settings": {}})

    created = {}

    def fake_create(session_id, role, content, metadata=None):
        created["metadata"] = metadata
        return {"id": "m1"}

    monkeypatch.setattr("app.db.crud.create_message", fake_create)
    await svc.request("s1", "reason", urgency="ultra")
    assert created["metadata"]["handoff"]["urgency"] == "normal"


@pytest.mark.asyncio
async def test_notify_reports_no_webhook_when_unset(svc, monkeypatch):
    monkeypatch.setattr("app.db.crud.get_project", lambda _p: {"tenant_id": "t1"})
    monkeypatch.setattr("app.db.crud.get_tenant", lambda _t: {"settings": {}})
    ok, detail = await svc._notify({"id": "s1", "project_id": "p1"}, {"id": "m1"}, {})
    assert ok is False
    assert "no webhook" in detail
