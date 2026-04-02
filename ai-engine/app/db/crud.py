"""
CRUD 工具函數 — AI Trainer Platform 資料存取層

所有表使用 ait_ 前綴（與 PokerVerse 共用 Supabase）
使用 service_role key 繞過 RLS
"""
from typing import Optional
from app.db.supabase import get_supabase

# ============================================
# 表名常數（ait_ 前綴）
# ============================================
T_TENANTS = "ait_tenants"
T_USERS = "ait_users"
T_PROJECTS = "ait_projects"
T_SESSIONS = "ait_training_sessions"
T_MESSAGES = "ait_training_messages"
T_FEEDBACKS = "ait_feedbacks"
T_PROMPTS = "ait_prompt_versions"
T_SUGGESTIONS = "ait_prompt_suggestions"


# ============================================
# Tenant
# ============================================

def create_tenant(name: str, plan: str = "free") -> dict:
    result = get_supabase().table(T_TENANTS).insert({
        "name": name,
        "plan": plan,
    }).execute()
    return result.data[0]


def get_tenant(tenant_id: str) -> Optional[dict]:
    result = get_supabase().table(T_TENANTS).select("*").eq("id", tenant_id).execute()
    return result.data[0] if result.data else None


# ============================================
# User
# ============================================

def create_user(
    tenant_id: str,
    email: str,
    role: str = "viewer",
    display_name: Optional[str] = None,
) -> dict:
    data = {
        "tenant_id": tenant_id,
        "email": email,
        "role": role,
    }
    if display_name:
        data["display_name"] = display_name
    result = get_supabase().table(T_USERS).insert(data).execute()
    return result.data[0]


def get_user(user_id: str) -> Optional[dict]:
    result = get_supabase().table(T_USERS).select("*").eq("id", user_id).execute()
    return result.data[0] if result.data else None


def get_user_by_email(email: str) -> Optional[dict]:
    result = get_supabase().table(T_USERS).select("*").eq("email", email).limit(1).execute()
    return result.data[0] if result.data else None


# ============================================
# Project
# ============================================

def create_project(
    tenant_id: str,
    name: str,
    description: Optional[str] = None,
    domain_template: Optional[str] = None,
) -> dict:
    data = {
        "tenant_id": tenant_id,
        "name": name,
    }
    if description:
        data["description"] = description
    if domain_template:
        data["domain_template"] = domain_template
    result = get_supabase().table(T_PROJECTS).insert(data).execute()
    return result.data[0]


def get_project(project_id: str) -> Optional[dict]:
    result = get_supabase().table(T_PROJECTS).select("*").eq("id", project_id).execute()
    return result.data[0] if result.data else None


