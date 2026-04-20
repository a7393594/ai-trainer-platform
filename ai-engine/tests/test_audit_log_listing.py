"""Tests for audit log listing CRUD helper."""
from __future__ import annotations

from types import SimpleNamespace

import pytest


def _fake_supabase_factory(recorded_calls):
    """Build a minimal chain that records filter chain and returns canned rows."""

    class Chain:
        def __init__(self, table_name):
            recorded_calls["table"] = table_name
            self.filters = []

        def select(self, *args):
            recorded_calls["select"] = args
            return self

        def eq(self, col, val):
            self.filters.append(("eq", col, val))
            return self

        def gte(self, col, val):
            self.filters.append(("gte", col, val))
            return self

        def order(self, col, desc=False):
            recorded_calls["order"] = (col, desc)
            return self

        def range(self, start, end):
            recorded_calls["range"] = (start, end)
            return self

        def execute(self):
            recorded_calls["filters"] = self.filters
            return SimpleNamespace(data=[
                {
                    "id": "a1", "tenant_id": "t1", "action_type": "tool_call",
                    "status": "success", "duration_ms": 12, "created_at": "2025-01-01",
                }
            ])

    class Client:
        def table(self, name):
            return Chain(name)

    return Client()


def test_list_audit_logs_applies_filters(monkeypatch):
    from app.db import crud

    recorded: dict = {}
    client = _fake_supabase_factory(recorded)
    monkeypatch.setattr("app.db.crud.get_supabase", lambda: client)

    rows = crud.list_audit_logs(
        "t1", action_type="tool_call", status="success", tool_id="tool-xx",
        limit=20, offset=40,
    )

    assert rows and rows[0]["id"] == "a1"
    # tenant_id always applied
    assert ("eq", "tenant_id", "t1") in recorded["filters"]
    # each optional filter applied
    assert ("eq", "action_type", "tool_call") in recorded["filters"]
    assert ("eq", "status", "success") in recorded["filters"]
    assert ("eq", "tool_id", "tool-xx") in recorded["filters"]
    # order desc
    assert recorded["order"] == ("created_at", True)
    # pagination range
    assert recorded["range"] == (40, 59)


def test_list_audit_logs_caps_limit(monkeypatch):
    from app.db import crud

    recorded: dict = {}
    client = _fake_supabase_factory(recorded)
    monkeypatch.setattr("app.db.crud.get_supabase", lambda: client)
    crud.list_audit_logs("t1", limit=10_000, offset=0)
    start, end = recorded["range"]
    # limit capped at 500
    assert end - start + 1 == 500
