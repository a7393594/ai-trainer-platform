"""
API v1 路由 — 所有對外端點
"""
import json
from fastapi import APIRouter, HTTPException, Query
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
    DemoContext,
)
from app.core.orchestrator.agent import AgentOrchestrator
from app.core.orchestrator.onboarding import OnboardingManager
from app.core.prompt.optimizer import PromptOptimizer
from app.db import crud

router = APIRouter()
orchestrator = AgentOrchestrator()
onboarding_mgr = OnboardingManager()
prompt_optimizer = PromptOptimizer()


# ============================================
# Demo Context
# ============================================

@router.get("/demo/context", response_model=DemoContext)
async def get_demo_context():
    """取得 demo 環境的 tenant/user/project IDs"""
    user = crud.get_user_by_email("demo@ai-trainer.dev")
    if not user:
        raise HTTPException(status_code=404, detail="Demo user 不存在，請先執行 seed")

    projects = crud.list_projects(user["tenant_id"])
    if not projects:
        raise HTTPException(status_code=404, detail="Demo project 不存在")

    return DemoContext(
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        project_id=projects[0]["id"],
        project_name=projects[0]["name"],
    )


# ============================================
# 對話（核心端點）
# ============================================

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """核心對話端點"""
    try:
        response = await orchestrator.process(request)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Streaming 對話端點 (SSE)"""
    from app.core.llm_router.router import stream_chat_completion

    # 取得 user_id
    user_id = request.user_id
    if not user_id:
        demo = crud.get_user_by_email("demo@ai-trainer.dev")
        user_id = demo["id"] if demo else None

    # 取得或建立 session
    session_id = request.session_id
    if not session_id:
        session = crud.create_session(request.project_id, user_id, "freeform")
        session_id = session["id"]

    # 存 user message
    crud.create_message(session_id, "user", request.message)

    # 組合 messages
    messages = []
    prompt = crud.get_active_prompt(request.project_id)
    if prompt:
        messages.append({"role": "system", "content": prompt["content"]})

    history = crud.list_messages(session_id)
    messages.extend([
        {"role": m["role"], "content": m["content"]}
        for m in history if m["role"] in ("user", "assistant")
    ])

    model = request.model or "claude-sonnet-4-20250514"

    async def generate():
        full_content = ""
        yield f"data: {json.dumps({'session_id': session_id})}\n\n"
        try:
            async for chunk in stream_chat_completion(messages=messages, model=model):
                full_content += chunk
                yield f"data: {json.dumps({'content': chunk})}\n\n"

            # 存 assistant message
            msg = crud.create_message(session_id, "assistant", full_content)
            yield f"data: {json.dumps({'done': True, 'message_id': msg['id']})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/chat/widget-response", response_model=ChatResponse)
async def handle_widget_response(response: WidgetResponse):
    """接收使用者對互動元件的操作結果"""
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
async def list_sessions(project_id: str):
    """列出專案的所有訓練會話"""
    sessions = crud.list_sessions(project_id)
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
    """上傳文件到知識庫"""
    from app.core.rag.pipeline import rag_pipeline
    try:
        doc = await rag_pipeline.upload_document(
            request.project_id, request.title, request.content or "", request.source_type
        )
        return {"status": "ready", "document": doc}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge/{project_id}")
async def list_knowledge(project_id: str):
    """列出專案的知識庫內容"""
    docs = crud.list_knowledge_docs(project_id)
    return {"documents": docs}


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


# ============================================
# 能力規則
# ============================================

@router.post("/capabilities")
async def create_capability(rule: CapabilityRule):
    """建立能力規則"""
    # Store in DB (simplified — no embedding for now)
    from app.db.supabase import get_supabase
    result = get_supabase().table("ait_capability_rules").insert({
        "project_id": rule.trigger_description,  # Will be fixed when we add project_id to schema
        "trigger_description": rule.trigger_description,
        "action_type": rule.action_type,
        "action_config": rule.action_config,
        "priority": rule.priority,
    }).execute()
    return {"status": "created", "rule": result.data[0] if result.data else {}}


@router.get("/capabilities/{project_id}")
async def list_capabilities(project_id: str):
    """列出能力規則"""
    from app.db.supabase import get_supabase
    result = (
        get_supabase().table("ait_capability_rules")
        .select("*").eq("project_id", project_id).eq("is_active", True)
        .order("priority", desc=True).execute()
    )
    return {"rules": result.data}


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


@router.delete("/workflows/{workflow_id}")
async def delete_workflow_api(workflow_id: str):
    """停用工作流"""
    crud.delete_workflow(workflow_id)
    return {"status": "deleted"}


# ============================================
# LLM 管理
# ============================================

@router.get("/models")
async def list_available_models():
    """列出可用 LLM 模型"""
    return {
        "models": [
            {"id": "claude-sonnet-4-20250514", "provider": "anthropic", "label": "Claude Sonnet 4"},
            {"id": "claude-opus-4-20250514", "provider": "anthropic", "label": "Claude Opus 4"},
            {"id": "gpt-4o", "provider": "openai", "label": "GPT-4o"},
            {"id": "gpt-4o-mini", "provider": "openai", "label": "GPT-4o Mini"},
            {"id": "gemini/gemini-2.0-flash", "provider": "google", "label": "Gemini 2.0 Flash"},
        ]
    }
