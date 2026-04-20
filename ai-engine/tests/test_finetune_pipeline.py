"""Tests for Fine-tune pipeline (data prep + provider submission logic)."""
from __future__ import annotations

import json
import pytest

from app.core.finetune.pipeline import FineTunePipeline, FineTuneSubmitError


@pytest.fixture
def pipeline():
    return FineTunePipeline()


@pytest.mark.asyncio
async def test_clean_training_data_filters_short_and_dedups(pipeline):
    pairs = [
        {"user_message": "hi", "assistant_message": "hello"},          # too short
        {"user_message": "good Q", "assistant_message": "long enough answer here"},
        {"user_message": "good Q", "assistant_message": "duplicate"},  # dup by user
        {"user_message": "", "assistant_message": "x" * 50},           # empty user
        {"user_message": "another", "assistant_message": "x" * 20},
    ]
    cleaned = await pipeline.clean_training_data(pairs)
    assert len(cleaned) == 2


@pytest.mark.asyncio
async def test_export_jsonl_openai_format(pipeline, monkeypatch):
    monkeypatch.setattr(
        pipeline, "extract_training_data",
        lambda _pid: _async_return([{"user_message": "q1", "assistant_message": "a1" * 10}]),
    )
    monkeypatch.setattr(
        "app.db.crud.get_active_prompt",
        lambda _pid: {"content": "SYS"},
    )
    jsonl = await pipeline.export_jsonl("p1", format="openai")
    line = json.loads(jsonl.splitlines()[0])
    assert line["messages"][0]["role"] == "system"
    assert line["messages"][0]["content"] == "SYS"


@pytest.mark.asyncio
async def test_export_jsonl_anthropic_format(pipeline, monkeypatch):
    monkeypatch.setattr(
        pipeline, "extract_training_data",
        lambda _pid: _async_return([{"user_message": "q", "assistant_message": "x" * 20}]),
    )
    monkeypatch.setattr("app.db.crud.get_active_prompt", lambda _pid: None)
    jsonl = await pipeline.export_jsonl("p1", format="anthropic")
    line = json.loads(jsonl.splitlines()[0])
    assert "system" in line
    assert line["messages"][0]["role"] == "user"


@pytest.mark.asyncio
async def test_create_job_rejects_insufficient_data(pipeline, monkeypatch):
    monkeypatch.setattr(
        pipeline, "extract_training_data",
        lambda _pid: _async_return([{"user_message": "x", "assistant_message": "x" * 20}]),
    )
    result = await pipeline.create_job("p1", "openai", "gpt-4o-mini")
    assert result["status"] == "error"
    assert "Not enough" in result["message"]


@pytest.mark.asyncio
async def test_submit_openai_without_key_raises(pipeline, monkeypatch):
    monkeypatch.setattr("app.core.finetune.pipeline.settings.openai_api_key", "", raising=False)
    with pytest.raises(FineTuneSubmitError):
        await pipeline._submit_openai("gpt-4o-mini", "{}")


@pytest.mark.asyncio
async def test_anthropic_returns_not_available(pipeline, monkeypatch):
    # Patch data pipeline
    many_pairs = [{"user_message": f"q{i}", "assistant_message": "x" * 20} for i in range(15)]
    monkeypatch.setattr(pipeline, "extract_training_data", lambda _p: _async_return(many_pairs))
    monkeypatch.setattr("app.db.crud.get_active_prompt", lambda _p: None)
    monkeypatch.setattr("app.db.crud.create_finetune_job", lambda *a, **k: {"id": "j1"})
    monkeypatch.setattr("app.db.crud.update_finetune_job", lambda *a, **k: None)

    result = await pipeline.create_job("p1", "anthropic", "claude-3-5-haiku")
    assert result["status"] == "not_available"


# helper for monkeypatched async fns
async def _async_return(value):
    return value
