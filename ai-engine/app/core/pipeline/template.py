"""Variable substitution engine for DAG node prompts.

Syntax: `{{node_id.field}}` or `{{node_id.field.nested.path}}`.

The engine reads from a `node_outputs: dict[node_id -> output_dict]` map and
substitutes `{{...}}` references with the looked-up values. Type handling:
- str / int / float / bool → inserted as str()
- list / dict → JSON-stringified (compact, ensure_ascii=False)
- None / missing → empty string + warning logged

Special root keys (besides node_ids):
- `user_input.message` — always available, the request user_message
- `ctx.<field>` — direct DAGContext field access (escape hatch)

Errors don't raise — missing variables become empty strings so downstream LLMs
can degrade gracefully. Misspelled paths show up in the rendered prompt so users
can debug visually.
"""
from __future__ import annotations

import json as _json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Match {{ anything except {{ }} inside }}, allowing whitespace around content
_VAR_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def _lookup_path(root: Any, path: list[str]) -> Any:
    """Walk a list of keys/indices into nested dict/list. Return None on miss."""
    cur = root
    for key in path:
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(key)
            continue
        if isinstance(cur, list):
            try:
                cur = cur[int(key)]
            except (ValueError, IndexError):
                return None
            continue
        # Attribute access fallback (for dataclasses / objects)
        cur = getattr(cur, key, None)
    return cur


def _format_value(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, (list, dict)):
        try:
            return _json.dumps(val, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(val)
    return str(val)


def render_template(template: str, node_outputs: dict[str, Any], extra_roots: dict[str, Any] | None = None) -> str:
    """Substitute `{{node.field.path}}` references in `template`.

    `node_outputs` maps node_id → that node's `output` dict (handler return value).
    `extra_roots` adds top-level keys (e.g. `{"user_input": {"message": "..."}}`)
    that aren't node ids.
    """
    if not template:
        return template or ""

    roots: dict[str, Any] = dict(extra_roots or {})
    roots.update(node_outputs)

    def _replace(m: re.Match[str]) -> str:
        expr = m.group(1).strip()
        if not expr:
            return ""
        parts = expr.split(".")
        if not parts:
            return ""
        root_key, *path = parts
        root_val = roots.get(root_key)
        if root_val is None:
            logger.warning("[template] unknown root '%s' in {{%s}}", root_key, expr)
            return ""
        val = _lookup_path(root_val, path) if path else root_val
        if val is None:
            logger.warning("[template] path miss '%s' in {{%s}}", ".".join(path), expr)
            return ""
        return _format_value(val)

    return _VAR_RE.sub(_replace, template)


def list_referenced_vars(template: str) -> list[str]:
    """Extract all `{{...}}` references in template (for static analysis / UI hints)."""
    if not template:
        return []
    return [m.group(1).strip() for m in _VAR_RE.finditer(template)]
