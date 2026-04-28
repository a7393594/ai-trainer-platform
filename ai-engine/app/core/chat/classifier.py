"""
Light classifier — 判斷使用者訊息該走哪個場景 + 智慧起始點偵測。

V3 用 capability_rules + intent_classifier (keyword + embedding hybrid)，問題：
  - 短訊息「選擇棄牌」3 字就誤分 capability（threshold 0.3 太鬆）
  - 不看 history 上一則 assistant 是否帶 widget
  - 命中 capability 後直接走假工具 prompt-injection

V4 改為兩層判斷：
  1. **規則先行（zero-cost）**：
     - 任一 attachment 是 image → SCREENSHOT
     - 訊息含 "[手牌紀錄]" → HAND_ANALYSIS
     - session.metadata.game_state 不為 None → PRACTICE（對戰練習中）
  2. **Haiku LLM 8 場景判斷**（規則沒命中時）：
     LEARNING_PLAN / ICM / FSRS_REVIEW / PRACTICE / HAND_ANALYSIS / SCREENSHOT / FREE_FORM

Phase 3：升級為完整 8 場景 + tree_entry_node hint（preflight 會二次精化）。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from app.core.llm_router.router import chat_completion


CLASSIFIER_MODEL = "claude-haiku-4-5-20251001"


class Scenario(str, Enum):
    FREE_FORM = "free_form"          # 雜聊 / 簡訊息 / 概念問答
    HAND_ANALYSIS = "hand_analysis"  # 手牌分析（場景 1）
    LEARNING_PLAN = "learning_plan"  # 學習計畫（場景 3）
    PRACTICE = "practice"            # 對戰練習（場景 4）
    ICM = "icm"                      # ICM 賽事（場景 5）
    FSRS_REVIEW = "fsrs_review"      # FSRS 複習（場景 6）
    SCREENSHOT = "screenshot"        # 截圖預處理（場景 2）


@dataclass
class ClassificationResult:
    scenario: Scenario
    tree_entry_node: Optional[str] = None
    forced_leaf_config: Optional[dict[str, Any]] = None
    reason: str = ""


_LLM_SYSTEM_PROMPT = """\
你是撲克 AI 教練的場景分類器。讀使用者訊息（含可能的歷史摘要），
回 strict JSON，從以下 7 個場景中選一個（外加 free_form 簡訊息/雜聊/概念問答）：

| scenario        | trigger 與範例 |
|-----------------|---------------|
| learning_plan   | 「規劃 / 訓練 / 計畫 / 課表 / 排練」訴求。範例：「幫我規劃這週」/「我想排訓練」/「弱點根除我的 BB defense」 |
| icm             | 「ICM / push fold / FT / 賽事終盤 / SB push 範圍」。範例：「FT 5 人這把要不要 jam」/「ICM 怎麼算」/「這個 push 範圍」 |
| fsrs_review     | 「複習 / 到期 / FSRS / 複習一下」。範例：「來複習一下」/「今天到期」/「FSRS 進度」 |
| practice        | 「練習 / 對戰 / 練一把 / 模擬對手 / 跟我練」。範例：「跟我練 BTN open」/「我想練一把」/「模擬一個 LAG 對手」 |
| hand_analysis   | 描述具體手牌（含手牌符號 8s9s 或 board J♦9♦8♦ 或 [手牌紀錄] 標記）。範例：「我拿 AKo 在 BTN open」/「這把 river 我蓋了」 |
| screenshot      | 訊息含圖片附件（這個由規則判斷，LLM 通常看不到。若文字明確提到「截圖」也算）|
| free_form       | 雜聊 / 致謝 / 純概念問題（"什麼是 polarized"）/ 短訊息 / 不屬上面任一類 |

回 JSON 格式：
{
  "scenario": "learning_plan" | "icm" | "fsrs_review" | "practice" | "hand_analysis" | "screenshot" | "free_form",
  "reason": "一句話說明為何選這個場景",
  "tree_entry_node_hint": "L1" | "L2_xxx" | null  // 可選：使用者已表達多少 context
}

