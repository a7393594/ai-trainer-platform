"""Tests for Quality Monitor."""
from __future__ import annotations

import pytest

from app.core.quality.monitor import QualityMonitor


@pytest.fixture
def svc():
    return QualityMonitor()


def _project(cfg: dict | None = None, tenant_id: str = "t1") -> dict:
    return {
        "id": "p1",
        "tenant_id": tenant_id,
        "domain_config": {"quality_alert": cfg} if cfg is not None else {},
    }


@pytest.mark.asyncio
async def test_status_disabled_by_default(svc, monkeypatch):
    monkeypatch.setattr("app.db.crud.get_project", lambda _p: _project(None))
    monkeypatch.setattr(
        "app.db.crud.get_feedback_stats_window",
        lambda _p, _since: {"correct": 5, "partial": 1, "wrong": 2, "total": 8},
    )
    status = await svc.get_status("p1")
    assert status["level"] == "disabled"
    assert status["total"] == 8


@pytest.mark.asyncio
async def test_status_insufficient_data_when_below_min_samples(svc, monkeypatch):
    cfg = {"enabled": True, "min_samples": 20}
    monkeypatch.setattr("app.db.crud.get_project", lambda _p: _project(cfg))
    monkeypatch.setattr(
        "app.db.crud.get_feedback_stats_window",
        lambda _p, _since: {"correct": 3, "partial": 1, "wrong": 2, "total": 6},
    )
    status = await svc.get_status("p1")
    assert status["level"] == "insufficient_data"


@pytest.mark.asyncio
async def test_status_wrong_high(svc, monkeypatch):
    cfg = {"enabled": True, "min_samples": 5, "wrong_ratio_threshold": 0.2}
    monkeypatch.setattr("app.db.crud.get_project", lambda _p: _project(cfg))
    monkeypatch.setattr(
        "app.db.crud.get_feedback_stats_window",
        lambda _p, _since: {"correct": 6, "partial": 0, "wrong": 4, "total": 10},
    )
    status = await svc.get_status("p1")
    assert status["level"] == "wrong_high"
    assert status["wrong_ratio"] == 0.4


@pytest.mark.asyncio
async def test_status_negative_high(svc, monkeypatch):
    cfg = {
        "enabled": True, "min_samples": 5,
        "wrong_ratio_threshold": 0.9,
        "negative_ratio_threshold": 0.4,
    }
    monkeypatch.setattr("app.db.crud.get_project", lambda _p: _project(cfg))
    monkeypatch.setattr(
        "app.db.crud.get_feedback_stats_window",
        lambda _p, _since: {"correct": 4, "partial": 4, "wrong": 2, "total": 10},
    )
    status = await svc.get_status("p1")
    # wrong=20% (below 90%), negative=60% (above 40%) → negative_high
    assert status["level"] == "negative_high"


@pytest.mark.asyncio
async def test_update_config_clamps_thresholds(svc, monkeypatch):
    captured = {}

    def fake_update(pid, domain_config):
        captured.update(domain_config)
        return {"id": pid, "domain_config": domain_config}

    monkeypatch.setattr("app.db.crud.update_project_config", fake_update)
    await svc.update_config(
        "p1",
        enabled=True,
        window_hours=0,              # clamped to 1
        min_samples=-5,              # clamped to 1
        wrong_ratio_threshold=2.0,   # clamped to 1.0
        negative_ratio_threshold=-0.1,  # clamped to 0.0
        webhook="https://hook",
    )
    qa = captured["quality_alert"]
    assert qa["window_hours"] == 1
    assert qa["min_samples"] == 1
    assert qa["wrong_ratio_threshold"] == 1.0
    assert qa["negative_ratio_threshold"] == 0.0
    assert qa["webhook"] == "https://hook"


@pytest.mark.asyncio
async def test_check_and_notify_skips_when_ok(svc, monkeypatch):
    cfg = {"enabled": True, "min_samples": 1, "wrong_ratio_threshold": 0.99, "negative_ratio_threshold": 0.99}
    monkeypatch.setattr("app.db.crud.get_project", lambda _p: _project(cfg))
    monkeypatch.setattr(
        "app.db.crud.get_feedback_stats_window",
        lambda _p, _since: {"correct": 9, "partial": 1, "wrong": 0, "total": 10},
    )
    result = await svc.check_and_notify("p1")
    assert result["notified"] is False
    assert result["reason"] == "ok"


@pytest.mark.asyncio
async def test_check_and_notify_sends_webhook(svc, monkeypatch):
    cfg = {
        "enabled": True, "min_samples": 5,
        "wrong_ratio_threshold": 0.2,
        "webhook": "https://hook/quality",
    }
    monkeypatch.setattr("app.db.crud.get_project", lambda _p: _project(cfg))
    monkeypatch.setattr("app.db.crud.get_tenant", lambda _t: {"id": "t1", "settings": {}})
    monkeypatch.setattr(
        "app.db.crud.get_feedback_stats_window",
        lambda _p, _since: {"correct": 6, "partial": 0, "wrong": 4, "total": 10},
    )

    called = {}

    async def fake_send(url, event, data, fmt=None):
        called["url"] = url
        called["event"] = event
        called["data"] = data
        return True, None

    monkeypatch.setattr("app.core.quality.monitor.notifier_send", fake_send)
    result = await svc.check_and_notify("p1")
    assert result["notified"] is True
    assert called["url"] == "https://hook/quality"
    assert called["event"] == "ait.quality_alert"
    assert called["data"]["level"] == "wrong_high"
