"""
Screenshot OCR — 牌桌截圖辨識

使用 Claude Opus 4.7 vision 解析撲克桌面截圖：
- 玩家位置、籌碼量
- 公共牌、手牌
- 底池大小、當前動作
- HUD 數字（如有）
"""
import base64
from typing import Optional
from app.core.llm_router.router import chat_completion


async def parse_table_screenshot(
    image_base64: str,
    image_type: str = "image/png",
) -> dict:
    """Parse a poker table screenshot using vision model.

    Args:
        image_base64: base64 encoded image
        image_type: MIME type

    Returns:
        {
            "players": [{"position": str, "stack": float, "cards": [str], "status": str}],
            "board": [str],
            "pot": float,
            "hero_cards": [str],
            "hero_position": str,
            "current_action": str,
            "hud_data": {...} | null,
            "client": str,  # pokerstars, ggpoker, etc.
            "confidence": float,
        }
    """
    prompt = """分析這張撲克牌桌截圖，提取以下資訊。以 JSON 格式回覆：

{
  "players": [
    {"position": "BTN/CO/MP/UTG/SB/BB", "stack": 數字(bb), "cards": ["Ah", "Kd"] 或 null, "status": "active/fold/allin/sitting_out"}
  ],
  "board": ["Ah", "Kd", "3c"] 或 [],
  "pot": 底池大小(bb),
  "hero_cards": ["手牌1", "手牌2"] 或 null,
  "hero_position": "位置",
  "current_action": "目前需要做的動作描述",
  "hud_data": {"vpip": 數字, "pfr": 數字, "hands": 數字} 或 null（如果看到 HUD overlay）,
  "client": "pokerstars/ggpoker/acr/wpn/unknown",
  "confidence": 0.0-1.0
}

注意：
- 牌用英文表示：A/K/Q/J/T/9-2 + h/d/c/s（如 Ah = 黑桃A）
- 如果看不清某些資訊，寫 null
- 如果有 HUD overlay 數字，盡量讀取
只回覆 JSON。"""

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image_type,
                        "data": image_base64,
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }
    ]

    try:
        # Use vision-capable model (Opus 4.7 preferred, fallback to Opus 4.6)
        response = await chat_completion(
            messages=messages,
            model="claude-opus-4-6",  # Will upgrade to 4.7 when available
            temperature=0.1,
            max_tokens=800,
        )
        raw = response.choices[0].message.content or "{}"

        import json
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            return json.loads(raw[start:end])
        except Exception:
            return {"error": "Failed to parse response", "raw": raw[:300], "confidence": 0}

    except Exception as e:
        return {"error": str(e), "confidence": 0}
