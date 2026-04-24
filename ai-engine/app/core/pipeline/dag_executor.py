"""
DAG Executor — 依 DAG 定義執行 pipeline。

用途（MVP）：
- 測試 DAG 行為：test endpoint 呼叫，不影響生產對話
- A/B 比較：並排跑兩個 DAG
- 未來可擴充為生產 orchestrator 的替代品

設計原則：
- 每個 node_type 對應一個 handler function
- Context 物件在節點間傳遞 state
- 失敗就停、回傳 partial trace（不中斷整個 request）
"""
import asyncio
import json
import re
import time
from collections import defaultdict
from typing import Any, Awaitable, Callable, Optional

from app.core.llm_router.router import chat_completion
from app.core.tools.registry import tool_registry
from app.core.orchestrator.constants import WIDGET_INSTRUCTION
from app.core.orchestrator.prompt_loader import load_active_prompt, search_knowledge
from app.core.pipeline.mode_prompts import MODE_PROMPTS, build_blended_prompt
from app.db import crud


# ============================================================================
# Context
# ============================================================================

class DAGContext:
    """節點間傳遞的狀態容器。"""

    def __init__(
        self,
        project_id: str,
        user_id: Optional[str],
        user_message: str,
        session_id: Optional[str] = None,
        persist: bool = False,
        pre_loaded_history: Optional[list[dict]] = None,
    ):
        self.project_id = project_id
        self.user_id = user_id
        self.user_message = user_message

        # 生產整合欄位（adapter 注入）
        self.session_id = session_id
        self.persist = persist
        self.pre_loaded_history = pre_loaded_history

        # 狀態欄位（各 node handler 按需讀寫）
        self.history: list[dict] = []
        self.intent_type: Optional[str] = None
        self.intent_rule: Optional[dict] = None  # capability rule dict when intent_type==capability_rule
        self.capability_handled: bool = False  # 某 capability 節點執行後設為 True,讓下游 general 節點透過 condition 跳過
        self.rag_context: Optional[str] = None
        self.system_prompt: str = ""
        self.messages: list[dict] = []
        self.model: Optional[str] = None
        self.temperature: float = 0.7
        self.max_tokens: int = 2000
        self.llm_tools: Optional[list[dict]] = None
        self.db_tools: list[dict] = []
        self.llm_response_text: str = ""
        self.tool_call_count: int = 0
        self.tool_iterations: int = 0
        self.tool_results: list[dict] = []  # list of {name, params, result, status, iteration}
        self.total_tokens_in: int = 0
        self.total_tokens_out: int = 0
        self.total_cost_usd: float = 0.0
        self.widgets: list[dict] = []
        self.clean_text: str = ""
        self.guardrail_triggered: bool = False
        self.assistant_message_id: Optional[str] = None

        # capability 節點要寫入 assistant_msg.metadata 的額外欄位(capability_rule_id、tool_id 等)
        self.extra_metadata: dict = {}
        # capability 節點要寫入 ChatResponse.metadata 的額外欄位(handoff、workflow_status 等)
        self.response_metadata: dict = {}

        # 可選的進度事件 sink（asyncio.Queue），若設定則 handler 會 push 即時事件
        # 用於 SSE 串流顯示「正在規劃工具」「正在呼叫 X」等狀態
        self.progress_sink: Optional[object] = None

        # 前端 chat mode 對應的 system prompt 前綴（教練/研究/課程/對戰）
        # compose_prompt 會在組 system prompt 時 prepend
        self.mode_prompt: Optional[str] = None

        # analyze_intent 節點的結構化輸出：{actions, warnings, knowledge_points, response_styles}
        # load_knowledge 用 knowledge_points 做定向 RAG；compose_prompt 注入 warnings 和混合人格
        self.analysis: Optional[dict] = None

        # ── New primitive infrastructure (MVP-1) ──────────────────────────────
        # Per-node output snapshots, for {{node_id.field}} variable substitution
        # in downstream model_call / branch nodes. Keyed by node_id, value is
        # the handler's `output` dict.
        self.node_outputs: dict[str, dict] = {}
        # Set of node_ids that an upstream `branch` node decided NOT to take.
        # The execute_dag loop checks this before running a node and skips if hit.
        self.skipped_by_branch: set[str] = set()

    def emit(self, event: dict) -> None:
        """Best-effort 推事件到 progress_sink。若 sink 不存在或推失敗，靜默忽略。"""
        sink = self.progress_sink
        if sink is None:
            return
        try:
            sink.put_nowait(event)
        except Exception:
            pass


# ============================================================================
# Node handlers — each returns NodeResult dict
# ============================================================================

async def handle_input(node: dict, ctx: DAGContext) -> dict:
    return {
        "status": "ok",
        "output": {"text": ctx.user_message, "length": len(ctx.user_message)},
        "summary": f"收到輸入（{len(ctx.user_message)} 字）",
    }


async def handle_load_history(node: dict, ctx: DAGContext) -> dict:
    """載入歷史。生產模式由 adapter 預載(pre_loaded_history);測試模式空歷史。"""
    if ctx.pre_loaded_history is not None:
        ctx.history = ctx.pre_loaded_history
        return {
            "status": "ok",
            "output": {"history_length": len(ctx.history), "source": "adapter_injected"},
            "summary": f"載入 {len(ctx.history)} 則歷史(adapter 注入)",
        }
    ctx.history = []
    return {
        "status": "ok",
        "output": {"history_length": 0, "note": "test mode — empty history"},
        "summary": "測試模式：跳過歷史載入",
    }


async def handle_triage(node: dict, ctx: DAGContext) -> dict:
    """真實 intent 分類 — keyword + semantic embedding hybrid。

    依 classify_async 回傳決定:
      - capability_rule: 帶著 rule dict,讓下游 capability_* 節點依 action_type 接手
      - active_workflow: 下游 workflow_continue 節點接手
      - general: 下游 load_knowledge → compose_prompt → call_model 鏈
    """
    try:
        from app.core.intent.classifier import intent_classifier
        result = await intent_classifier.classify_async(
            ctx.user_message, ctx.project_id, mode="hybrid"
        )
        ctx.intent_type = result.get("type", "general")
        ctx.intent_rule = result.get("rule")
    except Exception as e:  # noqa: BLE001
        ctx.intent_type = "general"
        return {
            "status": "ok",
            "output": {"intent_type": "general", "error": str(e)[:200]},
            "summary": f"分類失敗退回 general:{e}",
        }

    matched = None
    if ctx.intent_type == "capability_rule" and ctx.intent_rule:
        matched = ctx.intent_rule.get("trigger_description")
    return {
        "status": "ok",
        "output": {
            "intent_type": ctx.intent_type,
            "matched": matched,
            "action_type": (ctx.intent_rule or {}).get("action_type") if ctx.intent_rule else None,
        },
        "summary": f"意圖:{ctx.intent_type}" + (f"({matched})" if matched else ""),
    }


async def handle_triage_llm(node: dict, ctx: DAGContext) -> dict:
    """LLM-based intent classification using a cheap model (default: claude-haiku-4-5-20251001).

    讀取 project 的 capability rules，組成列表給便宜模型判斷；
    失敗時降級為 keyword classifier。
    """
    import json as _json
    import re as _re

    rules = crud.list_capability_rules(ctx.project_id)
    cfg = node.get("config") or {}
    cheap_model = cfg.get("model", "claude-haiku-4-5-20251001")

    if not rules:
        ctx.intent_type = "general"
        return {
            "status": "ok",
            "output": {"intent_type": "general", "reason": "no_rules", "user_message": ctx.user_message[:300]},
            "summary": "無 capability rules → general",
        }

    rules_desc = "\n".join(
        f"{i + 1}. [{r['action_type']}] {r['trigger_description']}"
        for i, r in enumerate(rules)
    )
    # 允許 node config 覆寫 system prompt 模板（可用 {rules_desc} 當佔位符）
    custom_sys_prompt = cfg.get("system_prompt")
    if custom_sys_prompt:
        sys_content = custom_sys_prompt.replace("{rules_desc}", rules_desc)
    else:
        sys_content = (
            "你是一個意圖分類器。根據使用者訊息，判斷是否符合以下任一規則：\n\n"
            f"{rules_desc}\n\n"
            "只回傳 JSON，格式如下：\n"
            '- 不符合：{"type": "general"}\n'
            '- 符合：{"type": "capability_rule", "rule_index": <1-based int>}\n'
            "不要加任何其他說明。"
        )
    system_msg = {"role": "system", "content": sys_content}

    try:
        resp = await chat_completion(
            messages=[system_msg, {"role": "user", "content": ctx.user_message}],
            model=cheap_model,
            max_tokens=50,
            temperature=0.0,
            project_id=ctx.project_id,
            session_id=ctx.session_id,
            span_label="triage_llm",
        )
        text = (resp.get("content") or "").strip()
        m = _re.search(r"\{.*?\}", text, _re.DOTALL)
        parsed = _json.loads(m.group()) if m else {"type": "general"}

        if parsed.get("type") == "capability_rule":
            idx = int(parsed.get("rule_index", 1)) - 1
            if 0 <= idx < len(rules):
                ctx.intent_type = "capability_rule"
                ctx.intent_rule = rules[idx]
                desc = (rules[idx].get("trigger_description") or "")[:60]
                return {
                    "status": "ok",
                    "output": {
                        "intent_type": "capability_rule",
                        "matched": desc,
                        "action_type": rules[idx].get("action_type"),
                        "model_used": cheap_model,
                    },
                    "summary": f"LLM意圖: capability_rule({desc})",
                }

        ctx.intent_type = "general"
        return {
            "status": "ok",
            "output": {"intent_type": "general", "model_used": cheap_model},
            "summary": "LLM意圖: general",
        }
    except Exception as e:  # noqa: BLE001
        from app.core.intent.classifier import intent_classifier

        fallback = intent_classifier.classify(ctx.user_message, ctx.project_id)
        ctx.intent_type = fallback.get("type", "general")
        ctx.intent_rule = fallback.get("rule")
        return {
            "status": "ok",
            "output": {
                "intent_type": ctx.intent_type,
                "fallback": "keyword",
                "error": str(e)[:100],
            },
            "summary": f"LLM失敗→keyword fallback: {ctx.intent_type}",
        }


