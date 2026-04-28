"""V4 chat tools — 工具註冊器 + builtin 工具 + 共用 schemas。

公開介面：
  - v4_tool_registry：全域 registry singleton（已自動載入 BUILTIN_TOOLS）
  - BuiltinTool：內建工具描述 NamedTuple

Import 此 package 時會自動把 builtin/ 下所有工具註冊進 v4_tool_registry。
"""
import logging

from .registry import v4_tool_registry, V4ToolRegistry  # noqa: F401
from .schemas import BuiltinTool  # noqa: F401

logger = logging.getLogger(__name__)


def _register_builtins() -> None:
    """把 builtin/__init__.py 的 BUILTIN_TOOLS 全部註冊到 registry。"""
    try:
        from .builtin import BUILTIN_TOOLS
    except Exception as e:  # noqa: BLE001
        logger.warning("[v4_tools] BUILTIN_TOOLS import failed: %s", e)
        return

    registered = 0
    for tool in BUILTIN_TOOLS:
        try:
            if isinstance(tool, dict):
                name = tool["name"]
                fn = tool["execute"]
                schema = tool.get("input_schema") or {}
                desc = tool.get("description") or ""
            else:
                name = getattr(tool, "name")
                fn = getattr(tool, "fn", None) or getattr(tool, "execute")
                schema = getattr(tool, "schema", None) or getattr(tool, "input_schema", {})
                desc = getattr(tool, "description", "")

            v4_tool_registry.register_builtin(
                name=name, fn=fn, schema=schema, description=desc,
            )
            registered += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("[v4_tools] failed to register %r: %s", tool, e)

    logger.info("[v4_tools] registered %d builtin tools", registered)


_register_builtins()
