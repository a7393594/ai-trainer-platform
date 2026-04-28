"""
Tool: opponent_modeling
Description: 從 ait_opponent_profiles 讀取對手模型。Phase 1 stub — best-effort 直接讀 supabase。
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

TOOL_NAME = "opponent_modeling"

TOOL_DESCRIPTION = (
    "Look up an opponent profile (style, ranges, leaks) from ait_opponent_profiles. "
    "STUB IN PHASE 1 — best-effort table read; falls back to empty if the table is unavailable."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "opponent_id": {"type": "string", "description": "Opponent profile id (uuid) or alias."},
        "filter": {
            "type": "object",
            "description": "Optional column filter, e.g. {'style': 'lag'}.",
        },
    },
    "required": [],
}


async def execute(
    params: dict,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    opp_id = params.get("opponent_id")
    filt = params.get("filter") or {}

    try:
        from app.db.supabase import get_supabase
        sb = get_supabase()
        q = sb.table("ait_opponent_profiles").select("*")
        if user_id:
            q = q.eq("user_id", user_id)
        if project_id:
            q = q.eq("project_id", project_id)
        if opp_id:
            q = q.eq("id", opp_id)
        if isinstance(filt, dict):
            for k, v in filt.items():
                q = q.eq(k, v)
        result = q.limit(20).execute()
        return {"profiles": result.data or [], "count": len(result.data or [])}
    except Exception as e:
        logger.warning("opponent_modeling read failed: %s", e)
        return {
            "profiles": [],
            "note": f"stub — table read failed: {e}",
        }
