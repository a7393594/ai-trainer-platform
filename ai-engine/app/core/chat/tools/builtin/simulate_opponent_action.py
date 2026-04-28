"""
Tool: simulate_opponent_action
Description: 對手 LLM 角色扮演(Phase 5)。Phase 1 stub。
"""
from typing import Any

TOOL_NAME = "simulate_opponent_action"

TOOL_DESCRIPTION = (
    "Have an LLM-controlled opponent decide its next action given the current spot. "
    "STUB IN PHASE 1 — returns a placeholder check action. Real implementation in Phase 5."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "practice_session_id": {"type": "string"},
        "spot_state": {
            "type": "object",
            "description": "Current state: pot, board, hero_action, stacks, etc.",
        },
        "opponent_profile": {
            "type": "object",
            "description": "Opponent style/range info.",
        },
    },
    "required": ["spot_state"],
}


async def execute(
    params: dict,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    return {
        "action": "check",
        "amount": 0,
        "rationale": "stub — opponent simulation lands in Phase 5",
        "note": "stub",
    }
