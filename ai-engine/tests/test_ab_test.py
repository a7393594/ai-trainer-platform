"""Tests for Prompt A/B Test Service."""
from __future__ import annotations

import pytest

from app.core.ab_test.service import ABTestService, _deterministic_choice


def test_deterministic_choice_is_stable():
    variants = [
        {"label": "A", "weight": 0.5, "prompt_version_id": "va"},
        {"label": "B", "weight": 0.5, "prompt_version_id": "vb"},
    ]
    a = _deterministic_choice("session-abc", variants)
    b = _deterministic_choice("session-abc", variants)
    assert a["label"] == b["label"]  # deterministic


def test_deterministic_choice_respects_weights():
    variants = [
        {"label": "A", "weight": 0.1, "prompt_version_id": "va"},
        {"label": "B", "weight": 0.9, "prompt_version_id": "vb"},
    ]
    counts = {"A": 0, "B": 0}
    for i in range(200):
        pick = _deterministic_choice(f"s{i}", variants)
        counts[pick["label"]] += 1
    # B should dominate; allow generous skew
    assert counts["B"] > counts["A"] * 3


def test_deterministic_choice_handles_empty():
    assert _deterministic_choice("s1", []) == {}


@pytest.fixture
def svc():
    return ABTestService()


@pytest.mark.asyncio
async def test_configure_rejects_empty_variants(svc):
    assert await svc.configure("p1", []) is None
    assert await svc.configure("p1", [{"weight": 1}]) is None  # missing prompt_version_id


@pytest.mark.asyncio
async def test_configure_stores_cleaned_config(svc, monkeypatch):
    captured = {}

    def fake_update(pid, patch):
        captured.update(patch)
        return {"id": pid, "domain_config": patch}

    monkeypatch.setattr("app.db.crud.update_project_config", fake_update)
    await svc.configure("p1", [
        {"prompt_version_id": "v1", "weight": 0.3, "label": "control"},
        {"prompt_version_id": "v2", "weight": 0.7, "label": "treatment"},
    ])
    ab = captured["ab_test"]
    assert ab["enabled"] is True
    assert len(ab["variants"]) == 2
    assert ab["variants"][0]["label"] == "control"


@pytest.mark.asyncio
async def test_pick_variant_disabled_returns_none(svc, monkeypatch):
    monkeypatch.setattr("app.db.crud.get_project", lambda _p: {"domain_config": {}})
    assert await svc.pick_variant("p1", "s1") is None


@pytest.mark.asyncio
async def test_pick_variant_tags_session_metadata(svc, monkeypatch):
    cfg = {
        "ab_test": {
            "enabled": True,
            "variants": [
                {"prompt_version_id": "v1", "weight": 1.0, "label": "A"},
            ],
        }
    }
    monkeypatch.setattr("app.db.crud.get_project", lambda _p: {"domain_config": cfg})

    # Fake supabase state: session with no previous ab_variant
    updates: list[dict] = []

    class _Chain:
        def __init__(self, data):
            self.data = data
        def select(self, *_a): return self
        def eq(self, *a): return self
        def execute(self):
            return type("R", (), {"data": self.data})()
        def update(self, patch):
            updates.append(patch)
            return self

    class _Client:
        def table(self, _name):
            return _Chain([{"metadata": {}}])

    monkeypatch.setattr("app.core.ab_test.service.get_supabase", lambda: _Client())

    picked = await svc.pick_variant("p1", "s1")
    assert picked["label"] == "A"
    # session metadata should have been updated
    assert any("metadata" in u for u in updates)


@pytest.mark.asyncio
async def test_pick_variant_keeps_existing_assignment(svc, monkeypatch):
    cfg = {
        "ab_test": {
            "enabled": True,
            "variants": [
                {"prompt_version_id": "v1", "weight": 1.0, "label": "A"},
            ],
        }
    }
    monkeypatch.setattr("app.db.crud.get_project", lambda _p: {"domain_config": cfg})

    updates: list[dict] = []

    class _Chain:
        def __init__(self, data):
            self.data = data
        def select(self, *_a): return self
        def eq(self, *a): return self
        def execute(self):
            return type("R", (), {"data": self.data})()
        def update(self, patch):
            updates.append(patch)
            return self

    class _Client:
        def table(self, _name):
            return _Chain([{"metadata": {"ab_variant": "already", "ab_prompt_version_id": "old"}}])

    monkeypatch.setattr("app.core.ab_test.service.get_supabase", lambda: _Client())

    picked = await svc.pick_variant("p1", "s1")
    assert picked["label"] == "A"
    # Should NOT issue an update since metadata already has ab_variant
    assert updates == []


@pytest.mark.asyncio
async def test_conclude_activates_winner(svc, monkeypatch):
    cfg = {
        "ab_test": {
            "enabled": True,
            "variants": [
                {"prompt_version_id": "v1", "weight": 0.5, "label": "A"},
                {"prompt_version_id": "v2", "weight": 0.5, "label": "B"},
            ],
        }
    }
    monkeypatch.setattr("app.db.crud.get_project", lambda _p: {"domain_config": cfg})
    activated = {}
    monkeypatch.setattr(
        "app.db.crud.activate_prompt_version",
        lambda vid, pid: activated.update(vid=vid, pid=pid) or {"id": vid, "is_active": True},
    )
    patched = {}
    monkeypatch.setattr(
        "app.db.crud.update_project_config",
        lambda pid, p: patched.update(p),
    )

    result = await svc.conclude("p1", "B")
    assert result["status"] == "concluded"
    assert activated["vid"] == "v2"
    assert patched["ab_test"]["enabled"] is False
    assert patched["ab_test"]["concluded_label"] == "B"


@pytest.mark.asyncio
async def test_conclude_unknown_label_errors(svc, monkeypatch):
    monkeypatch.setattr(
        "app.db.crud.get_project",
        lambda _p: {"domain_config": {"ab_test": {"variants": [{"label": "A", "prompt_version_id": "v1"}]}}},
    )
    result = await svc.conclude("p1", "Z")
    assert result["status"] == "error"
