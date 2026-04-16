"""
Audit Logger — 不可篡改的裁決審計日誌
每筆裁決自動產生完整 JSON 記錄,寫入 pkr_audit_logs。
"""
import datetime
from app.db import crud


def create_audit_entry(
    ruling_id: str,
    dispute: str,
    game_context: dict,
    ruling_result: dict,
    confidence: dict,
    project_id: str = None,
) -> dict:
    """建立完整審計日誌條目(規格書 §3 定義的結構)。"""
    full_log = {
        "decision_id": ruling_id,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "game_context": game_context or {},
        "dispute_description": dispute,
        "retrieval": {
            "rules_retrieved": ruling_result.get("rules_retrieved", []),
            "effective_rule": ruling_result.get("effective_rule"),
        },
        "model_outputs": {
            "primary": {
                "model": ruling_result.get("model_used"),
                "decision": ruling_result.get("ruling", {}).get("decision"),
                "applicable_rules": ruling_result.get("ruling", {}).get("applicable_rules", []),
                "reasoning": ruling_result.get("ruling", {}).get("reasoning"),
                "subsequent_steps": ruling_result.get("ruling", {}).get("subsequent_steps", []),
                "raw_confidence": ruling_result.get("ruling", {}).get("confidence"),
                "latency_ms": ruling_result.get("latency_ms"),
            },
        },
        "confidence": confidence,
        "outcome": {
            "final_decision": "pending",
            "challenged": False,
            "human_override": None,
        },
        "cost": {
            "tokens": ruling_result.get("tokens", {}),
            "cost_usd": ruling_result.get("cost_usd", 0),
        },
    }

    try:
        return crud.create_audit_log(ruling_id, full_log, project_id=project_id)
    except Exception as e:
        print(f"[WARN] Audit log write failed: {e}")
        return {"error": str(e), "full_log": full_log}
