"""Hand History Parser — multi-format parsing engine"""

from app.core.poker.hh_parser.pokerstars import PokerStarsParser
from app.core.poker.hh_parser.ggpoker import GGPokerParser


def detect_and_parse(raw_text: str) -> list[dict]:
    """Auto-detect format and parse hand histories."""
    text = raw_text.strip()

    if "PokerStars Hand" in text or "PokerStars Zoom Hand" in text:
        return PokerStarsParser().parse(text)
    elif "Poker Hand #RC" in text or "Poker Hand #TM" in text or "GGPoker" in text:
        return GGPokerParser().parse(text)
    else:
        # Try PokerStars format as default
        try:
            result = PokerStarsParser().parse(text)
            if result:
                return result
        except Exception:
            pass
        raise ValueError("Unrecognized hand history format")
