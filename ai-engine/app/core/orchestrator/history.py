"""對話歷史載入 + 自動壓縮。

從 agent.py 抽出成獨立模組，讓 DAG executor 與 orchestrator 共用同一份實作，
避免兩邊行為分歧。

`compression_stats` 是全域 in-memory 計數器，重啟歸零；agent.py 保留
class attribute alias 給 analytics endpoint 讀取。
"""
from typing import Optional

from app.core.llm_router.router import chat_completion
from app.db import crud


HISTORY_COMPRESS_THRESHOLD = 30
HISTORY_KEEP_RECENT = 8

compression_stats: dict = {
    "sessions_compressed": 0,
    "turns_dropped": 0,
    "chars_before": 0,
    "chars_after": 0,
}


async def load_history(session_id: str, exclude_last_user: bool = True) -> list[dict]:
    """載入對話歷史，轉為 LLM 格式。

    若長度超過 `HISTORY_COMPRESS_THRESHOLD`，把最前段壓縮成 system 摘要，
    只保留最後 `HISTORY_KEEP_RECENT` 條原始訊息，降低 token 成本。

    Args:
        exclude_last_user: 排除最後一條 user message（避免與 messages.append 重複）
    """
    messages = crud.list_messages(session_id) or []

    pre_summary: Optional[str] = None
    last_summary_idx = -1
    for idx, m in enumerate(messages):
        if m.get("role") == "system" and (m.get("metadata") or {}).get("summary"):
            pre_summary = m.get("content") or pre_summary
            last_summary_idx = idx

    tail = messages[last_summary_idx + 1:] if last_summary_idx >= 0 else messages
    dialogue = [m for m in tail if m.get("role") in ("user", "assistant")]

    history: list[dict] = []
    if pre_summary:
        history.append({"role": "system", "content": f"[Earlier conversation summary]\n{pre_summary}"})

    if len(dialogue) > HISTORY_COMPRESS_THRESHOLD:
        head = dialogue[: -HISTORY_KEEP_RECENT]
        chars_before = sum(len(m.get("content") or "") for m in head)
        compressed = await compress_history_head(head)
        if compressed:
            history.append({"role": "system", "content": f"[Auto-compressed earlier turns]\n{compressed}"})
            dialogue = dialogue[-HISTORY_KEEP_RECENT:]
            compression_stats["sessions_compressed"] += 1
            compression_stats["turns_dropped"] += len(head)
            compression_stats["chars_before"] += chars_before
            compression_stats["chars_after"] += len(compressed)

    history.extend(
        {"role": m["role"], "content": m["content"]} for m in dialogue
    )
    if exclude_last_user and history and history[-1]["role"] == "user":
        history = history[:-1]
    return history


async def compress_history_head(head: list[dict]) -> Optional[str]:
    """用 summarizer 把較早的歷史壓成幾行。失敗回 None。"""
    if not head:
        return None
    try:
        transcript = "\n".join(
            f"{m.get('role','?')}: {(m.get('content') or '')[:400]}" for m in head
        )
        resp = await chat_completion(
            messages=[
                {"role": "system", "content": (
                    "Compress the following dialogue into 5-10 concise bullet points in the "
                    "original language, preserving key facts, decisions, and unresolved items."
                )},
                {"role": "user", "content": transcript[:10000]},
            ],
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            temperature=0.2,
        )
        return (resp.choices[0].message.content or "").strip() or None
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] compress_history_head failed: {e}")
        return None
