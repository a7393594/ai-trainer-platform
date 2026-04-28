"""
學習計畫樹（場景 3）——資料收集型。

樹結構：

[L1] 規劃哪種尺度？
  ├ 整週課表（多日分配，多數）
  ├ 今天 focus（單日 30-90 分鐘）
  ├ 月度 review
  ├ 弱點根除戰
  └ 我不知道 → 預設「整週課表」

[L2_*] 你能花多少時間？（依 L1 動態調整 label）
  ├ < 2h / 2-5h / 5-10h / 10h+
  └ 我不知道 → 預設「中等時段」

[L3_*] 偏重？
  ├ 70/20/10（學習科學標準）
  ├ 偏重弱點 90/10/0
  ├ 偏重新概念 30/60/10
  ├ 偏重複習 20/20/60
  └ 我不知道 → 預設「70/20/10」

每葉子 → coach persona + 多 tool 並行（get_user_stats / get_mastery / get_due_reviews
+ compose_learning_plan + schedule_plan）。
"""
from __future__ import annotations

from .base import LeafConfig, Option, Tree, TreeNode, WidgetType


_LEAF_PLAN = LeafConfig(
    persona="coach",
    tools=[
        "get_user_stats",
        "get_mastery",
        "get_due_reviews",
        "compose_learning_plan",
        "schedule_plan",
        "kb_search",
    ],
    kb_query_template="learning plan template for {scope} with {weight}",
    system_prompt_segment=(
        "葉子配置：學習計畫產生。並行呼叫 get_user_stats / get_mastery / "
        "get_due_reviews 取得學員資料，再 compose_learning_plan 結構化輸出，"
        "用使用者選的 (scope, time_budget, weight) 撐起計畫骨架。"
        "結尾 widget：[存到排程] [從哪一項開始？] [換時間/偏重重新規劃]"
    ),
)


def _l3_node(node_id: str, scope_hint: str) -> TreeNode:
    """L3 節點：偏重比例（每個 scope 都長得一樣，只 hint 改）。"""
    return TreeNode(
        id=node_id,
        widget_type=WidgetType.SINGLE_SELECT,
        question="偏重？",
        preamble_text=f"針對「{scope_hint}」，要怎麼分配時間在弱點/新概念/複習？",
        options=[
            Option(
                id="balanced",
                label="70/20/10（弱點/新概念/複習，學習科學標準）",
                leaf_config=_LEAF_PLAN,
            ),
            Option(
                id="weakness",
                label="偏重弱點補強（90/10/0）",
                leaf_config=_LEAF_PLAN,
            ),
            Option(
                id="new_concept",
                label="偏重新概念探索（30/60/10）",
                leaf_config=_LEAF_PLAN,
            ),
            Option(
                id="review",
                label="偏重複習鞏固（20/20/60）",
                leaf_config=_LEAF_PLAN,
            ),
            Option(
                id="default",
                label="我不知道 → 預設「70/20/10」",
                leaf_config=_LEAF_PLAN,
                is_default=True,
            ),
        ],
    )


def _l2_node(node_id: str, scope_hint: str, default_label: str) -> TreeNode:
    """L2 節點：時間預算（依 L1 scope 動態 label）。"""
    return TreeNode(
        id=node_id,
        widget_type=WidgetType.SINGLE_SELECT,
        question=f"你{scope_hint}能花多少時間？",
        options=[
            Option(id="lite", label="< 2 小時（速成）", next_node_id=f"L3_{node_id[3:]}"),
            Option(id="standard", label="2-5 小時（標準）", next_node_id=f"L3_{node_id[3:]}"),
            Option(id="intense", label="5-10 小時（密集）", next_node_id=f"L3_{node_id[3:]}"),
            Option(id="sprint", label="10+ 小時（衝刺）", next_node_id=f"L3_{node_id[3:]}"),
            Option(
                id="default",
                label=f"我不知道 → 預設「{default_label}」",
                next_node_id=f"L3_{node_id[3:]}",
                is_default=True,
            ),
        ],
    )


_NODES: dict[str, TreeNode] = {
    "L1": TreeNode(
        id="L1",
        widget_type=WidgetType.SINGLE_SELECT,
        question="規劃哪種尺度？",
        preamble_text="好，幫你排訓練前先確認幾件事。",
        options=[
            Option(
                id="weekly",
                label="整週課表（多日分配）",
                next_node_id="L2_weekly",
                description="多數人選這個",
            ),
            Option(
                id="today",
                label="今天 focus（單日 30-90 分鐘）",
                next_node_id="L2_today",
            ),
            Option(
                id="monthly",
                label="月度 review（高階回顧 + 下月方向）",
                next_node_id="L2_monthly",
            ),
            Option(
                id="weakness",
                label="弱點根除戰（針對特定弱點深練 7-14 天）",
                next_node_id="L2_weakness",
            ),
            Option(
                id="default",
                label="我不知道 → 預設「整週課表」",
                next_node_id="L2_weekly",
                is_default=True,
            ),
        ],
    ),
    "L2_weekly": _l2_node("L2_weekly", "這週", "3 小時"),
    "L2_today": _l2_node("L2_today", "今天", "60 分鐘"),
    "L2_monthly": _l2_node("L2_monthly", "這個月", "10 小時"),
    "L2_weakness": _l2_node("L2_weakness", "這 7-14 天", "8 小時"),
    "L3_weekly": _l3_node("L3_weekly", "整週課表"),
    "L3_today": _l3_node("L3_today", "今天 focus"),
    "L3_monthly": _l3_node("L3_monthly", "月度 review"),
    "L3_weakness": _l3_node("L3_weakness", "弱點根除戰"),
}


tree = Tree(
    id="learning_plan",
    name="學習計畫",
    description="資料收集型——收 (粒度, 時間, 偏重) 三層後並行多 tool 生成計畫",
    root_id="L1",
    nodes=_NODES,
)
