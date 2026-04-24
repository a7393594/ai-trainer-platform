"""Call Claude Haiku vision once per image to extract a text description.

This lets the rest of the system (DAG executor, orchestrator, tool use) continue
to work with plain-text messages. The extracted description is prepended to the
user message so the downstream planner / model sees what was in the image.
"""
from __future__ import annotations

import asyncio
import logging
import re

import litellm

from app.core.llm_router.router import _inject_api_key

logger = logging.getLogger(__name__)

# Haiku is the cheapest Claude with vision; keep cost low for a one-shot describe.
VISION_MODEL = "claude-haiku-4-5-20251001"
VISION_MAX_TOKENS = 800
VISION_TIMEOUT = 30.0

# Reasonable prompt for the poker domain — but phrased generically so it also handles
# non-poker images gracefully.
DEFAULT_PROMPT = (
    "請用繁體中文詳細描述這張圖片的內容。如果是撲克相關畫面（手牌 / 公共牌 / 桌面 / "
    "籌碼 / 獎金結構 / 盲注 / 聊天記錄），請明確標示每張牌（如 Ah、Kd、9c）、位置、"
    "下注金額、各玩家狀態等結構化資訊，方便後續 AI 分析。若非撲克相關，直接描述主題與"
    "可辨識的文字。保持精簡，不要加任何前言或結論。"
)

_DATA_URL_RE = re.compile(r"^data:(image/[a-zA-Z0-9+.-]+);base64,(.+)$", re.DOTALL)


def _parse_data_url(url: str) -> tuple[str, str] | None:
    """Return (media_type, base64_body) or None if `url` is not a data URL."""
    m = _DATA_URL_RE.match(url.strip())
    if not m:
        return None
    return m.group(1), m.group(2)


async def describe_image(image_data_url: str, tenant_id: str | None = None, prompt: str | None = None) -> str:
    """Return a text description of one image, or "" on failure.

    Accepts either a `data:image/...;base64,...` URL or a public https URL. Base64
    is sent as Anthropic-style image block; https URL is sent as OpenAI-style
    image_url block (both supported by LiteLLM).
    """
    if not image_data_url:
        return ""

    # LiteLLM unified multimodal format: image_url works for both base64 data URLs
    # and https URLs across Anthropic / OpenAI / Gemini providers.
    if not (
        image_data_url.startswith("data:image/")
        or image_data_url.startswith("http://")
        or image_data_url.startswith("https://")
    ):
        logger.warning("describe_image: unsupported image ref")
        return ""

    content_blocks = [
        {"type": "text", "text": prompt or DEFAULT_PROMPT},
        {"type": "image_url", "image_url": {"url": image_data_url}},
    ]
    kwargs: dict = {
        "model": VISION_MODEL,
        "messages": [{"role": "user", "content": content_blocks}],
        "max_tokens": VISION_MAX_TOKENS,
        "timeout": VISION_TIMEOUT,
    }
    _inject_api_key(kwargs, VISION_MODEL, tenant_id)

    try:
        response = await litellm.acompletion(**kwargs)
        return (response.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("describe_image failed: %s", str(e)[:200])
        return ""


async def describe_images(images: list[str], tenant_id: str | None = None) -> list[str]:
    """Describe N images in parallel. Results preserve input order; failures become empty strings."""
    if not images:
        return []
    tasks = [describe_image(img, tenant_id=tenant_id) for img in images]
    return await asyncio.gather(*tasks, return_exceptions=False)


def build_message_with_image_descriptions(original_message: str, descriptions: list[str]) -> str:
    """Prepend non-empty image descriptions as [圖片 1] / [圖片 2] blocks to the user message."""
    parts: list[str] = []
    for i, desc in enumerate(descriptions, 1):
        if not desc:
            continue
        parts.append(f"[圖片 {i}]\n{desc}")
    if not parts:
        return original_message
    return "\n\n".join(parts) + "\n\n" + (original_message or "")
