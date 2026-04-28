"""
V4 對話樹 registry。

集合 6 棵樹的定義，提供 get_tree(scenario) lookup 給 engine 使用。

scenario 名稱與 classifier.Scenario enum 對齊（除了 free_form）：
  - hand_analysis
  - learning_plan
  - practice
  - icm
  - fsrs_review
  - screenshot
"""
from __future__ import annotations

from .base import LeafConfig, Option, Tree, TreeNode, WidgetType, walk_tree
from .fsrs_review import tree as fsrs_review_tree
from .hand_analysis import tree as hand_analysis_tree
from .icm import tree as icm_tree
from .learning_plan import tree as learning_plan_tree
from .practice import tree as practice_tree
from .screenshot import tree as screenshot_tree


TREES: dict[str, Tree] = {
    "hand_analysis": hand_analysis_tree,
    "learning_plan": learning_plan_tree,
    "practice": practice_tree,
    "icm": icm_tree,
    "fsrs_review": fsrs_review_tree,
    "screenshot": screenshot_tree,
}


def get_tree(scenario: str) -> Tree:
    if scenario not in TREES:
        raise KeyError(
            f"Unknown scenario: {scenario}. "
            f"Available: {list(TREES.keys())}"
        )
    return TREES[scenario]


__all__ = [
    "TREES",
    "get_tree",
    "Tree",
    "TreeNode",
    "Option",
    "LeafConfig",
    "WidgetType",
    "walk_tree",
]
