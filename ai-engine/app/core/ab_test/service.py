"""
Prompt A/B Test Tracker — 簡易版 Prompt 流量分流

設計：
  - 設定存於 `projects.domain_config.ab_test`
      {
        "enabled": bool,
        "variants": [{"prompt_version_id": "...", "weight": 0.5, "label": "A"}],
        "started_at": iso
      }
  - 指派：pick_variant(session_id) → 決定 session 用哪個 version；結果寫入 session.metadata
  - 統計：summarize(project_id) → 每個 variant 的回饋分佈
  - 結束：conclude(project_id, winner_label) → 啟用勝方版本，停用 ab_test

  零 schema 變動：用 training_sessions.metadata.ab_variant 標記每 session
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from app.db import crud
from app.db.supabase import get_supabase


def _config(project: dict | None) -> dict:
    return ((project or {}).get("domain_config") or {}).get("ab_test") or {}


def _deterministic_choice(session_id: str, variants: list[dict]) -> dict:
    """Hash-based stable assignment: same session always gets same variant."""
    if not variants:
        return {}
    weights = [max(0.0, float(v.get("weight") or 0)) for v in variants]
    total = sum(weights) or 1.0
    h = int(hashlib.sha1((session_id or "").encode()).hexdigest(), 16)
    target = (h % 1_000_000) / 1_000_000 * total
    cumulative = 0.0
    for v, w in zip(variants, weights):
        cumulative += w
        if target < cumulative:
            return v
    return variants[-1]


class ABTestService:

    async def configure(
        self,
        project_id: str,
        variants: list[dict],
        enabled: bool = True,
    ) -> Optional[dict]:
        """Replace the ab_test config for a project."""
        if not isinstance(variants, list) or not variants:
            return None
        cleaned = []
        for v in variants:
            pvid = (v.get("prompt_version_id") or "").strip()
            if not pvid:
                continue
            cleaned.append({
                "prompt_version_id": pvid,
                "weight": max(0.0, float(v.get("weight") or 0)) or 1.0,
                "label": str(v.get("label") or pvid[:8]),
            })
        if not cleaned:
            return None
        config = {
            "enabled": bool(enabled),
            "variants": cleaned,
            "started_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        return crud.update_project_config(project_id, {"ab_test": config})

    async def get_status(self, project_id: str) -> dict:
        project = crud.get_project(project_id)
        cfg = _config(project)
        return {
            "project_id": project_id,
            "enabled": bool(cfg.get("enabled", False)),
            "started_at": cfg.get("started_at"),
            "variants": cfg.get("variants", []),
        }

    async def pick_variant(self, project_id: str, session_id: str) -> Optional[dict]:
        """Return the chosen variant (or None when test inactive).

        Also tags the session metadata so that downstream feedback/cost rollups
        can aggregate by variant without schema changes.
        """
        project = crud.get_project(project_id)
        cfg = _config(project)
        if not cfg.get("enabled") or not cfg.get("variants"):
            return None
        chosen = _deterministic_choice(session_id, cfg["variants"])
        if not chosen:
            return None

        try:
            db = get_supabase()
            existing = db.table("ait_training_sessions").select("metadata").eq("id", session_id).execute().data or []
            meta = (existing[0].get("metadata") if existing else {}) or {}
            # Don't overwrite an existing assignment (stay sticky across reloads)
            if not meta.get("ab_variant"):
                meta["ab_variant"] = chosen["label"]
                meta["ab_prompt_version_id"] = chosen["prompt_version_id"]
                db.table("ait_training_sessions").update({"metadata": meta}).eq("id", session_id).execute()
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] ab_test pick_variant failed to tag session: {e}")
        return chosen

    async def summarize(self, project_id: str) -> dict:
        """Aggregate feedback per variant for this project."""
        project = crud.get_project(project_id)
        cfg = _config(project)
        variants = cfg.get("variants", [])
        if not variants:
            return {"project_id": project_id, "variants": []}

        db = get_supabase()
        # Pull sessions with ab_variant tag
        sessions = (
            db.table("ait_training_sessions").select("id,metadata")
            .eq("project_id", project_id).execute().data or []
        )
        by_label: dict[str, list[str]] = {v["label"]: [] for v in variants}
        for s in sessions:
            label = (s.get("metadata") or {}).get("ab_variant")
            if label in by_label:
                by_label[label].append(s["id"])

        results = []
        for v in variants:
            sids = by_label.get(v["label"], [])
            counts = {"correct": 0, "partial": 0, "wrong": 0, "total": 0}
            if sids:
                for i in range(0, len(sids), 50):
                    chunk = sids[i : i + 50]
                    msgs = db.table("ait_training_messages").select("id").in_("session_id", chunk).eq("role", "assistant").execute().data or []
                    mids = [m["id"] for m in msgs]
                    for j in range(0, len(mids), 50):
                        mchunk = mids[j : j + 50]
                        fbs = db.table("ait_feedbacks").select("rating").in_("message_id", mchunk).execute().data or []
                        for fb in fbs:
                            r = fb.get("rating") or ""
                            if r in counts:
                                counts[r] += 1
                            counts["total"] += 1
            results.append({
                "label": v["label"],
                "prompt_version_id": v["prompt_version_id"],
                "sessions": len(sids),
                **counts,
                "correct_rate": round(counts["correct"] / counts["total"], 4) if counts["total"] else 0,
            })
        return {"project_id": project_id, "variants": results}

    async def conclude(self, project_id: str, winner_label: str) -> dict:
        """Activate the winning prompt version and disable the experiment."""
        project = crud.get_project(project_id)
        cfg = _config(project)
        winner = next((v for v in cfg.get("variants", []) if v["label"] == winner_label), None)
        if not winner:
            return {"status": "error", "message": f"Unknown variant label '{winner_label}'"}
        pvid = winner["prompt_version_id"]
        activated = crud.activate_prompt_version(pvid, project_id)
        # Disable ab_test but keep history
        crud.update_project_config(project_id, {
            "ab_test": {**cfg, "enabled": False, "concluded_label": winner_label},
        })
        return {
            "status": "concluded",
            "winner_label": winner_label,
            "activated_prompt_version_id": pvid,
            "prompt": activated,
        }


ab_test_service = ABTestService()
