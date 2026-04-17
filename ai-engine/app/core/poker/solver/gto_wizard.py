"""
GTO Wizard API Client — 查詢 GTO 策略

MVP: 以 LLM 模擬 solver 分析（真實 API 整合留給有 key 後）
生產環境: 呼叫 GTO Wizard 研究者 API (限額 100K hands/月)
"""
import hashlib
import json
from typing import Optional
from app.db.supabase import get_supabase


T_SOLVER = "ait_solver_results"


def compute_spot_hash(game_type: str, positions: list, actions: list, board: list) -> str:
    """Compute deterministic hash for a spot."""
    key = json.dumps({
        "game_type": game_type,
        "positions": sorted(positions) if positions else [],
        "actions": actions[:10],  # Normalize to first 10 actions
        "board": board,
    }, sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def get_cached_result(spot_hash: str) -> Optional[dict]:
    """Check cache for existing solver result."""
    result = (
        get_supabase().table(T_SOLVER).select("*")
        .eq("spot_hash", spot_hash).execute()
    )
    return result.data[0] if result.data else None


def cache_result(spot_hash: str, source: str, params: dict, result: dict) -> dict:
    """Store solver result in cache."""
    data = {
        "spot_hash": spot_hash,
        "solver_source": source,
        "request_params": params,
        "result_json": result,
    }
    try:
        return get_supabase().table(T_SOLVER).insert(data).execute().data[0]
    except Exception:
        # Duplicate — return existing
        return get_cached_result(spot_hash) or data


async def query_gto_strategy(
    hand: dict,
    decision_point: str = "all",
) -> dict:
    """Query solver for GTO strategy at a spot.

    MVP: Uses LLM to generate approximate GTO analysis.
    Production: Replace with actual GTO Wizard API call.

    Returns:
        {
            "source": "llm_approximation" | "gto_wizard" | "cache",
            "strategy": {
                "recommended_action": str,
                "action_frequencies": {"fold": 0.0, "call": 0.3, "raise": 0.7},
                "ev_by_action": {"fold": 0, "call": -2.5, "raise": 3.1},
            },
            "analysis": str,
        }
    """
    # Compute spot hash for caching
    spot_hash = compute_spot_hash(
        game_type=hand.get("game_type", "nlh"),
        positions=[hand.get("hero_position", "")],
        actions=[a.get("action", "") for a in hand.get("actions", [])[:10]],
        board=hand.get("board", []),
    )

    # Check cache
    cached = get_cached_result(spot_hash)
    if cached:
        return {**cached.get("result_json", {}), "source": "cache", "solver_result_id": cached["id"]}

    # MVP: Use LLM for approximate analysis
    from app.core.llm_router.router import chat_completion

    hero_cards = " ".join(hand.get("hero_cards", []))
    board_str = " ".join(hand.get("board", []))
    position = hand.get("hero_position", "?")
    actions_summary = _summarize_actions(hand.get("actions", []))

    prompt = f"""你是一個 GTO solver 分析引擎。分析以下撲克手牌的 GTO 最優策略。

手牌: {hero_cards}
位置: {position}
公共牌: {board_str or '(翻前)'}
動作序列: {actions_summary}
底池大小: {hand.get('pot_size_bb', 0)} bb

請以 JSON 格式回覆，包含:
1. recommended_action: 最佳動作
2. action_frequencies: 各動作的 GTO 頻率 (fold/check/call/bet/raise)
3. ev_by_action: 各動作的 EV (bb)
4. reasoning: 推理過程（50字內）

只回覆 JSON，不要 markdown。"""

    try:
        response = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model="claude-haiku-4-5-20251001",
            temperature=0.1,
            max_tokens=500,
        )
        raw = response.choices[0].message.content or "{}"
        try:
            # Parse JSON
            if raw.startswith("{"):
                strategy = json.loads(raw)
            else:
                start = raw.find("{")
                end = raw.rfind("}") + 1
                strategy = json.loads(raw[start:end])
        except Exception:
            strategy = {"recommended_action": "unknown", "reasoning": raw[:200]}

        result = {"strategy": strategy, "source": "llm_approximation"}

        # Cache it
        solver_row = cache_result(spot_hash, "llm_approximation", {
            "hero_cards": hero_cards, "board": board_str, "position": position,
        }, result)

        return {**result, "solver_result_id": solver_row.get("id")}

    except Exception as e:
        return {
            "source": "error",
            "strategy": {"recommended_action": "unknown"},
            "error": str(e),
        }


def _summarize_actions(actions: list[dict]) -> str:
    """Summarize action sequence for prompt."""
    parts = []
    current_street = ""
    for a in actions:
        street = a.get("street", "")
        if street != current_street:
            current_street = street
            parts.append(f"\n[{street}]")
        player = "Hero" if a.get("is_hero") else a.get("player", "?")[:8]
        act = a.get("action", "?")
        amt = a.get("amount", 0)
        if amt:
            parts.append(f"{player} {act} {amt}bb")
        else:
            parts.append(f"{player} {act}")
    return " ".join(parts)
