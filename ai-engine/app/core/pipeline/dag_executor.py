"""
DAG Executor — 依 DAG 定義執行 pipeline。

用途（MVP）：
- 測試 DAG 行為：test endpoint 呼叫，不影響生產對話
- A/B 比較：並排跑兩個 DAG
- 未來可擴充為生產 orchestrator 的替代品

設計原則：
- 每個 node_type 對應一個 handler function
- Context 物件在節點間傳遞 state
- 失敗就停、回傳 partial trace（不中斷整個 request）
"""
import asyncio
import json
import re
import time
from collections import defaultdict
from typing import Any, Awaitable, Callable, Optional

from app.core.llm_router.router import chat_completion
from app.core.tools.registry import tool_registry
from app.core.orchestrator.constants import WIDGET_INSTRUCTION
from app.core.orchestrator.prompt_loader import load_active_prompt, search_knowledge
from app.db import crud


# ============================================================================
# Context
# ============================================================================

class DAGContext:
    """節點間傳遞的狀態容器。"""

    def __init__(
        self,
        project_id: str,
        user_id: Optional[str],
        user_message: str,
        session_id: Optional[str] = None,
        persist: bool = False,
        pre_loaded_history: Optional[list[dict]] = None,
    ):
        self.project_id = project_id
        self.user_id = user_id
        self.user_message = user_message

        # 生產整合欄位（adapter 注入）
        self.session_id = session_id
        self.persist = persist
        self.pre_loaded_history = pre_loaded_history

        # 狀態欄位（各 node handler 按需讀寫）
        self.history: list[dict] = []
        self.intent_type: Optional[str] = None
        self.intent_rule: Optional[dict] = None  # capability rule dict when intent_type==capability_rule
        self.capability_handled: bool = False  # 某 capability 節點執行後設為 True,讓下游 general 節點透過 condition 跳過
        self.rag_context: Optional[str] = None
        self.system_prompt: str = ""
        self.messages: list[dict] = []
        self.model: Optional[str] = None
        self.temperature: float = 0.7
        self.max_tokens: int = 2000
        self.llm_tools: Optional[list[dict]] = None
        self.db_tools: list[dict] = []
        self.llm_response_text: str = ""
        self.tool_call_count: int = 0
        self.tool_iterations: int = 0
        self.tool_results: list[dict] = []  # list of {name, params, result, status, iteration}
        self.total_tokens_in: int = 0
        self.total_tokens_out: int = 0
        self.total_cost_usd: float = 0.0
        self.widgets: list[dict] = []
        self.clean_text: str = ""
        self.guardrail_triggered: bool = False
        self.assistant_message_id: Optional[str] = None

        # capability 節點要寫入 assistant_msg.metadata 的額外欄位(capability_rule_id、tool_id 等)
        self.extra_metadata: dict = {}
        # capability 節點要寫入 ChatResponse.metadata 的額外欄位(handoff、workflow_status 等)
        self.response_metadata: dict = {}


# ============================================================================
# Node handlers — each returns NodeResult dict
# ============================================================================

async def handle_input(node: dict, ctx: DAGContext) -> dict:
    return {
        "status": "ok",
        "output": {"text": ctx.user_message, "length": len(ctx.user_message)},
        "summary": f"收到輸入（{len(ctx.user_message)} 字）",
    }


async def handle_load_history(node: dict, ctx: DAGContext) -> dict:
    """載入歷史。生產模式由 adapter 預載(pre_loaded_history);測試模式空歷史。"""
    if ctx.pre_loaded_history is not None:
        ctx.history = ctx.pre_loaded_history
        return {
            "status": "ok",
            "output": {"history_length": len(ctx.history), "source": "adapter_injected"},
            "summary": f"載入 {len(ctx.history)} 則歷史(adapter 注入)",
        }
    ctx.history = []
    return {
        "status": "ok",
        "output": {"history_length": 0, "note": "test mode — empty history"},
        "summary": "測試模式：跳過歷史載入",
    }


async def handle_triage(node: dict, ctx: DAGContext) -> dict:
    """真實 intent 分類 — keyword + semantic embedding hybrid。

    依 classify_async 回傳決定:
      - capability_rule: 帶著 rule dict,讓下游 capability_* 節點依 action_type 接手
      - active_workflow: 下游 workflow_continue 節點接手
      - general: 下游 load_knowledge → compose_prompt → call_model 鏈
    """
    try:
        from app.core.intent.classifier import intent_classifier
        result = await intent_classifier.classify_async(
            ctx.user_message, ctx.project_id, mode="hybrid"
        )
        ctx.intent_type = result.get("type", "general")
        ctx.intent_rule = result.get("rule")
    except Exception as e:  # noqa: BLE001
        ctx.intent_type = "general"
        return {
            "status": "ok",
            "output": {"intent_type": "general", "error": str(e)[:200]},
            "summary": f"分類失敗退回 general:{e}",
        }

    matched = None
    if ctx.intent_type == "capability_rule" and ctx.intent_rule:
        matched = ctx.intent_rule.get("trigger_description")
    return {
        "status": "ok",
        "output": {
            "intent_type": ctx.intent_type,
            "matched": matched,
            "action_type": (ctx.intent_rule or {}).get("action_type") if ctx.intent_rule else None,
        },
        "summary": f"意圖:{ctx.intent_type}" + (f"({matched})" if matched else ""),
    }


