"""
Public REST API — for server-to-server integrations.

Authentication: X-API-Key header (sk_live_ prefix)
Rate limited on chat endpoints. Usage logged on all endpoints.
"""
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.auth.context import AuthContext, require_api_key_auth
from app.core.auth.rate_limit import check_rate_limit
from app.core.auth.usage_logger import log_usage, UsageTimer
from app.core.orchestrator.agent import AgentOrchestrator
from app.core.llm_router.router import stream_chat_completion
from app.models.schemas import ChatRequest, ChatResponse
from app.db import crud

router = APIRouter()
orchestrator = AgentOrchestrator()


class PublicChatRequest(BaseModel):
    """Request body for /public/v1/chat."""
    message: str = Field(..., max_length=10000)
    session_id: str | None = None
    user_id: str | None = None  # caller can specify user; otherwise auto-created


@router.post("/chat", response_model=ChatResponse)
async def public_chat(
    req: PublicChatRequest,
    ctx: AuthContext = Depends(require_api_key_auth(scope="chat:write")),
):
    """Non-streaming chat. Rate-limited."""
    check_rate_limit(ctx)

    with UsageTimer() as timer:
        try:
            user_id = req.user_id
            if not user_id:
                user = crud.get_or_create_external_user(ctx.tenant_id)
                user_id = user["id"]

            internal_req = ChatRequest(
                project_id=ctx.project_id,
                session_id=req.session_id,
                user_id=user_id,
                message=req.message,
            )
            response = await orchestrator.process(internal_req)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    tokens_in = len(req.message)
    tokens_out = len(response.message.content) if response.message else 0
    log_usage(ctx, "/public/v1/chat", "POST", 200,
              tokens_in=tokens_in, tokens_out=tokens_out,
              latency_ms=timer.elapsed_ms)
    return response


@router.post("/chat/stream")
async def public_chat_stream(
    req: PublicChatRequest,
    ctx: AuthContext = Depends(require_api_key_auth(scope="chat:write")),
):
    """Streaming chat (SSE). Rate-limited."""
    check_rate_limit(ctx)

    user_id = req.user_id
    if not user_id:
        user = crud.get_or_create_external_user(ctx.tenant_id)
        user_id = user["id"]

    session_id = req.session_id
    if session_id:
        existing = crud.get_session(session_id)
        if not existing or existing.get("project_id") != ctx.project_id:
            raise HTTPException(status_code=404, detail="Session not found for this project")
    else:
        session = crud.create_session(ctx.project_id, user_id, "freeform")
        session_id = session["id"]

    crud.create_message(session_id, "user", req.message)

    messages = []
    prompt = crud.get_active_prompt(ctx.project_id)
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
        yield f"data: {json.dumps({'session_id': session_id})}\n\n"
        try:
            async for chunk in stream_chat_completion(
                messages=messages,
                model="claude-sonnet-4-20250514",
            ):
                full += chunk
                yield f"data: {json.dumps({'content': chunk})}\n\n"

            msg = crud.create_message(session_id, "assistant", full)
            yield f"data: {json.dumps({'done': True, 'message_id': msg['id']})}\n\n"

            latency_ms = int((time.monotonic() - start_time) * 1000)
            log_usage(ctx, "/public/v1/chat/stream", "POST", 200,
                      tokens_in=tokens_in, tokens_out=len(full),
                      latency_ms=latency_ms)
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            latency_ms = int((time.monotonic() - start_time) * 1000)
            log_usage(ctx, "/public/v1/chat/stream", "POST", 500,
                      tokens_in=tokens_in, latency_ms=latency_ms)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/sessions")
async def public_list_sessions(
    user_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    ctx: AuthContext = Depends(require_api_key_auth(scope="chat:read")),
):
    """List sessions for the token's project."""
    with UsageTimer() as timer:
        sessions = crud.list_sessions(ctx.project_id, user_id=user_id, limit=limit)
        result = {
            "project_id": ctx.project_id,
            "sessions": [
                {
                    "id": s["id"],
                    "user_id": s.get("user_id"),
                    "session_type": s.get("session_type"),
                    "started_at": s.get("started_at"),
                    "ended_at": s.get("ended_at"),
                }
                for s in sessions
            ],
        }
    log_usage(ctx, "/public/v1/sessions", "GET", 200, latency_ms=timer.elapsed_ms)
    return result


@router.get("/sessions/{session_id}/messages")
async def public_session_messages(
    session_id: str,
    ctx: AuthContext = Depends(require_api_key_auth(scope="chat:read")),
):
    """Get message history for a session."""
    with UsageTimer() as timer:
        session = crud.get_session(session_id)
        if not session or session.get("project_id") != ctx.project_id:
            raise HTTPException(status_code=404, detail="Session not found")

        messages = crud.list_messages(session_id)
        result = {
            "session_id": session_id,
            "project_id": ctx.project_id,
            "messages": [
                {"id": m["id"], "role": m["role"], "content": m["content"], "created_at": m["created_at"]}
                for m in messages
                if m["role"] in ("user", "assistant")
            ],
        }
    log_usage(ctx, "/public/v1/sessions/messages", "GET", 200, latency_ms=timer.elapsed_ms)
    return result
