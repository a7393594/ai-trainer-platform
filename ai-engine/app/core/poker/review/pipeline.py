"""
Deep Review Pipeline — 4-stage batch analysis

Stage 1: Haiku Filter — 每手快速評分 0-10 可疑度
Stage 2: Solver Lookup — 對疑問手查詢 GTO 策略
Stage 3: Opus Analysis — 深度分析每個決策點
Stage 4: Report — 7 區段總結報告
"""
import json
from typing import Optional
from app.db.supabase import get_supabase
from app.db import crud_poker
from app.core.llm_router.router import chat_completion
from app.core.poker.solver.gto_wizard import query_gto_strategy


T_ANALYSES = "ait_hand_analyses"
T_REPORTS = "ait_review_reports"


async def run_review(
    user_id: str,
    project_id: str,
    hand_ids: list[str] = None,
    batch_id: str = None,
    max_deep_analysis: int = 30,
) -> dict:
    """Execute full review pipeline.

    Returns: {report_id, status, summary}
    """
    sb = get_supabase()

    # Load hands
    if hand_ids:
        hands_data = []
        for hid in hand_ids:
            h = crud_poker.get_hand_history(hid)
            if h:
                hands_data.append(h)
    elif batch_id:
        result = sb.table("ait_hand_histories").select("*").eq("batch_id", batch_id).execute()
        hands_data = result.data or []
    else:
        hands_data = crud_poker.list_hand_histories(user_id, project_id, limit=200)

    if not hands_data:
        return {"error": "No hands found"}

    # Create report record
    report = sb.table(T_REPORTS).insert({
        "user_id": user_id,
        "project_id": project_id,
        "batch_id": batch_id,
        "hand_count": len(hands_data),
        "status": "processing",
    }).execute().data[0]
    report_id = report["id"]

    total_cost = 0.0

    try:
        # ═══ Stage 1: Haiku Filter ═══
        filtered_hands = []
        for hand in hands_data:
            parsed = hand.get("parsed_json", {})
            if not parsed:
                continue

            score, reason = await _filter_hand(parsed)

            # Save analysis record
            analysis_data = {
                "hand_history_id": hand["id"],
                "review_report_id": report_id,
                "filter_score": score,
                "filter_pass": score >= 4.0,
                "filter_reason": reason,
            }
            sb.table(T_ANALYSES).insert(analysis_data).execute()

            if score >= 4.0:
                filtered_hands.append({"hand": hand, "parsed": parsed, "filter_score": score})

        # Sort by score, take top N
        filtered_hands.sort(key=lambda x: x["filter_score"], reverse=True)
        top_hands = filtered_hands[:max_deep_analysis]

        # ═══ Stage 2+3: Solver + Deep Analysis ═══
        analyses = []
        for item in top_hands:
            parsed = item["parsed"]
            hand = item["hand"]

            # Solver
            solver_result = await query_gto_strategy(parsed)
            solver_id = solver_result.get("solver_result_id")

            # Deep analysis with Opus-level model
            analysis = await _deep_analyze(parsed, solver_result, user_id, project_id)
            ev_loss = analysis.get("ev_loss_mbb", 0)
            severity = _classify_severity(ev_loss)
            concepts = analysis.get("concepts_tagged", [])

            # Update analysis record
            sb.table(T_ANALYSES).update({
                "solver_result_id": solver_id,
                "analysis_json": analysis,
                "ev_loss_mbb": ev_loss,
                "mistake_severity": severity,
                "concepts_tagged": concepts,
            }).eq("hand_history_id", hand["id"]).eq("review_report_id", report_id).execute()

            analyses.append({
                "hand_id": hand.get("hand_id"),
                "hero_cards": parsed.get("hero_cards", []),
                "board": parsed.get("board", []),
                "position": parsed.get("hero_position", ""),
                "ev_loss_mbb": ev_loss,
                "severity": severity,
                "key_mistake": analysis.get("key_mistake", ""),
                "concepts": concepts,
            })

        # ═══ Stage 4: Generate Report ═══
        report_json = await _generate_report(analyses, hands_data, user_id, project_id)

        # Calculate totals
        total_ev_loss = sum(a["ev_loss_mbb"] for a in analyses if a["ev_loss_mbb"])
        avg_ev_loss = total_ev_loss / max(len(analyses), 1)

        top_weaknesses = _extract_weaknesses(analyses)

        # Update report
        sb.table(T_REPORTS).update({
            "status": "completed",
            "analyzed_count": len(analyses),
            "report_json": report_json,
            "summary": report_json.get("executive_summary", ""),
            "overall_ev_loss_mbb": round(avg_ev_loss, 1),
            "top_weaknesses": top_weaknesses,
            "model_used": "claude-sonnet-4-20250514",
        }).eq("id", report_id).execute()

        return {
            "report_id": report_id,
            "status": "completed",
            "total_hands": len(hands_data),
            "filtered": len(filtered_hands),
            "analyzed": len(analyses),
            "avg_ev_loss_mbb": round(avg_ev_loss, 1),
            "top_weaknesses": top_weaknesses[:5],
        }

    except Exception as e:
        sb.table(T_REPORTS).update({
            "status": "error",
            "report_json": {"error": str(e)},
        }).eq("id", report_id).execute()
        return {"report_id": report_id, "status": "error", "error": str(e)}


