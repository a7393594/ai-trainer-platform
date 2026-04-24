"""
API v1 路由 — 所有對外端點
"""
import json
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from app.models.schemas import (
    ChatRequest, ChatResponse,
    FeedbackRequest,
    WidgetResponse,
    DocumentUploadRequest,
    ToolDefinition,
    CapabilityRule,
    TestCaseRequest, EvalRunResult,
    OnboardingStartRequest, OnboardingAnswerRequest, OnboardingProgress,
    DemoContext, ProjectSummary,
)
from app.core.orchestrator.agent import AgentOrchestrator
from app.core.orchestrator.onboarding import OnboardingManager
from app.core.prompt.optimizer import PromptOptimizer
from app.config import settings
from app.db import crud

router = APIRouter()
orchestrator = AgentOrchestrator()
onboarding_mgr = OnboardingManager()
prompt_optimizer = PromptOptimizer()


# ============================================
# Demo Context
# ============================================

@router.get("/demo/context", response_model=DemoContext)
async def get_demo_context(email: str = Query(default=None)):
    """取得用戶的 context（支援 auth email 或 fallback demo）"""
    lookup_email = email or "demo@ai-trainer.dev"
    user = crud.get_user_by_email(lookup_email)

    if not user and email:
        # Auto-provision: create ait_user for new auth user
        # Use demo tenant for now
        demo = crud.get_user_by_email("demo@ai-trainer.dev")
        if demo:
            user = crud.create_user(
                tenant_id=demo["tenant_id"],
                email=email,
                role="trainer",
                display_name=email.split("@")[0],
            )

    if not user:
        raise HTTPException(status_code=404, detail="User not found. Run seed first.")

    projects = crud.list_projects(user["tenant_id"])
    if not projects:
        raise HTTPException(status_code=404, detail="No projects found")

    # Default to first trainer project (backwards compat)
    default = next((p for p in projects if p.get("project_type") == "trainer"), projects[0])

    return DemoContext(
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        project_id=default["id"],
        project_name=default["name"],
        projects=[
            ProjectSummary(
                id=p["id"], name=p["name"],
                project_type=p.get("project_type", "trainer"),
                description=p.get("description"),
            )
            for p in projects
        ],
    )


