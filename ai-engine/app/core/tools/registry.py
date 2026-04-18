"""
Tool Registry — 註冊與執行外部工具

支援五種執行器：
  - api_call     : HTTP API（任意方法、auth、URL 模板）
  - webhook      : POST webhook（firing-and-forget 式）
  - db_query     : 受限 Supabase 查詢（白名單 table + 欄位/過濾）
  - internal_fn  : 內建 Python 函數（白名單）
  - mcp_server   : MCP 伺服器代理（HTTP JSON-RPC 2.0）

通用能力：
  - 認證自動注入（bearer / api_key / basic）
  - 速率限制（in-memory sliding window，格式 "N/unit"，unit ∈ {s,m,h}）
  - Audit log 寫入
  - Pipeline Studio span 記錄
"""
from __future__ import annotations

import time
import base64
import asyncio
from collections import deque
from typing import Any, Awaitable, Callable

import httpx

from app.db import crud


# ============================================
# 速率限制（in-memory sliding window）
# ============================================

_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600}
_rate_buckets: dict[str, deque[float]] = {}
_rate_lock = asyncio.Lock()


def _parse_rate_limit(spec: str | None) -> tuple[int, int] | None:
    """解析 'N/unit' → (max_calls, window_seconds)。None / 不合法時回 None。"""
    if not spec:
        return None
    try:
        count_str, unit = spec.split("/")
        count = int(count_str.strip())
        unit = unit.strip().lower()
        window = _UNIT_SECONDS.get(unit[0] if unit else "")
        if not window or count <= 0:
            return None
        return count, window
    except (ValueError, AttributeError):
        return None


async def _check_rate_limit(tool_id: str, spec: str | None) -> bool:
    """True=通過，False=超限。"""
    parsed = _parse_rate_limit(spec)
    if not parsed:
        return True
    max_calls, window = parsed
    now = time.time()
    async with _rate_lock:
        bucket = _rate_buckets.setdefault(tool_id, deque())
        cutoff = now - window
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= max_calls:
            return False
        bucket.append(now)
        return True


# ============================================
# 認證注入
# ============================================

