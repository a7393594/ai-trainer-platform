"""
Hand-off Service — 將 AI 對話升級到真人客服

設計：
  - 不新增 schema，利用 `ait_training_messages` 寫一筆 role=system 訊息，
    metadata.handoff = {status, reason, requested_at, resolved_at, resolved_by}
  - 建立時若 tenant.settings.handoff_webhook 有設，POST 通知真人客服系統
  - 支援列出「未解決」的 handoff（供客服儀表板輪詢）

API：
  - request(session_id, reason, triggered_by, urgency) : 建立 handoff + 通知
  - list_pending(tenant_id, limit) : 列出租戶底下未解決 handoff
  - resolve(handoff_message_id, resolved_by, note) : 標記已解決
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.core.notifier import send as notifier_send
from app.db import crud


class HandoffService:

    async def request(
        self,
        session_id: str,
        reason: str,
        triggered_by: str = "system",
        urgency: str = "normal",
    ) -> dict:
        session = crud.get_session(session_id)
        if not session:
            return {"status": "error", "message": "Session not found"}

        payload = {
            "status": "pending",
            "reason": (reason or "").strip() or "user requested human",
            "urgency": urgency if urgency in ("low", "normal", "high", "urgent") else "normal",
            "triggered_by": triggered_by,
            "requested_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        msg = crud.create_message(
            session_id=session_id,
            role="system",
            content=f"[HANDOFF] {payload['reason']}",
            metadata={"handoff": payload},
        )

        # Notify tenant webhook
        notified, detail = await self._notify(session, msg, payload)
        return {
            "status": "handoff_requested",
            "handoff_message_id": msg.get("id"),
            "session_id": session_id,
            "urgency": payload["urgency"],
            "notified": notified,
            "webhook_detail": detail,
        }

    async def _notify(self, session: dict, message: dict, handoff: dict) -> tuple[bool, Optional[str]]:
        project_id = session.get("project_id")
        project = crud.get_project(project_id) if project_id else None
        tenant_id = (project or {}).get("tenant_id")
        tenant = crud.get_tenant(tenant_id) if tenant_id else None
        tenant_settings = (tenant or {}).get("settings") or {}
        webhook = tenant_settings.get("handoff_webhook") or ""
        if not webhook:
            return False, "no webhook configured"

        data = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "session_id": session.get("id"),
            "handoff_message_id": message.get("id"),
            "handoff": handoff,
        }
        return await notifier_send(
            webhook, "ait.handoff_requested", data,
            fmt=tenant_settings.get("notification_format"),
        )

    async def list_pending(self, tenant_id: str, limit: int = 50) -> list[dict]:
        """列出租戶底下所有未解決的 handoff (status == pending)。"""
        from app.db.supabase import get_supabase

        db = get_supabase()
        # 先取得租戶所有 project ids
        projects = db.table("ait_projects").select("id").eq("tenant_id", tenant_id).execute().data or []
        pids = [p["id"] for p in projects]
        if not pids:
            return []
        # 取得這些 project 底下的 sessions
        sessions: list[dict] = []
        for i in range(0, len(pids), 50):
            chunk = pids[i : i + 50]
            rows = db.table("ait_training_sessions").select("id,project_id").in_("project_id", chunk).execute().data or []
            sessions.extend(rows)
        if not sessions:
            return []
        sids = [s["id"] for s in sessions]
        session_map = {s["id"]: s["project_id"] for s in sessions}

        # 取 handoff 訊息（system role + metadata.handoff.status == pending）
        pending: list[dict] = []
        for i in range(0, len(sids), 50):
            chunk = sids[i : i + 50]
            rows = (
                db.table("ait_training_messages")
                .select("id,session_id,content,metadata,created_at")
                .in_("session_id", chunk)
                .eq("role", "system")
                .order("created_at", desc=True)
                .limit(min(limit, 500))
                .execute()
            ).data or []
            for r in rows:
                meta = r.get("metadata") or {}
                h = meta.get("handoff")
                if isinstance(h, dict) and h.get("status") == "pending":
                    pending.append({
                        "id": r["id"],
                        "session_id": r["session_id"],
                        "project_id": session_map.get(r["session_id"]),
                        "created_at": r.get("created_at"),
                        "handoff": h,
                    })
        pending.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return pending[:limit]

    async def resolve(
        self,
        handoff_message_id: str,
        resolved_by: str,
        note: str = "",
    ) -> dict:
        from app.db.supabase import get_supabase

        db = get_supabase()
        existing = db.table("ait_training_messages").select("*").eq("id", handoff_message_id).execute()
        rows = existing.data or []
        if not rows:
            return {"status": "error", "message": "Handoff not found"}
        row = rows[0]
        meta = dict(row.get("metadata") or {})
        h = dict(meta.get("handoff") or {})
        if not h:
            return {"status": "error", "message": "Not a handoff message"}
        h["status"] = "resolved"
        h["resolved_at"] = datetime.now(tz=timezone.utc).isoformat()
        h["resolved_by"] = resolved_by
        if note:
            h["resolution_note"] = note[:500]
        meta["handoff"] = h
        db.table("ait_training_messages").update({"metadata": meta}).eq("id", handoff_message_id).execute()
        return {"status": "resolved", "id": handoff_message_id, "handoff": h}


handoff_service = HandoffService()