async def handle_triage_llm(node: dict, ctx: DAGContext) -> dict:
    """LLM-based intent classification using a cheap model (default: claude-haiku-4-5-20251001).

    讀取 project 的 capability rules，組成列表給便宜模型判斷；
    失敗時降級為 keyword classifier。
    """
    import json as _json
    import re as _re

    rules = crud.list_capability_rules(ctx.project_id)
    cfg = node.get("config") or {}
    cheap_model = cfg.get("model", "claude-haiku-4-5-20251001")

    if not rules:
        ctx.intent_type = "general"
        return {
            "status": "ok",
            "output": {"intent_type": "general", "reason": "no_rules", "user_message": ctx.user_message[:300]},
            "summary": "無 capability rules → general",
        }

    rules_desc = "\n".join(
        f"{i + 1}. [{r['action_type']}] {r['trigger_description']}"
        for i, r in enumerate(rules)
    )
    system_msg = {
        "role": "system",
        "content": (
            "你是一個意圖分類器。根據使用者訊息，判斷是否符合以下任一規則：\n\n"
            f"{rules_desc}\n\n"
            "只回傳 JSON，格式如下：\n"
            '- 不符合：{"type": "general"}\n'
            '- 符合：{"type": "capability_rule", "rule_index": <1-based int>}\n'
            "不要加任何其他說明。"
        ),
    }

    try:
        resp = await chat_completion(
            messages=[system_msg, {"role": "user", "content": ctx.user_message}],
            model=cheap_model,
            max_tokens=50,
            temperature=0.0,
            project_id=ctx.project_id,
            session_id=ctx.session_id,
            span_label="triage_llm",
        )
        text = (resp.get("content") or "").strip()
        m = _re.search(r"\{.*?\}", text, _re.DOTALL)
        parsed = _json.loads(m.group()) if m else {"type": "general"}

        if parsed.get("type") == "capability_rule":
            idx = int(parsed.get("rule_index", 1)) - 1
            if 0 <= idx < len(rules):
                ctx.intent_type = "capability_rule"
                ctx.intent_rule = rules[idx]
                desc = (rules[idx].get("trigger_description") or "")[:60]
                return {
                    "status": "ok",
                    "output": {
                        "intent_type": "capability_rule",
                        "matched": desc,
                        "action_type": rules[idx].get("action_type"),
                        "model_used": cheap_model,
                    },
                    "summary": f"LLM意圖: capability_rule({desc})",
                }

        ctx.intent_type = "general"
        return {
            "status": "ok",
            "output": {"intent_type": "general", "model_used": cheap_model},
            "summary": "LLM意圖: general",
        }
    except Exception as e:  # noqa: BLE001
        from app.core.intent.classifier import intent_classifier

        fallback = intent_classifier.classify(ctx.user_message, ctx.project_id)
        ctx.intent_type = fallback.get("type", "general")
        ctx.intent_rule = fallback.get("rule")
        return {
            "status": "ok",
            "output": {
                "intent_type": ctx.intent_type,
                "fallback": "keyword",
                "error": str(e)[:100],
            },
            "summary": f"LLM失敗→keyword fallback: {ctx.intent_type}",
        }


async def handle_load_knowledge(node: dict, ctx: DAGContext) -> dict:
    """RAG 檢索 — 走 orchestrator.prompt_loader.search_knowledge(pipeline:Qdrant → pgvector → keyword)。"""
    cfg = node.get("config") or {}
    rag_limit = int(cfg.get("rag_limit", 5))
    if rag_limit == 0:
        return {"status": "ok", "output": {"skipped": True}, "summary": "RAG 關閉"}

    try:
        rag_text = await search_knowledge(ctx.user_message, ctx.project_id)
        if rag_text:
            ctx.rag_context = rag_text
            # 估個片段數(以 "---" 分隔)供 trace 顯示
            chunk_count = rag_text.count("\n\n---\n\n") + 1
            return {
                "status": "ok",
                "output": {
                    "chunk_count": chunk_count,
                    "total_chars": len(rag_text),
                    "rag_limit": rag_limit,
                    "rag_preview": rag_text[:1000] + ("..." if len(rag_text) > 1000 else ""),
                    "query": ctx.user_message[:300],
                },
                "summary": f"取 {chunk_count} 個 RAG 片段",
            }
    except Exception as e:  # noqa: BLE001
        return {"status": "ok", "output": {"error": str(e)[:200], "query": ctx.user_message[:300]}, "summary": "RAG 檢索失敗(略過)"}

    return {"status": "ok", "output": {"chunk_count": 0, "rag_limit": rag_limit, "query": ctx.user_message[:300]}, "summary": "沒有相關知識"}


