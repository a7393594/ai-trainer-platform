"""V4 chat KB — Schema v1.1 Knowledge Base 整合。

模組架構：
    interface.py    — KnowledgeRetriever Protocol
    schema.py       — KBEntry / KBChunk pydantic types（v1.1 schema）
    adapter_md.py   — 從 markdown 檔讀 KB
    retriever.py    — InMemoryKBIndex + 全域單例 kb_retriever
    injector.py     — KB chunks 注入 system prompt
"""
from .injector import inject_kb_context
from .interface import KnowledgeRetriever
from .retriever import InMemoryKBIndex, kb_retriever
from .schema import KBChunk, KBEntry

__all__ = [
    "KnowledgeRetriever",
    "KBEntry",
    "KBChunk",
    "kb_retriever",
    "InMemoryKBIndex",
    "inject_kb_context",
]
