"""
Tool: calc_ev
Description: 純 EV 公式計算: ev = win_prob * win_amount - lose_prob * lose_amount。
"""
from typing import Any

TOOL_NAME = "calc_ev"

TOOL_DESCRIPTION = (
    "Compute expected value (EV) for a single decision. "
    "EV = win_prob * win_amount - (1 - win_prob - tie_prob) * lose_amount. "
    "Tie outcomes are assumed neutral (zero EV contribution)."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "win_prob": {"type": "number", "description": "Probability of winning (0-1)."},
        "win_amount": {"type": "number", "description": "Amount won in winning outcome (in chips/bb/$)."},
        "lose_amount": {"type": "number", "description": "Amount lost in losing outcome (positive number)."},
        "tie_prob": {
            "type": "number",
            "description": "Probability of tie (default 0). Tie outcome is treated as zero EV.",
            "default": 0,
        },
    },
    "required": ["win_prob", "win_amount", "lose_amount"],
}


async def execute(
    params: dict,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    win_prob = float(params.get("win_prob", 0))
    win_amount = float(params.get("win_amount", 0))
    lose_amount = float(params.get("lose_amount", 0))
    tie_prob = float(params.get("tie_prob", 0) or 0)
    lose_prob = max(0.0, 1.0 - win_prob - tie_prob)
    ev = win_prob * win_amount - lose_prob * lose_amount
    return {
        "ev": round(ev, 6),
        "win_prob": win_prob,
        "tie_prob": tie_prob,
        "lose_prob": round(lose_prob, 6),
        "win_amount": win_amount,
        "lose_amount": lose_amount,
    }
