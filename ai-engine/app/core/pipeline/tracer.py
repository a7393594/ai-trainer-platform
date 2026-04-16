"""
Pipeline Tracer — contextvars 驅動的階段追蹤器

設計重點:
1. 透過 contextvars 隱式傳遞,呼叫端(llm_router / tools / orchestrator)只需取
   current_run() 檢查是否有 run 正在進行,有就寫 span,沒就 no-op。對既有路徑零侵入。
2. 所有階段 span 累積在 PipelineRun.nodes 裡,結束時 finalize() 一次寫入
   ait_pipeline_runs(nodes_json 欄位)。
3. Finalize 走 fire-and-forget(try/except),即使 Supabase 寫入失敗也不影響主流程。

節點類型:
- input    —— 使用者輸入(process())
- process  —— 純程式邏輯(context_loader / router / compose)
- model    —— LLM 呼叫(triage / main_model,支援多次 iteration)
- parallel —— 並行工具呼叫的 parent span
- tool     —— parallel 底下的單一工具 child span
- output   —— 最終回覆 + 總計
"""
from __future__ import annotations

import contextvars
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

_current_run: contextvars.ContextVar[Optional["PipelineRun"]] = contextvars.ContextVar(
    "pipeline_run", default=None
)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _short_id() -> str:
    return uuid.uuid4().hex[:8]


# ============================================================================
# NodeSpan
# ============================================================================

@dataclass
class NodeSpan:
    """單一階段的快照。序列化後存進 ait_pipeline_runs.nodes_json。"""

    id: str
    node_type: str          # input | process | model | parallel | tool | output
    label: str
    started_at_ms: int
    parent_id: Optional[str] = None
    finished_at_ms: Optional[int] = None
    latency_ms: int = 0
    status: str = "running"   # running | ok | error
    model: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    input_ref: Any = None       # 可 JSON 序列化的輸入快照
    output_ref: Any = None      # 可 JSON 序列化的輸出快照
    metadata: dict = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.node_type,
            "label": self.label,
            "parent_id": self.parent_id,
            "started_at_ms": self.started_at_ms,
            "finished_at_ms": self.finished_at_ms,
            "latency_ms": self.latency_ms,
            "status": self.status,
            "model": self.model,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": round(self.cost_usd, 8),
            "input_ref": self.input_ref,
            "output_ref": self.output_ref,
            "metadata": self.metadata,
            "error": self.error,
        }


# ============================================================================
# PipelineRun
# ============================================================================

@dataclass
class PipelineRun:
    """一個 chat turn 對應一個 PipelineRun,結束時 finalize() 寫入資料庫。"""

    id: str
    project_id: str
    session_id: Optional[str]
    input_text: str
    mode: str = "live"          # live | lab
    message_id: Optional[str] = None
    parent_run_id: Optional[str] = None
    triggered_by: Optional[str] = None
    nodes: list[NodeSpan] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)  # (from_id, to_id)
    started_at_ms: int = field(default_factory=_now_ms)
    finalized: bool = False
    status: str = "running"     # running | completed | failed

    def add_span(self, span: NodeSpan) -> NodeSpan:
        self.nodes.append(span)
        return span

    def add_edge(self, from_id: str, to_id: str) -> None:
        self.edges.append((from_id, to_id))

    def connect_to_previous(self, span: NodeSpan) -> None:
        """把新 span 接到最近一個沒有 parent 的同層節點後面。"""
        if not self.nodes:
            return
        prev = None
        for existing in reversed(self.nodes):
            if existing.id == span.id:
                continue
            if existing.parent_id == span.parent_id:
                prev = existing
                break
        if prev is not None:
            self.add_edge(prev.id, span.id)

    def total_cost(self) -> float:
        return round(sum(n.cost_usd for n in self.nodes), 8)

    def total_duration_ms(self) -> int:
        return max(0, _now_ms() - self.started_at_ms)

    def to_nodes_json(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [{"from": f, "to": t} for f, t in self.edges],
        }

    def finalize(self, status: str = "completed") -> None:
        """寫入 ait_pipeline_runs。fire-and-forget(失敗不影響主流程)。"""
        if self.finalized:
            return
        self.finalized = True
        self.status = status
        try:
            from app.db.supabase import get_supabase
            get_supabase().table("ait_pipeline_runs").insert({
                "id": self.id,
                "project_id": self.project_id,
                "session_id": self.session_id,
                "message_id": self.message_id,
                "mode": self.mode,
                "input_text": self.input_text,
                "nodes_json": self.to_nodes_json(),
                "total_cost_usd": self.total_cost(),
                "total_duration_ms": self.total_duration_ms(),
                "parent_run_id": self.parent_run_id,
                "triggered_by": self.triggered_by,
                "status": status,
            }).execute()
        except Exception as e:
            print(f"[pipeline.tracer] finalize failed: {e}")


# ============================================================================
# Context helpers
# ============================================================================

def current_run() -> Optional[PipelineRun]:
    return _current_run.get()


class _PipelineRunContext:
    def __init__(
        self,
        project_id: str,
        session_id: Optional[str],
        input_text: str,
        mode: str = "live",
        parent_run_id: Optional[str] = None,
        triggered_by: Optional[str] = None,
    ):
        self.run = PipelineRun(
            id=str(uuid.uuid4()),
            project_id=project_id,
            session_id=session_id,
            input_text=input_text,
            mode=mode,
            parent_run_id=parent_run_id,
            triggered_by=triggered_by,
        )
        self._token: Optional[contextvars.Token] = None

    async def __aenter__(self) -> PipelineRun:
        self._token = _current_run.set(self.run)
        return self.run

    async def __aexit__(self, exc_type, exc, tb) -> None:
        status = "failed" if exc_type is not None else "completed"
        self.run.finalize(status=status)
        if self._token is not None:
            _current_run.reset(self._token)


