"""
Tool: kb_search
Description: 知識庫檢索(KB v1.1)。Phase 1 stub — Phase 4 由其他 agent 接 KB 真實實作。
"""
from typing import Any

TOOL_NAME = "kb_search"

TOOL_DESCRIPTION = (
    "Search the project knowledge base. "
    "level_max controls KB hierarchy depth (default 2). top_k controls result count (default 5). "
    "STUB IN PHASE 1 — returns empty until KB integration lands."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Free-text search query."},
        "level_max": {"type": "integer", "description": "Max hierarchy depth.", "default": 2},
        "top_k": {"type": "integer", "description": "Number of results to return.", "default": 5},
    },
    "required": ["query"],
}


async def execute(
    params: dict,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    # TODO: integrate KB v1.1 in Phase 4.
    return {
        "results": [],
        "query": params.get("query", ""),
        "note": "KB integration pending Phase 4 — kb_search currently returns empty.",
    }
