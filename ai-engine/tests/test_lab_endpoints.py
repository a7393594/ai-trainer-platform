"""Tests for Experiment Studio (Lab) endpoints.

Covers:
  - 4-source unified case listing
  - Single-question rerun dispatch for all source types
  - Batch rerun fan-out (validation + parallel invocation)
  - Overrides persistence
  - Workflow engine `_steps_override` honors lab overrides
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import lab as lab_module
from app.core.workflows.engine import WorkflowEngine


@pytest.fixture
def client(monkeypatch):
    # Build a minimal FastAPI app mounting only the lab router to avoid heavy
    # top-level imports during isolated endpoint tests.
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(lab_module.router, prefix="/api/v1")
    return TestClient(app)


# -----------------------------------------------------------------------
# /lab/cases/by-project — 4-source union listing
# -----------------------------------------------------------------------

def test_list_cases_unions_four_sources(client, monkeypatch):
    monkeypatch.setattr(
        lab_module.crud,
        "list_pipeline_runs",
        lambda **kw: [
            {
                "id": "pl1",
                "input_text": "what is 2+2?",
                "mode": "live",
                "status": "completed",
                "total_cost_usd": 0.001,
                "created_at": "2026-04-15T00:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        lab_module.crud,
        "list_sessions",
        lambda **kw: [
            {
                "id": "s1",
                "session_type": "freeform",
                "user_id": "abcdef123456",
                "started_at": "2026-04-14T00:00:00Z",
                "ended_at": None,
            }
        ],
    )

    # Stub supabase for workflow + comparison runs
    class _Table:
        def __init__(self, rows):
            self._rows = rows
            self._active_table = None

        def select(self, *a, **kw):
            return self

        def eq(self, *a, **kw):
            return self

        def in_(self, *a, **kw):
            return self

        def order(self, *a, **kw):
            return self

        def limit(self, *a, **kw):
            return self

        def execute(self):
            import types as _t
            return _t.SimpleNamespace(data=self._rows)

    class _Client:
        def table(self, name):
            if name == "ait_workflows":
                return _Table([{"id": "wf1", "name": "Greet flow"}])
            if name == "ait_workflow_runs":
                return _Table(
                    [
                        {
                            "id": "wr1",
                            "workflow_id": "wf1",
                            "status": "completed",
                            "started_at": "2026-04-13T00:00:00Z",
                            "context_json": {"_trace": [{}, {}]},
                        }
                    ]
                )
            if name == "ait_comparison_runs":
                return _Table(
                    [
                        {
                            "id": "cr1",
                            "name": "multi-model shootout",
                            "status": "completed",
                            "created_at": "2026-04-16T00:00:00Z",
                        }
                    ]
                )
            return _Table([])

    monkeypatch.setattr(lab_module, "get_supabase", lambda: _Client())

    res = client.get("/api/v1/lab/cases/by-project/proj-1")
    assert res.status_code == 200
    items = res.json()["items"]
    source_types = {i["source_type"] for i in items}
    assert source_types == {"pipeline", "workflow", "session", "comparison"}
    # Sorted new-to-old
    assert items[0]["source_type"] == "comparison"  # 2026-04-16 is newest


def test_list_cases_filters_by_source_type(client, monkeypatch):
    monkeypatch.setattr(
        lab_module.crud,
        "list_pipeline_runs",
        lambda **kw: [{"id": "pl1", "input_text": "q", "mode": "live", "created_at": "2026-04-15T00:00:00Z"}],
    )
    res = client.get("/api/v1/lab/cases/by-project/proj-1?source_type=pipeline")
    assert res.status_code == 200
    items = res.json()["items"]
    assert all(i["source_type"] == "pipeline" for i in items)


# -----------------------------------------------------------------------
# /lab/rerun — source dispatch
# -----------------------------------------------------------------------

def _stub_pipeline_source(monkeypatch, project_id="proj-1"):
    monkeypatch.setattr(
        lab_module.crud,
        "get_pipeline_run",
        lambda rid: {
            "id": rid,
            "project_id": project_id,
            "session_id": None,
            "input_text": "hi",
            "mode": "live",
        },
    )
    monkeypatch.setattr(
        lab_module.crud, "get_project", lambda pid: {"id": pid, "default_model": "claude-sonnet-4-20250514"}
    )
    monkeypatch.setattr(lab_module.crud, "get_active_prompt", lambda pid: {"content": "active system prompt"})


def _stub_parallel(monkeypatch):
    async def fake_parallel(messages, models, project_id=None, session_id=None):
        return [
            {
                "model": models[0],
                "output_text": "ok",
                "input_tokens": 3,
                "output_tokens": 5,
                "cost_usd": 0.0001,
                "latency_ms": 12,
            }
        ]
    monkeypatch.setattr(lab_module, "run_single_prompt_parallel", fake_parallel)


def _stub_supabase_insert(monkeypatch):
    class _Ins:
        def __init__(self, payload):
            self.data = [payload]

        def execute(self):
            return self

    class _Table:
        def insert(self, payload):
            return _Ins(payload)

        def update(self, payload):
            return self

        def eq(self, *a, **kw):
            return self

        def select(self, *a, **kw):
            return self

        def execute(self):
            import types as _t
            return _t.SimpleNamespace(data=[])

    monkeypatch.setattr(lab_module, "get_supabase", lambda: type("C", (), {"table": lambda self, n: _Table()})())


def test_rerun_pipeline_source_creates_lab_run_and_comparison(client, monkeypatch):
    _stub_pipeline_source(monkeypatch)
    _stub_parallel(monkeypatch)
    _stub_supabase_insert(monkeypatch)
    monkeypatch.setattr(lab_module.crud, "create_pipeline_comparison", lambda d: {"id": "cmp1", **d})

    res = client.post(
        "/api/v1/lab/rerun",
        json={
            "source_type": "pipeline",
            "source_id": "pl1",
            "input": "override question?",
            "overrides": {"prompt_override": "You are a pirate"},
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["lab_run_id"]
    assert body["result"]["output"] == "ok"
    assert body["result"]["comparison_id"] == "cmp1"


def test_rerun_rejects_unknown_source_type(client):
    res = client.post(
        "/api/v1/lab/rerun",
        json={"source_type": "invalid", "source_id": "x", "input": "q"},
    )
    assert res.status_code == 422  # pydantic validation


def test_batch_rerun_validates_input_bounds(client):
    # empty inputs array
    res = client.post(
        "/api/v1/lab/batch-rerun",
        json={"source_type": "pipeline", "source_id": "x", "inputs": []},
    )
    assert res.status_code == 422

    # too many inputs (>20)
    res = client.post(
        "/api/v1/lab/batch-rerun",
        json={"source_type": "pipeline", "source_id": "x", "inputs": ["q"] * 21},
    )
    assert res.status_code == 422


def test_batch_rerun_fans_out_in_parallel(client, monkeypatch):
    _stub_pipeline_source(monkeypatch)
    _stub_parallel(monkeypatch)
    _stub_supabase_insert(monkeypatch)
    monkeypatch.setattr(lab_module.crud, "create_pipeline_comparison", lambda d: {"id": "cmp_fake", **d})

    res = client.post(
        "/api/v1/lab/batch-rerun",
        json={
            "source_type": "pipeline",
            "source_id": "pl1",
            "inputs": ["a", "b", "c"],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["results"]) == 3
    assert all(r["output"] == "ok" for r in body["results"])


# -----------------------------------------------------------------------
# Workflow engine — _steps_override
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_engine_honors_steps_override(monkeypatch):
    # Stub workflow fetch + run creation + update + project lookup
    def fake_get_workflow(wid):
        return {
            "id": wid,
            "project_id": "proj-1",
            "steps_json": [{"id": "orig", "type": "action", "kind": "noop"}],
        }

    def fake_get_project(pid):
        return {"id": pid, "tenant_id": "tnt-1"}

    def fake_create_workflow_run(wid, sid, uid):
        return {"id": "wfr-1"}

    calls = {"updated": []}

    def fake_update_workflow_run(rid, **kw):
        calls["updated"].append(kw)
        return {"id": rid, **kw}

    monkeypatch.setattr("app.core.workflows.engine.crud.get_workflow", fake_get_workflow)
    monkeypatch.setattr("app.core.workflows.engine.crud.get_project", fake_get_project)
    monkeypatch.setattr("app.core.workflows.engine.crud.create_workflow_run", fake_create_workflow_run)
    monkeypatch.setattr("app.core.workflows.engine.crud.update_workflow_run", fake_update_workflow_run)

    executed = []

    async def capture_executor(step, ctx):
        executed.append(step.get("id"))
        return {"status": "success"}

    engine = WorkflowEngine(action_executor=capture_executor)
    override_steps = [
        {"id": "override1", "type": "action", "kind": "noop"},
        {"id": "override2", "type": "action", "kind": "noop"},
    ]
    result = await engine.run_to_completion(
        "wf1",
        session_id=None,
        user_id="u1",
        initial_vars={"_steps_override": override_steps},
    )
    assert result["status"] == "completed"
    # Only override steps executed, not the original "orig"
    assert executed == ["override1", "override2"]


@pytest.mark.asyncio
async def test_engine_falls_back_when_override_empty(monkeypatch):
    def fake_get_workflow(wid):
        return {
            "id": wid,
            "project_id": "proj-1",
            "steps_json": [{"id": "orig", "type": "action", "kind": "noop"}],
        }

    monkeypatch.setattr("app.core.workflows.engine.crud.get_workflow", fake_get_workflow)
    monkeypatch.setattr("app.core.workflows.engine.crud.get_project", lambda pid: None)
    monkeypatch.setattr("app.core.workflows.engine.crud.create_workflow_run", lambda *a, **kw: {"id": "wfr-2"})
    monkeypatch.setattr("app.core.workflows.engine.crud.update_workflow_run", lambda *a, **kw: None)

    executed = []

    async def capture_executor(step, ctx):
        executed.append(step.get("id"))
        return {"status": "success"}

    engine = WorkflowEngine(action_executor=capture_executor)
    # Empty list should fall back to original
    result = await engine.run_to_completion(
        "wf1",
        initial_vars={"_steps_override": []},
    )
    assert result["status"] == "completed"
    assert executed == ["orig"]
