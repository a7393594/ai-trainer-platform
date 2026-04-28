"""
Tool: compose_learning_plan
Description: 把 stats / mastery / due_reviews 組成結構化學習計畫(70/20/10 weighting)。純函數工具。
"""
from typing import Any

TOOL_NAME = "compose_learning_plan"

TOOL_DESCRIPTION = (
    "Compose a structured learning plan from stats, mastery, and due_reviews. "
    "Splits time_budget_minutes by weight string 'A-B-C' (default 70-20-10) "
    "across weakness drills / new concepts / FSRS reviews."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "scope": {
            "type": "string",
            "enum": ["recent", "month", "all"],
            "description": "Stat scope used to build plan.",
        },
        "time_budget_minutes": {
            "type": "integer",
            "description": "Total minutes available.",
        },
        "weight": {
            "type": "string",
            "description": "Weight ratio 'A-B-C' for weakness/new/FSRS (default '70-20-10').",
            "default": "70-20-10",
        },
        "stats": {"type": "object", "description": "Stats payload (typically from get_user_stats)."},
        "mastery": {"type": "object", "description": "Mastery payload (from get_mastery)."},
        "due_reviews": {"type": "array", "description": "Due-review items (from get_due_reviews)."},
    },
    "required": ["scope", "time_budget_minutes"],
}


def _parse_weight(w: str) -> tuple[float, float, float]:
    try:
        parts = [float(x) for x in str(w).split("-")]
        if len(parts) != 3:
            raise ValueError
        s = sum(parts)
        if s <= 0:
            raise ValueError
        return parts[0] / s, parts[1] / s, parts[2] / s
    except Exception:
        return 0.7, 0.2, 0.1


def _weakness_items(stats: Any) -> list[dict]:
    """Extract worst-performing positions/spots from stats payload."""
    items: list[dict] = []
    if isinstance(stats, dict):
        rows = stats.get("stats") if "stats" in stats else None
        if rows is None and "data" in stats:
            rows = stats["data"]
        if rows is None:
            rows = []
    elif isinstance(stats, list):
        rows = stats
    else:
        rows = []
    if not isinstance(rows, list):
        rows = []

    # Build a candidate list with a heuristic "weakness score" based on common columns.
    candidates: list[tuple[float, dict]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        # Lower winrate / vpip + bad bb/100 => higher weakness score.
        bb100 = row.get("bb_100") or row.get("winrate_bb100") or 0
        try:
            bb100 = float(bb100)
        except Exception:
            bb100 = 0
        score = -bb100
        candidates.append((score, row))

    candidates.sort(key=lambda x: -x[0])
    for _, row in candidates[:10]:
        label = row.get("position") or row.get("spot") or row.get("category") or "weak spot"
        items.append({
            "title": f"Drill: {label}",
            "category": "weakness_drill",
            "source": row,
        })
    return items


def _new_concept_items(mastery: Any) -> list[dict]:
    """Pick concepts with low mastery levels for fresh study."""
    items: list[dict] = []
    if isinstance(mastery, dict):
        rows = mastery.get("mastery") if "mastery" in mastery else mastery.get("data", [])
    elif isinstance(mastery, list):
        rows = mastery
    else:
        rows = []
    if not isinstance(rows, list):
        rows = []

    sorted_rows = sorted(
        (r for r in rows if isinstance(r, dict)),
        key=lambda r: float(r.get("level", r.get("mastery_level", 0)) or 0),
    )
    for r in sorted_rows[:10]:
        cid = r.get("concept_id") or r.get("concept_code") or "unknown"
        items.append({
            "title": f"Study new concept: {cid}",
            "category": "new_concept",
            "source": r,
        })
    return items


def _fsrs_items(due_reviews: Any) -> list[dict]:
    items: list[dict] = []
    rows = due_reviews
    if isinstance(rows, dict):
        rows = rows.get("due_reviews", [])
    if not isinstance(rows, list):
        rows = []
    for r in rows[:20]:
        cid = r.get("concept_id") if isinstance(r, dict) else str(r)
        items.append({
            "title": f"FSRS review: {cid}",
            "category": "fsrs_review",
            "source": r if isinstance(r, dict) else {"concept_id": cid},
        })
    return items


def _slot_minutes(items: list[dict], minutes: float) -> list[dict]:
    """Distribute `minutes` across `items`. Round to int and trim trailing zero items."""
    if not items or minutes <= 0:
        return []
    per = max(1, int(minutes // max(1, len(items))))
    out = []
    used = 0
    for it in items:
        if used >= minutes:
            break
        m = min(per, max(1, int(minutes - used)))
        out.append({**it, "estimated_minutes": m})
        used += m
    return out


async def execute(
    params: dict,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    scope = params.get("scope", "recent")
    budget = int(params.get("time_budget_minutes", 30))
    weights = _parse_weight(params.get("weight", "70-20-10"))
    stats = params.get("stats")
    mastery = params.get("mastery")
    due_reviews = params.get("due_reviews")

    weak_min = budget * weights[0]
    new_min = budget * weights[1]
    fsrs_min = budget * weights[2]

    weak = _slot_minutes(_weakness_items(stats), weak_min)
    new = _slot_minutes(_new_concept_items(mastery), new_min)
    fsrs = _slot_minutes(_fsrs_items(due_reviews), fsrs_min)

    items = weak + new + fsrs
    total = sum(it.get("estimated_minutes", 0) for it in items)

    return {
        "plan": {
            "scope": scope,
            "weight_ratio": list(weights),
            "items": items,
            "total_minutes": total,
            "budget_minutes": budget,
        }
    }