async def handle_compose_prompt(node: dict, ctx: DAGContext) -> dict:
    """組 LLM messages:system(prefix + active prompt + WIDGET_INSTRUCTION) + RAG + history + user。

    用 load_active_prompt 取 A/B variant-aware 的 prompt。WIDGET_INSTRUCTION 一定要附,
    否則 DAG 路徑永遠不會產生 widget 標記。
    """
    cfg = node.get("config") or {}
    prefix = cfg.get("system_prompt_prefix", "") or ""

    base_prompt = ""
    try:
        base_prompt = await load_active_prompt(ctx.project_id, ctx.session_id) or ""
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] load_active_prompt failed in DAG: {e}")

    # 組 system prompt:prefix + base + WIDGET_INSTRUCTION(與 orchestrator 對齊)
    parts = []
    if prefix:
        parts.append(prefix)
    if base_prompt:
        parts.append(base_prompt)
    parts.append(WIDGET_INSTRUCTION)
    ctx.system_prompt = "\n\n".join(p for p in parts if p)

    ctx.messages = []
    if ctx.system_prompt:
        ctx.messages.append({"role": "system", "content": ctx.system_prompt})
    if ctx.rag_context:
        ctx.messages.append({"role": "system", "content": f"以下是相關參考資料:\n\n{ctx.rag_context}"})
    ctx.messages.extend(ctx.history)
    ctx.messages.append({"role": "user", "content": ctx.user_message})

    return {
        "status": "ok",
        "output": {
            "message_count": len(ctx.messages),
            "system_prompt_length": len(ctx.system_prompt),
            "system_prompt_preview": ctx.system_prompt[:1500] + ("..." if len(ctx.system_prompt) > 1500 else ""),
            "has_rag": bool(ctx.rag_context),
            "rag_length": len(ctx.rag_context) if ctx.rag_context else 0,
            "has_prefix": bool(prefix),
            "prefix_preview": prefix[:500] if prefix else "",
            "has_widget_instruction": True,
            "history_count": len(ctx.history),
            "user_message": ctx.user_message[:500],
        },
        "summary": f"組出 {len(ctx.messages)} 則訊息(system {len(ctx.system_prompt)} 字)",
    }