# ═══ Stage 1: Filter ═══

async def _filter_hand(parsed: dict) -> tuple[float, str]:
    """Quick triage with Haiku — score 0-10."""
    hero_cards = " ".join(parsed.get("hero_cards", []))
    board = " ".join(parsed.get("board", []))
    net_bb = parsed.get("hero_net_bb", 0)
    actions_count = len(parsed.get("actions", []))
    position = parsed.get("hero_position", "?")

    # Rule-based fast scoring
    score = 0.0
    reasons = []

    # Big loss = interesting
    if net_bb < -10:
        score += 3
        reasons.append("big_loss")
    elif net_bb < -3:
        score += 1.5
        reasons.append("moderate_loss")

    # All-in = interesting
    has_allin = any(a.get("action") == "all-in" for a in parsed.get("actions", []))
    if has_allin:
        score += 2
        reasons.append("all_in")

    # Multi-street = more interesting than preflop fold
    if board:
        score += 1
        if len(board) >= 4:
            score += 1
            reasons.append("turn+")
        if len(board) == 5:
            score += 0.5
            reasons.append("river")

    # Check-raise or raise on later streets
    hero_raises_postflop = [
        a for a in parsed.get("actions", [])
        if a.get("is_hero") and a.get("action") in ("raise", "all-in") and a.get("street") != "preflop"
    ]
    if hero_raises_postflop:
        score += 1.5
        reasons.append("postflop_aggression")

    return min(score, 10), ", ".join(reasons) if reasons else "routine"


# ═══ Stage 3: Deep Analysis ═══

async def _deep_analyze(parsed: dict, solver_result: dict, user_id: str, project_id: str) -> dict:
    """Deep analysis of a single hand with Sonnet."""
    hero_cards = " ".join(parsed.get("hero_cards", []))
    board = " ".join(parsed.get("board", []))
    position = parsed.get("hero_position", "?")
    net_bb = parsed.get("hero_net_bb", 0)

    from app.core.poker.hh_parser.unified_schema import Action
    actions_text = []
    for a in parsed.get("actions", []):
        player = "Hero" if a.get("is_hero") else "Villain"
        act = a.get("action", "?")
        amt = a.get("amount", 0)
        street = a.get("street", "")
        actions_text.append(f"[{street}] {player} {act}" + (f" {amt}bb" if amt else ""))

    solver_strategy = solver_result.get("strategy", {})
    solver_rec = solver_strategy.get("recommended_action", "unknown")

    prompt = f"""分析以下撲克手牌的決策品質。

Hero 手牌: {hero_cards} | 位置: {position}
公共牌: {board or '(翻前結束)'}
動作: {chr(10).join(actions_text)}
結果: {net_bb:+.1f} bb

Solver 建議: {solver_rec}
Solver 分析: {json.dumps(solver_strategy, ensure_ascii=False)[:300]}

請以 JSON 回覆：
{{
  "key_mistake": "最大失誤的一句話描述（如無失誤寫 null）",
  "ev_loss_mbb": 估計的 EV 損失（mbb，0-200），
  "decision_quality": "optimal/minor_error/moderate_error/major_error",
  "concepts_tagged": ["相關概念代碼，如 preflop_3bet, postflop_cbet_flop"],
  "analysis": "50字內分析"
}}
只回覆 JSON。"""

    try:
        response = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model="claude-sonnet-4-20250514",
            temperature=0.2,
            max_tokens=400,
        )
        raw = response.choices[0].message.content or "{}"
        try:
            if "{" in raw:
                start = raw.find("{")
                end = raw.rfind("}") + 1
                return json.loads(raw[start:end])
        except Exception:
            pass
        return {"key_mistake": None, "ev_loss_mbb": 0, "analysis": raw[:200]}
    except Exception as e:
        return {"error": str(e), "ev_loss_mbb": 0}


