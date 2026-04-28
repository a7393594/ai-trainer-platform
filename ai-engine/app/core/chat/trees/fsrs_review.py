"""
FSRS 複習樹（場景 6）——流轉型，題目順序由 due 自動排。

樹結構：

[L1_start] single_select widget：「開始複習」按鈕
  └ start → 葉子 (coach + get_due_reviews + record_fsrs_response)

葉子先 get_due_reviews 取 due 題目，每則回覆顯示一題 + 4 個評分按鈕
（簡單/普通/難/不會），使用者點完後再 record_fsrs_response 更新 mastery
與下次到期時間，繼續下一題直到全部完成。
"""
from __future__ import annotations

from .base import LeafConfig, Option, Tree, TreeNode, WidgetType


_LEAF_FSRS = LeafConfig(
    persona="coach",
    tools=["get_due_reviews", "record_fsrs_response", "kb_search"],
    kb_query_template="FSRS spaced repetition concept review",
    system_prompt_segment=(
        "葉子配置：FSRS 複習。先 get_due_reviews 取出 due 陣列，"
        "依序一次出一題（widget single_select 4 選項：簡單/普通/難/不會）。"
        "使用者答完一題 → record_fsrs_response 更新，繼續下一題。"
        "全部完成後輸出本輪統計（n 題複習、x 題標難、下次最早到期 yyyy-mm-dd）。"
    ),
)


_NODES: dict[str, TreeNode] = {
    "L1_start": TreeNode(
        id="L1_start",
        widget_type=WidgetType.SINGLE_SELECT,
        question="準備好開始複習嗎？",
        preamble_text="我已經拿到你今天到期的概念清單。",
        options=[
            Option(
                id="start",
                label="開始複習",
                leaf_config=_LEAF_FSRS,
            ),
            Option(
                id="see_list",
                label="先看看清單",
                leaf_config=_LEAF_FSRS,
                description="只列出 due 概念不評分",
            ),
            Option(
                id="default",
                label="我不知道 → 預設「開始複習」",
                leaf_config=_LEAF_FSRS,
                is_default=True,
            ),
        ],
    ),
}


tree = Tree(
    id="fsrs_review",
    name="FSRS 複習",
    description="流轉型——一題一題評分到結束，自動更新 mastery + 下次到期",
    root_id="L1_start",
    nodes=_NODES,
)
