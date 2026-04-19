"""
Conversation Summarizer — 長會話自動壓縮

用途：
  - 長對話送入模型前，把早期訊息壓成摘要，降低 context 成本
  - 給 reviewer / PM 看一個 session 的重點

策略：
  - 取 role=user/assistant 的訊息；skip system
  - 如果訊息數 < threshold，直接回傳逐條，不呼叫 LLM
  - 超過時，用 LLM 產出 markdown bullet 摘要
  - 若 persist=True，把摘要寫為 role=system 訊息，metadata.summary=True
"""
from __future__ import annotations

from typing import Optional

from app.core.llm_router.router import chat_completion
from app.db import crud


DEFAULT_THRESHOLD = 20
DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class ConversationSummarizer:

    async def summarize_session(
        self,
        session_id: str,
        threshold: int = DEFAULT_THRESHOLD,
        model: str = DEFAULT_MODEL,
        persist: bool = False,
    ) -> dict:
        session = crud.get_session(session_id)
        if not session:
            return {"status": "error", "message": "Session not found"}

        msgs = crud.list_messages(session_id) or []
        dialogue = [m for m in msgs if m.get("role") in ("user", "assistant")]
        if not dialogue:
            return {"status": "empty", "session_id": session_id, "summary": ""}

        if len(dialogue) < threshold:
            return {
                "status": "below_threshold",
                "session_id": session_id,
                "message_count": len(dialogue),
                "threshold": threshold,
                "summary": None,
            }

        transcript_lines = []
        for m in dialogue:
            role = m.get("role", "?")
            content = (m.get("content") or "").strip().replace("\n", " ")
            transcript_lines.append(f"{role}: {content[:500]}")
        transcript = "\n".join(transcript_lines)

        system_prompt = (
            "你是對話摘要助手。請用繁體中文將以下對話壓成簡潔摘要：\n"
            "  - 用條列式 (Markdown bullets)\n"
            "  - 保留關鍵事實、決策、未解決問題\n"
            "  - 8-15 條之內；不要逐字複述"
        )
        resp = await chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"對話紀錄：\n{transcript[:12000]}"},
            ],
            model=model,
            max_tokens=800,
            temperature=0.2,
        )
        summary = (resp.choices[0].message.content or "").strip()

        saved_id: Optional[str] = None
        if persist and summary:
            try:
                saved = crud.create_message(
                    session_id=session_id,
                    role="system",
                    content=summary,
                    metadata={"summary": True, "message_count": len(dialogue), "model": model},
                )
                saved_id = saved.get("id")
            except Exception as e:  # noqa: BLE001
                saved_id = None
                summary += f"\n\n[WARN] failed to persist: {e}"

        return {
            "status": "summarized",
            "session_id": session_id,
            "message_count": len(dialogue),
            "summary": summary,
            "persisted_message_id": saved_id,
            "model": model,
        }


conversation_summarizer = ConversationSummarizer()