async def handle_call_model(node: dict, ctx: DAGContext) -> dict:
    """主模型呼叫 + 完整工具迴圈。

    若 model 要求呼叫工具，實際執行工具、把結果餵回模型，最多跑 max_iterations 輪。
    max_iterations 從 execute_tools 節點的 config 讀（如存在於 DAG），否則預設 5。
    """
    cfg = node.get("config") or {}
    try:
        project = crud.get_project(ctx.project_id)
    except Exception:
        project = None

    # Per-project pipeline config override(與 orchestrator agent.py:517 對齊)
    try:
        per_project_cfg = crud.get_node_config(ctx.project_id, "main_model") or {}
    except Exception:
        per_project_cfg = {}

    # 優先序:node cfg > per-project cfg > project default > fallback
    ctx.model = (
        cfg.get("model")
        or per_project_cfg.get("model")
        or (project.get("default_model") if project else None)
        or "claude-sonnet-4-20250514"
    )
    ctx.temperature = float(cfg.get("temperature", per_project_cfg.get("temperature", 0.7)))
    ctx.max_tokens = int(cfg.get("max_tokens", per_project_cfg.get("max_tokens", 2000)))
    max_iterations = int(cfg.get("max_iterations", 5))

    # Resolve tools:優先 node cfg.tool_ids,否則 per-project cfg.tool_ids,否則全部
    tool_ids = cfg.get("tool_ids")
    if tool_ids is None:
        tool_ids = per_project_cfg.get("tool_ids")
    tools_payload = None
    if project:
        try:
            all_tools = await tool_registry.list_tools(project.get("tenant_id"))
            if tool_ids is not None:
                selected = [t for t in all_tools if t["id"] in set(tool_ids)]
            else:
                selected = all_tools
            ctx.db_tools = selected
            tools_payload = tool_registry.convert_to_llm_tools(selected) if selected else None
            ctx.llm_tools = tools_payload
        except Exception:
            pass

    total_latency_ms = 0
    total_in = 0
    total_out = 0
    final_tool_call_count = 0
    iteration_details: list[dict] = []   # 每輪詳細（for trace output）
    synthesis_layer: str = ""             # L1 / L2 / L3 / "" (not needed)

    try:
        for iteration in range(max_iterations + 1):  # initial + up to N iterations
            start = time.time()
            resp = await chat_completion(
                messages=ctx.messages,
                model=ctx.model,
                temperature=ctx.temperature,
                max_tokens=ctx.max_tokens,
                tools=tools_payload,
                project_id=ctx.project_id,
                session_id=ctx.session_id,
                span_label=f"main_model{'' if iteration == 0 else f'_iter_{iteration + 1}'}",
            )
            msg = resp.choices[0].message
            text = msg.content or ""
            usage = getattr(resp, "usage", None)
            in_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
            out_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
            tool_calls = getattr(msg, "tool_calls", None) or []
            iter_latency = int((time.time() - start) * 1000)

            total_in += in_tokens
            total_out += out_tokens
            total_latency_ms += iter_latency

            iteration_details.append({
                "iter": iteration + 1,
                "phase": "tool_loop",
                "tokens_in": in_tokens,
                "tokens_out": out_tokens,
                "latency_ms": iter_latency,
                "tool_calls": [
                    {"name": tc.function.name, "arguments": tc.function.arguments[:300] if tc.function.arguments else ""}
                    for tc in tool_calls
                ],
                "text_preview": text[:200] if text else "",
                "finish_reason": "text" if not tool_calls else "tool_calls",
            })

            if not tool_calls:
                # Done
                ctx.llm_response_text = text
                final_tool_call_count = 0
                break

            # Model wants to use tools — execute them
            final_tool_call_count = len(tool_calls)
            ctx.tool_iterations += 1

            # Append assistant message with tool_calls to history
            ctx.messages.append({
                "role": "assistant",
                "content": text,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            })

            # Execute each tool call and append tool results
            for tc in tool_calls:
                tool_name = tc.function.name
                try:
                    params = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except Exception:
                    params = {}
                try:
                    result = await tool_registry.execute_tool_by_name(
                        name=tool_name,
                        params=params,
                        tools=ctx.db_tools,
                    )
                    status = "ok" if not (isinstance(result, dict) and result.get("status") == "error") else "error"
                except Exception as e:
                    result = {"error": str(e)}
                    status = "error"

                ctx.tool_results.append({
                    "iteration": ctx.tool_iterations,
                    "name": tool_name,
                    "params": params,
                    "result": result,
                    "status": status,
                })
                ctx.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False)[:4000],
                })

            # 達到 iteration cap：三層防呆合成，保證 ctx.llm_response_text 絕對非空。
            # 所有 print 用 flush=True，確保 Uvicorn --reload 下 worker 子行程能輸出 log。
            if iteration >= max_iterations:
                if not ctx.llm_response_text and ctx.tool_results:
                    import litellm as _litellm
                    import traceback as _tb
                    _syn_text = ""

                    # Layer 1: tool_choice="none" 保留完整上下文（Anthropic 原生）
                    try:
                        _start = time.time()
                        _resp = await _litellm.acompletion(
                            model=ctx.model,
                            messages=ctx.messages,
                            temperature=ctx.temperature,
                            max_tokens=ctx.max_tokens,
                            tools=tools_payload,
                            tool_choice="none",
                        )
                        _syn_text = (_resp.choices[0].message.content or "").strip()
                        _usage = getattr(_resp, "usage", None)
                        _syn_in = getattr(_usage, "prompt_tokens", 0) if _usage else 0
                        _syn_out = getattr(_usage, "completion_tokens", 0) if _usage else 0
                        _syn_lat = int((time.time() - _start) * 1000)
                        total_in += _syn_in
                        total_out += _syn_out
                        total_latency_ms += _syn_lat
                        iteration_details.append({
                            "iter": len(iteration_details) + 1, "phase": "synthesis_L1",
                            "tokens_in": _syn_in, "tokens_out": _syn_out, "latency_ms": _syn_lat,
                            "text_preview": _syn_text[:200], "finish_reason": "text" if _syn_text else "empty",
                        })
                        if _syn_text:
                            synthesis_layer = "L1"
                        print(f"[INFO] synthesis L1 tool_choice=none: len={len(_syn_text)}", flush=True)
                    except Exception as _e:
                        iteration_details.append({
                            "iter": len(iteration_details) + 1, "phase": "synthesis_L1",
                            "tokens_in": 0, "tokens_out": 0, "latency_ms": 0,
                            "text_preview": "", "finish_reason": f"error: {str(_e)[:100]}",
                        })
                        print(f"[WARN] synthesis L1 failed: {_e}", flush=True)
                        _tb.print_exc()

                    # Layer 2: 乾淨上下文 + 簡化 system prompt
                    if not _syn_text:
                        try:
                            _start = time.time()
                            _user_msg = next(
                                (m.get("content", "") for m in ctx.messages if m.get("role") == "user"),
                                ctx.user_message,
                            )
                            _tool_text = "\n\n".join(
                                f"[{tr['name']}]\n{json.dumps(tr['result'], ensure_ascii=False)[:1000]}"
                                for tr in ctx.tool_results
                            )
                            _clean_msgs = [
                                {"role": "system", "content": "你是一個助手。根據以下工具執行結果，用繁體中文提供清楚完整的回答。"},
                                {"role": "user", "content": f"問題：{_user_msg}\n\n工具結果：\n{_tool_text}\n\n請根據結果完整回答。"},
                            ]
                            _resp = await _litellm.acompletion(
                                model=ctx.model,
                                messages=_clean_msgs,
                                temperature=ctx.temperature,
                                max_tokens=ctx.max_tokens,
                            )
                            _syn_text = (_resp.choices[0].message.content or "").strip()
                            _usage = getattr(_resp, "usage", None)
                            _syn_in = getattr(_usage, "prompt_tokens", 0) if _usage else 0
                            _syn_out = getattr(_usage, "completion_tokens", 0) if _usage else 0
                            _syn_lat = int((time.time() - _start) * 1000)
                            total_in += _syn_in
                            total_out += _syn_out
                            total_latency_ms += _syn_lat
                            iteration_details.append({
                                "iter": len(iteration_details) + 1, "phase": "synthesis_L2",
                                "tokens_in": _syn_in, "tokens_out": _syn_out, "latency_ms": _syn_lat,
                                "text_preview": _syn_text[:200], "finish_reason": "text" if _syn_text else "empty",
                            })
                            if _syn_text:
                                synthesis_layer = "L2"
                            print(f"[INFO] synthesis L2 clean-context: len={len(_syn_text)}", flush=True)
                        except Exception as _e:
                            iteration_details.append({
                                "iter": len(iteration_details) + 1, "phase": "synthesis_L2",
                                "tokens_in": 0, "tokens_out": 0, "latency_ms": 0,
                                "text_preview": "", "finish_reason": f"error: {str(_e)[:100]}",
                            })
                            print(f"[WARN] synthesis L2 failed: {_e}", flush=True)
                            _tb.print_exc()

                    # Layer 3: 工具結果直接當文字（保底絕對非空）
                    if not _syn_text:
                        _syn_text = "工具執行完成，結果如下：\n\n" + "\n\n".join(
                            f"**{tr['name']}**\n```json\n{json.dumps(tr['result'], ensure_ascii=False, indent=2)[:800]}\n```"
                            for tr in ctx.tool_results
                        )
                        synthesis_layer = "L3"
                        iteration_details.append({
                            "iter": len(iteration_details) + 1, "phase": "synthesis_L3",
                            "tokens_in": 0, "tokens_out": 0, "latency_ms": 0,
                            "text_preview": _syn_text[:200], "finish_reason": "fallback",
                        })
                        print(f"[INFO] synthesis L3 tool-as-text: len={len(_syn_text)}", flush=True)

                    ctx.llm_response_text = _syn_text
                break

        ctx.total_tokens_in += total_in
        ctx.total_tokens_out += total_out
        ctx.tool_call_count = final_tool_call_count

        tool_summary = f"，呼叫 {len(ctx.tool_results)} 個工具" if ctx.tool_results else ""
        syn_suffix = f"（合成 {synthesis_layer}）" if synthesis_layer else ""
        return {
            "status": "ok",
            "output": {
                "text": ctx.llm_response_text[:500] + ("..." if len(ctx.llm_response_text) > 500 else ""),
                "model": ctx.model,
                "temperature": ctx.temperature,
                "max_tokens": ctx.max_tokens,
                "max_iterations": max_iterations,
                "tokens_in": total_in,
                "tokens_out": total_out,
                "latency_ms": total_latency_ms,
                "iterations": ctx.tool_iterations,
                "tool_calls_total": len(ctx.tool_results),
                "tools_available": [t.get("name") for t in (ctx.db_tools or [])],
                "synthesis_layer": synthesis_layer,
                "iteration_details": iteration_details,
            },
            "summary": f"{ctx.model} · 收 {total_in} 出 {total_out} · {total_latency_ms}ms{tool_summary}{syn_suffix}",
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "summary": f"模型呼叫失敗：{e}"}


