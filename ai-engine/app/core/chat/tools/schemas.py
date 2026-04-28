"""V4 工具共用 schema 定義。

主要對外型別：
  - BuiltinTool：內建 Python 函數工具描述
  - ToolExecResult：工具執行結果（共用 dict 結構約定）

每個 builtin/* 的工具 module 約定提供：

    TOOL_NAME: str
    TOOL_DESCRIPTION: str
    INPUT_SCHEMA: dict   # JSON Schema (Claude tool input_schema 格式)
    async def run(params: dict, *, tenant_id, user_id, project_id, session_id) -> dict

並在啟動時呼叫：

    from app.core.chat.tools import v4_tool_registry
    from app.core.chat.tools.builtin import present_widget as pw

    v4_tool_registry.register_builtin(
        name=pw.TOOL_NAME,
        fn=pw.run,
        schema=pw.INPUT_SCHEMA,
        description=pw.TOOL_DESCRIPTION,
    )

`fn` 永遠回 dict，內含工具具體 output。registry.execute() 會把它包成
`{"status": "ok"|"error", "result": <dict>}` 給 tool_use_loop 串回 messages。

Phase 1 不為任何具體工具定義 pydantic input model（其他 agent 寫 builtin 工具時
會自己負責 input 驗證；INPUT_SCHEMA dict 已足夠驅動 Claude tool-use）。
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, NamedTuple, Optional

from pydantic import BaseModel


# 工具函數簽名：永遠 async、永遠回 dict
ToolFn = Callable[..., Awaitable[dict[str, Any]]]


class BuiltinTool(NamedTuple):
    """內建 Python 函數工具描述。

    name        : 工具名（要與 INPUT_SCHEMA 對應）
    fn          : async callable, signature:
                    async def fn(params: dict, *, tenant_id, user_id, project_id, session_id) -> dict
    schema      : Claude tool input_schema (JSON Schema dict)
    description : 給 LLM 看的工具描述（會放進 tools[].description）
    """

    name: str
    fn: ToolFn
    schema: dict[str, Any]
    description: str = ""


class ToolExecResult(BaseModel):
    """工具執行結果統一外殼。

    status="ok" 時 result 為工具實際輸出 dict；
    status="error" 時 detail 為錯誤訊息（不一定有 result）。
    """

    status: str  # "ok" | "error"
    result: Optional[dict[str, Any]] = None
    detail: Optional[str] = None
    tool_name: Optional[str] = None
    latency_ms: Optional[int] = None


__all__ = ["BuiltinTool", "ToolFn", "ToolExecResult"]
