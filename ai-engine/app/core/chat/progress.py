"""
SSE event emitter — V4 chat 的進度事件統一介面。

V3 的進度事件分散在 dag_executor / chat_adapter 各處；V4 統一由 PipelineRunContext
轉發到 SSE。事件型別：

  status: 階段標記（classifying / preflight / planning / calling_tool / synthesizing）
  content: 增量文字（LLM streaming chunk）
  tool_call: 工具呼叫開始
  tool_result: 工具結果（含 success/error）
  widget: widget 物件（structured_review / form / single_select 等）
  session_id: 第一次建 session 時送
  done: 結束（含 message_id, widgets, tool_results 完整 metadata）
  error: 錯誤
"""
from __future__ import annotations

from typing import Any


def status_event(status: str, detail: dict | None = None) -> dict[str, Any]:
    return {"type": "status", "status": status, **(detail or {})}


def content_event(text: str) -> dict[str, Any]:
    return {"type": "content", "content": text}


def tool_call_event(tool_name: str, params: dict) -> dict[str, Any]:
    return {"type": "tool_call", "tool_name": tool_name, "params": params}


def tool_result_event(tool_name: str, result: Any, status: str = "ok") -> dict[str, Any]:
    return {"type": "tool_result", "tool_name": tool_name, "result": result, "status": status}


def widget_event(widget: dict) -> dict[str, Any]:
    return {"type": "widget", "widget": widget}


def session_event(session_id: str) -> dict[str, Any]:
    return {"type": "session_id", "session_id": session_id}


def done_event(message_id: str | None, widgets: list | None = None,
               tool_results: list | None = None) -> dict[str, Any]:
    return {
        "type": "done",
        "done": True,
        "message_id": message_id,
        "widgets": widgets or [],
        "tool_results": tool_results or [],
    }


def error_event(message: str) -> dict[str, Any]:
    return {"type": "error", "error": message}
