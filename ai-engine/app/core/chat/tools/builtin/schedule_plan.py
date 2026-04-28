"""
Tool: schedule_plan
Description: 把 plan 寫進 ait_learning_plans 表。Phase 1 stub — 直寫 supabase 試試,失敗則 fallback。
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

TOOL_NAME = "schedule_plan"

TOOL_DESCRIPTION = (
    "Persist a learning plan (typically from compose_learning_plan) into ait_learning_plans. "
    "Returns the created plan_id. Phase 1: best-effort — falls back to a stub id if the table "
    "does not yet exist or the write fails."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "plan": {
            "type": "object",
            "description": "Plan dict, typically from compose_learning_plan.",
        }
    },
    "required": ["plan"],
}


async def execute(
    params: dict,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    plan = params.get("plan") or {}
    if not isinstance(plan, dict):
        return {"scheduled": False, "error": "plan must be a dict"}

    try:
        from app.db.supabase import get_supabase
        sb = get_supabase()
        row = {
            "user_id": user_id,
            "project_id": project_id,
            "session_id": session_id,
            "plan": plan,
            "scope": plan.get("scope"),
            "total_minutes": plan.get("total_minutes"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        result = sb.table("ait_learning_plans").insert(row).execute()
        record = (result.data or [None])[0]
        plan_id = (record or {}).get("id") or (record or {}).get("plan_id")
        return {
            "scheduled": True,
            "plan_id": plan_id or "unknown",
            "row": record,
        }
    except Exception as e:
        logger.warning("schedule_plan DB write failed (likely table missing): %s", e)
        # TODO: replace with real crud helper once ait_learning_plans schema is finalised.
        return {
            "scheduled": False,
            "plan_id": f"stub-{uuid.uuid4()}",
            "note": f"insert failed: {e}",
        }
