"""把 retrieved KB chunks 注入 system prompt。

設計重點：
- KB chunks 帶明確邊界（### 知識庫參考），跟對話歷史明顯區隔
- 每個 chunk 帶 `citation` (kb://{id}) 標記，方便 LLM 引用 + 前端 link 還原
- profile 也可選注入（學員背景）
"""
from __future__ import annotations

from typing import Optional

from .schema import KBChunk


def inject_kb_context(
    *,
    base_system: str,
    persona_block: str,
    profile: Optional[dict] = None,
    kb_chunks: Optional[list[KBChunk]] = None,
) -> str:
    """組成完整 system prompt。

    Args:
        base_system: 基礎 system prompt（chat engine 的 default）
        persona_block: persona 描述（教練語氣、限制等）
        profile: 學員 profile dict（可選）— 注入個人化背景
        kb_chunks: 從 KB retriever 拿到的 chunks（可選）

    結構：
        {base_system}

        {persona_block}

        ### 知識庫參考（不是對話歷史，僅供查證）
        [kb://...] (level X) Title
        ...content_text...

        ### 學員 Profile
        - key: value
    """
    parts: list[str] = [base_system, "", persona_block, ""]

    if kb_chunks:
        parts.append("### 知識庫參考（不是對話歷史，僅供查證）")
        parts.append("")
        for chunk in kb_chunks:
            parts.append(f"[{chunk.citation}] (level {chunk.level}) {chunk.title}")
            parts.append(chunk.content_text)
            parts.append("")

    if profile:
        parts.append("### 學員 Profile")
        for k, v in profile.items():
            parts.append(f"- {k}: {v}")
        parts.append("")

    return "\n".join(parts)
