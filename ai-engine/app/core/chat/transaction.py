"""
Pipeline Run Transaction — atomic commit user_msg + assistant_msg + tool_results。

V3 的痛點：user_msg 立即寫 DB，DAG 中途死掉留孤兒 → 下一輪 history 看到使用者
問題但無對應回覆。V4 改為：所有訊息 stage 在 transaction 內，全部成功才 commit；
任一階段失敗 rollback。

接 contextvar 暴露 emit_sse 給內部 stage 廣播進度事件。

Commit 順序：
  1. user_msg
  2. assistant_msg（含 tool_results / widgets metadata）

Rollback 策略：
  - assistant_msg 寫失敗 → 視 user_msg 是否已寫
      * 已寫 → 保留（使用者訊息合法存在；下一輪 history 看到，符合 V4 設計）
      * 未寫 → 直接清掉 staged
  - user_msg 寫失敗 → 兩者都未寫 → 純清 staged

`crud.create_message` 是同步函數，async commit 內用 asyncio.to_thread 包裝。
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

from app.db import crud

logger = logging.getLogger(__name__)


class PipelineRunContext:
    """V4 一個 chat call 的 transaction 邊界。"""

    def __init__(self, session_id: Optional[str], user_id: Optional[str], project_id: str):
        self.session_id = session_id
        self.user_id = user_id
        self.project_id = project_id
        self._staged_user: Optional[dict[str, Any]] = None
        self._staged_assistant: Optional[dict[str, Any]] = None
        self._sse_emitter: Optional[Callable[[dict], Awaitable[None]]] = None

        # 寫入後填上 ID 給呼叫者讀回
        self.staged_user_message_id: Optional[str] = None
        self.staged_assistant_message_id: Optional[str] = None
        self.committed: bool = False

    # ------------------------------------------------------------------
    # Staging
    # ------------------------------------------------------------------

    def stage_user_message(
        self,
        session_id: str,
        content: str,
        attachments: list | None = None,
        metadata: dict | None = None,
    ) -> None:
        """暫存 user msg，commit() 才寫 DB。"""
        meta = dict(metadata or {})
        if attachments:
            meta.setdefault("attachments", attachments)
        self._staged_user = {
            "session_id": session_id,
            "content": content,
            "metadata": meta,
        }

    def stage_assistant_message(
        self,
        session_id: str,
        text: str,
        tool_results: list | None = None,
        widgets: list | None = None,
        metadata: dict | None = None,
    ) -> None:
        meta = dict(metadata or {})
        if tool_results:
            meta.setdefault("tool_results", tool_results)
        if widgets:
            meta.setdefault("widgets", widgets)
        self._staged_assistant = {
            "session_id": session_id,
            "content": text,
            "metadata": meta,
        }

    # ------------------------------------------------------------------
    # SSE
    # ------------------------------------------------------------------

    def set_sse_emitter(self, emitter: Callable[[dict], Awaitable[None]]) -> None:
        self._sse_emitter = emitter

    async def emit_sse(self, event: dict) -> None:
        if self._sse_emitter:
            try:
                await self._sse_emitter(event)
            except Exception as e:  # noqa: BLE001
                logger.debug("[pipeline_run] emit_sse swallowed: %s", e)

    # ------------------------------------------------------------------
    # Commit / Rollback
    # ------------------------------------------------------------------

    async def commit(self) -> None:
        """原子提交。

        順序：user_msg → assistant_msg。
        crud.create_message 為同步呼叫，包 asyncio.to_thread。
        """
        if self.committed:
            logger.warning("[pipeline_run] commit() called twice; skipping")
            return

        # === 1. user_msg ===
        if self._staged_user is not None:
            try:
                row = await asyncio.to_thread(
                    crud.create_message,
                    session_id=self._staged_user["session_id"],
                    role="user",
                    content=self._staged_user["content"],
                    metadata=self._staged_user.get("metadata") or None,
                )
                self.staged_user_message_id = (row or {}).get("id")
            except Exception as e:  # noqa: BLE001
                logger.exception("[pipeline_run] commit user_msg failed")
                # user_msg 失敗 → 直接放棄整個 commit（不嘗試 assistant_msg）
                await self.rollback()
                raise

        # === 2. assistant_msg ===
        if self._staged_assistant is not None:
            try:
                row = await asyncio.to_thread(
                    crud.create_message,
                    session_id=self._staged_assistant["session_id"],
                    role="assistant",
                    content=self._staged_assistant["content"],
                    metadata=self._staged_assistant.get("metadata") or None,
                )
                self.staged_assistant_message_id = (row or {}).get("id")
            except Exception as e:  # noqa: BLE001
                logger.exception(
                    "[pipeline_run] commit assistant_msg failed (user_msg id=%s already written)",
                    self.staged_user_message_id,
                )
                # 注意：依設計 user_msg 仍保留（合法存在）。不做 best-effort 刪除——
                # 既有 crud 沒有 delete_message helper，下一輪 history 看到使用者問題
                # 也比沒有來得好。
                raise

        self.committed = True

    async def rollback(self) -> None:
        """異常時清理 staged buffer。

        目前沒有實際 DB 反向操作（crud 無 delete_message）。Phase 1 行為：
          - 若任何訊息已寫進 DB，記錄但不嘗試刪除
          - 清掉所有 staged buffer 防止後續再 commit
        """
        if self.staged_user_message_id or self.staged_assistant_message_id:
            logger.warning(
                "[pipeline_run] rollback called after partial commit (user=%s assistant=%s) — "
                "leaving rows in DB",
                self.staged_user_message_id,
                self.staged_assistant_message_id,
            )
        self._staged_user = None
        self._staged_assistant = None


@asynccontextmanager
async def pipeline_run_transaction(
    session_id: Optional[str],
    user_id: Optional[str],
    project_id: str,
) -> AsyncIterator[PipelineRunContext]:
    ctx = PipelineRunContext(session_id, user_id, project_id)
    try:
        yield ctx
    except Exception:
        await ctx.rollback()
        raise


__all__ = ["PipelineRunContext", "pipeline_run_transaction"]
