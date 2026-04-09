"""
Embed API — for iframe/JS-SDK integrations.

Authentication: X-Embed-Token header (or ?token= query param)
All endpoints enforce project_id from the token, never from the request body.
"""
import json
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.auth.context import AuthContext, require_embed_auth
from app.core.orchestrator.agent import AgentOrchestrator
from app.core.llm_router.router import stream_chat_completion
from app.models.schemas import ChatRequest, ChatResponse, Role, ChatMessage
from app.db import crud

router = APIRouter()
orchestrator = AgentOrchestrator()


class EmbedChatRequest(BaseModel):
    """Request body for /embed/chat. Note: project_id is NOT here — comes from token."""
    message: str = Field(..., max_length=10000)
    session_id: str | None = None
    external_user_id: str | None = None  # optional: host system's user id


@router.post("/chat", response_model=ChatResponse)
async def embed_chat(
    req: EmbedChatRequest,
    ctx: AuthContext = Depends(require_embed_auth(scope="chat")),
):
    """Non-streaming chat endpoint for embed integrations."""
    try:
        # Map external user to internal ait_users
        user = crud.get_or_create_external_user(ctx.tenant_id, req.external_user_id)

        internal_req = ChatRequest(
            project_id=ctx.project_id,  # forced from token
            session_id=req.session_id,
            user_id=user["id"],
            message=req.message,
        )
        return await orchestrator.process(internal_req)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def embed_chat_stream(
    req: EmbedChatRequest,
    ctx: AuthContext = Depends(require_embed_auth(scope="chat")),
):
    """Streaming chat endpoint (SSE)."""
    user = crud.get_or_create_external_user(ctx.tenant_id, req.external_user_id)
    user_id = user["id"]

    # Get or create session
    session_id = req.session_id
    if not session_id:
        session = crud.create_session(ctx.project_id, user_id, "freeform")
        session_id = session["id"]

    # Store user message
    crud.create_message(session_id, "user", req.message)

    # Build LLM messages
    messages = []
    prompt = crud.get_active_prompt(ctx.project_id)
    if prompt:
        messages.append({"role": "system", "content": prompt["content"]})

    history = crud.list_messages(session_id)
    messages.extend([
        {"role": m["role"], "content": m["content"]}
        for m in history if m["role"] in ("user", "assistant")
    ])

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
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/session/{session_id}/history")
async def embed_session_history(
    session_id: str,
    ctx: AuthContext = Depends(require_embed_auth(scope="chat")),
):
    """Get message history for a session. Must belong to the token's project."""
    session = crud.get_session(session_id)
    if not session or session.get("project_id") != ctx.project_id:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = crud.list_messages(session_id)
    return {
        "session_id": session_id,
        "messages": [
            {"id": m["id"], "role": m["role"], "content": m["content"], "created_at": m["created_at"]}
            for m in messages
            if m["role"] in ("user", "assistant")
        ],
    }
