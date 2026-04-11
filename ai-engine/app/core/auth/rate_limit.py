"""
In-memory sliding window rate limiter.

Two windows per credential:
- RPM (requests per minute): default 30
- RPD (requests per day): default 5000

Render runs a single instance, so in-memory is fine.
Phase 3+ can swap to Redis/Upstash if needed.
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.core.auth.context import AuthContext

# key = credential_id, value = deque of timestamps
_rpm_windows: dict[str, deque] = defaultdict(deque)
_rpd_windows: dict[str, deque] = defaultdict(deque)


def check_rate_limit(ctx: AuthContext) -> None:
    """
    Check rate limits for the given credential.
    Raises HTTPException(429) with Retry-After header if exceeded.
    Call this BEFORE processing the request.
    """
    now = time.time()
    cred_id = ctx.credential_id
    max_rpm = ctx.max_rpm
    max_rpd = ctx.max_rpd

    # --- RPM check ---
    rpm_window = _rpm_windows[cred_id]
    minute_ago = now - 60

    # Evict old entries
    while rpm_window and rpm_window[0] < minute_ago:
        rpm_window.popleft()

    if len(rpm_window) >= max_rpm:
        # Calculate retry-after: when the oldest entry in window expires
        retry_after = int(rpm_window[0] + 60 - now) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {max_rpm} requests per minute",
            headers={"Retry-After": str(max(retry_after, 1))},
        )

    # --- RPD check ---
    rpd_window = _rpd_windows[cred_id]
    day_ago = now - 86400

    while rpd_window and rpd_window[0] < day_ago:
        rpd_window.popleft()

    if len(rpd_window) >= max_rpd:
        retry_after = int(rpd_window[0] + 86400 - now) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {max_rpd} requests per day",
            headers={"Retry-After": str(max(retry_after, 1))},
        )

    # Record this request
    rpm_window.append(now)
    rpd_window.append(now)


def get_current_usage(credential_id: str) -> dict:
    """Get current in-memory usage counts (for debugging)."""
    now = time.time()
    rpm = _rpm_windows.get(credential_id, deque())
    rpd = _rpd_windows.get(credential_id, deque())

    # Count only non-expired entries
    rpm_count = sum(1 for t in rpm if t > now - 60)
    rpd_count = sum(1 for t in rpd if t > now - 86400)

    return {"rpm_current": rpm_count, "rpd_current": rpd_count}
