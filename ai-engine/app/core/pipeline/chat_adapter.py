"""DAG-backed /chat endpoint adapter.

當 `settings.use_dag_executor_for_chat=True` 時,api/v1/__init__.py 的 /chat 端點
會呼叫這裡的 `process_via_dag()`,讓生產流量走 DAG Executor 而非 orchestrator。

職責:
  1. Mirror orchestrator.process() 的 session 管理與 user_msg 落庫
  2. 預載 history(含壓縮)傳給 DAG
  3. 確保 project 有 active DAG — 沒有就懶建立一份 14 節點預設 DAG
  4. 包 pipeline_run_context 讓 Pipeline Studio 追蹤到這一輪
  5. 把 execute_dag 的 dict 結果轉成 ChatResponse

capability_rule 與 active_workflow 分支由 DAG 內的 capability_* 節點處理;
general 分支走 load_knowledge → compose_prompt → call_model → execute_tools → parse_widget。
"""
from typing import Optional
from fastapi import HTTPException

from app.models.schemas import ChatRequest, ChatResponse, ChatMessage, Role
from app.core.orchestrator import history as _history
from app.core.orchestrator.constants import DEMO_USER_EMAIL
from app.core.pipeline.tracer import pipeline_run_context, current_run
from app.core.pipeline.dag_executor import execute_dag
from app.db import crud


async def process_via_dag(request: ChatRequest, progress_sink: Optional[object] = None) -> ChatResponse:
    """/chat 的 DAG 替代路徑。

    若 progress_sink (asyncio.Queue) 傳入，DAG 的 call_model 會推
    plan/tool/synthesis 進度事件（給 /chat/stream 即時串流）。
    """
    # 1. 解析 user_id
    user_id = request.user_id
    if not user_id:
        demo_user = crud.get_user_by_email(DEMO_USER_EMAIL)
        if demo_user:
            user_id = demo_user["id"]
        else:
            raise HTTPException(status_code=400, detail="找不到 demo user,請先執行 seed")

    # 2. 解析或建立 session
    session_id = request.session_id
    if not session_id:
        session = await _create_session(request.project_id, user_id)
        session_id = session["id"]

    # 3. 預載 history(排除最後一條 user — DAG 的 compose_prompt 會自己加 current message)
    history = await _history.load_history(session_id, exclude_last_user=True)

    # 4. 存 user_msg(與 orchestrator agent.py:462-466 對齊)
    try:
        crud.create_message(session_id=session_id, role="user", content=request.message)
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] chat_adapter: create user_msg failed: {e}")

    # 5. 取 active DAG — 沒就懶建立
    dag = await ensure_active_dag(request.project_id)

    # 5b. 解析 tenant_id（給 model_call handler 找 per-tenant provider key）
    tenant_id_for_dag: Optional[str] = None
    try:
        proj = crud.get_project(request.project_id)
        tenant_id_for_dag = (proj or {}).get("tenant_id")
    except Exception:
        tenant_id_for_dag = None

    # 6. 包 pipeline_run_context,讓 Pipeline Studio 追蹤此輪
    async with pipeline_run_context(
        project_id=request.project_id,
        session_id=session_id,
        input_text=request.message,
        mode="live",
        triggered_by=user_id,
    ):
        result = await execute_dag(
            dag=dag,
            project_id=request.project_id,
            user_message=request.message,
            user_id=user_id,
            session_id=session_id,
            persist=True,
            pre_loaded_history=history,
            progress_sink=progress_sink,
            mode_prompt=request.mode_prompt,
            tenant_id=tenant_id_for_dag,
        )
        # 對齊 agent.py:150-152：把 assistant_message_id 連結回 pipeline run
        run = current_run()
        if run is not None and result.get("assistant_message_id"):
            run.message_id = result["assistant_message_id"]

    # 7. 組 ChatResponse
    final_text = result.get("final_text") or ""
    return ChatResponse(
        session_id=session_id,
        message=ChatMessage(role=Role.ASSISTANT, content=final_text),
        message_id=result.get("assistant_message_id"),
        widgets=result.get("widgets") or [],
        tool_results=result.get("tool_results") or [],
        metadata=result.get("response_metadata") or {},
    )


async def _create_session(project_id: str, user_id: str) -> dict:
    """與 AgentOrchestrator._create_session 同邏輯(plan limit enforcement + create)。"""
    from app.core.plan.limits import plan_limits_service

    project = crud.get_project(project_id)
    tenant_id = (project or {}).get("tenant_id")
    if tenant_id:
        try:
            plan_limits_service.enforce_session_create(tenant_id)
        except Exception as e:  # noqa: BLE001
            if e.__class__.__name__ == "LimitExceeded":
                raise
    return crud.create_session(project_id, user_id, "freeform")


# ============================================================================
# Active DAG 懶建立
# ============================================================================

