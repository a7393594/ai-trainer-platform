"""
Workflow Template Library — 常見場景的預製樣板

每個樣板包含：
  id / name / description / trigger_description / steps

使用：
  - list_templates() 供前端選單
  - instantiate(project_id, template_id, overrides) → 建立 workflow
"""
from __future__ import annotations

from copy import deepcopy
from typing import Optional

from app.db import crud


TEMPLATES: list[dict] = [
    {
        "id": "support_escalation",
        "name": "客服升級流程",
        "description": "偵測負面情緒或明確要求 → 建立 handoff → 通知真人",
        "trigger_description": "使用者表達強烈不滿或直接要求真人客服",
        "steps": [
            {
                "id": "step_handoff",
                "type": "action",
                "kind": "tool_call",
                "comment": "可綁定 mcp/tool 實際建立 handoff 記錄",
                "params": {"reason": "auto-escalated from workflow"},
            },
            {
                "id": "step_reply",
                "type": "action",
                "kind": "set",
                "value": {"reply": "已為您安排真人客服，稍後會與您聯繫。"},
            },
        ],
    },
    {
        "id": "refund_request",
        "name": "退款請求流程",
        "description": "驗證訂單 → 金額判斷（< $100 直批 / 否則轉審核） → 回覆",
        "trigger_description": "使用者請求退款",
        "steps": [
            {
                "id": "verify_order",
                "type": "action",
                "kind": "set",
                "output_var": "order",
                "value": {"verified": True, "amount": 0},
                "comment": "實務上改綁 db_query 工具取得真實訂單",
            },
            {
                "id": "amount_branch",
                "type": "if",
                "condition": "order['verified'] and order['amount'] <= 100",
                "then": [
                    {"id": "auto_approve", "type": "action", "kind": "set",
                     "value": {"reply": "小額退款已自動核准，將在 3 天內退回。"}},
                ],
                "else": [
                    {"id": "queue_review", "type": "action", "kind": "set",
                     "value": {"reply": "已提交人工審核，24 小時內回覆。"}},
                ],
            },
        ],
    },
    {
        "id": "knowledge_fallback",
        "name": "知識庫回答流程",
        "description": "找不到信心答案 → 告知並建立 handoff 或追問",
        "trigger_description": "使用者詢問未涵蓋的領域問題",
        "steps": [
            {
                "id": "note_uncovered",
                "type": "action",
                "kind": "set",
                "output_var": "coverage",
                "value": {"covered": False},
            },
            {
                "id": "covered_branch",
                "type": "if",
                "condition": "coverage['covered']",
                "then": [
                    {"id": "answer", "type": "action", "kind": "set",
                     "value": {"reply": "以下是依知識庫整理的答案..."}},
                ],
                "else": [
                    {"id": "ask_followup", "type": "action", "kind": "set",
                     "value": {"reply": "能再提供一些細節嗎？這有助於我給您更精確的答案。"}},
                ],
            },
        ],
    },
    {
        "id": "nps_survey",
        "name": "NPS 問卷收集",
        "description": "每三次對話觸發一次，收集評分與原因",
        "trigger_description": "對話三次後詢問 NPS",
        "steps": [
            {"id": "score", "type": "action", "kind": "set",
             "value": {"reply": "想請問您對這次對話的推薦度 (0-10)？"}},
            {"id": "reason", "type": "action", "kind": "set",
             "value": {"reply": "能簡單分享原因嗎？"}},
        ],
    },
]


def list_templates() -> list[dict]:
    # Shallow copy without steps bodies to keep payload small
    return [
        {"id": t["id"], "name": t["name"], "description": t["description"], "step_count": len(t["steps"])}
        for t in TEMPLATES
    ]


def get_template(template_id: str) -> Optional[dict]:
    return next((t for t in TEMPLATES if t["id"] == template_id), None)


def instantiate(
    project_id: str,
    template_id: str,
    name_override: Optional[str] = None,
    trigger_override: Optional[str] = None,
) -> Optional[dict]:
    tpl = get_template(template_id)
    if not tpl:
        return None
    steps = deepcopy(tpl["steps"])
    return crud.create_workflow(
        project_id=project_id,
        name=name_override or tpl["name"],
        trigger_description=trigger_override or tpl["trigger_description"],
        steps_json=steps,
    )
