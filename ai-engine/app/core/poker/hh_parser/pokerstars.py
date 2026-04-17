"""
PokerStars Hand History Parser

Handles:
- PokerStars Hand #xxx: Hold'em No Limit ($X/$Y)
- PokerStars Zoom Hand #xxx
- Standard 7-section format: Header → Seats → Posts → HOLE CARDS → FLOP → TURN → RIVER → SUMMARY
"""
import re
from datetime import datetime
from typing import Optional
from app.core.poker.hh_parser.unified_schema import UnifiedHand, Action


class PokerStarsParser:

    # Regex patterns
    RE_HEADER = re.compile(
        r"PokerStars (?:Zoom )?Hand #(\d+):\s+"
        r"(Hold'em No Limit|Omaha Pot Limit|Hold'em Limit)"
        r"\s+\(\$?([\d.]+)/\$?([\d.]+)"
        r"(?:\s+USD)?\)"
        r"\s*-\s*(.+)"
    )
    RE_TABLE = re.compile(r"Table '([^']+)'\s+(\d+)-max")
    RE_SEAT = re.compile(r"Seat (\d+): (.+?) \(\$?([\d.]+) in chips\)")
    RE_HERO = re.compile(r"Dealt to (.+?) \[(.+?)\]")
    RE_ACTION = re.compile(
        r"^(.+?):\s+(folds|checks|calls|bets|raises|is all-in)"
        r"(?:\s+\$?([\d.]+))?"
        r"(?:\s+to\s+\$?([\d.]+))?",
        re.MULTILINE,
    )
    RE_BOARD = re.compile(r"\[(.+?)\]")
    RE_COLLECTED = re.compile(r"^(.+?) collected \$?([\d.]+)", re.MULTILINE)
    RE_SUMMARY_SEAT = re.compile(
        r"Seat (\d+): (.+?) (?:\((.+?)\) )?(?:folded|showed|mucked|collected|lost)"
    )
    RE_TOTAL_POT = re.compile(r"Total pot \$?([\d.]+)")

    def parse(self, raw_text: str) -> list[UnifiedHand]:
        """Parse multi-hand text into list of UnifiedHand."""
        # Split by hand separator
        hands_raw = re.split(r'\n\n\n+', raw_text.strip())
        if len(hands_raw) <= 1:
            # Try splitting by PokerStars Hand header
            hands_raw = re.split(r'(?=PokerStars (?:Zoom )?Hand #)', raw_text.strip())

        results = []
        for hand_text in hands_raw:
            hand_text = hand_text.strip()
            if not hand_text or "PokerStars" not in hand_text:
                continue
            try:
                hand = self._parse_single(hand_text)
                if hand:
                    results.append(hand)
            except Exception as e:
                # Skip malformed hands
                continue
        return results

    def _parse_single(self, text: str) -> Optional[UnifiedHand]:
        """Parse a single hand."""
        # Header
        m = self.RE_HEADER.search(text)
        if not m:
            return None

        hand_id = m.group(1)
        game_str = m.group(2)
        sb_str, bb_str = m.group(3), m.group(4)
        date_str = m.group(5).strip()

        bb = float(bb_str)
        game_type = "nlh" if "Hold'em No Limit" in game_str else "plo" if "Omaha" in game_str else "lhe"
        stakes = f"{sb_str}/{bb_str}"

        # Parse date
        played_at = None
        try:
            # "2016/07/30 18:48:33 ET"
            dt_match = re.search(r'(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})', date_str)
            if dt_match:
                played_at = datetime.strptime(dt_match.group(1), "%Y/%m/%d %H:%M:%S").isoformat()
        except Exception:
            pass

        # Table
        table_size = 6
        tm = self.RE_TABLE.search(text)
        if tm:
            table_size = int(tm.group(2))

        # Seats
        players = []
        for sm in self.RE_SEAT.finditer(text):
            players.append({
                "seat": int(sm.group(1)),
                "name": sm.group(2),
                "stack_bb": round(float(sm.group(3)) / bb, 1) if bb > 0 else 0,
            })

        # Hero cards
        hero = ""
        hero_cards = []
        hm = self.RE_HERO.search(text)
        if hm:
            hero = hm.group(1)
            hero_cards = hm.group(2).split()

        # Determine hero position from summary
        hero_position = ""
        for sm in self.RE_SUMMARY_SEAT.finditer(text):
            if sm.group(2).strip() == hero and sm.group(3):
                pos = sm.group(3).strip()
                hero_position = self._normalize_position(pos, table_size)
                break

        # Parse streets and actions
        sections = self._split_streets(text)
        actions = []
        order = 0
        for street, section_text in sections.items():
            for am in self.RE_ACTION.finditer(section_text):
                player_name = am.group(1).strip()
                action_type = am.group(2).lower().replace("is all-in", "all-in")
                amount = float(am.group(3) or am.group(4) or 0)
                amount_bb = round(amount / bb, 1) if bb > 0 else 0

                actions.append(Action(
                    street=street,
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

        # Pot and result
        pot_bb = 0.0
        pm = self.RE_TOTAL_POT.search(text)
        if pm:
            pot_bb = round(float(pm.group(1)) / bb, 1) if bb > 0 else 0

        # Hero net result
        hero_net_bb = 0.0
        for cm in self.RE_COLLECTED.finditer(text):
            if cm.group(1).strip() == hero:
                hero_net_bb = round(float(cm.group(2)) / bb, 1) if bb > 0 else 0

        # If hero didn't collect, check if they lost (invested - 0)
        if hero_net_bb == 0:
            hero_invested = sum(a.amount for a in actions if a.is_hero and a.action in ("call", "bet", "raise", "all-in"))
            hero_net_bb = -hero_invested

        # Determine format
        fmt = "cash"
        if "Tournament" in text or "Sit & Go" in text:
            fmt = "mtt"

        hand = UnifiedHand(
            hand_id=hand_id,
            source="pokerstars",
            game_type=game_type,
            format=fmt,
            stakes=stakes,
            bb_size=bb,
            table_size=table_size,
            hero=hero,
            hero_position=hero_position,
            hero_cards=hero_cards,
            board=board,
            actions=actions,
            pot_size_bb=pot_bb,
            hero_net_bb=hero_net_bb,
            players=players,
            played_at=played_at,
            raw_text=text,
        )
        return hand

    def _split_streets(self, text: str) -> dict[str, str]:
        """Split hand text into street sections."""
        streets = {}
        patterns = [
            ("preflop", r"\*\*\* HOLE CARDS \*\*\*(.+?)(?=\*\*\* (?:FLOP|SHOW|SUMM)|$)"),
            ("flop", r"\*\*\* FLOP \*\*\*[^\n]*\n(.+?)(?=\*\*\* (?:TURN|SHOW|SUMM)|$)"),
            ("turn", r"\*\*\* TURN \*\*\*[^\n]*\n(.+?)(?=\*\*\* (?:RIVER|SHOW|SUMM)|$)"),
            ("river", r"\*\*\* RIVER \*\*\*[^\n]*\n(.+?)(?=\*\*\* (?:SHOW|SUMM)|$)"),
        ]
        for street, pattern in patterns:
            m = re.search(pattern, text, re.DOTALL)
            if m:
                streets[street] = m.group(1)
        return streets

    def _normalize_position(self, pos: str, table_size: int) -> str:
        """Normalize position labels."""
        pos = pos.lower().strip()
        mapping = {
            "button": "BTN", "small blind": "SB", "big blind": "BB",
            "under the gun": "UTG", "utg": "UTG", "utg+1": "UTG1",
            "middle position": "MP", "cut-off": "CO", "cutoff": "CO",
            "hijack": "HJ", "lojack": "LJ",
        }
        return mapping.get(pos, pos.upper()[:3])
