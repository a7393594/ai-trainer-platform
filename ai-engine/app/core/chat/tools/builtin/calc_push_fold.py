"""
Tool: calc_push_fold
Description: MTT push/fold 決策 — 比較 push 與 fold 的 chip EV / dollar EV(經 ICM)。
            獨立檔(不依賴 calc_equity / calc_icm 工具),內含簡化版 equity & ICM 計算。
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

TOOL_NAME = "calc_push_fold"

TOOL_DESCRIPTION = (
    "Decide MTT push-vs-fold for a given hand. "
    "Computes chip EV and (when payouts provided) dollar EV via ICM, returns 'push' / 'fold' / 'mixed' verdict."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "hand": {"type": "string", "description": "Hero hand, e.g. 'AsKd' or shorthand 'AKs'."},
        "position": {"type": "string", "description": "Hero position, e.g. 'BTN'."},
        "stack": {"type": "number", "description": "Hero stack in bb."},
        "opp_stacks": {
            "type": "object",
            "description": "Opponent stacks: {position: bb}.",
            "additionalProperties": {"type": "number"},
        },
        "opp_calling_range": {
            "type": "string",
            "description": "Calling range; supports 'Nash', 'top12%', or comma-separated combos.",
            "default": "top12%",
        },
        "payouts": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Payout structure (1st, 2nd, ...) for $EV via ICM.",
        },
    },
    "required": ["hand", "position", "stack", "opp_stacks"],
}


# --- minimal embedded equity (rough, vs simple "top X%" range) ---

_TOP_PERCENT_RANGES = {
    # cumulative top X% calling range (rough heuristics)
    5: "TT+,AKs,AKo",
    8: "88+,ATs+,KQs,AJo+",
    12: "55+,A2s+,KTs+,QTs+,JTs,ATo+,KJo+",
    15: "33+,A2s+,K9s+,QTs+,JTs,T9s,A9o+,KTo+,QJo",
    20: "22+,A2s+,K7s+,Q9s+,J9s+,T9s,98s,A7o+,KTo+,QTo+,JTo",
    25: "22+,A2s+,K5s+,Q8s+,J8s+,T8s+,97s+,87s,76s,A2o+,K9o+,Q9o+,J9o+,T9o",
    30: "22+,A2+,K2s+,Q2s+,J7s+,T7s+,97s+,87s,76s,65s,A2o+,K7o+,Q9o+,J9o+,T9o,98o",
}


def _approx_equity(hero: str, top_pct: int) -> float:
    """Lookup-table approximation of hero equity vs a top-X% calling range, preflop.

    Source: rough hand-equity numbers; not exact but adequate for push/fold decisions.
    """
    h = hero.upper()
    rank_strength = {
        "AA": 0.85, "KK": 0.82, "QQ": 0.80, "JJ": 0.77, "TT": 0.75,
        "99": 0.71, "88": 0.69, "77": 0.66, "66": 0.63, "55": 0.60,
        "44": 0.57, "33": 0.54, "22": 0.50,
        "AKS": 0.67, "AKO": 0.65, "AQS": 0.66, "AQO": 0.64, "AJS": 0.65, "AJO": 0.62,
        "ATS": 0.63, "ATO": 0.60, "KQS": 0.62, "KQO": 0.59, "KJS": 0.60, "KJO": 0.57,
        "QJS": 0.58, "JTS": 0.57, "T9S": 0.55, "98S": 0.53,
    }
    # normalise hero to 'AKs' / 'AKo' / 'AA' form
    if len(h) == 4:
        # explicit suits e.g. 'AsKh'
        r1, s1, r2, s2 = h[0], h[1], h[2], h[3]
        if r1 == r2:
            key = r1 + r2
        elif s1 == s2:
            key = (r1 + r2) + "S" if rank_idx(r1) >= rank_idx(r2) else (r2 + r1) + "S"
        else:
            key = (r1 + r2) + "O" if rank_idx(r1) >= rank_idx(r2) else (r2 + r1) + "O"
    elif len(h) == 2:
        key = h
    elif len(h) == 3:
        key = h
    else:
        key = h[:3]
    base = rank_strength.get(key.upper(), 0.45)
    # adjust by tightness: against tighter (lower top_pct) range, equity shifts down
    adj = 1.0 - 0.005 * max(0, 12 - top_pct)
    return max(0.05, min(0.95, base * adj))


def rank_idx(r: str) -> int:
    order = "23456789TJQKA"
    return order.index(r.upper()) if r.upper() in order else 0


# --- minimal ICM (recursive Malmuth-Harville) ---

def _icm_simple(stacks: dict[str, float], payouts: list[float]) -> dict[str, float]:
    positions = list(stacks.keys())
    evs = {p: 0.0 for p in positions}
    if not payouts or not positions:
        return evs
    if len(positions) > 9:
        return evs

    def recurse(remaining: list[str], place: int, prob: float):
        if place >= len(payouts) or not remaining:
            return
        total = sum(stacks[p] for p in remaining)
        if total <= 0:
            return
        for p in remaining:
            pr = prob * (stacks[p] / total)
            evs[p] += pr * payouts[place]
            recurse([q for q in remaining if q != p], place + 1, pr)

    recurse(positions, 0, 1.0)
    return evs


# --- main ---

async def execute(
    params: dict,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    hand = str(params.get("hand", ""))
    position = str(params.get("position", ""))
    stack = float(params.get("stack", 0))
    opp_stacks = params.get("opp_stacks") or {}
    calling_range = str(params.get("opp_calling_range", "top12%"))
    payouts = params.get("payouts") or []

    if not hand or not position or stack <= 0 or not isinstance(opp_stacks, dict):
        return {"verdict": "fold", "error": "missing required params"}

    # Parse calling range to a top-percent
    top_pct = 12
    cr = calling_range.lower().strip()
    if cr.startswith("top"):
        try:
            top_pct = int(cr.replace("top", "").replace("%", "").strip())
        except Exception:
            top_pct = 12
    elif cr == "nash":
        top_pct = 12  # rough Nash-equilibrium approximation
    # else: explicit combos — would need full equity calc; use 15% heuristic
    elif "," in cr:
        top_pct = 15

    eq = _approx_equity(hand, top_pct)

    # Assume single biggest opp acts as caller
    if not opp_stacks:
        return {"verdict": "fold", "error": "no opponents"}
    biggest_opp_stack = max(opp_stacks.values()) if opp_stacks else 0
    risk = min(stack, float(biggest_opp_stack))
    if risk <= 0:
        return {"verdict": "fold", "error": "no opponent has chips"}

    pot_assumption = 1.5  # SB + BB pre-action
    win_amount = pot_assumption + risk  # what hero collects when called and wins
    # Estimate fold-equity: assume opp folds (1 - calling_freq); calling_freq ~ top_pct / 100
    fold_eq = max(0.0, 1.0 - top_pct / 100.0)
    push_chip_ev = (
        fold_eq * pot_assumption  # opp folds, hero takes blinds
        + (1 - fold_eq) * (eq * win_amount - (1 - eq) * risk)
    )
    fold_chip_ev = 0.0

    push_dollar_ev: float | None = None
    fold_dollar_ev: float | None = None
    if payouts and isinstance(payouts, list):
        # baseline ICM with hero alive
        all_stacks = {position: stack, **{k: float(v) for k, v in opp_stacks.items()}}
        baseline_icm = _icm_simple(all_stacks, [float(p) for p in payouts])
        baseline_hero_dollar = baseline_icm.get(position, 0.0)
        # post-call hero double-up scenario
        double_stacks = dict(all_stacks)
        double_stacks[position] = stack + risk
        # decrement biggest opp
        biggest_pos = max(opp_stacks, key=lambda k: opp_stacks[k])
        double_stacks[biggest_pos] = max(0.0, opp_stacks[biggest_pos] - risk)
        if double_stacks[biggest_pos] == 0:
            double_stacks.pop(biggest_pos)
        win_icm = _icm_simple(double_stacks, [float(p) for p in payouts])
        hero_win_dollar = win_icm.get(position, 0.0)
        # bust scenario
        bust_stacks = {k: v for k, v in all_stacks.items() if k != position}
        bust_icm = _icm_simple(bust_stacks, [float(p) for p in payouts])
        # hero ICM when busted = 0 (bust no payout assumption simplification)
        # blinds-collected scenario (push, opp folds, hero gets pot)
        fold_stacks = dict(all_stacks)
        fold_stacks[position] = stack + pot_assumption
        fold_icm = _icm_simple(fold_stacks, [float(p) for p in payouts])
        hero_fold_dollar = fold_icm.get(position, 0.0)

        push_dollar_ev = (
            fold_eq * (hero_fold_dollar - baseline_hero_dollar)
            + (1 - fold_eq) * (eq * (hero_win_dollar - baseline_hero_dollar)
                               + (1 - eq) * (0 - baseline_hero_dollar))
        )
        fold_dollar_ev = 0.0

    # Verdict
    threshold = 0.05  # bb
    decisive_ev = push_dollar_ev if push_dollar_ev is not None else push_chip_ev
    if decisive_ev > threshold:
        verdict = "push"
        frequency = 1.0
    elif decisive_ev < -threshold:
        verdict = "fold"
        frequency = 0.0
    else:
        verdict = "mixed"
        # rough mixed frequency: closer to 0 -> closer to 50/50
        frequency = round(0.5 + max(-0.5, min(0.5, decisive_ev)), 3)

    return {
        "push_chip_ev": round(push_chip_ev, 4),
        "fold_chip_ev": round(fold_chip_ev, 4),
        "push_dollar_ev": round(push_dollar_ev, 6) if push_dollar_ev is not None else None,
        "fold_dollar_ev": round(fold_dollar_ev, 6) if fold_dollar_ev is not None else None,
        "verdict": verdict,
        "frequency": frequency,
        "hero_equity": round(eq, 4),
        "fold_equity": round(fold_eq, 4),
        "calling_range_top_pct": top_pct,
    }
