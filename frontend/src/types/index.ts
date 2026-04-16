/**
 * AI Trainer Platform — 型別定義
 * 與後端 Pydantic models 保持同步
 */

// ============================================
// 通用
// ============================================

export type Role = 'user' | 'assistant' | 'system'
export type Rating = 'correct' | 'partial' | 'wrong'

// ============================================
// 對話
// ============================================

export interface ChatMessage {
  role: Role
  content: string
  metadata?: Record<string, any>
}

export interface ChatRequest {
  project_id: string
  session_id?: string
  user_id?: string
  message: string
  model?: string
}

export interface ChatResponse {
  session_id: string
  message: ChatMessage
  message_id?: string
  widgets: WidgetDefinition[]
  tool_results: ToolResult[]
  metadata: Record<string, any>
}

export interface ProjectSummary {
  id: string
  name: string
  project_type: 'trainer' | 'referee'
  description?: string
}

export interface NavItem {
  href: string
  label: string
  icon: string
}

export interface DomainConfig {
  nav: NavItem[]
  terms: Record<string, string>
  features: Record<string, boolean>
  chat: { mode: string; streaming: boolean }
  contextFields?: { key: string; label: string; type: string; options?: string[]; placeholder?: string }[]
  modes?: Record<string, { label: string; color: string }>
  referee?: Record<string, any>
}

export interface DemoContext {
  tenant_id: string
  user_id: string
  project_id: string
  project_name: string
  projects: ProjectSummary[]
}

// ============================================
// 互動元件
// ============================================

export type WidgetType =
  | 'single_select'
  | 'multi_select'
  | 'rank'
  | 'confirm'
  | 'form'
  | 'card_carousel'
  | 'date_picker'
  | 'slider'

export interface WidgetOption {
  id: string
  label: string
  description?: string
  icon?: string
}

export interface WidgetDefinition {
  widget_type: WidgetType
  question: string
  options: WidgetOption[]
  config: Record<string, any>
  allow_skip: boolean
}

export interface WidgetResponsePayload {
  session_id: string
  widget_type: WidgetType
  result: Record<string, any>
}

// ============================================
// 工具
// ============================================

export type ToolType = 'api_call' | 'db_query' | 'webhook' | 'internal_fn' | 'mcp_server'

export interface ToolResult {
  tool_id: string
  tool_name: string
  status: 'success' | 'error' | 'dry_run'
  data: any
}

// ============================================
// 回饋
// ============================================

export interface FeedbackRequest {
  message_id: string
  rating: Rating
  correction_text?: string
}

// ============================================
// 專案
// ============================================

export interface Project {
  id: string
  tenant_id: string
  name: string
  description?: string
  domain_template?: string
  status: 'draft' | 'training' | 'active' | 'archived'
  created_at: string
}

// ============================================
// 知識庫
// ============================================

export interface KnowledgeDoc {
  id: string
  project_id: string
  title: string
  source_type: 'upload' | 'url' | 'auto_extract'
  chunk_count: number
  status: 'processing' | 'ready' | 'error'
  created_at: string
}

// ============================================
// 評估
// ============================================

export interface EvalTestCase {
  id: string
  project_id: string
  input_text: string
  expected_output: string
  category?: string
}

export interface EvalRunResult {
  run_id: string
  total_score: number
  passed_count: number
  failed_count: number
  details: any[]
}

export interface EvalTrendPoint {
  run_id: string
  total_score: number
  passed_count: number
  failed_count: number
  run_at: string
  prompt_version_id?: string
  model_used?: string
}

export interface CategoryAnalytics {
  category: string
  avg_score: number
  passed_count: number
  failed_count: number
  total: number
}

export interface PhaseStatus {
  test_case_count: number
  run_count: number
  latest_score: number | null
  agreement_rate: number | null
  auto_mode_eligible: boolean
  current_phase: 'manual' | 'semi-auto' | 'full-auto'
}

export interface RegressionResult {
  regression_detected: boolean
  overall_delta: number
  current_score?: number
  previous_score?: number
  regressions: Array<{ test_case_id: string; old_score: number; new_score: number; delta: number }>
  improvements: Array<{ test_case_id: string; old_score: number; new_score: number; delta: number }>
  regression_level?: 'ok' | 'warning' | 'critical'
}
