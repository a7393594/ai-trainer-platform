"""
Budget Service — 租戶月預算追蹤與告警

設定儲存於 `tenants.settings` JSONB：
  - monthly_budget_usd        : float（月預算上限，單位 USD）
  - budget_alert_threshold    : float（告警門檻，0.0-1.0，預設 0.8）
  - budget_alert_webhook      : str（接收告警 JSON 的 POST URL）
  - budget_alert_sent_for     : str（記錄本月已觸發過的等級 "threshold"|"exceeded"，避免重複通知）

API：
  - get_status(tenant_id) → dict 當前月消費 / 百分比 / 告警等級
  - update_config(tenant_id, **kwargs) → 更新上述設定
  - check_and_notify(tenant_id) → 必要時 POST webhook，標記已發送
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.db import crud


DEFAULT_THRESHOLD = 0.8


def _month_key(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(tz=timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


class BudgetService:

    async def get_status(self, tenant_id: str) -> dict:
        tenant = crud.get_tenant(tenant_id)
        if not tenant:
            return {"status": "error", "message": "Tenant not found"}
        settings = tenant.get("settings") or {}
        budget = float(settings.get("monthly_budget_usd") or 0.0)
        threshold = float(settings.get("budget_alert_threshold") or DEFAULT_THRESHOLD)
        webhook = settings.get("budget_alert_webhook") or ""
        spent = crud.get_tenant_monthly_cost(tenant_id)
        pct = (spent / budget) if budget > 0 else 0.0
        if budget <= 0:
            level = "disabled"
        elif pct >= 1.0:
            level = "exceeded"
        elif pct >= threshold:
            level = "threshold"
        else:
            level = "ok"
        return {
            "tenant_id": tenant_id,
            "month": _month_key(),
            "budget_usd": budget,
            "spent_usd": round(spent, 4),
            "pct": round(pct, 4),
            "threshold": threshold,
            "level": level,
            "webhook_configured": bool(webhook),
            "last_alert_sent_for": settings.get("budget_alert_sent_for") or None,
            "last_alert_month": settings.get("budget_alert_month") or None,
        }

    async def update_config(
        self,
        tenant_id: str,
        monthly_budget_usd: Optional[float] = None,
        budget_alert_threshold: Optional[float] = None,
        budget_alert_webhook: Optional[str] = None,
    ) -> Optional[dict]:
        patch: dict[str, Any] = {}
        if monthly_budget_usd is not None:
            patch["monthly_budget_usd"] = float(monthly_budget_usd)
        if budget_alert_threshold is not None:
            t = float(budget_alert_threshold)
            patch["budget_alert_threshold"] = max(0.0, min(1.0, t))
        if budget_alert_webhook is not None:
            patch["budget_alert_webhook"] = str(budget_alert_webhook)
        # 任何設定異動都重置當月已發標記
        patch["budget_alert_sent_for"] = None
        patch["budget_alert_month"] = _month_key()
        return crud.update_tenant_settings(tenant_id, patch)

    async def check_and_notify(self, tenant_id: str) -> dict:
        status = await self.get_status(tenant_id)
        if status.get("level") in (None, "disabled", "ok"):
            return {**status, "notified": False, "reason": "under threshold"}

        tenant = crud.get_tenant(tenant_id)
        settings = (tenant or {}).get("settings") or {}
        webhook = settings.get("budget_alert_webhook") or ""
        current_level = status["level"]
        current_month = _month_key()

        # Reset on month change
        if settings.get("budget_alert_month") != current_month:
            crud.update_tenant_settings(
                tenant_id,
                {"budget_alert_month": current_month, "budget_alert_sent_for": None},
            )
            settings = {**settings, "budget_alert_month": current_month, "budget_alert_sent_for": None}

        already_sent = settings.get("budget_alert_sent_for")
        # 告警升級邏輯：threshold → exceeded 仍要再發一次；同級別不重發
        rank = {"threshold": 1, "exceeded": 2}
        if already_sent and rank.get(already_sent, 0) >= rank.get(current_level, 0):
            return {**status, "notified": False, "reason": f"already sent for {already_sent}"}

        ok = False
        detail: str | None = None
        if webhook:
            payload = {
                "event": "ait.budget_alert",
                "tenant_id": tenant_id,
                "level": current_level,
                "month": current_month,
                "budget_usd": status["budget_usd"],
                "spent_usd": status["spent_usd"],
                "pct": status["pct"],
                "threshold": status["threshold"],
            }
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(webhook, json=payload)
                ok = 200 <= resp.status_code < 300
                detail = None if ok else f"HTTP {resp.status_code}: {resp.text[:300]}"
            except Exception as e:  # noqa: BLE001
                ok = False
                detail = str(e)
        else:
            detail = "no webhook configured"

        if ok:
            crud.update_tenant_settings(
                tenant_id,
                {"budget_alert_sent_for": current_level, "budget_alert_month": current_month},
            )

        return {
            **status,
            "notified": ok,
            "webhook_detail": detail,
        }


budget_service = BudgetService()
