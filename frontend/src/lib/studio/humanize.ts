/**
 * humanize — translate raw NodeSpan data into human-readable summaries.
 *
 * Each node type has different input_ref/output_ref/metadata shapes. This
 * layer gives the UI a consistent "what happened here" description rather
 * than forcing users to read raw JSON.
 */

import type { NodeSpan } from './types'

export interface HumanizedNode {
  /** One-line summary shown as the node headline */
  summary: string
  /** Category of detail items — each has a label + value (markdown-safe string) */
  details: Array<{ label: string; value: string; code?: boolean }>
  /** Optional long-form content (e.g., full prompts, outputs) */
  excerpts: Array<{ label: string; content: string; lang?: 'json' | 'text' | 'markdown' }>
  /** Warning/notice to surface prominently */
  notices: Array<{ level: 'info' | 'warn' | 'error'; text: string }>
}

function truncate(s: string, n: number): string {
  if (!s) return ''
  return s.length > n ? s.slice(0, n) + '…' : s
}

function safeJson(v: unknown, n = 800): string {
  try {
    const str = typeof v === 'string' ? v : JSON.stringify(v, null, 2)
    return str.length > n ? str.slice(0, n) + '\n…(截斷)' : str
  } catch { return String(v) }
}

function asObj(v: unknown): Record<string, unknown> {
  return (v && typeof v === 'object' && !Array.isArray(v)) ? (v as Record<string, unknown>) : {}
}

function asArr<T = unknown>(v: unknown): T[] {
  return Array.isArray(v) ? (v as T[]) : []
}

export function humanize(node: NodeSpan): HumanizedNode {
  const r: HumanizedNode = { summary: '', details: [], excerpts: [], notices: [] }

  // Always show basic metrics
  if (node.latency_ms > 0) {
    r.details.push({ label: '耗時', value: `${node.latency_ms} ms`, code: true })
  }
  if (node.status === 'error') {
    r.notices.push({ level: 'error', text: node.error || '執行錯誤' })
  }

  const input = asObj(node.input_ref)
  const output = asObj(node.output_ref)
  const meta = node.metadata || {}

  switch (node.type) {
    case 'input':
      return humanizeInput(node, input, r)
    case 'output':
      return humanizeOutput(node, output, r)
    case 'model':
      return humanizeModel(node, input, output, meta, r)
    case 'tool':
      return humanizeTool(node, input, output, r)
    case 'parallel':
      return humanizeParallel(node, input, output, r)
    case 'process':
      return humanizeProcess(node, input, output, meta, r)
    default:
      r.summary = node.label
      if (node.input_ref) r.excerpts.push({ label: 'input', content: safeJson(node.input_ref), lang: 'json' })
      if (node.output_ref) r.excerpts.push({ label: 'output', content: safeJson(node.output_ref), lang: 'json' })
      return r
  }
}

function humanizeInput(node: NodeSpan, input: Record<string, unknown>, r: HumanizedNode): HumanizedNode {
  const text = String(input.text || input.message || '')
  r.summary = text ? `收到用戶訊息（${text.length} 字）` : '收到輸入'
  if (text) r.excerpts.push({ label: '訊息內容', content: truncate(text, 2000), lang: 'text' })
  if (input.user_id) r.details.push({ label: '用戶 ID', value: String(input.user_id).slice(0, 8) + '...', code: true })
  if (input.session_id) r.details.push({ label: 'Session', value: String(input.session_id).slice(0, 8) + '...', code: true })
  return r
}

function humanizeOutput(node: NodeSpan, output: Record<string, unknown>, r: HumanizedNode): HumanizedNode {
  const text = String(output.text || output.content || '')
  const widgets = asArr(output.widgets)
  r.summary = text ? `AI 回應（${text.length} 字）${widgets.length > 0 ? ` + ${widgets.length} 個互動元件` : ''}` : '產出完成'
  if (text) r.excerpts.push({ label: '最終回應', content: truncate(text, 2000), lang: 'markdown' })
  if (widgets.length > 0) {
    r.details.push({ label: '互動元件', value: widgets.map((w) => (w as { widget_type?: string }).widget_type || '?').join(', ') })
  }
  if (output.message_id) r.details.push({ label: 'Message ID', value: String(output.message_id).slice(0, 8) + '...', code: true })
  return r
}