async def handle_execute_tools(node: dict, ctx: DAGContext) -> dict:
    """顯示在 call_model 節點內執行的工具結果。"""
    if not ctx.tool_results:
        return {"status": "ok", "output": {"iterations": 0}, "summary": "模型未呼叫工具"}

    # Summarize per tool
    summary_lines = []
    for tr in ctx.tool_results:
        status_icon = "✓" if tr["status"] == "ok" else "✗"
        summary_lines.append(f"{status_icon} {tr['name']} (iter {tr['iteration']})")

    return {
        "status": "ok",
        "output": {
            "iterations": ctx.tool_iterations,
            "total_calls": len(ctx.tool_results),
            "results": ctx.tool_results[:10],  # limit dump size
        },
        "summary": f"執行 {ctx.tool_iterations} 輪 · {len(ctx.tool_results)} 個工具呼叫｜" + "、".join(summary_lines[:5]),
    }


async def handle_guardrail(node: dict, ctx: DAGContext) -> dict:
    cfg = node.get("config") or {}
    forbidden = cfg.get("forbidden_patterns") or []
    action = cfg.get("action", "warn")
    if not forbidden:
        return {"status": "ok", "output": {"skipped": True}, "summary": "沒設禁用詞，略過"}

    text = ctx.llm_response_text or ctx.clean_text
    hits = []
    for pat in forbidden:
        if pat and pat.lower() in text.lower():
            hits.append(pat)

    if not hits:
        return {
            "status": "ok",
            "output": {"hits": 0, "action": action},
            "summary": f"通過檢查（檢查 {len(forbidden)} 個關鍵字）",
        }

    ctx.guardrail_triggered = True
    result = {
        "status": "ok" if action == "warn" else "error",
        "output": {"hits": hits, "action": action},
        "summary": f"🛡️ 偵測到 {len(hits)} 個禁用詞（{action}）",
    }
    if action == "block":
        ctx.llm_response_text = "[此回應因 Guardrail 規則被阻擋]"
    elif action == "retry":
        # MVP: 只標記，完整 retry 需要 graph loop 支援
        result["output"]["note"] = "MVP: retry 未實作（需支援 DAG loop）"
    return result


async def handle_retry(node: dict, ctx: DAGContext) -> dict:
    # MVP: retry 節點本身是 no-op；語意是「包裹前一個節點 N 次重試」
    # 實作完整 retry 需要 DAG executor 支援包裝語意，本 MVP 簡化
    cfg = node.get("config") or {}
    return {
        "status": "ok",
        "output": {
            "max_retries": cfg.get("max_retries", 3),
            "backoff_ms": cfg.get("backoff_ms", 1000),
            "note": "MVP: retry 節點僅標記，實際重試邏輯後續版本",
        },
        "summary": "Retry 節點（MVP 標記）",
    }


async def handle_parse_widget(node: dict, ctx: DAGContext) -> dict:
    text = ctx.llm_response_text
    widgets: list[dict] = []
    pattern = r'<!--WIDGET:([\s\S]*?)-->'
    matches = re.findall(pattern, text)
    clean = re.sub(pattern, '', text).strip()
    for m in matches:
        try:
            widgets.append(json.loads(m.strip()))
        except Exception:
            pass
    ctx.widgets = widgets
    ctx.clean_text = clean
    return {
        "status": "ok",
        "output": {
            "widget_count": len(widgets),
            "clean_length": len(clean),
            "raw_length": len(text),
            "clean_preview": clean[:500] + ("..." if len(clean) > 500 else ""),
            "widgets_preview": widgets[:3],
        },
        "summary": f"解析出 {len(widgets)} 個 widget",
    }


