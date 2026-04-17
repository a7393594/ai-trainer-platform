"""
CRUD — Poker Coach 專用資料存取層

Tables: ait_student_profiles, ait_concepts, ait_user_concept_mastery
"""
from typing import Optional
from app.db.supabase import get_supabase

T_PROFILES = "ait_student_profiles"
T_CONCEPTS = "ait_concepts"
T_MASTERY = "ait_user_concept_mastery"


# ============================================
# Student Profiles
# ============================================

def get_or_create_student_profile(user_id: str, project_id: str) -> dict:
    """取得或建立學生 profile"""
    sb = get_supabase()
    existing = (
        sb.table(T_PROFILES).select("*")
        .eq("user_id", user_id).eq("project_id", project_id)
        .execute()
    )
    if existing.data:
        return existing.data[0]
    result = sb.table(T_PROFILES).insert({
        "user_id": user_id,
        "project_id": project_id,
    }).execute()
    return result.data[0]


def get_student_profile(user_id: str, project_id: str) -> Optional[dict]:
    result = (
        get_supabase().table(T_PROFILES).select("*")
        .eq("user_id", user_id).eq("project_id", project_id)
        .execute()
    )
    return result.data[0] if result.data else None


def update_student_profile(profile_id: str, updates: dict) -> dict:
    updates["updated_at"] = "now()"
    result = (
        get_supabase().table(T_PROFILES)
        .update(updates).eq("id", profile_id).execute()
    )
    return result.data[0] if result.data else {}


def update_profile_activity(profile_id: str):
    """更新最後活動時間"""
    get_supabase().table(T_PROFILES).update({
        "last_active_at": "now()", "updated_at": "now()"
    }).eq("id", profile_id).execute()


# ============================================
# Concepts
# ============================================

def list_concepts(project_id: str) -> list[dict]:
    return (
        get_supabase().table(T_CONCEPTS).select("*")
        .eq("project_id", project_id)
        .order("category").order("difficulty")
        .execute()
    ).data


def get_concept_by_code(project_id: str, code: str) -> Optional[dict]:
    result = (
        get_supabase().table(T_CONCEPTS).select("*")
        .eq("project_id", project_id).eq("code", code)
        .execute()
    )
    return result.data[0] if result.data else None


# ============================================
# User Concept Mastery
# ============================================

def get_user_mastery(user_id: str, project_id: str) -> list[dict]:
    """取得使用者所有概念掌握度（join concept name）"""
    concepts = list_concepts(project_id)
    concept_map = {c["id"]: c for c in concepts}

    mastery = (
        get_supabase().table(T_MASTERY).select("*")
        .eq("user_id", user_id)
        .execute()
    ).data

    # Filter to this project's concepts and enrich
    result = []
    for m in mastery:
        concept = concept_map.get(m["concept_id"])
        if concept:
            m["concept_code"] = concept["code"]
            m["concept_name"] = concept["name"]
            m["category"] = concept["category"]
            m["difficulty"] = concept["difficulty"]
            result.append(m)
    return result


def init_mastery_for_user(user_id: str, project_id: str):
    """為使用者初始化所有概念的 mastery records（idempotent）"""
    sb = get_supabase()
    concepts = list_concepts(project_id)

    existing = (
        sb.table(T_MASTERY).select("concept_id")
        .eq("user_id", user_id).execute()
    ).data
    existing_ids = {e["concept_id"] for e in existing}

    new_records = [
        {"user_id": user_id, "concept_id": c["id"]}
        for c in concepts
        if c["id"] not in existing_ids
    ]
    if new_records:
        sb.table(T_MASTERY).insert(new_records).execute()

    return len(new_records)


def record_concept_exposure(user_id: str, concept_id: str, correct: bool) -> dict:
    """記錄一次概念接觸（練習/對話）"""
    sb = get_supabase()
    record = (
        sb.table(T_MASTERY).select("*")
        .eq("user_id", user_id).eq("concept_id", concept_id)
        .execute()
    ).data

    if not record:
        # Auto-create
        record = sb.table(T_MASTERY).insert({
            "user_id": user_id, "concept_id": concept_id,
        }).execute().data

    r = record[0]
    exposure = r.get("exposure_count", 0) + 1
    correct_n = r.get("correct_count", 0) + (1 if correct else 0)
    mastery = correct_n / max(exposure, 1)

    updated = sb.table(T_MASTERY).update({
        "exposure_count": exposure,
        "correct_count": correct_n,
        "mastery_level": round(mastery, 3),
        "last_reviewed_at": "now()",
        "updated_at": "now()",
    }).eq("id", r["id"]).execute()

    return updated.data[0] if updated.data else r
