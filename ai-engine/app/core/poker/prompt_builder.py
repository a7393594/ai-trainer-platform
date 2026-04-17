"""
三層 Prompt 架構 — Poker AI Coach

L1 Meta（永久）: 教練人格 + 7 鐵律
L2 Level-Directive（動態）: 根據 scaffolding_stage 調整
L3 Turn Context（每回合）: student profile + stats + 當前概念
"""
import json
from typing import Optional


# ═══ Layer 1: Meta Prompt（永久注入）═══

L1_META = """# 角色設定
你是「撲克教練 AI」，一位經驗豐富、善於因材施教的撲克策略教練。你精通德州撲克（NLHE）和底池限注奧馬哈（PLO），熟悉 GTO 理論和實戰剝削策略。

## 七條鐵律（不可違反）
1. **禁止直接回答結果導向問題** — 玩家問「我這手該 call 嗎」，你必須先反問「你覺得對手的 range 裡有什麼？」引導 range 思考。
2. **必須參考 Student Model** — 根據學生的等級、弱點、掌握度調整回答深度和術語。
3. **禁止編造 solver 數字** — 不可隨意說「GTO 建議 67% c-bet」，除非有 tool 回傳的數據。如無數據，說「這需要查 solver」。
4. **區分 variance 與 skill** — 學生說「我這週輸了 20 buy-ins」，不能直接判定退步。先問手數，<5000 手只談決策品質。
5. **Bloom 層級不跳兩級** — 如果學生在 Remember 階段，不要跳到 Analyze。循序漸進。
6. **自我偵測 drift** — 如果你發現自己連續 3 輪都在直接給答案而非提問，主動切回蘇格拉底模式。
7. **語言預設繁體中文** — 術語可中英混用（如「c-bet」「3-bet」「equity」保留英文）。

## 互動風格
- 像一位嚴格但溫暖的教練，偶爾幽默
- 每次回覆最多一個引導問題，避免問題轟炸
- 讚美具體進步（「你的 3-bet range 比上次寬了，方向對了」），不空泛鼓勵
- 對高階學生可以直接挑戰（「你確定這裡 check-raise 比 call 好？為什麼？」）
"""


# ═══ Layer 2: Level-Directive（依 scaffolding_stage 動態注入）═══

L2_DIRECTIVES = {
    "modeling": """## 教學模式：完整示範（Modeling）
- 對初學者，提供完整的思考過程示範
- 每句話最多 1 個專業術語，首次使用時解釋
- 多用比喻和生活化例子
- 句尾附一句重點摘要
- 直接告訴答案但解釋「為什麼」
- 範例：「底池有 100，對手下注 50。你需要 33% 的勝率才值得 call——就像買彩券，要先算期望值。」""",

    "guided": """## 教學模式：引導練習（Guided Practice）
- 先問 1 個導引問題，等學生回答後再補充
- 術語可自由使用，但新術語首次解釋
- 提示不超過 25 字
- 不直接給最終答案，給框架讓學生推導
- 範例：「這個 flop texture 很乾，你覺得 range advantage 在哪一邊？」""",

    "prompting": """## 教學模式：提示引導（Prompting）
- 只給關鍵提示片語，不超過 15 字
- 例如：「想想 blockers」「比較他的 continuing range」
- 不揭露 EV 數字
- 讓學生自己 connect the dots
- 如果學生卡住，給第二個提示而非答案""",

    "sparring": """## 教學模式：對等切磋（Sparring）
- 魔鬼代言人：挑戰學生的每個判斷
- 只問刺探性問題，不給提示、不給答案
- 「你說 check-raise 比 call 好，但如果對手的 range 比你想的極化呢？」
- 鼓勵學生使用 solver 驗證自己的想法
- 偶爾故意提出 suboptimal 策略看學生能否反駁""",
}


# ═══ Layer 3: Turn Context Builder ═══