async def handle_capability_widget(node: dict, ctx: DAGContext) -> dict:
    """Capability rule · widget action — 回傳預定義 widget + 可選的 LLM 文字回覆。

    Condition 應綁 intent_type == capability_rule AND intent_rule.action_type == widget。
    """
    rule = ctx.intent_rule or {}
    action_config = rule.get("action_config") or {}
    widget_def = action_config.get("widget") or {}
    text_response = action_config.get("text") or ""

    if not text_response:
        # 產生 contextual 文字
        try:
            system_prompt = await load_active_prompt(ctx.project_id, ctx.session_id) or ""
            messages: list[dict] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.extend(ctx.history)
            messages.append({"role": "user", "content": ctx.user_message})
            messages.append({"role": "system", "content": (
                f"使用者的問題匹配到了一個互動元件規則。請用自然語言回覆使用者,"
                f"然後系統會自動顯示互動元件。規則描述:{rule.get('trigger_description', '')}"
            )})
            resp = await chat_completion(
                messages=messages,
                model="claude-sonnet-4-20250514",
                project_id=ctx.project_id,
                session_id=ctx.session_id,
                span_label="capability_widget_text",
            )
            text_response = (resp.choices[0].message.content or "").strip()
        except Exception as e:  # noqa: BLE001
            text_response = "好的,我為你準備了一個互動元件。"
            print(f"[WARN] capability_widget text generation failed: {e}")

    ctx.clean_text = text_response
    ctx.widgets = [widget_def] if widget_def else []
    ctx.extra_metadata.update({
        "capability_rule_id": rule.get("id"),
        "action_type": "widget",
    })
    ctx.capability_handled = True

    return {
        "status": "ok",
        "output": {
            "rule_id": rule.get("id"),
            "has_widget": bool(widget_def),
            "text_length": len(text_response),
        },
        "summary": f"Widget:{rule.get('trigger_description', '(unknown)')[:30]}",
    }


async def handle_capability_tool_call(node: dict, ctx: DAGContext) -> dict:
    """Capability rule · tool_call action — LLM 被動參考工具回覆。"""
    rule = ctx.intent_rule or {}
    action_config = rule.get("action_config") or {}
    tool_id = action_config.get("tool_id")

    if not tool_id:
        # fallback:讓下游 general 節點接手
        ctx.capability_handled = False
        return {"status": "ok", "output": {"skipped": True, "reason": "no tool_id"}, "summary": "無 tool_id,退回 general"}

    tool = crud.get_tool(tool_id)
    if not tool:
        ctx.capability_handled = False
        return {"status": "ok", "output": {"skipped": True, "reason": "tool not found"}, "summary": "tool 不存在,退回 general"}

    try:
        system_prompt = await load_active_prompt(ctx.project_id, ctx.session_id) or ""
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.extend(ctx.history)
        messages.append({"role": "user", "content": ctx.user_message})
        messages.append({"role": "system", "content": f"可用工具:{tool['name']} — {tool.get('description', '')}。請使用此工具回答使用者。"})
        resp = await chat_completion(
            messages=messages,
            model="claude-sonnet-4-20250514",
            project_id=ctx.project_id,
            session_id=ctx.session_id,
            span_label="capability_tool_call",
        )
        text_response = (resp.choices[0].message.content or "").strip()
    except Exception as e:  # noqa: BLE001
        text_response = f"(工具呼叫失敗:{e})"

    ctx.clean_text = text_response
    ctx.tool_results = [{"tool_name": tool["name"], "status": "referenced"}]
    ctx.extra_metadata.update({
        "capability_rule_id": rule.get("id"),
        "tool_id": tool_id,
    })
    ctx.capability_handled = True

    return {
        "status": "ok",
        "output": {"rule_id": rule.get("id"), "tool_name": tool["name"], "text_length": len(text_response)},
        "summary": f"Tool:{tool['name']}",
    }


async def handle_capability_workflow(node: dict, ctx: DAGContext) -> dict:
    """Capability rule · workflow action — 啟動 workflow(auto 或 step 模式)。"""
    from app.core.workflows.engine import workflow_engine

    rule = ctx.intent_rule or {}
    action_config = rule.get("action_config") or {}
    workflow_id = action_config.get("workflow_id")
    run_mode = action_config.get("run_mode", "step")

    if not workflow_id:
        ctx.capability_handled = False
        return {"status": "ok", "output": {"skipped": True, "reason": "no workflow_id"}, "summary": "無 workflow_id,退回 general"}

    user_id = ctx.user_id or "anonymous"

    if run_mode == "auto":
        result = await workflow_engine.run_to_completion(
            workflow_id,
            session_id=ctx.session_id,
            user_id=user_id,
            initial_vars={"message": ctx.user_message},
        )
        status = result.get("status")
        trace_len = len(result.get("trace") or [])
        if status == "completed":
            text = f"工作流已自動執行完成({trace_len} 個步驟)。"
        else:
            text = f"工作流執行失敗:{result.get('error', 'unknown')}"
        ctx.clean_text = text
        ctx.extra_metadata.update({
            "workflow_run_id": result.get("run_id"),
            "capability_rule_id": rule.get("id"),
            "workflow_status": status,
            "workflow_vars": result.get("vars"),
        })
        ctx.response_metadata.update({
            "workflow_status": status,
            "workflow_run_id": result.get("run_id"),
        })
        ctx.capability_handled = True
        return {
            "status": "ok",
            "output": {"run_id": result.get("run_id"), "workflow_status": status, "steps": trace_len},
            "summary": f"Workflow auto:{status} ({trace_len} steps)",
        }

    # 步進式
    result = await workflow_engine.start_workflow(workflow_id, ctx.session_id, user_id)
    if result.get("status") == "started":
        step = result.get("current_step", {})
        text = f"已啟動工作流:{result.get('workflow_name', '')}。\n\n當前步驟:{step.get('id', '')}"
        ctx.clean_text = text
        if step.get("widget"):
            ctx.widgets = [step["widget"]]
        ctx.extra_metadata.update({
            "workflow_run_id": result.get("run_id"),
            "capability_rule_id": rule.get("id"),
        })
        ctx.capability_handled = True
        return {
            "status": "ok",
            "output": {"run_id": result.get("run_id"), "step_id": step.get("id")},
            "summary": f"Workflow step:{result.get('workflow_name', '')}",
        }

    # 啟動失敗 → fallback
    ctx.capability_handled = False
    return {
        "status": "ok",
        "output": {"skipped": True, "reason": result.get("detail", "workflow start failed")},
        "summary": "Workflow 啟動失敗,退回 general",
    }


