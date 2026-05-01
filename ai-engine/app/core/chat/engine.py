"""
V4 Chat Engine — 主入口。

flow:
  1. 解析 user / 確保 session
  2. 載入 history + active prompt + persona
  3. light classifier 判斷場景 + 智慧起始點
  4. free-form → main LLM；複雜場景 → 走樹 → 葉子 → main LLM (Phase 3+)
  5. atomic commit user_msg + assistant_msg + tool_results

V3 -> V4 介面對齊：
  /chat 端點傳進來的是 `app.models.schemas.ChatRequest`(pydantic)，回傳是
  `app.models.schemas.ChatResponse`。本 module 同時暴露同名 dataclass 給 c-end
  / 內部測試用，但對 /chat 端點專用 entry point 是 chat()，接 pydantic ChatRequest。

Phase 1 範圍：
  - 只實作 free-form 路徑（classifier 永遠回 FREE_FORM）
  - 樹狀分支 raise NotImplementedError("Phase 3+")
  - persona 永遠用 COACH
  - free-form 暫不接 KB / DB tools（Phase 4 接）
  - tool_use_loop 已支援 tools 為空陣列以利 Phase 3+
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from app.db import crud
from app.core.orchestrator.constants import DEMO_USER_EMAIL
from app.core.orchestrator.history import load_history
from app.core.orchestrator.prompt_loader import load_active_prompt
from app.models.schemas import (
    ChatResponse as V3ChatResponse,
    ChatMessage,
    Role,
)

from .classifier import Scenario, classify
from .personas import Persona, get_persona_prompt
from .preflight import detect_entry_point
from .tool_use_loop import run_tool_use_loop
from .tools.registry import v4_tool_registry
from .transaction import pipeline_run_transaction
from .trees import TREES, get_tree
from .trees.base import LeafConfig, TreeNode

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# 公開 dataclass（給內部 / 測試 / c-end BFF 直呼用；/chat 端點走 pydantic 版）
# ----------------------------------------------------------------------

@dataclass
class ChatRequest:
    project_id: str
    message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    client_session_id: Optional[str] = None
    attachments: list[dict[str, Any]] | None = None
    # 給 /chat/tree-choice 用：跳過 classifier + tree walk 直接用這個 leaf 跑
    forced_leaf_config: Optional[dict[str, Any]] = None
    # 給 /chat/tree-choice 用：tree walk 走到非葉子節點時，繼續從這個節點走
    tree_id: Optional[str] = None
    tree_node_id: Optional[str] = None
    # 給 __other__ escape 用：強制跳過 classifier 走 free-form。
    # 否則 chat() 會看 history 含 widget 又重判場景跳回 tree，造成循環。
    bypass_classifier: bool = False


@dataclass
class ChatResponse:
    content: str
    session_id: str
    message_id: Optional[str] = None
    widgets: list[dict[str, Any]] | None = None
    tool_results: list[dict[str, Any]] | None = None
    tree_pending: bool = False  # True 時表示在樹中等使用者答 widget


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _normalize_request(request: Any) -> ChatRequest:
    """把 V3 pydantic ChatRequest 或 V4 dataclass 統一成 V4 dataclass。"""
    if isinstance(request, ChatRequest):
        return request
    # 假設是 pydantic V3 ChatRequest（或 dict）
    if isinstance(request, dict):
        return ChatRequest(
            project_id=request.get("project_id"),
            message=request.get("message", ""),
            session_id=request.get("session_id"),
            user_id=request.get("user_id"),
            client_session_id=request.get("client_session_id"),
            attachments=request.get("attachments") or request.get("images"),
        )
    return ChatRequest(
        project_id=getattr(request, "project_id"),
        message=getattr(request, "message", ""),
        session_id=getattr(request, "session_id", None),
        user_id=getattr(request, "user_id", None),
        client_session_id=getattr(request, "client_session_id", None),
        attachments=getattr(request, "attachments", None) or getattr(request, "images", None),
        forced_leaf_config=getattr(request, "forced_leaf_config", None),
        tree_id=getattr(request, "tree_id", None),
        tree_node_id=getattr(request, "tree_node_id", None),
        bypass_classifier=bool(getattr(request, "bypass_classifier", False)),
    )


def _resolve_user_id(user_id: Optional[str]) -> str:
    """解析 user_id：給定就用；否則 fallback demo user。"""
    if user_id:
        return user_id
    demo = crud.get_user_by_email(DEMO_USER_EMAIL)
    if not demo:
        raise RuntimeError(
            f"找不到 demo user ({DEMO_USER_EMAIL})；請先執行 seed 或顯式傳 user_id"
        )
    return demo["id"]


def _ensure_session(
    session_id: Optional[str],
    project_id: str,
    user_id: str,
    client_session_id: Optional[str] = None,
) -> str:
    """確保 session 存在；不存在就建。

    若 client_session_id 提供，會 attach 進新 session 的 metadata（idempotency 補強
    Phase 2 再實作真正的查詢）。
    """
    if session_id:
        existing = crud.get_session(session_id)
        if existing:
            return existing["id"]
        logger.warning("[v4_chat] session_id %s 不存在，建新 session", session_id)
    new_session = crud.create_session(
        project_id=project_id,
        user_id=user_id,
        session_type="freeform",
    )
    sid = new_session["id"]
    if client_session_id:
        # 寫進 metadata 但不查（後續 phase 補 idempotency lookup）
        logger.debug("[v4_chat] new session %s linked to client_session_id=%s", sid, client_session_id)
    return sid


def _build_system_prompt(base_prompt: Optional[str], persona: Persona) -> str:
    """把 base prompt + persona 段組成 system prompt。"""
    parts: list[str] = []
    if base_prompt:
        parts.append(base_prompt.strip())
    parts.append(get_persona_prompt(persona).strip())
    return "\n\n".join(parts)


def _to_v3_response(
    sid: str,
    text: str,
    message_id: Optional[str],
    widgets: list[dict[str, Any]] | None,
    tool_results: list[dict[str, Any]] | None,
    metadata: dict[str, Any] | None = None,
) -> V3ChatResponse:
    return V3ChatResponse(
        session_id=sid,
        message=ChatMessage(role=Role.ASSISTANT, content=text or ""),
        message_id=message_id,
        widgets=widgets or [],
        tool_results=tool_results or [],
        metadata=metadata or {},
    )


# ----------------------------------------------------------------------
# Main entry
# ----------------------------------------------------------------------

async def chat(request: Any) -> V3ChatResponse:
    """V4 chat 主入口。

    參數可以是：
      - V3 pydantic ChatRequest（/chat 端點直接傳）
      - V4 ChatRequest dataclass
      - 任何具相同欄位的物件 / dict

    回傳 V3 ChatResponse pydantic 物件，跟 V3 路徑完全相容。

    Phase 1 只支援 free-form 場景。
    """
    req = _normalize_request(request)

    user_id = _resolve_user_id(req.user_id)
    session_id = _ensure_session(req.session_id, req.project_id, user_id, req.client_session_id)

    # 載入 history（exclude_last_user：避免後面 messages.append(user) 重複）
    try:
        history = await load_history(session_id, exclude_last_user=True)
    except Exception as e:  # noqa: BLE001
        logger.warning("[v4_chat] load_history failed: %s", e)
        history = []

    # 載入 active prompt
    try:
        base_prompt = await load_active_prompt(req.project_id, session_id=session_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("[v4_chat] load_active_prompt failed: %s", e)
        base_prompt = None

    # Light classifier — bypass_classifier=True 時強制走 free-form
    # （供 __other__ escape 使用，避免 history 含 widget 又被重判回 tree）
    if req.bypass_classifier:
        from .classifier import ClassificationResult as _CR
        classification = _CR(scenario=Scenario.FREE_FORM, reason="bypass_classifier=True")
    else:
        classification = await classify(
            message=req.message,
            history=history,
            attachments=req.attachments,
            game_state=None,  # Phase 5 才接 in-game state
        )

    async with pipeline_run_transaction(session_id, user_id, req.project_id) as run:
        # ============================================================
        # Tree-choice 延續路徑：forced_leaf_config / tree_id+tree_node_id
        # 由 /chat/tree-choice endpoint 設定，跳過 classifier
        # ============================================================
        if req.forced_leaf_config is not None:
            leaf = LeafConfig(**req.forced_leaf_config) if isinstance(req.forced_leaf_config, dict) else req.forced_leaf_config
            return await _execute_leaf(
                req=req, run=run, session_id=session_id, user_id=user_id,
                base_prompt=base_prompt, history=history, leaf=leaf,
                scenario_name=req.tree_id or "tree_choice",
            )

        if req.tree_id and req.tree_node_id:
            # 從指定 tree node 繼續 walk（preflight 已預判 → 此節點是 widget 待答）
            tree = get_tree(req.tree_id)
            current = tree.get_node(req.tree_node_id)
            return await _walk_or_widget(
                req=req, run=run, session_id=session_id, user_id=user_id,
                base_prompt=base_prompt, history=history,
                tree=tree, current=current, scenario_name=req.tree_id,
            )

        # ============================================================
        # Free-form 路徑
        # ============================================================
        if classification.scenario == Scenario.FREE_FORM:
            return await _run_free_form(
                req=req, run=run, session_id=session_id, user_id=user_id,
                base_prompt=base_prompt, history=history, classification=classification,
            )

        # ============================================================
        # 複雜場景 → 樹路徑（preflight 智慧起始點 → tree walk → leaf or widget）
        # ============================================================
        scenario_key = classification.scenario.value
        if scenario_key not in TREES:
            logger.warning("[v4_chat] scenario %s not in TREES, falling back to free_form", scenario_key)
            return await _run_free_form(
                req=req, run=run, session_id=session_id, user_id=user_id,
                base_prompt=base_prompt, history=history, classification=classification,
            )

        tree = get_tree(scenario_key)

        # 智慧起始點偵測（hint from classifier 優先；否則 preflight LLM 跑）
        entry_node_id: str = classification.tree_entry_node or tree.root_id
        implied_choices: dict[str, str] = {}
        try:
            entry_node_id, implied_choices = await detect_entry_point(
                tree=tree, message=req.message, history=history,
                project_id=req.project_id, session_id=session_id,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[v4_chat] preflight failed, using root: %s", e)
            entry_node_id = tree.root_id
            implied_choices = {}

        try:
            current = tree.get_node(entry_node_id)
        except KeyError:
            logger.warning("[v4_chat] preflight returned invalid node %s, using root", entry_node_id)
            current = tree.get_node(tree.root_id)

        # 套用 implied_choices 一直走到無法再走（葉子或下一個未答節點）
        for node_id, choice_id in (implied_choices or {}).items():
            if current.id != node_id or current.is_leaf:
                break
            try:
                current = tree.advance(current.id, choice_id)
            except (ValueError, KeyError):
                break
            if current.is_leaf:
                break

        return await _walk_or_widget(
            req=req, run=run, session_id=session_id, user_id=user_id,
            base_prompt=base_prompt, history=history,
            tree=tree, current=current, scenario_name=scenario_key,
        )

    # （unreachable — 上面 async-with 已 return）
    return _to_v3_response(sid=session_id, text="", message_id=None, widgets=None, tool_results=None)


# ----------------------------------------------------------------------
# Tree path helpers
# ----------------------------------------------------------------------

async def _walk_or_widget(*, req, run, session_id, user_id, base_prompt, history, tree, current: TreeNode, scenario_name: str):
    """如果 current 是葉子 → 走 leaf；否則發 widget 等使用者答。"""
    if current.is_leaf and current.leaf_config is not None:
        return await _execute_leaf(
            req=req, run=run, session_id=session_id, user_id=user_id,
            base_prompt=base_prompt, history=history, leaf=current.leaf_config,
            scenario_name=scenario_name,
        )

    # 非葉子 — 發 widget 等使用者答
    widget = current.to_widget()
    widget["tree_id"] = tree.id
    widget["node_id"] = current.id
    widget["blocking"] = bool(current.blocking)

    preamble = current.preamble_text or current.question or ""

    run.stage_user_message(
        session_id=session_id,
        content=req.message,
        attachments=req.attachments,
        metadata={
            "client_session_id": req.client_session_id,
        } if req.client_session_id else None,
    )
    run.stage_assistant_message(
        session_id=session_id,
        text=preamble,
        widgets=[widget],
        metadata={
            "tree_pending": tree.id,
            "node_id": current.id,
            "scenario": scenario_name,
            "engine_version": "v4",
        },
    )
    await run.commit()

    return _to_v3_response(
        sid=session_id,
        text=preamble,
        message_id=run.staged_assistant_message_id,
        widgets=[widget],
        tool_results=None,
        metadata={
            "tree_pending": tree.id,
            "node_id": current.id,
            "scenario": scenario_name,
            "engine_version": "v4",
        },
    )


async def _execute_leaf(*, req, run, session_id, user_id, base_prompt, history, leaf: LeafConfig, scenario_name: str):
    """走葉子配置：subset tools + persona + system_prompt_segment + main LLM。"""
    persona_name = (leaf.persona or "coach").lower()
    try:
        persona = Persona(persona_name)
    except ValueError:
        persona = Persona.COACH

    parts: list[str] = []
    if base_prompt:
        parts.append(base_prompt.strip())
    parts.append(get_persona_prompt(persona).strip())
    if leaf.system_prompt_segment:
        parts.append(leaf.system_prompt_segment.strip())
    system_prompt = "\n\n".join(parts)

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for m in history:
        role = m.get("role")
        if role in ("user", "assistant", "system"):
            messages.append({"role": role, "content": m.get("content") or ""})
    messages.append({"role": "user", "content": req.message})

    tools = v4_tool_registry.list_for_chat(
        project_id=req.project_id,
        subset=leaf.tools or [],
        tenant_id=None,
        include_db_tools=False,
    )

    result = await run_tool_use_loop(
        messages=messages,
        tools=tools,
        project_id=req.project_id,
        session_id=session_id,
        user_id=user_id,
        tenant_id=None,
        emit_progress=run.emit_sse,
        span_label=f"v4_chat/{scenario_name}/{persona.value}",
    )

    clean_text = result.clean_text or ""
    widgets = result.widgets or []
    tool_results = result.tool_results or []

    run.stage_user_message(
        session_id=session_id,
        content=req.message,
        attachments=req.attachments,
        metadata={
            "client_session_id": req.client_session_id,
        } if req.client_session_id else None,
    )
    run.stage_assistant_message(
        session_id=session_id,
        text=clean_text,
        tool_results=tool_results,
        widgets=widgets,
        metadata={
            "persona": persona.value,
            "scenario": scenario_name,
            "iterations": result.iterations,
            "stop_reason": result.stop_reason,
            "usage": result.usage,
            "tools_used": leaf.tools or [],
            "engine_version": "v4",
        },
    )
    await run.commit()

    return _to_v3_response(
        sid=session_id,
        text=clean_text,
        message_id=run.staged_assistant_message_id,
        widgets=widgets,
        tool_results=tool_results,
        metadata={
            "persona": persona.value,
            "scenario": scenario_name,
            "engine_version": "v4",
            "iterations": result.iterations,
            "stop_reason": result.stop_reason,
        },
    )


async def _run_free_form(*, req, run, session_id, user_id, base_prompt, history, classification):
    """Free-form 路徑：coach persona，暴露最少工具給 LLM 自決。

    工具策略（Phase 1 → Phase 2 過渡）：
      - subset=["kb_search"] 給概念問答能引用 KB
      - 其他重工具（calc_*, get_*）不暴露 — 它們屬於樹的葉子場景
        如果在 free-form 暴露，LLM 容易亂呼叫導致 30-60 秒 latency，
        而且也讓 c-end 從 SSE 等不到回應

    Phase 2+ 再考慮：context-aware tool subset（例如有手牌 attachment 才開
    calc_equity）。
    """
    persona = Persona.COACH
    system_prompt = _build_system_prompt(base_prompt, persona)

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for m in history:
        role = m.get("role")
        if role in ("user", "assistant", "system"):
            messages.append({"role": role, "content": m.get("content") or ""})
    messages.append({"role": "user", "content": req.message})

    # Free-form 只給 kb_search（概念問答用）；不給 calc_* / get_* 等重工具
    # 避免 LLM 亂呼叫拖長 latency。
    tools = v4_tool_registry.list_for_chat(
        project_id=req.project_id,
        subset=["kb_search"],
        tenant_id=None,
        include_db_tools=False,
    )

    result = await run_tool_use_loop(
        messages=messages,
        tools=tools,
        project_id=req.project_id,
        session_id=session_id,
        user_id=user_id,
        tenant_id=None,
        emit_progress=run.emit_sse,
        span_label="v4_chat/free_form",
    )

    clean_text = result.clean_text or ""
    widgets = result.widgets or []
    tool_results = result.tool_results or []

    run.stage_user_message(
        session_id=session_id,
        content=req.message,
        attachments=req.attachments,
        metadata={
            "client_session_id": req.client_session_id,
        } if req.client_session_id else None,
    )
    run.stage_assistant_message(
        session_id=session_id,
        text=clean_text,
        tool_results=tool_results,
        widgets=widgets,
        metadata={
            "persona": persona.value,
            "scenario": classification.scenario.value,
            "iterations": result.iterations,
            "stop_reason": result.stop_reason,
            "usage": result.usage,
            "engine_version": "v4",
        },
    )
    await run.commit()

    return _to_v3_response(
        sid=session_id,
        text=clean_text,
        message_id=run.staged_assistant_message_id,
        widgets=widgets,
        tool_results=tool_results,
        metadata={
            "persona": persona.value,
            "scenario": classification.scenario.value,
            "engine_version": "v4",
            "iterations": result.iterations,
            "stop_reason": result.stop_reason,
        },
    )


__all__ = ["chat", "ChatRequest", "ChatResponse"]
