"""
Cost Monitor — 成本監控與告警

監控：每日/月成本限額、per-user 成本、模型使用分佈
"""
from datetime import datetime, timedelta, timezone
from app.db.supabase import get_supabase


def get_cost_summary(project_id: str, days: int = 30) -> dict:
    """Get cost breakdown by model for a project."""
    sb = get_supabase()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    usage = (
        sb.table("ait_llm_usage")
        .select("model, cost_usd, input_tokens, output_tokens, created_at")
        .eq("project_id", project_id)
        .gte("created_at", since)
        .execute()
    ).data or []

    total_cost = sum(u.get("cost_usd", 0) or 0 for u in usage)
    total_calls = len(usage)
    total_input = sum(u.get("input_tokens", 0) or 0 for u in usage)
    total_output = sum(u.get("output_tokens", 0) or 0 for u in usage)

    # By model
    by_model: dict[str, dict] = {}
    for u in usage:
        model = u.get("model", "unknown")
        if model not in by_model:
            by_model[model] = {"calls": 0, "cost": 0, "input_tokens": 0, "output_tokens": 0}
        by_model[model]["calls"] += 1
        by_model[model]["cost"] += u.get("cost_usd", 0) or 0
        by_model[model]["input_tokens"] += u.get("input_tokens", 0) or 0
        by_model[model]["output_tokens"] += u.get("output_tokens", 0) or 0

    # By day
    daily: dict[str, float] = {}
    for u in usage:
        day = u.get("created_at", "")[:10]
        daily[day] = daily.get(day, 0) + (u.get("cost_usd", 0) or 0)

    return {
        "period_days": days,
        "total_cost_usd": round(total_cost, 4),
        "total_calls": total_calls,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "avg_cost_per_call": round(total_cost / max(total_calls, 1), 6),
        "by_model": {k: {**v, "cost": round(v["cost"], 4)} for k, v in sorted(by_model.items(), key=lambda x: x[1]["cost"], reverse=True)},
        "daily_cost": dict(sorted(daily.items())),
    }


def check_alerts(project_id: str) -> list[dict]:
    """Check cost alerts for a project."""
    sb = get_supabase()
    alerts = sb.table("ait_cost_alerts").select("*").eq("project_id", project_id).execute().data or []

    triggered = []
    for alert in alerts:
        atype = alert["alert_type"]
        threshold = float(alert["threshold_usd"])

        if atype == "daily_limit":
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            usage = sb.table("ait_llm_usage").select("cost_usd").eq("project_id", project_id).gte("created_at", today).execute().data or []
            current = sum(u.get("cost_usd", 0) or 0 for u in usage)
        elif atype == "monthly_limit":
            month_start = datetime.now(timezone.utc).replace(day=1).isoformat()
            usage = sb.table("ait_llm_usage").select("cost_usd").eq("project_id", project_id).gte("created_at", month_start).execute().data or []
            current = sum(u.get("cost_usd", 0) or 0 for u in usage)
        else:
            current = 0

        is_over = current >= threshold
        if is_over != alert.get("is_triggered", False):
            sb.table("ait_cost_alerts").update({
                "is_triggered": is_over, "current_usd": round(current, 4)
            }).eq("id", alert["id"]).execute()

        if is_over:
            triggered.append({**alert, "current_usd": round(current, 4)})

    return triggered
