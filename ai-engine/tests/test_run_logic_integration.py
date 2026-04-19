"""Integration tests verifying key flows after the run-logic audit."""
from __future__ import annotations

import pytest

from app.core.orchestrator.agent import AgentOrchestrator


# -------------------------------------------------------------------
# A/B test is actually triggered by orchestrator._load_active_prompt
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_active_prompt_consults_ab_test_when_session_given(monkeypatch):
    orch = AgentOrchestrator()

    called = {}

    async def fake_pick(project_id, session_id):
        called["project_id"] = project_id
        called["session_id"] = session_id
        return {"prompt_version_id": "pv-variant", "label": "B"}

    monkeypatch.setattr("app.core.ab_test.service.ab_test_service.pick_variant", fake_pick)
    monkeypatch.setattr(
        "app.db.crud.get_prompt_version",
        lambda vid: {"id": vid, "content": f"[variant-{vid}]"},
    )
    monkeypatch.setattr("app.db.crud.get_active_prompt", lambda _p: {"content": "[fallback]"})

    content = await orch._load_active_prompt("p1", session_id="s1")
    assert content == "[variant-pv-variant]"
    assert called == {"project_id": "p1", "session_id": "s1"}


@pytest.mark.asyncio
async def test_load_active_prompt_without_session_skips_ab(monkeypatch):
    orch = AgentOrchestrator()

    async def should_not_call(*_a, **_kw):
        raise AssertionError("pick_variant should not fire without session_id")

    monkeypatch.setattr("app.core.ab_test.service.ab_test_service.pick_variant", should_not_call)
    monkeypatch.setattr("app.db.crud.get_active_prompt", lambda _p: {"content": "[fallback]"})

    content = await orch._load_active_prompt("p1")
    assert content == "[fallback]"


@pytest.mark.asyncio
async def test_load_active_prompt_handles_ab_pick_exception(monkeypatch):
    orch = AgentOrchestrator()

    async def boom(*_a, **_kw):
        raise RuntimeError("db down")

    monkeypatch.setattr("app.core.ab_test.service.ab_test_service.pick_variant", boom)
    monkeypatch.setattr("app.db.crud.get_active_prompt", lambda _p: {"content": "[safe]"})
    content = await orch._load_active_prompt("p1", session_id="s1")
    assert content == "[safe]"


# -------------------------------------------------------------------
# Capability action_type=handoff dispatches to HandoffService
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_capability_handoff_triggers_handoff_service(monkeypatch):
    from app.models.schemas import ChatRequest

    orch = AgentOrchestrator()

    called = {}

    async def fake_request(session_id, reason, triggered_by="system", urgency="normal"):
        called.update(session_id=session_id, reason=reason, triggered_by=triggered_by, urgency=urgency)
        return {
            "status": "handoff_requested",
            "handoff_message_id": "h1",
            "urgency": urgency,
            "notified": True,
        }

    monkeypatch.setattr("app.core.handoff.service.handoff_service.request", fake_request)
    monkeypatch.setattr("app.db.crud.create_message", lambda **kw: {"id": "m1", **kw})

    intent = {
        "type": "capability_rule",
        "rule": {
            "id": "rule-1",
            "action_type": "handoff",
            "action_config": {
                "reason": "angry user",
                "urgency": "high",
                "text": "已轉接真人客服。",
            },
        },
    }
    req = ChatRequest(project_id="p1", session_id="s1", user_id="u1", message="要真人")
    result = await orch._execute_capability(intent, req, "s1", [])

    assert called["session_id"] == "s1"
    assert called["urgency"] == "high"
    assert called["triggered_by"] == "capability_rule"
    assert result.metadata["handoff"] is True
    assert result.metadata["handoff_message_id"] == "h1"
    assert result.message.content.startswith("已轉接")


