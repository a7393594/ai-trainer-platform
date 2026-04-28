"""
Tool: analyze_screenshot
Description: 解析撲克截圖出結構化手牌記錄(hand / board / position / action / players / stacks / pot)。
            底層用 Claude Haiku vision。
"""
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

TOOL_NAME = "analyze_screenshot"

TOOL_DESCRIPTION = (
    "Parse a poker screenshot into a structured hand record. "
    "Provide image_url (base64 data URL or external URL). "
    "Optional 'hint' lets the user say e.g. 'I am BTN' to disambiguate. "
    "Returns hand_record with hand, board, position, action, players, stacks, pot."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "image_url": {
            "type": "string",
            "description": "Image to analyse — either an https:// URL or a data:image/...;base64,... URL.",
        },
        "hint": {
            "type": "string",
            "description": "Optional user-supplied hint, e.g. 'I am BTN with 100bb'.",
        },
    },
    "required": ["image_url"],
}


_SYSTEM_PROMPT = (
    "You are a poker screenshot parser. The user will send a poker hand screenshot. "
    "Extract a structured JSON object with the following shape (omit fields you cannot read):\n"
    "{\n"
    '  "hand": "AsKd",            // hero hole cards, two-character notation\n'
    '  "board": "JhTs2c",         // community cards, may be 0/3/4/5 cards\n'
    '  "position": "BTN",         // SB/BB/UTG/MP/HJ/CO/BTN\n'
    '  "action": "raise 2.5bb",   // hero\'s last action if visible\n'
    '  "players": 6,              // number of seated players\n'
    '  "stacks": {"BTN": 100, "BB": 95, ...},  // in bb if known, else chips\n'
    '  "pot": 6.5                 // current pot in bb if known\n'
    "}\n"
    "Return ONLY the JSON object, no prose."
)


async def execute(
    params: dict,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    """Send the screenshot to Claude Haiku vision and parse the JSON reply."""
    image_url = params.get("image_url")
    hint = params.get("hint", "")
    if not image_url:
        return {"hand_record": None, "error": "image_url required"}

    try:
        from app.core.llm_router.router import chat_completion
    except Exception as e:  # pragma: no cover
        return {"hand_record": None, "error": f"llm_router unavailable: {e}"}

    user_text = "Parse this poker screenshot."
    if hint:
        user_text += f"\n\nHint from player: {hint}"

    # LiteLLM/OpenAI-style vision content blocks. For Anthropic, LiteLLM converts.
    # We pass image as image_url block (works for both data: URLs and https URLs).
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": user_text},
            ],
        },
    ]

    try:
        response = await chat_completion(
            messages=messages,
            model="claude-haiku-4-5-20251001",
            temperature=0.1,
            max_tokens=1000,
            tenant_id=tenant_id,
            project_id=project_id,
            session_id=session_id,
            span_label="analyze_screenshot",
        )
        text = response.choices[0].message.content or ""
    except Exception as e:
        logger.warning("analyze_screenshot vision call failed: %s", e)
        # TODO: when vision API stabilises, wire in better error reporting.
        return {"hand_record": None, "error": f"vision call failed: {e}"}

    # Strip code fences if any.
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        # remove possible json language tag on first line
        if "\n" in text:
            first, rest = text.split("\n", 1)
            if first.lower().startswith("json"):
                text = rest

    try:
        hand_record = json.loads(text)
    except Exception as e:
        return {
            "hand_record": None,
            "error": f"could not parse JSON from model: {e}",
            "raw": text[:500],
        }

    hand_record["hint_used"] = hint or None
    return {"hand_record": hand_record}