async def handle_analyze_intent(node: dict, ctx: DAGContext) -> dict:
    """中間層分析：用便宜模型把使用者問題拆成結構化 JSON，供下游節點取用。

    輸出欄位（寫入 ctx.analysis）：
      - actions:          需要執行哪些動作（例：calculate_equity / 教學 / 出題 / 批改）
      - warnings:         本題需提防的注意事項（常見誤區、missing context 等）
      - knowledge_points: 相關知識概念（RAG 用來做定向檢索）
      - response_styles:  該用哪些人格組合（coach/research/course/battle，可多選混用）
    """
    import json as _json
    import re as _re

    cfg = node.get("config") or {}
    model = cfg.get("model") or "claude-haiku-4-5-20251001"

    available_modes = ", ".join(f"{k}（{v['label']}：{v['description']}）" for k, v in MODE_PROMPTS.items())

    default_sys = f"""你是一個問題分析器。任務：把使用者問題拆成結構化 JSON，讓下游系統知道該做什麼。

可用的回覆人格（response_styles 的選項，可多選混用）：
{available_modes}

分析四個維度：
1. actions           — 需要執行哪些動作（例：["計算 AA vs KK 勝率", "教 pot odds 概念", "出一題 BTN vs BB 翻前題"]）
2. warnings          — 本題使用者可能忽略或誤解的地方（例：["未說明籌碼深度", "可能混淆 equity 和 pot odds"]）
3. knowledge_points  — 相關知識關鍵字，給 RAG 定向檢索（例：["pot odds", "range balance", "c-bet sizing"]）
4. response_styles   — 該用哪些人格，用 key 名稱（coach/research/course/battle）。允許多選，例：["coach", "research"] 代表分析＋研究並重

輸出**純 JSON**（不要 markdown code block、不要加說明），格式：
{{
  "actions":          ["...", "..."],
  "warnings":         ["...", "..."],
  "knowledge_points": ["...", "..."],
  "response_styles":  ["coach"]
}}"""
    # 優先序：cfg.system_prompt_ref_version（釘版本）> cfg.system_prompt_ref（追 active）
    # > cfg.system_prompt（raw）> DB slot='analyze_intent' active > 程式預設
    sys_content = crud.resolve_prompt(
        project_id=ctx.project_id,
        ref_version_id=cfg.get("system_prompt_ref_version"),
        ref=cfg.get("system_prompt_ref") or "analyze_intent",
        raw_text=cfg.get("system_prompt"),
        fallback=default_sys,
    )

    try:
        ctx.emit({"status": "analyzing", "message": "分析問題需要哪些工具和知識…"})
        print(f"[INFO] analyze_intent starting with {model}", flush=True)
        start = time.time()
        resp = await chat_completion(
            messages=[
                {"role": "system", "content": sys_content},
                {"role": "user", "content": ctx.user_message},
            ],
            model=model,
            temperature=0.0,
            max_tokens=800,
            project_id=ctx.project_id,
            session_id=ctx.session_id,
            span_label="analyze_intent",
        )
        text = (resp.choices[0].message.content or "").strip()
        latency = int((time.time() - start) * 1000)

        # 解析 JSON（寬鬆：找第一個 { ... } 區塊）
        m = _re.search(r"\{[\s\S]*\}", text)
        if not m:
            raise ValueError(f"analyze_intent 沒回 JSON: {text[:200]}")
        parsed = _json.loads(m.group())
        if not isinstance(parsed, dict):
            raise ValueError("analyze_intent 回傳非 dict")

        analysis = {
            "actions": [str(a) for a in (parsed.get("actions") or []) if a][:8],
            "warnings": [str(w) for w in (parsed.get("warnings") or []) if w][:5],
            "knowledge_points": [str(k) for k in (parsed.get("knowledge_points") or []) if k][:8],
            "response_styles": [s for s in (parsed.get("response_styles") or []) if s in MODE_PROMPTS] or ["coach"],
        }
        ctx.analysis = analysis

        # 用 analysis 組 ctx.mode_prompt：每個 style 優先從 DB slot='mode_{id}' 讀 active 版本，
        # 失敗 fallback 到 code 預設（mode_prompts.MODE_PROMPTS）。
        mode_parts: list[str] = []
        for style_id in analysis["response_styles"]:
            fallback = MODE_PROMPTS.get(style_id, {}).get("prompt", "")
            content = crud.resolve_prompt(
                project_id=ctx.project_id,
                ref=f"mode_{style_id}",
                fallback=fallback,
            )
            if content:
                mode_parts.append(content)
        if len(mode_parts) == 1:
            ctx.mode_prompt = mode_parts[0]
        elif mode_parts:
            labels = [MODE_PROMPTS[s]["label"] for s in analysis["response_styles"] if s in MODE_PROMPTS]
            header = f"# 本題要融合以下 {len(mode_parts)} 種人格風格回覆：{' + '.join(labels)}\n"
            ctx.mode_prompt = header + "\n" + "\n\n---\n\n".join(mode_parts)
        else:
            ctx.mode_prompt = build_blended_prompt(analysis["response_styles"])  # final fallback

        ctx.emit({
            "status": "analyzed",
            "styles": analysis["response_styles"],
            "actions": analysis["actions"][:3],
        })
        print(
            f"[INFO] analyze_intent ok: styles={analysis['response_styles']}, "
            f"actions={len(analysis['actions'])}, kps={len(analysis['knowledge_points'])}, "
            f"warnings={len(analysis['warnings'])}",
            flush=True,
        )

        usage = getattr(resp, "usage", None)
        _in = getattr(usage, "prompt_tokens", 0) if usage else 0
        _out = getattr(usage, "completion_tokens", 0) if usage else 0

        style_labels = " + ".join(MODE_PROMPTS[s]["label"] for s in analysis["response_styles"])
        return {
            "status": "ok",
            "output": {
                "actions": analysis["actions"],
                "warnings": analysis["warnings"],
                "knowledge_points": analysis["knowledge_points"],
                "response_styles": analysis["response_styles"],
                "model_used": model,
                "tokens_in": _in,
                "tokens_out": _out,
                "latency_ms": latency,
            },
            "summary": (
                f"{model} · 人格: {style_labels} · "
                f"{len(analysis['actions'])} actions · {len(analysis['knowledge_points'])} knowledge_points · "
                f"{len(analysis['warnings'])} warnings"
            ),
        }
    except Exception as e:
        # 分析失敗不中斷 pipeline — 用 coach 預設人格走下去
        ctx.analysis = {"actions": [], "warnings": [], "knowledge_points": [], "response_styles": ["coach"]}
        ctx.mode_prompt = MODE_PROMPTS["coach"]["prompt"]
        return {
            "status": "ok",
            "output": {"fallback": True, "error": str(e)[:200], "response_styles": ["coach"]},
            "summary": f"分析失敗，fallback 用 coach 人格：{str(e)[:80]}",
        }


async def handle_load_knowledge(node: dict, ctx: DAGContext) -> dict:
    """RAG 檢索 — 走 orchestrator.prompt_loader.search_knowledge(pipeline:Qdrant → pgvector → keyword)。

    若 ctx.analysis.knowledge_points 存在，用它們做**定向檢索**（比用原 user_message 精準）。
    """
    cfg = node.get("config") or {}
    rag_limit = int(cfg.get("rag_limit", 5))
    if rag_limit == 0:
        return {"status": "ok", "output": {"skipped": True}, "summary": "RAG 關閉"}

    # 優先用 analyze_intent 產出的 knowledge_points 做檢索查詢
    kps = (ctx.analysis or {}).get("knowledge_points") or []
    if kps:
        query = " ".join(kps) + "\n\n" + ctx.user_message  # 關鍵字 + 原問題補足 context
        query_source = "analysis"
    else:
        query = ctx.user_message
        query_source = "user_message"

    try:
        rag_text = await search_knowledge(query, ctx.project_id)
        if rag_text:
            ctx.rag_context = rag_text
            # 估個片段數(以 "---" 分隔)供 trace 顯示
            chunk_count = rag_text.count("\n\n---\n\n") + 1
            return {
                "status": "ok",
                "output": {
                    "chunk_count": chunk_count,
                    "total_chars": len(rag_text),
                    "rag_limit": rag_limit,
                    "rag_preview": rag_text[:1000] + ("..." if len(rag_text) > 1000 else ""),
                    "query": query[:500],
                    "query_source": query_source,
                    "knowledge_points_used": kps if query_source == "analysis" else [],
                },
                "summary": f"取 {chunk_count} 個 RAG 片段（查詢來源：{query_source}）",
            }
    except Exception as e:  # noqa: BLE001
        return {"status": "ok", "output": {"error": str(e)[:200], "query": query[:500], "query_source": query_source}, "summary": "RAG 檢索失敗(略過)"}

    return {"status": "ok", "output": {"chunk_count": 0, "rag_limit": rag_limit, "query": query[:500], "query_source": query_source}, "summary": f"沒有相關知識（查詢來源：{query_source}）"}


