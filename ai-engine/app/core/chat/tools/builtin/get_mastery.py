"""
Tool: get_mastery
Description: 取使用者概念掌握度(ait_user_concept_mastery)。
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

TOOL_NAME = "get_mastery"

TOOL_DESCRIPTION = (
    "Return user's concept-mastery levels (ait_user_concept_mastery). "
    "No params — uses execution-context user_id and project_id."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
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
    if not user_id or not project_id:
        return {"mastery": [], "note": "user_id / project_id missing in execution context"}

    try:
        from app.db import crud_poker
    except Exception as e:  # pragma: no cover
        return {"mastery": [], "error": f"crud_poker import failed: {e}"}

    try:
        rows = crud_poker.get_user_mastery(user_id=user_id, project_id=project_id)
    except Exception as e:
        logger.warning("get_mastery DB read failed: %s", e)
        return {"mastery": [], "error": f"DB read failed: {e}"}

    return {"mastery": rows or [], "count": len(rows or [])}
