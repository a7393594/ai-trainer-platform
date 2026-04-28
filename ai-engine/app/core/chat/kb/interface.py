"""V4 KB KnowledgeRetriever Protocol.

前端只看這個 interface — 不論底層實作是 in-memory、外部 vector DB 或其他形式。
"""
from typing import Optional, Protocol, runtime_checkable

from .schema import KBChunk


@runtime_checkable
class KnowledgeRetriever(Protocol):
    """KB 檢索 protocol。

    所有實作都應符合這三個方法。Phase 4 預設用 InMemoryKBIndex。
    """

    async def search(
        self,
        query: str,
        *,
        level_max: int = 2,
        top_k: int = 5,
    ) -> list[KBChunk]:
        """根據 query 找最相關的 KB chunks。

        Args:
            query: 使用者查詢字串
            level_max: 最高 prerequisite_level（過濾過於進階的條目）
            top_k: 最多回傳幾筆
        """
        ...

    def list_entries(self) -> list[str]:
        """回傳所有已 load 的 entry IDs。"""
        ...

    def get_entry(self, entry_id: str) -> Optional[dict]:
        """取單一條目的完整 dict（給 entry 詳情頁用）。"""
        ...