async def handle_compose_prompt(node: dict, ctx: DAGContext) -> dict:
    """組 LLM messages:system(prefix + active prompt + WIDGET_INSTRUCTION) + RAG + history + user。

    用 load_active_prompt 取 A/B variant-aware 的 prompt。WIDGET_INSTRUCTION 一定要附,
    否則 DAG 路徑永遠不會產生 widget 標記。
    """
    cfg = node.get("config") or {}
    # 優先序：system_prompt_prefix_ref_version > system_prompt_prefix_ref > system_prompt_prefix raw
    prefix = crud.resolve_prompt(
        project_id=ctx.project_id,
        ref_version_id=cfg.get("system_prompt_prefix_ref_version"),
        ref=cfg.get("system_prompt_prefix_ref"),
        raw_text=cfg.get("system_prompt_prefix") or "",
        fallback="",
    ) or ""

    base_prompt = ""
    try:
        base_prompt = await load_active_prompt(ctx.project_id, ctx.session_id) or ""
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] load_active_prompt failed in DAG: {e}")

    # 組 system prompt: mode_prompt（人格） + prefix(DAG 節點) + base(active prompt)
    #                 + analysis 注入（warnings + knowledge_points）+ WIDGET_INSTRUCTION
    parts = []
    if ctx.mode_prompt:
        parts.append(ctx.mode_prompt)
    if prefix:
        parts.append(prefix)
    if base_prompt:
        parts.append(base_prompt)

    # 注入中間層分析結果
    analysis = ctx.analysis or {}
    warnings = analysis.get("warnings") or []
    knowledge_points = analysis.get("knowledge_points") or []
    actions = analysis.get("actions") or []
    if warnings or knowledge_points or actions:
        sections = []
        if actions:
            sections.append("## 本題該涵蓋的動作\n" + "\n".join(f"- {a}" for a in actions))
        if knowledge_points:
            sections.append("## 需要帶到的知識點\n" + "、".join(knowledge_points))
        if warnings:
            sections.append("## ⚠️ 本題需提防\n" + "\n".join(f"- {w}" for w in warnings))
        parts.append("\n\n".join(sections))

    parts.append(WIDGET_INSTRUCTION)
    ctx.system_prompt = "\n\n".join(p for p in parts if p)

    ctx.messages = []
    if ctx.system_prompt:
        ctx.messages.append({"role": "system", "content": ctx.system_prompt})
    if ctx.rag_context:
        ctx.messages.append({"role": "system", "content": f"以下是相關參考資料:\n\n{ctx.rag_context}"})
    ctx.messages.extend(ctx.history)
    ctx.messages.append({"role": "user", "content": ctx.user_message})

    return {
        "status": "ok",
        "output": {
            "message_count": len(ctx.messages),
            "system_prompt_length": len(ctx.system_prompt),
            "system_prompt_preview": ctx.system_prompt[:1500] + ("..." if len(ctx.system_prompt) > 1500 else ""),
            "has_rag": bool(ctx.rag_context),
            "rag_length": len(ctx.rag_context) if ctx.rag_context else 0,
            "has_prefix": bool(prefix),
            "prefix_preview": prefix[:500] if prefix else "",
            "has_widget_instruction": True,
            "history_count": len(ctx.history),
            "user_message": ctx.user_message[:500],
            "analysis_injected": bool(warnings or knowledge_points or actions),
            "response_styles": analysis.get("response_styles") or [],
            "warnings_count": len(warnings),
            "knowledge_points_count": len(knowledge_points),
            "actions_count": len(actions),
        },
        "summary": (
            f"組出 {len(ctx.messages)} 則訊息(system {len(ctx.system_prompt)} 字)"
            + (f" · 人格: {'+'.join(analysis.get('response_styles') or [])}" if analysis else "")
        ),
    }


# ============================================================================
# Synthesis model auto-upgrade
# ============================================================================

SONNET_MODEL = "claude-sonnet-4-20250514"


def _maybe_upgrade_synthesis_model(
    ctx: DAGContext,
    cfg: dict,
    current_model: str,
) -> tuple[str, str | None]:
    """複雜題時把 Haiku synthesis 升級到較強模型。

    Returns (model, upgrade_reason or None)。

    Toggles (per-node config on call_model):
      - `synthesis_auto_upgrade` (bool, default True) — False 時整個機制關閉
      - `synthesis_upgrade_model` (str, default "claude-sonnet-4-20250514") — 升級目標

    非 Haiku 模型永遠不動（不會被「降級」），因為使用者明確選了一個非便宜模型。
    """
    if cfg.get("synthesis_auto_upgrade") is False:
        return current_model, None
    cur = (current_model or "").lower()
    if "haiku" not in cur:
        return current_model, None

    analysis = ctx.analysis or {}
    actions = analysis.get("actions") or []
    knowledge = analysis.get("knowledge_points") or []
    styles = analysis.get("response_styles") or []
    msg = ctx.user_message or ""

    reasons: list[str] = []
    if len(actions) >= 3:
        reasons.append(f"actions={len(actions)}")
    if len(knowledge) >= 5:
        reasons.append(f"knowledge_points={len(knowledge)}")
    if len(styles) >= 2:
        reasons.append(f"multi-persona={'+'.join(styles)}")
    if "=== AI 分析資料 ===" in msg or "[手牌紀錄]" in msg:
        reasons.append("hand-record-block")

    if not reasons:
        return current_model, None

    upgrade_target = cfg.get("synthesis_upgrade_model") or SONNET_MODEL
    return upgrade_target, ", ".join(reasons)


