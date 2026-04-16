"""
Rule Resolver — 規則疊加覆寫引擎
類似 CSS 層疊的優先權模型:多層規則按 priority 排序,高優先權覆寫低優先權。
"""
from typing import Optional


def resolve_rules(retrieved_rules: list[dict]) -> dict:
    """從檢索到的規則清單中,解析出最終有效規則。

    Args:
        retrieved_rules: hybrid_search() 回傳的規則清單,每條含 priority、rule_code、override_targets

    Returns:
        {
            "effective_rule": {...},          # 最終適用的規則
            "overridden_rules": [...],        # 被覆寫的規則(供參考)
            "all_applicable_rules": [...],    # 所有相關規則(含覆寫)
            "requires_judgment": bool,        # 是否需要 LLM 推理
            "conflict_detected": bool,        # 是否偵測到規則衝突
        }
    """
    if not retrieved_rules:
        return {
            "effective_rule": None,
            "overridden_rules": [],
            "all_applicable_rules": [],
            "requires_judgment": True,  # 找不到規則 → 需要推理
            "conflict_detected": False,
        }

    # 按 priority 排序(1 = 最高優先權)
    sorted_rules = sorted(
        retrieved_rules,
        key=lambda r: r.get("priority", 99),
    )

    # 建立覆寫映射
    overridden_codes: set[str] = set()
    for rule in sorted_rules:
        targets = rule.get("override_targets") or []
        for t in targets:
            overridden_codes.add(t)

    # 過濾掉被覆寫的規則
    active_rules = [
        r for r in sorted_rules
        if r.get("rule_code") not in overridden_codes
    ]
    overridden_rules = [
        r for r in sorted_rules
        if r.get("rule_code") in overridden_codes
    ]

    # 最高優先權的 active 規則 = effective rule
    effective = active_rules[0] if active_rules else sorted_rules[0]

    # 偵測衝突:多條 active 規則的結論是否可能不同
    # 簡化判斷:如果有 ≥2 條不同 source 的 active 規則,標記為潛在衝突
    unique_sources = set(r.get("source_id") for r in active_rules if r.get("source_id"))
    conflict = len(unique_sources) > 1

    # 是否需要推理
    requires_judgment = effective.get("requires_judgment", False) or conflict

    return {
        "effective_rule": effective,
        "overridden_rules": overridden_rules,
        "all_applicable_rules": sorted_rules,
        "requires_judgment": requires_judgment,
        "conflict_detected": conflict,
    }
