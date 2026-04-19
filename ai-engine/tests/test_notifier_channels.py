"""Tests for notification channels — Slack formatter + dispatch."""
from __future__ import annotations

import pytest

from app.core.notifier import channels


def test_detect_format_slack_by_hostname():
    assert channels.detect_format("https://hooks.slack.com/services/xxx") == "slack"


def test_detect_format_generic_by_default():
    assert channels.detect_format("https://example.com/webhook") == "generic"


def test_detect_format_explicit_overrides():
    assert channels.detect_format("https://anything", explicit="slack") == "slack"
    assert channels.detect_format("https://hooks.slack.com", explicit="generic") == "generic"


def test_format_payload_generic_preserves_event_and_data():
    payload = channels.format_payload("ait.x", {"a": 1, "b": "two"}, "generic")
    assert payload == {"event": "ait.x", "a": 1, "b": "two"}


def test_format_payload_slack_budget_alert_exceeded_has_red_color():
    payload = channels.format_payload(
        "ait.budget_alert",
        {
            "tenant_id": "tenant1234abcd",
            "level": "exceeded",
            "month": "2025-04",
            "budget_usd": 100.0,
            "spent_usd": 150.0,
            "pct": 1.5,
            "threshold": 0.8,
        },
        "slack",
    )
    assert "Budget EXCEEDED" in payload["blocks"][0]["text"]["text"]
    assert payload["attachments"][0]["color"] == "#E01E5A"
    # text fallback present
    assert payload["text"].startswith("Budget EXCEEDED")


def test_format_payload_slack_handoff_fields():
    payload = channels.format_payload(
        "ait.handoff_requested",
        {
            "tenant_id": "t1",
            "project_id": "p1",
            "session_id": "s1",
            "handoff": {
                "reason": "user angry",
                "urgency": "urgent",
                "triggered_by": "user",
            },
        },
        "slack",
    )
    header = payload["blocks"][0]["text"]["text"]
    assert "urgent" in header
    # color maps to red for urgent
    assert payload["attachments"][0]["color"] == "#E01E5A"


def test_format_payload_slack_unknown_event_generic_fallback():
    payload = channels.format_payload("ait.unknown", {"x": 1, "y": "hi"}, "slack")
    # unknown events still produce valid Slack blocks
    assert payload["blocks"][0]["type"] == "header"


@pytest.mark.asyncio
async def test_send_returns_false_when_no_url():
    ok, detail = await channels.send("", "ait.x", {})
    assert ok is False
    assert "no webhook" in detail


@pytest.mark.asyncio
async def test_send_posts_json(monkeypatch):
    captured: dict = {}

    class _Resp:
        status_code = 200
        text = "ok"

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            captured["url"] = url
            captured["json"] = json
            return _Resp()

    import httpx as _h
    monkeypatch.setattr(_h, "AsyncClient", _Client)

    ok, detail = await channels.send(
        "https://hooks.slack.com/services/xx",
        "ait.handoff_requested",
        {"handoff": {"reason": "r", "urgency": "high"}},
    )
    assert ok is True and detail is None
    # Slack format auto-detected
    assert "blocks" in captured["json"]


@pytest.mark.asyncio
async def test_send_reports_non_2xx(monkeypatch):
    class _Resp:
        status_code = 500
        text = "server boom"

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            return _Resp()

    import httpx as _h
    monkeypatch.setattr(_h, "AsyncClient", _Client)

    ok, detail = await channels.send("https://x.test", "ait.x", {})
    assert ok is False
    assert "500" in detail