async def _plan_and_execute(
    node: dict,
    ctx: DAGContext,
    cfg: dict,
    tools_payload: list,
    iteration_details: list,
) -> dict:
    """Plan-and-Execute 架構：
    1) Planner model 一次輸出 JSON array of tool_calls
    2) 平行執行所有 tool
    3) Synthesis model 根據結果合成最終回覆
    """
    import asyncio as _asyncio
    import re as _re

    planner_model = cfg.get("planner_model") or cfg.get("synthesis_model") or ctx.model
    syn_model = cfg.get("synthesis_model") or ctx.model
    _upgraded_syn, _upgrade_reason = _maybe_upgrade_synthesis_model(ctx, cfg, syn_model)
    if _upgrade_reason:
        print(f"[INFO] synthesis auto-upgrade: {syn_model} → {_upgraded_syn} (reason: {_upgrade_reason})", flush=True)
        syn_model = _upgraded_syn
    _syn_base = crud.resolve_prompt(
        project_id=ctx.project_id,
        ref_version_id=cfg.get("synthesis_system_prompt_ref_version"),
        ref=cfg.get("synthesis_system_prompt_ref"),
        raw_text=cfg.get("synthesis_system_prompt"),
        fallback=(
            "你是一個助手。根據以下工具執行結果，用繁體中文提供完整、具體的回覆。"
            "把所有工具結果的數據都整合進回答，列表/表格呈現更佳。"
            "不要憑空添加未在資料中出現的內容。"
        ),
    )
    # 合併主對話 system prompt（含人格規則）到 synthesis，確保 synthesis 也遵守
    # 例如：mode_coach 禁止憑眼睛推斷牌型名稱，必須也作用於 synthesis 步驟
    _main_sys = ctx.system_prompt or ""
    syn_sys = (f"{_main_sys}\n\n---\n{_syn_base}") if _main_sys else _syn_base

    total_in = 0
    total_out = 0
    total_latency_ms = 0

    # 開始 — 告訴前端「要用 plan-and-execute」
    ctx.emit({"status": "thinking", "message": "規劃要呼叫哪些工具…"})

    # ─── Step 1: Plan ────────────────────────────────────────────────
    # 用 tools_payload（已轉成 LLM 標準格式，含正確 schema）做完整描述
    tools_desc_full = json.dumps(
        [{
            "name": t.get("function", {}).get("name") or t.get("name"),
            "description": t.get("function", {}).get("description") or t.get("description", ""),
            "parameters": t.get("function", {}).get("parameters") or t.get("parameters") or {},
        } for t in (tools_payload or [])],
        ensure_ascii=False,
        indent=2,
    )[:4000]
    # 生成具體範例（取第一個 tool 的 schema 做 dummy 範例，強化參數格式 anchor）
    example_block = ""
    if tools_payload:
        first = tools_payload[0]
        fname = first.get("function", {}).get("name") or first.get("name", "")
        fschema = first.get("function", {}).get("parameters") or first.get("parameters") or {}
        props = fschema.get("properties", {}) if isinstance(fschema, dict) else {}
        # 產生 dummy 參數 example
        dummy = {}
        for pname, pspec in props.items():
            ptype = pspec.get("type") if isinstance(pspec, dict) else None
            if ptype == "array":
                dummy[pname] = ["AA", "KK"] if "player" in pname.lower() or "hand" in pname.lower() else []
            elif ptype == "integer":
                dummy[pname] = 0
            elif ptype == "number":
                dummy[pname] = 0.0
            elif ptype == "boolean":
                dummy[pname] = False
            else:
                dummy[pname] = ""
        example_block = f"""

### 具體範例（參考正確 params 欄位名稱）

若要計算「AA vs KK」的勝率，正確格式是：
```json
{{"name": "{fname}", "params": {json.dumps(dummy, ensure_ascii=False)}}}
```

**絕對不要**自己發明欄位名稱（例如 hero_hand、villain_hand、opponent 等都是錯的）。
只能使用上方 schema properties 裡列出的欄位名稱。"""

    # 從 analysis 拿 actions 當強制提示
    analysis_hint = ""
    if ctx.analysis:
        acts = ctx.analysis.get("actions") or []
        if acts:
            analysis_hint = "\n\n分析層已列出本題需要執行的 actions（必須對應到工具呼叫）：\n" + "\n".join(f"- {a}" for a in acts)

    plan_prompt = f"""你是工具呼叫規劃器。根據使用者問題，規劃所有需要的工具呼叫（可多個）。

使用者問題：{ctx.user_message}{analysis_hint}

可用工具（完整 JSON schema）：
{tools_desc_full}
{example_block}

規則：
1. 涵蓋問題的**所有**情境，不要偷懶只列一兩個。
2. 若問題涉及多種比較（例如「AA 對各種牌」），列出所有該比較的對手牌型。
3. **params 欄位名稱必須完全照上方 schema 的 properties 來**，不要自己發明欄位名。
4. 每個呼叫參數必須合法：
   - 撲克牌面計算：若 hero 和 villain 手牌會共用花色（例如 AA vs AKs 都有 A），**必須指定具體花色**避免重複。
     範例（正確）：AA vs AK → 用 `["AhAs", "KdAc"]` 或 `["AsAh", "KdQd"]`（AK 拿不同 suit 的 A）
     範例（錯誤）：`["AA", "AKs"]` — 會觸發 duplicate cards 錯誤。
   - 單一花色牌型（suited）用 `s` 後綴代表同花（例：`AKs`）；`o` 代表不同花（例：`AKo`）。
   - 撲克用詞簡寫：`AA`=雙 A、`22`=雙 2、`AKs`=同花 AK、`AKo`=不同花 AK。
5. 最多列 12 個呼叫。

## 【必規劃工具的觸發關鍵字】（硬規則）
若使用者問題含以下任一情境，**必須**規劃對應工具，不可回傳空 array：

A. 問題含「勝率 / equity / 打得如何 / 評價這手 / 算一下」
   → 規劃 `calculate_equity`，參數取自問題中提到的手牌 / 牌面

B. 問題含「pot odds / 底池賠率 / 跟注是否正確」
   → 規劃 `calculate_pot_odds` + `calculate_equity` 兩個

C. 問題含 `[手牌紀錄]` 或 `=== AI 分析資料 ===` 區塊
   → 必從該 JSON 抓出：
     * hero.hand (例 "8s9s") + villain.hand (例 "KhJh") + board (例 "Jd9d8d5cQc")
     * 規劃 `calculate_equity` with params {{"players": [hero.hand, villain.hand], "board": board}}
     * 若有完整 pot_by_street → 也規劃 `calculate_pot_odds`
   → **禁止**因為「牌已經看得出輸贏」就不呼叫 — 硬規則就是要呼叫驗證

D. 問題含「EV / 期望值」
   → 規劃 `calculate_ev`

E. 問題含 `[手牌紀錄]` 或 `=== AI 分析資料 ===` 區塊，且問題涉及「為什麼贏/輸 / 哪種牌型 / 牌力 / 比較牌型 / 誰的手更好」
   → 除了 `calculate_equity`，**也規劃** `evaluate_hand`
   → params: {{"players": [hero.hand, villain.hand], "board": board}}
   → 理由：`calculate_equity` 只給勝率，`evaluate_hand` 給確切牌型名稱（如兩對/一對），避免 AI 憑眼睛腦補

F. 問題含「聽牌 / outs / 補牌 / 差幾張 / 聽什麼 / draws / 順子聽牌 / 同花聽牌 / 腸子 / 雙頭 / 幾個 outs」
   → 規劃 `analyze_draws`
   → params: {{"players": [手牌...], "board": board（必須是 3 或 4 張，flop 或 turn）}}
   → 若問題來自 `=== AI 分析資料 ===` 區塊，board 直接取 JSON 中的 board 欄位（但確認牌數 ≤ 4）
   → 注意：river（5 張 board）不支援，此情況改用 `evaluate_hand`

若以上都不符合（純概念教學、閒聊），可回傳 `[]` 空 array。

輸出**純 JSON**（不要加任何說明、不要 markdown code block），格式：
[{{"name": "tool_name", "params": {{...}}}}, ...]"""

    _start = time.time()
    plan_resp = await chat_completion(
        messages=[{"role": "user", "content": plan_prompt}],
        model=planner_model,
        temperature=0.0,
        max_tokens=2000,
        project_id=ctx.project_id,
        session_id=ctx.session_id,
        span_label="plan_tools",
    )
    plan_text = (plan_resp.choices[0].message.content or "").strip()
    _usage = getattr(plan_resp, "usage", None)
    _plan_in = getattr(_usage, "prompt_tokens", 0) if _usage else 0
    _plan_out = getattr(_usage, "completion_tokens", 0) if _usage else 0
    _plan_lat = int((time.time() - _start) * 1000)
    total_in += _plan_in
    total_out += _plan_out
    total_latency_ms += _plan_lat

    # 解析 JSON array（寬鬆：找第一個 [...] 區塊）
    m = _re.search(r"\[[\s\S]*\]", plan_text)
    if not m:
        raise ValueError(f"planner did not return JSON array: {plan_text[:200]}")
    plan = json.loads(m.group())
    if not isinstance(plan, list) or not plan:
        raise ValueError(f"planner returned empty plan")

    iteration_details.append({
        "iter": 1,
        "phase": "planning",
        "tokens_in": _plan_in,
        "tokens_out": _plan_out,
        "latency_ms": _plan_lat,
        "text_preview": f"{len(plan)} tool_calls planned: " + ", ".join(p.get("name", "?") for p in plan[:8]),
        "finish_reason": "planned",
    })
    print(f"[INFO] planning ok: {len(plan)} calls planned with {planner_model}", flush=True)

    # 告訴前端：規劃了 N 個工具、即將平行執行
    ctx.emit({
        "status": "tool_plan",
        "message": f"規劃了 {len(plan)} 個工具呼叫，即將平行執行",
        "tools": [{"name": p.get("name"), "params": p.get("params")} for p in plan],
    })

    # ─── Step 2: Parallel execute ────────────────────────────────────
    _start = time.time()

    def _autofix_duplicate_cards(params: dict) -> dict:
        """若 players 是簡寫（AA、AKs）且偵測到會衝突，轉成具體花色字串避免 duplicate cards。"""
        if not isinstance(params, dict):
            return params
        players = params.get("players")
        if not isinstance(players, list) or len(players) < 2:
            return params
        # 僅當所有 player 都是 ≤3 字元的簡寫時，做 disambiguation
        shorthand_suits = ['s', 'h', 'd', 'c']
        used_cards: set[str] = set()
        fixed = []
        for hand in players:
            if not isinstance(hand, str):
                fixed.append(hand)
                continue
            h = hand.strip()
            # 已是具體格式（4 字元如 AhAs）就保留
            if len(h) == 4 and all(c in "23456789TJQKA" or c in "shdc" for c in h):
                fixed.append(h)
                used_cards.add(h[:2]); used_cards.add(h[2:])
                continue
            # 簡寫：Pair (AA / 22) 或 AKs / AKo
            if len(h) == 2 and h[0] == h[1]:  # Pair: AA, KK, ...
                rank = h[0]
                # 找兩個未用的花色
                picks = []
                for s in shorthand_suits:
                    card = rank + s
                    if card not in used_cards:
                        picks.append(card)
                        if len(picks) == 2:
                            break
                if len(picks) == 2:
                    new_hand = picks[0] + picks[1]
                    fixed.append(new_hand)
                    used_cards.add(picks[0]); used_cards.add(picks[1])
                else:
                    fixed.append(h)  # fallback
            elif len(h) == 3 and h[-1] in ('s', 'o'):  # AKs / AKo
                r1, r2, kind = h[0], h[1], h[2]
                if kind == 's':
                    # 找一個未用的花色給兩張牌
                    for s in shorthand_suits:
                        c1, c2 = r1 + s, r2 + s
                        if c1 not in used_cards and c2 not in used_cards:
                            fixed.append(c1 + c2)
                            used_cards.add(c1); used_cards.add(c2)
                            break
                    else:
                        fixed.append(h)
                else:  # 'o' offsuit
                    picked1, picked2 = None, None
                    for s in shorthand_suits:
                        if r1 + s not in used_cards:
                            picked1 = r1 + s; break
                    for s in shorthand_suits:
                        if r2 + s not in used_cards and (not picked1 or s != picked1[1]):
                            picked2 = r2 + s; break
                    if picked1 and picked2:
                        fixed.append(picked1 + picked2)
                        used_cards.add(picked1); used_cards.add(picked2)
                    else:
                        fixed.append(h)
            else:
                fixed.append(h)
                # 嘗試 extract used cards from specific format
        new_params = dict(params)
        new_params["players"] = fixed
        return new_params

    async def _run_one(tc, allow_retry=True):
        name = tc.get("name")
        params = tc.get("params") or {}
        ctx.emit({"status": "tool_start", "tool_name": name, "params": params})
        try:
            r = await tool_registry.execute_tool_by_name(
                name=name, params=params, tools=ctx.db_tools,
            )
            status = "ok" if not (isinstance(r, dict) and r.get("status") == "error") else "error"
        except Exception as e:
            r = {"error": str(e)}
            status = "error"
        ctx.emit({"status": "tool_done", "tool_name": name, "ok": status == "ok"})
        # Retry with autofix for duplicate-card errors
        if status == "error" and allow_retry:
            err_str = json.dumps(r, ensure_ascii=False).lower()
            if "duplicate" in err_str and "players" in params:
                fixed_params = _autofix_duplicate_cards(params)
                if fixed_params != params:
                    print(f"[INFO] retrying {name} with autofixed params: {fixed_params}", flush=True)
                    try:
                        r2 = await tool_registry.execute_tool_by_name(
                            name=name, params=fixed_params, tools=ctx.db_tools,
                        )
                        r2_status = "ok" if not (isinstance(r2, dict) and r2.get("status") == "error") else "error"
                        if r2_status == "ok":
                            return {"name": name, "params": fixed_params, "result": r2, "status": "ok"}
                    except Exception:
                        pass
        return {"name": name, "params": params, "result": r, "status": status}

    tool_results = await _asyncio.gather(*[_run_one(tc) for tc in plan])
    for tr in tool_results:
        ctx.tool_results.append({
            "iteration": 1,
            "name": tr["name"],
            "params": tr["params"],
            "result": tr["result"],
            "status": tr["status"],
        })
    ctx.tool_iterations = 1
    _exec_lat = int((time.time() - _start) * 1000)
    total_latency_ms += _exec_lat
    ok_count = sum(1 for tr in tool_results if tr["status"] == "ok")
    iteration_details.append({
        "iter": 2,
        "phase": "parallel_execute",
        "tokens_in": 0,
        "tokens_out": 0,
        "latency_ms": _exec_lat,
        "text_preview": f"{ok_count}/{len(tool_results)} tools succeeded",
        "finish_reason": "executed",
    })

    # 告訴前端：工具都跑完了，現在整理回覆
    ctx.emit({
        "status": "synthesizing",
        "message": f"整理 {ok_count} 個工具結果，正在撰寫回覆…",
    })

    # ─── Step 3: Synthesis ───────────────────────────────────────────
    tool_text = "\n\n".join(
        f"[{tr['name']}] params={json.dumps(tr['params'], ensure_ascii=False)}\n"
        f"{'結果' if tr['status']=='ok' else '錯誤'}: {json.dumps(tr['result'], ensure_ascii=False)[:1000]}"
        for tr in tool_results
    )
    syn_msgs = [
        {"role": "system", "content": syn_sys},
        {"role": "user", "content": (
            f"問題：{ctx.user_message}\n\n"
            f"工具結果（共 {len(tool_results)} 個）：\n{tool_text}\n\n"
            "請根據以上工具結果提供完整且具體的最終回覆。\n\n"
            "【硬規則】禁止自行推斷雙方最終牌型名稱（如順子/兩對/同花/三條/葫蘆/同花順）。"
            "牌型名稱需要完整 5 張牌組合計算，工具結果沒有明確告訴你就不要說。"
            "若 equity=100%，只說『工具確認 Hero 100% 獲勝』，不要猜測是哪種牌力。"
        )},
    ]
    _start = time.time()
    syn_resp = await chat_completion(
        messages=syn_msgs,
        model=syn_model,
        temperature=ctx.temperature,
        max_tokens=ctx.max_tokens,
        project_id=ctx.project_id,
        session_id=ctx.session_id,
        span_label="synthesis",
    )
    syn_text = (syn_resp.choices[0].message.content or "").strip()
    _usage = getattr(syn_resp, "usage", None)
    _syn_in = getattr(_usage, "prompt_tokens", 0) if _usage else 0
    _syn_out = getattr(_usage, "completion_tokens", 0) if _usage else 0
    _syn_lat = int((time.time() - _start) * 1000)
    total_in += _syn_in
    total_out += _syn_out
    total_latency_ms += _syn_lat
    iteration_details.append({
        "iter": 3,
        "phase": "synthesis",
        "tokens_in": _syn_in,
        "tokens_out": _syn_out,
        "latency_ms": _syn_lat,
        "text_preview": syn_text[:200],
        "finish_reason": "text" if syn_text else "empty",
    })
    ctx.llm_response_text = syn_text
    print(f"[INFO] synthesis ok: len={len(syn_text)} with {syn_model}", flush=True)

    # 更新全域累積 tokens
    ctx.total_tokens_in += total_in
    ctx.total_tokens_out += total_out
    ctx.tool_call_count = len(tool_results)

    return {
        "status": "ok",
        "output": {
            "text": ctx.llm_response_text[:500] + ("..." if len(ctx.llm_response_text) > 500 else ""),
            "model": ctx.model,
            "planner_model": planner_model,
            "synthesis_model": syn_model,
            "planning_mode": True,
            "tokens_in": total_in,
            "tokens_out": total_out,
            "latency_ms": total_latency_ms,
            "tool_calls_total": len(tool_results),
            "tool_calls_ok": ok_count,
            "iteration_details": iteration_details,
        },
        "summary": f"planning_mode · 規劃 {len(plan)} 個 tool · 平行執行 {ok_count}/{len(tool_results)} 成功 · 合成 {syn_model} · 收 {total_in} 出 {total_out}",
    }


