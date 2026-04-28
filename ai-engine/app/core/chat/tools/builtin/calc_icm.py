"""
Tool: calc_icm
Description: Malmuth-Harville ICM 計算 — 各 position 的 dollar EV。
            遞迴版本,簡單但 O(n!) 在玩家數很多時會慢;對 9-player MTT FT 仍可用。
"""
from typing import Any

TOOL_NAME = "calc_icm"

TOOL_DESCRIPTION = (
    "Compute each player's dollar EV under the Malmuth-Harville ICM model. "
    "stacks is a dict position -> chip count (or bb). payouts is a list of payout shares "
    "for 1st, 2nd, ... place (length must be >= number of remaining players or shorter)."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "stacks": {
            "type": "object",
            "description": "Mapping of position label (e.g. 'BTN') to chip stack.",
            "additionalProperties": {"type": "number"},
        },
        "payouts": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Payout for 1st, 2nd, ... (any unit; e.g. share of prize pool).",
        },
    },
    "required": ["stacks", "payouts"],
}


def _icm_recurse(
    positions: list[str],
    stacks: dict[str, float],
    payouts: list[float],
) -> dict[str, float]:
    """
    Returns {position: $EV}. Malmuth-Harville:
      P(player i finishes 1st) = stack_i / sum(stacks)
      $EV(i) = sum over k of P(i finishes k-th) * payout_k
    Recursion: assign each finishing slot from 1st to last.
    """
    n = len(positions)
    evs: dict[str, float] = {p: 0.0 for p in positions}
    if n == 0 or not payouts:
        return evs

    def recurse(remaining: list[str], place: int, prefix_prob: float):
        # `place` is the next finishing slot to assign (0 = 1st place).
        if place >= len(payouts) or not remaining:
            return
        total = sum(stacks[p] for p in remaining)
        if total <= 0:
            return
        for p in remaining:
            prob = prefix_prob * (stacks[p] / total)
            evs[p] += prob * payouts[place]
            new_remaining = [q for q in remaining if q != p]
            recurse(new_remaining, place + 1, prob)

    recurse(positions, 0, 1.0)
    return evs


async def execute(
    params: dict,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    stacks_raw = params.get("stacks") or {}
    payouts = params.get("payouts") or []

    if not isinstance(stacks_raw, dict) or not stacks_raw:
        return {"position_evs": {}, "error": "stacks required (dict)"}
    if not isinstance(payouts, list) or not payouts:
        return {"position_evs": {}, "error": "payouts required (list)"}

    # filter zero/negative stacks
    stacks: dict[str, float] = {}
    for k, v in stacks_raw.items():
        try:
            f = float(v)
            if f > 0:
                stacks[str(k)] = f
        except Exception:
            continue

    if not stacks:
        return {"position_evs": {}, "error": "no positive stacks"}

    positions = list(stacks.keys())

    # Guard against pathological input sizes (11! ~= 40M; 10! ~= 3.6M is OK).
    if len(positions) > 9:
        return {
            "position_evs": {},
            "error": f"too many players for recursive ICM ({len(positions)} > 9)",
        }

    payouts_f = [float(p) for p in payouts]
    evs = _icm_recurse(positions, stacks, payouts_f)

    total_pool = sum(payouts_f)
    return {
        "position_evs": {k: round(v, 6) for k, v in evs.items()},
        "total_pool": round(total_pool, 6),
        "method": "malmuth_harville_recursive",
    }
