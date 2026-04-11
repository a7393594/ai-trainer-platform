"""
Async fire-and-forget usage logger.

Writes to ait_api_usage table without blocking the request.
Uses the same asyncio.create_task(asyncio.to_thread(...)) pattern
as touch_embed_token in context.py.
"""
import asyncio
import time
from typing import Optional

from app.core.auth.context import AuthContext
from app.db import crud_usage


def log_usage(
    ctx: AuthContext,
    endpoint: str,
    method: str,
    status_code: int,
    tokens_in: int = 0,
    tokens_out: int = 0,
    latency_ms: Optional[int] = None,
    project_id: Optional[str] = None,
) -> None:
    """
    Fire-and-forget: schedule a background task to insert a usage record.
    Safe to call from sync or async context — will not block or raise.
    """
    data = {
        "tenant_id": ctx.tenant_id,
        "project_id": project_id or ctx.project_id,
        "credential_type": ctx.credential_type,
        "credential_id": ctx.credential_id,
        "endpoint": endpoint,
        "method": method,
        "status_code": status_code,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
        "origin": ctx.origin,
        "ip": ctx.ip,
    }
    try:
        asyncio.create_task(asyncio.to_thread(crud_usage.insert_usage, data))
    except Exception:
        pass  # Never break the request


class UsageTimer:
    """Context manager to measure request latency in ms."""

    def __init__(self):
        self.start: float = 0
        self.elapsed_ms: int = 0

    def __enter__(self):
        self.start = time.monotonic()
        return self

    def __exit__(self, *args):
        self.elapsed_ms = int((time.monotonic() - self.start) * 1000)