def _apply_auth(headers: dict, auth_config: dict) -> dict:
    """把 auth_config 套用到 headers。支援 bearer / api_key / basic。"""
    if not auth_config:
        return headers
    auth_type = (auth_config.get("type") or "").lower()
    headers = dict(headers)

    if auth_type == "bearer":
        token = auth_config.get("token", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    elif auth_type == "api_key":
        header_name = auth_config.get("header", "X-API-Key")
        key = auth_config.get("key", "")
        if key:
            headers[header_name] = key
    elif auth_type == "basic":
        user = auth_config.get("username", "")
        pwd = auth_config.get("password", "")
        token = base64.b64encode(f"{user}:{pwd}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    return headers


# ============================================
# Internal Function 白名單
# ============================================

InternalFn = Callable[[dict], Awaitable[Any] | Any]
_INTERNAL_FN_REGISTRY: dict[str, InternalFn] = {}


def register_internal_fn(name: str):
    """裝飾器：把函數註冊成可供 internal_fn 工具呼叫。"""

    def wrapper(fn: InternalFn) -> InternalFn:
        _INTERNAL_FN_REGISTRY[name] = fn
        return fn

    return wrapper


@register_internal_fn("echo")
async def _builtin_echo(params: dict) -> dict:
    return {"echo": params}


@register_internal_fn("now")
async def _builtin_now(_: dict) -> dict:
    from datetime import datetime, timezone

    return {"iso": datetime.now(tz=timezone.utc).isoformat()}


@register_internal_fn("math.add")
async def _builtin_add(params: dict) -> dict:
    try:
        a = float(params.get("a", 0))
        b = float(params.get("b", 0))
        return {"result": a + b}
    except (TypeError, ValueError):
        return {"error": "a,b must be numeric"}


# ============================================
# DB Query 白名單
# ============================================

# 僅允許使用者明確授權的 table；每個 table 可再限制欄位。
_ALLOWED_DB_TABLES = {
    "ait_projects": {"id", "name", "description", "project_type", "status", "created_at"},
    "ait_training_sessions": {"id", "project_id", "session_type", "created_at", "ended_at"},
    "ait_prompt_versions": {"id", "project_id", "version", "is_active", "eval_score"},
    "ait_eval_runs": {"id", "project_id", "total_score", "passed_count", "failed_count", "run_at"},
}


# ============================================
# Registry
# ============================================

class ToolRegistry:

    async def register_tool(
        self,
        tenant_id: str,
        name: str,
        description: str,
        tool_type: str,
        config_json: dict,
        auth_config: dict | None = None,
        permissions: list | None = None,
        rate_limit: str | None = None,
    ) -> dict:
        return crud.create_tool(
            tenant_id=tenant_id,
            name=name,
            description=description,
            tool_type=tool_type,
            config_json=config_json,
            auth_config=auth_config or {},
            permissions=permissions or ["admin", "trainer"],
            rate_limit=rate_limit,
        )

    async def execute_tool(
        self,
        tool_id: str,
        params: dict | None = None,
        dry_run: bool = False,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict:
        tool = crud.get_tool(tool_id)
        if not tool:
            return {"status": "error", "detail": "Tool not found"}
        if not tool.get("is_active"):
            return {"status": "error", "detail": "Tool is inactive"}

        params = params or {}
        start = time.time()

        # Rate limit（僅對真正執行的呼叫生效）
        if not dry_run and not await _check_rate_limit(tool_id, tool.get("rate_limit")):
            result = {"status": "error", "detail": "Rate limit exceeded"}
            self._audit(tenant_id, user_id, tool_id, params, result, start, dry_run)
            return result

        tool_type = tool.get("tool_type", "")
        try:
            if dry_run:
                result = {"status": "dry_run", "tool": tool["name"], "tool_type": tool_type, "params": params}
            elif tool_type == "api_call":
                result = await self._execute_api_call(tool, params)
            elif tool_type == "webhook":
                result = await self._execute_webhook(tool, params)
            elif tool_type == "db_query":
                result = await self._execute_db_query(tool, params)
            elif tool_type == "internal_fn":
                result = await self._execute_internal_fn(tool, params)
            elif tool_type == "mcp_server":
                result = await self._execute_mcp_server(tool, params)
            else:
                result = {"status": "error", "detail": f"Unsupported type: {tool_type}"}
        except Exception as e:
            result = {"status": "error", "detail": str(e)}

        self._audit(tenant_id, user_id, tool_id, params, result, start, dry_run)
        return result

    # --------------------------------------------
    # Audit
    # --------------------------------------------

    @staticmethod
    def _audit(
        tenant_id: str | None,
        user_id: str | None,
        tool_id: str,
        params: dict,
        result: dict,
        start: float,
        dry_run: bool,
    ) -> None:
        if not tenant_id:
            return
        duration = int((time.time() - start) * 1000)
        status = "dry_run" if dry_run else ("success" if result.get("status") != "error" else "error")
        try:
            crud.create_audit_log(
                tenant_id=tenant_id,
                user_id=user_id,
                action_type="tool_call",
                tool_id=tool_id,
                request_data=params,
                response_data=result,
                status=status,
                duration_ms=duration,
            )
        except Exception:
            pass  # 稽核失敗不應阻斷工具執行

    # --------------------------------------------
    # 執行器
    # --------------------------------------------

    async def _execute_api_call(self, tool: dict, params: dict) -> dict:
        config = tool.get("config_json", {}) or {}
        method = (config.get("method") or "GET").upper()
        url = config.get("url", "")
        headers = _apply_auth(config.get("headers", {}) or {}, tool.get("auth_config") or {})
        timeout = float(config.get("timeout", 30))

        # Template URL params（{key} → value）
        for key, val in params.items():
            url = url.replace(f"{{{key}}}", str(val))

        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers, params=params)
            else:
                resp = await client.request(method, url, headers=headers, json=params)

        body = resp.text[:4000]
        try:
            data: Any = resp.json()
        except Exception:
            data = body

        ok = 200 <= resp.status_code < 300
        return {
            "status": "success" if ok else "error",
            "status_code": resp.status_code,
            "data": data,
            "detail": None if ok else body,
        }

    async def _execute_webhook(self, tool: dict, params: dict) -> dict:
        config = tool.get("config_json", {}) or {}
        url = config.get("url", "")
        headers = _apply_auth(config.get("headers", {}) or {}, tool.get("auth_config") or {})
        timeout = float(config.get("timeout", 15))

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=headers, json=params)

        ok = 200 <= resp.status_code < 300
        return {
            "status": "success" if ok else "error",
            "status_code": resp.status_code,
            "detail": None if ok else resp.text[:2000],
        }

    async def _execute_db_query(self, tool: dict, params: dict) -> dict:
        """受限 Supabase 查詢。

        config_json schema:
          { "table": "ait_projects",
            "select": ["id","name"],            # 欄位（必須在白名單）
            "filters": [["tenant_id","eq","{tenant_id}"]],
            "order": {"column":"created_at","desc":true},
            "limit": 50 }
        """
        from app.db.supabase import get_supabase

        config = tool.get("config_json", {}) or {}
        table = config.get("table")
        if table not in _ALLOWED_DB_TABLES:
            return {"status": "error", "detail": f"Table '{table}' not allowed"}

        allowed_cols = _ALLOWED_DB_TABLES[table]
        select_cols = config.get("select") or list(allowed_cols)
        bad = [c for c in select_cols if c not in allowed_cols and c != "*"]
        if bad:
            return {"status": "error", "detail": f"Columns not allowed: {bad}"}

        select_clause = "*" if "*" in select_cols else ",".join(select_cols)
        query = get_supabase().table(table).select(select_clause)

        # 過濾器（欄位/運算子白名單）
        allowed_ops = {"eq", "neq", "gt", "gte", "lt", "lte", "like", "ilike", "in_"}
        for flt in config.get("filters", []) or []:
            if not (isinstance(flt, (list, tuple)) and len(flt) == 3):
                continue
            col, op, val = flt
            if col not in allowed_cols or op not in allowed_ops:
                return {"status": "error", "detail": f"Filter not allowed: {col}/{op}"}
            if isinstance(val, str):
                val = val.format(**params) if "{" in val else val
            query = getattr(query, op)(col, val)

        # 排序
        order = config.get("order")
        if isinstance(order, dict) and order.get("column") in allowed_cols:
            query = query.order(order["column"], desc=bool(order.get("desc", False)))

        limit = min(int(config.get("limit", 50)), 500)
        query = query.limit(limit)

        data = query.execute().data
        return {"status": "success", "rows": data, "count": len(data)}

    async def _execute_internal_fn(self, tool: dict, params: dict) -> dict:
        config = tool.get("config_json", {}) or {}
        fn_name = config.get("fn")
        fn = _INTERNAL_FN_REGISTRY.get(fn_name or "")
        if not fn:
            return {"status": "error", "detail": f"Internal fn '{fn_name}' not registered"}

        result = fn(params)
        if asyncio.iscoroutine(result):
            result = await result
        return {"status": "success", "data": result}

    async def _execute_mcp_server(self, tool: dict, params: dict) -> dict:
        """MCP Server 代理（HTTP transport，JSON-RPC 2.0）。

        config_json:
          { "server_url": "https://mcp.example.com/rpc",
            "method": "tools/call",
            "tool_name": "search_docs" }
        """
        config = tool.get("config_json", {}) or {}
        url = config.get("server_url")
        method = config.get("method", "tools/call")
        inner_tool = config.get("tool_name")
        if not url or not inner_tool:
            return {"status": "error", "detail": "server_url and tool_name required"}

        headers = _apply_auth({"Content-Type": "application/json"}, tool.get("auth_config") or {})
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": method,
            "params": {"name": inner_tool, "arguments": params},
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, json=payload)

        try:
            body = resp.json()
        except Exception:
            return {"status": "error", "detail": resp.text[:1000]}

        if "error" in body:
            return {"status": "error", "detail": body["error"]}
        return {"status": "success", "data": body.get("result")}

    # --------------------------------------------
    # 列表 / 測試 / LLM 整合
    # --------------------------------------------

    def convert_to_llm_tools(self, tools: list[dict]) -> list[dict]:
        """轉為 OpenAI/Claude tool-use 格式。"""
        out = []
        for tool in tools:
            config = tool.get("config_json", {}) or {}
            schema = config.get("input_schema") or {"type": "object", "properties": {}, "required": []}
            out.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": schema,
                },
            })
        return out

    async def execute_tool_by_name(
        self,
        name: str,
        params: dict,
        tools: list[dict],
        parent_span_id: str | None = None,
    ) -> dict:
        start = time.time()
        status = "ok"
        error: str | None = None
        result: dict = {}
        try:
            for tool in tools:
                if tool["name"] == name:
                    result = await self.execute_tool(tool["id"], params=params)
                    if isinstance(result, dict) and result.get("status") == "error":
                        status = "error"
                        error = result.get("detail")
                    return result
            result = {"status": "error", "detail": f"Tool '{name}' not found"}
            status = "error"
            error = result["detail"]
            return result
        except Exception as e:
            status = "error"
            error = str(e)
            result = {"status": "error", "detail": error}
            return result
        finally:
            try:
                from app.core.pipeline.tracer import record_tool_span
                latency_ms = int((time.time() - start) * 1000)
                record_tool_span(
                    tool_name=name,
                    params=params or {},
                    result=result,
                    latency_ms=latency_ms,
                    status=status,
                    error=error,
                    parent_id=parent_span_id,
                )
            except Exception:
                pass

    async def list_tools(self, tenant_id: str) -> list[dict]:
        return crud.list_tools(tenant_id)

    async def test_tool(self, tool_id: str, tenant_id: str | None = None) -> dict:
        return await self.execute_tool(tool_id, params={"test": True}, dry_run=True, tenant_id=tenant_id)


tool_registry = ToolRegistry()
