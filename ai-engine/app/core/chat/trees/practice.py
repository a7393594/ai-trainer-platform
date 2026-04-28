"""
對戰練習樹（場景 4）——form widget 設定 + 隱性 in_game 狀態機。

樹結構：

[L1_setup] form widget：對手原型 / 賽制 / 籌碼 / 位置 / 起始手牌
  └ submit → 葉子 (in_game persona 隱性，由 game_state 觸發)
              tools = [start_practice_session, simulate_opponent_action,
                       get_legal_actions, analyze_completed_hand]

設定後 session.metadata.game_state 會被寫入；後續每輪由 engine 偵測 game_state
切到 in_game persona，本樹本身不再參與。
"""
from __future__ import annotations

from .base import LeafConfig, Option, Tree, TreeNode, WidgetType


_LEAF_PRACTICE_START = LeafConfig(
    persona="in_game",
    tools=[
        "start_practice_session",
        "simulate_opponent_action",
        "get_legal_actions",
        "analyze_completed_hand",
    ],
    kb_query_template=None,
    system_prompt_segment=(
        "葉子配置：對戰練習啟動。呼叫 start_practice_session 初始化 game_state，"
        "把 archetype/stack/format/position/hand 寫入 session.metadata.game_state。"
        "回覆極簡：發牌結果 + 第一個 action 提示 + 快捷按鈕。"
        "後續 in_game 由 engine 偵測 game_state 自動切，不走樹。"
    ),
)


_NODES: dict[str, TreeNode] = {
    "L1_setup": TreeNode(
        id="L1_setup",
        widget_type=WidgetType.FORM,
        question="設定對戰練習",
        preamble_text="好，跟我練一把。先設定一下：",
        fields=[
            {
                "name": "archetype",
                "label": "對手原型",
                "type": "select",
                "options": [
                    {"value": "shark_reg", "label": "鯊魚 reg（GTO 偏 + 微 exploit）"},
                    {"value": "tag", "label": "TAG（緊兇）"},
                    {"value": "lag", "label": "LAG（鬆兇）"},
                    {"value": "nit", "label": "Nit（極緊）"},
                    {"value": "calling_station", "label": "Calling station（鬆被動）"},
                    {"value": "maniac", "label": "Maniac（瘋兇）"},
                ],
                "default": "shark_reg",
                "required": True,
            },
            {
                "name": "format",
                "label": "賽制",
                "type": "select",
                "options": [
                    {"value": "cash", "label": "Cash"},
                    {"value": "mtt", "label": "MTT"},
                    {"value": "spin", "label": "Spin & Go"},
                ],
                "default": "cash",
                "required": True,
            },
            {
                "name": "stake",
                "label": "級別",
                "type": "select",
                "options": [
                    {"value": "NL25", "label": "NL25"},
                    {"value": "NL50", "label": "NL50"},
                    {"value": "NL100", "label": "NL100"},
                    {"value": "NL200", "label": "NL200"},
                    {"value": "NL500", "label": "NL500"},
                ],
                "default": "NL100",
                "required": True,
            },
            {
                "name": "stack_bb",
                "label": "起始籌碼 (BB)",
                "type": "number",
                "default": 100,
                "min": 10,
                "max": 500,
                "required": True,
            },
            {
                "name": "position",
                "label": "你的位置",
                "type": "select",
                "options": [
                    {"value": "BTN", "label": "BTN"},
                    {"value": "SB", "label": "SB"},
                    {"value": "BB", "label": "BB"},
                    {"value": "CO", "label": "CO"},
                    {"value": "MP", "label": "MP"},
                    {"value": "UTG", "label": "UTG"},
                ],
                "default": "BTN",
                "required": True,
            },
            {
                "name": "hand",
                "label": "起始手牌（留空＝隨機發）",
                "type": "text",
                "placeholder": "如 AsKs，留空隨機",
                "required": False,
            },
        ],
        options=[
            Option(
                id="submit",
                label="開始",
                leaf_config=_LEAF_PRACTICE_START,
            ),
        ],
        blocking=True,
    ),
}


tree = Tree(
    id="practice",
    name="對戰練習",
    description="form widget 設定 + 隱性 in_game 狀態機（後續由 game_state 驅動）",
    root_id="L1_setup",
    nodes=_NODES,
)
