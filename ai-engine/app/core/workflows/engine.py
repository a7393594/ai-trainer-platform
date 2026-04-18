"""
Workflow Engine — 多步驟流程編排

支援三種步驟類型，由 `type` 欄位區分（向後相容：無 type 視為 action）：

  action    : 單一動作（對話、工具呼叫、元件、外部 API）
              { "id":"s1", "type":"action", "kind":"tool_call", "params":{...}, "output_var":"x" }

  if        : 條件分支
              { "id":"s2", "type":"if", "condition":"x.status == 'ok'",
                "then":[ ...steps ], "else":[ ...steps ] }

  parallel  : 並行分支（各分支獨立執行，結果寫入 output_var）
              { "id":"s3", "type":"parallel", "branches":[ [ ...steps ], [ ...steps ] ] }

  loop      : 迴圈（while 或 foreach）
              { "id":"s4", "type":"loop", "mode":"while"|"foreach",
                "condition":"i < 3", "items_var":"list_var", "item_var":"it",
                "body":[ ...steps ], "max_iterations": 100 }

`context` 範本：
  - 所有 action 結果可寫入 `context[output_var]`
  - step 之間的變數用 Python-safe 表達式（受限 eval）存取
  - `execute_action` hook 可由呼叫端覆寫以接外部動作
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from app.db import crud


ActionExecutor = Callable[[dict, dict], Awaitable[dict]]


# ============================================
# 受限 condition 求值
# ============================================

_SAFE_BUILTINS: dict[str, Any] = {
    "len": len, "min": min, "max": max, "sum": sum,
    "any": any, "all": all, "abs": abs, "bool": bool,
    "int": int, "float": float, "str": str, "True": True, "False": False, "None": None,
}


def _eval_condition(expr: str | bool, context: dict) -> bool:
    """安全求值條件。只允許表達式（單一 line），只能讀 context 變數 + 安全 builtins。"""
    if isinstance(expr, bool):
        return expr
    if not expr or not isinstance(expr, str):
        return False
    try:
        # 禁止 dunder / import
        banned = ["__", "import ", "exec(", "eval(", "open(", "compile(", "globals(", "locals("]
        if any(b in expr for b in banned):
            return False
        return bool(eval(expr, {"__builtins__": _SAFE_BUILTINS}, dict(context)))
    except Exception:
        return False


# ============================================
# 預設 action 執行器
# ============================================

async def _default_action_executor(step: dict, context: dict) -> dict:
    """預設不做實際呼叫；只把 step.params 當結果回傳。外部可注入真 executor。"""
    kind = step.get("kind", "noop")

    if kind == "tool_call":
        tool_id = step.get("tool_id")
        if tool_id:
            from app.core.tools.registry import tool_registry

            return await tool_registry.execute_tool(tool_id, params=step.get("params", {}))
        return {"status": "error", "detail": "tool_id required"}

    if kind == "set":
        # 直接寫入變數：{"kind":"set", "value":{"x":1}} → merged into context
        return {"status": "success", "data": step.get("value", {})}

    if kind == "noop":
        return {"status": "success"}

    return {"status": "success", "detail": f"unhandled kind={kind}", "params": step.get("params", {})}


# ============================================
# 引擎
# ============================================

MAX_STEPS_PER_RUN = 500  # 安全上限，避免無窮迴圈


class WorkflowEngine:

    def __init__(self, action_executor: ActionExecutor | None = None):
        self._executor: ActionExecutor = action_executor or _default_action_executor

    # ----------------------------
    # Legacy API（保留向後相容）
    # ----------------------------

    async def create_workflow(
        self,
        project_id: str,
        name: str,
        trigger_description: str,
        steps: list,
    ) -> dict:
        return crud.create_workflow(project_id, name, trigger_description, steps)

    async def start_workflow(self, workflow_id: str, session_id: str, user_id: str) -> dict:
        workflow = crud.get_workflow(workflow_id)
        if not workflow:
            return {"status": "error", "detail": "Workflow not found"}

        steps = self._normalize_steps(workflow.get("steps_json", []))
        if not steps:
            return {"status": "error", "detail": "Workflow has no steps"}

        run = crud.create_workflow_run(workflow_id, session_id, user_id)
        first_step = steps[0]
        crud.update_workflow_run(
            run["id"],
            current_step=first_step.get("id", "step_0"),
            status="waiting_input",
            context_json={"step_index": 0, "vars": {}},
        )
        return {
            "status": "started",
            "run_id": run["id"],
            "current_step": first_step,
            "workflow_name": workflow["name"],
        }

    async def advance_workflow(self, run_id: str, step_result: dict) -> dict:
        """推進一步（舊版線性用法，保留相容）。"""
        run = crud.get_workflow_run(run_id)
        if not run:
            return {"status": "error", "detail": "Run not found"}

        workflow = crud.get_workflow(run["workflow_id"])
        steps = self._normalize_steps(workflow.get("steps_json", []))

        context = run.get("context_json") or {}
        step_index = context.get("step_index", 0)
        context[f"step_{step_index}_result"] = step_result

        next_index = step_index + 1
        if next_index >= len(steps):
            crud.update_workflow_run(run_id, current_step="done", status="completed", context_json=context)
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

    # ----------------------------
    # 新：完整編排（支援 if/parallel/loop）
    # ----------------------------

    async def run_to_completion(
        self,
        workflow_id: str,
        session_id: str | None = None,
        user_id: str | None = None,
        initial_vars: dict | None = None,
    ) -> dict:
        """從頭跑到尾（適用於不需人工介入的自動工作流）。"""
        workflow = crud.get_workflow(workflow_id)
        if not workflow:
            return {"status": "error", "detail": "Workflow not found"}

        steps = self._normalize_steps(workflow.get("steps_json", []))
        if not steps:
            return {"status": "error", "detail": "Workflow has no steps"}

        run = crud.create_workflow_run(workflow_id, session_id, user_id or "")
        context = {"vars": dict(initial_vars or {}), "_step_count": 0, "_trace": []}

        try:
            await self._run_steps(steps, context)
            status = "completed"
        except WorkflowError as e:
            context["_error"] = str(e)
            status = "failed"
        except Exception as e:  # noqa: BLE001
            context["_error"] = f"unexpected: {e}"
            status = "failed"

        # Supabase 不允許序列化某些 dict；做一次淺拷貝 + str 化保險
        save_ctx = {k: v for k, v in context.items() if k != "_internal"}
        crud.update_workflow_run(run["id"], current_step="done", status=status, context_json=save_ctx)
        return {
            "status": status,
            "run_id": run["id"],
            "vars": context.get("vars", {}),
            "trace": context.get("_trace", []),
            "error": context.get("_error"),
        }

    async def _run_steps(self, steps: list[dict], context: dict) -> None:
        for step in steps:
            await self._run_step(step, context)

    async def _run_step(self, step: dict, context: dict) -> None:
        context["_step_count"] = context.get("_step_count", 0) + 1
        if context["_step_count"] > MAX_STEPS_PER_RUN:
            raise WorkflowError(f"Exceeded MAX_STEPS_PER_RUN={MAX_STEPS_PER_RUN}")

        step_type = step.get("type", "action")
        step_id = step.get("id", f"s{context['_step_count']}")
        context["_trace"].append({"step": step_id, "type": step_type})

        if step_type == "action":
            await self._run_action(step, context)
        elif step_type == "if":
            await self._run_if(step, context)
        elif step_type == "parallel":
            await self._run_parallel(step, context)
        elif step_type == "loop":
            await self._run_loop(step, context)
        else:
            raise WorkflowError(f"Unknown step type: {step_type}")

    async def _run_action(self, step: dict, context: dict) -> None:
        # 把 vars 展平到 context 讓 executor 直接讀
        exec_ctx = {**context.get("vars", {}), "_context": context}
        result = await self._executor(step, exec_ctx)

        # set kind 把 value 合併進 vars
        if step.get("kind") == "set" and isinstance(result.get("data"), dict):
            context["vars"].update(result["data"])

        output_var = step.get("output_var")
        if output_var:
            context["vars"][output_var] = result

    async def _run_if(self, step: dict, context: dict) -> None:
        cond = step.get("condition", False)
        branch = step.get("then", []) if _eval_condition(cond, context.get("vars", {})) else step.get("else", [])
        await self._run_steps(branch or [], context)

    async def _run_parallel(self, step: dict, context: dict) -> None:
        branches = step.get("branches", []) or []
        # 每個分支跑在獨立 context copy，完成後把 vars 合併回主 context
        async def _run_branch(branch_steps: list[dict]) -> dict:
            sub = {"vars": dict(context["vars"]), "_step_count": 0, "_trace": []}
            await self._run_steps(branch_steps, sub)
            return sub

        results = await asyncio.gather(*[_run_branch(b) for b in branches], return_exceptions=True)
        for idx, r in enumerate(results):
            if isinstance(r, Exception):
                context["_trace"].append({"branch": idx, "error": str(r)})
                continue
            # 最後寫入者勝；trace 保留所有分支
            context["vars"].update(r.get("vars", {}))
            context["_trace"].extend([{"branch": idx, **t} for t in r.get("_trace", [])])

    async def _run_loop(self, step: dict, context: dict) -> None:
        mode = step.get("mode", "while")
        body = step.get("body", []) or []
        max_iter = int(step.get("max_iterations", 100))

        if mode == "foreach":
            items_var = step.get("items_var")
            item_var = step.get("item_var", "item")
            items = context["vars"].get(items_var, []) if items_var else []
            if not isinstance(items, list):
                raise WorkflowError(f"items_var '{items_var}' is not a list")
            for i, item in enumerate(items[:max_iter]):
                context["vars"][item_var] = item
                context["vars"][f"{item_var}_index"] = i
                await self._run_steps(body, context)
            return

        # while
        cond = step.get("condition", False)
        i = 0
        while _eval_condition(cond, context.get("vars", {})) and i < max_iter:
            context["vars"]["_loop_i"] = i
            await self._run_steps(body, context)
            i += 1

    # ----------------------------
    # Helpers
    # ----------------------------

    @staticmethod
    def _normalize_steps(steps_raw: Any) -> list[dict]:
        if isinstance(steps_raw, dict):
            steps_raw = steps_raw.get("steps", [])
        return list(steps_raw or [])


class WorkflowError(Exception):
    """Raised when the workflow definition is malformed or execution is aborted."""


workflow_engine = WorkflowEngine()
