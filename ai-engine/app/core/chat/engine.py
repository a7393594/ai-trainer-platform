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
from .tool_use_loop import run_tool_use_loop
from .tools.registry import v4_tool_registry
from .transaction import pipeline_run_transaction

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

    # Light classifier — Phase 1 永遠回 FREE_FORM
    classification = await classify(
        message=req.message,
        history=history,
        attachments=req.attachments,
        game_state=None,  # Phase 5 才接 in-game state
    )

    async with pipeline_run_transaction(session_id, user_id, req.project_id) as run:
        if classification.scenario != Scenario.FREE_FORM:
            # 複雜場景 → 樹路徑（Phase 3+）
            raise NotImplementedError(
                f"V4 scenario {classification.scenario} not implemented yet (Phase 3+)"
            )

        # ============================================================
        # Free-form 路徑
        # ============================================================
        persona = Persona.COACH
        system_prompt = _build_system_prompt(base_prompt, persona)

        # 組 messages: [system, *history, {user}]
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        # 過濾掉 history 內可能的 system summary 之外的 system role，保留乾淨結構
        # （load_history 的 system summary 我們直接接受其作為 context）
        for m in history:
            role = m.get("role")
            if role in ("user", "assistant", "system"):
                messages.append({"role": role, "content": m.get("content") or ""})
        messages.append({"role": "user", "content": req.message})

        # tools（Phase 1 free-form 不暴露工具；列空陣列以利 Phase 3+ 沿用同 loop）
        tools = v4_tool_registry.list_for_chat(
            project_id=req.project_id,
            subset=[],  # Phase 1 一律不暴露工具
            tenant_id=None,
            include_db_tools=False,
        )

        # 跑 tool-use loop（Phase 1 純粹當 LLM completion 用）
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

        # Stage + commit
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
