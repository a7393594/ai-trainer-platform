"""
Unified Hand History Schema — 統一手牌 JSON 格式

所有 parser 輸出都必須符合此結構。
"""
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Action:
    street: str           # preflop, flop, turn, river
    player: str           # seat name or hero
    action: str           # fold, check, call, bet, raise, all-in
    amount: float = 0.0   # in bb
    is_hero: bool = False
    order: int = 0


@dataclass
class UnifiedHand:
    hand_id: str
    source: str              # pokerstars, ggpoker
    game_type: str = "nlh"   # nlh, plo
    format: str = "cash"     # cash, mtt, sng
    stakes: str = ""         # "0.05/0.10", "1/2"
    bb_size: float = 0.0     # big blind in $
    table_size: int = 6
    hero: str = ""
    hero_position: str = ""
    hero_cards: list[str] = field(default_factory=list)
    board: list[str] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    pot_size_bb: float = 0.0
    hero_net_bb: float = 0.0
    players: list[dict] = field(default_factory=list)  # [{name, position, stack_bb}]
    played_at: Optional[str] = None  # ISO timestamp
    raw_text: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["actions"] = [asdict(a) for a in self.actions]
        return d

    def to_db_row(self, user_id: str, project_id: str, batch_id: str = None) -> dict:
        """Convert to ait_hand_histories insert format."""
        return {
            "user_id": user_id,
            "project_id": project_id,
            "batch_id": batch_id,
            "source": self.source,
            "hand_id": self.hand_id,
            "game_type": self.game_type,
            "format": self.format,
            "stakes": self.stakes,
            "table_size": self.table_size,
            "hero_position": self.hero_position,
            "hero_cards": self.hero_cards,
            "board": self.board,
            "actions": [asdict(a) for a in self.actions],
            "pot_size": self.pot_size_bb,
            "hero_net_bb": self.hero_net_bb,
            "parsed_json": self.to_dict(),
            "played_at": self.played_at,
        }