async def handle_capability_handoff(node: dict, ctx: DAGContext) -> dict:
    """Capability rule · handoff action — 升級至真人客服。"""
    from app.core.handoff.service import handoff_service

    rule = ctx.intent_rule or {}
    action_config = rule.get("action_config") or {}

    reason = action_config.get("reason") or "User triggered handoff capability"
    urgency = action_config.get("urgency", "normal")
    result = await handoff_service.request(
        ctx.session_id, reason=reason, triggered_by="capability_rule", urgency=urgency,
    )
    reply = action_config.get("text") or "已為您轉接真人客服,稍後會有專員與您聯繫。"

    ctx.clean_text = reply
    ctx.extra_metadata.update({
        "capability_rule_id": rule.get("id"),
        "handoff_message_id": result.get("handoff_message_id"),
        "handoff_notified": result.get("notified"),
        "handoff_urgency": urgency,
    })
    ctx.response_metadata.update({
        "handoff": True,
        "handoff_message_id": result.get("handoff_message_id"),
        "urgency": urgency,
    })
    ctx.capability_handled = True

    return {
        "status": "ok",
        "output": {
            "rule_id": rule.get("id"),
            "handoff_message_id": result.get("handoff_message_id"),
            "notified": result.get("notified"),
            "urgency": urgency,
        },
        "summary": f"Handoff · {urgency}",
    }


async def handle_workflow_continue(node: dict, ctx: DAGContext) -> dict:
    """active_workflow 分支 — Phase 5 stub,目前直接退回 general。

    未來 Phase 5 完工時,此節點會:
      1. 找出 session 的進行中 workflow_run(waiting_input 狀態)
      2. 把 user_message 當作 step_result 呼叫 workflow_engine.advance_workflow
      3. 回傳下一步的 widget 或完成訊息
    """
    ctx.capability_handled = False
    return {
        "status": "ok",
        "output": {"note": "Phase 5 stub · 退回 general"},
        "summary": "Workflow continue(stub)",
    }


async def handle_output(node: dict, ctx: DAGContext) -> dict:
    """組最終輸出。生產模式(ctx.persist && ctx.session_id)會寫 ait_training_messages,
    metadata 的 widgets / tool_results 欄位與 orchestrator 對齊。
    """
    final_text = ctx.clean_text or ctx.llm_response_text
    output: dict = {
        "final_text": final_text,
        "final_text_preview": final_text[:1000] + ("..." if len(final_text) > 1000 else ""),
        "final_text_length": len(final_text),
        "widget_count": len(ctx.widgets),
        "total_tokens_in": ctx.total_tokens_in,
        "total_tokens_out": ctx.total_tokens_out,
        "tool_call_count": len(ctx.tool_results),
    }

    if ctx.persist and ctx.session_id:
        try:
            metadata: dict = {}
            if ctx.widgets:
                metadata["widgets"] = ctx.widgets
            if ctx.tool_results:
                metadata["tool_results"] = ctx.tool_results
            if ctx.extra_metadata:
                metadata.update(ctx.extra_metadata)
            assistant_msg = crud.create_message(
                session_id=ctx.session_id,
                role="assistant",
                content=final_text,
                metadata=metadata,
            )
            ctx.assistant_message_id = assistant_msg["id"]
            output["assistant_message_id"] = assistant_msg["id"]
        except Exception as e:  # noqa: BLE001
            # 寫庫失敗不阻斷回覆 — 記在 output
            output["persist_error"] = str(e)[:200]

    return {
        "status": "ok",
        "output": output,
        "summary": f"輸出完成({len(final_text)} 字)" + ("|已落庫" if ctx.assistant_message_id else ""),
    }


# ============================================================================
# Handler registry
# ============================================================================

NodeHandler = Callable[[dict, DAGContext], Awaitable[dict]]

HANDLERS: dict[str, NodeHandler] = {
    "input": handle_input,
    "load_history": handle_load_history,
    "triage": handle_triage,
    "triage_llm": handle_triage_llm,
    "load_knowledge": handle_load_knowledge,
    "compose_prompt": handle_compose_prompt,
    "call_model": handle_call_model,
    "execute_tools": handle_execute_tools,
    "guardrail": handle_guardrail,
    "retry": handle_retry,
    "parse_widget": handle_parse_widget,
    "output": handle_output,
    # Capability rule actions(intent_type == capability_rule 時按 action_type 分派)
    "capability_widget": handle_capability_widget,
    "capability_tool_call": handle_capability_tool_call,
    "capability_workflow": handle_capability_workflow,
    "capability_handoff": handle_capability_handoff,
    # active_workflow 分支
    "workflow_continue": handle_workflow_continue,
}


# ============================================================================
# Executor
# ============================================================================

