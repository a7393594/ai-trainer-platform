"""KB v1.1 entry pydantic types。

對應 `poker-kb-schema-v1.1.md` 第 3 章「完整 Schema v1.1」13 個欄位。

注意：
- yaml 使用 `zh-tw` key，pydantic field 用 `zh_tw`，靠 alias 處理
- `populate_by_name=True` 讓兩種 key 都能讀進來
- sources / changelog 等元資料欄位 schema 上允許 extra fields
  （實際資料中 L1-MATH-RISK_OF_RUIN 的 sources 帶有 `publisher` 之類非 schema 欄位）
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MultiLang(BaseModel):
    """多語言字串（zh-tw / en）。"""

    zh_tw: Optional[str] = Field(None, alias="zh-tw")
    en: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class MultiLangList(BaseModel):
    """多語言字串陣列。"""

    zh_tw: list[str] = Field(default_factory=list, alias="zh-tw")
    en: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class Example(BaseModel):
    """examples / common_mistakes / edge_cases 的共用結構。"""

    title: str
    description: str
    note: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class CommonMistake(BaseModel):
    title: str
    description: str
    note: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class EdgeCase(BaseModel):
    title: str
    description: str
    note: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class Content(BaseModel):
    definition: str
    core_concept: str
    mechanics: Optional[str] = None
    examples: list[Example] = Field(default_factory=list)
    common_mistakes: list[CommonMistake] = Field(default_factory=list)
    edge_cases: list[EdgeCase] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class Relation(BaseModel):
    type: str  # causal | contrast | hierarchy | application
    subtype: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class RelatedEntry(BaseModel):
    id: str
    relation: Relation

    model_config = ConfigDict(extra="allow")


class Source(BaseModel):
    """KB v1.1 sources 條目。

    extra="allow" 是必要的：實測 L1-MATH-RISK_OF_RUIN 的 sources 帶有
    `publisher` 之類非 schema 欄位。
    """

    type: str  # book | paper | video | solver | coach | community | personal_experience | other
    title: Optional[str] = None
    author: Optional[str] = None
    year: Optional[int] = None
    page: Optional[str] = None
    description: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class ChangelogEntry(BaseModel):
    version: str
    date: str
    note: str
    revision_log: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class KBEntry(BaseModel):
    """KB v1.1 完整條目（13 個欄位）。"""

    id: str
    title: MultiLang
    category: str
    aliases: Optional[MultiLangList] = None
    content: dict[str, Content]  # {"zh-tw": Content, "en": Content?}
    related: list[RelatedEntry] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    prerequisite_level: int  # 0..3
    environment: list[str] = Field(default_factory=list)  # online | live
    applicable_format: list[str] = Field(default_factory=list)  # cash | mtt
    typical_stack_depth: Optional[int] = None
    sources: list[Source] = Field(default_factory=list)
    version: str
    changelog: list[ChangelogEntry] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    @property
    def primary_title(self) -> str:
        """優先 zh-tw，回退 en，最後用 id。"""
        if self.title.zh_tw:
            return self.title.zh_tw
        if self.title.en:
            return self.title.en
        return self.id

    def primary_content(self) -> Optional[Content]:
        """優先 zh-tw，回退 en。"""
        return self.content.get("zh-tw") or self.content.get("en")


class KBChunk(BaseModel):
    """Retrieval 回傳給 LLM 的 chunk format。

    LLM 看到的 KB 訊息單位 — 已 format 好可以直接放進 system prompt。
    """

    id: str  # entry id
    citation: str  # "kb://{id}"
    level: int  # prerequisite_level
    title: str
    content_text: str  # 已 format 好的 chunk 文字（含 definition + core_concept + 1 example）
    full_url: str  # "/kb/entry/{id}" (供前端展開詳細頁)
