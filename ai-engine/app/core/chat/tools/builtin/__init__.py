"""
Built-in tool registry for V4 chat engine.

Each tool module exposes:
  - TOOL_NAME: str
  - TOOL_DESCRIPTION: str
  - INPUT_SCHEMA: dict (JSON schema for Claude tool-use)
  - execute(params, *, tenant_id, user_id, project_id, session_id) -> dict (async)

`BUILTIN_TOOLS` aggregates them into a list of dicts that the registry layer
(written by another agent in tools/registry.py) can consume directly.

Each entry shape:
  {
    "module": <module>,                    # the imported tool module
    "name": str,                           # tool name (== module.TOOL_NAME)
    "description": str,                    # human-readable description
    "input_schema": dict,                  # Claude tool-use JSON schema
    "execute": async callable,             # the execute() coroutine fn
  }
"""
from . import (
    present_widget,
    analyze_screenshot,
    calc_equity,
    calc_ev,
    calc_gto_solution,
    calc_icm,
    calc_push_fold,
    kb_search,
    get_user_stats,
    get_mastery,
    get_due_reviews,
    compose_learning_plan,
    schedule_plan,
    start_workflow,
    start_practice_session,
    simulate_opponent_action,
    get_legal_actions,
    analyze_completed_hand,
    record_fsrs_response,
    opponent_modeling,
)

_MODULES = [
    present_widget,
    analyze_screenshot,
    calc_equity,
    calc_ev,
    calc_gto_solution,
    calc_icm,
    calc_push_fold,
    kb_search,
    get_user_stats,
    get_mastery,
    get_due_reviews,
    compose_learning_plan,
    schedule_plan,
    start_workflow,
    start_practice_session,
    simulate_opponent_action,
    get_legal_actions,
    analyze_completed_hand,
    record_fsrs_response,
    opponent_modeling,
]


def _build_tool_entry(mod) -> dict:
    return {
        "module": mod,
        "name": mod.TOOL_NAME,
        "description": mod.TOOL_DESCRIPTION,
        "input_schema": mod.INPUT_SCHEMA,
        "execute": mod.execute,
    }


BUILTIN_TOOLS: list[dict] = [_build_tool_entry(m) for m in _MODULES]


__all__ = [
    "BUILTIN_TOOLS",
    "present_widget",
    "analyze_screenshot",
    "calc_equity",
    "calc_ev",
    "calc_gto_solution",
    "calc_icm",
    "calc_push_fold",
    "kb_search",
    "get_user_stats",
    "get_mastery",
    "get_due_reviews",
    "compose_learning_plan",
    "schedule_plan",
    "start_workflow",
    "start_practice_session",
    "simulate_opponent_action",
    "get_legal_actions",
    "analyze_completed_hand",
    "record_fsrs_response",
    "opponent_modeling",
]
