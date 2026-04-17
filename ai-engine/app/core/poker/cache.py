"""
Response Cache — LLM 回應快取層

目標 40% 命中率：對同等級學生的常見問題重用回答。
Cache key = hash(system_prompt_hash, last_2_user_messages, model, student_level)
TTL = 24 hours
"""
import hashlib
import json
from typing import Optional
from datetime import datetime, timedelta, timezone
from app.db.supabase import get_supabase

T_CACHE = "ait_cache_entries"


def compute_cache_key(
    system_prompt: str,
    recent_messages: list[dict],
    model: str,
    student_level: str = "L1",
) -> str:
    """Compute deterministic cache key."""
    prompt_hash = hashlib.sha256(system_prompt.encode()).hexdigest()[:8]
    # Use last 2 user messages as key component
    user_msgs = [m["content"][:200] for m in recent_messages if m.get("role") == "user"][-2:]
    key_data = json.dumps({
        "prompt_hash": prompt_hash,
        "user_msgs": user_msgs,
        "model": model,
        "level": student_level,
    }, sort_keys=True)
    return hashlib.sha256(key_data.encode()).hexdigest()[:24]


def get_cached_response(cache_key: str) -> Optional[str]:
    """Look up cached response. Returns response text or None."""
    sb = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    result = (
        sb.table(T_CACHE).select("id, response_text, expires_at")
        .eq("cache_key", cache_key)
        .execute()
    )

    if not result.data:
        return None

    entry = result.data[0]
    expires = entry.get("expires_at")
    if expires and expires < now:
        # Expired — delete and return None
        sb.table(T_CACHE).delete().eq("id", entry["id"]).execute()
        return None

    # Hit — increment counter
    sb.table(T_CACHE).update({"hit_count": entry.get("hit_count", 0) + 1}).eq("id", entry["id"]).execute()
    return entry["response_text"]


def set_cached_response(
    cache_key: str,
    model: str,
    response_text: str,
    ttl_hours: int = 24,
    metadata: dict = None,
) -> None:
    """Store response in cache."""
    sb = get_supabase()
    expires = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat()

    try:
        sb.table(T_CACHE).insert({
            "cache_key": cache_key,
            "model": model,
            "response_text": response_text,
            "metadata": metadata or {},
            "expires_at": expires,
        }).execute()
    except Exception:
        # Duplicate key — update instead
        sb.table(T_CACHE).update({
            "response_text": response_text,
            "expires_at": expires,
        }).eq("cache_key", cache_key).execute()


def get_cache_stats() -> dict:
    """Return cache performance stats."""
    sb = get_supabase()
    all_entries = sb.table(T_CACHE).select("hit_count, created_at").execute().data or []
    total = len(all_entries)
    total_hits = sum(e.get("hit_count", 0) for e in all_entries)
    return {
        "total_entries": total,
        "total_hits": total_hits,
        "avg_hits_per_entry": round(total_hits / max(total, 1), 1),
    }
