"""
GGPoker Hand History Parser

Key differences from PokerStars:
1. Player names are encrypted (e.g., 'c1a2b3d4'), only Hero visible
2. Each hand is a separate file — need to merge before parsing
3. Rush & Cash has prefix "Poker Hand #RC...", needs conversion
4. Header format: "Poker Hand #TM12345: ..."
"""
import re
from typing import Optional
from app.core.poker.hh_parser.unified_schema import UnifiedHand, Action


class GGPokerParser:

    RE_HEADER = re.compile(
        r"Poker Hand #((?:RC|TM|HD)\d+):\s+"
        r"(Hold'em No Limit|Omaha Pot Limit)"
        r"\s+\(\$?([\d.]+)/\$?([\d.]+)\)"
        r"\s*-\s*(.+)"
    )
    RE_SEAT = re.compile(r"Seat (\d+): (.+?) \(\$?([\d.]+) in chips\)")
    RE_HERO = re.compile(r"Dealt to (.+?) \[(.+?)\]")
    RE_ACTION = re.compile(
        r"^(.+?):\s+(folds|checks|calls|bets|raises|all-in)"
        r"(?:\s+\$?([\d.]+))?"
        r"(?:\s+to\s+\$?([\d.]+))?",
        re.MULTILINE,
    )
    RE_BOARD = re.compile(r"\[(.+?)\]")
    RE_COLLECTED = re.compile(r"^(.+?) collected \$?([\d.]+)", re.MULTILINE)
    RE_TOTAL_POT = re.compile(r"Total pot \$?([\d.]+)")

    def parse(self, raw_text: str) -> list[UnifiedHand]:
        """Parse GGPoker format (may be single or multi-hand)."""
        # Normalize: convert GG format header to be parseable
        text = raw_text.strip()

        # Split by hand boundaries
        hands_raw = re.split(r'(?=Poker Hand #)', text)

        results = []
        for hand_text in hands_raw:
            hand_text = hand_text.strip()
            if not hand_text or "Poker Hand" not in hand_text:
                continue
            try:
                hand = self._parse_single(hand_text)
                if hand:
                    results.append(hand)
            except Exception:
                continue
        return results

    def _parse_single(self, text: str) -> Optional[UnifiedHand]:
        """Parse a single GGPoker hand."""
        m = self.RE_HEADER.search(text)
        if not m:
            return None

        hand_id = m.group(1)
        game_str = m.group(2)
        sb_str, bb_str = m.group(3), m.group(4)
        bb = float(bb_str)
        game_type = "nlh" if "Hold'em" in game_str else "plo"
        stakes = f"{sb_str}/{bb_str}"

        # Table size (default 6 for Rush & Cash)
        table_size = 6
        seats = list(self.RE_SEAT.finditer(text))
        if seats:
            table_size = max(int(s.group(1)) for s in seats)

        players = [
            {"seat": int(s.group(1)), "name": s.group(2),
             "stack_bb": round(float(s.group(3)) / bb, 1) if bb > 0 else 0}
            for s in seats
        ]

        # Hero
        hero, hero_cards = "", []
        hm = self.RE_HERO.search(text)
        if hm:
            hero = hm.group(1)
            hero_cards = hm.group(2).split()

        # Actions (same format as PokerStars after normalization)
        actions = []
        order = 0
        current_street = "preflop"
        for line in text.split("\n"):
            line = line.strip()
            if "*** FLOP ***" in line:
                current_street = "flop"
            elif "*** TURN ***" in line:
                current_street = "turn"
            elif "*** RIVER ***" in line:
                current_street = "river"

            am = self.RE_ACTION.match(line)
            if am:
                player_name = am.group(1).strip()
                action_type = am.group(2).lower()
                amount = float(am.group(3) or am.group(4) or 0)
                amount_bb = round(amount / bb, 1) if bb > 0 else 0

                actions.append(Action(
                    street=current_street,
                    player=player_name,
                    action=action_type,
                    amount=amount_bb,
                    is_hero=(player_name == hero),
                    order=order,
                ))
                order += 1

        # Board
        board = []
        for street_name in ["FLOP", "TURN", "RIVER"]:
            pattern = rf"\*\*\* {street_name} \*\*\* \[(.+?)\]"
            bm = re.search(pattern, text)
            if bm:
                board.extend(bm.group(1).split())

        # Pot
        pot_bb = 0.0
        pm = self.RE_TOTAL_POT.search(text)
        if pm:
            pot_bb = round(float(pm.group(1)) / bb, 1) if bb > 0 else 0

        # Hero result
        hero_net_bb = 0.0
        for cm in self.RE_COLLECTED.finditer(text):
            if cm.group(1).strip() == hero:
                hero_net_bb = round(float(cm.group(2)) / bb, 1) if bb > 0 else 0
        if hero_net_bb == 0:
            invested = sum(a.amount for a in actions if a.is_hero and a.action in ("call", "bet", "raise", "all-in"))
            hero_net_bb = -invested

        fmt = "cash"
        if hand_id.startswith("TM"):
            fmt = "mtt"
        elif hand_id.startswith("RC"):
            fmt = "cash"  # Rush & Cash

        return UnifiedHand(
            hand_id=hand_id,
            source="ggpoker",
            game_type=game_type,
            format=fmt,
            stakes=stakes,
            bb_size=bb,
            table_size=min(table_size, 10),
            hero=hero,
            hero_position="",  # GG doesn't always show position clearly
            hero_cards=hero_cards,
            board=board,
            actions=actions,
            pot_size_bb=pot_bb,
            hero_net_bb=hero_net_bb,
            players=players,
            raw_text=text,
        )
