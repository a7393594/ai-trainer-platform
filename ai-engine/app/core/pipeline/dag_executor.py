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
from app.db import crud


# ============================================================================
# Context
# ============================================================================

class DAGContext:
    """節點間傳遞的狀態容器。"""

    def __init__(self, project_id: str, user_id: Optional[str], user_message: str):
        self.project_id = project_id
        self.user_id = user_id
        self.user_message = user_message

        # 狀態欄位（各 node handler 按需讀寫）
        self.history: list[dict] = []
        self.intent_type: Optional[str] = None
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
        self.total_tokens_in: int = 0
        self.total_tokens_out: int = 0
        self.total_cost_usd: float = 0.0
        self.widgets: list[dict] = []
        self.clean_text: str = ""
        self.guardrail_triggered: bool = False


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
    # MVP test mode: 空歷史（測試 DAG 不需要完整 session 上下文）
    ctx.history = []
    return {
        "status": "ok",
        "output": {"history_length": 0, "note": "test mode — empty history"},
        "summary": "測試模式：跳過歷史載入",
    }


async def handle_triage(node: dict, ctx: DAGContext) -> dict:
    # MVP: 固定走 general_chat
    ctx.intent_type = "general"
    return {
        "status": "ok",
        "output": {"intent_type": "general"},
        "summary": "意圖：一般對話",
    }


async def handle_load_knowledge(node: dict, ctx: DAGContext) -> dict:
    cfg = node.get("config") or {}
    rag_limit = int(cfg.get("rag_limit", 5))
    if rag_limit == 0:
        return {"status": "ok", "output": {"skipped": True}, "summary": "RAG 關閉"}

    # Reuse knowledge search if available
    try:
        from app.core.knowledge.retriever import search_knowledge
        chunks = await search_knowledge(
            project_id=ctx.project_id,
            query=ctx.user_message,
            limit=rag_limit,
        )
        if chunks:
            ctx.rag_context = "\n\n".join(c.get("content", "") for c in chunks)
            return {
                "status": "ok",
                "output": {"chunk_count": len(chunks), "total_chars": len(ctx.rag_context)},
                "summary": f"取 {len(chunks)} 個 RAG 片段",
            }
    except Exception as e:
        return {"status": "ok", "output": {"error": str(e)}, "summary": "RAG 檢索失敗（略過）"}

    return {"status": "ok", "output": {"chunk_count": 0}, "summary": "沒有相關知識"}


async def handle_compose_prompt(node: dict, ctx: DAGContext) -> dict:
    cfg = node.get("config") or {}
    prefix = cfg.get("system_prompt_prefix", "") or ""

    # Load active prompt for project
    try:
        active = crud.get_active_prompt(ctx.project_id)
        base_prompt = (active or {}).get("content", "") if active else ""
    except Exception:
        base_prompt = ""

    ctx.system_prompt = (prefix + "\n\n" if prefix else "") + base_prompt

    ctx.messages = []
    if ctx.system_prompt:
        ctx.messages.append({"role": "system", "content": ctx.system_prompt})
    if ctx.rag_context:
        ctx.messages.append({"role": "system", "content": f"參考資料：\n{ctx.rag_context}"})
    ctx.messages.extend(ctx.history)
    ctx.messages.append({"role": "user", "content": ctx.user_message})

    return {
        "status": "ok",
        "output": {
            "message_count": len(ctx.messages),
            "system_prompt_length": len(ctx.system_prompt),
            "has_rag": bool(ctx.rag_context),
            "has_prefix": bool(prefix),
        },
        "summary": f"組出 {len(ctx.messages)} 則訊息（system {len(ctx.system_prompt)} 字）",
    }


