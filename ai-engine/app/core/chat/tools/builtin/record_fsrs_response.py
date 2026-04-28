"""
Tool: record_fsrs_response
Description: 紀錄 FSRS 評分(Again/Hard/Good/Easy)。Phase 1 stub。
"""
from typing import Any

TOOL_NAME = "record_fsrs_response"

TOOL_DESCRIPTION = (
    "Record a user's FSRS response (Again/Hard/Good/Easy) for a concept. "
    "STUB IN PHASE 1 — accepts inputs but does not yet write to the FSRS schedule."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "concept_id": {"type": "string", "description": "Concept the user just reviewed."},
        "rating": {
            "type": "string",
            "enum": ["again", "hard", "good", "easy"],
            "description": "FSRS rating.",
        },
        "duration_seconds": {
            "type": "number",
            "description": "Time spent on the review.",
        },
    },
    "required": ["concept_id", "rating"],
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
        "recorded": False,
        "concept_id": params.get("concept_id"),
        "rating": params.get("rating"),
        "note": "stub — FSRS write integration lands with full FSRS scheduler",
    }