判斷原則：
- 短訊息（< 6 字）+ 無關鍵字 → free_form（謝謝/嗨/嗯/好/收到）
- 純概念問題（"什麼是 X" / "X 是什麼意思"）→ free_form
- 模糊描述（"昨天打牌不順" / "最近狀態不好"）→ free_form
- 同時 hit 多場景時，以最具體者為準（hand_analysis 通常 > free_form）
- tree_entry_node_hint 不確定就回 null（後續 preflight 會精細處理）
"""


async def classify(
    message: str,
    history: list[dict] | None = None,
    attachments: list[dict] | None = None,
    game_state: dict | None = None,
    project_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> ClassificationResult:
    """V4 場景分類。先規則後 LLM。

    Args:
        message:     使用者訊息
        history:     對話歷史（最近 N 則）
        attachments: 附件清單，每筆 {"type": "image" | "file" | ..., "url": ...}
        game_state:  session.metadata.game_state，存在表示對戰練習中
        project_id / session_id: 成本追蹤
    """
    # ---- Rule-based fast path ----
    if attachments:
        for a in attachments:
            if isinstance(a, dict) and a.get("type") == "image":
                return ClassificationResult(
                    scenario=Scenario.SCREENSHOT,
                    reason="image attachment detected",
                )

    if "[手牌紀錄]" in message:
        return ClassificationResult(
            scenario=Scenario.HAND_ANALYSIS,
            reason="hand record marker detected",
        )

    if game_state:
        return ClassificationResult(
            scenario=Scenario.PRACTICE,
            reason="game_state present in session metadata",
        )

    # ---- LLM-based 8-scenario classification ----
    history = history or []
    history_summary = _format_history(history[-3:])

    user_content = (
        f"歷史摘要（最近 3 則）：\n{history_summary}\n\n"
        f"使用者訊息：{message}\n\n"
        f"只回 JSON，不要其他文字。"
    )

    try:
        response = await chat_completion(
            messages=[
                {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            model=CLASSIFIER_MODEL,
            max_tokens=200,
            temperature=0.0,
            project_id=project_id,
            session_id=session_id,
            span_label="classify",
        )
    except Exception as e:
        # LLM 失敗 → 保守回 free_form（main LLM 至少能 handle）
        return ClassificationResult(
            scenario=Scenario.FREE_FORM,
            reason=f"classifier LLM failure, fallback to free_form: {type(e).__name__}",
        )

    text = ""
    try:
        text = (response.choices[0].message.content or "").strip()
    except Exception:
        return ClassificationResult(
            scenario=Scenario.FREE_FORM,
            reason="classifier response missing content",
        )

    return _parse_classification(text)


def _parse_classification(text: str) -> ClassificationResult:
    """從 LLM 回覆抓 JSON 並轉成 ClassificationResult。"""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return ClassificationResult(
            scenario=Scenario.FREE_FORM,
            reason="classifier returned non-JSON text",
        )

    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return ClassificationResult(
            scenario=Scenario.FREE_FORM,
            reason="classifier JSON decode failed",
        )

    scenario_raw = (data.get("scenario") or "free_form").strip().lower()
    try:
        scenario = Scenario(scenario_raw)
    except ValueError:
        scenario = Scenario.FREE_FORM

    entry_hint = data.get("tree_entry_node_hint")
    if isinstance(entry_hint, str):
        entry_hint = entry_hint.strip() or None
    else:
        entry_hint = None

    return ClassificationResult(
        scenario=scenario,
        tree_entry_node=entry_hint,
        reason=str(data.get("reason", "")),
    )


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(無歷史)"
    parts: list[str] = []
    for h in history:
        role = h.get("role", "?")
        content = h.get("content", "")
        if isinstance(content, list):
            text_parts = [c.get("text", "") for c in content if isinstance(c, dict)]
            content = " ".join(p for p in text_parts if p)
        parts.append(f"[{role}] {str(content)[:200]}")
    return "\n".join(parts)