async def handle_call_model(node: dict, ctx: DAGContext) -> dict:
    """主模型呼叫 + 完整工具迴圈。

    若 model 要求呼叫工具，實際執行工具、把結果餵回模型，最多跑 max_iterations 輪。
    max_iterations 預設 20（夠複雜題目用，偶發 runaway 由重複偵測 + token 預算兜底）。
    """
    cfg = node.get("config") or {}
    try:
        project = crud.get_project(ctx.project_id)
    except Exception:
        project = None

    # Per-project pipeline config override(與 orchestrator agent.py:517 對齊)
    try:
        per_project_cfg = crud.get_node_config(ctx.project_id, "main_model") or {}
    except Exception:
        per_project_cfg = {}

    # 優先序:node cfg > per-project cfg > project default > fallback
    ctx.model = (
        cfg.get("model")
        or per_project_cfg.get("model")
        or (project.get("default_model") if project else None)
        or "claude-sonnet-4-20250514"
    )
    ctx.temperature = float(cfg.get("temperature", per_project_cfg.get("temperature", 0.7)))
    ctx.max_tokens = int(cfg.get("max_tokens", per_project_cfg.get("max_tokens", 2000)))
    max_iterations = int(cfg.get("max_iterations", 20))
    # Runaway safeguards (Layer 2 & 3)
    _dup_threshold = 3          # 連續 N 次同 tool+params 視為 runaway
    _token_budget = 150_000     # 累計 input tokens 硬上限

    # Resolve tools:優先 node cfg.tool_ids,否則 per-project cfg.tool_ids,否則全部
    tool_ids = cfg.get("tool_ids")
    if tool_ids is None:
        tool_ids = per_project_cfg.get("tool_ids")
    tools_payload = None
    if project:
        try:
            all_tools = await tool_registry.list_tools(project.get("tenant_id"))
            if tool_ids is not None:
                selected = [t for t in all_tools if t["id"] in set(tool_ids)]
            else:
                selected = all_tools
            ctx.db_tools = selected
            tools_payload = tool_registry.convert_to_llm_tools(selected) if selected else None
            ctx.llm_tools = tools_payload
        except Exception:
            pass

    total_latency_ms = 0
    total_in = 0
    total_out = 0
    final_tool_call_count = 0
    iteration_details: list[dict] = []   # 每輪詳細（for trace output）
    synthesis_layer: str = ""             # L1 / L2 / L3 / "" (not needed)

    # Plan-and-Execute mode：Haiku 一次規劃所有 tool_calls → 平行執行 → Haiku 合成
    # 比傳統 tool_loop 省 ~80% 成本（避開每輪重送完整歷史）
    if cfg.get("planning_mode") and tools_payload:
        try:
            _pe_result = await _plan_and_execute(
                node, ctx, cfg, tools_payload,
                iteration_details=iteration_details,
            )
            # 把 synthesis_model 冒泡到 response_metadata，方便前端 / debug
            _pe_out = _pe_result.get("output") or {}
            if _pe_out.get("synthesis_model"):
                ctx.response_metadata["synthesis_model"] = _pe_out["synthesis_model"]
            if _pe_out.get("planner_model"):
                ctx.response_metadata["planner_model"] = _pe_out["planner_model"]
            return _pe_result
        except Exception as _pe:
            # fallback 到傳統 tool_loop
            print(f"[WARN] plan_and_execute failed, falling back to tool_loop: {_pe}", flush=True)
            import traceback as _tb
            _tb.print_exc()

    try:
        for iteration in range(max_iterations + 1):  # initial + up to N iterations
            start = time.time()
            resp = await chat_completion(
                messages=ctx.messages,
                model=ctx.model,
                temperature=ctx.temperature,
                max_tokens=ctx.max_tokens,
                tools=tools_payload,
                project_id=ctx.project_id,
                session_id=ctx.session_id,
                span_label=f"main_model{'' if iteration == 0 else f'_iter_{iteration + 1}'}",
            )
            msg = resp.choices[0].message
            text = msg.content or ""
            usage = getattr(resp, "usage", None)
            in_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
            out_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
            tool_calls = getattr(msg, "tool_calls", None) or []
            iter_latency = int((time.time() - start) * 1000)

            total_in += in_tokens
            total_out += out_tokens
            total_latency_ms += iter_latency

            iteration_details.append({
                "iter": iteration + 1,
                "phase": "tool_loop",
                "tokens_in": in_tokens,
                "tokens_out": out_tokens,
                "latency_ms": iter_latency,
                "tool_calls": [
                    {"name": tc.function.name, "arguments": tc.function.arguments[:300] if tc.function.arguments else ""}
                    for tc in tool_calls
                ],
                "text_preview": text[:200] if text else "",
                "finish_reason": "text" if not tool_calls else "tool_calls",
            })

            if not tool_calls:
                # Done
                ctx.llm_response_text = text
                final_tool_call_count = 0
                break

            # Model wants to use tools — execute them
            final_tool_call_count = len(tool_calls)
            ctx.tool_iterations += 1

            # Append assistant message with tool_calls to history
            ctx.messages.append({
                "role": "assistant",
                "content": text,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            })

            # Execute each tool call and append tool results
            for tc in tool_calls:
                tool_name = tc.function.name
                try:
                    params = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except Exception:
                    params = {}
                try:
                    result = await tool_registry.execute_tool_by_name(
                        name=tool_name,
                        params=params,
                        tools=ctx.db_tools,
                    )
                    status = "ok" if not (isinstance(result, dict) and result.get("status") == "error") else "error"
                except Exception as e:
                    result = {"error": str(e)}
                    status = "error"

                ctx.tool_results.append({
                    "iteration": ctx.tool_iterations,
                    "name": tool_name,
                    "params": params,
                    "result": result,
                    "status": status,
                })
                ctx.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False)[:4000],
                })

            # Runaway safeguards（在合成判斷之前檢查，觸發則強制進入合成分支）
            # Layer 2: 連續 N 個 tool_call 都是同 tool+params → 視為 runaway
            _recent = ctx.tool_results[-_dup_threshold:]
            if len(_recent) == _dup_threshold and all(
                r["name"] == _recent[0]["name"] and r["params"] == _recent[0]["params"]
                for r in _recent
            ):
                print(
                    f"[WARN] duplicate tool_call loop detected: {_recent[0]['name']} × {_dup_threshold}, forcing synthesis",
                    flush=True,
                )
                iteration = max_iterations

            # Layer 3: 累計 input tokens 超過硬上限 → 強制進入合成
            if total_in > _token_budget:
                print(
                    f"[WARN] token budget exhausted: total_in={total_in} > {_token_budget}, forcing synthesis",
                    flush=True,
                )
                iteration = max_iterations

            # 達到 iteration cap：三層防呆合成，保證 ctx.llm_response_text 絕對非空。
            # 所有 print 用 flush=True，確保 Uvicorn --reload 下 worker 子行程能輸出 log。
            if iteration >= max_iterations:
                if not ctx.llm_response_text and ctx.tool_results:
                    import litellm as _litellm
                    import traceback as _tb
                    _syn_text = ""

                    # Layer 1: tool_choice="none" 保留完整上下文（Anthropic 原生）
                    try:
                        _start = time.time()
                        _resp = await _litellm.acompletion(
                            model=ctx.model,
                            messages=ctx.messages,
                            temperature=ctx.temperature,
                            max_tokens=ctx.max_tokens,
                            tools=tools_payload,
                            tool_choice="none",
                        )
                        _syn_text = (_resp.choices[0].message.content or "").strip()
                        _usage = getattr(_resp, "usage", None)
                        _syn_in = getattr(_usage, "prompt_tokens", 0) if _usage else 0
                        _syn_out = getattr(_usage, "completion_tokens", 0) if _usage else 0
                        _syn_lat = int((time.time() - _start) * 1000)
                        total_in += _syn_in
                        total_out += _syn_out
                        total_latency_ms += _syn_lat
                        iteration_details.append({
                            "iter": len(iteration_details) + 1, "phase": "synthesis_L1",
                            "tokens_in": _syn_in, "tokens_out": _syn_out, "latency_ms": _syn_lat,
                            "text_preview": _syn_text[:200], "finish_reason": "text" if _syn_text else "empty",
                        })
                        if _syn_text:
                            synthesis_layer = "L1"
                        print(f"[INFO] synthesis L1 tool_choice=none: len={len(_syn_text)}", flush=True)
                    except Exception as _e:
                        iteration_details.append({
                            "iter": len(iteration_details) + 1, "phase": "synthesis_L1",
                            "tokens_in": 0, "tokens_out": 0, "latency_ms": 0,
                            "text_preview": "", "finish_reason": f"error: {str(_e)[:100]}",
                        })
                        print(f"[WARN] synthesis L1 failed: {_e}", flush=True)
                        _tb.print_exc()

                    # Layer 2: 乾淨上下文 + 可配置 system prompt + 可配置模型（預設用 call_model 同一顆）
                    if not _syn_text:
                        try:
                            _start = time.time()
                            _user_msg = next(
                                (m.get("content", "") for m in ctx.messages if m.get("role") == "user"),
                                ctx.user_message,
                            )
                            _tool_text = "\n\n".join(
                                f"[{tr['name']}]\n{json.dumps(tr['result'], ensure_ascii=False)[:1000]}"
                                for tr in ctx.tool_results
                            )
                            # 允許 node config 覆寫：synthesis_model / synthesis_system_prompt
                            _syn_model = cfg.get("synthesis_model") or ctx.model
                            _upgraded, _reason = _maybe_upgrade_synthesis_model(ctx, cfg, _syn_model)
                            if _reason:
                                print(f"[INFO] synthesis L2 auto-upgrade: {_syn_model} → {_upgraded} (reason: {_reason})", flush=True)
                                _syn_model = _upgraded
                            _syn_sys_prompt = cfg.get("synthesis_system_prompt") or (
                                "你是一個助手。根據以下工具執行結果，用繁體中文提供清楚完整的回答。"
                            )
                            _clean_msgs = [
                                {"role": "system", "content": _syn_sys_prompt},
                                {"role": "user", "content": f"問題：{_user_msg}\n\n工具結果：\n{_tool_text}\n\n請根據結果完整回答。"},
                            ]
                            _resp = await _litellm.acompletion(
                                model=_syn_model,
                                messages=_clean_msgs,
                                temperature=ctx.temperature,
                                max_tokens=ctx.max_tokens,
                            )
                            _syn_text = (_resp.choices[0].message.content or "").strip()
                            _usage = getattr(_resp, "usage", None)
                            _syn_in = getattr(_usage, "prompt_tokens", 0) if _usage else 0
                            _syn_out = getattr(_usage, "completion_tokens", 0) if _usage else 0
                            _syn_lat = int((time.time() - _start) * 1000)
                            total_in += _syn_in
                            total_out += _syn_out
                            total_latency_ms += _syn_lat
                            iteration_details.append({
                                "iter": len(iteration_details) + 1, "phase": "synthesis_L2",
                                "tokens_in": _syn_in, "tokens_out": _syn_out, "latency_ms": _syn_lat,
                                "text_preview": _syn_text[:200], "finish_reason": "text" if _syn_text else "empty",
                            })
                            if _syn_text:
                                synthesis_layer = "L2"
                            print(f"[INFO] synthesis L2 clean-context: len={len(_syn_text)}", flush=True)
                        except Exception as _e:
                            iteration_details.append({
                                "iter": len(iteration_details) + 1, "phase": "synthesis_L2",
                                "tokens_in": 0, "tokens_out": 0, "latency_ms": 0,
                                "text_preview": "", "finish_reason": f"error: {str(_e)[:100]}",
                            })
                            print(f"[WARN] synthesis L2 failed: {_e}", flush=True)
                            _tb.print_exc()

                    # Layer 3: 工具結果直接當文字（保底絕對非空）
                    if not _syn_text:
                        _syn_text = "工具執行完成，結果如下：\n\n" + "\n\n".join(
                            f"**{tr['name']}**\n```json\n{json.dumps(tr['result'], ensure_ascii=False, indent=2)[:800]}\n```"
                            for tr in ctx.tool_results
                        )
                        synthesis_layer = "L3"
                        iteration_details.append({
                            "iter": len(iteration_details) + 1, "phase": "synthesis_L3",
                            "tokens_in": 0, "tokens_out": 0, "latency_ms": 0,
                            "text_preview": _syn_text[:200], "finish_reason": "fallback",
                        })
                        print(f"[INFO] synthesis L3 tool-as-text: len={len(_syn_text)}", flush=True)

                    ctx.llm_response_text = _syn_text
                break

        ctx.total_tokens_in += total_in
        ctx.total_tokens_out += total_out
        ctx.tool_call_count = final_tool_call_count

        tool_summary = f"，呼叫 {len(ctx.tool_results)} 個工具" if ctx.tool_results else ""
        syn_suffix = f"（合成 {synthesis_layer}）" if synthesis_layer else ""
        return {
            "status": "ok",
            "output": {
                "text": ctx.llm_response_text[:500] + ("..." if len(ctx.llm_response_text) > 500 else ""),
                "model": ctx.model,
                "synthesis_model": cfg.get("synthesis_model") or ctx.model,
                "synthesis_system_prompt": cfg.get("synthesis_system_prompt") or "（預設）",
                "system_prompt_prefix": cfg.get("system_prompt_prefix") or "（無）",
                "temperature": ctx.temperature,
                "max_tokens": ctx.max_tokens,
                "max_iterations": max_iterations,
                "tokens_in": total_in,
                "tokens_out": total_out,
                "latency_ms": total_latency_ms,
                "iterations": ctx.tool_iterations,
                "tool_calls_total": len(ctx.tool_results),
                "tools_available": [t.get("name") for t in (ctx.db_tools or [])],
                "synthesis_layer": synthesis_layer,
                "iteration_details": iteration_details,
            },
            "summary": f"{ctx.model} · 收 {total_in} 出 {total_out} · {total_latency_ms}ms{tool_summary}{syn_suffix}",
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "summary": f"模型呼叫失敗：{e}"}