function humanizeModel(
  node: NodeSpan,
  input: Record<string, unknown>,
  output: Record<string, unknown>,
  meta: Record<string, unknown>,
  r: HumanizedNode,
): HumanizedNode {
  const messages = asArr<{ role: string; content: unknown }>(input.messages)
  const systemMsg = messages.find((m) => m.role === 'system')
  const lastUser = [...messages].reverse().find((m) => m.role === 'user')

  const toolCalls = meta.has_tool_calls === true || meta.tool_call_count
  const outputText = String(output.text || output.content || '')

  r.summary = `${node.model || '未知模型'} · 收 ${node.tokens_in} tokens · 回 ${node.tokens_out} tokens · 成本 $${node.cost_usd.toFixed(6)}`

  r.details.push({ label: '模型', value: node.model || '?', code: true })
  r.details.push({ label: 'Tokens', value: `輸入 ${node.tokens_in} / 輸出 ${node.tokens_out}` })
  r.details.push({ label: '成本', value: `$${node.cost_usd.toFixed(6)}` })
  if (meta.streaming) r.details.push({ label: '模式', value: '串流' })
  if (toolCalls) r.details.push({ label: '工具呼叫', value: String(meta.tool_call_count || '有') })
  r.details.push({ label: '訊息數', value: `system + ${messages.filter((m) => m.role !== 'system').length} 對話` })

  if (systemMsg) {
    const sysContent = typeof systemMsg.content === 'string' ? systemMsg.content : safeJson(systemMsg.content)
    r.excerpts.push({ label: 'System Prompt（預覽）', content: truncate(sysContent, 1200), lang: 'markdown' })
  }
  if (lastUser) {
    const userContent = typeof lastUser.content === 'string' ? lastUser.content : safeJson(lastUser.content)
    r.excerpts.push({ label: '最後一則 User 訊息', content: truncate(userContent, 800), lang: 'markdown' })
  }
  if (outputText) {
    r.excerpts.push({ label: 'AI 回應', content: truncate(outputText, 1500), lang: 'markdown' })
  }

  return r
}

function humanizeTool(
  node: NodeSpan,
  input: Record<string, unknown>,
  output: Record<string, unknown>,
  r: HumanizedNode,
): HumanizedNode {
  const toolName = String(input.tool || node.label || '')
  const params = input.params ?? input.args ?? {}
  const result = output.result ?? output
  r.summary = `🔧 呼叫工具 ${toolName}`
  r.details.push({ label: '工具名稱', value: toolName, code: true })
  r.excerpts.push({ label: '參數', content: safeJson(params, 600), lang: 'json' })
  r.excerpts.push({ label: '結果', content: safeJson(result, 1500), lang: 'json' })
  return r
}

function humanizeParallel(
  node: NodeSpan,
  input: Record<string, unknown>,
  output: Record<string, unknown>,
  r: HumanizedNode,
): HumanizedNode {
  const count = Number(input.tool_calls || output.completed_count || 0)
  r.summary = `並行執行 ${count} 個子節點`
  r.details.push({ label: '子節點數', value: String(count) })
  r.notices.push({ level: 'info', text: '展開節點可看各子節點詳情' })
  return r
}

function humanizeProcess(
  node: NodeSpan,
  input: Record<string, unknown>,
  output: Record<string, unknown>,
  meta: Record<string, unknown>,
  r: HumanizedNode,
): HumanizedNode {
  const label = node.label.toLowerCase()

  // context_loader: load history
  if (label.includes('context') || label.includes('history')) {
    const hist = output.history_length ?? output.count
    r.summary = `載入對話歷史 ${hist ?? '?'} 則訊息`
    r.details.push({ label: 'Session', value: String(input.session_id || '').slice(0, 12) + '...', code: true })
    if (hist != null) r.details.push({ label: '歷史訊息數', value: String(hist) })
    if (meta.history_preview) {
      r.excerpts.push({ label: '歷史預覽', content: safeJson(meta.history_preview, 1000), lang: 'json' })
    }
    return r
  }

  // triage: intent classification
  if (label.includes('triage') || label.includes('intent')) {
    const intent = String(output.intent_type || output.intent || '')
    r.summary = `意圖分類：${intent || '未知'}`
    r.details.push({ label: '意圖類型', value: intent })
    if (output.matched_rule) r.details.push({ label: '匹配規則', value: String(output.matched_rule) })
    if (output.workflow_id) r.details.push({ label: 'Workflow', value: String(output.workflow_id) })
    if (output.confidence) r.details.push({ label: '信心度', value: String(output.confidence) })
    return r
  }

  // prompt_compose: assemble messages
  if (label.includes('prompt') || label.includes('compose')) {
    const msgCount = output.message_count ?? output.total_messages
    const sysLen = output.system_prompt_length ?? output.system_length
    const ragCount = output.rag_chunks ?? output.knowledge_count ?? 0
    r.summary = `組裝 prompt（${msgCount ?? '?'} 則訊息${Number(ragCount) > 0 ? ` + ${ragCount} RAG 片段` : ''}）`
    if (sysLen != null) r.details.push({ label: 'System Prompt 長度', value: `${sysLen} 字` })
    if (msgCount != null) r.details.push({ label: '總訊息數', value: String(msgCount) })
    if (Number(ragCount) > 0) r.details.push({ label: 'RAG 片段', value: String(ragCount) })
    if (meta.composed_messages) {
      r.excerpts.push({ label: '組裝後的訊息', content: safeJson(meta.composed_messages, 1500), lang: 'json' })
    }
    return r
  }

  // load_tools
  if (label.includes('tool') && label.includes('load')) {
    const count = output.tool_count ?? asArr(output.tools).length
    r.summary = `載入 ${count} 個可用工具`
    if (output.tools) {
      const names = asArr(output.tools).map((t) => (t as { name?: string }).name || String(t)).join(', ')
      r.details.push({ label: '工具清單', value: names })
    }
    return r
  }

  // generic process fallback
  r.summary = node.label
  if (Object.keys(input).length > 0) {
    r.excerpts.push({ label: 'input', content: safeJson(input, 800), lang: 'json' })
  }
  if (Object.keys(output).length > 0) {
    r.excerpts.push({ label: 'output', content: safeJson(output, 800), lang: 'json' })
  }
  return r
}
