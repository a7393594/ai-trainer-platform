"""
Pipeline Studio API — v2.2

Live Mode(MVP):
- GET    /pipeline/runs/by-project/{project_id}                — 列出最近的 pipeline runs
- GET    /pipeline/runs/detail/{run_id}                        — 取單一 run 完整內容 + 所有 node 比較候選

Lab Mode(v1):
- POST   /pipeline/runs/lab                                    — fork 一個 Live run 成 Lab run
- POST   /pipeline/runs/{run_id}/nodes/{node_id}/compare       — 針對某節點平行呼叫多個模型
- POST   /pipeline/runs/{run_id}/nodes/{node_id}/rerun         — 單節點重跑
- POST   /pipeline/runs/{run_id}/nodes/{node_id}/select        — 把某 comparison 標記為選用
- POST   /pipeline/comparisons/{comparison_id}/save-as-prompt  — 存為新的 ait_prompt_versions

v2 新增:
- POST   /pipeline/comparisons/{comparison_id}/score           — 自動評分(Haiku judge)
- POST   /pipeline/comparisons/{comparison_id}/save-as-test-case — 存為 eval test case
- DELETE /pipeline/runs/{run_id}                               — 刪除 lab run(live run 不允許)
"""
import json
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.comparison.engine import run_single_prompt_parallel
from app.db import crud
from app.db.supabase import get_supabase

router = APIRouter(prefix="/pipeline", tags=["pipeline-studio"])


# ============================================================================
# Request models
# ============================================================================

class LabRunRequest(BaseModel):
    project_id: str
    seed_run_id: Optional[str] = None  # 若提供,從該 Live run fork
    input_text: Optional[str] = None   # 不 fork 時的使用者輸入
    triggered_by: Optional[str] = None


class CompareRequest(BaseModel):
    models: list[str]
    prompt_override: Optional[list[dict]] = None  # 可覆寫 messages


class RerunRequest(BaseModel):
    model_override: Optional[str] = None
    prompt_override: Optional[list[dict]] = None
    # Batch 4A: extended config overrides
    temperature_override: Optional[float] = None
    max_tokens_override: Optional[int] = None
    tool_ids: Optional[list[str]] = None  # whitelist of tool IDs for this rerun
    preset_name: Optional[str] = None  # label stored with the comparison


class PresetCreateRequest(BaseModel):
    project_id: str
    node_type: str  # typically 'model'
    name: str
    description: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tool_ids: Optional[list[str]] = None


class SelectRequest(BaseModel):
    comparison_id: str


class SaveAsPromptRequest(BaseModel):
    change_notes: Optional[str] = None


class ScoreRequest(BaseModel):
    judge_model: Optional[str] = None
    principles: Optional[str] = None
    force_rescore: bool = False


class SaveAsTestCaseRequest(BaseModel):
    category: Optional[str] = None
    tags: Optional[list[str]] = None


# ============================================================================
# GET /pipeline/runs/by-project/{project_id}
# ============================================================================
# Note: we namespace under /runs/by-project/ to avoid collision with the
# literal routes /runs/lab, /runs/{run_id}/nodes/..., etc. A bare
# /runs/{project_id} would swallow POST /runs/lab and return 405.