def build_system_prompt(
    profile: Optional[dict] = None,
    mastery_summary: Optional[list[dict]] = None,
    stats_summary: Optional[str] = None,
    rag_context: Optional[str] = None,
) -> str:
    """組合完整三層 system prompt。

    Args:
        profile: student_profile record
        mastery_summary: list of {concept_name, category, mastery_level}
        stats_summary: pre-formatted stats string (optional, Phase 2)
        rag_context: RAG retrieval context (optional)

    Returns:
        Complete system prompt string
    """
    parts = [L1_META]

    # Layer 2: scaffolding directive
    stage = "modeling"
    level = "L1"
    if profile:
        stage = profile.get("scaffolding_stage", "modeling")
        level = profile.get("level", "L1")

    directive = L2_DIRECTIVES.get(stage, L2_DIRECTIVES["modeling"])
    parts.append(directive)

    # Layer 3: student context
    if profile:
        ctx = _build_student_context(profile, mastery_summary, stats_summary)
        parts.append(ctx)

    return "\n\n".join(parts)


def _build_student_context(
    profile: dict,
    mastery_summary: Optional[list[dict]] = None,
    stats_summary: Optional[str] = None,
) -> str:
    """Build Layer 3 turn context from student data."""
    lines = ["## 學生檔案"]
    lines.append(f"- 等級：{profile.get('level', 'L1')}（信心度 {profile.get('level_confidence', 0.5):.0%}）")
    lines.append(f"- 教學模式：{profile.get('scaffolding_stage', 'modeling')}")
    lines.append(f"- 偏好遊戲：{', '.join(profile.get('game_types', [])) or '未設定'}")
    lines.append(f"- 偏好格式：{profile.get('preferred_format', '6max')}")

    weaknesses = profile.get("weaknesses", [])
    if weaknesses:
        lines.append(f"- 主要弱點：{', '.join(weaknesses[:5])}")

    strengths = profile.get("strengths", [])
    if strengths:
        lines.append(f"- 強項：{', '.join(strengths[:5])}")

    # Mastery overview
    if mastery_summary:
        lines.append("\n### 概念掌握度")
        # Group by category
        by_cat: dict[str, list] = {}
        for m in mastery_summary:
            cat = m.get("category", "other")
            by_cat.setdefault(cat, []).append(m)

        for cat, items in by_cat.items():
            avg = sum(i.get("mastery_level", 0) for i in items) / max(len(items), 1)
            weak = [i["concept_name"] for i in items if i.get("mastery_level", 0) < 0.3]
            line = f"- {cat}：平均 {avg:.0%}"
            if weak:
                line += f"（待加強：{', '.join(weak[:3])}）"
            lines.append(line)

    # Stats (Phase 2)
    if stats_summary:
        lines.append(f"\n### 統計數據\n{stats_summary}")

    return "\n".join(lines)


# ═══ Scaffolding Adjustment Logic ═══

def adjust_scaffolding(
    profile: dict,
    consecutive_correct: int = 0,
    consecutive_wrong: int = 0,
    emotion_signal: Optional[str] = None,
) -> str:
    """決定是否調整 scaffolding stage。

    Rules:
    - 連 3 次答對 → 降階（更少支撐）
    - 連 2 次答錯 → 升階（更多支撐）
    - 情緒低落（frustrated/tilting）→ 鎖定 ≤ guided
    """
    stages = ["modeling", "guided", "prompting", "sparring"]
    current = profile.get("scaffolding_stage", "modeling")
    idx = stages.index(current) if current in stages else 0

    # Emotion override
    if emotion_signal in ("frustrated", "tilting", "upset"):
        return stages[min(idx, 1)]  # lock to modeling or guided

    # Progression
    if consecutive_correct >= 3 and idx < len(stages) - 1:
        return stages[idx + 1]

    # Regression
    if consecutive_wrong >= 2 and idx > 0:
        return stages[idx - 1]

    return current
