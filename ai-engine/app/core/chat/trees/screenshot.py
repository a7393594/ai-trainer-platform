"""
截圖預處理樹（場景 2）——structured_review widget → 流轉 hand_analysis 樹。

樹結構：

[L1_review] structured_review widget：Vision 解析後的結構化資料 + 逐欄編輯
  ├ confirm（核對無誤，進分析）→ 葉子 metadata={"flows_to": "hand_analysis"}
  └ retry（自己貼文字重來）→ 葉子 metadata={"flows_to": "free_form"} (rollback 到原始輸入)

葉子完成 → engine 讀 metadata.flows_to 切到對應樹的 root（hand_analysis 樹的 L1）。
"""
from __future__ import annotations

from .base import LeafConfig, Option, Tree, TreeNode, WidgetType


_LEAF_FLOW_TO_HAND_ANALYSIS = LeafConfig(
    persona="coach",
    tools=["analyze_screenshot"],
    kb_query_template=None,
    system_prompt_segment=(
        "葉子配置：截圖確認後流轉。把 structured_review 的編輯結果寫成 hand_record，"
        "回覆「收到這把 X，進入分析」一行 + 觸發 hand_analysis 樹 L1 widget。"
    ),
    metadata={"flows_to": "hand_analysis", "next_root": "L1"},
)

_LEAF_FLOW_TO_FREE_FORM = LeafConfig(
    persona="coach",
    tools=[],
    kb_query_template=None,
    system_prompt_segment=(
        "葉子配置：截圖解析失敗，使用者選擇自己貼文字重來。"
        "回覆「好，請直接把手牌資料貼給我」。"
    ),
    metadata={"flows_to": "free_form"},
)


_NODES: dict[str, TreeNode] = {
    "L1_review": TreeNode(
        id="L1_review",
        widget_type=WidgetType.STRUCTURED_REVIEW,
        question="從截圖解出以下手牌記錄，請核對：",
        preamble_text="我來解讀你的截圖（Claude Vision 解析中）...",
        fields=[
            # 這些 fields 為 placeholder schema；實際 widget 顯示時
            # 由 analyze_screenshot tool 結果動態填值。
            {"name": "hand", "label": "手牌", "type": "text", "editable": True},
            {"name": "position", "label": "位置", "type": "text", "editable": True},
            {"name": "board", "label": "Board", "type": "text", "editable": True},
            {
                "name": "actions",
                "label": "動作流",
                "type": "list",
                "editable": True,
                "item_actions": ["edit", "delete"],
            },
            {"name": "villain_alias", "label": "對手暱稱", "type": "text",
             "editable": True, "default": "對手"},
            {"name": "villain_style", "label": "對手風格", "type": "select",
             "options": [
                 {"value": "TAG", "label": "TAG"},
                 {"value": "LAG", "label": "LAG"},
                 {"value": "Nit", "label": "Nit"},
                 {"value": "Station", "label": "Calling Station"},
                 {"value": "Unknown", "label": "未知 (預設 TAG)"},
             ],
             "default": "TAG",
             "editable": True},
            {"name": "stake", "label": "級別", "type": "text", "editable": True},
        ],
        options=[
            Option(
                id="confirm",
                label="核對無誤，進分析",
                leaf_config=_LEAF_FLOW_TO_HAND_ANALYSIS,
            ),
            Option(
                id="retry",
                label="自己貼文字重來",
                leaf_config=_LEAF_FLOW_TO_FREE_FORM,
            ),
        ],
        blocking=True,
    ),
}


tree = Tree(
    id="screenshot",
    name="截圖預處理",
    description="Vision 解析 → structured_review 核對 → 流轉 hand_analysis 樹",
    root_id="L1_review",
    nodes=_NODES,
)
