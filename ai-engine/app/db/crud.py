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
T_PIPELINE_RUNS = "ait_pipeline_runs"
T_PIPELINE_CMP = "ait_pipeline_node_comparisons"


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


def get_or_create_external_user(
    tenant_id: str,
    external_id: Optional[str] = None,
) -> dict:
    """
    Get or create a guest user for external (embed/API) requests.

    If external_id is provided, create a deterministic email like
    `external_<id>@embed.local` so repeat visitors map to the same user.
    Otherwise create an anonymous guest with a random external_id.
    """
    if not external_id:
        import secrets
        external_id = f"anon_{secrets.token_urlsafe(8)}"

    email = f"external_{external_id}@embed.local"
    existing = get_user_by_email(email)
    if existing and existing.get("tenant_id") == tenant_id:
        return existing

    # Create new guest user
    return create_user(
        tenant_id=tenant_id,
        email=email,
        role="viewer",
        display_name=f"Guest {external_id[:12]}",
    )


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


def list_projects_by_ids(project_ids: list[str]) -> list[dict]:
    """Batch fetch projects by id (for embed token multi-project support)."""
    if not project_ids:
        return []
    result = (
        get_supabase().table(T_PROJECTS)
        .select("id,tenant_id,name,description,created_at")
        .in_("id", project_ids)
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


def list_sessions(
    project_id: str,
    user_id: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    query = (
        get_supabase().table(T_SESSIONS)
        .select("*")
        .eq("project_id", project_id)
        .order("started_at", desc=True)
        .limit(limit)
    )
    if user_id:
        query = query.eq("user_id", user_id)
    return query.execute().data


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


def get_eval_score_trend(project_id: str, limit: int = 20) -> list[dict]:
    """取最近 N 次 eval run 的分數趨勢"""
    return (
        get_supabase().table(T_EVAL_RUNS)
        .select("id, total_score, passed_count, failed_count, run_at, prompt_version_id, model_used")
        .eq("project_id", project_id)
        .order("run_at", desc=True).limit(limit).execute()
    ).data


def get_category_analytics(project_id: str, run_id: str) -> list[dict]:
    """按 category 分群的平均分/通過率"""
    results = get_supabase().table(T_EVAL_RESULTS).select("*").eq("run_id", run_id).execute().data
    if not results:
        return []
    tc_ids = list({r["test_case_id"] for r in results})
    test_cases = (
        get_supabase().table(T_TEST_CASES)
        .select("id, category").in_("id", tc_ids).execute()
    ).data
    tc_map = {tc["id"]: tc.get("category") or "Uncategorized" for tc in test_cases}

    # Aggregate by category
    cats: dict[str, dict] = {}
    for r in results:
        cat = tc_map.get(r["test_case_id"], "Uncategorized")
        if cat not in cats:
            cats[cat] = {"category": cat, "total_score": 0, "passed_count": 0, "failed_count": 0, "total": 0}
        cats[cat]["total_score"] += r["score"]
        cats[cat]["total"] += 1
        if r["passed"]:
            cats[cat]["passed_count"] += 1
        else:
            cats[cat]["failed_count"] += 1

    return [
        {**c, "avg_score": round(c["total_score"] / c["total"], 1) if c["total"] else 0}
        for c in cats.values()
    ]


def get_regression_comparison(project_id: str, current_run_id: str) -> dict:
    """對比當前 run 與前一次 run，找出退步/改善的 case"""
    runs = (
        get_supabase().table(T_EVAL_RUNS)
        .select("id, total_score, run_at")
        .eq("project_id", project_id)
        .order("run_at", desc=True).limit(10).execute()
    ).data

    current_run = None
    previous_run = None
    found_current = False
    for r in runs:
        if r["id"] == current_run_id:
            current_run = r
            found_current = True
            continue
        if found_current:
            previous_run = r
            break

    if not current_run or not previous_run:
        return {"regression_detected": False, "overall_delta": 0, "regressions": [], "improvements": [], "message": "No previous run to compare"}

    # Fetch results for both runs
    cur_results = get_supabase().table(T_EVAL_RESULTS).select("*").eq("run_id", current_run["id"]).execute().data
    prev_results = get_supabase().table(T_EVAL_RESULTS).select("*").eq("run_id", previous_run["id"]).execute().data

    prev_map = {r["test_case_id"]: r for r in prev_results}
    regressions = []
    improvements = []

    for cr in cur_results:
        pr = prev_map.get(cr["test_case_id"])
        if not pr:
            continue
        delta = cr["score"] - pr["score"]
        item = {"test_case_id": cr["test_case_id"], "old_score": pr["score"], "new_score": cr["score"], "delta": round(delta, 1)}
        if delta < -5:
            regressions.append(item)
        elif delta > 5:
            improvements.append(item)

    overall_delta = round(current_run["total_score"] - previous_run["total_score"], 1)
    regression_detected = overall_delta < -5 or any(r["delta"] < -15 for r in regressions)

    return {
        "regression_detected": regression_detected,
        "overall_delta": overall_delta,
        "current_score": current_run["total_score"],
        "previous_score": previous_run["total_score"],
        "regressions": regressions,
        "improvements": improvements,
    }


def get_prompt_version_comparison(project_id: str, version_ids: list[str]) -> list[dict]:
    """多版本 eval 成績比較"""
    result = []
    for vid in version_ids:
        runs = (
            get_supabase().table(T_EVAL_RUNS)
            .select("*").eq("project_id", project_id).eq("prompt_version_id", vid)
            .order("run_at", desc=True).limit(1).execute()
        ).data
        if runs:
            run = runs[0]
            # Get category breakdown
            cats = get_category_analytics(project_id, run["id"])
            result.append({
                "prompt_version_id": vid,
                "run_id": run["id"],
                "total_score": run["total_score"],
                "passed_count": run["passed_count"],
                "failed_count": run["failed_count"],
                "run_at": run["run_at"],
                "model_used": run["model_used"],
                "categories": cats,
            })
        else:
            result.append({"prompt_version_id": vid, "run_id": None, "total_score": None})
    return result


def get_phase_status(project_id: str) -> dict:
    """計算 test case 數量、一致率、是否達自動化門檻"""
    cases = (
        get_supabase().table(T_TEST_CASES)
        .select("id").eq("project_id", project_id).eq("is_active", True).execute()
    ).data
    test_case_count = len(cases)

    runs = (
        get_supabase().table(T_EVAL_RUNS)
        .select("id, total_score, passed_count, failed_count")
        .eq("project_id", project_id)
        .order("run_at", desc=True).limit(1).execute()
    ).data

    latest_score = None
    agreement_rate = None
    if runs:
        latest = runs[0]
        latest_score = latest["total_score"]
        total = latest["passed_count"] + latest["failed_count"]
        agreement_rate = round((latest["passed_count"] / total) * 100, 1) if total > 0 else 0

    auto_eligible = test_case_count >= 200 and (agreement_rate or 0) >= 90
    if auto_eligible:
        phase = "full-auto"
    elif test_case_count >= 50 and (agreement_rate or 0) >= 70:
        phase = "semi-auto"
    else:
        phase = "manual"

    run_count = len((
        get_supabase().table(T_EVAL_RUNS)
        .select("id").eq("project_id", project_id).execute()
    ).data)

    return {
        "test_case_count": test_case_count,
        "run_count": run_count,
        "latest_score": latest_score,
        "agreement_rate": agreement_rate,
        "auto_mode_eligible": auto_eligible,
        "current_phase": phase,
    }


def update_prompt_eval_score(version_id: str, score: float) -> None:
    """更新 prompt version 的 eval_score"""
    get_supabase().table(T_PROMPTS).update({"eval_score": round(score, 1)}).eq("id", version_id).execute()


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


T_FINETUNE_JOBS = "ait_finetune_jobs"


def create_finetune_job(project_id: str, provider: str, model_base: str, training_data_count: int) -> dict:
    return get_supabase().table(T_FINETUNE_JOBS).insert({
        "project_id": project_id, "provider": provider,
        "model_base": model_base, "training_data_count": training_data_count,
        "status": "pending",
    }).execute().data[0]


def list_finetune_jobs(project_id: str) -> list[dict]:
    return (
        get_supabase().table(T_FINETUNE_JOBS)
        .select("*").eq("project_id", project_id)
        .order("created_at", desc=True).execute()
    ).data


def get_finetune_job(job_id: str) -> Optional[dict]:
    result = get_supabase().table(T_FINETUNE_JOBS).select("*").eq("id", job_id).execute()
    return result.data[0] if result.data else None


def update_finetune_job(job_id: str, status: str = None, result_model_id: str = None, error_message: str = None) -> dict:
    data: dict = {}
    if status:
        data["status"] = status
    if result_model_id:
        data["result_model_id"] = result_model_id
    if error_message is not None:
        data["error_message"] = error_message
    if status in ("completed", "failed"):
        data["completed_at"] = "now()"
    result = get_supabase().table(T_FINETUNE_JOBS).update(data).eq("id", job_id).execute()
    return result.data[0] if result.data else {}


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
# Capability Rules
# ============================================

T_CAPABILITY_RULES = "ait_capability_rules"


def create_capability_rule(
    project_id: str, trigger_description: str, action_type: str,
    action_config: dict, trigger_keywords: list = None, priority: int = 0,
    created_by: str = None
) -> dict:
    data: dict = {
        "project_id": project_id,
        "trigger_description": trigger_description,
        "action_type": action_type,
        "action_config": action_config,
        "priority": priority,
    }
    if trigger_keywords:
        data["trigger_keywords"] = trigger_keywords
    if created_by:
        data["created_by"] = created_by
    return get_supabase().table(T_CAPABILITY_RULES).insert(data).execute().data[0]


def list_capability_rules(project_id: str) -> list[dict]:
    return (
        get_supabase().table(T_CAPABILITY_RULES)
        .select("*").eq("project_id", project_id).eq("is_active", True)
        .order("priority", desc=True).execute()
    ).data


def get_capability_rule(rule_id: str) -> Optional[dict]:
    result = get_supabase().table(T_CAPABILITY_RULES).select("*").eq("id", rule_id).execute()
    return result.data[0] if result.data else None


def update_capability_rule(rule_id: str, **kwargs) -> dict:
    data = {k: v for k, v in kwargs.items() if v is not None}
    result = get_supabase().table(T_CAPABILITY_RULES).update(data).eq("id", rule_id).execute()
    return result.data[0] if result.data else {}


def delete_capability_rule(rule_id: str) -> None:
    get_supabase().table(T_CAPABILITY_RULES).update({"is_active": False}).eq("id", rule_id).execute()


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


def list_workflow_runs(workflow_id: str) -> list[dict]:
    return (
        get_supabase().table(T_WF_RUNS)
        .select("*").eq("workflow_id", workflow_id)
        .order("started_at", desc=True).execute()
    ).data


def get_workflow_run(run_id: str) -> Optional[dict]:
    result = get_supabase().table(T_WF_RUNS).select("*").eq("id", run_id).execute()
    return result.data[0] if result.data else None


# ============================================
# Pipeline Studio (Phase 7)
# ============================================

def list_pipeline_runs(
    project_id: str,
    limit: int = 50,
    mode: Optional[str] = None,
    cursor_created_at: Optional[str] = None,
) -> list[dict]:
    """列出專案最近的 pipeline runs(新到舊)。

    回傳時只帶摘要欄位,nodes_json 另外用 get_pipeline_run() 讀。
    """
    q = (
        get_supabase().table(T_PIPELINE_RUNS)
        .select(
            "id, project_id, session_id, message_id, mode, input_text, "
            "total_cost_usd, total_duration_ms, status, parent_run_id, created_at"
        )
        .eq("project_id", project_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if mode:
        q = q.eq("mode", mode)
    if cursor_created_at:
        q = q.lt("created_at", cursor_created_at)
    return q.execute().data or []


def get_pipeline_run(run_id: str) -> Optional[dict]:
    """取單一 run 完整內容(含 nodes_json)。"""
    result = (
        get_supabase().table(T_PIPELINE_RUNS)
        .select("*")
        .eq("id", run_id)
        .execute()
    )
    return result.data[0] if result.data else None


def list_pipeline_comparisons(run_id: str) -> list[dict]:
    """取某個 run 下所有節點的多模型比較候選。"""
    result = (
        get_supabase().table(T_PIPELINE_CMP)
        .select("*")
        .eq("pipeline_run_id", run_id)
        .order("created_at")
        .execute()
    )
    return result.data or []


def create_pipeline_comparison(data: dict) -> dict:
    """新增一筆 node 多模型比較候選(Lab v1 用)。"""
    result = get_supabase().table(T_PIPELINE_CMP).insert(data).execute()
    return result.data[0] if result.data else {}


def select_pipeline_comparison(comparison_id: str) -> Optional[dict]:
    """把 comparison 標記為 is_selected=true(同節點其他候選自動取消)。"""
    supabase = get_supabase()
    cmp_row = (
        supabase.table(T_PIPELINE_CMP)
        .select("*")
        .eq("id", comparison_id)
        .execute()
    )
    if not cmp_row.data:
        return None
    row = cmp_row.data[0]
    # 先把同 run + node 其他候選的 is_selected 關掉(避免 partial unique index 衝突)
    supabase.table(T_PIPELINE_CMP).update({"is_selected": False}).eq(
        "pipeline_run_id", row["pipeline_run_id"]
    ).eq("node_id", row["node_id"]).execute()
    # 再把這筆打開
    updated = (
        supabase.table(T_PIPELINE_CMP)
        .update({"is_selected": True})
        .eq("id", comparison_id)
        .execute()
    )
    return updated.data[0] if updated.data else None
