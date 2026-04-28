"""
Tool: calc_equity
Description: 計算 hero 手牌 vs villain range 的 equity (win/tie/lose)。
            無 poker 評估 lib(treys/pypokerengine 都未安裝),所以用 Monte Carlo 1000 次模擬,
            搭配自寫的 7-card hand evaluator(rank-by-category, cached)。
"""
import random
from itertools import combinations
from typing import Any

TOOL_NAME = "calc_equity"

TOOL_DESCRIPTION = (
    "Calculate hero equity vs a villain range on a given board (Monte Carlo 1000 trials). "
    "hero is two-card string 'AsKd'; villain_range can be a single combo 'KhJh' or a "
    "shorthand range '22+,A2s+,KQs'; board is 0/3/4/5 cards as a single string."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "hero": {"type": "string", "description": "Hero hole cards, e.g. '8s9s'."},
        "villain_range": {
            "type": "string",
            "description": "Either a specific combo like 'KhJh' or a range string '22+,A2s+,KQs'.",
        },
        "board": {
            "type": "string",
            "description": "Community cards concatenated, e.g. 'JdQc8d5cQc' (0/3/4/5 cards).",
        },
    },
    "required": ["hero", "villain_range"],
}


# ----- card utilities -----

_RANK_ORDER = "23456789TJQKA"
_RANK_VAL = {r: i for i, r in enumerate(_RANK_ORDER, start=2)}  # 2..14
_SUITS = "shdc"
_FULL_DECK = [r + s for r in _RANK_ORDER for s in _SUITS]


def _parse_cards(s: str) -> list[str]:
    """Parse 'AsKd' or 'JdQc8d5cQc' -> ['As','Kd', ...]. Tolerates whitespace/commas."""
    if not s:
        return []
    cleaned = s.replace(" ", "").replace(",", "")
    out = []
    i = 0
    while i + 1 < len(cleaned):
        out.append(cleaned[i] + cleaned[i + 1].lower())
        i += 2
    return out


def _expand_range(range_str: str) -> list[tuple[str, str]]:
    """Expand a shorthand range like '22+,A2s+,KQs,KhJh' into a list of 2-card combos.

    Supports:
      - explicit combos like 'KhJh'
      - pair codes 'AA', 'TT'
      - 'XX+' pair plus (e.g. '22+' = 22..AA)
      - 'XYs' suited two-rank, 'XYo' offsuit
      - 'XYs+' / 'XYo+' (raise the lower of the two ranks up to one below higher)
    """
    combos: list[tuple[str, str]] = []
    if not range_str:
        return combos
    parts = [p.strip() for p in range_str.split(",") if p.strip()]
    for p in parts:
        # Explicit combo? two ranks each with explicit suit, e.g. KhJh
        if len(p) == 4 and p[0] in _RANK_ORDER and p[1].lower() in _SUITS \
                and p[2] in _RANK_ORDER and p[3].lower() in _SUITS:
            combos.append((p[0] + p[1].lower(), p[2] + p[3].lower()))
            continue

        plus = p.endswith("+")
        body = p[:-1] if plus else p

        # Pair?  'AA' or 'AA+'
        if len(body) == 2 and body[0] == body[1] and body[0] in _RANK_ORDER:
            base = _RANK_VAL[body[0]]
            ranks = range(base, 15) if plus else [base]
            for v in ranks:
                r = _RANK_ORDER[v - 2]
                for s1, s2 in combinations(_SUITS, 2):
                    combos.append((r + s1, r + s2))
            continue

        # Suited / offsuit code?  'AKs', 'AKo', 'A2s+', 'KQo+'
        if len(body) == 3 and body[0] in _RANK_ORDER and body[1] in _RANK_ORDER \
                and body[2] in ("s", "o"):
            high, low, st = body[0], body[1], body[2]
            hv, lv = _RANK_VAL[high], _RANK_VAL[low]
            if hv <= lv:
                continue  # invalid input
            low_starts = range(lv, hv) if plus else [lv]
            for low_v in low_starts:
                low_r = _RANK_ORDER[low_v - 2]
                for s1 in _SUITS:
                    for s2 in _SUITS:
                        if st == "s" and s1 != s2:
                            continue
                        if st == "o" and s1 == s2:
                            continue
                        combos.append((high + s1, low_r + s2))
            continue
        # Unparseable token — skip silently.
    return combos


# ----- 5-card hand evaluator (returns a comparable rank tuple) -----

