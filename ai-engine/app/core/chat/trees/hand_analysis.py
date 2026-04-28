"""
手牌分析樹（場景 1）——意圖收斂型。

樹結構（嚴格對齊 plan「6 個複雜場景的完整模擬」section）：

[L1] 你想了解這把的什麼？
  ├ 我要學東西 (Coach)
  │   [L2_coach] 學什麼面向？
  │     ├ 為什麼贏/輸（結果論）→ [L3_outcome] 聚焦哪一街/決定？→ 葉子 (coach + ev/equity)
  │     ├ GTO 概念（理論論）→ [L3_gto_concept] 哪個概念？→ 葉子 (coach + kb_search)
  │     └ 對手心理 / Exploit → [L3_exploit] 哪個對手行為？→ 葉子 (coach + opponent_modeling)
  ├ GTO baseline (Solver) → [L2_solver] 解哪個 spot？→ 葉子 (solver_lookup + calc_gto_solution)
  └ 快評 (Quick) → 葉子 (quick_take + calc_equity)
"""
from __future__ import annotations

from .base import LeafConfig, Option, Tree, TreeNode, WidgetType


_LEAF_COACH_OUTCOME = LeafConfig(
    persona="coach",
    tools=["calc_equity", "calc_ev", "calc_gto_solution", "kb_search"],
    kb_query_template="EV pot odds for {street} decision",
    system_prompt_segment=(
        "葉子配置：結果論教學。聚焦使用者選擇的特定街/決定，"
        "用 calc_equity + calc_ev 算出 break-even 與實際 EV，"
        "對比 GTO solver 結果說明偏離點。結尾學習點 1-2 行。"
    ),
)

_LEAF_COACH_GTO_CONCEPT = LeafConfig(
    persona="coach",
    tools=["kb_search", "calc_gto_solution"],
    kb_query_template="{concept_topic}",
    system_prompt_segment=(
        "葉子配置：GTO 概念教學。先 kb_search 取理論基礎，"
        "再用 calc_gto_solution 在當前 spot 印證概念。"
        "範例 → 規則 → 反例的順序展開。"
    ),
)

_LEAF_COACH_EXPLOIT = LeafConfig(
    persona="coach",
    tools=["opponent_modeling", "kb_search", "calc_ev"],
    kb_query_template="exploitative play vs {style}",
    system_prompt_segment=(
        "葉子配置：對手心理 / Exploit。先 opponent_modeling 取對手 archetype/leak，"
        "對比 GTO baseline 找剝削路徑，計算 exploit EV vs GTO EV 差。"
    ),
)

_LEAF_SOLVER_GTO = LeafConfig(
    persona="solver_lookup",
    tools=["calc_gto_solution", "calc_equity"],
    kb_query_template=None,
    system_prompt_segment=(
        "葉子配置：單一 spot 純 GTO solver 結果。\n"
        "**必須**呼叫一次 calc_gto_solution(spot) 取得精確 mixed strategy / "
        "frequencies / EVs，不要從歷史推測或腦補數字。\n"
        "表格化呈現工具結果，不展開原理。\n"
        "若工具回傳結果不全（例如只有單一 action），明確標註資料來源是 LLM 近似而非真實 solver。"
    ),
)


_LEAF_SOLVER_GTO_FULL_TREE = LeafConfig(
    persona="solver_lookup",
    tools=["calc_gto_solution", "calc_equity"],
    kb_query_template=None,
    system_prompt_segment=(
        "葉子配置：完整 4 街 GTO 解算（使用者選了「整條樹」）。\n"
        "**必須**對 Preflop / Flop / Turn / River **各呼叫一次** calc_gto_solution，"
        "用各街對應的 board / pot / hero+villain ranges。\n"
        "並行呼叫（plan-and-execute）以節省時間。\n"
        "輸出格式：\n"
        "  ## Preflop spot\n"
        "  | Action | Frequency | EV (bb) |\n"
        "  ...\n"
        "  ## Flop spot ...\n"
        "  ## Turn spot ...\n"
        "  ## River spot ...\n"
        "  ## 總結\n"
        "  - 每街 hero 動作 vs solver 推薦比對（✓/✗）\n"
        "  - 總 EV 偏差（bb）— 此值由四個 spot EV 差總和計算，不要憑感覺寫\n"
        "**禁止**從對話歷史腦補某街的 GTO，只能用 calc_gto_solution 工具的回傳。\n"
        "**禁止**回傳少於 4 街的內容。如果某街工具呼叫失敗，明確標「工具失敗」而非編造。"
    ),
)

_LEAF_QUICK = LeafConfig(
    persona="quick_take",
    tools=["calc_equity", "calc_ev"],
    kb_query_template=None,
    system_prompt_segment=(
        "葉子配置：快評。一句結論（✓/✗/⚠️）+ 1-2 個關鍵 metric，"
        "整則 < 80 字。結尾留「下一步可試」一行。"
    ),
)


