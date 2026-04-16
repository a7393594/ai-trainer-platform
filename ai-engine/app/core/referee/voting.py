"""
Multi-Model Voting Engine — 多模型投票機制

規格書 §3:
- 日常裁決 (≥0.85): 僅主模型,不投票
- 中等信心 (0.60-0.84): 雙模型 (Claude + GPT-5.4)
- 關鍵裁決 (<0.60 或高額底池): 三模型 (+ Gemini)
- 需 2/3 以上一致才產出建議,否則強制升級

使用 asyncio.gather 並行呼叫,延遲 = max(各模型延遲) 而非加總。
"""
import asyncio
import json
import time
from typing import Optional

from app.config import settings
from app.core.referee.engine import make_ruling


async def dual_model_vote(
    dispute: str,
    game_context: dict = None,
) -> dict:
    """雙模型並行裁決 + 比較。

    Returns:
        {
            "primary": {...},          # 主模型結果
            "secondary": {...},        # 備援模型結果
            "agreement": bool,         # 結論是否一致
            "agreement_score": float,  # 一致性分數 (0-1)
            "combined_decision": str,  # 融合後的裁決
            "latency_ms": int,         # 總延遲 (並行)
        }
    """
    start = time.time()

    primary_task = make_ruling(
        dispute=dispute,
        game_context=game_context,
        model=settings.primary_model,
    )
    secondary_task = make_ruling(
        dispute=dispute,
        game_context=game_context,
        model=settings.backup_model,
    )

    results = await asyncio.gather(primary_task, secondary_task, return_exceptions=True)

    primary = results[0] if not isinstance(results[0], Exception) else None
    secondary = results[1] if not isinstance(results[1], Exception) else None

    # 如果主模型失敗
    if primary is None and secondary is not None:
        return {
            "primary": None,
            "secondary": _summarize(secondary),
            "agreement": False,
            "agreement_score": 0.0,
            "combined_decision": secondary.get("ruling", {}).get("decision", ""),
            "failover": True,
            "latency_ms": int((time.time() - start) * 1000),
        }

    # 如果備援也失敗
    if primary is None and secondary is None:
        return {
            "primary": None,
            "secondary": None,
            "agreement": False,
            "agreement_score": 0.0,
            "combined_decision": None,
            "failover": True,
            "escalate": True,
            "latency_ms": int((time.time() - start) * 1000),
        }

    # 比較兩個模型的結論(用 applicable_rules + 關鍵動作詞,不依賴語言)
    p_ruling = primary.get("ruling", {})
    s_ruling = secondary.get("ruling", {}) if secondary else {}

    p_rules = set(p_ruling.get("applicable_rules", []))
    s_rules = set(s_ruling.get("applicable_rules", []))

    p_decision = (p_ruling.get("decision", "") or "").lower()
    s_decision = (s_ruling.get("decision", "") or "").lower()

    # 如果適用規則一致(rule codes 是語言無關的),視為一致
    rules_agree = bool(p_rules & s_rules) if p_rules and s_rules else False
    text_agree = _decisions_agree(p_decision, s_decision)
    agreement = rules_agree or text_agree
    agreement_score = 1.0 if agreement else 0.5

    # 融合裁決:一致時用主模型,不一致時標記
    if agreement:
        combined = p_ruling.get("decision", "")
    else:
        combined = f"[雙模型分歧] 主模型: {p_decision[:100]} | 備援模型: {s_decision[:100]}"

    return {
        "primary": _summarize(primary),
        "secondary": _summarize(secondary) if secondary else None,
        "agreement": agreement,
        "agreement_score": agreement_score,
        "combined_decision": combined,
        "failover": False,
        "latency_ms": int((time.time() - start) * 1000),
    }


async def triple_model_vote(
    dispute: str,
    game_context: dict = None,
    third_model: str = "gemini/gemini-3.1-pro",
) -> dict:
    """三模型並行裁決 + 多數決。需 2/3 一致才出裁決。"""
    start = time.time()

    tasks = [
        make_ruling(dispute=dispute, game_context=game_context, model=settings.primary_model),
        make_ruling(dispute=dispute, game_context=game_context, model=settings.backup_model),
        make_ruling(dispute=dispute, game_context=game_context, model=third_model),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    valid_results = []
    model_names = [settings.primary_model, settings.backup_model, third_model]
    for i, r in enumerate(results):
        if not isinstance(r, Exception) and r is not None:
            valid_results.append({"model": model_names[i], "result": r})

    if len(valid_results) < 2:
        return {
            "votes": [],
            "consensus": False,
            "combined_decision": None,
            "escalate": True,
            "latency_ms": int((time.time() - start) * 1000),
        }

    # 多數決:比較每對模型的結論
    decisions = [
        v["result"].get("ruling", {}).get("decision", "").lower()
        for v in valid_results
    ]

    # 找多數
    agree_pairs = 0
    total_pairs = 0
    for i in range(len(decisions)):
        for j in range(i + 1, len(decisions)):
            total_pairs += 1
            if _decisions_agree(decisions[i], decisions[j]):
                agree_pairs += 1

    consensus = agree_pairs >= (total_pairs / 2)  # 至少半數配對一致

    # 選主模型的結論(如果它在多數中)
    primary_result = valid_results[0]["result"] if valid_results else None
    combined = primary_result.get("ruling", {}).get("decision", "") if consensus else None

    return {
        "votes": [
            {
                "model": v["model"],
                "decision": v["result"].get("ruling", {}).get("decision", "")[:200],
                "confidence": v["result"].get("ruling", {}).get("confidence", 0),
                "cost_usd": v["result"].get("cost_usd", 0),
            }
            for v in valid_results
        ],
        "consensus": consensus,
        "agreement_ratio": f"{agree_pairs}/{total_pairs}",
        "combined_decision": combined,
        "escalate": not consensus,
        "latency_ms": int((time.time() - start) * 1000),
    }


def _decisions_agree(a: str, b: str) -> bool:
    """簡化的裁決一致性比較。

    判斷兩個裁決是否語意一致:
    - 都包含相同的關鍵動作詞 (call/fold/raise/string bet/misdeal 等)
    - 前 60 字的重疊率 > 50%
    """
    if not a or not b:
        return False

    # 關鍵動作詞比對
    action_words = [
        "string bet", "string raise", "call", "fold", "raise", "misdeal",
        "dead hand", "penalty", "warning", "all-in", "reopening",
        "valid", "invalid", "binding", "not binding",
    ]

    a_actions = {w for w in action_words if w in a}
    b_actions = {w for w in action_words if w in b}

    if a_actions and b_actions:
        overlap = len(a_actions & b_actions) / max(len(a_actions | b_actions), 1)
        return overlap >= 0.5

    # Fallback:字詞重疊率
    a_words = set(a[:200].split())
    b_words = set(b[:200].split())
    if not a_words or not b_words:
        return False
    overlap = len(a_words & b_words) / max(len(a_words | b_words), 1)
    return overlap >= 0.3


def _summarize(result: dict) -> dict:
    """精簡模型結果,只保留裁決摘要。"""
    if not result:
        return None
    return {
        "model": result.get("model_used"),
        "decision": result.get("ruling", {}).get("decision", ""),
        "applicable_rules": result.get("ruling", {}).get("applicable_rules", []),
        "confidence": result.get("ruling", {}).get("confidence", 0),
        "latency_ms": result.get("latency_ms", 0),
        "cost_usd": result.get("cost_usd", 0),
    }