async def handle_execute_tools(node: dict, ctx: DAGContext) -> dict:
    """顯示在 call_model 節點內執行的工具結果。"""
    if not ctx.tool_results:
        return {"status": "ok", "output": {"iterations": 0}, "summary": "模型未呼叫工具"}

    # Summarize per tool
    summary_lines = []
    for tr in ctx.tool_results:
        status_icon = "✓" if tr["status"] == "ok" else "✗"
        summary_lines.append(f"{status_icon} {tr['name']} (iter {tr['iteration']})")

    return {
        "status": "ok",
        "output": {
            "iterations": ctx.tool_iterations,
            "total_calls": len(ctx.tool_results),
            "results": ctx.tool_results[:10],  # limit dump size
        },
        "summary": f"執行 {ctx.tool_iterations} 輪 · {len(ctx.tool_results)} 個工具呼叫｜" + "、".join(summary_lines[:5]),
    }


async def handle_guardrail(node: dict, ctx: DAGContext) -> dict:
    cfg = node.get("config") or {}
    forbidden = cfg.get("forbidden_patterns") or []
    action = cfg.get("action", "warn")
    if not forbidden:
        return {"status": "ok", "output": {"skipped": True}, "summary": "沒設禁用詞，略過"}

    text = ctx.llm_response_text or ctx.clean_text
    hits = []
    for pat in forbidden:
        if pat and pat.lower() in text.lower():
            hits.append(pat)

    if not hits:
        return {
            "status": "ok",
            "output": {"hits": 0, "action": action},
            "summary": f"通過檢查（檢查 {len(forbidden)} 個關鍵字）",
        }

    ctx.guardrail_triggered = True
    result = {
        "status": "ok" if action == "warn" else "error",
        "output": {"hits": hits, "action": action},
        "summary": f"🛡️ 偵測到 {len(hits)} 個禁用詞（{action}）",
    }
    if action == "block":
        ctx.llm_response_text = "[此回應因 Guardrail 規則被阻擋]"
    elif action == "retry":
        # MVP: 只標記，完整 retry 需要 graph loop 支援
        result["output"]["note"] = "MVP: retry 未實作（需支援 DAG loop）"
    return result


