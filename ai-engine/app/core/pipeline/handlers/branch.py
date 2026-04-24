"""Conditional branch primitive — evaluates a condition against upstream output
and marks downstream nodes NOT on the chosen path as skipped.

Config:
  {
    "condition": {
      "source": "n_classifier.json.tool_call",  # variable ref
      "operator": "==",                          # one of: == != > < >= <= contains exists
      "value": true                              # right-hand side (omitted for `exists`)
    },
    "route_to_when_true": ["n_tool_call"],       # downstream node ids to take if condition is True
    "route_to_when_false": ["n_default"]         # OPTIONAL — only marked skipped if not in true path
  }

If `condition` evaluates True → the loop continues normally for nodes in
`route_to_when_true`; nodes that are downstream-of-this-branch but NOT in
`route_to_when_true` get added to `ctx.skipped_by_branch`.

Downstream is computed from the DAG edges given to execute_dag (we re-walk
edges from this node).
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.pipeline.template import _lookup_path  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


def _resolve_source(source_ref: str, ctx: Any) -> Any:
    """Resolve `node_id.field.path` against ctx.node_outputs (and a few extra roots)."""
    if not source_ref:
        return None
    parts = source_ref.split(".")
    if not parts:
        return None
    root_key, *path = parts

    # Same extra roots as render_template
    if root_key == "user_input":
        root = {"message": ctx.user_message or ""}
    elif root_key == "ctx":
        root = {
            "rag_context": ctx.rag_context or "",
            "history": ctx.history or [],
            "intent_type": ctx.intent_type,
        }
    else:
        root = ctx.node_outputs.get(root_key)
    if root is None:
        return None
    if not path:
        return root
    return _lookup_path(root, path)


def _evaluate(operator: str, lhs: Any, rhs: Any) -> bool:
    op = (operator or "==").strip()
    try:
        if op == "exists":
            return lhs is not None
        if op == "==":
            return lhs == rhs
        if op == "!=":
            return lhs != rhs
        if op == "contains":
            if lhs is None:
                return False
            if isinstance(lhs, (list, tuple, set, str)):
                return rhs in lhs
            if isinstance(lhs, dict):
                return rhs in lhs
            return False
        # Numeric comparisons — coerce both sides
        try:
            l_num = float(lhs)
            r_num = float(rhs)
        except (TypeError, ValueError):
            return False
        if op == ">":
            return l_num > r_num
        if op == "<":
            return l_num < r_num
        if op == ">=":
            return l_num >= r_num
        if op == "<=":
            return l_num <= r_num
    except Exception as e:
        logger.warning("branch evaluate raised: %s", e)
        return False
    logger.warning("branch unknown operator: %s", operator)
    return False


def _immediate_children(start_node_id: str, edges: list[dict]) -> set[str]:
    """Direct children of `start_node_id` (one hop downstream)."""
    return {e.get("to") for e in edges if e.get("from") == start_node_id and e.get("to")}


async def handle_branch(node: dict, ctx: Any) -> dict:
    """Evaluate condition, mark skipped nodes on losing routes."""
    cfg = node.get("config") or {}
    condition = cfg.get("condition") or {}
    source = condition.get("source")
    operator = condition.get("operator", "==")
    rhs = condition.get("value")

    lhs = _resolve_source(source, ctx)
    matched = _evaluate(operator, lhs, rhs)

    route_true: list[str] = list(cfg.get("route_to_when_true") or [])
    route_false: list[str] = list(cfg.get("route_to_when_false") or [])

    # Mark only IMMEDIATE children that aren't on the chosen path. The executor
    # handles cascading skip — if a downstream node loses ALL its predecessors to
    # skipped/error, the executor marks it skipped too. This way diamond patterns
    # (n_output reached via two parents) still run when at least one path survives.
    edges: list[dict] = getattr(ctx, "_dag_edges", []) or []
    my_id = node.get("id") or ""
    children = _immediate_children(my_id, edges) if my_id else set()

    chosen = set(route_true) if matched else set(route_false)
    if not chosen:
        # No explicit route on this side → all immediate children proceed.
        skipped: set[str] = set()
    else:
        # Skip immediate children not in chosen route.
        skipped = children - chosen

    ctx.skipped_by_branch.update(skipped)

    output = {
        "matched": matched,
        "lhs": lhs,
        "rhs": rhs,
        "operator": operator,
        "route_taken": "true" if matched else "false",
        "skipped_node_ids": sorted(skipped),
    }
    summary = f"branch: {source} {operator} {rhs!r} → {matched} ({'true' if matched else 'false'} route, skipped {len(skipped)})"
    return {"status": "ok", "output": output, "summary": summary}
