"""
Tool: get_due_reviews
Description: 取 FSRS 到期複習題。Phase 1 stub — 真實 FSRS scheduler 整合在後續 phase。
"""
from typing import Any

TOOL_NAME = "get_due_reviews"

TOOL_DESCRIPTION = (
    "Return concepts that are due for FSRS review. "
    "STUB IN PHASE 1 — returns empty until FSRS scheduler is wired up."
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
    # TODO: integrate FSRS scheduler from app.core.poker.fsrs.
    return {
        "due_reviews": [],
        "note": "FSRS scheduler integration pending — get_due_reviews currently returns empty.",
    }
