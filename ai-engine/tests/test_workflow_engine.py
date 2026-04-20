"""Tests for Workflow Engine conditional branching, parallel, loop."""
from __future__ import annotations

import pytest

from app.core.workflows.engine import WorkflowEngine, WorkflowError, _eval_condition


# ---------- safe condition eval ----------

def test_eval_condition_true():
    assert _eval_condition("x > 2", {"x": 5}) is True


def test_eval_condition_false():
    assert _eval_condition("x > 2", {"x": 1}) is False


def test_eval_condition_blocks_imports():
    assert _eval_condition("__import__('os')", {}) is False


def test_eval_condition_blocks_exec():
    assert _eval_condition("exec('print(1)')", {}) is False


def test_eval_condition_handles_bool_literal():
    assert _eval_condition(True, {}) is True
    assert _eval_condition(False, {}) is False


def test_eval_condition_handles_missing_var():
    assert _eval_condition("nope == 1", {}) is False


# ---------- engine ----------

@pytest.fixture
def engine():
    async def recorder_executor(step, ctx):
        # Record side-effects on shared list and write output
        return {"status": "success", "kind": step.get("kind", "noop"), "params": step.get("params", {})}
    return WorkflowEngine(action_executor=recorder_executor)


@pytest.mark.asyncio
async def test_run_linear_action_chain(engine):
    context = {"vars": {"counter": 0}, "_step_count": 0, "_trace": []}
    steps = [
        {"id": "a", "type": "action", "kind": "set", "output_var": "r1"},
        {"id": "b", "type": "action", "kind": "set", "output_var": "r2"},
    ]
    await engine._run_steps(steps, context)
    assert "r1" in context["vars"]
    assert "r2" in context["vars"]


@pytest.mark.asyncio
async def test_run_if_then_branch(engine):
    context = {"vars": {"x": 10}, "_step_count": 0, "_trace": []}
    steps = [{
        "id": "cond", "type": "if", "condition": "x > 5",
        "then": [{"id": "t", "type": "action", "output_var": "taken"}],
        "else": [{"id": "e", "type": "action", "output_var": "skipped"}],
    }]
    await engine._run_steps(steps, context)
    assert "taken" in context["vars"]
    assert "skipped" not in context["vars"]


@pytest.mark.asyncio
async def test_run_if_else_branch(engine):
    context = {"vars": {"x": 1}, "_step_count": 0, "_trace": []}
    steps = [{
        "id": "cond", "type": "if", "condition": "x > 5",
        "then": [{"id": "t", "type": "action", "output_var": "taken"}],
        "else": [{"id": "e", "type": "action", "output_var": "skipped"}],
    }]
    await engine._run_steps(steps, context)
    assert "skipped" in context["vars"]
    assert "taken" not in context["vars"]


@pytest.mark.asyncio
async def test_run_parallel_merges_vars(engine):
    context = {"vars": {}, "_step_count": 0, "_trace": []}
    steps = [{
        "id": "p", "type": "parallel",
        "branches": [
            [{"id": "b1", "type": "action", "output_var": "a"}],
            [{"id": "b2", "type": "action", "output_var": "b"}],
        ],
    }]
    await engine._run_steps(steps, context)
    assert "a" in context["vars"]
    assert "b" in context["vars"]


@pytest.mark.asyncio
async def test_run_loop_foreach(engine):
    context = {"vars": {"items": ["x", "y", "z"]}, "_step_count": 0, "_trace": []}
    steps = [{
        "id": "l", "type": "loop", "mode": "foreach",
        "items_var": "items", "item_var": "it",
        "body": [{"id": "a", "type": "action", "output_var": "last"}],
    }]
    await engine._run_steps(steps, context)
    # 最後 iteration 的 it 變數應為 'z'
    assert context["vars"]["it"] == "z"


@pytest.mark.asyncio
async def test_run_loop_while_respects_max(engine):
    context = {"vars": {"n": 0}, "_step_count": 0, "_trace": []}
    steps = [{
        "id": "w", "type": "loop", "mode": "while",
        "condition": "True",  # 無限迴圈，應被 max_iterations 截斷
        "max_iterations": 3,
        "body": [{"id": "a", "type": "action"}],
    }]
    await engine._run_steps(steps, context)
    # _loop_i 應為 2 (0,1,2)
    assert context["vars"]["_loop_i"] == 2


@pytest.mark.asyncio
async def test_unknown_step_type_raises(engine):
    context = {"vars": {}, "_step_count": 0, "_trace": []}
    with pytest.raises(WorkflowError):
        await engine._run_step({"id": "bad", "type": "zzz"}, context)
