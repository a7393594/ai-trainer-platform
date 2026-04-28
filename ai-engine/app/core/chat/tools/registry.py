"""V4 ToolRegistry — V4 chat 自有的小型工具註冊器。

設計目標：
  - 內建 Python 函數工具直接 register（present_widget / calc_equity / kb_search …）
  - DB 工具（既有 ait_tools 表的 api_call/webhook/db_query/internal_fn/mcp_server）
    透過 legacy `app.core.tools.registry.tool_registry` 橋接，不重新發明
  - 給 chat engine 一個統一介面：list_for_chat() 拿 LLM tool 清單；execute() 執行工具

不動既有 `app.core.tools.registry.ToolRegistry`（DAG / orchestrator 仍依賴它）。

Claude tool format（Anthropic native，相容 OpenAI function format via litellm）：

    {
      "type": "function",
      "function": {
        "name": "<tool_name>",
        "description": "<desc>",
        "parameters": <JSON Schema>,
      },
    }
"""
from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, Optional

from .schemas import BuiltinTool, ToolFn

logger = logging.getLogger(__name__)


class V4ToolRegistry:
    """V4 工具註冊器：支援內建 Python 函數工具 + 既有 DB 工具的橋接。"""

    def __init__(self) -> None:
        self._builtins: dict[str, BuiltinTool] = {}

    # ---------------------------------------------------------------
    # Registration
    # ---------------------------------------------------------------

    def register_builtin(
        self,
        name: str,
        fn: ToolFn,
        schema: dict[str, Any],
        description: str = "",
    ) -> None:
        """註冊一個內建 Python 函數工具。

        重複註冊同名會覆蓋（並 warn）。
        """
        if name in self._builtins:
            logger.warning("[v4_tool_registry] overriding builtin tool %s", name)
        self._builtins[name] = BuiltinTool(
            name=name, fn=fn, schema=schema, description=description,
        )

    def unregister_builtin(self, name: str) -> None:
        self._builtins.pop(name, None)

    def has_builtin(self, name: str) -> bool:
        return name in self._builtins

    def list_builtins(self) -> list[str]:
        return list(self._builtins.keys())

    # ---------------------------------------------------------------
    # Tool listing for LLM
    # ---------------------------------------------------------------

    def list_for_chat(
        self,
        project_id: str,
        subset: Optional[list[str]] = None,
        tenant_id: Optional[str] = None,
        include_db_tools: bool = False,
    ) -> list[dict[str, Any]]:
        """回傳 Claude tool format 的工具清單。

        Args:
            project_id: 專案 ID（保留給後續 per-project 過濾使用）
            subset: 限定只暴露這些工具（依 name 過濾）；None = 全部
            tenant_id: 若提供且 include_db_tools=True，會把 ait_tools 內 active
                tools 一併納入清單
            include_db_tools: Phase 1 預設 False。Phase 3+ 葉子配置如果指定要用
                DB 工具，把這個打開。

        Returns:
            list of {"type": "function", "function": {...}} dicts
        """
        out: list[dict[str, Any]] = []

        # 1) Builtin tools
        for name, tool in self._builtins.items():
            if subset is not None and name not in subset:
                continue
            out.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.schema or {
                        "type": "object", "properties": {}, "required": [],
                    },
                },
            })

        # 2) DB tools via legacy registry (僅在指定 include_db_tools 時)
        if include_db_tools and tenant_id:
            try:
                from app.db import crud
                from app.core.tools.registry import tool_registry as _legacy

                db_tools = crud.list_tools(tenant_id) or []
                # 只取 active
                db_tools = [t for t in db_tools if t.get("is_active")]
                if subset is not None:
                    db_tools = [t for t in db_tools if t.get("name") in subset]
                # 避免與 builtin 同名衝突 — builtin 優先
                builtin_names = set(self._builtins.keys())
                db_tools = [t for t in db_tools if t.get("name") not in builtin_names]
                converted = _legacy.convert_to_llm_tools(db_tools)
                out.extend(converted)
            except Exception as e:  # noqa: BLE001
                logger.warning("[v4_tool_registry] list DB tools failed: %s", e)

        return out

    # ---------------------------------------------------------------
    # Execution
    # ---------------------------------------------------------------

    async def execute(
        self,
        name: str,
        params: dict[str, Any],
        *,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """執行工具。內建直接呼叫 fn，DB 工具走 legacy registry。

        永遠回 dict，外殼為 {"status": "ok"|"error", ...}。
        - 成功：{"status": "ok", "result": <fn output>, "tool_name": name, "latency_ms": int}
        - 失敗：{"status": "error", "detail": <error msg>, "tool_name": name, "latency_ms": int}
        """
        start = time.time()
        params = params or {}

        # 1) Builtin tool
        if name in self._builtins:
            tool = self._builtins[name]
            try:
                result = await tool.fn(
                    params,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    project_id=project_id,
                    session_id=session_id,
                )
                if not isinstance(result, dict):
                    # 工具回非 dict — 包起來不要炸 loop
                    result = {"value": result}
                latency_ms = int((time.time() - start) * 1000)
                # 若內建工具自己回了 status=error，尊重之
                if result.get("status") == "error":
                    return {
                        "status": "error",
                        "detail": result.get("detail") or result.get("error") or "tool returned error",
                        "result": result,
                        "tool_name": name,
                        "latency_ms": latency_ms,
                    }
                return {
                    "status": "ok",
                    "result": result,
                    "tool_name": name,
                    "latency_ms": latency_ms,
                }
            except Exception as e:  # noqa: BLE001
                logger.exception("[v4_tool_registry] builtin %s raised", name)
                return {
                    "status": "error",
                    "detail": str(e),
                    "tool_name": name,
                    "latency_ms": int((time.time() - start) * 1000),
                }

        # 2) DB tool — 走 legacy
        try:
            from app.db import crud
            from app.core.tools.registry import tool_registry as _legacy

            # 找 tool by name within tenant scope
            db_tools: list[dict] = []
            if tenant_id:
                db_tools = crud.list_tools(tenant_id) or []
            else:
                # 沒 tenant_id 時無法定位 DB tool — 回 not found
                pass
            result = await _legacy.execute_tool_by_name(name, params, db_tools)
            latency_ms = int((time.time() - start) * 1000)
            if result.get("status") == "error":
                return {
                    "status": "error",
                    "detail": result.get("detail") or "tool error",
                    "result": result,
                    "tool_name": name,
                    "latency_ms": latency_ms,
                }
            return {
                "status": "ok",
                "result": result,
                "tool_name": name,
                "latency_ms": latency_ms,
            }
        except Exception as e:  # noqa: BLE001
            logger.exception("[v4_tool_registry] db tool %s failed", name)
            return {
                "status": "error",
                "detail": f"tool '{name}' not found or failed: {e}",
                "tool_name": name,
                "latency_ms": int((time.time() - start) * 1000),
            }


# Module-level singleton（與 personas/progress 一致風格）
v4_tool_registry = V4ToolRegistry()


__all__ = ["V4ToolRegistry", "v4_tool_registry"]
