"""
資料模型定義 — 用 Pydantic 驗證所有進出的資料
"""
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime
from enum import Enum


# ============================================
# 通用
# ============================================

class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Rating(str, Enum):
    CORRECT = "correct"
    PARTIAL = "partial"
    WRONG = "wrong"


# ============================================
# 對話
# ============================================

class ChatMessage(BaseModel):
    role: Role
    content: str
    metadata: dict[str, Any] = {}


class ChatRequest(BaseModel):
    project_id: str
    session_id: Optional[str] = None  # None = 建立新會話
    user_id: Optional[str] = None     # None = 用 demo user
    message: str
    model: Optional[str] = None       # None = 用專案預設模型
    mode_prompt: Optional[str] = None  # 前端 mode（教練/研究/課程/對戰）對應的 system prompt 前綴


class ChatResponse(BaseModel):
    session_id: str
    message: ChatMessage
    message_id: Optional[str] = None   # DB 中 assistant 訊息的 ID（給 FeedbackBar 用）
    widgets: list[dict[str, Any]] = []  # 互動元件（如果 AI 決定要顯示）
    tool_results: list[dict[str, Any]] = []  # 工具呼叫結果
    metadata: dict[str, Any] = {}


# ============================================
# 回饋
# ============================================

class FeedbackRequest(BaseModel):
    message_id: str
    rating: Rating
    correction_text: Optional[str] = None


# ============================================
# 互動元件
# ============================================

class WidgetType(str, Enum):
    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"
    RANK = "rank"
    CONFIRM = "confirm"
    FORM = "form"
    CARD_CAROUSEL = "card_carousel"
    DATE_PICKER = "date_picker"
    SLIDER = "slider"


class WidgetOption(BaseModel):
    id: str
    label: str
    description: Optional[str] = None
    icon: Optional[str] = None


class WidgetDefinition(BaseModel):
    widget_type: WidgetType
    question: str
    options: list[WidgetOption] = []
    config: dict[str, Any] = {}        # 元件特定設定（如 slider 的 min/max）
    allow_skip: bool = False


class WidgetResponse(BaseModel):
    session_id: str
    widget_type: WidgetType
    result: dict[str, Any]             # 使用者操作的結果


# ============================================
# 工具
# ============================================

class ToolType(str, Enum):
    API_CALL = "api_call"
    DB_QUERY = "db_query"
    WEBHOOK = "webhook"
    INTERNAL_FN = "internal_fn"
    MCP_SERVER = "mcp_server"


class ToolDefinition(BaseModel):
    name: str
    description: str
    tool_type: ToolType
    config_json: dict[str, Any]
    auth_config: dict[str, Any] = {}
    permissions: list[str] = ["admin", "trainer"]
    rate_limit: Optional[str] = None


# ============================================
# 能力規則
# ============================================

class ActionType(str, Enum):
    WIDGET = "widget"
    TOOL_CALL = "tool_call"
    WORKFLOW = "workflow"
    COMPOSITE = "composite"


class CapabilityRule(BaseModel):
    project_id: str
    trigger_description: str           # 人話描述的觸發條件
    trigger_keywords: list[str] = []   # 觸發關鍵字（用於意圖匹配）
    action_type: ActionType
    action_config: dict[str, Any]      # 對應的動作設定（widget config / tool_id / workflow_id）
    priority: int = 0


# ============================================
# 知識庫
# ============================================

class DocumentUploadRequest(BaseModel):
    project_id: str
    title: str
    source_type: str = "upload"        # 'upload' | 'url' | 'auto_extract'
    content: Optional[str] = None      # 純文字內容
    url: Optional[str] = None          # 網頁連結


# ============================================
# 評估
# ============================================

class TestCaseRequest(BaseModel):
    project_id: str
    input_text: str
    expected_output: str
    category: Optional[str] = None


class EvalRunResult(BaseModel):
    run_id: str
    total_score: float
    passed_count: int
    failed_count: int
    details: list[dict[str, Any]] = []


class EvalTrendPoint(BaseModel):
    run_id: str
    total_score: float
    passed_count: int
    failed_count: int
    run_at: str
    prompt_version_id: Optional[str] = None
    model_used: Optional[str] = None


class CategoryAnalytics(BaseModel):
    category: str
    avg_score: float
    passed_count: int
    failed_count: int
    total: int


class RegressionResult(BaseModel):
    regression_detected: bool
    overall_delta: float
    current_score: Optional[float] = None
    previous_score: Optional[float] = None
    regressions: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []
    regression_level: Optional[str] = None  # "ok" | "warning" | "critical"


class PhaseStatus(BaseModel):
    test_case_count: int
    run_count: int
    latest_score: Optional[float] = None
    agreement_rate: Optional[float] = None
    auto_mode_eligible: bool
    current_phase: str  # "manual" | "semi-auto" | "full-auto"


# ============================================
# Onboarding
# ============================================

class OnboardingStartRequest(BaseModel):
    project_id: str
    user_id: Optional[str] = None
    template_id: str = "general"


class OnboardingAnswerRequest(BaseModel):
    session_id: str
    question_id: str
    answer: dict[str, Any]


class OnboardingProgress(BaseModel):
    session_id: str
    current: int
    total: int
    template_id: str
    completed: bool


# ============================================
# Demo Context
# ============================================

class ProjectSummary(BaseModel):
    id: str
    name: str
    project_type: str = "trainer"
    description: str | None = None


class DemoContext(BaseModel):
    tenant_id: str
    user_id: str
    project_id: str
    project_name: str
    projects: list[ProjectSummary] = []