async def handle_retry(node: dict, ctx: DAGContext) -> dict:
    # MVP: retry 節點本身是 no-op；語意是「包裹前一個節點 N 次重試」
    # 實作完整 retry 需要 DAG executor 支援包裝語意，本 MVP 簡化
    cfg = node.get("config") or {}
    return {
        "status": "ok",
        "output": {
            "max_retries": cfg.get("max_retries", 3),
            "backoff_ms": cfg.get("backoff_ms", 1000),
            "note": "MVP: retry 節點僅標記，實際重試邏輯後續版本",
        },
        "summary": "Retry 節點（MVP 標記）",
    }


async def handle_parse_widget(node: dict, ctx: DAGContext) -> dict:
    text = ctx.llm_response_text
    widgets: list[dict] = []
    pattern = r'<!--WIDGET:([\s\S]*?)-->'
    matches = re.findall(pattern, text)
    clean = re.sub(pattern, '', text).strip()
    for m in matches:
        try:
            widgets.append(json.loads(m.strip()))
        except Exception:
            pass
    ctx.widgets = widgets
    ctx.clean_text = clean
    return {
        "status": "ok",
        "output": {
            "widget_count": len(widgets),
            "clean_length": len(clean),
            "raw_length": len(text),
            "clean_preview": clean[:500] + ("..." if len(clean) > 500 else ""),
            "widgets_preview": widgets[:3],
        },
        "summary": f"解析出 {len(widgets)} 個 widget",
    }


async def handle_capability_widget(node: dict, ctx: DAGContext) -> dict:
    """Capability rule · widget action — 回傳預定義 widget + 可選的 LLM 文字回覆。

    Condition 應綁 intent_type == capability_rule AND intent_rule.action_type == widget。
    """
    rule = ctx.intent_rule or {}
    action_config = rule.get("action_config") or {}
    widget_def = action_config.get("widget") or {}
    text_response = action_config.get("text") or ""

    if not text_response:
        # 產生 contextual 文字
        try:
            system_prompt = await load_active_prompt(ctx.project_id, ctx.session_id) or ""
            messages: list[dict] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.extend(ctx.history)
            messages.append({"role": "user", "content": ctx.user_message})
            messages.append({"role": "system", "content": (
                f"使用者的問題匹配到了一個互動元件規則。請用自然語言回覆使用者,"
                f"然後系統會自動顯示互動元件。規則描述:{rule.get('trigger_description', '')}"
            )})
            resp = await chat_completion(
                messages=messages,
                model="claude-sonnet-4-20250514",
                project_id=ctx.project_id,
                session_id=ctx.session_id,
                span_label="capability_widget_text",
            )
            text_response = (resp.choices[0].message.content or "").strip()
        except Exception as e:  # noqa: BLE001
            text_response = "好的,我為你準備了一個互動元件。"
            print(f"[WARN] capability_widget text generation failed: {e}")

    ctx.clean_text = text_response
    ctx.widgets = [widget_def] if widget_def else []
    ctx.extra_metadata.update({
        "capability_rule_id": rule.get("id"),
        "action_type": "widget",
    })
    ctx.capability_handled = True

    return {
        "status": "ok",
        "output": {
            "rule_id": rule.get("id"),
            "has_widget": bool(widget_def),
            "text_length": len(text_response),
        },
        "summary": f"Widget:{rule.get('trigger_description', '(unknown)')[:30]}",
    }


async def handle_capability_tool_call(node: dict, ctx: DAGContext) -> dict:
    """Capability rule · tool_call action — LLM 被動參考工具回覆。"""
    rule = ctx.intent_rule or {}
    action_config = rule.get("action_config") or {}
    tool_id = action_config.get("tool_id")

    if not tool_id:
        # fallback:讓下游 general 節點接手
        ctx.capability_handled = False
        return {"status": "ok", "output": {"skipped": True, "reason": "no tool_id"}, "summary": "無 tool_id,退回 general"}

    tool = crud.get_tool(tool_id)
    if not tool:
        ctx.capability_handled = False
        return {"status": "ok", "output": {"skipped": True, "reason": "tool not found"}, "summary": "tool 不存在,退回 general"}

    try:
        system_prompt = await load_active_prompt(ctx.project_id, ctx.session_id) or ""
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.extend(ctx.history)
        messages.append({"role": "user", "content": ctx.user_message})
        messages.append({"role": "system", "content": f"可用工具:{tool['name']} — {tool.get('description', '')}。請使用此工具回答使用者。"})
        resp = await chat_completion(
            messages=messages,
            model="claude-sonnet-4-20250514",
            project_id=ctx.project_id,
            session_id=ctx.session_id,
            span_label="capability_tool_call",
        )
        text_response = (resp.choices[0].message.content or "").strip()
    except Exception as e:  # noqa: BLE001
        text_response = f"(工具呼叫失敗:{e})"

    ctx.clean_text = text_response
    ctx.tool_results = [{"tool_name": tool["name"], "status": "referenced"}]
    ctx.extra_metadata.update({
        "capability_rule_id": rule.get("id"),
        "tool_id": tool_id,
    })
    ctx.capability_handled = True

    return {
        "status": "ok",
        "output": {"rule_id": rule.get("id"), "tool_name": tool["name"], "text_length": len(text_response)},
        "summary": f"Tool:{tool['name']}",
    }


async def handle_capability_workflow(node: dict, ctx: DAGContext) -> dict:
    """Capability rule · workflow action — 啟動 workflow(auto 或 step 模式)。"""
    from app.core.workflows.engine import workflow_engine

    rule = ctx.intent_rule or {}
    action_config = rule.get("action_config") or {}
    workflow_id = action_config.get("workflow_id")
    run_mode = action_config.get("run_mode", "step")

    if not workflow_id:
        ctx.capability_handled = False
        return {"status": "ok", "output": {"skipped": True, "reason": "no workflow_id"}, "summary": "無 workflow_id,退回 general"}

    user_id = ctx.user_id or "anonymous"

    if run_mode == "auto":
        result = await workflow_engine.run_to_completion(
            workflow_id,
            session_id=ctx.session_id,
            user_id=user_id,
            initial_vars={"message": ctx.user_message},
        )
        status = result.get("status")
        trace_len = len(result.get("trace") or [])
        if status == "completed":
            text = f"工作流已自動執行完成({trace_len} 個步驟)。"
        else:
            text = f"工作流執行失敗:{result.get('error', 'unknown')}"
        ctx.clean_text = text
        ctx.extra_metadata.update({
            "workflow_run_id": result.get("run_id"),
            "capability_rule_id": rule.get("id"),
            "workflow_status": status,
            "workflow_vars": result.get("vars"),
        })
        ctx.response_metadata.update({
            "workflow_status": status,
            "workflow_run_id": result.get("run_id"),
        })
        ctx.capability_handled = True
        return {
            "status": "ok",
            "output": {"run_id": result.get("run_id"), "workflow_status": status, "steps": trace_len},
            "summary": f"Workflow auto:{status} ({trace_len} steps)",
        }

    # 步進式
    result = await workflow_engine.start_workflow(workflow_id, ctx.session_id, user_id)
    if result.get("status") == "started":
        step = result.get("current_step", {})
        text = f"已啟動工作流:{result.get('workflow_name', '')}。\n\n當前步驟:{step.get('id', '')}"
        ctx.clean_text = text
        if step.get("widget"):
            ctx.widgets = [step["widget"]]
        ctx.extra_metadata.update({
            "workflow_run_id": result.get("run_id"),
            "capability_rule_id": rule.get("id"),
        })
        ctx.capability_handled = True
        return {
            "status": "ok",
            "output": {"run_id": result.get("run_id"), "step_id": step.get("id")},
            "summary": f"Workflow step:{result.get('workflow_name', '')}",
        }

    # 啟動失敗 → fallback
    ctx.capability_handled = False
    return {
        "status": "ok",
        "output": {"skipped": True, "reason": result.get("detail", "workflow start failed")},
        "summary": "Workflow 啟動失敗,退回 general",
    }


async def handle_capability_handoff(node: dict, ctx: DAGContext) -> dict:
    """Capability rule · handoff action — 升級至真人客服。"""
    from app.core.handoff.service import handoff_service

    rule = ctx.intent_rule or {}
    action_config = rule.get("action_config") or {}

    reason = action_config.get("reason") or "User triggered handoff capability"
    urgency = action_config.get("urgency", "normal")
    result = await handoff_service.request(
        ctx.session_id, reason=reason, triggered_by="capability_rule", urgency=urgency,
    )
    reply = action_config.get("text") or "已為您轉接真人客服,稍後會有專員與您聯繫。"

    ctx.clean_text = reply
    ctx.extra_metadata.update({
        "capability_rule_id": rule.get("id"),
        "handoff_message_id": result.get("handoff_message_id"),
        "handoff_notified": result.get("notified"),
        "handoff_urgency": urgency,
    })
    ctx.response_metadata.update({
        "handoff": True,
        "handoff_message_id": result.get("handoff_message_id"),
        "urgency": urgency,
    })
    ctx.capability_handled = True

    return {
        "status": "ok",
        "output": {
            "rule_id": rule.get("id"),
            "handoff_message_id": result.get("handoff_message_id"),
            "notified": result.get("notified"),
            "urgency": urgency,
        },
        "summary": f"Handoff · {urgency}",
    }


async def handle_workflow_continue(node: dict, ctx: DAGContext) -> dict:
    """active_workflow 分支 — Phase 5 stub,目前直接退回 general。

    未來 Phase 5 完工時,此節點會:
      1. 找出 session 的進行中 workflow_run(waiting_input 狀態)
      2. 把 user_message 當作 step_result 呼叫 workflow_engine.advance_workflow
      3. 回傳下一步的 widget 或完成訊息
    """
    ctx.capability_handled = False
    return {
        "status": "ok",
        "output": {"note": "Phase 5 stub · 退回 general"},
        "summary": "Workflow continue(stub)",
    }


