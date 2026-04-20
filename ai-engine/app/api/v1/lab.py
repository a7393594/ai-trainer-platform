"""
Experiment Studio (Lab) API — 統一 4 源案例 + 覆寫重跑

端點:
  GET  /lab/cases/by-project/{project_id}     — 4 源(pipeline/workflow/session/comparison)統一列表
  POST /lab/rerun                             — 單次 rerun w/ overrides
  POST /lab/batch-rerun                       — N 個 demo inputs 並行跑
  PUT  /lab/runs/{run_id}/overrides           — 持久化 overrides bundle 到 metadata

資料模型: 沿用 ait_pipeline_runs (mode='lab'),metadata 存 source_type + overrides。
Workflow rerun 走 workflow engine,結果關聯回 workflow_runs + parent_run_id。
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.comparison.engine import run_single_prompt_parallel
from app.db import crud
from app.db.supabase import get_supabase

router = APIRouter(prefix="/lab", tags=["experiment-studio"])


# ============================================================================
# Request models
# ============================================================================

class Overrides(BaseModel):
    """可覆寫的四大面向 — 任一可留空表示不覆寫。"""
    prompt_override: Optional[str] = None           # system prompt 文字
    model_override: Optional[str] = None            # model id
    tools_bundle: Optional[list[str]] = None        # tool ids 白名單(None=用預設)
    knowledge_override: Optional[dict] = None       # {doc_ids_include:[...], doc_ids_exclude:[...], backend: 'pgvector'|'qdrant'|'keyword'}
    workflow_steps_override: Optional[list[dict]] = None  # workflow only: 用這組 steps 取代原 workflow def


class RerunRequest(BaseModel):
    source_type: str = Field(..., pattern="^(pipeline|workflow|session|comparison)$")
    source_id: str
    input: Optional[str] = None                     # 若省略,取 source 原始 input
    overrides: Overrides = Field(default_factory=Overrides)
    lab_run_id: Optional[str] = None                # 若有,紀錄 comparison 時掛這個 lab run;無則自動 fork


class BatchRerunRequest(BaseModel):
    source_type: str = Field(..., pattern="^(pipeline|workflow|session|comparison)$")
    source_id: str
    inputs: list[str] = Field(..., min_length=1, max_length=20)
    overrides: Overrides = Field(default_factory=Overrides)
    lab_run_id: Optional[str] = None


class OverridesPatch(BaseModel):
    overrides: Optional[dict] = None
    demo_inputs: Optional[list[str]] = None


# ============================================================================
# GET /lab/cases/by-project/{project_id}
# ============================================================================

@router.get("/cases/by-project/{project_id}")
async def list_cases(
    project_id: str,
    source_type: Optional[str] = Query(default=None, pattern="^(pipeline|workflow|session|comparison)$"),
    limit: int = Query(default=40, ge=1, le=100),
):
    """列出專案的 4 源案例,union + created_at 新到舊。

    回傳:
      { items: [{source_type, id, title, summary, created_at, total_cost_usd?, status?}] }
    """
    try:
        items: list[dict] = []

        want_pipeline = source_type in (None, "pipeline")
        want_workflow = source_type in (None, "workflow")
        want_session = source_type in (None, "session")
        want_comparison = source_type in (None, "comparison")

        if want_pipeline:
            runs = crud.list_pipeline_runs(project_id=project_id, limit=limit) or []
            for r in runs:
                items.append({
                    "source_type": "pipeline",
                    "id": r["id"],
                    "title": (r.get("input_text") or "(empty input)")[:120],
                    "summary": f"{r.get('mode', 'live')} · {r.get('status', '-')}",
                    "created_at": r.get("created_at"),
                    "total_cost_usd": r.get("total_cost_usd"),
                    "status": r.get("status"),
                })

        if want_workflow:
            # Project 下所有 workflow 的 runs 合併
            sb = get_supabase()
            wfs = sb.table("ait_workflows").select("id, name").eq(
                "project_id", project_id
            ).eq("is_active", True).execute().data or []
            wf_map = {w["id"]: w.get("name") for w in wfs}
            if wf_map:
                wf_runs = (
                    sb.table("ait_workflow_runs")
                    .select("id, workflow_id, status, started_at, context_json")
                    .in_("workflow_id", list(wf_map.keys()))
                    .order("started_at", desc=True)
                    .limit(limit)
                    .execute()
                ).data or []
                for r in wf_runs:
                    ctx = r.get("context_json") or {}
                    trace_len = len((ctx or {}).get("_trace") or [])
                    items.append({
                        "source_type": "workflow",
                        "id": r["id"],
                        "title": wf_map.get(r.get("workflow_id")) or "(unnamed workflow)",
                        "summary": f"{r.get('status', '-')} · {trace_len} steps",
                        "created_at": r.get("started_at"),
                        "status": r.get("status"),
                    })

        if want_session:
            sessions = crud.list_sessions(project_id=project_id, limit=limit) or []
            for s in sessions:
                items.append({
                    "source_type": "session",
                    "id": s["id"],
                    "title": f"Session · {s.get('session_type', 'freeform')}",
                    "summary": f"user={s.get('user_id', '')[:8]}",
                    "created_at": s.get("started_at"),
                    "status": "ended" if s.get("ended_at") else "active",
                })

        if want_comparison:
            sb = get_supabase()
            cmp_runs = (
                sb.table("ait_comparison_runs")
                .select("id, name, status, created_at")
                .eq("project_id", project_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            ).data or []
            for r in cmp_runs:
                items.append({
                    "source_type": "comparison",
                    "id": r["id"],
                    "title": r.get("name") or "(untitled comparison)",
                    "summary": r.get("status") or "-",
                    "created_at": r.get("created_at"),
                    "status": r.get("status"),
                })

        # Sort union by created_at desc (treat None as very old)
        items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return {"items": items[: limit * 4]}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to list cases: {e}")


# ============================================================================
# Helpers — source loaders
# ============================================================================

def _load_source_context(source_type: str, source_id: str) -> dict:
    """根據 source 讀出 rerun 需要的 context: project_id + 原始 input + 原始 output/prompt。"""
    sb = get_supabase()
    if source_type == "pipeline":
        run = crud.get_pipeline_run(source_id)
        if not run:
            raise HTTPException(status_code=404, detail="pipeline run not found")
        return {
            "project_id": run["project_id"],
            "session_id": run.get("session_id"),
            "original_input": run.get("input_text") or "",
            "mode": "pipeline",
        }
    if source_type == "workflow":
        row = sb.table("ait_workflow_runs").select("*").eq("id", source_id).execute()
        if not row.data:
            raise HTTPException(status_code=404, detail="workflow run not found")
        wf_run = row.data[0]
        wf = crud.get_workflow(wf_run["workflow_id"])
        if not wf:
            raise HTTPException(status_code=404, detail="workflow def not found")
        return {
            "project_id": wf["project_id"],
            "session_id": wf_run.get("session_id"),
            "workflow_id": wf_run["workflow_id"],
            "workflow_steps": wf.get("steps_json") or [],
            "original_vars": (wf_run.get("context_json") or {}).get("vars") or {},
            "mode": "workflow",
        }
    if source_type == "session":
        session = crud.get_session(source_id)
        if not session:
            raise HTTPException(status_code=404, detail="session not found")
        msgs = crud.list_messages(source_id, limit=200)
        last_user = next((m["content"] for m in reversed(msgs) if m.get("role") == "user"), "")
        return {
            "project_id": session["project_id"],
            "session_id": source_id,
            "original_input": last_user,
            "mode": "session",
        }
    if source_type == "comparison":
        row = sb.table("ait_comparison_runs").select("*").eq("id", source_id).execute()
        if not row.data:
            raise HTTPException(status_code=404, detail="comparison run not found")
        cmp_run = row.data[0]
        questions = cmp_run.get("questions") or []
        first_q = questions[0] if questions else {}
        return {
            "project_id": cmp_run["project_id"],
            "session_id": None,
            "original_input": (first_q.get("text") if isinstance(first_q, dict) else str(first_q)) or "",
            "mode": "comparison",
        }
    raise HTTPException(status_code=400, detail=f"unsupported source_type: {source_type}")


async def _ensure_lab_run(
    source_ctx: dict,
    source_type: str,
    source_id: str,
    provided_lab_run_id: Optional[str],
    overrides: dict,
    demo_inputs: Optional[list[str]] = None,
) -> dict:
    """若前端沒提供 lab_run_id,自動建立一個 mode=lab 的 pipeline run 作為實驗容器。"""
    if provided_lab_run_id:
        existing = crud.get_pipeline_run(provided_lab_run_id)
        if existing:
            return existing

    lab_id = str(uuid.uuid4())
    metadata = {
        "source_type": source_type,
        "source_id": source_id,
        "overrides": overrides,
    }
    if demo_inputs:
        metadata["demo_inputs"] = demo_inputs
    row = {
        "id": lab_id,
        "project_id": source_ctx["project_id"],
        "session_id": source_ctx.get("session_id"),
        "mode": "lab",
        "input_text": source_ctx.get("original_input", ""),
        "nodes_json": {"nodes": [], "edges": []},
        "total_cost_usd": 0,
        "total_duration_ms": 0,
        "parent_run_id": source_id if source_type == "pipeline" else None,
        "metadata": metadata,
        "status": "completed",
    }
    result = get_supabase().table("ait_pipeline_runs").insert(row).execute()
    return result.data[0] if result.data else row


async def _execute_rerun(
    source_type: str,
    source_ctx: dict,
    user_input: str,
    overrides: Overrides,
    lab_run: dict,
) -> dict:
    """單次 rerun 核心: 依 source_type 分派到對應執行器,結果寫 comparisons / workflow_runs。"""
    o = overrides
    project_id = source_ctx["project_id"]

    # Pipeline / Session / Comparison — 單模型呼叫
    if source_type in ("pipeline", "session", "comparison"):
        messages: list[dict] = []
        if o.prompt_override:
            messages.append({"role": "system", "content": o.prompt_override})
        else:
            active = crud.get_active_prompt(project_id)
            if active and active.get("content"):
                messages.append({"role": "system", "content": active["content"]})

        # Optional knowledge context
        if o.knowledge_override:
            rag_text = await _run_knowledge_search(
                project_id, user_input, o.knowledge_override
            )
            if rag_text:
                messages.append({"role": "system", "content": f"以下是相關參考資料：\n\n{rag_text}"})

        messages.append({"role": "user", "content": user_input})

        project = crud.get_project(project_id)
        model = (
            o.model_override
            or (project.get("default_model") if project else None)
            or "claude-sonnet-4-20250514"
        )
        results = await run_single_prompt_parallel(
            messages=messages,
            models=[model],
            project_id=project_id,
            session_id=source_ctx.get("session_id"),
        )
        r = results[0]
        cmp_row = crud.create_pipeline_comparison({
            "pipeline_run_id": lab_run["id"],
            "node_id": f"lab_rerun_{uuid.uuid4().hex[:8]}",
            "model": r["model"],
            "input_prompt": json.dumps(messages, ensure_ascii=False),
            "output_text": r["output_text"] or (r.get("error") or ""),
            "input_tokens": r["input_tokens"],
            "output_tokens": r["output_tokens"],
            "cost_usd": r["cost_usd"],
            "latency_ms": r["latency_ms"],
        })
        return {
            "source_type": source_type,
            "input": user_input,
            "output": r.get("output_text") or "",
            "cost_usd": r.get("cost_usd", 0),
            "latency_ms": r.get("latency_ms", 0),
            "model": r.get("model"),
            "comparison_id": cmp_row.get("id"),
        }

    # Workflow — 走 engine,可選 override steps
    if source_type == "workflow":
        from app.core.workflows.engine import workflow_engine

        initial_vars: dict = dict(source_ctx.get("original_vars") or {})
        initial_vars["message"] = user_input
        if o.tools_bundle is not None:
            initial_vars["_tools_bundle"] = list(o.tools_bundle)
        if o.model_override:
            initial_vars["_model_override"] = o.model_override
        if o.prompt_override:
            initial_vars["_prompt_override"] = o.prompt_override
        if o.workflow_steps_override is not None:
            initial_vars["_steps_override"] = list(o.workflow_steps_override)

        wf_id = source_ctx["workflow_id"]
        result = await workflow_engine.run_to_completion(
            wf_id,
            session_id=source_ctx.get("session_id"),
            user_id=None,
            initial_vars=initial_vars,
        )
        # Tag workflow_runs.context_json.lab_run_id 方便 diff
        try:
            sb = get_supabase()
            row = sb.table("ait_workflow_runs").select("context_json").eq("id", result.get("run_id")).execute()
            if row.data:
                ctx = row.data[0].get("context_json") or {}
                ctx["_lab_run_id"] = lab_run["id"]
                ctx["_lab_source_id"] = source_ctx.get("workflow_id")
                sb.table("ait_workflow_runs").update({"context_json": ctx}).eq(
                    "id", result.get("run_id")
                ).execute()
        except Exception:
            pass
        return {
            "source_type": "workflow",
            "input": user_input,
            "output": json.dumps(result.get("vars") or {}, ensure_ascii=False),
            "trace": result.get("trace") or [],
            "status": result.get("status"),
            "workflow_run_id": result.get("run_id"),
            "error": result.get("error"),
        }

    raise HTTPException(status_code=400, detail=f"unsupported source_type: {source_type}")


async def _run_knowledge_search(
    project_id: str, query: str, knowledge_override: dict
) -> Optional[str]:
    """處理 knowledge override: include/exclude doc_ids + backend 選擇。"""
    try:
        from app.core.rag.pipeline import rag_pipeline

        results = await rag_pipeline.search(project_id, query, top_k=5)
        include = set(knowledge_override.get("doc_ids_include") or [])
        exclude = set(knowledge_override.get("doc_ids_exclude") or [])
        filtered: list[dict] = []
        for r in results:
            doc_id = r.get("doc_id")
            if include and doc_id and doc_id not in include:
                continue
            if exclude and doc_id and doc_id in exclude:
                continue
            filtered.append(r)
        parts = [r.get("content", "") for r in filtered if r.get("content")]
        return "\n\n---\n\n".join(parts) if parts else None
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] knowledge search override failed: {e}")
        return None


# ============================================================================
# POST /lab/rerun
# ============================================================================

@router.post("/rerun")
async def lab_rerun(req: RerunRequest):
    """單次 rerun: 指定 source + overrides,執行一次後寫入 comparison(or workflow_run)。"""
    try:
        source_ctx = _load_source_context(req.source_type, req.source_id)
        user_input = req.input or source_ctx.get("original_input") or ""
        if not user_input and req.source_type != "workflow":
            raise HTTPException(
                status_code=400,
                detail="input required (source has no original input to replay)",
            )

        lab_run = await _ensure_lab_run(
            source_ctx,
            req.source_type,
            req.source_id,
            req.lab_run_id,
            overrides=req.overrides.model_dump(exclude_none=True),
        )
        result = await _execute_rerun(
            req.source_type, source_ctx, user_input, req.overrides, lab_run
        )
        return {"lab_run_id": lab_run["id"], "result": result}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Lab rerun failed: {e}")


# ============================================================================
# POST /lab/batch-rerun
# ============================================================================

@router.post("/batch-rerun")
async def lab_batch_rerun(req: BatchRerunRequest):
    """並行跑 N 個 demo inputs,回傳 matrix。"""
    try:
        source_ctx = _load_source_context(req.source_type, req.source_id)
        lab_run = await _ensure_lab_run(
            source_ctx,
            req.source_type,
            req.source_id,
            req.lab_run_id,
            overrides=req.overrides.model_dump(exclude_none=True),
            demo_inputs=req.inputs,
        )

        tasks = [
            _execute_rerun(req.source_type, source_ctx, inp, req.overrides, lab_run)
            for inp in req.inputs
        ]
        gathered: list[Any] = await asyncio.gather(*tasks, return_exceptions=True)
        results: list[dict] = []
        for inp, g in zip(req.inputs, gathered):
            if isinstance(g, Exception):
                results.append({"input": inp, "error": str(g)})
            else:
                results.append(g)
        return {"lab_run_id": lab_run["id"], "results": results}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Batch rerun failed: {e}")


# ============================================================================
# PUT /lab/runs/{run_id}/overrides
# ============================================================================

@router.put("/runs/{run_id}/overrides")
async def save_overrides(run_id: str, req: OverridesPatch):
    """持久化 overrides 到 lab run 的 metadata.overrides — 方便重整後繼續。"""
    try:
        run = crud.get_pipeline_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="lab run not found")
        if run.get("mode") != "lab":
            raise HTTPException(status_code=400, detail="not a lab run")
        metadata = run.get("metadata") or {}
        if req.overrides is not None:
            metadata["overrides"] = req.overrides
        if req.demo_inputs is not None:
            metadata["demo_inputs"] = req.demo_inputs
        updated = (
            get_supabase().table("ait_pipeline_runs")
            .update({"metadata": metadata})
            .eq("id", run_id)
            .execute()
        )
        return {"run": updated.data[0] if updated.data else None}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Save overrides failed: {e}")