# ============================================================================
# Conditional execution — 讓 DAG 支援分支
# ============================================================================

def _resolve_field(field: str, ctx: DAGContext):
    """支援 dotted path(如 'intent_rule.action_type')取得 ctx 或 ctx.dict 的值。"""
    parts = field.split(".")
    val: Any = ctx
    for p in parts:
        if val is None:
            return None
        if isinstance(val, dict):
            val = val.get(p)
        else:
            val = getattr(val, p, None)
    return val


def _evaluate_condition(cond: dict, ctx: DAGContext) -> bool:
    """遞迴條件解析器。

    Shape:
      atomic: {"field": "intent_type", "op": "==", "value": "general"}
      compound: {"all": [cond1, cond2, ...]} 或 {"any": [cond1, cond2, ...]}

    支援 op: ==, !=, in, not_in, truthy, falsy。field 支援 dotted path。
    """
    if not cond:
        return True
    if "all" in cond:
        return all(_evaluate_condition(c, ctx) for c in (cond.get("all") or []))
    if "any" in cond:
        return any(_evaluate_condition(c, ctx) for c in (cond.get("any") or []))

    field = cond.get("field")
    if not field:
        return True
    op = cond.get("op", "==")
    expected = cond.get("value")
    actual = _resolve_field(field, ctx)

    if op == "==":
        return actual == expected
    if op == "!=":
        return actual != expected
    if op == "in":
        return actual in (expected or [])
    if op == "not_in":
        return actual not in (expected or [])
    if op == "truthy":
        return bool(actual)
    if op == "falsy":
        return not bool(actual)
    return True


def _topological_order(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Kahn's algorithm — 傳回節點 id 列表。若有循環則傳回已能處理的部分。"""
    incoming: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, set[str]] = defaultdict(set)
    all_ids = {n["id"] for n in nodes}

    for e in edges:
        src = e.get("from")
        dst = e.get("to")
        if src in all_ids and dst in all_ids:
            outgoing[src].add(dst)
            incoming[dst].add(src)

    ready = [nid for nid in all_ids if not incoming[nid]]
    order: list[str] = []
    while ready:
        # 穩定排序：優先無 incoming + 節點定義出現早的
        current = ready.pop(0)
        order.append(current)
        for dest in list(outgoing[current]):
            incoming[dest].discard(current)
            if not incoming[dest]:
                ready.append(dest)
        outgoing[current].clear()

    return order


async def execute_dag(
    dag: dict,
    project_id: str,
    user_message: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    persist: bool = False,
    pre_loaded_history: Optional[list[dict]] = None,
) -> dict:
    """執行一個 DAG 定義。

    生產模式(adapter 呼叫)傳入 session_id + persist=True + pre_loaded_history,
    output 節點會寫入 ait_training_messages。測試模式(/dag/test 端點)不傳,
    handle_load_history 回退成空歷史 stub、handle_output 不落庫。

    Returns:
        {
          "final_text": str,
          "widgets": [...],
          "tool_results": [...],
          "intent_type": str | None,
          "assistant_message_id": str | None,
          "total_tokens_in": int,
          "total_tokens_out": int,
          "trace": [{node_id, label, type_key, status, summary, latency_ms, output}, ...],
          "guardrail_triggered": bool,
        }
    """
    nodes = dag.get("nodes") or []
    edges = dag.get("edges") or []
    node_by_id = {n["id"]: n for n in nodes}
    ctx = DAGContext(
        project_id=project_id,
        user_id=user_id,
        user_message=user_message,
        session_id=session_id,
        persist=persist,
        pre_loaded_history=pre_loaded_history,
    )

    order = _topological_order(nodes, edges)
    trace: list[dict] = []

    for node_id in order:
        node = node_by_id.get(node_id)
        if not node:
            continue
        type_key = node.get("type_key")
        handler = HANDLERS.get(type_key)
        entry = {
            "node_id": node_id,
            "label": node.get("label"),
            "type_key": type_key,
        }
        if not handler:
            entry.update({"status": "skipped", "summary": f"未知節點類型:{type_key}"})
            trace.append(entry)
            continue

        # Conditional execution:condition 不符就 skip(不執行 handler、不記 latency)
        cond = node.get("condition")
        if cond and not _evaluate_condition(cond, ctx):
            entry.update({
                "status": "skipped",
                "summary": f"條件不符:{cond.get('field')} {cond.get('op')} {cond.get('value')}",
                "latency_ms": 0,
            })
            trace.append(entry)
            continue

        start = time.time()
        try:
            result = await handler(node, ctx)
        except Exception as e:
            result = {"status": "error", "error": str(e), "summary": f"節點執行例外:{e}"}
        latency = int((time.time() - start) * 1000)
        entry.update(result)
        entry["latency_ms"] = latency
        trace.append(entry)

        # Fatal error: stop
        if result.get("status") == "error" and type_key in ("call_model", "guardrail"):
            if type_key == "guardrail" and (node.get("config") or {}).get("action") == "block":
                break
            if type_key == "call_model":
                break

    return {
        "final_text": ctx.clean_text or ctx.llm_response_text,
        "widgets": ctx.widgets,
        "tool_results": ctx.tool_results,
        "intent_type": ctx.intent_type,
        "assistant_message_id": ctx.assistant_message_id,
        "response_metadata": ctx.response_metadata,
        "total_tokens_in": ctx.total_tokens_in,
        "total_tokens_out": ctx.total_tokens_out,
        "guardrail_triggered": ctx.guardrail_triggered,
        "trace": trace,
    }