# -------------------------------------------------------------------
# Workflow tool_call propagates tenant_id / user_id for audit log
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workflow_default_executor_passes_tenant_to_tool_registry(monkeypatch):
    from app.core.workflows.engine import _default_action_executor

    seen = {}

    async def fake_execute(tool_id, params=None, tenant_id=None, user_id=None, **_kw):
        seen.update(tool_id=tool_id, tenant_id=tenant_id, user_id=user_id, params=params)
        return {"status": "success", "data": {"ok": True}}

    monkeypatch.setattr(
        "app.core.tools.registry.tool_registry.execute_tool",
        fake_execute,
    )

    step = {"kind": "tool_call", "tool_id": "tool-xyz", "params": {"foo": 1}}
    ctx = {"_context": {"tenant_id": "t-abc", "user_id": "u-def"}}
    result = await _default_action_executor(step, ctx)
    assert result["status"] == "success"
    assert seen["tool_id"] == "tool-xyz"
    assert seen["tenant_id"] == "t-abc"
    assert seen["user_id"] == "u-def"
    assert seen["params"] == {"foo": 1}


@pytest.mark.asyncio
async def test_workflow_run_to_completion_resolves_tenant_from_project(monkeypatch):
    from app.core.workflows.engine import WorkflowEngine

    captured_exec: dict = {}

    async def recorder(step, ctx):
        # Capture the merged exec context's enclosing _context
        captured_exec.update(ctx.get("_context") or {})
        return {"status": "success"}

    engine = WorkflowEngine(action_executor=recorder)
    monkeypatch.setattr(
        "app.db.crud.get_workflow",
        lambda _w: {"id": "w1", "project_id": "p1", "steps_json": [{"id": "s1", "type": "action"}]},
    )
    monkeypatch.setattr(
        "app.db.crud.get_project",
        lambda _p: {"id": "p1", "tenant_id": "tenant-42"},
    )
    monkeypatch.setattr("app.db.crud.create_workflow_run", lambda *a, **kw: {"id": "run-1"})
    monkeypatch.setattr("app.db.crud.update_workflow_run", lambda *a, **kw: None)

    result = await engine.run_to_completion("w1", session_id="sess", user_id="user")
    assert result["status"] == "completed"
    assert captured_exec.get("tenant_id") == "tenant-42"
    assert captured_exec.get("user_id") == "user"
    assert captured_exec.get("session_id") == "sess"


# -------------------------------------------------------------------
# _search_knowledge walks rag_pipeline first, falls back to keyword
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_knowledge_uses_rag_pipeline_when_available(monkeypatch):
    orch = AgentOrchestrator()

    async def fake_search(project_id, query, top_k=5):
        return [{"content": "chunk-A", "similarity": 0.9}, {"content": "chunk-B"}]

    monkeypatch.setattr("app.core.rag.pipeline.rag_pipeline.search", fake_search)

    def should_not_call(*_a, **_kw):
        raise AssertionError("keyword fallback must not run when RAG returned hits")

    monkeypatch.setattr("app.db.crud.search_knowledge_chunks", should_not_call)
    context = await orch._search_knowledge("什麼是 GTO", "p1")
    assert "chunk-A" in context
    assert "chunk-B" in context


@pytest.mark.asyncio
async def test_search_knowledge_falls_back_to_keyword(monkeypatch):
    orch = AgentOrchestrator()

    async def fake_search(*_a, **_kw):
        return []

    monkeypatch.setattr("app.core.rag.pipeline.rag_pipeline.search", fake_search)
    monkeypatch.setattr(
        "app.db.crud.search_knowledge_chunks",
        lambda pid, q, limit=5: [{"content": "kw-chunk"}],
    )
    context = await orch._search_knowledge("x", "p1")
    assert context is not None
    assert "kw-chunk" in context


@pytest.mark.asyncio
async def test_search_knowledge_rag_exception_falls_back(monkeypatch):
    orch = AgentOrchestrator()

    async def boom(*_a, **_kw):
        raise RuntimeError("qdrant dead")

    monkeypatch.setattr("app.core.rag.pipeline.rag_pipeline.search", boom)
    monkeypatch.setattr(
        "app.db.crud.search_knowledge_chunks",
        lambda pid, q, limit=5: [{"content": "safe"}],
    )
    context = await orch._search_knowledge("x", "p1")
    assert "safe" in (context or "")
