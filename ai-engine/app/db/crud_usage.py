"""
CRUD for ait_api_usage table.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.db.supabase import get_supabase

T_USAGE = "ait_api_usage"


def insert_usage(data: dict) -> None:
    """Insert a usage record. Called from fire-and-forget background task."""
    try:
        get_supabase().table(T_USAGE).insert(data).execute()
    except Exception:
        pass  # Never fail the caller


def get_usage_summary(
    credential_id: str,
    days: int = 7,
) -> dict:
    """
    Get aggregated usage stats for a credential over the last N days.
    Returns: { call_count, tokens_in, tokens_out }
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    result = (
        get_supabase()
        .table(T_USAGE)
        .select("id,tokens_in,tokens_out")
        .eq("credential_id", credential_id)
        .gte("created_at", since)
        .execute()
    )
    rows = result.data or []
    return {
        "call_count": len(rows),
        "tokens_in": sum(r.get("tokens_in") or 0 for r in rows),
        "tokens_out": sum(r.get("tokens_out") or 0 for r in rows),
    }


def get_usage_by_day(
    credential_id: str,
    days: int = 7,
) -> list[dict]:
    """
    Get usage grouped by day for the last N days.
    Returns: [{ date: "2026-04-10", calls: 42, tokens_in: 1000, tokens_out: 5000 }, ...]

    Note: Supabase doesn't support GROUP BY via client lib,
    so we fetch raw rows and aggregate in Python.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    result = (
        get_supabase()
        .table(T_USAGE)
        .select("created_at,tokens_in,tokens_out")
        .eq("credential_id", credential_id)
        .gte("created_at", since)
        .order("created_at", desc=False)
        .limit(10000)
        .execute()
    )
    rows = result.data or []

    # Aggregate by date
    by_date: dict[str, dict] = {}
    for r in rows:
        try:
            dt = r["created_at"][:10]  # "2026-04-10T..." -> "2026-04-10"
        except (KeyError, TypeError):
            continue
        if dt not in by_date:
            by_date[dt] = {"date": dt, "calls": 0, "tokens_in": 0, "tokens_out": 0}
        by_date[dt]["calls"] += 1
        by_date[dt]["tokens_in"] += r.get("tokens_in") or 0
        by_date[dt]["tokens_out"] += r.get("tokens_out") or 0

    return sorted(by_date.values(), key=lambda x: x["date"])
