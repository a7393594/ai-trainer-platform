"""
Session Reporter — 每次教練 session 結束時的總結卡

自動產生：
- 對話時長、訊息數
- 討論到的概念
- XP 獲得
- 關鍵 takeaways
"""
from datetime import datetime, timezone
from app.db.supabase import get_supabase
from app.db import crud


async def generate_session_report(session_id: str, user_id: str, project_id: str) -> dict:
    """Generate a session summary report.

    Returns: report_json dict
    """
    sb = get_supabase()

    # Load session info
    session = sb.table("ait_training_sessions").select("*").eq("id", session_id).execute()
    if not session.data:
        return {"error": "Session not found"}
    session_data = session.data[0]

    # Load messages
    messages = crud.list_messages(session_id)
    user_msgs = [m for m in messages if m["role"] == "user"]
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]

    # Calculate duration
    started = session_data.get("started_at", "")
    ended = session_data.get("ended_at") or datetime.now(timezone.utc).isoformat()

    try:
        start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(ended.replace("Z", "+00:00"))
        duration_mins = int((end_dt - start_dt).total_seconds() / 60)
    except Exception:
        duration_mins = 0

    # Extract concepts mentioned (simple keyword matching)
    all_text = " ".join(m.get("content", "") for m in messages)
    concept_keywords = {
        "preflop": ["開牌", "open", "3-bet", "3bet", "position", "位置"],
        "postflop": ["c-bet", "cbet", "check-raise", "SPR", "barrel", "river"],
        "tournament": ["ICM", "bubble", "泡沫", "push/fold", "錦標賽"],
        "mental": ["tilt", "傾斜", "variance", "方差", "紀律"],
        "bankroll": ["bankroll", "資金", "buy-in"],
    }
    concepts_covered = []
    for cat, keywords in concept_keywords.items():
        if any(kw.lower() in all_text.lower() for kw in keywords):
            concepts_covered.append(cat)

    # Simple XP calculation
    xp_earned = len(user_msgs) * 5 + len(concepts_covered) * 10

    report = {
        "duration_mins": duration_mins,
        "messages_count": len(messages),
        "user_messages": len(user_msgs),
        "assistant_messages": len(assistant_msgs),
        "concepts_covered": concepts_covered,
        "xp_earned": xp_earned,
        "key_takeaways": [],  # Could be LLM-generated in future
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Save to DB
    try:
        sb.table("ait_session_reports").insert({
            "session_id": session_id,
            "user_id": user_id,
            "project_id": project_id,
            "report_json": report,
        }).execute()
    except Exception:
        pass

    return report
