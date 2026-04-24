"""Tenant context — request-scoped tenant_id propagated via contextvars.

Set once at HTTP middleware level (from project_id / embed token / API key),
read anywhere downstream (resolver.py, etc) without threading tenant_id through
every function signature.

PEP 567 contextvars are asyncio-aware: each request task gets its own context,
so concurrent requests don't see each other's tenant_id.

Background tasks spawned with asyncio.create_task INHERIT the current context
by default, so the tenant_id flows automatically into them too.
"""
from __future__ import annotations

import contextvars
from typing import Optional

_tenant_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "ait_tenant_id", default=None
)


def set_current_tenant(tenant_id: Optional[str]) -> contextvars.Token:
    """Set the request-scoped tenant_id. Returns a token to pass to reset()."""
    return _tenant_ctx.set(tenant_id)


def get_current_tenant() -> Optional[str]:
    """Return the current request's tenant_id, or None if unset."""
    return _tenant_ctx.get()


def reset_current_tenant(token: contextvars.Token) -> None:
    """Restore the previous tenant_id (call this in middleware finally block)."""
    _tenant_ctx.reset(token)
