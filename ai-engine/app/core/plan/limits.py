"""
Plan Limits — 方案式使用量上限

依 `tenants.plan` (free/pro/enterprise) 套預設上限；租戶可在 settings 覆寫。

上限指標（月）：
  - sessions_per_month
  - tokens_per_month
  - projects

API：
  - get_limits(tenant_id) → 合併後的 limits dict
  - check_usage(tenant_id) → 當月用量 + 是否超限 + 每項剩餘
  - enforce_session_create(tenant_id) → raise LimitExceeded 若不允許建立新 session
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.db import crud
from app.db.supabase import get_supabase


PLAN_DEFAULTS: dict[str, dict] = {
    "free": {
        "sessions_per_month": 100,
        "tokens_per_month": 50_000,
        "projects": 1,
    },
    "pro": {
        "sessions_per_month": 10_000,
        "tokens_per_month": 5_000_000,
        "projects": 10,
    },
    "enterprise": {
        "sessions_per_month": None,  # None = 不限制
        "tokens_per_month": None,
        "projects": None,
    },
}


class LimitExceeded(Exception):
    def __init__(self, key: str, limit: int, used: int) -> None:
        super().__init__(f"Plan limit exceeded: {key} ({used}/{limit})")
        self.key = key
        self.limit = limit
        self.used = used


def _month_start_iso() -> str:
    now = datetime.now(tz=timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


class PlanLimitsService:

    def get_limits(self, tenant_id: str) -> dict:
        tenant = crud.get_tenant(tenant_id) or {}
        plan = (tenant.get("plan") or "free").lower()
        defaults = PLAN_DEFAULTS.get(plan, PLAN_DEFAULTS["free"])
        overrides = (tenant.get("settings") or {}).get("plan_limits") or {}
        merged = {**defaults, **{k: v for k, v in overrides.items() if k in defaults}}
        return {"plan": plan, **merged}

    def _count_usage(self, tenant_id: str) -> dict:
        db = get_supabase()
        projects = db.table("ait_projects").select("id").eq("tenant_id", tenant_id).execute().data or []
        pids = [p["id"] for p in projects]
        sessions = 0
        tokens = 0
        if pids:
            since = _month_start_iso()
            for i in range(0, len(pids), 50):
                chunk = pids[i : i + 50]
                rows = (
                    db.table("ait_training_sessions").select("id,created_at")
                    .in_("project_id", chunk).gte("created_at", since).execute()
                ).data or []
                sessions += len(rows)
                usage_rows = (
                    db.table("ait_llm_usage").select("total_tokens")
                    .in_("project_id", chunk).gte("created_at", since).execute()
                ).data or []
                tokens += sum((r.get("total_tokens") or 0) for r in usage_rows)
        return {"sessions": sessions, "tokens": tokens, "projects": len(pids)}

    def check_usage(self, tenant_id: str) -> dict:
        limits = self.get_limits(tenant_id)
        usage = self._count_usage(tenant_id)

        def _remaining(key_limit: Optional[int], used: int) -> Optional[int]:
            if key_limit is None:
                return None
            return max(0, key_limit - used)

        blocked = []
        for key, used_key in [
            ("sessions_per_month", "sessions"),
            ("tokens_per_month", "tokens"),
            ("projects", "projects"),
        ]:
            lim = limits.get(key)
            used = usage.get(used_key, 0)
            if lim is not None and used >= lim:
                blocked.append({"key": key, "limit": lim, "used": used})

        return {
            "plan": limits["plan"],
            "limits": {k: v for k, v in limits.items() if k != "plan"},
            "usage": usage,
            "remaining": {
                "sessions_per_month": _remaining(limits.get("sessions_per_month"), usage["sessions"]),
                "tokens_per_month": _remaining(limits.get("tokens_per_month"), usage["tokens"]),
                "projects": _remaining(limits.get("projects"), usage["projects"]),
            },
            "blocked": blocked,
            "ok": not blocked,
        }

    def enforce_session_create(self, tenant_id: str) -> None:
        """只檢查會話數上限；projects 由 /projects 端點 enforce，tokens 僅警示不阻斷。"""
        status = self.check_usage(tenant_id)
        for item in status["blocked"]:
            if item["key"] == "sessions_per_month":
                raise LimitExceeded(item["key"], item["limit"], item["used"])

    def enforce_project_create(self, tenant_id: str) -> None:
        status = self.check_usage(tenant_id)
        for item in status["blocked"]:
            if item["key"] == "projects":
                raise LimitExceeded(item["key"], item["limit"], item["used"])


plan_limits_service = PlanLimitsService()
