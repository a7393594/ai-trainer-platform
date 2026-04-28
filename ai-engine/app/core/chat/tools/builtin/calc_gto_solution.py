"""
Tool: calc_gto_solution
Description: 查詢 GTO 解算結果(Phase 1 用 LLM 近似)。Cache 24h(spot_hash → solution),
            in-memory 即可,server 重啟清空。
"""
import hashlib
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

TOOL_NAME = "calc_gto_solution"

TOOL_DESCRIPTION = (
    "Approximate GTO action frequencies for a poker spot. "
    "spot_descriptor describes board, hero/villain ranges, position, stack depth, etc. "
    "Returns a list of {action, frequency, ev} suggestions."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "spot_descriptor": {
            "type": "object",
            "description": (
                "Spot description: e.g. {board, hero_range, villain_range, position, "
                "stack_depth_bb, pot_size_bb, prior_action}."
            ),
        }
    },
    "required": ["spot_descriptor"],
}


# in-memory cache: hash -> {"data": dict, "ts": epoch_seconds}
_GTO_CACHE: dict[str, dict] = {}
_CACHE_TTL_SEC = 24 * 3600


def _spot_hash(spot: dict) -> str:
    """Stable canonical hash of the spot descriptor."""
    blob = json.dumps(spot, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


_SYSTEM_PROMPT = (
    "You are a poker GTO advisor. Given a spot descriptor (board, ranges, "
    "stacks, position), respond with a JSON object of the form:\n"
    "{\n"
    '  "actions": [\n'
    '     {"action": "check"|"bet 33%"|"bet 75%"|"call"|"fold"|"raise 3x"|...,\n'
    '      "frequency": 0.0-1.0, "ev": <number in bb>}\n'
    "  ]\n"
    "}\n"
    "Frequencies should sum to ~1.0. EVs in bb. Output ONLY the JSON, no prose."
)


async def execute(
    params: dict,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    spot = params.get("spot_descriptor") or {}
    if not isinstance(spot, dict) or not spot:
        return {"actions": [], "error": "spot_descriptor required (dict)"}

    h = _spot_hash(spot)
    now = time.time()
    cached = _GTO_CACHE.get(h)
    if cached and (now - cached["ts"] < _CACHE_TTL_SEC):
        return {
            "actions": cached["data"].get("actions", []),
            "spot_hash": h,
            "from_cache": True,
        }

    try:
        from app.core.llm_router.router import chat_completion
    except Exception as e:  # pragma: no cover
        return {"actions": [], "error": f"llm_router unavailable: {e}"}

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(spot, ensure_ascii=False)},
    ]

    try:
        response = await chat_completion(
            messages=messages,
            model="claude-sonnet-4-20250514",
            temperature=0.2,
            max_tokens=1500,
            tenant_id=tenant_id,
            project_id=project_id,
            session_id=session_id,
            span_label="calc_gto_solution",
        )
        text = (response.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("calc_gto_solution LLM call failed: %s", e)
        return {"actions": [], "error": f"LLM call failed: {e}", "spot_hash": h}

    # Strip code fences if any
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            first, rest = text.split("\n", 1)
            if first.lower().startswith("json"):
                text = rest

    try:
        data = json.loads(text)
    except Exception as e:
        return {
            "actions": [],
            "error": f"could not parse JSON: {e}",
            "raw": text[:500],
            "spot_hash": h,
        }

    _GTO_CACHE[h] = {"data": data, "ts": now}
    return {
        "actions": data.get("actions", []),
        "spot_hash": h,
        "from_cache": False,
    }
