"""
Embed API — for iframe/JS-SDK integrations.

Authentication: X-Embed-Token header (or ?token= query param)
All endpoints enforce project_id must be in ctx.allowed_project_ids.
Rate limiting on chat endpoints (Phase 2).
Usage logging on all endpoints (Phase 2).
"""
import json
import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.auth.context import AuthContext, require_embed_auth
from app.core.auth.rate_limit import check_rate_limit
from app.core.auth.usage_logger import log_usage, UsageTimer
from app.core.orchestrator.agent import AgentOrchestrator
from app.core.llm_router.router import stream_chat_completion
from app.models.schemas import ChatRequest, ChatResponse
from app.db import crud

router = APIRouter()
orchestrator = AgentOrchestrator()


def _resolve_target_project(ctx: AuthContext, req_project_id: str | None) -> str:
    """Resolve target project_id — fallback to primary, enforce allowlist."""
    target = req_project_id or ctx.project_id
    if not ctx.can_access_project(target):
        raise HTTPException(
            status_code=403,
            detail=f"Token does not grant access to project {target}",
        )
    return target


class EmbedChatRequest(BaseModel):
    """Request body for /embed/chat.

    project_id is optional — when omitted, falls back to the token's primary project.
    When provided, must be within the token's allowed_project_ids.
    """
    message: str = Field(..., max_length=10000)
    session_id: str | None = None
    external_user_id: str | None = None
    project_id: str | None = None


class EmbedCreateSessionRequest(BaseModel):
    project_id: str | None = None
    external_user_id: str | None = None
    session_type: str = "freeform"


@router.get("/projects")
async def embed_list_projects(
    ctx: AuthContext = Depends(require_embed_auth(scope="chat")),
):
    """List projects this token can access."""
    with UsageTimer() as timer:
        rows = crud.list_projects_by_ids(ctx.allowed_project_ids)
        by_id = {r["id"]: r for r in rows}
        ordered = [by_id[p] for p in ctx.allowed_project_ids if p in by_id]
        result = {
            "projects": [
                {
                    "id": p["id"],
                    "name": p.get("name"),
                    "description": p.get("description"),
                    "is_primary": p["id"] == ctx.project_id,
                }
                for p in ordered
            ]
        }
    log_usage(ctx, "/embed/projects", "GET", 200, latency_ms=timer.elapsed_ms)
    return result


@router.get("/sessions")
async def embed_list_sessions(
    project_id: str | None = Query(default=None),
    external_user_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    ctx: AuthContext = Depends(require_embed_auth(scope="chat")),
):
    """List sessions for the given project filtered by external user."""
    with UsageTimer() as timer:
        target_pid = _resolve_target_project(ctx, project_id)
        user = crud.get_or_create_external_user(ctx.tenant_id, external_user_id)
        sessions = crud.list_sessions(target_pid, user_id=user["id"], limit=limit)
        result = {
            "project_id": target_pid,
            "external_user_id": external_user_id,
            "sessions": [
                {
                    "id": s["id"],
                    "session_type": s.get("session_type"),
                    "started_at": s.get("started_at"),
                    "ended_at": s.get("ended_at"),
                }
                for s in sessions
            ],
        }
    log_usage(ctx, "/embed/sessions", "GET", 200, latency_ms=timer.elapsed_ms, project_id=target_pid)
    return result


@router.post("/sessions")
async def embed_create_session(
    req: EmbedCreateSessionRequest,
    ctx: AuthContext = Depends(require_embed_auth(scope="chat")),
):
    """Explicitly create a new session."""
    with UsageTimer() as timer:
        target_pid = _resolve_target_project(ctx, req.project_id)
        user = crud.get_or_create_external_user(ctx.tenant_id, req.external_user_id)
        session = crud.create_session(target_pid, user["id"], req.session_type)
        result = {
            "session_id": session["id"],
            "project_id": target_pid,
            "started_at": session.get("started_at"),
        }
    log_usage(ctx, "/embed/sessions", "POST", 200, latency_ms=timer.elapsed_ms, project_id=target_pid)
    return result