# ═══ Stage 4: Report Generation ═══

async def _generate_report(analyses: list, all_hands: list, user_id: str, project_id: str) -> dict:
    """Generate 7-section review report."""
    if not analyses:
        return {"executive_summary": "No interesting hands found for deep analysis."}

    # Aggregate data
    total = len(all_hands)
    analyzed = len(analyses)
    mistakes = [a for a in analyses if a.get("ev_loss_mbb", 0) > 5]
    major = [a for a in analyses if a.get("severity") in ("major", "critical")]

    # Concept frequency
    concept_freq: dict[str, int] = {}
    for a in analyses:
        for c in a.get("concepts", []):
            concept_freq[c] = concept_freq.get(c, 0) + 1
    top_concepts = sorted(concept_freq.items(), key=lambda x: x[1], reverse=True)[:5]

    # Build report sections
    report = {
        "executive_summary": f"分析 {total} 手，深度檢視 {analyzed} 手。發現 {len(mistakes)} 個可改善決策，{len(major)} 個重大失誤。",
        "preflop_analysis": _section_preflop(analyses),
        "postflop_patterns": _section_postflop(analyses),
        "biggest_leaks": [
            {"hand_id": a["hand_id"], "ev_loss": a["ev_loss_mbb"], "mistake": a.get("key_mistake", ""), "severity": a.get("severity", "")}
            for a in sorted(analyses, key=lambda x: x.get("ev_loss_mbb", 0), reverse=True)[:5]
        ],
        "concept_gaps": [{"concept": c, "frequency": f} for c, f in top_concepts],
        "improvement_priorities": [c for c, _ in top_concepts[:3]],
        "study_plan": f"本週重點：{'、'.join(c for c, _ in top_concepts[:3])}",
    }
    return report


def _section_preflop(analyses: list) -> dict:
    preflop_issues = [a for a in analyses if any(c.startswith("preflop") for c in a.get("concepts", []))]
    return {"issues_count": len(preflop_issues), "common": [a.get("key_mistake") for a in preflop_issues[:3] if a.get("key_mistake")]}


def _section_postflop(analyses: list) -> dict:
    postflop_issues = [a for a in analyses if any(c.startswith("postflop") for c in a.get("concepts", []))]
    return {"issues_count": len(postflop_issues), "common": [a.get("key_mistake") for a in postflop_issues[:3] if a.get("key_mistake")]}


def _classify_severity(ev_loss: float) -> str:
    if ev_loss >= 50:
        return "critical"
    elif ev_loss >= 20:
        return "major"
    elif ev_loss >= 5:
        return "moderate"
    elif ev_loss > 0:
        return "minor"
    return "none"


def _extract_weaknesses(analyses: list) -> list[dict]:
    """Extract top weaknesses from analyses."""
    concept_loss: dict[str, float] = {}
    concept_count: dict[str, int] = {}
    for a in analyses:
        ev = a.get("ev_loss_mbb", 0)
        for c in a.get("concepts", []):
            concept_loss[c] = concept_loss.get(c, 0) + ev
            concept_count[c] = concept_count.get(c, 0) + 1

    weaknesses = [
        {"concept": c, "total_ev_loss": round(concept_loss[c], 1), "frequency": concept_count[c]}
        for c in concept_loss
    ]
    weaknesses.sort(key=lambda x: x["total_ev_loss"], reverse=True)
    return weaknesses[:10]
