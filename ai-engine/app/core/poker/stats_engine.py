"""
Stats Engine — 撲克統計計算引擎

從 parsed hand histories 計算核心統計指標：
VPIP, PFR, 3-Bet%, ATS, Fold-to-3Bet, C-Bet (flop/turn/river),
WTSD, W$SD, AF, WWSF, by-position breakdowns
"""
from collections import defaultdict
from typing import Optional


def compute_stats(hands: list[dict], hero_name: str = None) -> dict:
    """計算核心統計指標。

    Args:
        hands: list of parsed_json (UnifiedHand.to_dict() format)
        hero_name: optional hero name filter

    Returns:
        {
            "sample_size": int,
            "vpip": float (0-100),
            "pfr": float,
            "three_bet": float,
            "fold_to_three_bet": float,
            "cbet_flop": float,
            "cbet_turn": float,
            "wtsd": float,
            "won_at_sd": float,
            "af": float,
            "wwsf": float,
            "steal_pct": float,
            "bb_per_100": float,
            "by_position": { "BTN": {...}, "CO": {...}, ... }
        }
    """
    if not hands:
        return {"sample_size": 0}

    # Counters
    total = 0
    vpip_count = 0
    pfr_count = 0
    three_bet_opportunities = 0
    three_bet_count = 0
    fold_to_3b_opportunities = 0
    fold_to_3b_count = 0
    cbet_flop_opportunities = 0
    cbet_flop_count = 0
    cbet_turn_opportunities = 0
    cbet_turn_count = 0
    saw_flop_count = 0
    went_to_sd_count = 0
    won_at_sd_count = 0
    won_without_sd_count = 0
    total_bets_raises = 0
    total_calls = 0
    total_net_bb = 0.0
    steal_opportunities = 0
    steal_count = 0

    # By position
    pos_stats = defaultdict(lambda: {"hands": 0, "vpip": 0, "pfr": 0, "net_bb": 0.0})

    for hand in hands:
        actions = hand.get("actions", [])
        if not actions:
            continue

        total += 1
        hero = hand.get("hero", hero_name or "")
        position = hand.get("hero_position", "")
        net_bb = hand.get("hero_net_bb", 0) or 0
        total_net_bb += net_bb

        # Hero actions by street
        hero_actions = [a for a in actions if a.get("is_hero", False) or a.get("player") == hero]
        preflop_actions = [a for a in hero_actions if a.get("street") == "preflop"]
        flop_actions = [a for a in hero_actions if a.get("street") == "flop"]

        # All actions by street (all players)
        all_preflop = [a for a in actions if a.get("street") == "preflop"]
        all_flop = [a for a in actions if a.get("street") == "flop"]
        all_turn = [a for a in actions if a.get("street") == "turn"]
        all_river = [a for a in actions if a.get("street") == "river"]

        # VPIP: voluntarily put money in pot preflop (call, raise, bet — not posting blinds)
        hero_pf_voluntary = [a for a in preflop_actions if a.get("action") in ("call", "raise", "bet", "all-in")]
        is_vpip = len(hero_pf_voluntary) > 0
        if is_vpip:
            vpip_count += 1

        # PFR: preflop raise
        hero_pf_raises = [a for a in preflop_actions if a.get("action") in ("raise", "bet", "all-in")]
        is_pfr = len(hero_pf_raises) > 0
        if is_pfr:
            pfr_count += 1

        # 3-Bet detection (simplified)
        raise_count_preflop = sum(1 for a in all_preflop if a.get("action") in ("raise", "all-in"))
        if raise_count_preflop >= 1:
            # There was at least one raise, hero could 3-bet
            hero_raise_order = None
            for a in all_preflop:
                if a.get("action") in ("raise", "all-in"):
                    if a.get("is_hero") or a.get("player") == hero:
                        # Count how many raises came before hero's raise
                        prior_raises = sum(
                            1 for pa in all_preflop
                            if pa.get("action") in ("raise", "all-in") and pa.get("order", 0) < a.get("order", 0)
                        )
                        if prior_raises >= 1:
                            three_bet_count += 1
                            three_bet_opportunities += 1
                            break
            else:
                # Hero didn't 3-bet but had opportunity if there was a raise before hero acts
                hero_first_action = preflop_actions[0] if preflop_actions else None
                if hero_first_action and raise_count_preflop >= 1:
                    three_bet_opportunities += 1

        # Fold to 3-bet
        if is_pfr and raise_count_preflop >= 2:
            fold_to_3b_opportunities += 1
            hero_fold = any(a.get("action") == "folds" for a in preflop_actions)
            if hero_fold:
                fold_to_3b_count += 1

        # C-bet flop
        saw_flop = len(all_flop) > 0 and is_vpip
        if saw_flop:
            saw_flop_count += 1
            if is_pfr:
                cbet_flop_opportunities += 1
                hero_flop_bet = any(a.get("action") in ("bet", "raise", "all-in") for a in flop_actions)
                if hero_flop_bet:
                    cbet_flop_count += 1

        # WTSD & W$SD
        saw_river = len(all_river) > 0
        went_to_showdown = saw_river and not any(
            a.get("action") == "folds" and (a.get("is_hero") or a.get("player") == hero)
            for a in actions if a.get("street") == "river"
        )
        if saw_flop and went_to_showdown:
            went_to_sd_count += 1
            if net_bb > 0:
                won_at_sd_count += 1

        # WWSF
        if saw_flop and net_bb > 0:
            won_without_sd_count += 1

        # AF components
        for a in hero_actions:
            act = a.get("action", "")
            if act in ("bet", "raise", "all-in"):
                total_bets_raises += 1
            elif act == "call":
                total_calls += 1

        # Steal (from CO, BTN, SB)
        if position in ("CO", "BTN", "SB") and is_pfr:
            steal_opportunities += 1
            steal_count += 1
        elif position in ("CO", "BTN", "SB"):
            steal_opportunities += 1

        # Position stats
        if position:
            ps = pos_stats[position]
            ps["hands"] += 1
            ps["net_bb"] += net_bb
            if is_vpip:
                ps["vpip"] += 1
            if is_pfr:
                ps["pfr"] += 1

    # Calculate percentages
    def pct(num, den):
        return round(num / den * 100, 1) if den > 0 else 0.0

    af = round(total_bets_raises / max(total_calls, 1), 2)

    stats = {
        "sample_size": total,
        "vpip": pct(vpip_count, total),
        "pfr": pct(pfr_count, total),
        "three_bet": pct(three_bet_count, three_bet_opportunities),
        "fold_to_three_bet": pct(fold_to_3b_count, fold_to_3b_opportunities),
        "cbet_flop": pct(cbet_flop_count, cbet_flop_opportunities),
        "cbet_turn": pct(cbet_turn_count, cbet_turn_opportunities),
        "wtsd": pct(went_to_sd_count, saw_flop_count),
        "won_at_sd": pct(won_at_sd_count, max(went_to_sd_count, 1)),
        "af": af,
        "wwsf": pct(won_without_sd_count, saw_flop_count),
        "steal_pct": pct(steal_count, steal_opportunities),
        "bb_per_100": round(total_net_bb / max(total, 1) * 100, 2),
        "by_position": {
            pos: {
                "hands": d["hands"],
                "vpip": pct(d["vpip"], d["hands"]),
                "pfr": pct(d["pfr"], d["hands"]),
                "bb_per_100": round(d["net_bb"] / max(d["hands"], 1) * 100, 2),
            }
            for pos, d in pos_stats.items()
        },
    }
    return stats
