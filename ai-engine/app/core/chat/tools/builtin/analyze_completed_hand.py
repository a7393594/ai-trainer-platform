"""
Tool: analyze_completed_hand
Description: 對戰結束後分析(Phase 5)。Phase 1 stub。
"""
from typing import Any

TOOL_NAME = "analyze_completed_hand"

TOOL_DESCRIPTION = (
    "Analyse a completed hand history — pinpoint mistakes, suggest alternative lines, score by EV. "
    "STUB IN PHASE 1 — returns a placeholder analysis. Real implementation in Phase 5."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "hand_record": {
            "type": "object",
            "description": "Hand record (typically from analyze_screenshot or hand_recorder).",
        },
        "focus": {
            "type": "string",
            "description": "Optional analysis angle, e.g. 'preflop' or 'river-decision'.",
        },
    },
    "required": ["hand_record"],
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
        "analysis": {
            "verdict": "neutral",
            "mistakes": [],
            "alternative_lines": [],
            "ev_delta": 0.0,
        },
        "note": "stub — completed-hand analysis lands in Phase 5",
    }