async def handle_call_model(node: dict, ctx: DAGContext) -> dict:
    cfg = node.get("config") or {}
    try:
        project = crud.get_project(ctx.project_id)
    except Exception:
        project = None

    ctx.model = (
        cfg.get("model")
        or (project.get("default_model") if project else None)
        or "claude-sonnet-4-20250514"
    )
    ctx.temperature = float(cfg.get("temperature", 0.7))
    ctx.max_tokens = int(cfg.get("max_tokens", 2000))

    # Resolve tools if tool_ids specified
    tool_ids = cfg.get("tool_ids") or []
    tools_payload = None
    if tool_ids and project:
        try:
            all_tools = await tool_registry.list_tools(project.get("tenant_id"))
            selected = [t for t in all_tools if t["id"] in set(tool_ids)]
            ctx.db_tools = selected
            tools_payload = tool_registry.convert_to_llm_tools(selected) if selected else None
            ctx.llm_tools = tools_payload
        except Exception:
            pass

    try:
        start = time.time()
        resp = await chat_completion(
            messages=ctx.messages,
            model=ctx.model,
            temperature=ctx.temperature,
            max_tokens=ctx.max_tokens,
            tools=tools_payload,
            project_id=ctx.project_id,
            span_label=f"dag_exec:{ctx.model}",
        )
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        in_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        out_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        tool_calls = getattr(resp.choices[0].message, "tool_calls", None)

        ctx.llm_response_text = text
        ctx.total_tokens_in += in_tokens
        ctx.total_tokens_out += out_tokens
        ctx.tool_call_count = len(tool_calls) if tool_calls else 0

        latency = int((time.time() - start) * 1000)
        return {
            "status": "ok",
            "output": {
                "text": text[:500] + ("..." if len(text) > 500 else ""),
                "model": ctx.model,
                "tokens_in": in_tokens,
                "tokens_out": out_tokens,
                "latency_ms": latency,
                "has_tool_calls": bool(tool_calls),
            },
            "summary": f"{ctx.model} · 收 {in_tokens} 出 {out_tokens} · {latency}ms",
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "summary": f"模型呼叫失敗：{e}"}


async def handle_execute_tools(node: dict, ctx: DAGContext) -> dict:
    # MVP: 如果主模型沒叫工具就略過；叫了就記錄（完整 loop 在未來版本）
    if ctx.tool_call_count == 0:
        return {"status": "ok", "output": {"iterations": 0}, "summary": "模型未要求呼叫工具"}
    return {
        "status": "ok",
        "output": {"iterations": 1, "note": "MVP: tool loop simplified to single pass"},
        "summary": f"模型要求 {ctx.tool_call_count} 個工具呼叫（MVP 略過實際執行）",
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
        "output": {"widget_count": len(widgets), "clean_length": len(clean)},
        "summary": f"解析出 {len(widgets)} 個 widget",
    }


async def handle_output(node: dict, ctx: DAGContext) -> dict:
    # MVP test mode: 不寫入 ait_training_messages，直接回傳
    final_text = ctx.clean_text or ctx.llm_response_text
    return {
        "status": "ok",
        "output": {
            "final_text": final_text,
            "widget_count": len(ctx.widgets),
            "total_tokens_in": ctx.total_tokens_in,
            "total_tokens_out": ctx.total_tokens_out,
        },
        "summary": f"輸出完成（{len(final_text)} 字）",
    }


# ============================================================================
# Handler registry
# ============================================================================

NodeHandler = Callable[[dict, DAGContext], Awaitable[dict]]

HANDLERS: dict[str, NodeHandler] = {
    "input": handle_input,
    "load_history": handle_load_history,
    "triage": handle_triage,
    "load_knowledge": handle_load_knowledge,
    "compose_prompt": handle_compose_prompt,
    "call_model": handle_call_model,
    "execute_tools": handle_execute_tools,
    "guardrail": handle_guardrail,
    "retry": handle_retry,
    "parse_widget": handle_parse_widget,
    "output": handle_output,
}


# ============================================================================
# Executor
# ============================================================================

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
) -> dict:
    """執行一個 DAG 定義。

    Returns:
        {
          "final_text": str,
          "widgets": [...],
          "total_tokens_in": int,
          "total_tokens_out": int,
          "trace": [{node_id, label, type_key, status, summary, latency_ms, output}, ...],
          "guardrail_triggered": bool,
        }
    """
    nodes = dag.get("nodes") or []
    edges = dag.get("edges") or []
    node_by_id = {n["id"]: n for n in nodes}
    ctx = DAGContext(project_id=project_id, user_id=user_id, user_message=user_message)

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
            entry.update({"status": "skipped", "summary": f"未知節點類型：{type_key}"})
            trace.append(entry)
            continue

        start = time.time()
        try:
            result = await handler(node, ctx)
        except Exception as e:
            result = {"status": "error", "error": str(e), "summary": f"節點執行例外：{e}"}
        latency = int((time.time() - start) * 1000)
        entry.update(result)
        entry["latency_ms"] = latency
        trace.append(entry)

        # Fatal error: stop
        if result.get("status") == "error" and type_key in ("call_model", "guardrail"):
            # Only abort for critical nodes; soft failures continue
            if type_key == "guardrail" and (node.get("config") or {}).get("action") == "block":
                break
            if type_key == "call_model":
                break

    return {
        "final_text": ctx.clean_text or ctx.llm_response_text,
        "widgets": ctx.widgets,
        "total_tokens_in": ctx.total_tokens_in,
        "total_tokens_out": ctx.total_tokens_out,
        "guardrail_triggered": ctx.guardrail_triggered,
        "trace": trace,
    }
