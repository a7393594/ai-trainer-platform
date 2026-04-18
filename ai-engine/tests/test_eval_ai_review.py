"""Tests for eval AI-review flow."""
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
async def test_judge_with_model_parses_json(monkeypatch):
    engine = EvalEngine()

    async def fake_chat(**_kw):
        return _FakeResp('{"score": 92, "passed": true, "reason": "ok"}')

    monkeypatch.setattr("app.core.eval.engine.chat_completion", fake_chat)
    score, passed, reason = await engine._judge_with_model("q", "e", "a", "claude-opus")
    assert score == 92 and passed is True and reason == "ok"


@pytest.mark.asyncio
async def test_judge_with_model_handles_malformed(monkeypatch):
    engine = EvalEngine()

    async def fake_chat(**_kw):
        return _FakeResp("not-json-at-all")

    monkeypatch.setattr("app.core.eval.engine.chat_completion", fake_chat)
    score, passed, _ = await engine._judge_with_model("q", "e", "a", "m")
    assert 0 <= score <= 100
    assert isinstance(passed, bool)


@pytest.mark.asyncio
async def test_ai_review_run_aggregates_scores(monkeypatch):
    engine = EvalEngine()

    # Fake DB: 2 results, each with test_case
    fake_details = {
        "results": [
            {
                "id": "r1", "test_case_id": "tc1",
                "test_case": {"input_text": "q1", "expected_output": "e1"},
                "actual_output": "a1", "score": 50, "passed": False, "details": {},
            },
            {
                "id": "r2", "test_case_id": "tc2",
                "test_case": {"input_text": "q2", "expected_output": "e2"},
                "actual_output": "a2", "score": 40, "passed": False, "details": {},
            },
        ]
    }
    monkeypatch.setattr("app.db.crud.get_eval_run", lambda _r: {"id": "run-1"})
    monkeypatch.setattr("app.db.crud.get_eval_run_details", lambda _r: fake_details)

    captured_updates = []
    monkeypatch.setattr(
        "app.db.crud.update_eval_result",
        lambda **kw: captured_updates.append(kw),
    )
    monkeypatch.setattr("app.db.crud.update_eval_run_scores", lambda **_kw: None)

    async def fake_chat(**_kw):
        return _FakeResp('{"score": 88, "passed": true, "reason": "good"}')

    monkeypatch.setattr("app.core.eval.engine.chat_completion", fake_chat)

    result = await engine.ai_review_run("run-1", judge_model="claude-opus-4-20250514")
    assert result["status"] == "completed"
    assert result["reviewed"] == 2
    assert result["updated_score"] == 88
    assert result["passed_count"] == 2
    assert len(captured_updates) == 2
    assert captured_updates[0]["score"] == 88
