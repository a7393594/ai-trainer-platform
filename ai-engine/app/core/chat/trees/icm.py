"""
ICM 賽事樹（場景 5）——form widget 收集型。

樹結構：

[L1_form] form widget：stacks 表 / hero_position / hand / payouts (預設帶入) / opp_calling_range
  └ submit → 葉子 (coach persona + calc_icm + calc_push_fold)

葉子用 chipEV vs $EV 對比 + KB 引用組成回覆。
"""
from __future__ import annotations

from .base import LeafConfig, Option, Tree, TreeNode, WidgetType


_LEAF_ICM = LeafConfig(
    persona="coach",
    tools=["calc_icm", "calc_push_fold", "kb_search", "calc_ev"],
    kb_query_template="ICM theory and push fold for FT bubble",
    system_prompt_segment=(
        "葉子配置：ICM 賽事終盤。並行呼叫 calc_icm 取各位置 $EV，"
        "calc_push_fold 取 Nash push/call ranges。"
        "回覆結構：chipEV vs $EV 對比表 → 結論 → KB 引用 1-2 條。"
        "說明「為什麼 ICM 下你的決定不是 chipEV 最大」這個關鍵直覺。"
    ),
)


_NODES: dict[str, TreeNode] = {
    "L1_form": TreeNode(
        id="L1_form",
        widget_type=WidgetType.FORM,
        question="ICM 場景設定",
        preamble_text="好，我來幫你算 ICM。先把場上資料填一下：",
        fields=[
            {
                "name": "stacks",
                "label": "場上各位置籌碼",
                "type": "table",
                "columns": [
                    {"name": "position", "label": "位置", "type": "text"},
                    {"name": "stack_bb", "label": "Stack (BB)", "type": "number"},
                ],
                "default": [
                    {"position": "BTN", "stack_bb": 30},
                    {"position": "SB", "stack_bb": 25},
                    {"position": "BB", "stack_bb": 20},
                ],
                "required": True,
            },
            {
                "name": "hero_position",
                "label": "你的位置",
                "type": "select",
                "options": [
                    {"value": "BTN", "label": "BTN"},
                    {"value": "SB", "label": "SB"},
                    {"value": "BB", "label": "BB"},
                    {"value": "CO", "label": "CO"},
                ],
                "required": True,
            },
            {
                "name": "hand",
                "label": "你的手牌",
                "type": "text",
                "placeholder": "如 AsKs / 99",
                "required": True,
            },
            {
                "name": "payouts",
                "label": "獎金結構（百分比）",
                "type": "table",
                "columns": [
                    {"name": "place", "label": "名次", "type": "text"},
                    {"name": "pct", "label": "佔總獎金 %", "type": "number"},
                ],
                "default": [
                    {"place": "1st", "pct": 50},
                    {"place": "2nd", "pct": 30},
                    {"place": "3rd", "pct": 20},
                ],
                "required": True,
            },
            {
                "name": "opp_calling_range",
                "label": "對手 calling tightness（鬆度）",
                "type": "select",
                "options": [
                    {"value": "very_tight", "label": "非常緊（top 5%）"},
                    {"value": "tight", "label": "緊（top 12%）"},
                    {"value": "standard", "label": "標準（top 20%）"},
                    {"value": "loose", "label": "鬆（top 30%）"},
                    {"value": "unknown", "label": "我不知道 → 預設「標準」"},
                ],
                "default": "standard",
                "required": True,
            },
        ],
        options=[
            Option(
                id="submit",
                label="算",
                leaf_config=_LEAF_ICM,
            ),
        ],
        blocking=True,
    ),
}


tree = Tree(
    id="icm",
    name="ICM 賽事",
    description="form widget 收集 stacks/hand/payouts/opp_range，葉子並行算 ICM + push/fold",
    root_id="L1_form",
    nodes=_NODES,
)