async def ensure_active_dag(project_id: str) -> dict:
    """取得 project 的 active DAG;沒有就建一份預設並啟用。"""
    dag = crud.get_active_dag(project_id)
    if dag:
        return dag
    return _seed_default_dag(project_id)


def _seed_default_dag(project_id: str) -> dict:
    """建立一份標準 14 節點 DAG 並啟用。

    結構:
      input → load_history → triage
                                ├→ capability_widget   (intent_type==capability_rule & action_type==widget)
                                ├→ capability_tool     (intent_type==capability_rule & action_type==tool_call)
                                ├→ capability_workflow (intent_type==capability_rule & action_type==workflow)
                                ├→ capability_handoff  (intent_type==capability_rule & action_type==handoff)
                                ├→ workflow_continue   (intent_type==active_workflow)
                                └→ load_knowledge      (not capability_handled)
                                    → compose_prompt
                                    → call_model
                                    → execute_tools
                                    → parse_widget
                                    → output
    """
    def _cap_cond(action_type: str) -> dict:
        return {"all": [
            {"field": "intent_type", "op": "==", "value": "capability_rule"},
            {"field": "intent_rule.action_type", "op": "==", "value": action_type},
        ]}

    not_handled = {"field": "capability_handled", "op": "falsy"}

    nodes = [
        {"id": "n_input", "type_key": "input", "label": "使用者輸入"},
        {"id": "n_history", "type_key": "load_history", "label": "載入歷史"},
        {"id": "n_triage", "type_key": "triage", "label": "意圖分類"},

        # Capability branches
        {"id": "n_cap_widget", "type_key": "capability_widget", "label": "Widget 規則",
         "condition": _cap_cond("widget")},
        {"id": "n_cap_tool", "type_key": "capability_tool_call", "label": "Tool Call 規則",
         "condition": _cap_cond("tool_call")},
        {"id": "n_cap_workflow", "type_key": "capability_workflow", "label": "Workflow 規則",
         "condition": _cap_cond("workflow")},
        {"id": "n_cap_handoff", "type_key": "capability_handoff", "label": "Handoff 規則",
         "condition": _cap_cond("handoff")},
        {"id": "n_workflow_continue", "type_key": "workflow_continue", "label": "繼續工作流",
         "condition": {"field": "intent_type", "op": "==", "value": "active_workflow"}},

        # General chat chain(僅當 capability 沒接手時)
        {"id": "n_knowledge", "type_key": "load_knowledge", "label": "RAG 檢索",
         "condition": not_handled, "config": {"rag_limit": 5}},
        {"id": "n_prompt", "type_key": "compose_prompt", "label": "組 Prompt",
         "condition": not_handled},
        {"id": "n_model", "type_key": "call_model", "label": "主模型",
         "condition": not_handled, "config": {"max_iterations": 20}},
        {"id": "n_tools", "type_key": "execute_tools", "label": "工具結果",
         "condition": not_handled},
        {"id": "n_widget", "type_key": "parse_widget", "label": "Widget 解析",
         "condition": not_handled},

        # Output 永遠執行(有 final_text 才會真寫庫)
        {"id": "n_output", "type_key": "output", "label": "輸出"},
    ]

    edges = [
        {"from": "n_input", "to": "n_history"},
        {"from": "n_history", "to": "n_triage"},
        # triage 分叉 → 五個 capability 分支
        {"from": "n_triage", "to": "n_cap_widget"},
        {"from": "n_triage", "to": "n_cap_tool"},
        {"from": "n_triage", "to": "n_cap_workflow"},
        {"from": "n_triage", "to": "n_cap_handoff"},
        {"from": "n_triage", "to": "n_workflow_continue"},
        # general 鏈接在所有 capability 分支之後(topo sort 會讓 capability 先跑完)
        {"from": "n_cap_widget", "to": "n_knowledge"},
        {"from": "n_cap_tool", "to": "n_knowledge"},
        {"from": "n_cap_workflow", "to": "n_knowledge"},
        {"from": "n_cap_handoff", "to": "n_knowledge"},
        {"from": "n_workflow_continue", "to": "n_knowledge"},
        {"from": "n_knowledge", "to": "n_prompt"},
        {"from": "n_prompt", "to": "n_model"},
        {"from": "n_model", "to": "n_tools"},
        {"from": "n_tools", "to": "n_widget"},
        # 所有路徑最終進 output
        {"from": "n_widget", "to": "n_output"},
        {"from": "n_cap_widget", "to": "n_output"},
        {"from": "n_cap_tool", "to": "n_output"},
        {"from": "n_cap_workflow", "to": "n_output"},
        {"from": "n_cap_handoff", "to": "n_output"},
        {"from": "n_workflow_continue", "to": "n_output"},
    ]

    return crud.create_dag(
        project_id=project_id,
        name="Default production chat DAG",
        nodes=nodes,
        edges=edges,
        description="Auto-seeded by chat_adapter when use_dag_executor_for_chat=True",
        activate=True,
    )
