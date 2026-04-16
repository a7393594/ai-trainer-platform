"""
Confidence Scoring — 多方法融合信心分數
公式: calibrated = 0.4 × verbalized + 0.3 × consistency + 0.3 × cross_model
"""
from app.config import settings
from app.core.referee.engine import make_ruling


async def compute_confidence(
    ruling_result: dict,
    dispute: str,
    game_context: dict = None,
    enable_consistency: bool = True,
    enable_cross_model: bool = False,
) -> dict:
    """計算多方法融合信心分數。

    Args:
        ruling_result: make_ruling() 的回傳值
        dispute: 原始爭議描述
        game_context: 遊戲狀態
        enable_consistency: 是否啟用自我一致性抽樣
        enable_cross_model: 是否啟用跨模型驗證

    Returns:
        {
            "verbalized": float,        # LLM 自述信心 (0-1)
            "consistency_score": float,  # 自我一致性 (0-1)
            "cross_model_agreement": float,  # 跨模型一致 (0-1)
            "calibrated_final": float,  # 最終校準分數 (0-1)
            "routing_mode": str,        # 'A','B','C','escalated'
            "details": {...},
        }
    """
    primary_ruling = ruling_result.get("ruling", {})
    verbalized = primary_ruling.get("confidence", 0.5)
    if isinstance(verbalized, (int, float)):
        verbalized = max(0.0, min(1.0, float(verbalized)))
    else:
        verbalized = 0.5

    # Mode A: 純查表的結果,信心固定高
    if ruling_result.get("mode") == "A":
        return {
            "verbalized": 0.95,
            "consistency_score": 1.0,
            "cross_model_agreement": 1.0,
            "calibrated_final": 0.95,
            "routing_mode": "A",
            "details": {"lookup_result": True},
        }

    consistency_score = 1.0
    consistency_details = []

    # 自我一致性抽樣
    if enable_consistency and settings.consistency_samples > 1:
        primary_decision = primary_ruling.get("decision", "")
        matches = 0
        for _ in range(settings.consistency_samples - 1):
            try:
                sample = await make_ruling(
                    dispute=dispute,
                    game_context=game_context,
                    model=ruling_result.get("model_used", settings.primary_model),
                    temperature=settings.voting_temperature,
                )
                sample_decision = sample.get("ruling", {}).get("decision", "")
                # 簡化比較:取前 50 字看是否一致
                if sample_decision[:50].lower() == primary_decision[:50].lower():
                    matches += 1
                consistency_details.append({
                    "decision_preview": sample_decision[:80],
                    "matches": sample_decision[:50].lower() == primary_decision[:50].lower(),
                })
            except Exception:
                pass
        total_samples = settings.consistency_samples
        consistency_score = (matches + 1) / total_samples  # +1 for the original

    cross_model_score = 1.0
    cross_model_details = []

    # 跨模型驗證
    if enable_cross_model and settings.backup_model:
        try:
            backup_result = await make_ruling(
                dispute=dispute,
                game_context=game_context,
                model=settings.backup_model,
                temperature=settings.voting_temperature,
            )
            backup_decision = backup_result.get("ruling", {}).get("decision", "")
            primary_decision = primary_ruling.get("decision", "")
            # 簡化比較
            if backup_decision[:50].lower() == primary_decision[:50].lower():
                cross_model_score = 1.0
            else:
                cross_model_score = 0.5
            cross_model_details.append({
                "model": settings.backup_model,
                "decision_preview": backup_decision[:80],
                "agrees": cross_model_score >= 0.8,
            })
        except Exception:
            cross_model_score = 0.7  # 備援模型失敗,中間分

    # 融合分數
    calibrated = (
        0.4 * verbalized +
        0.3 * consistency_score +
        0.3 * cross_model_score
    )

    # 路由決策
    if calibrated >= settings.auto_decide_threshold:
        mode = "B"  # 可爭議模式
    elif calibrated >= settings.human_confirm_threshold:
        mode = "C"  # 輔助荷官模式
    else:
        mode = "escalated"  # 強制升級

    # 強制升級觸發條件
    if game_context:
        pot = game_context.get("pot_size", 0)
        avg_pot = game_context.get("avg_pot_size", pot)
        if pot > avg_pot * 10:
            mode = "escalated"
        if game_context.get("is_bubble"):
            mode = "C" if mode == "B" else mode

    return {
        "verbalized": round(verbalized, 3),
        "consistency_score": round(consistency_score, 3),
        "cross_model_agreement": round(cross_model_score, 3),
        "calibrated_final": round(calibrated, 3),
        "routing_mode": mode,
        "details": {
            "consistency_samples": consistency_details,
            "cross_model": cross_model_details,
        },
    }