@router.get("/runs/by-project/{project_id}")
async def list_runs(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    mode: Optional[str] = Query(default=None, pattern="^(live|lab)$"),
    cursor: Optional[str] = Query(default=None, description="ISO timestamp; 回傳早於此時間的 runs"),
):
    """列出某專案的 pipeline runs,新到舊排序,支援 cursor 分頁。"""
    try:
        runs = crud.list_pipeline_runs(
            project_id=project_id,
            limit=limit,
            mode=mode,
            cursor_created_at=cursor,
        )
        next_cursor = runs[-1]["created_at"] if len(runs) == limit else None
        return {
            "runs": runs,
            "next_cursor": next_cursor,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list runs: {e}")


# ============================================================================
# GET /pipeline/runs/detail/{run_id}
# ============================================================================

@router.get("/runs/detail/{run_id}")
async def get_run_detail(run_id: str):
    """取單一 pipeline run 完整內容,包含 nodes_json 與所有節點的比較候選。"""
    try:
        run = crud.get_pipeline_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Pipeline run not found")
        comparisons = crud.list_pipeline_comparisons(run_id)
        # 依 node_id 分組方便前端使用
        by_node: dict = {}
        for cmp in comparisons:
            by_node.setdefault(cmp["node_id"], []).append(cmp)
        return {
            "run": run,
            "comparisons_by_node": by_node,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get run: {e}")


@router.get("/runs/by-message/{message_id}")
async def get_run_by_message(message_id: str):
    """依 message_id 查對應的 pipeline run（供 history 頁面展開 trace 用）。"""
    try:
        run = crud.get_pipeline_run_by_message(message_id)
        if not run:
            raise HTTPException(status_code=404, detail="No pipeline run for this message")
        comparisons = crud.list_pipeline_comparisons(run["id"])
        by_node: dict = {}
        for cmp in comparisons:
            by_node.setdefault(cmp["node_id"], []).append(cmp)
        return {"run": run, "comparisons_by_node": by_node}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get run: {e}")


# ============================================================================
# Helpers
# ============================================================================

def _find_node(run: dict, node_id: str) -> Optional[dict]:
    for n in (run.get("nodes_json") or {}).get("nodes", []):
        if n.get("id") == node_id:
            return n
    return None


def _messages_from_node(node: dict) -> list[dict]:
    """從 node 的 input_ref 還原出可直接餵給 chat_completion 的 messages 列表。"""
    input_ref = node.get("input_ref")
    if isinstance(input_ref, list):
        # model span stores messages as a list
        out: list[dict] = []
        for m in input_ref:
            if not isinstance(m, dict):
                continue
            out.append(
                {
                    "role": m.get("role", "user"),
                    "content": m.get("content", ""),
                }
            )
        return out
    return []


# ============================================================================
# POST /pipeline/runs/lab  (v1)
# ============================================================================

@router.post("/runs/lab")
async def create_lab_run(req: LabRunRequest):
    """建立一個 Lab Mode 的 pipeline run。

    - 若提供 seed_run_id,從該 Live run fork 出一個 Lab 副本(nodes_json 整個複製)
    - 否則只建一個空殼(input_text 必填),讓使用者稍後在前端一步步比較/重跑
    """
    try:
        if req.seed_run_id:
            parent = crud.get_pipeline_run(req.seed_run_id)
            if not parent:
                raise HTTPException(
                    status_code=404, detail=f"seed run {req.seed_run_id} not found"
                )
            lab_id = str(uuid.uuid4())
            row = {
                "id": lab_id,
                "project_id": parent["project_id"],
                "session_id": parent.get("session_id"),
                "message_id": None,
                "mode": "lab",
                "input_text": parent.get("input_text", ""),
                "nodes_json": parent.get("nodes_json") or {"nodes": [], "edges": []},
                "total_cost_usd": parent.get("total_cost_usd", 0),
                "total_duration_ms": parent.get("total_duration_ms", 0),
                "parent_run_id": parent["id"],
                "triggered_by": req.triggered_by,
                "status": "completed",
            }
        else:
            if not req.input_text:
                raise HTTPException(
                    status_code=400,
                    detail="input_text is required when seed_run_id is not provided",
                )
            lab_id = str(uuid.uuid4())
            row = {
                "id": lab_id,
                "project_id": req.project_id,
                "mode": "lab",
                "input_text": req.input_text,
                "nodes_json": {"nodes": [], "edges": []},
                "total_cost_usd": 0,
                "total_duration_ms": 0,
                "parent_run_id": None,
                "triggered_by": req.triggered_by,
                "status": "completed",
            }
        result = get_supabase().table("ait_pipeline_runs").insert(row).execute()
        created = result.data[0] if result.data else row
        return {"run": created}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create lab run: {e}")


# ============================================================================
# POST /pipeline/runs/{run_id}/nodes/{node_id}/compare  (v1)
# ============================================================================

@router.post("/runs/{run_id}/nodes/{node_id}/compare")
async def compare_node(run_id: str, node_id: str, req: CompareRequest):
    """在某個 model 節點上同時跑多個模型,記錄為 ait_pipeline_node_comparisons。

    需求:
    - node 必須存在於 run 的 nodes_json 中
    - node.type 必須為 model(否則 400)
    - models 至少 1 個,最多 4 個
    """
    try:
        run = crud.get_pipeline_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Pipeline run not found")
        node = _find_node(run, node_id)
        if not node:
            raise HTTPException(
                status_code=404, detail=f"Node {node_id} not found in run"
            )
        if node.get("type") != "model":
            raise HTTPException(
                status_code=400,
                detail="Compare only available on model-type nodes",
            )
        if not req.models or len(req.models) < 1:
            raise HTTPException(status_code=400, detail="At least 1 model required")
        if len(req.models) > 4:
            raise HTTPException(status_code=400, detail="Max 4 models per compare")

        # 決定送去的 messages
        messages = req.prompt_override or _messages_from_node(node)
        if not messages:
            raise HTTPException(
                status_code=400,
                detail="No messages to replay (node has no input_ref)",
            )

        results = await run_single_prompt_parallel(
            messages=messages,
            models=req.models,
            project_id=run["project_id"],
            session_id=run.get("session_id"),
        )

        # 把結果寫入 ait_pipeline_node_comparisons
        input_prompt_serialized = json.dumps(messages, ensure_ascii=False)
        created_rows: list[dict] = []
        for r in results:
            row = crud.create_pipeline_comparison(
                {
                    "pipeline_run_id": run_id,
                    "node_id": node_id,
                    "model": r["model"],
                    "input_prompt": input_prompt_serialized,
                    "output_text": r["output_text"] or (r.get("error") or ""),
                    "input_tokens": r["input_tokens"],
                    "output_tokens": r["output_tokens"],
                    "cost_usd": r["cost_usd"],
                    "latency_ms": r["latency_ms"],
                }
            )
            created_rows.append(row)
        return {"comparisons": created_rows}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Compare failed: {e}")


# ============================================================================
# POST /pipeline/runs/{run_id}/nodes/{node_id}/rerun  (v1)
# ============================================================================

@router.post("/runs/{run_id}/nodes/{node_id}/rerun")
async def rerun_node(run_id: str, node_id: str, req: RerunRequest):
    """單節點重跑:用覆寫後的 prompt / model 重呼叫 LLM,寫成一個新的 comparison 候選。

    等同於 compare(models=[one_model], prompt_override=..)。
    """
    try:
        run = crud.get_pipeline_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Pipeline run not found")
        node = _find_node(run, node_id)
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
        if node.get("type") != "model":
            raise HTTPException(
                status_code=400,
                detail="Rerun only available on model-type nodes",
            )

        model = req.model_override or node.get("model") or "claude-sonnet-4-20250514"
        messages = req.prompt_override or _messages_from_node(node)
        if not messages:
            raise HTTPException(
                status_code=400, detail="No messages to replay"
            )

        # Batch 4A: resolve tools if tool_ids provided
        tools_payload = None
        if req.tool_ids:
            try:
                from app.core.tools.registry import tool_registry
                project = crud.get_project(run["project_id"])
                tenant_id = project.get("tenant_id") if project else None
                if tenant_id:
                    all_tools = await tool_registry.list_tools(tenant_id)
                    selected = [t for t in all_tools if t["id"] in set(req.tool_ids)]
                    tools_payload = tool_registry.convert_to_llm_tools(selected) if selected else None
            except Exception:
                tools_payload = None  # tool loading failure shouldn't block rerun

        results = await run_single_prompt_parallel(
            messages=messages,
            models=[model],
            project_id=run["project_id"],
            session_id=run.get("session_id"),
            temperature=req.temperature_override if req.temperature_override is not None else 0.7,
            max_tokens=req.max_tokens_override if req.max_tokens_override is not None else 2000,
            tools=tools_payload,
        )
        r = results[0]
        row = crud.create_pipeline_comparison(
            {
                "pipeline_run_id": run_id,
                "node_id": node_id,
                "model": r["model"],
                "input_prompt": json.dumps(messages, ensure_ascii=False),
                "output_text": r["output_text"] or (r.get("error") or ""),
                "input_tokens": r["input_tokens"],
                "output_tokens": r["output_tokens"],
                "cost_usd": r["cost_usd"],
                "latency_ms": r["latency_ms"],
                # Batch 4A: persist config used
                "temperature": req.temperature_override,
                "max_tokens": req.max_tokens_override,
                "tool_ids": req.tool_ids or None,
                "preset_name": req.preset_name,
            }
        )
        return {"comparison": row}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rerun failed: {e}")


# ============================================================================
# POST /pipeline/runs/{run_id}/nodes/{node_id}/select  (v1)
# ============================================================================

@router.post("/runs/{run_id}/nodes/{node_id}/select")
async def select_comparison(run_id: str, node_id: str, req: SelectRequest):
    """把某 comparison 標記為該節點的選用候選。"""
    try:
        # 驗證 comparison 屬於這個 run/node
        sb = get_supabase()
        row = (
            sb.table("ait_pipeline_node_comparisons")
            .select("*")
            .eq("id", req.comparison_id)
            .execute()
        )
        if not row.data:
            raise HTTPException(status_code=404, detail="Comparison not found")
        rec = row.data[0]
        if rec["pipeline_run_id"] != run_id or rec["node_id"] != node_id:
            raise HTTPException(
                status_code=400,
                detail="Comparison does not belong to this run/node",
            )
        updated = crud.select_pipeline_comparison(req.comparison_id)
        return {"comparison": updated}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Select failed: {e}")


# ============================================================================
# POST /pipeline/comparisons/{comparison_id}/save-as-prompt  (v1)
# ============================================================================

@router.post("/comparisons/{comparison_id}/save-as-prompt")
async def save_comparison_as_prompt(comparison_id: str, req: SaveAsPromptRequest):
    """把某 comparison 的 system prompt 存為新的 ait_prompt_versions。

    提取邏輯:從 input_prompt(messages JSON 字串)裡找第一個 role=system 的 content。
    """
    try:
        sb = get_supabase()
        row = (
            sb.table("ait_pipeline_node_comparisons")
            .select("*")
            .eq("id", comparison_id)
            .execute()
        )
        if not row.data:
            raise HTTPException(status_code=404, detail="Comparison not found")
        cmp_row = row.data[0]

        # Parse input_prompt 找到 system message
        try:
            messages = json.loads(cmp_row["input_prompt"])
        except Exception:
            raise HTTPException(
                status_code=400, detail="Failed to parse input_prompt JSON"
            )
        system_content = None
        for m in messages:
            if m.get("role") == "system":
                system_content = m.get("content", "")
                break
        if not system_content:
            raise HTTPException(
                status_code=400,
                detail="No system prompt found in the comparison's input_prompt",
            )

        # 取得 run → project_id
        run = crud.get_pipeline_run(cmp_row["pipeline_run_id"])
        if not run:
            raise HTTPException(status_code=404, detail="Parent pipeline run not found")
        project_id = run["project_id"]

        # 計算下一個 version 號(目前最大 + 1)
        latest = (
            sb.table("ait_prompt_versions")
            .select("version")
            .eq("project_id", project_id)
            .order("version", desc=True)
            .limit(1)
            .execute()
        )
        next_version = ((latest.data[0]["version"] if latest.data else 0) or 0) + 1

        # 建立 prompt version(不啟用)
        new_prompt = crud.create_prompt_version(
            project_id=project_id,
            content=system_content,
            version=next_version,
            is_active=False,
            change_notes=req.change_notes
            or f"Saved from Pipeline Studio comparison {comparison_id}",
        )

        # 回寫 comparison.prompt_version_id
        if new_prompt:
            sb.table("ait_pipeline_node_comparisons").update(
                {"prompt_version_id": new_prompt["id"]}
            ).eq("id", comparison_id).execute()

        return {"prompt_version": new_prompt}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Save as prompt failed: {e}")


# ============================================================================
# POST /pipeline/comparisons/{comparison_id}/score  (v2)
# ============================================================================

@router.post("/comparisons/{comparison_id}/score")
async def score_comparison(comparison_id: str, req: ScoreRequest):
    """用 Haiku judge 自動評分某 comparison(0-100)。

    冪等:若已有 score 且未指定 force_rescore,直接回傳既有分數。
    """
    try:
        sb = get_supabase()
        row = (
            sb.table("ait_pipeline_node_comparisons")
            .select("*")
            .eq("id", comparison_id)
            .execute()
        )
        if not row.data:
            raise HTTPException(status_code=404, detail="Comparison not found")
        cmp_row = row.data[0]

        # 冪等短路
        if cmp_row.get("score") is not None and not req.force_rescore:
            return {"comparison": cmp_row, "cached": True}

        # 取上層 run 的 input_text(使用者問題)
        run = crud.get_pipeline_run(cmp_row["pipeline_run_id"])
        if not run:
            raise HTTPException(status_code=404, detail="Parent run not found")
        question = run.get("input_text", "")

        from app.core.eval.engine import eval_engine

        judge_model = req.judge_model or "claude-haiku-4-5-20251001"
        score, reason, used_model = await eval_engine.judge_quality(
            question=question,
            response=cmp_row.get("output_text", ""),
            principles=req.principles or "",
            judge_model=judge_model,
        )

        updated = (
            sb.table("ait_pipeline_node_comparisons")
            .update(
                {
                    "score": score,
                    "score_reason": reason,
                    "score_model": used_model,
                }
            )
            .eq("id", comparison_id)
            .execute()
        )
        return {
            "comparison": updated.data[0] if updated.data else None,
            "cached": False,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Score failed: {e}")


# ============================================================================
# POST /pipeline/comparisons/{comparison_id}/save-as-test-case  (v2)
# ============================================================================

@router.post("/comparisons/{comparison_id}/save-as-test-case")
async def save_comparison_as_test_case(
    comparison_id: str, req: SaveAsTestCaseRequest
):
    """把某 comparison 存進 ait_eval_test_cases,讓後續 Eval Engine 可以重用。

    test case 的 input = 該 run 的使用者輸入;expected = comparison.output_text
    """
    try:
        sb = get_supabase()
        row = (
            sb.table("ait_pipeline_node_comparisons")
            .select("*")
            .eq("id", comparison_id)
            .execute()
        )
        if not row.data:
            raise HTTPException(status_code=404, detail="Comparison not found")
        cmp_row = row.data[0]

        run = crud.get_pipeline_run(cmp_row["pipeline_run_id"])
        if not run:
            raise HTTPException(status_code=404, detail="Parent run not found")

        data: dict = {
            "project_id": run["project_id"],
            "input_text": run.get("input_text", ""),
            "expected_output": cmp_row.get("output_text", ""),
            "category": req.category or "from_pipeline_studio",
        }
        if req.tags:
            data["tags"] = req.tags

        created = (
            sb.table("ait_eval_test_cases").insert(data).execute()
        )
        return {"test_case": created.data[0] if created.data else None}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Save as test case failed: {e}"
        )


# ============================================================================
# DELETE /pipeline/runs/{run_id}  (v2)
# ============================================================================

@router.delete("/runs/{run_id}")
async def delete_pipeline_run(run_id: str):
    """刪除一個 pipeline run。

    安全保護:只允許刪除 mode=lab 的 run,live run 一律拒絕(保留歷史軌跡)。
    comparisons 會透過 ON DELETE CASCADE 一併刪除。
    """
    try:
        run = crud.get_pipeline_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Pipeline run not found")
        if run.get("mode") != "lab":
            raise HTTPException(
                status_code=403,
                detail="Only lab runs can be deleted (live runs are protected)",
            )
        sb = get_supabase()
        sb.table("ait_pipeline_runs").delete().eq("id", run_id).execute()
        return {"deleted": run_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")


# ============================================================================
# Batch 4A: Rerun Presets — 儲存/讀取節點配置預設
# ============================================================================

@router.get("/presets")
async def list_presets(
    project_id: str = Query(..., description="Project ID"),
    node_type: Optional[str] = Query(None, description="Filter by node type"),
):
    """列出專案的 rerun presets。"""
    try:
        presets = crud.list_rerun_presets(project_id, node_type)
        return {"presets": presets}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"List presets failed: {e}")


@router.post("/presets")
async def create_preset(req: PresetCreateRequest):
    """建立新的 rerun preset。"""
    try:
        data = {
            "project_id": req.project_id,
            "node_type": req.node_type,
            "name": req.name,
            "description": req.description,
            "model": req.model,
            "system_prompt": req.system_prompt,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            "tool_ids": req.tool_ids or [],
        }
        preset = crud.create_rerun_preset(data)
        return {"preset": preset}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Create preset failed: {e}")


@router.delete("/presets/{preset_id}")
async def delete_preset(preset_id: str):
    """刪除 preset。"""
    try:
        crud.delete_rerun_preset(preset_id)
        return {"deleted": preset_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete preset failed: {e}")
