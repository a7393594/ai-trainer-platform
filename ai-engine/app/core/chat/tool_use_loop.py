"""V4 native tool-use loop — Anthropic style + parallel exec + token/duplicate guard.

呼叫者（chat engine）給：
  - messages: 已準備好的 LLM context（system + history + user）
  - tools: Claude tool format（從 v4_tool_registry.list_for_chat() 得到）
  - 各種 guard 與 callback

回 ToolUseResult：
  - clean_text       : assistant 最終回給使用者的純文字（不含 tool_use 結構）
  - tool_results     : 每輪每個 tool 的呼叫結果（給前端 / metadata 用）
  - widgets          : present_widget tool 產出的 widget dict 收集
  - iterations       : 共跑幾輪
  - usage            : 累計 token usage
  - persona_used     : 暫時填 None（留給 engine 設）
  - stop_reason      : "natural" | "duplicate_guard" | "token_guard" | "max_iterations" | "error"

實作策略：
  - 一輪：呼叫 chat_completion(messages, tools=tools, …)
  - 若 response 沒 tool_calls 或有純 content → 取 content 為 final，break
  - 若 response 有 tool_calls：
      * 並行 await asyncio.gather(execute_tool…) 所有 tool calls
      * append assistant tool_use turn + 每個 tool 結果（role=tool）
      * 進下一輪
  - duplicate guard：追蹤 (tool_name, params_hash) 連續 N 輪相同 → 強制 synthesize
  - token guard：累計 prompt+completion tokens > token_guard → 強制 synthesize
  - 強制 synthesize = append 一條 system message 提示 LLM「請基於現有資訊作答，
    不要再呼叫工具」並再多跑一輪、不帶 tools

Phase 1 plan-and-execute（Haiku planner）暫不實作（放 Phase 3 葉子配置驅動），
但 loop 已能容納其延伸。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from app.core.llm_router.router import chat_completion

from .progress import (
    content_event,
    status_event,
    tool_call_event,
    tool_result_event,
    widget_event,
)
from .tools.registry import v4_tool_registry

logger = logging.getLogger(__name__)

EmitFn = Callable[[dict], Awaitable[None]]


@dataclass
class ToolUseResult:
    clean_text: str = ""
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    widgets: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    usage: dict[str, int] = field(default_factory=lambda: {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    })
    persona_used: Optional[str] = None
    stop_reason: str = "natural"


def _params_signature(name: str, params: dict[str, Any]) -> str:
    """穩定的 (name, params) hash，給 duplicate guard 比對用。"""
    try:
        params_json = json.dumps(params or {}, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        params_json = str(params)
    return hashlib.md5(f"{name}::{params_json}".encode("utf-8")).hexdigest()


def _accumulate_usage(usage_obj: Any, target: dict[str, int]) -> None:
    """從 chat_completion response.usage 累計到 target dict。"""
    if not usage_obj:
        return
    target["prompt_tokens"] += int(getattr(usage_obj, "prompt_tokens", 0) or 0)
    target["completion_tokens"] += int(getattr(usage_obj, "completion_tokens", 0) or 0)
    cc = getattr(usage_obj, "cache_creation_input_tokens", 0) or 0
    cr = getattr(usage_obj, "cache_read_input_tokens", 0) or 0
    target["cache_creation_input_tokens"] += int(cc)
    target["cache_read_input_tokens"] += int(cr)


def _extract_widget_from_tool_result(name: str, raw_result: dict[str, Any]) -> Optional[dict[str, Any]]:
    """從 present_widget tool result 中抽出 widget dict。

    convention: present_widget 的 inner result 應有 `widget` key 或本身就是 widget dict。
    """
    if name != "present_widget":
        return None
    inner = raw_result.get("result") or {}
    if not isinstance(inner, dict):
        return None
    if "widget" in inner and isinstance(inner["widget"], dict):
        return inner["widget"]
    # 備用：result 本身像 widget（含 widget_type 欄位）
    if "widget_type" in inner:
        return inner
    return None


async def _safe_emit(emit: Optional[EmitFn], event: dict) -> None:
    if emit is None:
        return
    try:
        await emit(event)
    except Exception as e:  # noqa: BLE001
        logger.debug("[tool_use_loop] emit progress failed: %s", e)


async def run_tool_use_loop(
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str = "claude-sonnet-4-20250514",
    temperature: float = 0.7,
    max_tokens: int = 2000,
    max_iterations: int = 8,
    tenant_id: Optional[str] = None,
    project_id: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    emit_progress: Optional[EmitFn] = None,
    token_guard: int = 150_000,
    duplicate_guard: int = 3,
    span_label: str = "v4_chat",
) -> ToolUseResult:
    """跑 native tool-use loop 直到模型不再呼叫工具或觸發 guard。

    `messages` 會被 in-place mutate（append assistant + tool turns）— 呼叫者若需保留
    原始版本，自己先 deepcopy。
    """
    result = ToolUseResult()
    sig_history: list[str] = []  # duplicate guard 用
    forced_synth_done = False    # 已經做過一次強制 synthesize

    use_tools = list(tools) if tools else None

    for iteration in range(max_iterations):
        result.iterations = iteration + 1

        await _safe_emit(emit_progress, status_event("calling_model", {
            "iteration": result.iterations,
            "tools_available": len(use_tools or []),
        }))

        try:
            resp = await chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=use_tools,
                tenant_id=tenant_id,
                project_id=project_id,
                session_id=session_id,
                span_label=f"{span_label}/iter{result.iterations}",
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("[tool_use_loop] chat_completion failed iter=%s", result.iterations)
            await _safe_emit(emit_progress, status_event("error", {"detail": str(e)}))
            result.stop_reason = "error"
            result.clean_text = result.clean_text or f"[error] {e}"
            return result

        msg = resp.choices[0].message
        usage = getattr(resp, "usage", None)
        _accumulate_usage(usage, result.usage)

        text_part = (msg.content or "").strip() if getattr(msg, "content", None) else ""
        tool_calls = getattr(msg, "tool_calls", None) or []

        if text_part:
            # 取最新一輪的 text 作為 clean_text；若後續還有 tool round 也會被覆蓋
            result.clean_text = text_part
            await _safe_emit(emit_progress, content_event(text_part))

        # === Stop conditions ===
        if not tool_calls:
            # Preserve guard stop_reason if one was set in a prior iteration
            if not forced_synth_done:
                result.stop_reason = "natural"
            break

        # === Token guard ===
        total_used = result.usage["prompt_tokens"] + result.usage["completion_tokens"]
        if total_used > token_guard and not forced_synth_done:
            logger.info("[tool_use_loop] token guard tripped: used=%s > %s", total_used, token_guard)
            messages.append({
                "role": "system",
                "content": (
                    "Token budget reached. Do NOT call any more tools. "
                    "Synthesize a final answer for the user using only the information already gathered."
                ),
            })
            use_tools = None
            forced_synth_done = True
            result.stop_reason = "token_guard"
            continue

        # === Duplicate guard ===
        round_signatures = [
            _params_signature(
                tc.function.name,
                _safe_parse_args(tc.function.arguments),
            )
            for tc in tool_calls
        ]
        sig_history.append("|".join(sorted(round_signatures)))
        if len(sig_history) >= duplicate_guard and len(set(sig_history[-duplicate_guard:])) == 1 and not forced_synth_done:
            logger.info(
                "[tool_use_loop] duplicate guard tripped: same tool calls %s times",
                duplicate_guard,
            )
            messages.append({
                "role": "system",
                "content": (
                    f"You have called the same tool(s) {duplicate_guard} times in a row with the "
                    "same parameters. Do not call any tool again. Synthesize a final answer using "
                    "the information already collected."
                ),
            })
            use_tools = None
            forced_synth_done = True
            result.stop_reason = "duplicate_guard"
            continue

        # === Append assistant turn carrying the tool_use directives ===
        messages.append({
            "role": "assistant",
            "content": text_part or None,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ],
        })

        # === Execute all tool calls in parallel ===
        async def _run_one(tc) -> dict[str, Any]:
            params = _safe_parse_args(tc.function.arguments)
            await _safe_emit(emit_progress, tool_call_event(tc.function.name, params))
            exec_result = await v4_tool_registry.execute(
                tc.function.name,
                params,
                tenant_id=tenant_id,
                user_id=user_id,
                project_id=project_id,
                session_id=session_id,
            )
            return {
                "tool_call_id": tc.id,
                "name": tc.function.name,
                "params": params,
                "exec_result": exec_result,
            }

        try:
            results_per_call = await asyncio.gather(
                *[_run_one(tc) for tc in tool_calls],
                return_exceptions=False,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("[tool_use_loop] parallel exec failed")
            await _safe_emit(emit_progress, status_event("error", {"detail": f"tool exec: {e}"}))
            result.stop_reason = "error"
            result.clean_text = result.clean_text or f"[tool exec error] {e}"
            return result

        # === Record + feed back to LLM ===
        for entry in results_per_call:
            tc_id = entry["tool_call_id"]
            tname = entry["name"]
            params = entry["params"]
            exec_result = entry["exec_result"]

            # tool_results record（給外部 metadata 用）
            result.tool_results.append({
                "iteration": result.iterations,
                "name": tname,
                "params": params,
                "result": exec_result,
            })

            # widget extract
            widget = _extract_widget_from_tool_result(tname, exec_result)
            if widget is not None:
                result.widgets.append(widget)
                await _safe_emit(emit_progress, widget_event(widget))

            await _safe_emit(emit_progress, tool_result_event(
                tname,
                exec_result.get("result") if exec_result.get("status") == "ok" else exec_result.get("detail"),
                status=exec_result.get("status", "ok"),
            ))

            # Tool result message back to LLM
            payload_for_llm = exec_result.get("result") if exec_result.get("status") == "ok" else {
                "error": exec_result.get("detail") or "tool error",
            }
            try:
                content_str = json.dumps(payload_for_llm, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                content_str = str(payload_for_llm)
            # 太長截掉避免炸 context（與 dag handler 對齊 8000 字）
            if len(content_str) > 8000:
                content_str = content_str[:8000] + "...[truncated]"
            messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": content_str,
            })
        # 進下一輪 LLM call

    else:
        # max_iterations 跑完
        result.stop_reason = "max_iterations"
        if not result.clean_text:
            result.clean_text = (
                "I gathered all the information I could but reached the maximum number of "
                "tool-use iterations before producing a final answer."
            )

    return result


def _safe_parse_args(raw: Optional[str]) -> dict[str, Any]:
    """tool_call.function.arguments 通常是 JSON 字串；解析失敗回 {}。"""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


__all__ = ["ToolUseResult", "run_tool_use_loop"]
