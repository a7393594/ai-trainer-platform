"""Tests for Workflow Template Library."""
from __future__ import annotations

import pytest

from app.core.workflow_templates import library


def test_list_templates_returns_summaries():
    items = library.list_templates()
    assert len(items) >= 3
    for t in items:
        assert set(t.keys()) == {"id", "name", "description", "step_count"}
        assert t["step_count"] > 0


def test_get_template_known_id():
    tpl = library.get_template("support_escalation")
    assert tpl is not None
    assert tpl["id"] == "support_escalation"
    assert isinstance(tpl["steps"], list)


def test_get_template_unknown_id_returns_none():
    assert library.get_template("nonexistent") is None


def test_instantiate_calls_crud_with_deep_copy(monkeypatch):
    captured = {}

    def fake_create(project_id, name, trigger_description, steps_json):
        captured.update(
            project_id=project_id,
            name=name,
            trigger_description=trigger_description,
            steps_json=steps_json,
        )
        return {"id": "wf1", "name": name, "steps_json": steps_json}

    monkeypatch.setattr("app.db.crud.create_workflow", fake_create)

    wf = library.instantiate("p1", "refund_request", name_override="My Refund")
    assert wf["id"] == "wf1"
    assert captured["name"] == "My Refund"
    # steps should be a deep copy — mutating result must not affect template
    wf["steps_json"][0]["id"] = "mutated"
    original = library.get_template("refund_request")
    assert original["steps"][0]["id"] != "mutated"


def test_instantiate_unknown_template_returns_none(monkeypatch):
    monkeypatch.setattr("app.db.crud.create_workflow", lambda *a, **kw: pytest.fail("should not be called"))
    assert library.instantiate("p1", "not_a_template") is None


def test_instantiate_uses_template_defaults_when_no_overrides(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.db.crud.create_workflow",
        lambda project_id, name, trigger_description, steps_json: captured.update(
            name=name, trigger_description=trigger_description
        ) or {"id": "w"},
    )
    library.instantiate("p1", "support_escalation")
    assert captured["name"] == "客服升級流程"
    assert "真人" in captured["trigger_description"]
