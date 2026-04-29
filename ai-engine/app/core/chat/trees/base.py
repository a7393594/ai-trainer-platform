"""
Tree base classes — TreeNode, LeafConfig, Option, Tree.

V4 對話樹的核心資料結構。每棵樹由 Tree 物件持有 nodes dict，
節點之間靠 Option.next_node_id / Option.leaf_config 串接：

  - 非葉子節點（widget 問題）：options 帶 next_node_id 指向下一節點
  - 葉子節點：is_leaf=True，leaf_config 綁定 (persona, tools, kb_query, system_prompt_segment)
  - 「我不知道 → 預設 X」：Option.is_default=True，UI 醒目標示

advance() 從某節點走某選項，回下一節點（葉子時 wrap 成合成 leaf TreeNode）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class WidgetType(str, Enum):
    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"
    FORM = "form"
    STRUCTURED_REVIEW = "structured_review"
    NUMBER_INPUT = "number_input"


@dataclass
class LeafConfig:
    """葉子綁定的執行配置——main LLM 呼叫前所有變數已敲定。

    persona:                 "coach" / "solver_lookup" / "quick_take" / "in_game"
    tools:                   tool name 清單，將從 registry 取出
    kb_query_template:       例 "EV fundamentals on {street}"，{}slot 由 walking 路徑填入
    system_prompt_segment:   葉子特化的 prompt 段落
    metadata:                例 {"flows_to": "hand_analysis"} 表示完成後流轉到另一棵樹
    """
    persona: str
    tools: list[str]
    kb_query_template: Optional[str] = None
    system_prompt_segment: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Option:
    """樹節點的一個選項。

    非葉子選項：next_node_id 指向下一節點
    葉子選項：leaf_config 直接綁葉子配置（不需要 next_node_id）
    is_default=True：「我不知道 → 預設 X」常駐選項
    """
    id: str
    label: str
    next_node_id: Optional[str] = None
    leaf_config: Optional[LeafConfig] = None
    is_default: bool = False
    description: Optional[str] = None


@dataclass
class TreeNode:
    """樹節點——可能是 widget 問題（非葉子）或葉子（綁 leaf_config）。

    widget_type 決定 UI 渲染方式：single_select / multi_select / form 等
    options：    *_select 類用
    fields：     form / structured_review / number_input 用
    blocking：   widget 是否強制等使用者答（預設 True，free-form 場景才會 False）
    """
    id: str
    widget_type: WidgetType
    question: Optional[str] = None
    preamble_text: Optional[str] = None
    options: list[Option] = field(default_factory=list)
    fields: list[dict] = field(default_factory=list)
    is_leaf: bool = False
    leaf_config: Optional[LeafConfig] = None
    blocking: bool = True

    def to_widget(self) -> dict:
        """Convert to widget dict suitable for present_widget tool result.

        Key naming aligns with c-end Widget TypeScript interface:
            type / question / options / fields / blocking / tree_id / node_id
        We emit BOTH `type` and `widget_type` for backward compat with anything
        reading the older snake_case key, but front-end Widget renderer reads `type`.
        """
        type_str = self.widget_type.value
        widget: dict[str, Any] = {
            "type": type_str,             # ← c-end Widget.type 期望這個 key
            "widget_type": type_str,      # ← legacy / submission echo
            "node_id": self.id,
            "blocking": self.blocking,
        }
        if self.question:
            widget["question"] = self.question
        if self.preamble_text:
            widget["preamble_text"] = self.preamble_text
        if self.options:
            widget["options"] = [
                {
                    "id": o.id,
                    "label": o.label,
                    "is_default": o.is_default,
                    **({"description": o.description} if o.description else {}),
                }
                for o in self.options
            ]
        if self.fields:
            widget["fields"] = list(self.fields)
        return widget


@dataclass
class Tree:
    """一棵對話樹。

    id:       場景 key (與 classifier scenario enum 對齊)
    name:     人類可讀名稱
    root_id:  起始節點 id（智慧起始點偵測失敗時 fallback）
    nodes:    node_id → TreeNode
    """
    id: str
    name: str
    description: str
    root_id: str
    nodes: dict[str, TreeNode]

    def get_node(self, node_id: str) -> TreeNode:
        return self.nodes[node_id]

    def advance(self, current_node_id: str, choice_id: str) -> TreeNode:
        """從某 node 走某 choice，回下一 node（葉子或下層 widget）。"""
        node = self.nodes[current_node_id]
        for opt in node.options:
            if opt.id == choice_id:
                if opt.leaf_config:
                    # 直接是葉子 — wrap 一個合成 leaf TreeNode 回傳
                    return TreeNode(
                        id=f"leaf_{node.id}_{choice_id}",
                        widget_type=node.widget_type,
                        is_leaf=True,
                        leaf_config=opt.leaf_config,
                    )
                if opt.next_node_id:
                    return self.nodes[opt.next_node_id]
        raise ValueError(f"Invalid choice {choice_id} on node {current_node_id}")


def walk_tree(tree: Tree, choices: dict[str, str]) -> TreeNode:
    """從 root 連續走 choices，回終點 node（葉子或第一個還沒 choice 的 node）。

    choices: {node_id: choice_id}
    """
    current = tree.get_node(tree.root_id)
    while current.id in choices and not current.is_leaf:
        current = tree.advance(current.id, choices[current.id])
    return current