_NODES: dict[str, TreeNode] = {
    "L1": TreeNode(
        id="L1",
        widget_type=WidgetType.SINGLE_SELECT,
        question="你想了解這把的什麼？",
        preamble_text="收到。針對這把手牌，我可以從不同角度切入：",
        options=[
            Option(
                id="learn",
                label="我要學東西",
                next_node_id="L2_coach",
                description="帶推理敘事，把學習點融入分析",
            ),
            Option(
                id="gto",
                label="GTO baseline",
                next_node_id="L2_solver",
                description="純 solver 結果表格，不展開原理",
            ),
            Option(
                id="quick",
                label="快評",
                leaf_config=_LEAF_QUICK,
                description="一句結論 + 關鍵 metric",
            ),
            Option(
                id="default",
                label="我不知道 → 預設「我要學東西」",
                next_node_id="L2_coach",
                is_default=True,
            ),
        ],
    ),
    "L2_coach": TreeNode(
        id="L2_coach",
        widget_type=WidgetType.SINGLE_SELECT,
        question="學什麼面向？",
        options=[
            Option(
                id="outcome",
                label="為什麼贏/輸（結果論）",
                next_node_id="L3_outcome",
            ),
            Option(
                id="gto_concept",
                label="GTO 概念（理論論）",
                next_node_id="L3_gto_concept",
            ),
            Option(
                id="exploit",
                label="對手心理 / Exploit",
                next_node_id="L3_exploit",
            ),
            Option(
                id="default",
                label="我不知道 → 預設「為什麼贏/輸」",
                next_node_id="L3_outcome",
                is_default=True,
            ),
        ],
    ),
    "L3_outcome": TreeNode(
        id="L3_outcome",
        widget_type=WidgetType.SINGLE_SELECT,
        question="聚焦哪一街/決定？",
        options=[
            Option(id="flop", label="Flop lead", leaf_config=_LEAF_COACH_OUTCOME),
            Option(id="turn", label="Turn sizing", leaf_config=_LEAF_COACH_OUTCOME),
            Option(id="river", label="River call", leaf_config=_LEAF_COACH_OUTCOME),
            Option(id="line", label="整把線", leaf_config=_LEAF_COACH_OUTCOME),
            Option(
                id="default",
                label="我不知道 → 預設「最大 EV 偏離點」",
                leaf_config=_LEAF_COACH_OUTCOME,
                is_default=True,
            ),
        ],
    ),
    "L3_gto_concept": TreeNode(
        id="L3_gto_concept",
        widget_type=WidgetType.SINGLE_SELECT,
        question="哪個概念？",
        options=[
            Option(id="range_construction", label="Range construction",
                   leaf_config=_LEAF_COACH_GTO_CONCEPT),
            Option(id="bet_sizing", label="Bet sizing 理論",
                   leaf_config=_LEAF_COACH_GTO_CONCEPT),
            Option(id="bluff_freq", label="Bluff 頻率 / MDF",
                   leaf_config=_LEAF_COACH_GTO_CONCEPT),
            Option(id="polarized_merged", label="Polarized vs Merged",
                   leaf_config=_LEAF_COACH_GTO_CONCEPT),
            Option(
                id="default",
                label="我不知道 → 預設「最相關概念」",
                leaf_config=_LEAF_COACH_GTO_CONCEPT,
                is_default=True,
            ),
        ],
    ),
    "L3_exploit": TreeNode(
        id="L3_exploit",
        widget_type=WidgetType.SINGLE_SELECT,
        question="哪個對手行為？",
        options=[
            Option(id="too_loose_pre", label="Pre-flop 太鬆 (loose call/3bet)",
                   leaf_config=_LEAF_COACH_EXPLOIT),
            Option(id="cbet_too_much", label="Flop c-bet 太多",
                   leaf_config=_LEAF_COACH_EXPLOIT),
            Option(id="never_fold_river", label="River 不蓋牌 (calling station)",
                   leaf_config=_LEAF_COACH_EXPLOIT),
            Option(id="too_tight", label="整體偏 Nit / 太緊",
                   leaf_config=_LEAF_COACH_EXPLOIT),
            Option(
                id="default",
                label="我不知道 → 預設「最大 leak」",
                leaf_config=_LEAF_COACH_EXPLOIT,
                is_default=True,
            ),
        ],
    ),
    "L2_solver": TreeNode(
        id="L2_solver",
        widget_type=WidgetType.SINGLE_SELECT,
        question="解哪個 spot？",
        options=[
            Option(id="preflop", label="Preflop spot", leaf_config=_LEAF_SOLVER_GTO),
            Option(id="flop", label="Flop spot", leaf_config=_LEAF_SOLVER_GTO),
            Option(id="turn", label="Turn spot", leaf_config=_LEAF_SOLVER_GTO),
            Option(id="river", label="River spot", leaf_config=_LEAF_SOLVER_GTO),
            Option(id="full_tree", label="整條樹（每街都看）",
                   leaf_config=_LEAF_SOLVER_GTO_FULL_TREE),
            Option(
                id="default",
                label="我不知道 → 預設「最關鍵 spot」",
                leaf_config=_LEAF_SOLVER_GTO_FULL_TREE,
                is_default=True,
            ),
        ],
    ),
}


tree = Tree(
    id="hand_analysis",
    name="手牌分析",
    description="意圖收斂型——讓使用者選想學什麼面向，葉子綁對應 persona/tools",
    root_id="L1",
    nodes=_NODES,
)
