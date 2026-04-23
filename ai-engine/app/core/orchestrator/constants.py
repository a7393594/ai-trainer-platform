"""Orchestrator 共用常數。

抽出成獨立模組，避免 DAG executor 反向依賴 agent.py 造成循環 import。
"""

# Widget 標記指示 — 附加到所有 system prompt
WIDGET_INSTRUCTION = """

## 互動元件指示（重要）
當你的回覆包含需要使用者做選擇、排序、或回答的問題時，請在回覆最末尾附上一個 JSON 標記，格式如下：

<!--WIDGET:{"type":"single_select","question":"問題文字","options":[{"id":"a","label":"選項A"},{"id":"b","label":"選項B"}]}-->

支援的 widget 類型：
- single_select：單選題（最常用，適合 A/B/C/D 選擇）
- multi_select：多選題（適合「選出所有正確答案」）
- rank：排序題（適合「由強到弱排列」）
- form：簡答題（適合開放式問題，fields: [{"id":"answer","label":"你的答案","type":"text"}]）
- confirm：是/否確認

規則：
- 只有當你主動向使用者提問、出題、或需要使用者做選擇時才使用
- 純講解性質的回覆不需要附加 widget
- JSON 標記必須放在回覆的最後一行
- 標記前的文字會正常顯示給使用者
- 不要在回覆正文中提到這個標記的存在
"""

# Demo user fallback email
DEMO_USER_EMAIL = "demo@ai-trainer.dev"
