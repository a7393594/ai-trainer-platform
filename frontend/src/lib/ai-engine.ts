/**
 * AI Engine API Client
 * 前端呼叫 Python AI 引擎的統一介面
 */

import type {
  ChatRequest,
  ChatResponse,
  DemoContext,
  FeedbackRequest,
  WidgetResponsePayload,
} from '@/types'

const AI_ENGINE_URL = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${AI_ENGINE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(error.detail || `API Error: ${res.status}`)
  }

  return res.json()
}

// ============================================
// 對話
// ============================================

/** 送出訊息給 AI Agent */
export async function sendMessage(req: ChatRequest): Promise<ChatResponse> {
  return request<ChatResponse>('/api/v1/chat', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

/** Streaming 對話 — 逐字回傳 */
export async function sendMessageStream(
  req: ChatRequest,
  onChunk: (content: string) => void,
  onDone: (sessionId: string, messageId: string) => void,
  onError?: (error: string) => void,
): Promise<void> {
  const res = await fetch(`${AI_ENGINE_URL}/api/v1/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })

  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    onError?.(err.detail || `API Error: ${res.status}`)
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let sessionId = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    const text = decoder.decode(value, { stream: true })
    const lines = text.split('\n')

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const data = JSON.parse(line.slice(6))
        if (data.session_id) sessionId = data.session_id
        if (data.content) onChunk(data.content)
        if (data.done) onDone(sessionId, data.message_id)
        if (data.error) onError?.(data.error)
      } catch {}
    }
  }
}

/** 送出互動元件的操作結果 */
export async function sendWidgetResponse(
  payload: WidgetResponsePayload
): Promise<ChatResponse> {
  return request<ChatResponse>('/api/v1/chat/widget-response', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

// ============================================
// 回饋
// ============================================

/** 對 AI 輸出打分 / 修正 */
export async function submitFeedback(req: FeedbackRequest): Promise<void> {
  await request('/api/v1/feedback', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

// ============================================
// Demo Context
// ============================================

/** 取得 demo 環境的 IDs */
export async function getDemoContext(email?: string): Promise<DemoContext> {
  const params = email ? `?email=${encodeURIComponent(email)}` : ''
  return request<DemoContext>(`/api/v1/demo/context${params}`)
}

// ============================================
// Sessions
// ============================================

/** 列出專案的所有訓練會話 */
export async function listSessions(projectId: string) {
  return request<{ sessions: any[] }>(`/api/v1/sessions/${projectId}`)
}

/** 取得會話的訊息歷史 */
export async function getSessionMessages(projectId: string, sessionId: string) {
  return request<{ messages: any[] }>(`/api/v1/sessions/${projectId}/${sessionId}/messages`)
}

// ============================================
// Prompts
// ============================================

/** 列出 Prompt 版本 */
export async function listPromptVersions(projectId: string) {
  return request<{ versions: any[] }>(`/api/v1/prompts/${projectId}`)
}

/** 切換 active Prompt */
export async function activatePromptVersion(projectId: string, versionId: string) {
  return request(`/api/v1/prompts/${projectId}/activate/${versionId}`, { method: 'POST' })
}

// ============================================
// Onboarding
// ============================================

/** 開始 Onboarding */
export async function startOnboarding(projectId: string, userId: string, templateId: string = 'general') {
  return request<ChatResponse>('/api/v1/onboarding/start', {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId, user_id: userId, template_id: templateId }),
  })
}

/** 回答 Onboarding 問題 */
export async function answerOnboarding(sessionId: string, questionId: string, answer: Record<string, any>) {
  return request<ChatResponse>('/api/v1/onboarding/answer', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, question_id: questionId, answer }),
  })
}

/** 取得 Onboarding 進度 */
export async function getOnboardingProgress(sessionId: string) {
  return request<{ session_id: string; current: number; total: number; template_id: string; completed: boolean }>(
    `/api/v1/onboarding/progress/${sessionId}`
  )
}

// ============================================
// Prompt Suggestions
// ============================================

/** 觸發產出建議 */
export async function generateSuggestions(projectId: string) {
  return request<any>(`/api/v1/prompt/suggestions/${projectId}/generate`, { method: 'POST' })
}

/** 列出待審建議 */
export async function listSuggestions(projectId: string) {
  return request<{ suggestions: any[] }>(`/api/v1/prompt/suggestions/${projectId}`)
}

/** 套用建議 */
export async function applySuggestion(suggestionId: string, projectId: string) {
  return request<any>(`/api/v1/prompt/suggestions/${suggestionId}/apply?project_id=${projectId}`, { method: 'POST' })
}

/** 拒絕建議 */
export async function rejectSuggestion(suggestionId: string) {
  return request<any>(`/api/v1/prompt/suggestions/${suggestionId}/reject`, { method: 'POST' })
}

// ============================================
// 知識庫
// ============================================

/** 上傳文件到知識庫 */
export async function uploadDocument(projectId: string, title: string, content: string) {
  return request('/api/v1/knowledge/upload', {
    method: 'POST',
    body: JSON.stringify({
      project_id: projectId,
      title,
      content,
      source_type: 'upload',
    }),
  })
}

/** 列出知識庫文件 */
export async function listKnowledge(projectId: string) {
  return request(`/api/v1/knowledge/${projectId}`)
}

// ============================================
// 工具
// ============================================

/** 列出已註冊工具 */
export async function listTools(tenantId: string) {
  return request(`/api/v1/tools/${tenantId}`)
}

// ============================================
// 評估
// ============================================

/** 執行評估 */
export async function runEval(projectId: string) {
  return request(`/api/v1/eval/run/${projectId}`, { method: 'POST' })
}

// ============================================
// LLM 模型
// ============================================

/** 列出可用模型 */
export async function listModels() {
  return request<{ models: Array<{ id: string; provider: string; label: string }> }>(
    '/api/v1/models'
  )
}