def pipeline_run_context(
    project_id: str,
    session_id: Optional[str],
    input_text: str,
    mode: str = "live",
    parent_run_id: Optional[str] = None,
    triggered_by: Optional[str] = None,
) -> _PipelineRunContext:
    """Async context manager — wraps a chat turn and writes one pipeline_run row."""
    return _PipelineRunContext(
        project_id=project_id,
        session_id=session_id,
        input_text=input_text,
        mode=mode,
        parent_run_id=parent_run_id,
        triggered_by=triggered_by,
    )


# ============================================================================
# High-level helpers used by orchestrator / router / tools
# ============================================================================

def start_process_span(
    label: str,
    input_ref: Any = None,
    parent_id: Optional[str] = None,
    node_type: str = "process",
) -> Optional[NodeSpan]:
    """開一個 process/input/output 類型的 span。呼叫端需要自己 finish_span()。"""
    run = current_run()
    if run is None:
        return None
    span = NodeSpan(
        id=_short_id(),
        node_type=node_type,
        label=label,
        started_at_ms=_now_ms(),
        parent_id=parent_id,
        input_ref=input_ref,
    )
    run.add_span(span)
    run.connect_to_previous(span)
    return span


def finish_span(
    span: Optional[NodeSpan],
    output_ref: Any = None,
    status: str = "ok",
    error: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    if span is None:
        return
    span.finished_at_ms = _now_ms()
    span.latency_ms = max(0, span.finished_at_ms - span.started_at_ms)
    span.status = status
    if output_ref is not None:
        span.output_ref = output_ref
    if error is not None:
        span.error = error
    if metadata:
        span.metadata.update(metadata)


def record_llm_span(
    label: str,
    model: str,
    messages: list[dict],
    output_text: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    latency_ms: int,
    metadata: Optional[dict] = None,
) -> Optional[NodeSpan]:
    """由 llm_router.chat_completion() 呼叫 —— 把每次 LLM 呼叫記為 model span。"""
    run = current_run()
    if run is None:
        return None
    now = _now_ms()
    # 輸入快照:保留 messages 但截斷超長 content
    input_snapshot = _snapshot_messages(messages)
    span = NodeSpan(
        id=_short_id(),
        node_type="model",
        label=label,
        started_at_ms=now - latency_ms,
        finished_at_ms=now,
        latency_ms=latency_ms,
        status="ok",
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        input_ref=input_snapshot,
        output_ref={"text": _truncate(output_text, 4000)},
        metadata=metadata or {},
    )
    run.add_span(span)
    run.connect_to_previous(span)
    return span


def record_tool_span(
    tool_name: str,
    params: dict,
    result: Any,
    latency_ms: int,
    status: str = "ok",
    error: Optional[str] = None,
    parent_id: Optional[str] = None,
) -> Optional[NodeSpan]:
    """由 tools.registry.execute_tool_by_name() 呼叫 —— 記一個工具 child span。"""
    run = current_run()
    if run is None:
        return None
    now = _now_ms()
    span = NodeSpan(
        id=_short_id(),
        node_type="tool",
        label=f"tool:{tool_name}",
        started_at_ms=now - latency_ms,
        finished_at_ms=now,
        latency_ms=latency_ms,
        status=status,
        parent_id=parent_id,
        input_ref={"tool": tool_name, "params": params},
        output_ref={"result": _truncate_json(result, 4000)},
        error=error,
    )
    run.add_span(span)
    if parent_id:
        run.add_edge(parent_id, span.id)
    else:
        run.connect_to_previous(span)
    return span


# ============================================================================
# Snapshot utilities (避免 nodes_json 爆炸)
# ============================================================================

def _truncate(text: str, limit: int) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [truncated, {len(text)} chars total]"


def _truncate_json(data: Any, limit: int) -> Any:
    try:
        import json
        serialized = json.dumps(data, ensure_ascii=False)
        if len(serialized) <= limit:
            return data
        return {"_truncated": True, "preview": serialized[:limit] + "..."}
    except Exception:
        return {"_unserializable": True, "repr": _truncate(repr(data), limit)}


def _snapshot_messages(messages: list[dict]) -> list[dict]:
    """把 messages 存成可 JSON 序列化的快照,每則 content 截斷至 4000 字。"""
    out: list[dict] = []
    for m in messages or []:
        if hasattr(m, "model_dump"):
            m = m.model_dump()
        if not isinstance(m, dict):
            try:
                m = dict(m)
            except Exception:
                m = {"role": "unknown", "content": _truncate(repr(m), 4000)}
        entry = {"role": m.get("role", "unknown")}
        content = m.get("content")
        if content is not None:
            if isinstance(content, str):
                entry["content"] = _truncate(content, 4000)
            else:
                entry["content"] = _truncate_json(content, 4000)
        tool_calls = m.get("tool_calls")
        if tool_calls:
            entry["tool_calls"] = _truncate_json(tool_calls, 2000)
        tool_call_id = m.get("tool_call_id")
        if tool_call_id:
            entry["tool_call_id"] = tool_call_id
        out.append(entry)
    return out
