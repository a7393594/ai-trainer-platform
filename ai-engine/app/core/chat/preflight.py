"""
Pre-flight LLM 智慧起始點偵測。

當 classifier 判定要走某棵樹時，preflight 讀使用者訊息 + history，
判斷該從樹的哪個節點開始問——使用者越具體 → 起始點越深。

範例（hand_analysis 樹）：
  - 訊息「這把」/「幫我看」          → 從 root (L1)
  - 訊息「我要 GTO baseline」         → 跳到 L2_solver
  - 訊息「river 我跳不下去」          → 跳到 L3_outcome（並 implied L1=learn / L2=outcome）
  - 訊息「我覺得他 raise 太鬆」        → 跳到 L3_exploit

回 (entry_node_id, implied_choices)；implied_choices 裡的選擇直接套用，
等同使用者已經在那些節點上選過。
"""
from __future__ import annotations

import json
import re
from typing import Optional

from app.core.llm_router.router import chat_completion

from .trees import Tree


PREFLIGHT_MODEL = "claude-haiku-4-5-20251001"
MAX_HISTORY_LOOKBACK = 3


async def detect_entry_point(
    *,
    tree: Tree,
    message: str,
    history: list[dict] | None = None,
    project_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> tuple[str, dict[str, str]]:
    """讀使用者訊息 + history，判斷在 tree 上的哪個節點開始問。

    Args:
        tree: 對話樹物件
        message: 當前使用者訊息
        history: 對話歷史（最近 N 則）
        project_id / session_id: 用於 cost 追蹤 + Pipeline Studio span

    Returns:
        (entry_node_id, implied_choices)
        entry_node_id: 要從這個 node 開始 walk（fallback tree.root_id）
        implied_choices: {node_id: choice_id}，已能從訊息推得的選擇
    """
    history = history or []
    tree_summary = _summarize_tree(tree)
    recent_history = _format_history(history[-MAX_HISTORY_LOOKBACK:])

    system_prompt = (
        "你是對話樹起始點偵測器。\n"
        "給定一棵樹 + 使用者訊息 + 歷史，判斷在樹上的哪個節點開始問。\n\n"
        f"樹 ID：{tree.id}\n"
        f"樹結構：\n{tree_summary}\n\n"
        "回 strict JSON（只回 JSON，不要其他文字）：\n"
        "{\n"
        '  "entry_node_id": "L1" 或 "L2_xxx" 或 "L3_yyy" 或具體節點 id,\n'
        '  "implied_choices": {"L1": "choice_id", "L2_xxx": "choice_id"}\n'
        "}\n\n"
        "判斷原則：\n"
        "- 使用者訊息越具體 → 起始點越深\n"
        "- 訊息只說「這把」/「幫我看」/ 空白 → entry_node_id = root，implied_choices = {}\n"
        "- 訊息含明確訴求（如「river 我跳不下去」/「我要 GTO baseline」/「對手太鬆」）"
        "→ 直接到對應深層節點，並把途中已能推得的選擇填進 implied_choices\n"
        "- entry_node_id 必須是樹中真實存在的 node id\n"
        "- choice_id 必須是該 node options 中真實存在的 id\n"
        "- 不確定時 fallback 到 root，implied_choices 留空 dict"
    )

    user_content = (
        f"歷史最近 {MAX_HISTORY_LOOKBACK} 則：\n{recent_history}\n\n"
        f"當前訊息：{message}"
    )

    try:
        response = await chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            model=PREFLIGHT_MODEL,
            max_tokens=500,
            temperature=0.0,
            project_id=project_id,
            session_id=session_id,
            span_label="preflight_entry",
        )
    except Exception:
        # LLM 失敗 → fallback root
        return tree.root_id, {}

    # 解析 response
    text = ""
    try:
        text = (response.choices[0].message.content or "").strip()
    except Exception:
        return tree.root_id, {}

    return _parse_response(text, tree)


def _parse_response(text: str, tree: Tree) -> tuple[str, dict[str, str]]:
    """從 LLM 回覆中抓 JSON 並驗證 node_id / choice_id 真的存在。"""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return tree.root_id, {}

    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return tree.root_id, {}

    entry_node_id = data.get("entry_node_id") or tree.root_id
    implied_choices = data.get("implied_choices") or {}

    # 驗證 entry_node_id 存在
    if entry_node_id not in tree.nodes:
        entry_node_id = tree.root_id

    # 驗證 implied_choices 每個 (node, choice) pair 都合法
    if not isinstance(implied_choices, dict):
        implied_choices = {}
    else:
        validated: dict[str, str] = {}
        for node_id, choice_id in implied_choices.items():
            if not isinstance(node_id, str) or not isinstance(choice_id, str):
                continue
            if node_id not in tree.nodes:
                continue
            node = tree.nodes[node_id]
            if any(opt.id == choice_id for opt in node.options):
                validated[node_id] = choice_id
        implied_choices = validated

    return entry_node_id, implied_choices


def _summarize_tree(tree: Tree) -> str:
    """產生樹結構的緊湊摘要供 LLM 看。

    格式：
      L1: 你想了解這把的什麼？
        → learn: 我要學東西
          L2_coach: 學什麼面向？
            → outcome: 為什麼贏/輸
              L3_outcome: 聚焦哪一街/決定？
                → flop: Flop lead [LEAF persona=coach]
        → gto: GTO baseline
          L2_solver: 解哪個 spot？
            → preflop: Preflop spot [LEAF persona=solver_lookup]
    """
    lines: list[str] = []
    visited: set[str] = set()

    def walk(node_id: str, depth: int = 0) -> None:
        if node_id in visited:
            return
        visited.add(node_id)
        node = tree.nodes.get(node_id)
        if node is None:
            return
        prefix = "  " * depth
        if node.is_leaf:
            persona = node.leaf_config.persona if node.leaf_config else "?"
            lines.append(f"{prefix}{node_id}: [LEAF persona={persona}]")
            return
        question = node.question or "(no question)"
        lines.append(f"{prefix}{node_id}: {question}")
        for opt in node.options:
            tag_default = " (預設)" if opt.is_default else ""
            if opt.leaf_config:
                persona = opt.leaf_config.persona
                lines.append(
                    f"{prefix}  -> {opt.id}: {opt.label}{tag_default} "
                    f"[LEAF persona={persona}]"
                )
            else:
                lines.append(f"{prefix}  -> {opt.id}: {opt.label}{tag_default}")
                if opt.next_node_id:
                    walk(opt.next_node_id, depth + 2)

    walk(tree.root_id)
    return "\n".join(lines)


def _format_history(history: list[dict]) -> str:
    """把 history 緊湊化供 LLM 看，避免噴大量 tokens。"""
    if not history:
        return "(無歷史)"
    parts: list[str] = []
    for h in history:
        role = h.get("role", "?")
        content = h.get("content", "")
        if isinstance(content, list):
            # tool_use blocks etc. — 取第一個 text
            text_parts = [c.get("text", "") for c in content if isinstance(c, dict)]
            content = " ".join(p for p in text_parts if p)
        parts.append(f"[{role}] {str(content)[:200]}")
    return "\n".join(parts)
