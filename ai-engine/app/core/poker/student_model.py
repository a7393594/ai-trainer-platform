"""
Student Model Manager — 學生模型管理

負責等級偵測、profile 更新、onboarding 結果處理
"""
from typing import Optional
from app.db import crud_poker


# ═══ Level Detection from Onboarding ═══

LEVEL_MAP = {
    # self-assessment score (1-10) → initial level
    (1, 2): "L0",
    (3, 4): "L1",
    (5, 6): "L2",
    (7, 8): "L3",
    (9, 9): "L4",
    (10, 10): "L5",
}


def detect_level_from_onboarding(answers: dict) -> tuple[str, float]:
    """從 onboarding 答案推斷初始等級。

    Returns: (level, confidence)
    """
    # Primary signal: self-assessed skill level (q9, 1-10 scale)
    skill_score = answers.get("q9_skill_level", 3)
    if isinstance(skill_score, str):
        try:
            skill_score = int(skill_score)
        except ValueError:
            skill_score = 3

    # Map to level
    level = "L1"
    for (lo, hi), lv in LEVEL_MAP.items():
        if lo <= skill_score <= hi:
            level = lv
            break

    # Confidence based on supporting evidence
    confidence = 0.4  # base confidence from self-assessment alone

    # Boost if they mentioned specific topics (q10)
    leaks = answers.get("q10_leaks", [])
    if isinstance(leaks, list) and len(leaks) >= 3:
        confidence += 0.1  # knows enough to identify leaks

    # Boost if they play significant volume (q12)
    volume = answers.get("q12_monthly_hands", "")
    if volume in ("5000-10000", "10000+"):
        confidence += 0.1

    return level, min(confidence, 0.9)


# ═══ Profile Management ═══

def initialize_from_onboarding(
    user_id: str,
    project_id: str,
    answers: dict,
) -> dict:
    """Onboarding 完成後初始化 student profile。"""
    profile = crud_poker.get_or_create_student_profile(user_id, project_id)

    level, confidence = detect_level_from_onboarding(answers)

    # Determine scaffolding stage from level
    stage_map = {"L0": "modeling", "L1": "modeling", "L2": "guided",
                 "L3": "prompting", "L4": "sparring", "L5": "sparring"}
    stage = stage_map.get(level, "modeling")

    # Extract structured data from answers
    game_types = answers.get("q1_game_types", [])
    if isinstance(game_types, str):
        game_types = [game_types]

    weaknesses = answers.get("q10_leaks", [])
    if isinstance(weaknesses, str):
        weaknesses = [weaknesses]

    updates = {
        "level": level,
        "level_confidence": confidence,
        "scaffolding_stage": stage,
        "game_types": game_types,
        "weaknesses": weaknesses,
        "onboarding_answers": answers,
    }

    crud_poker.update_student_profile(profile["id"], updates)

    # Initialize concept mastery records
    crud_poker.init_mastery_for_user(user_id, project_id)

    return {**profile, **updates}


def get_profile_for_prompt(user_id: str, project_id: str) -> Optional[dict]:
    """取得用於 prompt 注入的 profile 摘要。"""
    profile = crud_poker.get_student_profile(user_id, project_id)
    if not profile:
        return None

    mastery = crud_poker.get_user_mastery(user_id, project_id)

    return {
        "profile": profile,
        "mastery_summary": [
            {
                "concept_name": m.get("concept_name", ""),
                "category": m.get("category", ""),
                "mastery_level": m.get("mastery_level", 0),
            }
            for m in mastery
        ],
    }