@router.post("/chat", response_model=ChatResponse)
async def embed_chat(
    req: EmbedChatRequest,
    ctx: AuthContext = Depends(require_embed_auth(scope="chat")),
):
    """Non-streaming chat endpoint for embed integrations. Rate-limited."""
    # Rate limit check (only on chat endpoints that consume LLM tokens)
    check_rate_limit(ctx)

    with UsageTimer() as timer:
        try:
            target_pid = _resolve_target_project(ctx, req.project_id)
            user = crud.get_or_create_external_user(ctx.tenant_id, req.external_user_id)

            internal_req = ChatRequest(
                project_id=target_pid,
                session_id=req.session_id,
                user_id=user["id"],
                message=req.message,
            )
            response = await orchestrator.process(internal_req)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Approximate token counts
    tokens_in = len(req.message)
    tokens_out = len(response.message.content) if response.message else 0
    log_usage(ctx, "/embed/chat", "POST", 200,
              tokens_in=tokens_in, tokens_out=tokens_out,
              latency_ms=timer.elapsed_ms, project_id=target_pid)
    return response


@router.post("/chat/stream")
async def embed_chat_stream(
    req: EmbedChatRequest,
    ctx: AuthContext = Depends(require_embed_auth(scope="chat")),
):
    """Streaming chat endpoint (SSE). Rate-limited."""
    # Rate limit check
    check_rate_limit(ctx)

    target_pid = _resolve_target_project(ctx, req.project_id)
    user = crud.get_or_create_external_user(ctx.tenant_id, req.external_user_id)
    user_id = user["id"]

    # Get or create session
    session_id = req.session_id
    if session_id:
        existing = crud.get_session(session_id)
        if not existing or existing.get("project_id") != target_pid:
            raise HTTPException(status_code=404, detail="Session not found for this project")
    else:
        session = crud.create_session(target_pid, user_id, "freeform")
        session_id = session["id"]

    # Store user message
    crud.create_message(session_id, "user", req.message)

    # Build LLM messages
    messages = []
    prompt = crud.get_active_prompt(target_pid)
    if prompt:
        messages.append({"role": "system", "content": prompt["content"]})

    history = crud.list_messages(session_id)
    messages.extend([
        {"role": m["role"], "content": m["content"]}
        for m in history if m["role"] in ("user", "assistant")
    ])

    start_time = time.monotonic()
    tokens_in = len(req.message)

    async def generate():
        full = ""
        yield f"data: {json.dumps({'session_id': session_id, 'project_id': target_pid})}\n\n"
        try:
            async for chunk in stream_chat_completion(
                messages=messages,
                model="claude-sonnet-4-20250514",
            ):
                full += chunk
                yield f"data: {json.dumps({'content': chunk})}\n\n"

            msg = crud.create_message(session_id, "assistant", full)
            yield f"data: {json.dumps({'done': True, 'message_id': msg['id']})}\n\n"

            # Log usage after stream completes (approximate token count)
            latency_ms = int((time.monotonic() - start_time) * 1000)
            log_usage(ctx, "/embed/chat/stream", "POST", 200,
                      tokens_in=tokens_in, tokens_out=len(full),
                      latency_ms=latency_ms, project_id=target_pid)
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            latency_ms = int((time.monotonic() - start_time) * 1000)
            log_usage(ctx, "/embed/chat/stream", "POST", 500,
                      tokens_in=tokens_in, latency_ms=latency_ms, project_id=target_pid)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/session/{session_id}/history")
async def embed_session_history(
    session_id: str,
    ctx: AuthContext = Depends(require_embed_auth(scope="chat")),
):
    """Get message history for a session. Must belong to one of the token's allowed projects."""
    with UsageTimer() as timer:
        session = crud.get_session(session_id)
        if not session or not ctx.can_access_project(session.get("project_id") or ""):
            raise HTTPException(status_code=404, detail="Session not found")

        messages = crud.list_messages(session_id)
        result = {
            "session_id": session_id,
            "project_id": session.get("project_id"),
            "messages": [
                {"id": m["id"], "role": m["role"], "content": m["content"], "created_at": m["created_at"]}
                for m in messages
                if m["role"] in ("user", "assistant")
            ],
        }
    log_usage(ctx, "/embed/session/history", "GET", 200, latency_ms=timer.elapsed_ms)
    return result
