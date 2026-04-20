"""Tests for before/after eval comparison."""
from __future__ import annotations

import pytest

from app.core.eval.engine import EvalEngine


@pytest.mark.asyncio
async def test_before_after_eval_aggregates_deltas(monkeypatch):
    engine = EvalEngine()

    async def fake_run_eval(project_id, model=None, prompt_version_id=None):
        if prompt_version_id == "v1":
            return {
                "status": "completed", "run_id": "run-before",
                "total_score": 60,
                "results": [
                    {"test_case_id": "tc1", "input": "Q1", "score": 50, "passed": False},
                    {"test_case_id": "tc2", "input": "Q2", "score": 70, "passed": True},
                ],
            }
        return {
            "status": "completed", "run_id": "run-after",
            "total_score": 75,
            "results": [
                {"test_case_id": "tc1", "input": "Q1", "score": 80, "passed": True},
                {"test_case_id": "tc2", "input": "Q2", "score": 70, "passed": True},
            ],
        }

    monkeypatch.setattr(engine, "run_eval", fake_run_eval)

    result = await engine.before_after_eval("p1", "v1", "v2")
    assert result["status"] == "completed"
    assert result["before_score"] == 60
    assert result["after_score"] == 75
    assert result["overall_delta"] == 15
    assert result["improved"] == 1
    assert result["regressed"] == 0
    assert result["unchanged"] == 1
    # deltas sorted ascending; lowest (unchanged 0) comes first
    assert result["deltas"][0]["delta"] == 0
    assert result["deltas"][-1]["delta"] == 30


@pytest.mark.asyncio
async def test_before_after_returns_incomplete_when_one_side_fails(monkeypatch):
    engine = EvalEngine()

    async def fake_run_eval(project_id, model=None, prompt_version_id=None):
        if prompt_version_id == "v_bad":
            return {"status": "no_prompt", "message": "Prompt version not found"}
        return {"status": "completed", "run_id": "ok", "total_score": 80, "results": []}

    monkeypatch.setattr(engine, "run_eval", fake_run_eval)

    result = await engine.before_after_eval("p1", "v_bad", "v_ok")
    assert result["status"] == "incomplete"
    assert result["before"]["status"] == "no_prompt"
