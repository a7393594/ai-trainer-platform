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
# Default Domain Configs (per project_type)
# ============================================

def _deep_merge(base: dict, override: dict) -> dict:
    """Deep-merge override into base (non-destructive)."""
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


DEFAULT_DOMAIN_CONFIGS: dict[str, dict] = {
    "trainer": {
        "nav": [
            {"href": "/overview",     "label": "nav.overview",  "icon": "📊"},
            {"href": "/chat",         "label": "nav.train",     "icon": "💬"},
            {"href": "/comparison",   "label": "nav.comparison","icon": "⚖️"},
            {"href": "/prompts",      "label": "nav.prompts",   "icon": "✏️"},
            {"href": "/behavior",     "label": "nav.behavior",  "icon": "🧠"},
            {"href": "/enhance",      "label": "nav.enhance",   "icon": "🧰"},
            {"href": "/studio",       "label": "nav.studio",    "icon": "🧬"},
            {"href": "/lab",          "label": "nav.lab",       "icon": "🧪"},
            {"href": "/knowledge",    "label": "nav.knowledge", "icon": "📚"},
            {"href": "/integrations", "label": "nav.deploy",    "icon": "🔌"},
            {"href": "/settings",     "label": "nav.settings",  "icon": "⚙️"},
        ],
        "terms": {"session": "Training Session", "knowledgeBase": "Knowledge Base"},
        "features": {
            "eval": True, "finetune": True, "pipeline_studio": True,
            "knowledge_rag": True, "confidence_scoring": False,
            "multi_model_voting": False, "challenge_mode": False,
        },
        "chat": {"mode": "orchestrator", "streaming": True},
    },
    "referee": {
        "nav": [
            {"href": "/overview",   "label": "nav.referee.dashboard", "icon": "📊"},
            {"href": "/chat",       "label": "nav.referee.submit",    "icon": "📝"},
            {"href": "/history",    "label": "nav.referee.history",   "icon": "📋"},
            {"href": "/knowledge",  "label": "nav.referee.knowledge", "icon": "📚"},
            {"href": "/settings",   "label": "nav.referee.settings",  "icon": "⚙️"},
        ],
        "terms": {
            "case": "Dispute", "ruling": "Ruling", "rule": "Rule",
            "knowledgeBase": "Rule Library", "confidence": "Confidence",
            "challenge": "Challenge",
        },
        "contextFields": [
            {"key": "game_type", "label": "Game Type", "type": "select",
             "options": ["NLHE", "PLO", "Limit", "Stud"]},
            {"key": "pot_size", "label": "Pot Size", "type": "number", "placeholder": "15000"},
            {"key": "blind_level", "label": "Blinds", "type": "text", "placeholder": "500/1000"},
        ],
        "modes": {
            "A": {"label": "Auto Decide",   "color": "emerald"},
            "B": {"label": "Challengeable", "color": "blue"},
            "C": {"label": "Human Confirm", "color": "amber"},
            "escalated": {"label": "Escalated", "color": "red"},
        },
        "features": {
            "eval": False, "finetune": False, "pipeline_studio": False,
            "knowledge_rag": True, "confidence_scoring": True,
            "multi_model_voting": True, "challenge_mode": True,
        },
        "chat": {"mode": "referee_engine", "streaming": False},
        "referee": {
            "primary_model": "claude-opus-4-6",
            "backup_model": "gpt-5.4",
            "triage_model": "claude-haiku-4-5-20251001",
            "auto_decide_threshold": 0.85,
            "human_confirm_threshold": 0.60,
            "enable_dual_model": True,
            "enable_triple_model": False,
            "voting_temperature": 0.3,
            "consistency_samples": 3,
        },
    },
    "poker_coach": {
        "nav": [
            # ── 撲克教練（玩家面向）──
            {"href": "/overview",       "label": "nav.overview",         "icon": "📊"},
            {"href": "/chat",           "label": "nav.train",            "icon": "💬"},
            {"href": "/poker-stats",    "label": "nav.poker.stats",     "icon": "📈"},
            {"href": "/poker-upload",   "label": "nav.poker.upload",    "icon": "📥"},
            {"href": "/poker-review",   "label": "nav.poker.review",   "icon": "🔍"},
            {"href": "/poker-mastery",  "label": "nav.poker.mastery",  "icon": "🎯"},
            {"href": "/poker-opponent", "label": "nav.poker.opponent", "icon": "🥊"},
            {"href": "/poker-drill",    "label": "nav.poker.drill",    "icon": "🧩"},
            {"href": "/poker-audit",    "label": "nav.poker.audit",    "icon": "📋"},
            # ── 訓練中間層（管理員面向）──
            {"href": "/comparison",     "label": "nav.comparison",      "icon": "⚖️"},
            {"href": "/eval",           "label": "nav.eval",            "icon": "🧪"},
            {"href": "/behavior",       "label": "nav.behavior",        "icon": "🧠"},
            {"href": "/enhance",        "label": "nav.enhance",         "icon": "🧰"},
            {"href": "/knowledge",      "label": "nav.knowledge",       "icon": "📚"},
            {"href": "/prompts",        "label": "nav.prompts",         "icon": "✏️"},
            {"href": "/studio",         "label": "nav.studio",          "icon": "🧬"},
            {"href": "/lab",            "label": "nav.lab",             "icon": "🧪"},
            {"href": "/tools",          "label": "nav.tools",           "icon": "🔧"},
            {"href": "/capabilities",   "label": "nav.capabilities",   "icon": "⚡"},
            {"href": "/workflows",      "label": "nav.workflows",      "icon": "🔄"},
            {"href": "/finetune",       "label": "nav.finetune",       "icon": "🎛️"},
            {"href": "/usage",          "label": "nav.usage",           "icon": "💰"},
            {"href": "/integrations",   "label": "nav.deploy",          "icon": "🔌"},
            {"href": "/settings",       "label": "nav.settings",        "icon": "⚙️"},
        ],
        "terms": {
            "session": "Training Session",
            "knowledgeBase": "Knowledge Base",
        },
        "features": {
            "eval": True, "finetune": True, "pipeline_studio": True,
            "knowledge_rag": True, "student_model": True,
            "hand_history": True, "solver": True,
            "confidence_scoring": False, "multi_model_voting": False,
        },
        "chat": {"mode": "poker_coach", "streaming": True},
    },
}


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


