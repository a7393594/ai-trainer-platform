"""
Rule Store — 規則儲存與管理層
負責規則的 CRUD、向量化、批量匯入。
"""
import json
from typing import Optional
from app.db import crud
from app.core.llm_router.router import get_embedding


async def ingest_rule(
    source_id: str,
    rule_code: str,
    title: str,
    rule_text: str,
    topic_tags: list[str],
    applies_to: list[str] = None,
    requires_judgment: bool = False,
    override_targets: list[str] = None,
) -> dict:
    """匯入一條規則,自動計算 embedding。"""
    embedding = await get_embedding(f"{title}: {rule_text}")
    data = {
        "source_id": source_id,
        "rule_code": rule_code,
        "title": title,
        "rule_text": rule_text,
        "topic_tags": topic_tags,
        "applies_to": applies_to or ["NLHE", "PLO"],
        "requires_judgment": requires_judgment,
        "override_targets": override_targets or [],
        "embedding": embedding,
    }
    return crud.create_rule(data)


async def batch_ingest(source_id: str, rules: list[dict]) -> list[dict]:
    """批量匯入規則清單。每條規則格式:
    {"code": "TDA-42", "title": "...", "text": "...", "tags": [...], "judgment": bool}
    """
    results = []
    for r in rules:
        result = await ingest_rule(
            source_id=source_id,
            rule_code=r["code"],
            title=r["title"],
            rule_text=r["text"],
            topic_tags=r.get("tags", []),
            requires_judgment=r.get("judgment", False),
            override_targets=r.get("overrides", []),
        )
        results.append(result)
        print(f"  [OK] {r['code']}: {r['title']}")
    return results


def get_rule_by_code(code: str) -> Optional[dict]:
    return crud.get_rule_by_code(code)


def list_rules_by_topic(topic: str) -> list[dict]:
    return crud.list_rules(topic=topic)
