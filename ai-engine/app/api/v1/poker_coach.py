"""
Poker Coach API — 教練系統端點
Prefix: /poker
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.db import crud_poker
from app.core.poker.concept_seed import seed_concepts
from app.core.poker.student_model import (
    initialize_from_onboarding,
    get_profile_for_prompt,
)

router = APIRouter(prefix="/poker", tags=["poker-coach"])


# ============================================
# Student Profile
# ============================================

@router.get("/profile")
async def get_profile(user_id: str = Query(...), project_id: str = Query(...)):
    """取得學生 profile（含概念掌握度摘要）"""
    data = get_profile_for_prompt(user_id, project_id)
    if not data:
        return {"profile": None, "mastery_summary": []}
    return data


@router.post("/profile/init-from-onboarding")
async def init_from_onboarding(data: dict):
    """Onboarding 完成後初始化 profile"""
    user_id = data.get("user_id")
    project_id = data.get("project_id")
    answers = data.get("answers", {})
    if not user_id or not project_id:
        raise HTTPException(400, "user_id and project_id required")

    profile = initialize_from_onboarding(user_id, project_id, answers)
    return {"status": "initialized", "profile": profile}


@router.post("/profile/update-scaffolding")
async def update_scaffolding(data: dict):
    """手動更新 scaffolding stage"""
    profile_id = data.get("profile_id")
    stage = data.get("scaffolding_stage")
    if not profile_id or not stage:
        raise HTTPException(400, "profile_id and scaffolding_stage required")

    result = crud_poker.update_student_profile(profile_id, {"scaffolding_stage": stage})
    return {"status": "updated", "profile": result}


# ============================================
# Concepts & Mastery
# ============================================

@router.get("/concepts")
async def list_concepts(project_id: str = Query(...)):
    """列出專案所有概念（30 KC）"""
    concepts = crud_poker.list_concepts(project_id)
    return {"concepts": concepts, "count": len(concepts)}


@router.get("/mastery")
async def get_mastery(user_id: str = Query(...), project_id: str = Query(...)):
    """取得學生所有概念掌握度"""
    mastery = crud_poker.get_user_mastery(user_id, project_id)
    return {"mastery": mastery, "count": len(mastery)}


@router.post("/mastery/record")
async def record_exposure(data: dict):
    """記錄一次概念接觸"""
    user_id = data.get("user_id")
    concept_id = data.get("concept_id")
    correct = data.get("correct", False)
    if not user_id or not concept_id:
        raise HTTPException(400, "user_id and concept_id required")

    result = crud_poker.record_concept_exposure(user_id, concept_id, correct)
    return {"status": "recorded", "mastery": result}


@router.post("/mastery/init")
async def init_mastery(data: dict):
    """為使用者初始化所有概念 mastery records"""
    user_id = data.get("user_id")
    project_id = data.get("project_id")
    if not user_id or not project_id:
        raise HTTPException(400, "user_id and project_id required")

    count = crud_poker.init_mastery_for_user(user_id, project_id)
    return {"status": "initialized", "new_records": count}


# ============================================
# Admin: Seed Concepts
# ============================================

@router.post("/admin/seed-concepts")
async def seed_concepts_endpoint(project_id: str = Query(...)):
    """Seed 30 KC 到指定專案"""
    count = seed_concepts(project_id)
    return {"status": "seeded", "count": count}


# ============================================
# Hand History Upload & Management
# ============================================

@router.post("/upload/hh")
async def upload_hand_history(data: dict):
    """上傳手牌歷史（純文字）→ 解析 → 存入 DB → 計算統計"""
    from app.core.poker.hh_parser import detect_and_parse
    from app.core.poker.stats_engine import compute_stats
    from datetime import datetime, timezone

    user_id = data.get("user_id")
    project_id = data.get("project_id")
    raw_text = data.get("raw_text", "")
    filename = data.get("filename", "upload.txt")

    if not user_id or not project_id or not raw_text.strip():
        raise HTTPException(400, "user_id, project_id, raw_text required")

    # Create upload batch
    batch = crud_poker.create_upload_batch(user_id, project_id, filename)
    batch_id = batch["id"]

    # Parse
    try:
        hands = detect_and_parse(raw_text)
    except Exception as e:
        crud_poker.update_upload_batch(batch_id, {
            "status": "error",
            "error_log": [{"error": str(e)}],
        })
        raise HTTPException(400, f"Parse failed: {e}")

    # Insert hands
    rows = [h.to_db_row(user_id, project_id, batch_id) for h in hands]
    inserted = crud_poker.bulk_insert_hands(rows)
    failed = len(hands) - inserted

    # Update batch
    crud_poker.update_upload_batch(batch_id, {
        "status": "completed",
        "total_hands": len(hands),
        "parsed_hands": inserted,
        "failed_hands": failed,
    })

    # Compute fresh stats snapshot
    all_hands_data = [h.to_dict() for h in hands]
    stats = compute_stats(all_hands_data)

    if stats.get("sample_size", 0) > 0:
        crud_poker.create_stats_snapshot({
            "user_id": user_id,
            "project_id": project_id,
            "period_start": datetime.now(timezone.utc).isoformat(),
            "period_end": datetime.now(timezone.utc).isoformat(),
            "sample_size": stats["sample_size"],
            "stats": stats,
            "stats_by_position": stats.get("by_position", {}),
            "game_type": hands[0].game_type if hands else "nlh",
        })

    return {
        "status": "completed",
        "batch_id": batch_id,
        "total_hands": len(hands),
        "inserted": inserted,
        "failed": failed,
        "stats_preview": {
            k: stats.get(k) for k in ["sample_size", "vpip", "pfr", "three_bet", "bb_per_100"]
        },
    }


@router.get("/hands")
async def list_hands(
    user_id: str = Query(...),
    project_id: str = Query(...),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """列出已解析的手牌"""
    hands = crud_poker.list_hand_histories(user_id, project_id, limit, offset)
    total = crud_poker.count_hands(user_id, project_id)
    return {"hands": hands, "total": total}


@router.get("/hands/{hand_id}")
async def get_hand(hand_id: str):
    """取得單手完整資料（含 parsed_json）"""
    hand = crud_poker.get_hand_history(hand_id)
    if not hand:
        raise HTTPException(404, "Hand not found")
    return hand


@router.get("/stats")
async def get_stats(user_id: str = Query(...), project_id: str = Query(...)):
    """取得最新統計快照"""
    latest = crud_poker.get_latest_stats(user_id, project_id)
    if not latest:
        return {"stats": None, "message": "No stats yet. Upload hand histories first."}
    return {
        "stats": latest.get("stats", {}),
        "by_position": latest.get("stats_by_position", {}),
        "sample_size": latest.get("sample_size", 0),
        "period_start": latest.get("period_start"),
        "created_at": latest.get("created_at"),
    }


@router.get("/stats/history")
async def get_stats_history(
    user_id: str = Query(...),
    project_id: str = Query(...),
    limit: int = Query(20, ge=1, le=100),
):
    """取得統計快照歷史（用於趨勢圖）"""
    snapshots = crud_poker.list_stats_snapshots(user_id, project_id, limit)
    return {"snapshots": snapshots}


@router.get("/uploads")
async def list_uploads(user_id: str = Query(...), project_id: str = Query(...)):
    """列出上傳批次"""
    batches = crud_poker.list_upload_batches(user_id, project_id)
    return {"batches": batches}


# ============================================
# Deep Review
# ============================================

@router.post("/review/start")
async def start_review(data: dict):
    """啟動深度複盤分析"""
    from app.core.poker.review.pipeline import run_review

    user_id = data.get("user_id")
    project_id = data.get("project_id")
    hand_ids = data.get("hand_ids")
    batch_id = data.get("batch_id")

    if not user_id or not project_id:
        raise HTTPException(400, "user_id and project_id required")

    result = await run_review(user_id, project_id, hand_ids=hand_ids, batch_id=batch_id)
    return result


@router.get("/review/list")
async def list_reviews(user_id: str = Query(...), project_id: str = Query(...)):
    """列出所有複盤報告"""
    from app.db.supabase import get_supabase
    reports = (
        get_supabase().table("ait_review_reports")
        .select("id, hand_count, analyzed_count, status, summary, overall_ev_loss_mbb, top_weaknesses, created_at")
        .eq("user_id", user_id).eq("project_id", project_id)
        .order("created_at", desc=True).limit(20)
        .execute()
    ).data
    return {"reports": reports}


@router.get("/review/{report_id}")
async def get_review(report_id: str):
    """取得完整複盤報告"""
    from app.db.supabase import get_supabase
    report = (
        get_supabase().table("ait_review_reports")
        .select("*").eq("id", report_id).execute()
    )
    if not report.data:
        raise HTTPException(404, "Report not found")

    # Also load analyses for this report
    analyses = (
        get_supabase().table("ait_hand_analyses")
        .select("*").eq("review_report_id", report_id)
        .order("ev_loss_mbb", desc=True)
        .execute()
    ).data

    return {"report": report.data[0], "analyses": analyses}


# ============================================
# Learning Plan & FSRS
# ============================================

@router.get("/learning-plan")
async def get_learning_plan(user_id: str = Query(...), project_id: str = Query(...)):
    """取得學生的學習計畫"""
    from app.core.poker.learning_plan import generate_plan
    plan = generate_plan(user_id, project_id)
    return plan


@router.post("/mastery/review")
async def record_review(data: dict):
    """記錄一次概念複習結果（觸發 FSRS 排程更新）"""
    from app.core.poker.fsrs import schedule_review
    user_id = data.get("user_id")
    concept_id = data.get("concept_id")
    grade = data.get("grade", 3)  # 1=Again, 2=Hard, 3=Good, 4=Easy

    if not user_id or not concept_id:
        raise HTTPException(400, "user_id and concept_id required")

    # Record exposure
    correct = grade >= 3
    crud_poker.record_concept_exposure(user_id, concept_id, correct)

    # Get current FSRS state
    from app.db.supabase import get_supabase
    record = get_supabase().table("ait_user_concept_mastery").select("*").eq(
        "user_id", user_id
    ).eq("concept_id", concept_id).execute()

    if record.data:
        old_state = record.data[0].get("fsrs_state", {}) or {}
        new_state = schedule_review(old_state, grade)
        get_supabase().table("ait_user_concept_mastery").update({
            "fsrs_state": new_state,
            "next_review_at": new_state.get("next_review_at"),
            "updated_at": "now()",
        }).eq("id", record.data[0]["id"]).execute()
        return {"status": "updated", "fsrs_state": new_state}

    return {"status": "not_found"}


@router.get("/due-reviews")
async def get_due_reviews(user_id: str = Query(...), project_id: str = Query(...)):
    """取得到期待複習的概念"""
    from app.core.poker.fsrs import get_due_concepts
    mastery = crud_poker.get_user_mastery(user_id, project_id)
    due = get_due_concepts(mastery)
    return {"due": due, "count": len(due)}


@router.get("/review/{report_id}/hands")
async def get_review_hands(report_id: str):
    """取得複盤報告的手牌分析清單"""
    from app.db.supabase import get_supabase
    analyses = (
        get_supabase().table("ait_hand_analyses")
        .select("*, ait_hand_histories(hand_id, hero_cards, board, hero_position, hero_net_bb)")
        .eq("review_report_id", report_id)
        .order("ev_loss_mbb", desc=True)
        .execute()
    ).data
    return {"analyses": analyses}