def update_tenant_settings(tenant_id: str, settings_patch: dict) -> Optional[dict]:
    """Merge-patch tenant.settings JSONB field."""
    tenant = get_tenant(tenant_id)
    if not tenant:
        return None
    merged = {**(tenant.get("settings") or {}), **(settings_patch or {})}
    r = get_supabase().table(T_TENANTS).update({"settings": merged}).eq("id", tenant_id).execute()
    return r.data[0] if r.data else None


def update_tenant_plan(tenant_id: str, plan: str) -> Optional[dict]:
    r = get_supabase().table(T_TENANTS).update({"plan": plan}).eq("id", tenant_id).execute()
    return r.data[0] if r.data else None


def get_tenant_monthly_cost(tenant_id: str) -> float:
    """Sum cost_usd for the current calendar month across all projects of tenant."""
    from datetime import datetime, timezone

    now = datetime.now(tz=timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    # Projects under this tenant
    projects = (
        get_supabase().table("ait_projects").select("id").eq("tenant_id", tenant_id).execute()
    ).data or []
    if not projects:
        return 0.0
    pids = [p["id"] for p in projects]
    total = 0.0
    # Batch in chunks
    for i in range(0, len(pids), 50):
        chunk = pids[i : i + 50]
        rows = (
            get_supabase().table("ait_llm_usage")
            .select("cost_usd")
            .in_("project_id", chunk)
            .gte("created_at", month_start)
            .execute()
        ).data or []
        total += sum(r.get("cost_usd") or 0 for r in rows)
    return float(total)


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
    project_type: str = "trainer",
    domain_config: Optional[dict] = None,
) -> dict:
    data = {
        "tenant_id": tenant_id,
        "name": name,
        "project_type": project_type,
        "domain_config": domain_config or DEFAULT_DOMAIN_CONFIGS.get(project_type, {}),
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


def get_project_config(project_id: str) -> Optional[dict]:
    """Return project with domain_config merged over defaults for its type."""
    project = get_project(project_id)
    if not project:
        return None
    ptype = project.get("project_type", "trainer")
    defaults = DEFAULT_DOMAIN_CONFIGS.get(ptype, {})
    stored = project.get("domain_config") or {}
    project["domain_config"] = _deep_merge(defaults, stored)
    return project


def update_project_config(project_id: str, partial_config: dict) -> Optional[dict]:
    """Partial JSONB merge update on domain_config."""
    project = get_project(project_id)
    if not project:
        return None
    current = project.get("domain_config") or {}
    merged = _deep_merge(current, partial_config)
    result = (
        get_supabase().table(T_PROJECTS)
        .update({"domain_config": merged})
        .eq("id", project_id)
        .execute()
    )
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
        .select("id,tenant_id,name,description,project_type,created_at")
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
    offset: int = 0,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search: Optional[str] = None,
) -> list[dict]:
    """List sessions with optional filters.

    Args:
        date_from/date_to: ISO8601 strings (YYYY-MM-DD or full timestamp)
        search: full-text search term — matches against any message content in the session
    """
    # If search is given, find session_ids whose messages contain the term first
    matching_session_ids: Optional[list[str]] = None
    if search:
        msg_query = (
            get_supabase().table(T_MESSAGES)
            .select("session_id")
            .ilike("content", f"%{search}%")
            .limit(500)
        )
        msg_res = msg_query.execute().data or []
        matching_session_ids = list({m["session_id"] for m in msg_res})
        if not matching_session_ids:
            return []  # no matches

    query = (
        get_supabase().table(T_SESSIONS)
        .select("*")
        .eq("project_id", project_id)
        .order("started_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if user_id:
        query = query.eq("user_id", user_id)
    if date_from:
        query = query.gte("started_at", date_from)
    if date_to:
        query = query.lte("started_at", date_to)
    if matching_session_ids is not None:
        query = query.in_("id", matching_session_ids)
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


def get_feedback_stats_window(project_id: str, since_iso: str) -> dict:
    """取得指定時間窗內的回饋統計（不受 1000 筆 cap）。"""
    db = get_supabase()
    sessions = db.table(T_SESSIONS).select("id").eq("project_id", project_id).execute().data or []
    sids = [s["id"] for s in sessions]
    if not sids:
        return {"correct": 0, "partial": 0, "wrong": 0, "total": 0}
    stats = {"correct": 0, "partial": 0, "wrong": 0, "total": 0}
    for i in range(0, len(sids), 50):
        chunk = sids[i : i + 50]
        msgs = db.table(T_MESSAGES).select("id").in_("session_id", chunk).eq("role", "assistant").execute().data or []
        mids = [m["id"] for m in msgs]
        for j in range(0, len(mids), 50):
            mchunk = mids[j : j + 50]
            fbs = (
                db.table(T_FEEDBACKS).select("rating")
                .in_("message_id", mchunk)
                .gte("created_at", since_iso)
                .execute()
            ).data or []
            for fb in fbs:
                r = fb.get("rating") or ""
                if r in stats:
                    stats[r] += 1
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


def get_prompt_version(version_id: str) -> Optional[dict]:
    r = get_supabase().table(T_PROMPTS).select("*").eq("id", version_id).execute()
    return r.data[0] if r.data else None


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
    results_data = results.data or []
    # 附上 test_case 詳情（input/expected/category）
    if results_data:
        tc_ids = list({r["test_case_id"] for r in results_data if r.get("test_case_id")})
        if tc_ids:
            tcs = (
                get_supabase().table(T_TEST_CASES)
                .select("id,input_text,expected_output,category").in_("id", tc_ids).execute()
            ).data or []
            tc_map = {tc["id"]: tc for tc in tcs}
            for r in results_data:
                r["test_case"] = tc_map.get(r.get("test_case_id"))
    return {"run": run.data[0] if run.data else None, "results": results_data}


def get_eval_run(run_id: str) -> Optional[dict]:
    r = get_supabase().table(T_EVAL_RUNS).select("*").eq("id", run_id).execute()
    return r.data[0] if r.data else None


def update_eval_result(
    result_id: str,
    score: Optional[float] = None,
    passed: Optional[bool] = None,
    details: Optional[dict] = None,
) -> dict:
    data: dict = {}
    if score is not None:
        data["score"] = score
    if passed is not None:
        data["passed"] = passed
    if details is not None:
        data["details"] = details
    if not data:
        return {}
    r = get_supabase().table(T_EVAL_RESULTS).update(data).eq("id", result_id).execute()
    return r.data[0] if r.data else {}


def update_eval_run_scores(
    run_id: str,
    total_score: Optional[float] = None,
    passed_count: Optional[int] = None,
    failed_count: Optional[int] = None,
) -> dict:
    data: dict = {}
    if total_score is not None:
        data["total_score"] = total_score
    if passed_count is not None:
        data["passed_count"] = passed_count
    if failed_count is not None:
        data["failed_count"] = failed_count
    if not data:
        return {}
    r = get_supabase().table(T_EVAL_RUNS).update(data).eq("id", run_id).execute()
    return r.data[0] if r.data else {}


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


def list_audit_logs(
    tenant_id: str,
    action_type: Optional[str] = None,
    tool_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    q = (
        get_supabase().table(T_AUDIT)
        .select("id,tenant_id,user_id,action_type,tool_id,status,duration_ms,request_data,response_data,created_at")
        .eq("tenant_id", tenant_id)
    )
    if action_type:
        q = q.eq("action_type", action_type)
    if tool_id:
        q = q.eq("tool_id", tool_id)
    if status:
        q = q.eq("status", status)
    return (
        q.order("created_at", desc=True)
        .range(offset, offset + min(limit, 500) - 1)
        .execute()
    ).data or []


def get_tool_call_stats(tenant_id: str, since_iso: Optional[str] = None) -> dict:
    """按 tool 聚合呼叫統計（呼叫次數、成功率、平均延遲、錯誤筆數）。"""
    q = (
        get_supabase().table(T_AUDIT)
        .select("tool_id, status, duration_ms, created_at")
        .eq("tenant_id", tenant_id)
        .eq("action_type", "tool_call")
    )
    if since_iso:
        q = q.gte("created_at", since_iso)
    rows = q.execute().data or []

    by_tool: dict[str, dict] = {}
    for r in rows:
        tid = r.get("tool_id") or "unknown"
        bucket = by_tool.setdefault(tid, {"calls": 0, "success": 0, "error": 0, "dry_run": 0, "total_latency": 0})
        bucket["calls"] += 1
        status = r.get("status") or "success"
        if status in bucket:
            bucket[status] += 1
        else:
            bucket.setdefault(status, 0)
            bucket[status] += 1
        bucket["total_latency"] += r.get("duration_ms") or 0

    # 解析 tool name
    ids = [k for k in by_tool.keys() if k != "unknown"]
    name_map: dict[str, str] = {}
    if ids:
        for i in range(0, len(ids), 50):
            chunk = ids[i : i + 50]
            tools = get_supabase().table(T_TOOLS).select("id,name,tool_type").in_("id", chunk).execute().data or []
            for t in tools:
                name_map[t["id"]] = t.get("name") or t["id"][:8]

    for tid, b in by_tool.items():
        b["avg_latency_ms"] = round(b["total_latency"] / b["calls"]) if b["calls"] else 0
        b["success_rate"] = round(b["success"] / b["calls"], 3) if b["calls"] else 0
        b["name"] = name_map.get(tid, "unknown" if tid == "unknown" else tid[:8])

    return {"total_calls": len(rows), "by_tool": by_tool}


def update_project_default_model(project_id: str, default_model: str) -> Optional[dict]:
    r = get_supabase().table("ait_projects").update({"default_model": default_model}).eq("id", project_id).execute()
    return r.data[0] if r.data else None


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


def get_pipeline_run_by_message(message_id: str) -> Optional[dict]:
    """依 message_id 查 pipeline run（用於 history 頁面展開 trace）。"""
    result = (
        get_supabase().table(T_PIPELINE_RUNS)
        .select("*")
        .eq("message_id", message_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


# ============================================================================
# Batch 4A: Rerun Presets (named node configurations)
# ============================================================================

T_RERUN_PRESETS = "ait_rerun_presets"


def list_rerun_presets(project_id: str, node_type: Optional[str] = None) -> list[dict]:
    """列出專案的所有 preset，可選依 node_type 過濾。"""
    q = (
        get_supabase().table(T_RERUN_PRESETS)
        .select("*")
        .eq("project_id", project_id)
        .order("created_at", desc=True)
    )
    if node_type:
        q = q.eq("node_type", node_type)
    return q.execute().data or []


def create_rerun_preset(data: dict) -> dict:
    """建立新 preset。上層應驗證 data 包含必要欄位。"""
    result = get_supabase().table(T_RERUN_PRESETS).insert(data).execute()
    return result.data[0] if result.data else {}


def delete_rerun_preset(preset_id: str) -> None:
    get_supabase().table(T_RERUN_PRESETS).delete().eq("id", preset_id).execute()


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

T_SOURCES = "pkr_rule_sources"
T_RULES = "pkr_rules"
T_RULINGS = "pkr_rulings"
T_AUDIT = "pkr_audit_logs"


# ============================================
# Rule Sources
# ============================================

def create_rule_source(name: str, priority: int, version: str = None, effective_date: str = None) -> dict:
    data = {"name": name, "priority": priority}
    if version:
        data["version"] = version
    if effective_date:
        data["effective_date"] = effective_date
    return get_supabase().table(T_SOURCES).insert(data).execute().data[0]


def list_rule_sources() -> list[dict]:
    return get_supabase().table(T_SOURCES).select("*").order("priority").execute().data


def get_rule_source(source_id: str) -> Optional[dict]:
    result = get_supabase().table(T_SOURCES).select("*").eq("id", source_id).execute()
    return result.data[0] if result.data else None


# ============================================
# Rules
# ============================================

def create_rule(data: dict) -> dict:
    return get_supabase().table(T_RULES).insert(data).execute().data[0]


def get_rule(rule_id: str) -> Optional[dict]:
    result = get_supabase().table(T_RULES).select("*").eq("id", rule_id).execute()
    return result.data[0] if result.data else None


def get_rule_by_code(rule_code: str) -> Optional[dict]:
    result = get_supabase().table(T_RULES).select("*").eq("rule_code", rule_code).execute()
    return result.data[0] if result.data else None


def list_rules(source_id: str = None, topic: str = None) -> list[dict]:
    q = get_supabase().table(T_RULES).select("*")
    if source_id:
        q = q.eq("source_id", source_id)
    if topic:
        q = q.contains("topic_tags", [topic])
    return q.order("rule_code").execute().data


def search_rules_by_text(query: str, limit: int = 10) -> list[dict]:
    """全文搜尋規則條文(用 ilike fallback)"""
    results = []
    for kw in query.split()[:3]:
        rows = (
            get_supabase().table(T_RULES)
            .select("*")
            .ilike("rule_text", f"%{kw}%")
            .limit(limit)
            .execute()
        ).data or []
        results.extend(rows)
    # 去重
    seen = set()
    deduped = []
    for r in results:
        if r["id"] not in seen:
            seen.add(r["id"])
            deduped.append(r)
    return deduped[:limit]


# ============================================
# Rulings
# ============================================

def create_ruling(data: dict, project_id: Optional[str] = None) -> dict:
    if project_id:
        data["project_id"] = project_id
    return get_supabase().table(T_RULINGS).insert(data).execute().data[0]


def get_ruling(ruling_id: str) -> Optional[dict]:
    result = get_supabase().table(T_RULINGS).select("*").eq("id", ruling_id).execute()
    return result.data[0] if result.data else None


def list_rulings(limit: int = 50, project_id: Optional[str] = None) -> list[dict]:
    q = get_supabase().table(T_RULINGS).select("*")
    if project_id:
        q = q.eq("project_id", project_id)
    return q.order("created_at", desc=True).limit(limit).execute().data


# ============================================
# Audit Logs
# ============================================

def create_audit_log(ruling_id: str, full_log: dict, project_id: Optional[str] = None) -> dict:
    data = {"ruling_id": ruling_id, "full_log": full_log}
    if project_id:
        data["project_id"] = project_id
    return get_supabase().table(T_AUDIT).insert(data).execute().data[0]


def get_audit_log(ruling_id: str) -> Optional[dict]:
    result = (
        get_supabase().table(T_AUDIT)
        .select("*")
        .eq("ruling_id", ruling_id)
        .execute()
    )
    return result.data[0] if result.data else None
