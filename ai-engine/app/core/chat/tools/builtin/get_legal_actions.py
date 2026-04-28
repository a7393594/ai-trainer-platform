"""
Tool: get_legal_actions
Description: 純函數計算撲克合法動作 — 給定當前 pot/stack/last_bet,計算可用的 fold/check/call/raise 範圍。
"""
from typing import Any

TOOL_NAME = "get_legal_actions"

TOOL_DESCRIPTION = (
    "Compute legal actions for the player to act. "
    "Inputs: pot, hero_stack, to_call (amount needed to call), last_raise_size, min_raise. "
    "Returns the set of legal action types and their valid ranges."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pot": {"type": "number", "description": "Current pot."},
        "hero_stack": {"type": "number", "description": "Hero's remaining stack."},
        "to_call": {"type": "number", "description": "Amount hero must put in to call (0 if option)."},
        "last_raise_size": {
            "type": "number",
            "description": "Size of the last raise (used to derive min raise).",
            "default": 0,
        },
        "min_raise": {
            "type": "number",
            "description": "Override for minimum raise size.",
        },
    },
    "required": ["pot", "hero_stack", "to_call"],
}


async def execute(
    params: dict,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    pot = float(params.get("pot", 0))
    stack = float(params.get("hero_stack", 0))
    to_call = float(params.get("to_call", 0))
    last_raise = float(params.get("last_raise_size", 0) or 0)
    explicit_min_raise = params.get("min_raise")

    actions: list[dict] = []

    # Fold is always legal if facing a bet
    if to_call > 0:
        actions.append({"action": "fold"})

    # Check is legal if no bet to call
    if to_call <= 0:
        actions.append({"action": "check"})

    # Call (or call all-in) is legal if facing a bet and hero has chips
    if to_call > 0 and stack > 0:
        call_amount = min(to_call, stack)
        actions.append({
            "action": "call",
            "amount": call_amount,
            "all_in": call_amount == stack,
        })

    # Raise is legal if hero has chips beyond the call amount
    if stack > to_call:
        if explicit_min_raise is not None:
            min_raise_total = float(explicit_min_raise)
        else:
            # Standard NLHE: min raise = to_call + max(last_raise, big_blind_proxy=pot * 0.02 floor 1)
            min_raise_total = to_call + (last_raise if last_raise > 0 else max(1.0, pot * 0.02))
        max_raise_total = stack  # all-in ceiling
        if min_raise_total > max_raise_total:
            min_raise_total = max_raise_total
        actions.append({
            "action": "raise",
            "min_total": round(min_raise_total, 4),
            "max_total": round(max_raise_total, 4),
            "all_in_amount": round(stack, 4),
        })

    return {
        "legal_actions": actions,
        "pot": pot,
        "hero_stack": stack,
        "to_call": to_call,
    }