def list_projects(tenant_id: str) -> list[dict]:
    result = (
        get_supabase().table(T_PROJECTS)
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


# ============================================
# Training Session
# ============================================

def create_session(
    project_id: str,
    user_id: str,
    session_type: str = "freeform",
) -> dict:
    result = get_supabase().table(T_SESSIONS).insert({
        "project_id": project_id,
        "user_id": user_id,
        "session_type": session_type,
    }).execute()
    return result.data[0]


def get_session(session_id: str) -> Optional[dict]:
    result = get_supabase().table(T_SESSIONS).select("*").eq("id", session_id).execute()
    return result.data[0] if result.data else None


def list_sessions(project_id: str) -> list[dict]:
    result = (
        get_supabase().table(T_SESSIONS)
        .select("*")
        .eq("project_id", project_id)
        .order("started_at", desc=True)
        .execute()
    )
    return result.data


def end_session(session_id: str) -> dict:
    result = (
        get_supabase().table(T_SESSIONS)
        .update({"ended_at": "now()"})
        .eq("id", session_id)
        .execute()
    )
    return result.data[0] if result.data else {}


# ============================================
# Training Message
# ============================================

def create_message(
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[dict] = None,
) -> dict:
    result = get_supabase().table(T_MESSAGES).insert({
        "session_id": session_id,
        "role": role,
        "content": content,
        "metadata": metadata or {},
    }).execute()
    return result.data[0]


def get_message(message_id: str) -> Optional[dict]:
    result = get_supabase().table(T_MESSAGES).select("*").eq("id", message_id).execute()
    return result.data[0] if result.data else None


def list_messages(session_id: str, limit: int = 100) -> list[dict]:
    result = (
        get_supabase().table(T_MESSAGES)
        .select("*")
        .eq("session_id", session_id)
        .order("created_at")
        .limit(limit)
        .execute()
    )
    return result.data


# ============================================
# Feedback
# ============================================

def create_feedback(
    message_id: str,
    rating: str,
    correction_text: Optional[str] = None,
    created_by: Optional[str] = None,
) -> dict:
    data: dict = {
        "message_id": message_id,
        "rating": rating,
    }
    if correction_text:
        data["correction_text"] = correction_text
    if created_by:
        data["created_by"] = created_by
    result = get_supabase().table(T_FEEDBACKS).insert(data).execute()
    return result.data[0]


def list_feedbacks_by_project(
    project_id: str,
    rating_filter: Optional[list[str]] = None,
    limit: int = 50,
) -> list[dict]:
    """撈回饋 + 關聯的訊息內容（跨表查詢）"""
    # 先取該 project 的所有 session IDs
    sessions = (
        get_supabase().table(T_SESSIONS)
        .select("id")
        .eq("project_id", project_id)
        .execute()
    )
    session_ids = [s["id"] for s in sessions.data]
    if not session_ids:
        return []

    # 取這些 session 中所有被回饋的 message IDs
    messages = (
        get_supabase().table(T_MESSAGES)
        .select("id, session_id, role, content, metadata")
        .in_("session_id", session_ids)
        .eq("role", "assistant")
        .execute()
    )
    message_ids = [m["id"] for m in messages.data]
    if not message_ids:
        return []
    message_map = {m["id"]: m for m in messages.data}

    # 取回饋
    query = (
        get_supabase().table(T_FEEDBACKS)
        .select("*")
        .in_("message_id", message_ids)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if rating_filter:
        query = query.in_("rating", rating_filter)
    feedbacks = query.execute()

    # 合併回饋 + 訊息
    result = []
    for fb in feedbacks.data:
        msg = message_map.get(fb["message_id"])
        if msg:
            fb["message"] = msg
            # 嘗試取得對應的 user 訊息（同 session 中，前一則）
            session_msgs = [
                m for m in messages.data
                if m["session_id"] == msg["session_id"]
            ]
            result.append(fb)

    return result


def get_feedback_stats(project_id: str) -> dict:
    """取得 project 的回饋統計"""
    feedbacks = list_feedbacks_by_project(project_id, limit=1000)
    stats = {"correct": 0, "partial": 0, "wrong": 0, "total": 0}
    for fb in feedbacks:
        stats[fb["rating"]] = stats.get(fb["rating"], 0) + 1
        stats["total"] += 1
    return stats


# ============================================
# Prompt Version
# ============================================

def create_prompt_version(
    project_id: str,
    content: str,
    version: int,
    is_active: bool = False,
    created_by: Optional[str] = None,
    change_notes: Optional[str] = None,
) -> dict:
    # 如果要設為 active，先把其他版本停用
    if is_active:
        get_supabase().table(T_PROMPTS).update(
            {"is_active": False}
        ).eq("project_id", project_id).eq("is_active", True).execute()

    data: dict = {
        "project_id": project_id,
        "content": content,
        "version": version,
        "is_active": is_active,
    }
    if created_by:
        data["created_by"] = created_by
    if change_notes:
        data["change_notes"] = change_notes
    result = get_supabase().table(T_PROMPTS).insert(data).execute()
    return result.data[0]


def get_active_prompt(project_id: str) -> Optional[dict]:
    result = (
        get_supabase().table(T_PROMPTS)
        .select("*")
        .eq("project_id", project_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def list_prompt_versions(project_id: str) -> list[dict]:
    result = (
        get_supabase().table(T_PROMPTS)
        .select("*")
        .eq("project_id", project_id)
        .order("version", desc=True)
        .execute()
    )
    return result.data


def activate_prompt_version(version_id: str, project_id: str) -> dict:
    """切換 active 版本：停用舊的，啟用指定的"""
    get_supabase().table(T_PROMPTS).update(
        {"is_active": False}
    ).eq("project_id", project_id).eq("is_active", True).execute()

    result = (
        get_supabase().table(T_PROMPTS)
        .update({"is_active": True})
        .eq("id", version_id)
        .execute()
    )
    return result.data[0] if result.data else {}


def get_next_version_number(project_id: str) -> int:
    result = (
        get_supabase().table(T_PROMPTS)
        .select("version")
        .eq("project_id", project_id)
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["version"] + 1
    return 1


# ============================================
# Prompt Suggestions
# ============================================

def create_suggestion(
    project_id: str,
    changes: list[dict],
    based_on_feedback_count: int = 0,
) -> dict:
    result = get_supabase().table(T_SUGGESTIONS).insert({
        "project_id": project_id,
        "changes": changes,
        "based_on_feedback_count": based_on_feedback_count,
    }).execute()
    return result.data[0]


def get_suggestion(suggestion_id: str) -> Optional[dict]:
    result = get_supabase().table(T_SUGGESTIONS).select("*").eq("id", suggestion_id).execute()
    return result.data[0] if result.data else None


def list_suggestions(project_id: str, status: Optional[str] = None) -> list[dict]:
    query = (
        get_supabase().table(T_SUGGESTIONS)
        .select("*")
        .eq("project_id", project_id)
        .order("created_at", desc=True)
    )
    if status:
        query = query.eq("status", status)
    return query.execute().data


def update_suggestion_status(
    suggestion_id: str,
    status: str,
    result_prompt_version_id: Optional[str] = None,
) -> dict:
    data: dict = {"status": status}
    if result_prompt_version_id:
        data["result_prompt_version_id"] = result_prompt_version_id
    result = (
        get_supabase().table(T_SUGGESTIONS)
        .update(data)
        .eq("id", suggestion_id)
        .execute()
    )
    return result.data[0] if result.data else {}


# ============================================
# Knowledge Docs
# ============================================

T_DOCS = "ait_knowledge_docs"
T_CHUNKS = "ait_knowledge_chunks"


def create_knowledge_doc(
    project_id: str, title: str, source_type: str, raw_content: Optional[str] = None
) -> dict:
    result = get_supabase().table(T_DOCS).insert({
        "project_id": project_id,
        "title": title,
        "source_type": source_type,
        "raw_content": raw_content,
    }).execute()
    return result.data[0]


def update_doc_status(doc_id: str, status: str, chunk_count: int) -> dict:
    result = (
        get_supabase().table(T_DOCS)
        .update({"status": status, "chunk_count": chunk_count})
        .eq("id", doc_id)
        .execute()
    )
    return result.data[0] if result.data else {}


def list_knowledge_docs(project_id: str) -> list[dict]:
    return (
        get_supabase().table(T_DOCS)
        .select("*")
        .eq("project_id", project_id)
        .order("created_at", desc=True)
        .execute()
    ).data


def delete_knowledge_doc(doc_id: str) -> None:
    get_supabase().table(T_DOCS).delete().eq("id", doc_id).execute()


def create_knowledge_chunk(
    doc_id: str, content: str, chunk_index: int, qdrant_point_id: str = ""
) -> dict:
    result = get_supabase().table(T_CHUNKS).insert({
        "doc_id": doc_id,
        "content": content,
        "chunk_index": chunk_index,
        "qdrant_point_id": qdrant_point_id or f"{doc_id}_{chunk_index}",
    }).execute()
    return result.data[0]


def search_knowledge_chunks(project_id: str, query: str, limit: int = 5) -> list[dict]:
    """Keyword search fallback"""
    docs = get_supabase().table(T_DOCS).select("id").eq("project_id", project_id).eq("status", "ready").execute()
    doc_ids = [d["id"] for d in docs.data]
    if not doc_ids:
        return []
    return (
        get_supabase().table(T_CHUNKS)
        .select("content, doc_id, chunk_index")
        .in_("doc_id", doc_ids)
        .ilike("content", f"%{query}%")
        .limit(limit)
        .execute()
    ).data


# ============================================
# Eval
# ============================================

T_TEST_CASES = "ait_eval_test_cases"
T_EVAL_RUNS = "ait_eval_runs"
T_EVAL_RESULTS = "ait_eval_results"


def create_test_case(
    project_id: str, input_text: str, expected_output: str,
    category: Optional[str] = None, created_by: Optional[str] = None
) -> dict:
    data: dict = {"project_id": project_id, "input_text": input_text, "expected_output": expected_output}
    if category:
        data["category"] = category
    if created_by:
        data["created_by"] = created_by
    return get_supabase().table(T_TEST_CASES).insert(data).execute().data[0]


def list_test_cases(project_id: str) -> list[dict]:
    return (
        get_supabase().table(T_TEST_CASES)
        .select("*").eq("project_id", project_id).eq("is_active", True)
        .order("created_at", desc=True).execute()
    ).data


def delete_test_case(test_case_id: str) -> None:
    get_supabase().table(T_TEST_CASES).update({"is_active": False}).eq("id", test_case_id).execute()


def create_eval_run(
    project_id: str, prompt_version_id: str, model_used: str,
    total_score: float, passed_count: int, failed_count: int
) -> dict:
    return get_supabase().table(T_EVAL_RUNS).insert({
        "project_id": project_id, "prompt_version_id": prompt_version_id,
        "model_used": model_used, "total_score": total_score,
        "passed_count": passed_count, "failed_count": failed_count,
    }).execute().data[0]


def create_eval_result(
    run_id: str, test_case_id: str, actual_output: str,
    score: float, passed: bool, details: dict = None
) -> dict:
    return get_supabase().table(T_EVAL_RESULTS).insert({
        "run_id": run_id, "test_case_id": test_case_id,
        "actual_output": actual_output, "score": score,
        "passed": passed, "details": details or {},
    }).execute().data[0]


def list_eval_runs(project_id: str) -> list[dict]:
    return (
        get_supabase().table(T_EVAL_RUNS)
        .select("*").eq("project_id", project_id)
        .order("run_at", desc=True).execute()
    ).data


def get_eval_run_details(run_id: str) -> dict:
    run = get_supabase().table(T_EVAL_RUNS).select("*").eq("id", run_id).execute()
    results = get_supabase().table(T_EVAL_RESULTS).select("*").eq("run_id", run_id).execute()
    return {"run": run.data[0] if run.data else None, "results": results.data}


# ============================================
# Fine-tune helpers
# ============================================

def get_correct_feedbacks_with_context(project_id: str) -> list[dict]:
    """Get training pairs from correct feedbacks"""
    sessions = get_supabase().table(T_SESSIONS).select("id").eq("project_id", project_id).execute()
    session_ids = [s["id"] for s in sessions.data]
    if not session_ids:
        return []
    messages = (
        get_supabase().table(T_MESSAGES)
        .select("id, session_id, role, content, created_at")
        .in_("session_id", session_ids).order("created_at").execute()
    )
    msg_ids = [m["id"] for m in messages.data if m["role"] == "assistant"]
    if not msg_ids:
        return []
    feedbacks = (
        get_supabase().table(T_FEEDBACKS)
        .select("message_id").in_("message_id", msg_ids).eq("rating", "correct").execute()
    )
    correct_ids = {f["message_id"] for f in feedbacks.data}
    pairs = []
    by_session: dict[str, list] = {}
    for m in messages.data:
        by_session.setdefault(m["session_id"], []).append(m)
    for session_msgs in by_session.values():
        for i, msg in enumerate(session_msgs):
            if msg["role"] == "assistant" and msg["id"] in correct_ids:
                for j in range(i - 1, -1, -1):
                    if session_msgs[j]["role"] == "user":
                        pairs.append({"user_message": session_msgs[j]["content"], "assistant_message": msg["content"]})
                        break
    return pairs


# ============================================
# Tools
# ============================================

T_TOOLS = "ait_tools"
T_AUDIT = "ait_audit_logs"


def create_tool(tenant_id: str, name: str, description: str, tool_type: str,
                config_json: dict, auth_config: dict = None,
                permissions: list = None, rate_limit: str = None) -> dict:
    data: dict = {"tenant_id": tenant_id, "name": name, "description": description,
                  "tool_type": tool_type, "config_json": config_json,
                  "auth_config": auth_config or {}, "permissions": permissions or ["admin", "trainer"]}
    if rate_limit:
        data["rate_limit"] = rate_limit
    return get_supabase().table(T_TOOLS).insert(data).execute().data[0]


def get_tool(tool_id: str) -> Optional[dict]:
    result = get_supabase().table(T_TOOLS).select("*").eq("id", tool_id).execute()
    return result.data[0] if result.data else None


def list_tools(tenant_id: str) -> list[dict]:
    return (
        get_supabase().table(T_TOOLS)
        .select("*").eq("tenant_id", tenant_id).eq("is_active", True)
        .order("created_at", desc=True).execute()
    ).data


def delete_tool(tool_id: str) -> None:
    get_supabase().table(T_TOOLS).update({"is_active": False}).eq("id", tool_id).execute()


def create_audit_log(tenant_id: str, user_id: Optional[str] = None, action_type: str = "",
                     tool_id: Optional[str] = None, request_data: dict = None,
                     response_data: dict = None, status: str = None, duration_ms: int = None) -> dict:
    data: dict = {"tenant_id": tenant_id, "action_type": action_type}
    if user_id:
        data["user_id"] = user_id
    if tool_id:
        data["tool_id"] = tool_id
    if request_data:
        data["request_data"] = request_data
    if response_data:
        data["response_data"] = response_data
    if status:
        data["status"] = status
    if duration_ms is not None:
        data["duration_ms"] = duration_ms
    return get_supabase().table(T_AUDIT).insert(data).execute().data[0]


# ============================================
# Workflows
# ============================================

T_WORKFLOWS = "ait_workflows"
T_WF_RUNS = "ait_workflow_runs"


def create_workflow(project_id: str, name: str, trigger_description: str, steps_json: list) -> dict:
    return get_supabase().table(T_WORKFLOWS).insert({
        "project_id": project_id, "name": name,
        "trigger_description": trigger_description, "steps_json": steps_json,
    }).execute().data[0]


def list_workflows(project_id: str) -> list[dict]:
    return (
        get_supabase().table(T_WORKFLOWS)
        .select("*").eq("project_id", project_id).eq("is_active", True)
        .order("created_at", desc=True).execute()
    ).data


def get_workflow(workflow_id: str) -> Optional[dict]:
    result = get_supabase().table(T_WORKFLOWS).select("*").eq("id", workflow_id).execute()
    return result.data[0] if result.data else None


def delete_workflow(workflow_id: str) -> None:
    get_supabase().table(T_WORKFLOWS).update({"is_active": False}).eq("id", workflow_id).execute()


def create_workflow_run(workflow_id: str, session_id: Optional[str], user_id: str) -> dict:
    data: dict = {"workflow_id": workflow_id, "user_id": user_id, "status": "running"}
    if session_id:
        data["session_id"] = session_id
    return get_supabase().table(T_WF_RUNS).insert(data).execute().data[0]


def update_workflow_run(run_id: str, current_step: str = None, status: str = None, context_json: dict = None) -> dict:
    data: dict = {}
    if current_step is not None:
        data["current_step"] = current_step
    if status:
        data["status"] = status
    if context_json is not None:
        data["context_json"] = context_json
    result = get_supabase().table(T_WF_RUNS).update(data).eq("id", run_id).execute()
    return result.data[0] if result.data else {}


def get_workflow_run(run_id: str) -> Optional[dict]:
    result = get_supabase().table(T_WF_RUNS).select("*").eq("id", run_id).execute()
    return result.data[0] if result.data else None
