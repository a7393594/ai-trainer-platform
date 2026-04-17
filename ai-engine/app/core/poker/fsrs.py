"""
FSRS-4.5 Spaced Repetition Scheduler — 撲克概念複習排程

FSRS (Free Spaced Repetition Scheduler) 是 Anki 2026 預設演算法。
比 SM-2 省 20-30% 複習次數。

核心三元組：(D 難度, S 穩定度, R 可擷取性)
Grade: Again(1) / Hard(2) / Good(3) / Easy(4)
"""
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

# FSRS-4.5 參數（從 open-spaced-repetition 預訓練）
W = [0.4, 0.6, 2.4, 5.8, 4.93, 0.94, 0.86, 0.01, 1.49, 0.14, 0.94, 2.18, 0.05, 0.34, 1.26, 0.29, 2.61]


def init_state() -> dict:
    """初始化 FSRS state for a new concept."""
    return {
        "stability": 0.0,
        "difficulty": 0.0,
        "elapsed_days": 0,
        "scheduled_days": 0,
        "reps": 0,
        "lapses": 0,
        "last_review": None,
    }


def schedule_review(state: dict, grade: int) -> dict:
    """Calculate next review time based on grade.

    Args:
        state: current FSRS state dict
        grade: 1=Again, 2=Hard, 3=Good, 4=Easy

    Returns:
        Updated state with next_review_at
    """
    grade = max(1, min(4, grade))
    now = datetime.now(timezone.utc)

    reps = state.get("reps", 0)
    lapses = state.get("lapses", 0)
    old_s = state.get("stability", 0.0)
    old_d = state.get("difficulty", 0.0)

    if reps == 0:
        # First review — initial stability based on grade
        new_s = _initial_stability(grade)
        new_d = _initial_difficulty(grade)
        interval = _next_interval(new_s, 0.9)
    else:
        # Subsequent reviews
        elapsed = state.get("elapsed_days", 1) or 1
        retrievability = _retrievability(elapsed, old_s)

        if grade == 1:
            # Again — lapse
            new_d = min(10, _mean_reversion(old_d, 8.0))
            new_s = max(0.1, old_s * 0.5)  # Stability drops
            lapses += 1
            interval = 1  # Review tomorrow
        else:
            new_d = _next_difficulty(old_d, grade)
            new_s = _next_stability(old_s, new_d, retrievability, grade)
            interval = _next_interval(new_s, 0.9)

    # Apply interval
    next_review = now + timedelta(days=max(1, int(interval)))

    return {
        "stability": round(new_s, 3),
        "difficulty": round(new_d, 3),
        "elapsed_days": 0,  # Reset — will be computed at next review
        "scheduled_days": max(1, int(interval)),
        "reps": reps + 1,
        "lapses": lapses,
        "last_review": now.isoformat(),
        "next_review_at": next_review.isoformat(),
    }


def get_due_concepts(mastery_records: list[dict]) -> list[dict]:
    """Filter concepts that are due for review."""
    now = datetime.now(timezone.utc)
    due = []
    for m in mastery_records:
        next_review_str = m.get("next_review_at") or (m.get("fsrs_state") or {}).get("next_review_at")
        if not next_review_str:
            # Never reviewed — always due
            due.append(m)
            continue
        try:
            next_dt = datetime.fromisoformat(next_review_str.replace("Z", "+00:00"))
            if next_dt <= now:
                due.append(m)
        except Exception:
            due.append(m)
    return due


# ═══ FSRS Internal Functions ═══

def _initial_stability(grade: int) -> float:
    return W[grade - 1]

def _initial_difficulty(grade: int) -> float:
    return max(1, min(10, W[4] - (grade - 3) * W[5]))

def _next_difficulty(d: float, grade: int) -> float:
    new_d = d - W[6] * (grade - 3)
    return max(1, min(10, _mean_reversion(new_d, W[4])))

def _mean_reversion(current: float, init: float) -> float:
    return W[7] * init + (1 - W[7]) * current

def _next_stability(s: float, d: float, r: float, grade: int) -> float:
    """Compute new stability after a successful review."""
    hard_penalty = W[15] if grade == 2 else 1
    easy_bonus = W[16] if grade == 4 else 1
    new_s = s * (1 + math.exp(W[8]) * (11 - d) * s ** (-W[9]) * (math.exp(W[10] * (1 - r)) - 1) * hard_penalty * easy_bonus)
    return max(0.1, new_s)

def _retrievability(elapsed_days: float, stability: float) -> float:
    if stability <= 0:
        return 0.0
    return (1 + elapsed_days / (9 * stability)) ** -1

def _next_interval(stability: float, desired_retention: float = 0.9) -> float:
    """Calculate days until desired retention drops to target."""
    if stability <= 0:
        return 1
    return max(1, stability * 9 * (1 / desired_retention - 1))
