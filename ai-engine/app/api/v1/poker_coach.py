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
