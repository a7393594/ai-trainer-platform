"""
Notification Channels — webhook dispatch with built-in formats

Formats:
  - slack   : Slack Block Kit (detected by hostname containing `slack.com`/`slack`)
  - generic : raw JSON payload (default)

Use-cases today:
  - budget alerts
  - hand-off requests

API:
  - format_payload(event, data, fmt) → provider-appropriate dict
  - send(url, event, data, fmt=None) → (ok, detail)
"""
from __future__ import annotations

from typing import Any, Optional, Tuple
from urllib.parse import urlparse

import httpx


def detect_format(webhook_url: str, explicit: Optional[str] = None) -> str:
    if explicit in ("slack", "generic"):
        return explicit
    try:
        host = (urlparse(webhook_url).hostname or "").lower()
    except Exception:
        host = ""
    if "slack.com" in host or host.endswith(".slack.com"):
        return "slack"
    return "generic"


def format_payload(event: str, data: dict, fmt: str) -> dict:
    if fmt == "slack":
        return _format_slack(event, data)
    return {"event": event, **data}


def _format_slack(event: str, data: dict) -> dict:
    title, summary, fields, color = _render_for_event(event, data)

    # Slack incoming webhooks accept a `text` fallback plus Block Kit `blocks`
    field_blocks = [
        {"type": "mrkdwn", "text": f"*{k}:*\n{v}"}
        for k, v in fields.items()
    ]
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": title[:150]}},
    ]
    if summary:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": summary[:3000]}})
    # Slack allows up to 10 fields per section
    if field_blocks:
        blocks.append({"type": "section", "fields": field_blocks[:10]})
    # Context line for event id
    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": f"event `{event}`"}],
    })
    return {"text": f"{title} — {summary or ''}".strip(" -"), "blocks": blocks, "attachments": [{"color": color}]}


def _render_for_event(event: str, data: dict) -> Tuple[str, str, dict, str]:
    """Map internal events to (title, summary, fields, slack-color).

    Unknown events fall back to a generic JSON dump.
    """
    if event == "ait.budget_alert":
        level = data.get("level", "?")
        pct = data.get("pct", 0)
        spent = data.get("spent_usd", 0)
        budget = data.get("budget_usd", 0)
        color = "#E01E5A" if level == "exceeded" else "#ECB22E"
        title = f"Budget {level.upper()} — {data.get('tenant_id', 'unknown')[:8]}"
        summary = f"Month {data.get('month', '?')} · spent ${spent:.2f} / ${budget:.2f} ({pct:.0%})"
        fields = {
            "Level": level,
            "Threshold": f"{data.get('threshold', 0):.0%}",
            "Spent": f"${spent:.2f}",
            "Budget": f"${budget:.2f}",
        }
        return title, summary, fields, color

    if event == "ait.handoff_requested":
        h = data.get("handoff", {})
        urgency = h.get("urgency", "normal")
        color = {"urgent": "#E01E5A", "high": "#ECB22E", "normal": "#1264A3", "low": "#6B7280"}.get(urgency, "#1264A3")
        title = f"Hand-off requested ({urgency})"
        summary = h.get("reason", "user requested human")
        fields = {
            "Tenant": (data.get("tenant_id") or "-")[:8],
            "Project": (data.get("project_id") or "-")[:8],
            "Session": (data.get("session_id") or "-")[:8],
            "Triggered by": h.get("triggered_by", "-"),
        }
        return title, summary, fields, color

    # generic fallback
    return event, "", {k: str(v)[:200] for k, v in data.items() if not isinstance(v, (dict, list))}, "#6B7280"


async def send(
    webhook_url: str,
    event: str,
    data: dict,
    fmt: Optional[str] = None,
    timeout: float = 10,
) -> Tuple[bool, Optional[str]]:
    if not webhook_url:
        return False, "no webhook configured"
    chosen = detect_format(webhook_url, fmt)
    payload = format_payload(event, data, chosen)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(webhook_url, json=payload)
        ok = 200 <= resp.status_code < 300
        return ok, None if ok else f"HTTP {resp.status_code}: {resp.text[:300]}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)
