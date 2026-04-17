"""
Learning Plan Generator — 學習計畫產生器

分配策略（借鑑 Duolingo Birdbrain）：
- 70% 弱點（EV loss 前 5 概念）
- 20% 新概念（難度略超當前，ZPD 實作）
- 10% 衰退中的強項（FSRS due）
"""
from datetime import datetime, timezone
from app.db import crud_poker
from app.core.poker.fsrs import get_due_concepts


def generate_plan(user_id: str, project_id: str) -> dict:
    """Generate a learning plan for the student.

    Returns:
        {
            "items": [
                {"concept_code": str, "concept_name": str, "priority": int,
                 "type": "weakness" | "new" | "review", "reason": str}
            ],
            "total_estimated_minutes": int,
            "generated_at": str,
        }
    """
    profile = crud_poker.get_student_profile(user_id, project_id)
    if not profile:
        return {"items": [], "message": "No profile found"}

    mastery = crud_poker.get_user_mastery(user_id, project_id)
    concepts = crud_poker.list_concepts(project_id)

    level = profile.get("level", "L1")
    level_num = int(level[1]) if len(level) == 2 else 1

    items = []

    # ═══ 70% Weaknesses ═══
    # Sort by lowest mastery + highest exposure (tried but still bad)
    weak = [
        m for m in mastery
        if m.get("mastery_level", 0) < 0.5 and m.get("exposure_count", 0) > 0
    ]
    weak.sort(key=lambda m: (m.get("mastery_level", 0), -m.get("exposure_count", 0)))

    for m in weak[:5]:
        items.append({
            "concept_code": m.get("concept_code", ""),
            "concept_name": m.get("concept_name", ""),
            "priority": 1,
            "type": "weakness",
            "mastery": m.get("mastery_level", 0),
            "reason": f"掌握度 {m.get('mastery_level', 0):.0%}，需加強",
        })

    # ═══ 20% New Concepts ═══
    # Find concepts not yet exposed, at appropriate difficulty
    concept_map = {c["code"]: c for c in concepts}
    exposed_codes = {m.get("concept_code") for m in mastery if m.get("exposure_count", 0) > 0}
    mastered_codes = {m.get("concept_code") for m in mastery if m.get("mastery_level", 0) >= 0.7}

    new_candidates = []
    for c in concepts:
        if c["code"] in exposed_codes:
            continue
        # Check prerequisites met
        prereqs = c.get("prerequisite_codes", [])
        prereqs_met = all(p in mastered_codes for p in prereqs) if prereqs else True
        if not prereqs_met:
            continue
        # Difficulty should be appropriate for level
        if c.get("difficulty", 1) <= level_num + 2:
            new_candidates.append(c)

    new_candidates.sort(key=lambda c: c.get("difficulty", 1))
    for c in new_candidates[:2]:
        items.append({
            "concept_code": c["code"],
            "concept_name": c["name"],
            "priority": 2,
            "type": "new",
            "difficulty": c.get("difficulty", 1),
            "reason": f"新概念（難度 {c.get('difficulty', 1)}/5）",
        })

    # ═══ 10% FSRS Review ═══
    due = get_due_concepts(mastery)
    # Only include concepts that were previously mastered but fading
    fading = [
        m for m in due
        if m.get("mastery_level", 0) >= 0.5 and m.get("concept_code") not in {i["concept_code"] for i in items}
    ]
    for m in fading[:2]:
        items.append({
            "concept_code": m.get("concept_code", ""),
            "concept_name": m.get("concept_name", ""),
            "priority": 3,
            "type": "review",
            "mastery": m.get("mastery_level", 0),
            "reason": "FSRS 排程到期，需複習",
        })

    # Estimate time: 5 min per weakness, 8 min per new, 3 min per review
    time_map = {"weakness": 5, "new": 8, "review": 3}
    total_minutes = sum(time_map.get(i["type"], 5) for i in items)

    return {
        "items": items,
        "total_estimated_minutes": total_minutes,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "stats": {
            "total_concepts": len(concepts),
            "exposed": len(exposed_codes),
            "mastered": len(mastered_codes),
            "due_review": len(due),
        },
    }
