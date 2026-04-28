"""
V4 Chat Engine

樹狀 pre-flight + native tool-use loop + atomic transaction + KB v1.1 整合。
取代 V3 (chat_adapter + dag_executor on chat path)。

Public entry: app.core.chat.engine.chat()

設計哲學（從 plan 確定）：
- 「所有功能融入對話內」：手牌分析 / 學習計畫 / 對戰 / ICM 都在 chat 內
- 「確定性 > 流暢性」：複雜場景樹狀 pre-flight，雜聊/概念問答 LLM 自由
- 「智慧起始點」：樹進入位置由 LLM 讀使用者已表達內容判斷
- 「葉子綁定 = 控制權拉回產品」：葉子綁 (persona, tools, kb_query)
- 「我不知道 → 預設 X」永遠 inline 在 widget 選項

V3 仍可用（feature flag use_v4_chat=False）。V4 上線時翻 flag。
"""

from .engine import chat  # noqa: F401
