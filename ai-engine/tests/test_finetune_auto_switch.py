"""Tests for fine-tune auto-switch of project.default_model on success."""
from __future__ import annotations

import pytest

from app.core.finetune.pipeline import FineTunePipeline


@pytest.mark.asyncio
async def test_poll_job_succeeded_auto_switches_default_model(monkeypatch):
    pipeline = FineTunePipeline()

    # Fake running job with external id
    job = {
        "id": "j1", "project_id": "p1", "provider": "openai",
        "model_base": "gpt-4o-mini", "status": "running",
        "result_model_id": "ftjob-xxx",
    }
    monkeypatch.setattr("app.db.crud.get_finetune_job", lambda _j: dict(job))

    captured = {}

    def fake_update_job(job_id, **kw):
        captured["job_update"] = {"id": job_id, **kw}
        # Simulate DB state transition
        job["status"] = kw.get("status", job["status"])
        if "result_model_id" in kw:
            job["result_model_id"] = kw["result_model_id"]

    monkeypatch.setattr("app.db.crud.update_finetune_job", fake_update_job)

    # Old project default
    monkeypatch.setattr("app.db.crud.get_project", lambda _p: {"id": "p1", "default_model": "gpt-4o-mini"})

    def fake_switch(pid, model):
        captured["switched"] = {"project_id": pid, "model": model}
        return {"id": pid, "default_model": model}

    monkeypatch.setattr("app.db.crud.update_project_default_model", fake_switch)

    async def fake_poll_openai(_external_id):
        return {
            "status": "succeeded",
            "fine_tuned_model": "ft:gpt-4o-mini:org::zzz",
        }

    monkeypatch.setattr(pipeline, "_poll_openai", fake_poll_openai)

    result = await pipeline.poll_job("j1")
    assert result["status"] == "succeeded"
    assert result["auto_switched"] is True
    assert result["switched_from"] == "gpt-4o-mini"
    assert result["switched_to"] == "ft:gpt-4o-mini:org::zzz"
    assert captured["switched"]["model"] == "ft:gpt-4o-mini:org::zzz"
    assert captured["job_update"]["status"] == "completed"


@pytest.mark.asyncio
async def test_poll_job_auto_switch_can_be_disabled(monkeypatch):
    pipeline = FineTunePipeline()
    job = {
        "id": "j1", "project_id": "p1", "provider": "openai",
        "status": "running", "result_model_id": "ftjob-xxx",
    }
    monkeypatch.setattr("app.db.crud.get_finetune_job", lambda _j: dict(job))
    monkeypatch.setattr("app.db.crud.update_finetune_job", lambda *a, **k: None)

    called = {"n": 0}

    def fake_switch(*_a, **_kw):
        called["n"] += 1

    monkeypatch.setattr("app.db.crud.update_project_default_model", fake_switch)
    monkeypatch.setattr("app.db.crud.get_project", lambda _p: {"default_model": "m"})

    async def fake_poll(_x):
        return {"status": "succeeded", "fine_tuned_model": "ft:new"}

    monkeypatch.setattr(pipeline, "_poll_openai", fake_poll)

    result = await pipeline.poll_job("j1", auto_switch=False)
    assert result["auto_switched"] is False
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_poll_job_failed_marks_failed(monkeypatch):
    pipeline = FineTunePipeline()
    job = {
        "id": "j1", "project_id": "p1", "provider": "openai",
        "status": "running", "result_model_id": "ftjob-xxx",
    }
    monkeypatch.setattr("app.db.crud.get_finetune_job", lambda _j: dict(job))

    captured = {}
    monkeypatch.setattr("app.db.crud.update_finetune_job", lambda jid, **kw: captured.update(kw))

    async def fake_poll(_x):
        return {"status": "failed", "error": "bad data"}

    monkeypatch.setattr(pipeline, "_poll_openai", fake_poll)
    result = await pipeline.poll_job("j1")
    assert result["status"] == "failed"
    assert captured.get("status") == "failed"
    assert captured.get("error_message") == "bad data"
