"""Tests for plan limits enforcement."""
from __future__ import annotations

import pytest

from app.core.plan.limits import LimitExceeded, PlanLimitsService, PLAN_DEFAULTS


@pytest.fixture
def svc():
    return PlanLimitsService()


def test_defaults_per_plan():
    assert PLAN_DEFAULTS["free"]["sessions_per_month"] == 100
    assert PLAN_DEFAULTS["enterprise"]["sessions_per_month"] is None


def test_get_limits_uses_plan(monkeypatch, svc):
    monkeypatch.setattr("app.db.crud.get_tenant", lambda _t: {"plan": "pro", "settings": {}})
    limits = svc.get_limits("t1")
    assert limits["plan"] == "pro"
    assert limits["sessions_per_month"] == 10_000


def test_get_limits_respects_overrides(monkeypatch, svc):
    monkeypatch.setattr(
        "app.db.crud.get_tenant",
        lambda _t: {"plan": "free", "settings": {"plan_limits": {"sessions_per_month": 9999}}},
    )
    limits = svc.get_limits("t1")
    assert limits["sessions_per_month"] == 9999
    # other fields keep default
    assert limits["tokens_per_month"] == 50_000


def test_get_limits_unknown_plan_falls_back_to_free(monkeypatch, svc):
    monkeypatch.setattr("app.db.crud.get_tenant", lambda _t: {"plan": "mystery", "settings": {}})
    limits = svc.get_limits("t1")
    assert limits["plan"] == "mystery"
    assert limits["sessions_per_month"] == PLAN_DEFAULTS["free"]["sessions_per_month"]


def _fake_supabase(rows_by_table):
    class _Chain:
        def __init__(self, rows):
            self._rows = rows
            self.data = rows
        def select(self, *_a): return self
        def eq(self, *_a): return self
        def in_(self, *_a): return self
        def gte(self, *_a): return self
        def execute(self):
            return type("R", (), {"data": self._rows})()

    class _Client:
        def table(self, name):
            return _Chain(rows_by_table.get(name, []))

    return _Client()


def test_check_usage_reports_blocked_keys(monkeypatch, svc):
    monkeypatch.setattr("app.db.crud.get_tenant", lambda _t: {"plan": "free", "settings": {}})
    # Free plan limits: sessions 100, tokens 50k, projects 1
    client = _fake_supabase({
        "ait_projects": [{"id": "p1"}, {"id": "p2"}],  # 2 projects — exceeds free=1
        "ait_training_sessions": [{"id": f"s{i}"} for i in range(200)],  # over 100
        "ait_llm_usage": [{"total_tokens": 1000}] * 100,
    })
    monkeypatch.setattr("app.core.plan.limits.get_supabase", lambda: client)
    status = svc.check_usage("t1")
    assert status["ok"] is False
    blocked_keys = {b["key"] for b in status["blocked"]}
    assert "sessions_per_month" in blocked_keys
    assert "projects" in blocked_keys
    # tokens at 100k, limit 50k → also blocked
    assert "tokens_per_month" in blocked_keys


def test_check_usage_ok_when_under_limits(monkeypatch, svc):
    monkeypatch.setattr("app.db.crud.get_tenant", lambda _t: {"plan": "pro", "settings": {}})
    client = _fake_supabase({
        "ait_projects": [{"id": "p1"}],
        "ait_training_sessions": [{"id": "s1"}],
        "ait_llm_usage": [{"total_tokens": 100}],
    })
    monkeypatch.setattr("app.core.plan.limits.get_supabase", lambda: client)
    status = svc.check_usage("t1")
    assert status["ok"] is True
    assert status["blocked"] == []
    assert status["remaining"]["sessions_per_month"] == 9999


def test_check_usage_enterprise_has_no_blocks(monkeypatch, svc):
    monkeypatch.setattr("app.db.crud.get_tenant", lambda _t: {"plan": "enterprise", "settings": {}})
    client = _fake_supabase({
        "ait_projects": [{"id": f"p{i}"} for i in range(200)],
        "ait_training_sessions": [{"id": f"s{i}"} for i in range(1_000_000)],
        "ait_llm_usage": [{"total_tokens": 10_000_000}],
    })
    monkeypatch.setattr("app.core.plan.limits.get_supabase", lambda: client)
    status = svc.check_usage("t1")
    assert status["ok"] is True
    assert status["remaining"]["sessions_per_month"] is None  # unlimited


def test_enforce_session_create_raises_when_blocked(monkeypatch, svc):
    monkeypatch.setattr("app.db.crud.get_tenant", lambda _t: {"plan": "free", "settings": {}})
    client = _fake_supabase({
        "ait_projects": [{"id": "p1"}],
        "ait_training_sessions": [{"id": f"s{i}"} for i in range(100)],
        "ait_llm_usage": [],
    })
    monkeypatch.setattr("app.core.plan.limits.get_supabase", lambda: client)
    with pytest.raises(LimitExceeded) as exc_info:
        svc.enforce_session_create("t1")
    assert exc_info.value.key == "sessions_per_month"


def test_enforce_session_create_ignores_token_and_projects(monkeypatch, svc):
    """Tokens or project-cap blocks should NOT stop new sessions on existing projects."""
    monkeypatch.setattr("app.db.crud.get_tenant", lambda _t: {"plan": "free", "settings": {}})
    client = _fake_supabase({
        "ait_projects": [{"id": "p1"}],  # at project cap
        "ait_training_sessions": [{"id": "s1"}],
        "ait_llm_usage": [{"total_tokens": 100_000}],  # over tokens limit
    })
    monkeypatch.setattr("app.core.plan.limits.get_supabase", lambda: client)
    # Should not raise — only sessions gates session creation
    svc.enforce_session_create("t1")


def test_enforce_project_create_blocks_at_project_cap(monkeypatch, svc):
    monkeypatch.setattr("app.db.crud.get_tenant", lambda _t: {"plan": "free", "settings": {}})
    client = _fake_supabase({
        "ait_projects": [{"id": "p1"}],
        "ait_training_sessions": [],
        "ait_llm_usage": [],
    })
    monkeypatch.setattr("app.core.plan.limits.get_supabase", lambda: client)
    with pytest.raises(LimitExceeded) as exc_info:
        svc.enforce_project_create("t1")
    assert exc_info.value.key == "projects"
