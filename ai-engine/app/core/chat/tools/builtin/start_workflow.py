"""
Tool: start_workflow
Description: 觸發 WORKFLOW DAG(從 ait_pipeline_dags 讀 dag_kind='workflow')。Phase 1 stub。
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

TOOL_NAME = "start_workflow"

TOOL_DESCRIPTION = (
    "Trigger a workflow DAG from ait_pipeline_dags. "
    "workflow_id is the DAG id; vars is initial variable bindings. "
    "Phase 1: best-effort — falls back to stub if the DAG cannot be executed."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "workflow_id": {"type": "string", "description": "DAG id (or workflow code)."},
        "vars": {
            "type": "object",
            "description": "Initial variable bindings for the workflow.",
        },
    },
    "required": ["workflow_id"],
}


async def execute(
    params: dict,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    workflow_id = params.get("workflow_id")
    vars_ = params.get("vars") or {}

    if not workflow_id:
        return {"workflow_started": False, "error": "workflow_id required"}

    # TODO: full integration in Phase 2+. Need DAG row fetch + dag_executor.execute_dag wiring.
    try:
        from app.db.supabase import get_supabase
        sb = get_supabase()
        result = (
            sb.table("ait_pipeline_dags")
            .select("*")
            .eq("id", workflow_id)
            .eq("dag_kind", "workflow")
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return {
                "workflow_started": False,
                "note": f"workflow not found: {workflow_id}",
            }
        # We have the DAG row but won't execute it yet — would need a non-chat
        # entry point into dag_executor and a user-message synthesised from vars.
        return {
            "workflow_started": False,
            "workflow_id": workflow_id,
            "dag_found": True,
            "note": "stub — workflow execution wiring pending Phase 2",
            "vars": vars_,
        }
    except Exception as e:
        logger.warning("start_workflow stub failed: %s", e)
        return {
            "workflow_started": False,
            "workflow_id": workflow_id,
            "note": f"stub — {e}",
            "vars": vars_,
        }
