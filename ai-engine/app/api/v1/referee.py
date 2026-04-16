"""
Poker Referee API -- merged router
Combines: rulings, rules, audit, analytics, config
Single router prefix: /referee
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.db import crud
from app.db.supabase import get_supabase
from app.core.referee.engine import make_ruling
from app.core.referee.confidence import compute_confidence
from app.core.referee.voting import dual_model_vote, triple_model_vote
from app.core.referee.audit import create_audit_entry
from app.core.referee.rules.retriever import hybrid_search, search_by_topic
from app.core.referee.config_resolver import get_referee_config

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/referee", tags=["poker-referee"])

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class RulingRequest(BaseModel):
    dispute: str
    game_context: Optional[dict] = None
    project_id: Optional[str] = None
    enable_consistency: bool = False
    enable_cross_model: bool = False
    force_dual_model: bool = False
    force_triple_model: bool = False


class ChallengeRequest(BaseModel):
    ruling_id: str
    reason: Optional[str] = None


class RuleSourceCreate(BaseModel):
    name: str
    priority: int
    version: Optional[str] = None
    effective_date: Optional[str] = None


class ConfigUpdate(BaseModel):
    primary_model: Optional[str] = None
    backup_model: Optional[str] = None
    triage_model: Optional[str] = None
    auto_decide_threshold: Optional[float] = None
    human_confirm_threshold: Optional[float] = None
    enable_dual_model: Optional[bool] = None
    enable_triple_model: Optional[bool] = None
    voting_temperature: Optional[float] = None
    consistency_samples: Optional[int] = None


# ===================================================================
# Ruling endpoints  (was /ruling)
# ===================================================================


@router.post("/ruling")
async def submit_ruling(req: RulingRequest):
    """Submit a dispute and receive an AI ruling.

    Full pipeline:
    1. RAG retrieval of relevant rules
    2. Rule overlay resolution (priority override)
    3. LLM reasoning (primary + failover backup)
    4. Confidence assessment (verbal + optional: consistency / cross-model)
    5. Routing decision (Mode A/B/C/escalated)
    6. Audit log entry
    """
    try:
        ref_cfg = get_referee_config(req.project_id)

        # Step 1-3: rule retrieval + LLM ruling
        ruling_result = await make_ruling(
            dispute=req.dispute,
            game_context=req.game_context,
            project_id=req.project_id,
        )

        # Step 4: confidence assessment
        confidence = await compute_confidence(
            ruling_result=ruling_result,
            dispute=req.dispute,
            game_context=req.game_context,
            enable_consistency=req.enable_consistency,
            enable_cross_model=req.enable_cross_model,
            project_id=req.project_id,
        )

        # Step 5: create initial ruling record
        ruling_row = crud.create_ruling({
            "game_context": req.game_context or {},
            "dispute_description": req.dispute,
            "rules_retrieved": ruling_result.get("rules_retrieved", []),
            "effective_rule": (
                ruling_result.get("effective_rule", {}).get("rule_code")
                if ruling_result.get("effective_rule")
                else None
            ),
            "model_outputs": {
                "primary": {
                    "model": ruling_result.get("model_used"),
                    "ruling": ruling_result.get("ruling"),
                    "latency_ms": ruling_result.get("latency_ms"),
                    "cost_usd": ruling_result.get("cost_usd"),
                },
            },
            "confidence": confidence,
            "routing_mode": confidence.get("routing_mode", "C"),
            "final_decision": ruling_result.get("ruling", {}).get("decision"),
        }, project_id=req.project_id)

        # Step 5b: multi-model verification (medium confidence or forced)
        voting_result = None
        mode = confidence.get("routing_mode", "C")

        if req.force_triple_model:
            voting_result = await triple_model_vote(req.dispute, req.game_context, project_id=req.project_id)
            if voting_result.get("escalate"):
                mode = "escalated"
        elif req.force_dual_model or (
            mode == "C" and ref_cfg["enable_dual_model"]
        ):
            voting_result = await dual_model_vote(req.dispute, req.game_context, project_id=req.project_id)
            if voting_result and voting_result.get("agreement"):
                confidence["cross_model_agreement"] = voting_result["agreement_score"]
                confidence["calibrated_final"] = min(
                    confidence["calibrated_final"] + 0.1, 0.95
                )
                mode = "B"
            elif voting_result and not voting_result.get("agreement"):
                mode = "C"

        confidence["routing_mode"] = mode

        # Step 6: persist final ruling record
        model_outputs = {
            "primary": {
                "model": ruling_result.get("model_used"),
                "ruling": ruling_result.get("ruling"),
                "latency_ms": ruling_result.get("latency_ms"),
                "cost_usd": ruling_result.get("cost_usd"),
            },
        }
        if voting_result:
            model_outputs["voting"] = voting_result

        ruling_row = crud.create_ruling({
            "game_context": req.game_context or {},
            "dispute_description": req.dispute,
            "rules_retrieved": ruling_result.get("rules_retrieved", []),
            "effective_rule": (
                ruling_result.get("effective_rule", {}).get("rule_code")
                if ruling_result.get("effective_rule")
                else None
            ),
            "model_outputs": model_outputs,
            "confidence": confidence,
            "routing_mode": mode,
            "final_decision": ruling_result.get("ruling", {}).get("decision"),
        }, project_id=req.project_id)

        # Step 7: audit log
        create_audit_entry(
            ruling_id=ruling_row["id"],
            dispute=req.dispute,
            game_context=req.game_context or {},
            ruling_result=ruling_result,
            confidence=confidence,
            project_id=req.project_id,
        )

        # total cost
        total_cost = ruling_result.get("cost_usd", 0)
        if voting_result:
            if voting_result.get("secondary"):
                total_cost += voting_result["secondary"].get("cost_usd", 0)
            for v in voting_result.get("votes", []):
                total_cost += v.get("cost_usd", 0)

        return {
            "ruling_id": ruling_row["id"],
            "decision": ruling_result.get("ruling", {}).get("decision"),
            "applicable_rules": ruling_result.get("ruling", {}).get("applicable_rules", []),
            "reasoning": ruling_result.get("ruling", {}).get("reasoning"),
            "subsequent_steps": ruling_result.get("ruling", {}).get("subsequent_steps", []),
            "confidence": confidence,
            "voting": voting_result,
            "rules_retrieved": ruling_result.get("rules_retrieved", []),
            "effective_rule": ruling_result.get("effective_rule"),
            "conflict_detected": ruling_result.get("conflict_detected", False),
            "model_used": ruling_result.get("model_used"),
            "latency_ms": ruling_result.get("latency_ms"),
            "total_cost_usd": round(total_cost, 6),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ruling failed: {e}")


@router.get("/ruling/history")
async def list_ruling_history(limit: int = 50, project_id: Optional[str] = Query(None)):
    return {"rulings": crud.list_rulings(limit, project_id=project_id)}


@router.get("/ruling/{ruling_id}")
async def get_ruling_detail(ruling_id: str):
    ruling = crud.get_ruling(ruling_id)
    if not ruling:
        raise HTTPException(404, "Ruling not found")
    audit = crud.get_audit_log(ruling_id)
    return {"ruling": ruling, "audit_log": audit}


# ===================================================================
# Rules endpoints  (was /rules)
# ===================================================================


@router.post("/rules/sources")
async def create_source(req: RuleSourceCreate):
    return crud.create_rule_source(req.name, req.priority, req.version, req.effective_date)


@router.get("/rules/sources")
async def list_sources():
    return {"sources": crud.list_rule_sources()}


@router.get("/rules/list")
async def list_rules(
    source_id: Optional[str] = None,
    topic: Optional[str] = None,
):
    return {"rules": crud.list_rules(source_id, topic)}


@router.get("/rules/search")
async def search_rules(
    q: str = Query(..., min_length=2),
    top_k: int = Query(default=5, ge=1, le=20),
    game_type: Optional[str] = None,
):
    """Hybrid search (semantic + keyword) over rule articles."""
    try:
        results = await hybrid_search(q, top_k=top_k, game_type=game_type)
        return {"query": q, "results": results, "count": len(results)}
    except Exception:
        results = crud.search_rules_by_text(q, limit=top_k)
        return {"query": q, "results": results, "count": len(results), "fallback": "keyword_only"}


@router.get("/rules/by-topic/{topic}")
async def get_rules_by_topic(topic: str, top_k: int = 5):
    results = await search_by_topic(topic, top_k)
    return {"topic": topic, "results": results}


@router.get("/rules/{rule_code}")
async def get_rule_detail(rule_code: str):
    rule = crud.get_rule_by_code(rule_code)
    if not rule:
        raise HTTPException(404, f"Rule {rule_code} not found")
    return rule


# ===================================================================
# Audit endpoints  (was /audit)
# ===================================================================


@router.get("/audit/{ruling_id}")
async def get_audit_log(ruling_id: str):
    log = crud.get_audit_log(ruling_id)
    if not log:
        raise HTTPException(404, "Audit log not found")
    return log


# ===================================================================
# Analytics endpoints  (was /analytics)
# ===================================================================


@router.get("/analytics/summary")
async def get_summary(project_id: Optional[str] = Query(None)):
    """Dashboard overview -- all KPIs. Filter by project_id when provided."""
    sb = get_supabase()

    q = sb.table("pkr_rulings").select("*")
    if project_id:
        q = q.eq("project_id", project_id)
    rulings = q.order("created_at", desc=True).execute().data or []
    total = len(rulings)

    if total == 0:
        return {
            "total_rulings": 0,
            "avg_confidence": 0,
            "total_cost_usd": 0,
            "avg_latency_ms": 0,
            "mode_distribution": {},
            "model_usage": {},
            "confidence_buckets": {"0.9+": 0, "0.8-0.9": 0, "0.6-0.8": 0, "<0.6": 0},
            "recent_rulings": [],
            "rules_count": 0,
        }

    confidences: list[float] = []
    costs: list[float] = []
    latencies: list[float] = []
    mode_dist: dict[str, int] = {}
    model_use: dict[str, int] = {}
    conf_buckets = {"0.9+": 0, "0.8-0.9": 0, "0.6-0.8": 0, "<0.6": 0}

    for r in rulings:
        conf = r.get("confidence", {})
        cal = conf.get("calibrated_final", 0) if isinstance(conf, dict) else 0
        confidences.append(cal)
        if cal >= 0.9:
            conf_buckets["0.9+"] += 1
        elif cal >= 0.8:
            conf_buckets["0.8-0.9"] += 1
        elif cal >= 0.6:
            conf_buckets["0.6-0.8"] += 1
        else:
            conf_buckets["<0.6"] += 1

        mode = r.get("routing_mode", "C")
        mode_dist[mode] = mode_dist.get(mode, 0) + 1

        outputs = r.get("model_outputs", {})
        primary = outputs.get("primary", {}) if isinstance(outputs, dict) else {}
        model = primary.get("model", "unknown")
        cost = primary.get("cost_usd", 0) or 0
        latency = primary.get("latency_ms", 0) or 0
        model_use[model] = model_use.get(model, 0) + 1
        costs.append(cost)
        latencies.append(latency)

    avg_conf = sum(confidences) / total if confidences else 0
    total_cost = sum(costs)
    avg_latency = sum(latencies) / total if latencies else 0

    rules = sb.table("pkr_rules").select("id", count="exact").execute()
    rules_count = len(rules.data) if rules.data else 0

    recent = []
    for r in rulings[:5]:
        conf = r.get("confidence", {})
        recent.append({
            "id": r["id"],
            "created_at": r.get("created_at"),
            "dispute_preview": (r.get("dispute_description", "") or "")[:100],
            "final_decision": (r.get("final_decision", "") or "")[:120],
            "routing_mode": r.get("routing_mode"),
            "confidence": conf.get("calibrated_final") if isinstance(conf, dict) else 0,
            "effective_rule": r.get("effective_rule"),
        })

    return {
        "total_rulings": total,
        "avg_confidence": round(avg_conf, 3),
        "total_cost_usd": round(total_cost, 4),
        "avg_latency_ms": int(avg_latency),
        "mode_distribution": mode_dist,
        "model_usage": model_use,
        "confidence_buckets": conf_buckets,
        "recent_rulings": recent,
        "rules_count": rules_count,
    }


# ===================================================================
# Config endpoints  (was /config)
# ===================================================================


@router.get("/config")
async def get_config(project_id: Optional[str] = Query(None)):
    """Return referee settings. When project_id given, returns per-project overrides."""
    ref_cfg = get_referee_config(project_id)
    return {
        **ref_cfg,
        "embedding_model": settings.embedding_model,
        "environment": settings.environment,
    }


@router.patch("/config")
async def update_config(update: ConfigUpdate, project_id: Optional[str] = Query(None)):
    """Update config. With project_id: persists to domain_config.referee. Without: runtime-only."""
    changes = update.model_dump(exclude_none=True)
    if not changes:
        return {"updated": {}, "current": await get_config(project_id)}

    if project_id:
        # Persist to project's domain_config.referee
        crud.update_project_config(project_id, {"referee": changes})
    else:
        # Legacy: runtime mutation of global settings (resets on restart)
        for field, value in changes.items():
            attr = f"referee_{field}" if not field.startswith("referee_") else field
            if hasattr(settings, attr):
                setattr(settings, attr, value)

    return {"updated": changes, "current": await get_config(project_id)}


# ===================================================================
# Models endpoint  (for the referee settings page)
# ===================================================================

AVAILABLE_MODELS = [
    {"id": "claude-opus-4-6",            "provider": "anthropic", "label": "Claude Opus 4.6",          "tier": "flagship"},
    {"id": "claude-sonnet-4-5-20250514", "provider": "anthropic", "label": "Claude Sonnet 4.5",        "tier": "mid"},
    {"id": "claude-haiku-4-5-20251001",  "provider": "anthropic", "label": "Claude Haiku 4.5",         "tier": "fast"},
    {"id": "gpt-5.4",                    "provider": "openai",    "label": "GPT-5.4",                  "tier": "flagship"},
    {"id": "gpt-4.1",                    "provider": "openai",    "label": "GPT-4.1",                  "tier": "mid"},
    {"id": "gpt-4.1-mini",              "provider": "openai",    "label": "GPT-4.1 Mini",             "tier": "fast"},
    {"id": "gpt-4.1-nano",              "provider": "openai",    "label": "GPT-4.1 Nano",             "tier": "nano"},
    {"id": "gemini-2.5-pro",            "provider": "google",    "label": "Gemini 2.5 Pro",           "tier": "flagship"},
    {"id": "gemini-2.5-flash",          "provider": "google",    "label": "Gemini 2.5 Flash",         "tier": "fast"},
    {"id": "deepseek-r1",               "provider": "deepseek",  "label": "DeepSeek R1",              "tier": "reasoning"},
    {"id": "deepseek-v3-0324",          "provider": "deepseek",  "label": "DeepSeek V3",              "tier": "mid"},
    {"id": "llama-4-maverick",          "provider": "groq",      "label": "Llama 4 Maverick (Groq)",  "tier": "fast"},
]


@router.get("/models")
async def list_available_models(project_id: Optional[str] = Query(None)):
    """Return the catalogue of models the referee can use."""
    ref_cfg = get_referee_config(project_id)
    return {
        "models": AVAILABLE_MODELS,
        "current": {
            "primary_model": ref_cfg["primary_model"],
            "backup_model": ref_cfg["backup_model"],
            "triage_model": ref_cfg["triage_model"],
        },
    }
