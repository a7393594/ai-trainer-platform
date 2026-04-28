"""
Tool: start_practice_session
Description: 對戰練習 session 初始化(Phase 5)。Phase 1 stub。
"""
import uuid
from typing import Any

TOOL_NAME = "start_practice_session"

TOOL_DESCRIPTION = (
    "Start an opponent-practice session. "
    "STUB IN PHASE 1 — returns a generated session id. Real implementation in Phase 5."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "spot_descriptor": {
            "type": "object",
            "description": "Spot definition: stacks, blinds, hero position, opp profile, etc.",
        },
        "opponent_profile_id": {
            "type": "string",
            "description": "Optional reference to ait_opponent_profiles row.",
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
    practice_id = f"practice-{uuid.uuid4()}"
    return {
        "started": False,
        "practice_session_id": practice_id,
        "note": "stub — practice-session initialiser will be implemented in Phase 5",
        "params": params,
    }