# ============================================
# 對話（核心端點）
# ============================================

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """核心對話端點。

    依 `settings.use_dag_executor_for_chat` 決定走哪一條路徑:
      - True  → chat_adapter.process_via_dag(request)(DAG Executor)
      - False → orchestrator.process(request)(AgentOrchestrator,預設)

    /chat/stream 與 /chat/widget-response 不受此 flag 影響。
    """
    try:
        if settings.use_dag_executor_for_chat:
            from app.core.pipeline.chat_adapter import process_via_dag
            return await process_via_dag(request)
        return await orchestrator.process(request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Streaming 對話端點 (SSE)。

    依 `settings.use_dag_executor_for_chat` 決定走哪一條路徑:
      - True  → DAG Executor（active DAG）+ pseudo-streaming（分塊送出 final_text）
      - False → orchestrator.process_stream()（真正的逐字元流）
    """

    async def generate():
        try:
            if settings.use_dag_executor_for_chat:
                # DAG 路徑：執行完 DAG 後把 final_text 當成 stream 分塊送
                from app.core.pipeline.chat_adapter import process_via_dag
                import asyncio as _asyncio
                # 先回 session 占位（若 request 沒提供）
                if not request.session_id:
                    pass  # chat_adapter 會自己建 session；client 會從 done 事件拿到 message_id
                response = await process_via_dag(request)
                if response.session_id:
                    yield f"data: {json.dumps({'session_id': response.session_id}, ensure_ascii=False)}\n\n"
                # pseudo-stream：把 message 切成 ~40 字一塊，每塊間隔 20ms 模擬打字感
                text = response.message or ""
                chunk_size = 40
                for i in range(0, len(text), chunk_size):
                    chunk = text[i:i + chunk_size]
                    yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
                    await _asyncio.sleep(0.02)
                # 帶上 widgets / metadata
                done_event = {"done": True}
                if response.message_id:
                    done_event["message_id"] = response.message_id
                if getattr(response, 'widgets', None):
                    done_event["widgets"] = response.widgets
                yield f"data: {json.dumps(done_event, ensure_ascii=False)}\n\n"
            else:
                async for event in orchestrator.process_stream(request):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/chat/widget-response", response_model=ChatResponse)
async def handle_widget_response(response: WidgetResponse):
    """接收使用者對互動元件的操作結果。

    Widget follow-up 目前只走 orchestrator（DAG 尚未支援 widget_response 的 context 注入）；
    若未來要擴，在 chat_adapter 加 process_widget_via_dag()。
    """
    try:
        result = await orchestrator.handle_widget_result(response)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 回饋
# ============================================

@router.post("/feedback")
async def submit_feedback(request: FeedbackRequest):
    """使用者對 AI 輸出打分 + 修正"""
    # 驗證 message 存在
    msg = crud.get_message(request.message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message 不存在")

    feedback = crud.create_feedback(
        message_id=request.message_id,
        rating=request.rating,
        correction_text=request.correction_text,
    )
    return {"status": "saved", "feedback_id": feedback["id"]}


@router.get("/feedback/stats/{project_id}")
async def get_feedback_stats(project_id: str):
    """取得 project 的回饋統計"""
    project = crud.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project 不存在")

    stats = crud.get_feedback_stats(project_id)
    return stats


# ============================================
# Sessions
# ============================================

@router.get("/sessions/{project_id}")
async def list_sessions(
    project_id: str,
    user_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search: Optional[str] = None,
):
    """列出專案的訓練會話（支援篩選）。

    Query params:
    - user_id: 篩選特定用戶
    - date_from / date_to: ISO8601 時間範圍
    - search: 搜尋 messages.content 內的關鍵字
    - limit / offset: 分頁
    """
    sessions = crud.list_sessions(
        project_id=project_id,
        user_id=user_id,
        limit=limit,
        offset=offset,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )

    # Enrich with first user message preview and message count for UI
    for s in sessions:
        msgs = crud.list_messages(s["id"], limit=200)
        s["message_count"] = len(msgs)
        first_user = next((m for m in msgs if m.get("role") == "user"), None)
        s["preview"] = (first_user["content"][:80] if first_user else "")

    return {"sessions": sessions}


@router.get("/sessions/{project_id}/{session_id}/messages")
async def get_session_messages(project_id: str, session_id: str):
    """取得會話的訊息歷史"""
    messages = crud.list_messages(session_id)
    return {"messages": messages}


# ============================================
# Prompt 版本管理
# ============================================

@router.get("/prompts/{project_id}")
async def list_prompts(project_id: str):
    """列出專案的所有 Prompt 版本"""
    versions = crud.list_prompt_versions(project_id)
    return {"versions": versions}


@router.get("/prompts/{project_id}/active")
async def get_active_prompt(project_id: str):
    """取得當前 active 的 Prompt"""
    prompt = crud.get_active_prompt(project_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="沒有 active 的 Prompt")
    return prompt


@router.post("/prompts/{project_id}/activate/{version_id}")
async def activate_prompt(project_id: str, version_id: str):
    """切換 active Prompt 版本"""
    result = crud.activate_prompt_version(version_id, project_id)
    if not result:
        raise HTTPException(status_code=404, detail="Prompt 版本不存在")
    return {"status": "activated", "version_id": version_id}


@router.post("/prompts/{project_id}")
async def create_prompt(project_id: str, data: dict):
    """建立新 Prompt 版本。

    body: { content: str, change_notes?: str, activate?: bool }
    版本號 = 目前最大版本 + 1
    activate=true 時直接啟用並停用其他版本
    """
    content = data.get("content", "").strip()
    if not content:
        raise HTTPException(400, "content required")
    change_notes = data.get("change_notes", "")
    activate = bool(data.get("activate", False))

    next_version = crud.get_next_version_number(project_id)
    created = crud.create_prompt_version(
        project_id=project_id,
        content=content,
        version=next_version,
        is_active=activate,
        change_notes=change_notes,
    )
    return created


# ============================================
# Prompt 優化建議（Phase 1 Week 3）
# ============================================

@router.post("/prompt/suggestions/{project_id}/generate")
async def generate_suggestions(project_id: str):
    """觸發 Prompt 優化建議產出"""
    try:
        result = await prompt_optimizer.analyze_and_suggest(project_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prompt/suggestions/{project_id}")
async def list_prompt_suggestions(project_id: str):
    """列出待審建議"""
    suggestions = crud.list_suggestions(project_id, status="pending")
    return {"suggestions": suggestions}


@router.post("/prompt/suggestions/{suggestion_id}/apply")
async def apply_suggestion(
    suggestion_id: str,
    project_id: str = Query(..., description="Project ID"),
):
    """套用建議"""
    try:
        result = await prompt_optimizer.apply_suggestion(project_id, suggestion_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prompt/suggestions/{suggestion_id}/reject")
async def reject_suggestion(suggestion_id: str):
    """拒絕建議"""
    try:
        result = await prompt_optimizer.reject_suggestion(suggestion_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Onboarding（Phase 1 Week 2）
# ============================================

@router.post("/onboarding/start")
async def start_onboarding(request: OnboardingStartRequest):
    """開始 Onboarding 引導"""
    try:
        user_id = request.user_id
        if not user_id:
            demo = crud.get_user_by_email("demo@ai-trainer.dev")
            user_id = demo["id"] if demo else None
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id required")
        return await onboarding_mgr.start_onboarding(
            request.project_id, user_id, request.template_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/onboarding/answer")
async def answer_onboarding(request: OnboardingAnswerRequest):
    """回答 Onboarding 問題"""
    try:
        return await onboarding_mgr.handle_answer(
            request.session_id, request.question_id, request.answer
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/onboarding/progress/{session_id}", response_model=OnboardingProgress)
async def get_onboarding_progress(session_id: str):
    """取得 Onboarding 進度"""
    try:
        return await onboarding_mgr.get_progress(session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 知識庫
# ============================================

@router.post("/knowledge/upload")
async def upload_document(request: DocumentUploadRequest):
    """上傳文件到知識庫（支援 upload / url / auto_extract）"""
    from app.core.rag.pipeline import rag_pipeline
    try:
        if request.source_type == "url":
            if not request.url:
                raise HTTPException(status_code=400, detail="url required for source_type=url")
            doc = await rag_pipeline.upload_url(request.project_id, request.url, request.title)
        else:
            doc = await rag_pipeline.upload_document(
                request.project_id, request.title, request.content or "", request.source_type
            )
        return {"status": "ready", "document": doc}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/knowledge/batch-upload")
async def batch_upload_documents(data: dict):
    """批次上傳文件。

    Body: {"project_id": "...", "documents": [{"title": "...", "content": "...",
           "source_type": "upload|url|auto_extract"}]}

    成功與失敗逐筆回報，不因單一失敗中斷整批。
    """
    from app.core.rag.pipeline import rag_pipeline

    project_id = (data or {}).get("project_id")
    documents = (data or {}).get("documents") or []
    if not project_id or not isinstance(documents, list) or not documents:
        raise HTTPException(status_code=400, detail="project_id and documents[] required")

    results: list[dict] = []
    ok = err = 0
    for i, item in enumerate(documents):
        if not isinstance(item, dict):
            results.append({"index": i, "status": "error", "detail": "not a dict"})
            err += 1
            continue
        title = (item.get("title") or f"Untitled {i+1}").strip()
        content = (item.get("content") or "").strip()
        url = (item.get("url") or "").strip()
        source_type = item.get("source_type") or ("url" if url else "upload")
        if source_type != "url" and not content:
            results.append({"index": i, "title": title, "status": "error", "detail": "empty content"})
            err += 1
            continue
        if source_type == "url" and not url:
            results.append({"index": i, "title": title, "status": "error", "detail": "missing url"})
            err += 1
            continue
        try:
            if source_type == "url":
                doc = await rag_pipeline.upload_url(project_id, url, title)
            else:
                doc = await rag_pipeline.upload_document(project_id, title, content, source_type)
            results.append({
                "index": i, "title": title, "status": "ready",
                "doc_id": doc.get("id"), "chunk_count": doc.get("chunk_count", 0),
                "source_type": source_type,
            })
            ok += 1
        except Exception as e:  # noqa: BLE001
            results.append({"index": i, "title": title, "status": "error", "detail": str(e)[:300]})
            err += 1

    return {
        "total": len(documents),
        "success": ok,
        "failed": err,
        "results": results,
    }


@router.get("/knowledge/{project_id}")
async def list_knowledge(project_id: str):
    """列出專案的知識庫內容"""
    docs = crud.list_knowledge_docs(project_id)
    return {"documents": docs}


@router.get("/knowledge/doc/{doc_id}")
async def get_knowledge_doc(doc_id: str):
    """取得單一文件詳情（含內容 + 切塊）"""
    from app.db.supabase import get_supabase
    doc = get_supabase().table("ait_knowledge_docs").select("*").eq("id", doc_id).execute()
    if not doc.data:
        raise HTTPException(status_code=404, detail="Document not found")
    chunks = get_supabase().table("ait_knowledge_chunks").select("content, chunk_index").eq("doc_id", doc_id).order("chunk_index").execute()
    return {"document": doc.data[0], "chunks": chunks.data}


@router.put("/knowledge/doc/{doc_id}")
async def update_knowledge_doc(doc_id: str, data: dict):
    """更新文件標題或內容"""
    from app.db.supabase import get_supabase
    from app.core.rag.pipeline import rag_pipeline

    doc = get_supabase().table("ait_knowledge_docs").select("*").eq("id", doc_id).execute()
    if not doc.data:
        raise HTTPException(status_code=404, detail="Document not found")

    updates: dict = {}
    if "title" in data:
        updates["title"] = data["title"]
    if "content" in data:
        updates["raw_content"] = data["content"]

    if updates:
        get_supabase().table("ait_knowledge_docs").update(updates).eq("id", doc_id).execute()

    # If content changed, re-chunk
    if "content" in data and data["content"]:
        # Delete old chunks
        get_supabase().table("ait_knowledge_chunks").delete().eq("doc_id", doc_id).execute()
        # Re-chunk
        chunks = rag_pipeline.chunk_text(data["content"])
        for i, chunk_text in enumerate(chunks):
            crud.create_knowledge_chunk(doc_id, chunk_text, i)
        crud.update_doc_status(doc_id, "ready", len(chunks))

    return {"status": "updated"}


@router.delete("/knowledge/{doc_id}")
async def delete_knowledge(doc_id: str):
    """刪除知識文件"""
    crud.delete_knowledge_doc(doc_id)
    return {"status": "deleted"}


# ============================================
# 工具管理
# ============================================

@router.post("/tools")
async def register_tool(tool: ToolDefinition):
    """註冊外部工具"""
    from app.core.tools.registry import tool_registry
    # Need tenant_id — get from demo context
    demo = crud.get_user_by_email("demo@ai-trainer.dev")
    tenant_id = demo["tenant_id"] if demo else None
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant found")
    result = await tool_registry.register_tool(
        tenant_id=tenant_id, name=tool.name, description=tool.description,
        tool_type=tool.tool_type, config_json=tool.config_json,
        auth_config=tool.auth_config, permissions=tool.permissions, rate_limit=tool.rate_limit
    )
    return {"status": "registered", "tool": result}


@router.get("/tools/{tenant_id}")
async def list_tools(tenant_id: str):
    """列出租戶的工具"""
    tools = crud.list_tools(tenant_id)
    return {"tools": tools}


@router.delete("/tools/{tool_id}")
async def delete_tool(tool_id: str):
    """停用工具"""
    crud.delete_tool(tool_id)
    return {"status": "deleted"}


@router.post("/tools/{tool_id}/test")
async def test_tool(tool_id: str):
    """Dry run 測試工具"""
    from app.core.tools.registry import tool_registry
    result = await tool_registry.test_tool(tool_id)
    return result


@router.post("/summarize/project/{project_id}")
async def batch_summarize_sessions(project_id: str, data: dict = {}):
    """批次壓縮此專案中較長的 sessions（cron-friendly）。"""
    from app.core.summarizer.service import conversation_summarizer
    result = await conversation_summarizer.batch_summarize_project(
        project_id,
        threshold=int((data or {}).get("threshold", 20)),
        model=(data or {}).get("model") or "claude-haiku-4-5-20251001",
        persist=bool((data or {}).get("persist", True)),
        skip_already_summarized=bool((data or {}).get("skip_already_summarized", True)),
        limit=int((data or {}).get("limit", 50)),
    )
    return result


@router.get("/observability/trace/{project_id}")
async def get_langfuse_links(project_id: str, limit: int = 20):
    """從 ait_llm_usage.trace_id 推導 Langfuse UI 深連結（若已設定 host）。"""
    from app.db.supabase import get_supabase
    from app.config import settings
    host = (settings.langfuse_host or "").rstrip("/")
    if not host:
        return {"enabled": False, "links": []}
    rows = (
        get_supabase().table("ait_llm_usage")
        .select("id,trace_id,model,cost_usd,latency_ms,created_at")
        .eq("project_id", project_id)
        .order("created_at", desc=True)
        .limit(min(max(1, limit), 200))
        .execute()
    ).data or []
    links = [
        {
            "id": r["id"],
            "model": r.get("model"),
            "cost_usd": r.get("cost_usd"),
            "latency_ms": r.get("latency_ms"),
            "created_at": r.get("created_at"),
            "trace_id": r.get("trace_id"),
            "url": f"{host}/trace/{r['trace_id']}" if r.get("trace_id") else None,
        }
        for r in rows
    ]
    return {"enabled": True, "host": host, "links": links}


@router.post("/chat/{session_id}/summarize")
async def summarize_session(session_id: str, data: dict = {}):
    """將 session 的對話壓成摘要。可選 persist=True 寫入為 system 訊息。"""
    from app.core.summarizer.service import conversation_summarizer
    result = await conversation_summarizer.summarize_session(
        session_id,
        threshold=int((data or {}).get("threshold", 20)),
        model=(data or {}).get("model") or "claude-haiku-4-5-20251001",
        persist=bool((data or {}).get("persist", False)),
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result


@router.get("/ab-test/{project_id}")
async def get_ab_test_status(project_id: str):
    """取得專案 A/B 測試狀態。"""
    from app.core.ab_test.service import ab_test_service
    return await ab_test_service.get_status(project_id)


@router.put("/ab-test/{project_id}")
async def configure_ab_test(project_id: str, data: dict):
    """設定 A/B 測試：variants=[{prompt_version_id, weight, label}]"""
    from app.core.ab_test.service import ab_test_service
    variants = (data or {}).get("variants") or []
    enabled = bool((data or {}).get("enabled", True))
    updated = await ab_test_service.configure(project_id, variants, enabled=enabled)
    if not updated:
        raise HTTPException(status_code=400, detail="Invalid variants or project not found")
    return {"status": "configured", "project": updated}


@router.get("/ab-test/{project_id}/results")
async def get_ab_test_results(project_id: str):
    """聚合每個變體的 session/回饋統計。"""
    from app.core.ab_test.service import ab_test_service
    return await ab_test_service.summarize(project_id)


@router.post("/ab-test/{project_id}/conclude")
async def conclude_ab_test(project_id: str, data: dict):
    """標記獲勝變體，啟用該 prompt 版本並停用 A/B 測試。"""
    from app.core.ab_test.service import ab_test_service
    label = (data or {}).get("winner_label")
    if not label:
        raise HTTPException(status_code=400, detail="winner_label required")
    result = await ab_test_service.conclude(project_id, label)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


@router.post("/chat/{session_id}/handoff")
async def request_handoff(session_id: str, data: dict = {}):
    """把對話升級到真人客服。支援 webhook 通知。"""
    from app.core.handoff.service import handoff_service
    reason = (data or {}).get("reason", "")
    triggered_by = (data or {}).get("triggered_by", "user")
    urgency = (data or {}).get("urgency", "normal")
    result = await handoff_service.request(session_id, reason, triggered_by, urgency)
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result


@router.get("/handoff/pending/{tenant_id}")
async def list_pending_handoffs(tenant_id: str, limit: int = 50):
    """列出租戶尚未解決的 handoff（給真人客服儀表板輪詢）。"""
    from app.core.handoff.service import handoff_service
    items = await handoff_service.list_pending(tenant_id, limit=limit)
    return {"pending": items, "count": len(items)}


@router.post("/handoff/{handoff_id}/resolve")
async def resolve_handoff(handoff_id: str, data: dict):
    """標記 handoff 已被真人處理完成。"""
    from app.core.handoff.service import handoff_service
    resolved_by = (data or {}).get("resolved_by", "agent")
    note = (data or {}).get("note", "")
    result = await handoff_service.resolve(handoff_id, resolved_by, note)
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result


@router.get("/plan/{tenant_id}")
async def get_plan_limits(tenant_id: str):
    """回傳租戶目前方案 + 當月使用量 + 是否超限。"""
    from app.core.plan.limits import plan_limits_service
    return plan_limits_service.check_usage(tenant_id)


@router.post("/billing/{tenant_id}/checkout")
async def create_billing_checkout(tenant_id: str, data: dict):
    """建立 Stripe Checkout Session；無 Stripe config 時回 mock URL。"""
    from app.core.billing.stripe_service import stripe_service, BillingError
    plan = (data or {}).get("plan", "pro")
    email = (data or {}).get("email")
    try:
        return await stripe_service.create_checkout_session(tenant_id, plan, user_email=email)
    except BillingError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/billing/webhook")
async def stripe_webhook(request: Request):
    """接 Stripe webhook 事件（需驗 signature）。"""
    from app.core.billing.stripe_service import stripe_service
    import json as _json
    body = await request.body()
    signature = request.headers.get("stripe-signature", "")
    if not stripe_service.verify_signature(body, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")
    try:
        event = _json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    return await stripe_service.handle_event(event)


@router.get("/sso/{tenant_id}")
async def get_sso_config(tenant_id: str):
    """取得租戶的 SSO 設定。"""
    from app.core.sso.service import sso_service
    return sso_service.get_config(tenant_id)


@router.patch("/sso/{tenant_id}")
async def update_sso_config(tenant_id: str, data: dict):
    """更新租戶的 SSO 設定。"""
    from app.core.sso.service import sso_service
    updated = sso_service.update_config(
        tenant_id,
        allowed_email_domains=data.get("allowed_email_domains"),
        oauth_providers=data.get("oauth_providers"),
        enforced=data.get("enforced"),
        sso_entity_id=data.get("sso_entity_id"),
        sso_metadata_url=data.get("sso_metadata_url"),
    )
    if not updated:
        raise HTTPException(status_code=400, detail="No valid fields or tenant not found")
    return {"status": "updated", "tenant": updated}


@router.get("/sso/resolve")
async def resolve_sso_by_email(email: str = Query(...)):
    """依 email 的 domain 解析應該導向哪個租戶 / IdP。"""
    from app.core.sso.service import sso_service
    hint = sso_service.resolve_tenant_by_email(email)
    if not hint:
        return {"matched": False}
    return {"matched": True, **hint}


@router.get("/budget/{tenant_id}")
async def get_budget_status(tenant_id: str):
    """取得租戶當月預算狀態 + 告警等級。"""
    from app.core.budget.service import budget_service
    status = await budget_service.get_status(tenant_id)
    if status.get("status") == "error":
        raise HTTPException(status_code=404, detail=status.get("message"))
    return status


@router.patch("/budget/{tenant_id}")
async def update_budget_config(tenant_id: str, data: dict):
    """設定租戶月預算 / 告警門檻 / webhook。"""
    from app.core.budget.service import budget_service
    updated = await budget_service.update_config(
        tenant_id,
        monthly_budget_usd=data.get("monthly_budget_usd"),
        budget_alert_threshold=data.get("budget_alert_threshold"),
        budget_alert_webhook=data.get("budget_alert_webhook"),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"status": "updated", "tenant": updated}


@router.post("/budget/{tenant_id}/check")
async def check_budget_and_notify(tenant_id: str):
    """強制檢查預算，必要時 POST webhook 通知。回傳發送結果。"""
    from app.core.budget.service import budget_service
    return await budget_service.check_and_notify(tenant_id)


@router.get("/quality/{project_id}")
async def get_quality_status(project_id: str):
    """當前對話品質指標與告警等級。"""
    from app.core.quality.monitor import quality_monitor
    status = await quality_monitor.get_status(project_id)
    if status.get("status") == "error":
        raise HTTPException(status_code=404, detail=status.get("message"))
    return status


@router.patch("/quality/{project_id}")
async def update_quality_config(project_id: str, data: dict):
    """設定對話品質告警（存於 projects.domain_config.quality_alert）。"""
    from app.core.quality.monitor import quality_monitor
    updated = await quality_monitor.update_config(
        project_id,
        enabled=data.get("enabled"),
        window_hours=data.get("window_hours"),
        min_samples=data.get("min_samples"),
        wrong_ratio_threshold=data.get("wrong_ratio_threshold"),
        negative_ratio_threshold=data.get("negative_ratio_threshold"),
        webhook=data.get("webhook"),
    )
    if not updated:
        raise HTTPException(status_code=400, detail="No valid fields or project not found")
    return {"status": "updated", "project": updated}


@router.post("/quality/{project_id}/check")
async def check_quality_and_notify(project_id: str):
    """強制檢查品質，必要時 POST webhook 通知。"""
    from app.core.quality.monitor import quality_monitor
    return await quality_monitor.check_and_notify(project_id)


@router.get("/workflow-templates")
async def list_workflow_templates():
    """取得內建工作流樣板清單。"""
    from app.core.workflow_templates.library import list_templates
    return {"templates": list_templates()}


@router.get("/workflow-templates/{template_id}")
async def get_workflow_template(template_id: str):
    """取得單一樣板詳情（含 steps）。"""
    from app.core.workflow_templates.library import get_template
    tpl = get_template(template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return tpl


@router.post("/workflow-templates/{template_id}/instantiate")
async def instantiate_workflow_template(template_id: str, data: dict):
    """從樣板建立 workflow。Body: {project_id, name?, trigger?}"""
    from app.core.workflow_templates.library import instantiate
    project_id = (data or {}).get("project_id")
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id required")
    wf = instantiate(
        project_id,
        template_id,
        name_override=(data or {}).get("name"),
        trigger_override=(data or {}).get("trigger"),
    )
    if not wf:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"status": "created", "workflow": wf}


@router.post("/alerts/run-all")
async def run_all_alert_checks(data: dict = {}):
    """Cron-friendly：對所有租戶/專案跑 budget + quality 檢查。

    Body 可選 `tenant_ids` 或 `project_ids` 限縮範圍；留空則全掃。
    """
    from app.core.budget.service import budget_service
    from app.core.quality.monitor import quality_monitor
    from app.db.supabase import get_supabase

    db = get_supabase()
    data = data or {}

    tenant_ids: list[str] = data.get("tenant_ids") or []
    if not tenant_ids:
        tenants = db.table("ait_tenants").select("id").execute().data or []
        tenant_ids = [t["id"] for t in tenants]
    budget_results = []
    for tid in tenant_ids:
        try:
            r = await budget_service.check_and_notify(tid)
            budget_results.append({"tenant_id": tid, "level": r.get("level"), "notified": r.get("notified")})
        except Exception as e:  # noqa: BLE001
            budget_results.append({"tenant_id": tid, "error": str(e)})

    project_ids: list[str] = data.get("project_ids") or []
    if not project_ids:
        projects = db.table("ait_projects").select("id").in_("tenant_id", tenant_ids).execute().data if tenant_ids else []
        project_ids = [p["id"] for p in (projects or [])]
    quality_results = []
    for pid in project_ids:
        try:
            r = await quality_monitor.check_and_notify(pid)
            quality_results.append({"project_id": pid, "level": r.get("level"), "notified": r.get("notified")})
        except Exception as e:  # noqa: BLE001
            quality_results.append({"project_id": pid, "error": str(e)})

    return {
        "tenants_checked": len(budget_results),
        "projects_checked": len(quality_results),
        "budget": budget_results,
        "quality": quality_results,
    }


@router.get("/audit/{tenant_id}")
async def list_audit_logs_api(
    tenant_id: str,
    action_type: str | None = None,
    tool_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """租戶稽核日誌查詢（支援 action_type / tool_id / status 過濾與分頁）"""
    logs = crud.list_audit_logs(
        tenant_id,
        action_type=action_type,
        tool_id=tool_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {"logs": logs, "count": len(logs), "limit": limit, "offset": offset}


# ============================================
# 能力規則
# ============================================

@router.post("/capabilities")
async def create_capability(rule: CapabilityRule):
    """建立能力規則"""
    result = crud.create_capability_rule(
        project_id=rule.project_id,
        trigger_description=rule.trigger_description,
        action_type=rule.action_type,
        action_config=rule.action_config,
        trigger_keywords=rule.trigger_keywords,
        priority=rule.priority,
    )
    return {"status": "created", "rule": result}


@router.get("/capabilities/{project_id}")
async def list_capabilities(project_id: str):
    """列出能力規則"""
    rules = crud.list_capability_rules(project_id)
    return {"rules": rules}


@router.put("/capabilities/{rule_id}")
async def update_capability(rule_id: str, data: dict):
    """更新能力規則"""
    allowed = {"trigger_description", "trigger_keywords", "action_type", "action_config", "priority"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    result = crud.update_capability_rule(rule_id, **updates)
    return {"status": "updated", "rule": result}


@router.delete("/capabilities/{rule_id}")
async def delete_capability(rule_id: str):
    """停用能力規則"""
    crud.delete_capability_rule(rule_id)
    return {"status": "deleted"}


@router.post("/capabilities/classify")
async def classify_intent(data: dict):
    """測試意圖分類。`mode` ∈ {keyword,semantic,hybrid}（預設 hybrid）"""
    from app.core.intent.classifier import intent_classifier
    project_id = data.get("project_id", "")
    message = data.get("message", "")
    mode = data.get("mode", "hybrid")
    threshold = float(data.get("threshold", 0.3))
    if not project_id or not message:
        raise HTTPException(status_code=400, detail="project_id and message required")
    result = await intent_classifier.classify_async(
        message, project_id, mode=mode, threshold=threshold,
    )
    return result


# ============================================
# 評估
# ============================================

@router.post("/eval/test-cases")
async def create_test_case(request: TestCaseRequest):
    """建立測試案例"""
    tc = crud.create_test_case(
        request.project_id, request.input_text, request.expected_output, request.category
    )
    return {"status": "created", "test_case": tc}


@router.get("/eval/test-cases/{project_id}")
async def list_test_cases(project_id: str):
    """列出測試案例"""
    cases = crud.list_test_cases(project_id)
    return {"test_cases": cases}


@router.delete("/eval/test-cases/{test_case_id}")
async def delete_test_case(test_case_id: str):
    """停用測試案例"""
    crud.delete_test_case(test_case_id)
    return {"status": "deleted"}


@router.post("/eval/run/{project_id}")
async def run_eval(project_id: str):
    """執行評估"""
    from app.core.eval.engine import eval_engine
    try:
        result = await eval_engine.run_eval(project_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/eval/runs/{project_id}")
async def list_eval_runs(project_id: str):
    """列出評估歷史"""
    runs = crud.list_eval_runs(project_id)
    return {"runs": runs}


@router.get("/eval/runs/{run_id}/details")
async def get_eval_run_details(run_id: str):
    """取得評估詳細結果"""
    details = crud.get_eval_run_details(run_id)
    return details


@router.post("/eval/runs/{run_id}/ai-review")
async def ai_review_eval_run(run_id: str, data: dict = {}):
    """用更強的 judge 模型對既有 run 重新打分（AI 輔助評審）"""
    from app.core.eval.engine import eval_engine
    judge_model = (data or {}).get("judge_model") or "claude-opus-4-20250514"
    result = await eval_engine.ai_review_run(run_id, judge_model=judge_model)
    if result.get("status") == "no_results":
        raise HTTPException(status_code=404, detail="No results for this run")
    return result


@router.post("/eval/runs/{run_id}/cluster-gaps")
async def cluster_eval_gaps(run_id: str, data: dict = {}):
    """把 run 內失敗案例聚類成弱點類別 + 補救建議。"""
    from app.core.eval.engine import eval_engine
    max_clusters = int((data or {}).get("max_clusters", 6))
    judge_model = (data or {}).get("judge_model") or "claude-sonnet-4-20250514"
    return await eval_engine.cluster_gaps(run_id, max_clusters=max_clusters, judge_model=judge_model)


@router.post("/eval/before-after/{project_id}")
async def eval_before_after(project_id: str, data: dict):
    """對同一測試集跑兩個 prompt 版本並回傳逐題 delta。

    Body: {"before_version_id": "...", "after_version_id": "...", "model": "..."}
    """
    from app.core.eval.engine import eval_engine
    before_id = (data or {}).get("before_version_id")
    after_id = (data or {}).get("after_version_id")
    if not before_id or not after_id:
        raise HTTPException(status_code=400, detail="before_version_id and after_version_id required")
    model = (data or {}).get("model")
    return await eval_engine.before_after_eval(project_id, before_id, after_id, model=model)


# ============================================
# 評估分析
# ============================================

@router.get("/eval/analytics/trend/{project_id}")
async def get_eval_trend(project_id: str, limit: int = 20):
    """分數趨勢"""
    trend = crud.get_eval_score_trend(project_id, limit)
    return {"trend": trend}


@router.get("/eval/analytics/categories/{project_id}/{run_id}")
async def get_eval_categories(project_id: str, run_id: str):
    """分類表現"""
    categories = crud.get_category_analytics(project_id, run_id)
    return {"categories": categories}


@router.get("/eval/analytics/regression/{project_id}/{run_id}")
async def get_eval_regression(project_id: str, run_id: str):
    """回歸比對"""
    from app.core.eval.engine import eval_engine
    return eval_engine.compare_runs(project_id, run_id)


@router.get("/eval/analytics/compare-versions/{project_id}")
async def compare_prompt_versions(project_id: str, version_ids: str = ""):
    """版本比較（version_ids 以逗號分隔）"""
    ids = [v.strip() for v in version_ids.split(",") if v.strip()]
    if not ids:
        return {"versions": []}
    versions = crud.get_prompt_version_comparison(project_id, ids)
    return {"versions": versions}


@router.get("/eval/analytics/phase-status/{project_id}")
async def get_eval_phase_status(project_id: str):
    """階段狀態"""
    return crud.get_phase_status(project_id)


# ============================================
# 多模型比較
# ============================================

@router.post("/comparison/create")
async def create_comparison(data: dict):
    """建立多模型比較"""
    from app.core.comparison.engine import comparison_engine
    project_id = data.get("project_id", "")
    name = data.get("name", "Untitled")
    questions = data.get("questions", [])
    models = data.get("models", [])
    if not project_id or not questions or not models:
        raise HTTPException(status_code=400, detail="project_id, questions, models required")
    run = comparison_engine.create_run(project_id, name, questions, models)
    return {"status": "created", "run": run}


@router.post("/comparison/{run_id}/run")
async def execute_comparison(run_id: str):
    """批次執行所有模型"""
    from app.core.comparison.engine import comparison_engine
    result = await comparison_engine.execute_run(run_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/comparison/{run_id}")
async def get_comparison_results(run_id: str):
    """取得比較結果"""
    from app.core.comparison.engine import comparison_engine
    return comparison_engine.get_run_results(run_id)


@router.get("/comparison/list/{project_id}")
async def list_comparisons(project_id: str):
    """列出專案的比較"""
    from app.core.comparison.engine import comparison_engine
    return {"runs": comparison_engine.list_runs(project_id)}


@router.post("/comparison/vote")
async def vote_response(data: dict):
    """投票/標記正確性"""
    from app.core.comparison.engine import comparison_engine
    response_id = data.get("response_id", "")
    is_correct = data.get("is_correct")
    voted_rank = data.get("voted_rank")
    result = comparison_engine.vote(response_id, is_correct, voted_rank)
    return {"status": "voted", "response": result}


@router.post("/comparison/{run_id}/select-model")
async def select_comparison_model(run_id: str, data: dict):
    """選定模型"""
    from app.core.comparison.engine import comparison_engine
    model_id = data.get("model_id", "")
    return comparison_engine.select_model(run_id, model_id)


@router.get("/comparison/{run_id}/gaps")
async def analyze_comparison_gaps(run_id: str):
    """概念差分析"""
    from app.core.comparison.engine import comparison_engine
    gaps = comparison_engine.analyze_gaps(run_id)
    return {"gaps": gaps}


@router.post("/comparison/gaps/{gap_id}/remediate")
async def remediate_gap(gap_id: str, data: dict):
    """自動補齊概念差"""
    from app.core.comparison.engine import comparison_engine
    rtype = data.get("type", "rag")
    result = await comparison_engine.remediate_gap(gap_id, rtype)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/comparison/gaps/list/{project_id}")
async def list_concept_gaps(project_id: str):
    """列出專案的概念差"""
    from app.core.comparison.engine import comparison_engine
    return {"gaps": comparison_engine.list_gaps(project_id)}


@router.post("/comparison/generate-questions/{project_id}")
async def generate_questions(project_id: str, data: dict = {}):
    """AI 自動產出關鍵測試問題"""
    from app.core.comparison.engine import comparison_engine
    count = data.get("count", 15) if data else 15
    questions = await comparison_engine.generate_questions(project_id, count)
    return {"questions": questions}


@router.post("/comparison/{run_id}/auto-judge")
async def auto_judge(run_id: str):
    """AI 輔助評審 — 自動打分"""
    from app.core.comparison.engine import comparison_engine
    verdicts = await comparison_engine.auto_judge(run_id)
    return {"verdicts": verdicts, "total": len(verdicts)}


@router.get("/comparison/{run_id}/recommend")
async def recommend_model(run_id: str):
    """自動推薦模型"""
    from app.core.comparison.engine import comparison_engine
    return comparison_engine.recommend_model(run_id)


# ============================================
# 成本追蹤
# ============================================

@router.get("/usage/cost/{project_id}")
async def get_project_cost(project_id: str, days: int = 30):
    """取得專案成本統計"""
    from app.db.supabase import get_supabase
    from datetime import datetime, timedelta
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    data = (
        get_supabase().table("ait_llm_usage")
        .select("model, input_tokens, output_tokens, total_tokens, cost_usd, latency_ms, endpoint, created_at")
        .eq("project_id", project_id)
        .gte("created_at", since)
        .order("created_at", desc=True)
        .execute()
    ).data

    total_cost = sum(r.get("cost_usd", 0) or 0 for r in data)
    total_tokens = sum(r.get("total_tokens", 0) or 0 for r in data)
    total_calls = len(data)

    by_model: dict = {}
    for r in data:
        m = r["model"]
        if m not in by_model:
            by_model[m] = {"calls": 0, "tokens": 0, "cost": 0, "total_latency": 0}
        by_model[m]["calls"] += 1
        by_model[m]["tokens"] += r.get("total_tokens", 0) or 0
        by_model[m]["cost"] += r.get("cost_usd", 0) or 0
        by_model[m]["total_latency"] += r.get("latency_ms", 0) or 0
    for s in by_model.values():
        s["avg_latency"] = round(s["total_latency"] / s["calls"]) if s["calls"] else 0

    daily: dict = {}
    for r in data:
        day = r["created_at"][:10]
        if day not in daily:
            daily[day] = {"calls": 0, "cost": 0, "tokens": 0}
        daily[day]["calls"] += 1
        daily[day]["cost"] += r.get("cost_usd", 0) or 0
        daily[day]["tokens"] += r.get("total_tokens", 0) or 0

    return {
        "total_cost": round(total_cost, 4),
        "total_tokens": total_tokens,
        "total_calls": total_calls,
        "by_model": {k: {**v, "cost": round(v["cost"], 4)} for k, v in by_model.items()},
        "daily_trend": [{"date": k, **v, "cost": round(v["cost"], 4)} for k, v in sorted(daily.items())],
        "period_days": days,
    }


@router.get("/analytics/{project_id}/csv")
async def get_project_analytics_csv(project_id: str, days: int = 30):
    """匯出分析資料為 CSV。"""
    import csv
    import io
    from fastapi.responses import Response

    data = await get_project_analytics(project_id, days=days)  # type: ignore[misc]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["section", "key", "value"])
    overview = data.get("overview", {})
    for k, v in overview.items():
        w.writerow(["overview", k, v])
    fb = data.get("feedback", {})
    for k, v in fb.items():
        w.writerow(["feedback", k, v])
    tools = data.get("tools", {})
    w.writerow(["tools", "registered", tools.get("registered", 0)])
    w.writerow(["tools", "total_calls", tools.get("total_calls", 0)])
    for tid, bucket in (tools.get("by_tool") or {}).items():
        name = bucket.get("name", tid)
        for k in ("calls", "success", "error", "avg_latency_ms", "success_rate"):
            w.writerow([f"tool:{name}", k, bucket.get(k, 0)])
    for day in data.get("daily_activity", []) or []:
        w.writerow(["daily_activity", day.get("date"), day.get("sessions", 0)])

    csv_text = buf.getvalue()
    filename = f"analytics-{project_id[:8]}-{days}d.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/analytics/{project_id}")
async def get_project_analytics(project_id: str, days: int = 30):
    """完整使用分析"""
    from app.db.supabase import get_supabase
    from datetime import datetime, timedelta
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    # 1. Sessions
    sessions = get_supabase().table("ait_training_sessions").select("id, started_at").eq("project_id", project_id).gte("started_at", since).execute().data
    total_sessions = len(sessions)

    # 2. Messages
    session_ids = [s["id"] for s in sessions]
    total_messages = 0
    user_messages = 0
    if session_ids:
        # Batch in chunks of 50
        for i in range(0, len(session_ids), 50):
            chunk = session_ids[i:i+50]
            msgs = get_supabase().table("ait_training_messages").select("role").in_("session_id", chunk).execute().data
            total_messages += len(msgs)
            user_messages += sum(1 for m in msgs if m["role"] == "user")

    # 3. Feedbacks
    feedbacks = crud.get_feedback_stats(project_id)

    # 4. Tool calls (from LLM usage with endpoint)
    tool_usage = get_supabase().table("ait_llm_usage").select("endpoint, model, cost_usd, created_at").eq("project_id", project_id).gte("created_at", since).execute().data
    by_endpoint: dict = {}
    for r in tool_usage:
        ep = r.get("endpoint", "chat")
        if ep not in by_endpoint:
            by_endpoint[ep] = {"calls": 0, "cost": 0}
        by_endpoint[ep]["calls"] += 1
        by_endpoint[ep]["cost"] += r.get("cost_usd", 0) or 0

    # 5. Registered tools + 實際呼叫細分統計
    project_data = crud.get_project(project_id)
    tenant_id = project_data.get("tenant_id") if project_data else None
    tools = crud.list_tools(tenant_id) if tenant_id else []
    try:
        tool_call_stats = crud.get_tool_call_stats(tenant_id, since) if tenant_id else {"total_calls": 0, "by_tool": {}}
    except Exception:
        tool_call_stats = {"total_calls": 0, "by_tool": {}}

    # 6. Prompt versions
    prompts = crud.list_prompt_versions(project_id)

    # 7. Knowledge docs
    docs = crud.list_knowledge_docs(project_id)

    # 8. Eval runs
    eval_runs = crud.list_eval_runs(project_id)

    # 9. Daily activity
    daily_activity: dict = {}
    for s in sessions:
        day = s["started_at"][:10]
        daily_activity.setdefault(day, {"sessions": 0})
        daily_activity[day]["sessions"] += 1

    # Compression metrics snapshot (since last ai-engine start)
    from app.core.orchestrator.agent import AgentOrchestrator
    comp = AgentOrchestrator.compression_stats
    saved_chars = max(0, comp["chars_before"] - comp["chars_after"])
    compression_ratio = round(comp["chars_after"] / comp["chars_before"], 4) if comp["chars_before"] else 0

    # Langfuse trace URL base (if configured)
    from app.config import settings as _settings
    langfuse_host = (_settings.langfuse_host or "").rstrip("/")

    return {
        "overview": {
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "user_messages": user_messages,
            "avg_messages_per_session": round(total_messages / total_sessions, 1) if total_sessions else 0,
        },
        "context_compression": {
            "sessions_compressed": comp["sessions_compressed"],
            "turns_dropped": comp["turns_dropped"],
            "chars_saved": saved_chars,
            "compression_ratio": compression_ratio,
        },
        "observability": {
            "langfuse_host": langfuse_host,
        },
        "feedback": feedbacks,
        "tools": {
            "registered": len(tools),
            "tool_names": [t["name"] for t in tools],
            "total_calls": tool_call_stats.get("total_calls", 0),
            "by_tool": tool_call_stats.get("by_tool", {}),
        },
        "prompts": {
            "total_versions": len(prompts),
            "active_version": next((p["version"] for p in prompts if p.get("is_active")), None),
        },
        "knowledge": {
            "total_docs": len(docs),
        },
        "eval": {
            "total_runs": len(eval_runs),
            "latest_score": eval_runs[0]["total_score"] if eval_runs else None,
        },
        "by_endpoint": {k: {**v, "cost": round(v["cost"], 4)} for k, v in by_endpoint.items()},
        "daily_activity": [{"date": k, **v} for k, v in sorted(daily_activity.items())],
        "period_days": days,
    }


# ============================================
# Fine-tune
# ============================================

@router.post("/finetune/extract/{project_id}")
async def extract_training_data(project_id: str):
    """抽取訓練資料"""
    from app.core.finetune.pipeline import finetune_pipeline
    pairs = await finetune_pipeline.extract_training_data(project_id)
    return {"pairs": pairs, "count": len(pairs)}


@router.post("/finetune/export/{project_id}")
async def export_training_data(project_id: str):
    """匯出 JSONL"""
    from app.core.finetune.pipeline import finetune_pipeline
    jsonl = await finetune_pipeline.export_jsonl(project_id)
    return {"jsonl": jsonl, "format": "openai"}


@router.get("/finetune/stats/{project_id}")
async def get_finetune_stats(project_id: str):
    """取得 Fine-tune 統計"""
    from app.core.finetune.pipeline import finetune_pipeline
    stats = await finetune_pipeline.get_stats(project_id)
    return stats


@router.post("/finetune/jobs/{project_id}")
async def create_finetune_job(project_id: str, data: dict):
    """建立微調任務"""
    from app.core.finetune.pipeline import finetune_pipeline
    result = await finetune_pipeline.create_job(
        project_id, data.get("provider", "openai"), data.get("model_base", "gpt-4o-mini")
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.get("/finetune/jobs/{project_id}")
async def list_finetune_jobs(project_id: str):
    """列出微調任務"""
    from app.core.finetune.pipeline import finetune_pipeline
    jobs = await finetune_pipeline.list_jobs(project_id)
    return {"jobs": jobs}


@router.get("/finetune/job/{job_id}")
async def get_finetune_job(job_id: str):
    """取得微調任務詳情"""
    from app.core.finetune.pipeline import finetune_pipeline
    job = await finetune_pipeline.get_job(job_id)
    if job.get("status") == "error":
        raise HTTPException(status_code=404, detail=job["message"])
    return job


@router.post("/finetune/job/{job_id}/complete")
async def complete_finetune_job(job_id: str, data: dict):
    """標記微調任務完成（含產出模型 ID）"""
    from app.core.finetune.pipeline import finetune_pipeline
    result = await finetune_pipeline.complete_job(job_id, data.get("result_model_id", ""))
    return {"status": "completed", "job": result}


@router.post("/finetune/job/{job_id}/poll")
async def poll_finetune_job(job_id: str):
    """輪詢 provider 狀態（OpenAI）。完成時會自動寫回 result_model_id。"""
    from app.core.finetune.pipeline import finetune_pipeline
    result = await finetune_pipeline.poll_job(job_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("message", "error"))
    return result


# ============================================
# Workflows
# ============================================

@router.get("/workflows/{project_id}")
async def list_workflows_api(project_id: str):
    """列出工作流"""
    from app.core.workflows.engine import workflow_engine
    workflows = await workflow_engine.list_workflows(project_id)
    return {"workflows": workflows}


@router.post("/workflows")
async def create_workflow_api(data: dict):
    """建立工作流"""
    from app.core.workflows.engine import workflow_engine
    wf = await workflow_engine.create_workflow(
        data["project_id"], data["name"], data["trigger_description"], data.get("steps", [])
    )
    return {"status": "created", "workflow": wf}


@router.get("/workflows/detail/{workflow_id}")
async def get_workflow_detail(workflow_id: str):
    """取得單一工作流詳情"""
    wf = crud.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.delete("/workflows/{workflow_id}")
async def delete_workflow_api(workflow_id: str):
    """停用工作流"""
    crud.delete_workflow(workflow_id)
    return {"status": "deleted"}


@router.post("/workflows/{workflow_id}/start")
async def start_workflow_api(workflow_id: str, data: dict):
    """啟動工作流執行（步進式，需人工推進）"""
    from app.core.workflows.engine import workflow_engine
    result = await workflow_engine.start_workflow(
        workflow_id, data.get("session_id", ""), data.get("user_id", "")
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["detail"])
    return result


@router.post("/workflows/{workflow_id}/run")
async def run_workflow_to_completion_api(workflow_id: str, data: dict = {}):
    """從頭跑到尾（自動編排，支援 if/parallel/loop）"""
    from app.core.workflows.engine import workflow_engine
    result = await workflow_engine.run_to_completion(
        workflow_id,
        session_id=(data or {}).get("session_id"),
        user_id=(data or {}).get("user_id"),
        initial_vars=(data or {}).get("initial_vars") or {},
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("detail", "error"))
    return result


@router.post("/workflows/runs/{run_id}/advance")
async def advance_workflow_api(run_id: str, data: dict):
    """推進工作流到下一步"""
    from app.core.workflows.engine import workflow_engine
    result = await workflow_engine.advance_workflow(run_id, data.get("step_result", {}))
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["detail"])
    return result


@router.get("/workflows/{workflow_id}/runs")
async def list_workflow_runs(workflow_id: str):
    """列出工作流執行歷史"""
    runs = crud.list_workflow_runs(workflow_id)
    return {"runs": runs}


@router.get("/workflows/runs/{run_id}")
async def get_workflow_run_api(run_id: str):
    """取得單一執行記錄"""
    run = crud.get_workflow_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


# ============================================
# 專案設定
# ============================================

@router.get("/projects")
async def list_all_projects(tenant_id: str = Query(...)):
    """列出租戶所有專案（含 project_type + domain_config）"""
    projects = crud.list_projects(tenant_id)
    return {"projects": projects}


@router.patch("/projects/{project_id}")
async def update_project(project_id: str, data: dict):
    """更新專案設定"""
    from app.db.supabase import get_supabase
    allowed = {"name", "description", "default_model", "domain_template", "project_type"}
    updates = {k: v for k, v in data.items() if k in allowed}
    # domain_config uses partial merge
    if "domain_config" in data and isinstance(data["domain_config"], dict):
        result = crud.update_project_config(project_id, data["domain_config"])
        if not result:
            raise HTTPException(status_code=404, detail="Project not found")
        if not updates:
            return {"status": "updated", "project": result}
    if not updates and "domain_config" not in data:
        raise HTTPException(status_code=400, detail="No valid fields")
    if updates:
        result = get_supabase().table("ait_projects").update(updates).eq("id", project_id).execute()
    return {"status": "updated", "project": result.data[0] if hasattr(result, 'data') and result.data else {}}


@router.get("/projects/{project_id}")
async def get_project_detail(project_id: str):
    """取得專案詳情（含 domain_config merged with defaults）"""
    project = crud.get_project_config(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


# ============================================
# LLM 管理
# ============================================

@router.get("/models")
async def list_available_models():
    """列出所有可用 LLM 模型（從集中模型定義讀取）"""
    from app.core.llm_router.models import get_models_for_api
    return {"models": get_models_for_api()}
