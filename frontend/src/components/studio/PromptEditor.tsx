'use client'

import { useEffect, useMemo, useState } from 'react'
import type { NodeSpan, PipelineComparison } from '@/lib/studio/types'
import { formatCost, formatDuration } from '@/lib/studio/graph'
import { listAvailableModels, rerunNode, type ModelInfo } from '@/lib/studio/api'

interface PromptEditorProps {
  runId: string
  span: NodeSpan
  onComparisonCreated: (cmp: PipelineComparison) => void
}

interface Message {
  role: string
  content: string
}

export default function PromptEditor({
  runId,
  span,
  onComparisonCreated,
}: PromptEditorProps) {
  // 從 span.input_ref 還原 messages
  const original = useMemo<Message[]>(() => {
    if (!Array.isArray(span.input_ref)) return []
    return (span.input_ref as Message[]).map((m) => ({
      role: m.role || 'user',
      content: typeof m.content === 'string' ? m.content : JSON.stringify(m.content),
    }))
  }, [span.input_ref])

  const [messages, setMessages] = useState<Message[]>(original)
  const [model, setModel] = useState(span.model || 'claude-sonnet-4-20250514')
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastResult, setLastResult] = useState<PipelineComparison | null>(null)

  useEffect(() => {
    listAvailableModels().then(setAvailableModels).catch(() => {})
  }, [])

  // span 換了就重置
  useEffect(() => {
    setMessages(original)
    setModel(span.model || 'claude-sonnet-4-20250514')
    setLastResult(null)
    setError(null)
  }, [original, span])

  const dirty = useMemo(
    () =>
      messages.length !== original.length ||
      messages.some((m, i) => m.content !== original[i]?.content),
    [messages, original]
  )

  const updateContent = (idx: number, content: string) => {
    setMessages((prev) => prev.map((m, i) => (i === idx ? { ...m, content } : m)))
  }

  const reset = () => setMessages(original)

  const handleRerun = async () => {
    setRunning(true)
    setError(null)
    try {
      const res = await rerunNode(runId, span.id, {
        modelOverride: model,
        promptOverride: messages,
      })
      setLastResult(res.comparison)
      onComparisonCreated(res.comparison)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }

  if (original.length === 0) {
    return (
      <p className="text-[11px] text-zinc-500">
        此節點沒有可編輯的 messages(input_ref 不是 messages 列表)
      </p>
    )
  }

  return (
    <div className="space-y-3">
      {/* Model + action bar */}
      <div className="rounded border border-zinc-800 bg-zinc-900/60 p-3">
        <label className="mb-1 block text-[10px] uppercase text-zinc-500">
          模型
        </label>
        <select
          value={model}
          onChange={(e) => setModel(e.target.value)}
          className="w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-[11px] text-zinc-200 outline-none focus:border-blue-500"
        >
          {availableModels.length > 0 ? (
            availableModels.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label} ({m.cost})
              </option>
            ))
          ) : (
            <option value={model}>{model.replace(/-\d{8}$/, '')}</option>
          )}
        </select>
        <div className="mt-2 flex items-center gap-2">
          <button
            onClick={handleRerun}
            disabled={running}
            className="flex-1 rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500"
          >
            {running ? '重跑中…' : dirty ? '用修改後 Prompt 重跑' : '重跑此節點'}
          </button>
          {dirty && (
            <button
              onClick={reset}
              className="rounded border border-zinc-700 px-2 py-1.5 text-[11px] text-zinc-400 hover:text-zinc-200"
            >
              還原
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded border border-red-500/60 bg-red-950/40 p-2 text-[11px] text-red-300">
          {error}
        </div>
      )}

      {lastResult && (
        <div className="rounded border border-emerald-500/60 bg-emerald-950/30 p-3">
          <div className="mb-1 flex items-center justify-between text-[10px] text-emerald-300">
            <span>新結果({lastResult.model.replace(/-\d{8}$/, '')})</span>
            <span>
              {formatDuration(lastResult.latency_ms)} / {formatCost(lastResult.cost_usd)}
            </span>
          </div>
          <pre className="max-h-36 overflow-auto whitespace-pre-wrap rounded bg-zinc-950/80 p-2 font-mono text-[11px] text-emerald-100">
            {lastResult.output_text}
          </pre>
        </div>
      )}

      {/* Messages editor */}
      <div className="space-y-2">
        {messages.map((m, i) => {
          const changed = m.content !== original[i]?.content
          return (
            <div
              key={i}
              className={`rounded border p-2 ${
                changed
                  ? 'border-amber-500/60 bg-amber-950/20'
                  : 'border-zinc-800 bg-zinc-900/60'
              }`}
            >
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[10px] uppercase text-zinc-500">{m.role}</span>
                {changed && (
                  <span className="text-[10px] text-amber-400">已修改</span>
                )}
              </div>
              <textarea
                value={m.content}
                onChange={(e) => updateContent(i, e.target.value)}
                rows={Math.min(Math.max(m.content.split('\n').length, 3), 12)}
                className="w-full resize-y rounded border border-zinc-800 bg-zinc-950 px-2 py-1 font-mono text-[11px] leading-relaxed text-zinc-100 outline-none focus:border-blue-500"
                readOnly={m.role === 'user' && i === messages.length - 1}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}
