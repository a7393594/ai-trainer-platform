"""
Quality Monitor — 對話品質指標與告警

設定（per-project，存於 `projects.domain_config.quality_alert`）：
  - enabled                 : bool
  - window_hours            : int  (預設 24)
  - min_samples             : int  (預設 10；不足樣本不告警)
  - wrong_ratio_threshold   : float (0-1，預設 0.3)
  - negative_ratio_threshold: float (0-1，預設 0.5；wrong + partial)
  - webhook                 : str (若空則不發；走 notifier)

API：
  - get_status(project_id) → dict 指標 + 告警等級
  - check_and_notify(project_id) → 必要時 POST 通知
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.notifier import send as notifier_send
from app.db import crud


DEFAULTS = {
    "enabled": False,
    "window_hours": 24,
    "min_samples": 10,
    "wrong_ratio_threshold": 0.3,
    "negative_ratio_threshold": 0.5,
    "webhook": "",
}


def _merged_config(project: dict | None) -> dict:
    cfg = dict(DEFAULTS)
    if not project:
        return cfg
    domain_config = (project.get("domain_config") or {})
    cfg.update(domain_config.get("quality_alert") or {})
    return cfg


def _window_iso(hours: int) -> str:
    return (datetime.now(tz=timezone.utc) - timedelta(hours=hours)).isoformat()


class QualityMonitor:

    async def get_status(self, project_id: str) -> dict:
        project = crud.get_project(project_id)
        if not project:
            return {"status": "error", "message": "Project not found"}
        cfg = _merged_config(project)

        since = _window_iso(int(cfg["window_hours"]))
        stats = crud.get_feedback_stats_window(project_id, since)
        total = stats.get("total", 0) or 0
        wrong = stats.get("wrong", 0) or 0
        partial = stats.get("partial", 0) or 0

        wrong_ratio = (wrong / total) if total else 0.0
        negative_ratio = ((wrong + partial) / total) if total else 0.0

        if not cfg["enabled"]:
            level = "disabled"
        elif total < int(cfg["min_samples"]):
            level = "insufficient_data"
        elif wrong_ratio >= float(cfg["wrong_ratio_threshold"]):
            level = "wrong_high"
        elif negative_ratio >= float(cfg["negative_ratio_threshold"]):
            level = "negative_high"
        else:
            level = "ok"

        return {
            "project_id": project_id,
            "window_hours": cfg["window_hours"],
            "since": since,
            "total": total,
            "correct": stats.get("correct", 0),
            "partial": partial,
            "wrong": wrong,
            "wrong_ratio": round(wrong_ratio, 4),
            "negative_ratio": round(negative_ratio, 4),
            "wrong_threshold": cfg["wrong_ratio_threshold"],
            "negative_threshold": cfg["negative_ratio_threshold"],
            "min_samples": cfg["min_samples"],
            "enabled": cfg["enabled"],
            "webhook_configured": bool(cfg["webhook"]),
            "level": level,
        }

    async def update_config(
        self,
        project_id: str,
        *,
        enabled: Optional[bool] = None,
        window_hours: Optional[int] = None,
        min_samples: Optional[int] = None,
        wrong_ratio_threshold: Optional[float] = None,
        negative_ratio_threshold: Optional[float] = None,
        webhook: Optional[str] = None,
    ) -> Optional[dict]:
        patch: dict = {}
        if enabled is not None:
            patch["enabled"] = bool(enabled)
        if window_hours is not None:
            patch["window_hours"] = max(1, int(window_hours))
        if min_samples is not None:
            patch["min_samples"] = max(1, int(min_samples))
        if wrong_ratio_threshold is not None:
            patch["wrong_ratio_threshold"] = max(0.0, min(1.0, float(wrong_ratio_threshold)))
        if negative_ratio_threshold is not None:
            patch["negative_ratio_threshold"] = max(0.0, min(1.0, float(negative_ratio_threshold)))
        if webhook is not None:
            patch["webhook"] = str(webhook)
        if not patch:
            return None
        return crud.update_project_config(project_id, {"quality_alert": patch})

    async def check_and_notify(self, project_id: str) -> dict:
        status = await self.get_status(project_id)
        if status.get("status") == "error":
            return status
        if status["level"] in ("disabled", "insufficient_data", "ok"):
            return {**status, "notified": False, "reason": status["level"]}

        project = crud.get_project(project_id)
        cfg = _merged_config(project)
        webhook = cfg.get("webhook") or ""
        if not webhook:
            return {**status, "notified": False, "reason": "no webhook configured"}

        fmt = None
        if project:
            tenant = crud.get_tenant(project.get("tenant_id") or "")
            fmt = ((tenant or {}).get("settings") or {}).get("notification_format")

        data = {
            "project_id": project_id,
            "level": status["level"],
            "window_hours": status["window_hours"],
            "total": status["total"],
            "wrong_ratio": status["wrong_ratio"],
            "negative_ratio": status["negative_ratio"],
            "wrong_threshold": status["wrong_threshold"],
            "negative_threshold": status["negative_threshold"],
        }
        ok, detail = await notifier_send(webhook, "ait.quality_alert", data, fmt=fmt)
        return {**status, "notified": ok, "webhook_detail": detail}


quality_monitor = QualityMonitor()
