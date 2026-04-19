"""Tests for Budget Service."""
from __future__ import annotations

import pytest

from app.core.budget.service import BudgetService, _month_key


@pytest.fixture
def svc():
    return BudgetService()


@pytest.mark.asyncio
async def test_status_disabled_when_no_budget_set(svc, monkeypatch):
    monkeypatch.setattr("app.db.crud.get_tenant", lambda _t: {"id": "t1", "settings": {}})
    monkeypatch.setattr("app.db.crud.get_tenant_monthly_cost", lambda _t: 10.0)
    status = await svc.get_status("t1")
    assert status["level"] == "disabled"
    assert status["budget_usd"] == 0


@pytest.mark.asyncio
async def test_status_levels(svc, monkeypatch):
    settings = {"monthly_budget_usd": 100, "budget_alert_threshold": 0.8}
    monkeypatch.setattr("app.db.crud.get_tenant", lambda _t: {"id": "t1", "settings": settings})

    monkeypatch.setattr("app.db.crud.get_tenant_monthly_cost", lambda _t: 10.0)
    assert (await svc.get_status("t1"))["level"] == "ok"

    monkeypatch.setattr("app.db.crud.get_tenant_monthly_cost", lambda _t: 85.0)
    assert (await svc.get_status("t1"))["level"] == "threshold"

    monkeypatch.setattr("app.db.crud.get_tenant_monthly_cost", lambda _t: 120.0)
    assert (await svc.get_status("t1"))["level"] == "exceeded"


@pytest.mark.asyncio
async def test_update_config_clamps_threshold(svc, monkeypatch):
    captured = {}
    monkeypatch.setattr("app.db.crud.get_tenant", lambda _t: {"id": "t1", "settings": {}})

    def fake_update(tid, patch):
        captured.update(patch)
        return {"id": tid, "settings": patch}

    monkeypatch.setattr("app.db.crud.update_tenant_settings", fake_update)
    await svc.update_config("t1", monthly_budget_usd=50, budget_alert_threshold=2.0, budget_alert_webhook="http://x")
    assert captured["monthly_budget_usd"] == 50.0
    assert captured["budget_alert_threshold"] == 1.0  # clamped
    assert captured["budget_alert_webhook"] == "http://x"
    # Any config change resets "sent" marker
    assert captured["budget_alert_sent_for"] is None
    assert captured["budget_alert_month"] == _month_key()


@pytest.mark.asyncio
async def test_check_and_notify_skips_if_under_threshold(svc, monkeypatch):
    monkeypatch.setattr(
        "app.db.crud.get_tenant",
        lambda _t: {"id": "t1", "settings": {"monthly_budget_usd": 100, "budget_alert_threshold": 0.8}},
    )
    monkeypatch.setattr("app.db.crud.get_tenant_monthly_cost", lambda _t: 10.0)
    result = await svc.check_and_notify("t1")
    assert result["notified"] is False
    assert result["reason"] == "under threshold"


@pytest.mark.asyncio
async def test_check_and_notify_does_not_resend_same_level(svc, monkeypatch):
    settings = {
        "monthly_budget_usd": 100,
        "budget_alert_threshold": 0.8,
        "budget_alert_webhook": "http://hook",
        "budget_alert_sent_for": "threshold",
        "budget_alert_month": _month_key(),
    }
    monkeypatch.setattr("app.db.crud.get_tenant", lambda _t: {"id": "t1", "settings": settings})
    monkeypatch.setattr("app.db.crud.get_tenant_monthly_cost", lambda _t: 85.0)

    called = {"n": 0}
    monkeypatch.setattr("app.db.crud.update_tenant_settings", lambda *a, **k: called.update(n=called["n"] + 1))

    result = await svc.check_and_notify("t1")
    assert result["notified"] is False
    assert "already sent" in result["reason"]


@pytest.mark.asyncio
async def test_check_and_notify_posts_webhook_when_threshold_crossed(svc, monkeypatch):
    settings = {
        "monthly_budget_usd": 100,
        "budget_alert_threshold": 0.8,
        "budget_alert_webhook": "http://hook.test/notify",
    }
    monkeypatch.setattr("app.db.crud.get_tenant", lambda _t: {"id": "t1", "settings": dict(settings)})
    monkeypatch.setattr("app.db.crud.get_tenant_monthly_cost", lambda _t: 85.0)

    patched = {}
    monkeypatch.setattr("app.db.crud.update_tenant_settings", lambda tid, p: patched.update(p))

    called = {}

    async def fake_send(url, event, data, fmt=None):
        called["url"] = url
        called["event"] = event
        called["data"] = data
        return True, None

    monkeypatch.setattr("app.core.budget.service.notifier_send", fake_send)

    result = await svc.check_and_notify("t1")
    assert result["notified"] is True
    assert called["url"] == "http://hook.test/notify"
    assert called["event"] == "ait.budget_alert"
    assert called["data"]["level"] == "threshold"
    assert patched["budget_alert_sent_for"] == "threshold"