async def handle_output(node: dict, ctx: DAGContext) -> dict:
    """組最終輸出。生產模式(ctx.persist && ctx.session_id)會寫 ait_training_messages,
    metadata 的 widgets / tool_results 欄位與 orchestrator 對齊。
    """
    final_text = ctx.clean_text or ctx.llm_response_text
    output: dict = {
        "final_text": final_text,
        "final_text_preview": final_text[:1000] + ("..." if len(final_text) > 1000 else ""),
        "final_text_length": len(final_text),
        "widget_count": len(ctx.widgets),
        "total_tokens_in": ctx.total_tokens_in,
        "total_tokens_out": ctx.total_tokens_out,
        "tool_call_count": len(ctx.tool_results),
    }

    if ctx.persist and ctx.session_id:
        try:
            metadata: dict = {}
            if ctx.widgets:
                metadata["widgets"] = ctx.widgets
            if ctx.tool_results:
                metadata["tool_results"] = ctx.tool_results
            if ctx.extra_metadata:
                metadata.update(ctx.extra_metadata)
            assistant_msg = crud.create_message(
                session_id=ctx.session_id,
                role="assistant",
                content=final_text,
                metadata=metadata,
            )
            ctx.assistant_message_id = assistant_msg["id"]
            output["assistant_message_id"] = assistant_msg["id"]
        except Exception as e:  # noqa: BLE001
            # 寫庫失敗不阻斷回覆 — 記在 output
            output["persist_error"] = str(e)[:200]

    return {
        "status": "ok",
        "output": output,
        "summary": f"輸出完成({len(final_text)} 字)" + ("|已落庫" if ctx.assistant_message_id else ""),
    }


# ============================================================================
# Handler registry
# ============================================================================

NodeHandler = Callable[[dict, DAGContext], Awaitable[dict]]

HANDLERS: dict[str, NodeHandler] = {
    "input": handle_input,
    "user_input": handle_input,  # alias — V3 DAG 用這個 key
    "load_history": handle_load_history,
    "triage": handle_triage,
    "triage_llm": handle_triage_llm,
    "analyze_intent": handle_analyze_intent,
    "load_knowledge": handle_load_knowledge,
    "compose_prompt": handle_compose_prompt,
    "call_model": handle_call_model,
    "execute_tools": handle_execute_tools,
    "guardrail": handle_guardrail,
    "retry": handle_retry,
    "parse_widget": handle_parse_widget,
    "output": handle_output,
    # Capability rule actions(intent_type == capability_rule 時按 action_type 分派)
    "capability_widget": handle_capability_widget,
    "capability_tool_call": handle_capability_tool_call,
    "capability_workflow": handle_capability_workflow,
    "capability_handoff": handle_capability_handoff,
    # active_workflow 分支
    "workflow_continue": handle_workflow_continue,
}

# ── MVP-1: 3 primitive 註冊（新通用節點）─────────────────────────────
# 直接 import + 註冊到 HANDLERS。新節點與舊節點並存，使用者可自由選用。
try:
    from app.core.pipeline.handlers.model_call import handle_model_call as _handle_model_call_v2
    from app.core.pipeline.handlers.branch import handle_branch as _handle_branch
    HANDLERS["model_call"] = _handle_model_call_v2  # 注意：取代舊 call_model 必須在 DB type_key migrate 後才會被使用
    HANDLERS["branch"] = _handle_branch
except ImportError as _e:
    import logging as _logging
    _logging.getLogger(__name__).warning("MVP-1 handler import failed: %s", _e)


# ============================================================================
# Executor
# ============================================================================

# ============================================================================
# Conditional execution — 讓 DAG 支援分支
# ============================================================================

def _resolve_field(field: str, ctx: DAGContext):
    """支援 dotted path(如 'intent_rule.action_type')取得 ctx 或 ctx.dict 的值。"""
    parts = field.split(".")
    val: Any = ctx
    for p in parts:
        if val is None:
            return None
        if isinstance(val, dict):
            val = val.get(p)
        else:
            val = getattr(val, p, None)
    return val


def _evaluate_condition(cond: dict, ctx: DAGContext) -> bool:
    """遞迴條件解析器。

    Shape:
      atomic: {"field": "intent_type", "op": "==", "value": "general"}
      compound: {"all": [cond1, cond2, ...]} 或 {"any": [cond1, cond2, ...]}

    支援 op: ==, !=, in, not_in, truthy, falsy。field 支援 dotted path。
    """
    if not cond:
        return True
    if "all" in cond:
        return all(_evaluate_condition(c, ctx) for c in (cond.get("all") or []))
    if "any" in cond:
        return any(_evaluate_condition(c, ctx) for c in (cond.get("any") or []))

    field = cond.get("field")
    if not field:
        return True
    op = cond.get("op", "==")
    expected = cond.get("value")
    actual = _resolve_field(field, ctx)

    if op == "==":
        return actual == expected
    if op == "!=":
        return actual != expected
    if op == "in":
        return actual in (expected or [])
    if op == "not_in":
        return actual not in (expected or [])
    if op == "truthy":
        return bool(actual)
    if op == "falsy":
        return not bool(actual)
    return True


def _topological_order(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Kahn's algorithm — 傳回節點 id 列表。若有循環則傳回已能處理的部分。"""
    incoming: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, set[str]] = defaultdict(set)
    all_ids = {n["id"] for n in nodes}

    for e in edges:
        src = e.get("from")
        dst = e.get("to")
        if src in all_ids and dst in all_ids:
            outgoing[src].add(dst)
            incoming[dst].add(src)

    ready = [nid for nid in all_ids if not incoming[nid]]
    order: list[str] = []
    while ready:
        # 穩定排序：優先無 incoming + 節點定義出現早的
        current = ready.pop(0)
        order.append(current)
        for dest in list(outgoing[current]):
            incoming[dest].discard(current)
            if not incoming[dest]:
                ready.append(dest)
        outgoing[current].clear()

    return order


async def execute_dag(
    dag: dict,
    project_id: str,
    user_message: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    persist: bool = False,
    pre_loaded_history: Optional[list[dict]] = None,
    progress_sink: Optional[object] = None,
    mode_prompt: Optional[str] = None,
) -> dict:
    """執行一個 DAG 定義。

    生產模式(adapter 呼叫)傳入 session_id + persist=True + pre_loaded_history,
    output 節點會寫入 ait_training_messages。測試模式(/dag/test 端點)不傳,
    handle_load_history 回退成空歷史 stub、handle_output 不落庫。

    Returns:
        {
          "final_text": str,
          "widgets": [...],
          "tool_results": [...],
          "intent_type": str | None,
          "assistant_message_id": str | None,
          "total_tokens_in": int,
          "total_tokens_out": int,
          "trace": [{node_id, label, type_key, status, summary, latency_ms, output}, ...],
          "guardrail_triggered": bool,
        }
    """
    nodes = dag.get("nodes") or []
    edges = dag.get("edges") or []
    node_by_id = {n["id"]: n for n in nodes}
    ctx = DAGContext(
        project_id=project_id,
        user_id=user_id,
        user_message=user_message,
        session_id=session_id,
        persist=persist,
        pre_loaded_history=pre_loaded_history,
    )
    ctx.progress_sink = progress_sink
    ctx.mode_prompt = mode_prompt
    # MVP-1: branch handler needs edges to compute downstream skip set
    ctx._dag_edges = edges  # type: ignore[attr-defined]

    order = _topological_order(nodes, edges)
    trace: list[dict] = []

    for node_id in order:
        node = node_by_id.get(node_id)
        if not node:
            continue
        type_key = node.get("type_key")
        handler = HANDLERS.get(type_key)
        entry = {
            "node_id": node_id,
            "label": node.get("label"),
            "type_key": type_key,
        }

        # MVP-1: branch upstream may have marked us as not-taken.
        if node_id in ctx.skipped_by_branch:
            entry.update({"status": "skipped", "summary": "上游 branch 未選此路", "latency_ms": 0})
            trace.append(entry)
            continue

        if not handler:
            entry.update({"status": "skipped", "summary": f"未知節點類型:{type_key}"})
            trace.append(entry)
            continue

        # Conditional execution:condition 不符就 skip(不執行 handler、不記 latency)
        cond = node.get("condition")
        if cond and not _evaluate_condition(cond, ctx):
            entry.update({
                "status": "skipped",
                "summary": f"條件不符:{cond.get('field')} {cond.get('op')} {cond.get('value')}",
                "latency_ms": 0,
            })
            trace.append(entry)
            continue

        start = time.time()
        try:
            result = await handler(node, ctx)
        except Exception as e:
            result = {"status": "error", "error": str(e), "summary": f"節點執行例外:{e}"}
        latency = int((time.time() - start) * 1000)
        entry.update(result)
        entry["latency_ms"] = latency
        trace.append(entry)

        # MVP-1: snapshot this node's output for downstream {{node.field}} access.
        out = result.get("output")
        if isinstance(out, dict):
            ctx.node_outputs[node_id] = out

        # Fatal error: stop
        if result.get("status") == "error" and type_key in ("call_model", "guardrail"):
            if type_key == "guardrail" and (node.get("config") or {}).get("action") == "block":
                break
            if type_key == "call_model":
                break

    return {
        "final_text": ctx.clean_text or ctx.llm_response_text,
        "widgets": ctx.widgets,
        "tool_results": ctx.tool_results,
        "intent_type": ctx.intent_type,
        "assistant_message_id": ctx.assistant_message_id,
        "response_metadata": ctx.response_metadata,
        "total_tokens_in": ctx.total_tokens_in,
        "total_tokens_out": ctx.total_tokens_out,
        "guardrail_triggered": ctx.guardrail_triggered,
        "trace": trace,
    }
