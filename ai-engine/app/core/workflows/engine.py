"""
Workflow Engine -- Multi-step process orchestration
"""
from app.db import crud


class WorkflowEngine:

    async def create_workflow(self, project_id: str, name: str,
                              trigger_description: str, steps: list) -> dict:
        return crud.create_workflow(project_id, name, trigger_description, steps)

    async def start_workflow(self, workflow_id: str, session_id: str, user_id: str) -> dict:
        workflow = crud.get_workflow(workflow_id)
        if not workflow:
            return {"status": "error", "detail": "Workflow not found"}

        steps = workflow.get("steps_json", [])
        if not steps:
            return {"status": "error", "detail": "Workflow has no steps"}

        run = crud.create_workflow_run(workflow_id, session_id, user_id)
        first_step = steps[0] if isinstance(steps, list) else steps.get("steps", [{}])[0]

        crud.update_workflow_run(
            run["id"],
            current_step=first_step.get("id", "step_0"),
            status="waiting_input",
            context_json={"step_index": 0},
        )

        return {
            "status": "started",
            "run_id": run["id"],
            "current_step": first_step,
            "workflow_name": workflow["name"],
        }

    async def advance_workflow(self, run_id: str, step_result: dict) -> dict:
        run = crud.get_workflow_run(run_id)
        if not run:
            return {"status": "error", "detail": "Run not found"}

        workflow = crud.get_workflow(run["workflow_id"])
        steps = workflow.get("steps_json", [])
        if isinstance(steps, dict):
            steps = steps.get("steps", [])

        context = run.get("context_json", {})
        step_index = context.get("step_index", 0)
        context[f"step_{step_index}_result"] = step_result

        next_index = step_index + 1
        if next_index >= len(steps):
            # Workflow complete
            crud.update_workflow_run(
                run_id, current_step="done", status="completed",
                context_json=context,
            )
            return {"status": "completed", "context": context}

        next_step = steps[next_index]
        context["step_index"] = next_index
        crud.update_workflow_run(
            run_id,
            current_step=next_step.get("id", f"step_{next_index}"),
            status="waiting_input",
            context_json=context,
        )

        return {
            "status": "advancing",
            "current_step": next_step,
            "step_index": next_index,
            "total_steps": len(steps),
        }

    async def list_workflows(self, project_id: str) -> list[dict]:
        return crud.list_workflows(project_id)


workflow_engine = WorkflowEngine()
