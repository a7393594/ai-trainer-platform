"""
Referee Engine — 核心裁決引擎
流程: 情境解析 → RAG 規則檢索 → 規則疊加解析 → LLM 推理 → 結構化裁決
"""
import json
import time
from typing import Optional

from app.config import settings
from app.core.llm_router.router import chat_completion
from app.core.referee.rules.retriever import hybrid_search
from app.core.referee.rules.resolver import resolve_rules
from app.core.referee.config_resolver import get_referee_config


SYSTEM_PROMPT = """你是一個專業的撲克賽事裁判 AI，精通 TDA 2024 規則、WSOP 規則、Robert's Rules of Poker 以及各大賽事的特殊條款。

## 裁決原則
1. **僅依據提供的規則條文進行推理**，不得引用未在檢索結果中出現的條文
2. 若規則不足以做出判斷，明確說明「需要更多資訊」或「建議升級人類裁判」
3. 裁決必須引用具體的規則編號（如 TDA-42）
4. 考慮規則的優先權層級：監管法規 > 場館規則 > TDA 規則 > 賽事附加條款
5. 遵循 TDA Rule 1 的精神：公平性和遊戲最佳利益優先於技術性規則

## 輸出格式
你必須以嚴格的 JSON 格式回覆,不要加任何 markdown 標記:
{
  "decision": "裁決結論（一句話）",
  "applicable_rules": ["TDA-42", "TDA-56"],
  "reasoning": "完整推理過程",
  "subsequent_steps": ["後續處理步驟1", "步驟2"],
  "confidence": 0.85,
  "requires_human": false,
  "alternative_interpretation": "如有其他可能的解讀,寫在這裡"
}
"""


async def make_ruling(
    dispute: str,
    game_context: dict = None,
    model: str = None,
    temperature: float = 0.2,
    project_id: str = None,
) -> dict:
    """執行一次完整的裁決流程。

    Args:
        dispute: 爭議描述（自然語言）
        game_context: 遊戲狀態 {game_type, pot_size, blind_level, players, ...}
        model: 使用的 LLM 模型,預設用 config.primary_model
        temperature: LLM 溫度,裁決用低溫度確保一致性

    Returns:
        {
            "ruling": {...},              # LLM 輸出的結構化裁決
            "rules_retrieved": [...],     # RAG 檢索到的規則
            "effective_rule": {...},       # 解析後的有效規則
            "conflict_detected": bool,    # 是否有規則衝突
            "model_used": str,
            "latency_ms": int,
            "tokens": {"in": int, "out": int},
            "cost_usd": float,
        }
    """
    ref_cfg = get_referee_config(project_id)
    model = model or ref_cfg["primary_model"]
    game_context = game_context or {}
    start = time.time()

    # Step 1: RAG 規則檢索
    game_type = game_context.get("game_type", "NLHE")
    retrieved = await hybrid_search(dispute, top_k=5, game_type=game_type)

    # Step 2: 規則疊加解析
    resolution = resolve_rules(retrieved)
    effective = resolution["effective_rule"]
    requires_judgment = resolution["requires_judgment"]

    # Step 3: 純查表短路 — 只在爭議描述很短且規則明確時才走 Mode A
    # 自由文字的爭議(>30 字)永遠走 LLM 推理,避免 RAG 檢索不準時直接回錯答案
    is_short_mechanical_query = len(dispute) < 30 and not requires_judgment and effective
    if is_short_mechanical_query:
        return {
            "ruling": {
                "decision": f"依據 {effective.get('rule_code', '?')}: {effective.get('title', '')}",
                "applicable_rules": [effective.get("rule_code")],
                "reasoning": f"此為可直接查表的規則,不需要推理判斷。條文:\n{effective.get('rule_text', '')}",
                "subsequent_steps": [],
                "confidence": 0.95,
                "requires_human": False,
                "alternative_interpretation": None,
            },
            "rules_retrieved": retrieved,
            "effective_rule": effective,
            "conflict_detected": resolution["conflict_detected"],
            "model_used": "lookup",
            "latency_ms": int((time.time() - start) * 1000),
            "tokens": {"in": 0, "out": 0},
            "cost_usd": 0.0,
            "mode": "A",
        }

    # Step 4: 組合 LLM prompt
    rules_context = "\n\n".join(
        f"### {r.get('rule_code', '?')} — {r.get('title', '')}\n"
        f"來源: {r.get('source_name', '?')} (優先權: {r.get('priority', '?')})\n"
        f"{r.get('rule_text', '')}"
        for r in retrieved
    )

    game_context_str = ""
    if game_context:
        game_context_str = f"\n\n## 遊戲狀態\n{json.dumps(game_context, ensure_ascii=False, indent=2)}"

    user_prompt = (
        f"## 爭議情境\n{dispute}"
        f"{game_context_str}"
        f"\n\n## 適用規則條文（由規則檢索引擎提供,僅依據這些條文裁決）\n\n{rules_context}"
    )

    if resolution["conflict_detected"]:
        user_prompt += "\n\n⚠️ 注意:檢索到的規則之間存在潛在衝突,請在推理中說明如何解決衝突。"

    # Step 5: LLM 推理
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = await chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=2000,
        )
        raw = response.choices[0].message.content or ""

        # 解析 JSON
        try:
            if raw.startswith("{"):
                ruling = json.loads(raw)
            else:
                start_idx = raw.find("{")
                end_idx = raw.rfind("}") + 1
                ruling = json.loads(raw[start_idx:end_idx])
        except (json.JSONDecodeError, ValueError):
            ruling = {
                "decision": raw[:500],
                "applicable_rules": [],
                "reasoning": raw,
                "subsequent_steps": [],
                "confidence": 0.50,
                "requires_human": True,
                "alternative_interpretation": "JSON 解析失敗,原始回覆已保留",
            }

        # Token usage
        usage = getattr(response, "usage", None)
        tokens_in = getattr(usage, "prompt_tokens", 0) if usage else 0
        tokens_out = getattr(usage, "completion_tokens", 0) if usage else 0
        from app.core.llm_router.router import calculate_cost
        cost = calculate_cost(model, tokens_in, tokens_out)

    except Exception as e:
        # Failover: 主模型失敗 → 備援模型
        if model == ref_cfg["primary_model"] and ref_cfg["backup_model"]:
            print(f"[WARN] Primary model failed ({e}), falling back to {ref_cfg['backup_model']}")
            return await make_ruling(
                dispute=dispute,
                game_context=game_context,
                model=ref_cfg["backup_model"],
                temperature=temperature,
                project_id=project_id,
            )
        raise

    latency = int((time.time() - start) * 1000)

    return {
        "ruling": ruling,
        "rules_retrieved": [
            {"rule_code": r.get("rule_code"), "title": r.get("title"),
             "score": r.get("score"), "source": r.get("source_name")}
            for r in retrieved
        ],
        "effective_rule": {
            "rule_code": effective.get("rule_code") if effective else None,
            "title": effective.get("title") if effective else None,
        } if effective else None,
        "conflict_detected": resolution["conflict_detected"],
        "model_used": model,
        "latency_ms": latency,
        "tokens": {"in": tokens_in, "out": tokens_out},
        "cost_usd": round(cost, 6),
    }
