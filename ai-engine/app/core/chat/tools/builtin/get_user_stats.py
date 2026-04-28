"""
Tool: get_user_stats
Description: 從 ait_stats_snapshots 讀使用者撲克數據。
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

TOOL_NAME = "get_user_stats"

TOOL_DESCRIPTION = (
    "Fetch user's poker stats from ait_stats_snapshots. "
    "scope: 'recent' (latest snapshot), 'month' (30d), or 'all'. "
    "filter is an optional dict of additional column filters, e.g. {'position': 'BB'}."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "scope": {
            "type": "string",
            "enum": ["recent", "month", "all"],
            "description": "Time scope. 'recent'=latest snapshot, 'month'=30d, 'all'=full history.",
        },
        "filter": {
            "type": "object",
            "description": "Optional column filters, e.g. {'position': 'BB'}.",
        },
    },
    "required": ["scope"],
}


async def execute(
    params: dict,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    if not user_id or not project_id:
        return {"stats": [], "note": "user_id / project_id missing in execution context"}

    scope = params.get("scope", "recent")
    filt = params.get("filter") or {}

    try:
        from app.db import crud_poker
    except Exception as e:  # pragma: no cover
        return {"stats": [], "error": f"crud_poker import failed: {e}"}

    try:
        if scope == "recent":
            latest = crud_poker.get_latest_stats(user_id=user_id, project_id=project_id)
            rows = [latest] if latest else []
        elif scope == "month":
            # crud_poker only exposes list_stats_snapshots(limit=N). Approximate 30d
            # by limit=30 most-recent rows; downstream can re-filter by created_at.
            rows = crud_poker.list_stats_snapshots(
                user_id=user_id, project_id=project_id, limit=30
            )
        else:
            rows = crud_poker.list_stats_snapshots(
                user_id=user_id, project_id=project_id, limit=200
            )
    except Exception as e:
        logger.warning("get_user_stats DB read failed: %s", e)
        return {"stats": [], "error": f"DB read failed: {e}"}

    # apply filter if any
    if filt and isinstance(filt, dict):
        filtered = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            ok = all(row.get(k) == v for k, v in filt.items())
            if ok:
                filtered.append(row)
        rows = filtered

    return {"stats": rows, "scope": scope, "count": len(rows)}
