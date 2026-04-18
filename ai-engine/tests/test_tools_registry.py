"""Tests for Tools Registry execution layer."""
from __future__ import annotations

import pytest

from app.core.tools.registry import (
    ToolRegistry,
    _apply_auth,
    _check_rate_limit,
    _parse_rate_limit,
    _rate_buckets,
    register_internal_fn,
)


# ---------- rate limit ----------

def test_parse_rate_limit_valid():
    assert _parse_rate_limit("5/s") == (5, 1)
    assert _parse_rate_limit("10/m") == (10, 60)
    assert _parse_rate_limit("100/h") == (100, 3600)


def test_parse_rate_limit_invalid():
    assert _parse_rate_limit(None) is None
    assert _parse_rate_limit("") is None
    assert _parse_rate_limit("bad") is None
    assert _parse_rate_limit("5/x") is None
    assert _parse_rate_limit("0/s") is None


@pytest.mark.asyncio
async def test_rate_limit_sliding_window():
    _rate_buckets.pop("tool-rl", None)
    ok1 = await _check_rate_limit("tool-rl", "2/s")
    ok2 = await _check_rate_limit("tool-rl", "2/s")
    ok3 = await _check_rate_limit("tool-rl", "2/s")
    assert ok1 and ok2 and not ok3


# ---------- auth ----------

def test_apply_auth_bearer():
    headers = _apply_auth({}, {"type": "bearer", "token": "abc"})
    assert headers["Authorization"] == "Bearer abc"


def test_apply_auth_api_key_custom_header():
    headers = _apply_auth({}, {"type": "api_key", "header": "X-Key", "key": "zzz"})
    assert headers["X-Key"] == "zzz"


def test_apply_auth_basic():
    headers = _apply_auth({}, {"type": "basic", "username": "u", "password": "p"})
    assert headers["Authorization"].startswith("Basic ")


def test_apply_auth_none():
    assert _apply_auth({"X": "1"}, {}) == {"X": "1"}


# ---------- internal fn ----------

@pytest.mark.asyncio
async def test_builtin_echo_and_math_add():
    reg = ToolRegistry()
    result = await reg._execute_internal_fn(
        {"config_json": {"fn": "math.add"}}, {"a": 2, "b": 3}
    )
    assert result["status"] == "success"
    assert result["data"]["result"] == 5


@pytest.mark.asyncio
async def test_internal_fn_unknown_name_returns_error():
    reg = ToolRegistry()
    result = await reg._execute_internal_fn(
        {"config_json": {"fn": "does_not_exist"}}, {}
    )
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_internal_fn_custom_registration():
    @register_internal_fn("test.double")
    async def _double(p):
        return p.get("n", 0) * 2

    reg = ToolRegistry()
    result = await reg._execute_internal_fn(
        {"config_json": {"fn": "test.double"}}, {"n": 7}
    )
    assert result["data"] == 14


# ---------- db_query guardrails ----------

@pytest.mark.asyncio
async def test_db_query_rejects_unknown_table():
    reg = ToolRegistry()
    result = await reg._execute_db_query({"config_json": {"table": "secret_table"}}, {})
    assert result["status"] == "error"
    assert "not allowed" in result["detail"]


@pytest.mark.asyncio
async def test_db_query_rejects_unknown_column(monkeypatch):
    reg = ToolRegistry()
    result = await reg._execute_db_query(
        {"config_json": {"table": "ait_projects", "select": ["password"]}}, {}
    )
    assert result["status"] == "error"


# ---------- mcp ----------

@pytest.mark.asyncio
async def test_mcp_requires_server_url():
    reg = ToolRegistry()
    result = await reg._execute_mcp_server({"config_json": {}}, {})
    assert result["status"] == "error"


# ---------- dry-run ----------

@pytest.mark.asyncio
async def test_execute_tool_dry_run(monkeypatch):
    reg = ToolRegistry()
    tool = {"id": "t1", "name": "noop", "tool_type": "api_call", "is_active": True}
    monkeypatch.setattr("app.db.crud.get_tool", lambda _id: tool)
    result = await reg.execute_tool("t1", params={"a": 1}, dry_run=True)
    assert result["status"] == "dry_run"
    assert result["tool"] == "noop"


@pytest.mark.asyncio
async def test_execute_tool_missing_returns_error(monkeypatch):
    reg = ToolRegistry()
    monkeypatch.setattr("app.db.crud.get_tool", lambda _id: None)
    result = await reg.execute_tool("x", dry_run=True)
    assert result["status"] == "error"
    assert "not found" in result["detail"].lower()
