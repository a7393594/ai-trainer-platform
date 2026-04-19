"""Tests for Eval gap clustering."""
from __future__ import annotations

import pytest

from app.core.eval.engine import EvalEngine


class _FakeChoice:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class _FakeResp:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


@pytest.mark.asyncio
async def test_cluster_gaps_empty_when_no_failures(monkeypatch):
    engine = EvalEngine()
    fake_details = {
        "results": [
            {"id": "r1", "passed": True, "actual_output": "ok"},
        ]
    }
    monkeypatch.setattr("app.db.crud.get_eval_run_details", lambda _r: fake_details)
    result = await engine.cluster_gaps("run-1")
    assert result["failure_count"] == 0
    assert result["clusters"] == []


@pytest.mark.asyncio
async def test_cluster_gaps_parses_json(monkeypatch):
    engine = EvalEngine()
    fake_details = {
        "results": [
            {
                "id": "r1", "passed": False, "actual_output": "wrong",
                "test_case": {"input_text": "Q1", "expected_output": "E1", "category": "accuracy"},
            },
            {
                "id": "r2", "passed": False, "actual_output": "bad",
                "test_case": {"input_text": "Q2", "expected_output": "E2", "category": "tone"},
            },
        ]
    }
    monkeypatch.setattr("app.db.crud.get_eval_run_details", lambda _r: fake_details)

    async def fake_chat(**_kw):
        return _FakeResp(
            '{"clusters":[{"name":"factual","description":"wrong facts",'
            '"test_case_ids":["r1"],"suggestion":"RAG"},'
            '{"name":"tone","description":"tone mismatch",'
            '"test_case_ids":["r2"],"suggestion":"Prompt"}]}'
        )

    monkeypatch.setattr("app.core.eval.engine.chat_completion", fake_chat)
    result = await engine.cluster_gaps("run-1", max_clusters=4)
    assert result["failure_count"] == 2
    assert len(result["clusters"]) == 2
    assert result["clusters"][0]["name"] == "factual"
    assert result["clusters"][0]["suggestion"] == "RAG"


@pytest.mark.asyncio
async def test_cluster_gaps_handles_malformed_response(monkeypatch):
    engine = EvalEngine()
    fake_details = {
        "results": [{"id": "r1", "passed": False, "actual_output": "x", "test_case": {}}]
    }
    monkeypatch.setattr("app.db.crud.get_eval_run_details", lambda _r: fake_details)

    async def fake_chat(**_kw):
        return _FakeResp("not json")

    monkeypatch.setattr("app.core.eval.engine.chat_completion", fake_chat)
    result = await engine.cluster_gaps("run-1")
    assert result["failure_count"] == 1
    assert result["clusters"] == []
