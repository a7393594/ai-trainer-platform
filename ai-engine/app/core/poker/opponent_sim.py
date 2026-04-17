"""
Opponent Simulator — 對手模擬 (Roleplay)

讓 LLM 扮演特定類型的對手，學生可以練習對抗。
6 種原型：Tight-Aggressive, Loose-Aggressive, Tight-Passive, Loose-Passive, Maniac, Nit
"""
from app.core.llm_router.router import chat_completion

ARCHETYPES = {
    "tag": {
        "name": "Tight-Aggressive Reg",
        "stats": {"vpip": 24, "pfr": 21, "three_bet": 8, "af": 3.0},
        "tendencies": {"bluff_freq": 0.3, "fold_to_aggression": 0.5, "value_bet_thin": True},
        "personality": "冷靜、精準、不留情面。只在有優勢時出手，但一旦出手就很兇。",
    },
    "lag": {
        "name": "Loose-Aggressive Maniac",
        "stats": {"vpip": 35, "pfr": 28, "three_bet": 12, "af": 4.5},
        "tendencies": {"bluff_freq": 0.5, "fold_to_aggression": 0.3, "overbets": True},
        "personality": "瘋狂、愛 bluff、頻繁 overbet。讓對手不舒服就是他的武器。",
    },
    "tp": {
        "name": "Tight-Passive Nit",
        "stats": {"vpip": 15, "pfr": 10, "three_bet": 3, "af": 1.2},
        "tendencies": {"bluff_freq": 0.05, "fold_to_aggression": 0.75, "only_value": True},
        "personality": "極度保守，只在拿到大牌時才大量投入。幾乎不 bluff。",
    },
    "lp": {
        "name": "Loose-Passive Fish",
        "stats": {"vpip": 45, "pfr": 10, "three_bet": 2, "af": 0.8},
        "tendencies": {"bluff_freq": 0.1, "fold_to_aggression": 0.6, "chases_draws": True},
        "personality": "喜歡看牌、愛 call、不太加注。經常追逐聽牌。",
    },
    "maniac": {
        "name": "Ultra-Aggressive Maniac",
        "stats": {"vpip": 50, "pfr": 40, "three_bet": 18, "af": 6.0},
        "tendencies": {"bluff_freq": 0.6, "fold_to_aggression": 0.2, "all_in_light": True},
        "personality": "每手都參與、瘋狂加注。讓人無法分辨他有沒有牌。",
    },
    "nit": {
        "name": "Super Nit",
        "stats": {"vpip": 10, "pfr": 8, "three_bet": 2, "af": 2.0},
        "tendencies": {"bluff_freq": 0.02, "fold_to_aggression": 0.8, "only_premiums": True},
        "personality": "只打 premium hands。如果他加注了，你最好棄牌。",
    },
}


async def simulate_opponent_action(
    archetype: str,
    game_state: dict,
    conversation_history: list[dict] = None,
) -> dict:
    """Generate an opponent action based on archetype.

    Args:
        archetype: key from ARCHETYPES
        game_state: {hero_cards, board, pot_size, action_to, street, ...}
        conversation_history: previous messages for context

    Returns:
        {action, amount, reasoning, archetype_name}
    """
    arch = ARCHETYPES.get(archetype, ARCHETYPES["tag"])

    prompt = f"""你正在扮演一個撲克玩家：{arch['name']}

## 玩家性格
{arch['personality']}

## 統計特徵
- VPIP: {arch['stats']['vpip']}%, PFR: {arch['stats']['pfr']}%
- 3-Bet: {arch['stats']['three_bet']}%, AF: {arch['stats']['af']}
- Bluff 頻率: {arch['tendencies']['bluff_freq']*100:.0f}%

## 當前牌面
- 底池: {game_state.get('pot_size', '?')} bb
- 公共牌: {' '.join(game_state.get('board', [])) or '(翻前)'}
- 街: {game_state.get('street', 'preflop')}
- 需要行動: {game_state.get('action_to', '?')}

以角色身份決定行動。回覆 JSON：
{{"action": "fold/check/call/bet/raise", "amount": 0, "reasoning": "角色思路(30字)"}}
只回覆 JSON。"""

    messages = conversation_history or []
    messages.append({"role": "user", "content": prompt})

    try:
        response = await chat_completion(
            messages=messages,
            model="claude-haiku-4-5-20251001",
            temperature=0.5,
            max_tokens=200,
        )
        import json
        raw = response.choices[0].message.content or "{}"
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            result = json.loads(raw[start:end])
        except Exception:
            result = {"action": "check", "reasoning": raw[:100]}

        result["archetype_name"] = arch["name"]
        return result

    except Exception as e:
        return {"action": "check", "reasoning": f"Error: {e}", "archetype_name": arch["name"]}


def list_archetypes() -> list[dict]:
    """Return all available opponent archetypes."""
    return [
        {"id": k, "name": v["name"], "stats": v["stats"], "personality": v["personality"]}
        for k, v in ARCHETYPES.items()
    ]