def _eval_5(cards: list[str]) -> tuple:
    """Return a rank tuple — bigger means stronger. Compare with > / < / = directly."""
    ranks = sorted((_RANK_VAL[c[0]] for c in cards), reverse=True)
    suits = [c[1] for c in cards]
    rank_counts: dict[int, int] = {}
    for r in ranks:
        rank_counts[r] = rank_counts.get(r, 0) + 1
    counts_sorted = sorted(rank_counts.items(), key=lambda x: (-x[1], -x[0]))
    count_pattern = tuple(c for _, c in counts_sorted)
    distinct = sorted(rank_counts.keys(), reverse=True)

    flush = len(set(suits)) == 1

    # Straight detection (incl wheel A2345)
    straight = False
    straight_high = 0
    if len(distinct) == 5:
        if distinct[0] - distinct[4] == 4:
            straight = True
            straight_high = distinct[0]
        elif distinct == [14, 5, 4, 3, 2]:
            straight = True
            straight_high = 5

    if straight and flush:
        return (8, straight_high)
    if count_pattern == (4, 1):
        # quads
        quad = counts_sorted[0][0]
        kicker = counts_sorted[1][0]
        return (7, quad, kicker)
    if count_pattern == (3, 2):
        return (6, counts_sorted[0][0], counts_sorted[1][0])
    if flush:
        return (5,) + tuple(ranks)
    if straight:
        return (4, straight_high)
    if count_pattern == (3, 1, 1):
        trip = counts_sorted[0][0]
        kickers = sorted([counts_sorted[1][0], counts_sorted[2][0]], reverse=True)
        return (3, trip, kickers[0], kickers[1])
    if count_pattern == (2, 2, 1):
        pairs = sorted([counts_sorted[0][0], counts_sorted[1][0]], reverse=True)
        return (2, pairs[0], pairs[1], counts_sorted[2][0])
    if count_pattern == (2, 1, 1, 1):
        pair = counts_sorted[0][0]
        kickers = sorted([counts_sorted[1][0], counts_sorted[2][0], counts_sorted[3][0]], reverse=True)
        return (1, pair, *kickers)
    return (0,) + tuple(ranks)


def _best_of_7(cards7: list[str]) -> tuple:
    best = (0,)
    for combo in combinations(cards7, 5):
        r = _eval_5(list(combo))
        if r > best:
            best = r
    return best


# ----- main execute -----

async def execute(
    params: dict,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    hero_cards = _parse_cards(params.get("hero", ""))
    villain_combos = _expand_range(params.get("villain_range", ""))
    board_cards = _parse_cards(params.get("board", ""))

    if len(hero_cards) != 2:
        return {"error": "hero must be two cards", "equity": 0.0}
    if not villain_combos:
        return {"error": "villain_range produced no combos", "equity": 0.0}
    if len(board_cards) not in (0, 3, 4, 5):
        return {"error": "board must be 0/3/4/5 cards", "equity": 0.0}

    known = set(c.lower() for c in hero_cards + board_cards)
    # filter out villain combos that conflict with known cards
    valid_villain = [
        (a, b) for (a, b) in villain_combos
        if a.lower() not in known and b.lower() not in known and a.lower() != b.lower()
    ]
    if not valid_villain:
        return {"error": "no valid villain combos after removing card conflicts", "equity": 0.0}

    trials = 1000
    win = tie = lose = 0
    rng = random.Random()
    deck_lower = [c.lower() for c in _FULL_DECK]

    for _ in range(trials):
        v = rng.choice(valid_villain)
        v_cards = [v[0].lower(), v[1].lower()]
        used = known | set(v_cards)
        remaining = [c for c in deck_lower if c not in used]
        need = 5 - len(board_cards)
        if need < 0 or need > len(remaining):
            continue
        run_out = rng.sample(remaining, need) if need else []
        full_board = [c.lower() for c in board_cards] + run_out
        hero7 = [c.lower() for c in hero_cards] + full_board
        vill7 = v_cards + full_board
        # case-fold for evaluator: ranks are upper, suits lower in our scheme; normalise.
        hero7n = [c[0].upper() + c[1].lower() for c in hero7]
        vill7n = [c[0].upper() + c[1].lower() for c in vill7]
        hr = _best_of_7(hero7n)
        vr = _best_of_7(vill7n)
        if hr > vr:
            win += 1
        elif hr == vr:
            tie += 1
        else:
            lose += 1

    total = win + tie + lose or 1
    equity = (win + tie / 2) / total
    return {
        "equity": round(equity, 4),
        "win": round(win / total, 4),
        "tie": round(tie / total, 4),
        "lose": round(lose / total, 4),
        "method": f"monte_carlo_{trials}",
        "villain_combos": len(valid_villain),
    }
