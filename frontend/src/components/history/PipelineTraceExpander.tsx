'use client'

/**
 * PipelineTraceExpander — 展開單一訊息的 pipeline 執行 trace。
 * 重用 Pipeline Studio 的 NodeSpan 資料結構。
 */

import { useState } from 'react'
import { getPipelineRunByMessage } from '@/lib/studio/api'
import type { NodeSpan, PipelineRunDetail } from '@/lib/studio/types'

interface Props {
  messageId: string
}

const NODE_TYPE_ICON: Record<string, string> = {
  input: '📥',
  process: '⚙️',
  model: '🧠',
  parallel: '🔀',
  tool: '🔧',
  output: '📤',
}

const NODE_TYPE_COLOR: Record<string, string> = {
  input: 'border-zinc-600',
  process: 'border-cyan-600',
  model: 'border-violet-600',
  parallel: 'border-yellow-600',
  tool: 'border-orange-600',
  output: 'border-emerald-600',
}

export function PipelineTraceExpander({ messageId }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [run, setRun] = useState<PipelineRunDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [noRun, setNoRun] = useState(false)

  const handleToggle = async () => {
    if (expanded) {
      setExpanded(false)
      return
    }
    if (!run && !noRun) {
      setLoading(true)
      setError(null)
      try {
        const res = await getPipelineRunByMessage(messageId)
        if (!res) {
          setNoRun(true)
        } else {
          setRun(res.run)
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : '載入失敗')
      }
      setLoading(false)
    }
    setExpanded(true)
  }

  return (
    <div className="mt-2">
      <button
        onClick={handleToggle}
        className="text-[10px] text-zinc-500 hover:text-zinc-300 flex items-center gap-1"
      >
        <span className={`transition-transform ${expanded ? 'rotate-90' : ''}`}>▶</span>
        {expanded ? '收合' : '展開'}執行環節
        {run && (
          <span className="ml-1 text-zinc-600">
            · {run.nodes_json?.nodes?.length || 0} 節點 · {run.total_duration_ms}ms · ${run.total_cost_usd?.toFixed(4)}
          </span>
        )}
      </button>

      {expanded && (
        <div className="mt-2 border border-zinc-800 rounded bg-zinc-950/50 p-2">
          {loading && (
            <div className="flex items-center gap-2 py-2">
              <div className="h-3 w-3 animate-spin rounded-full border-2 border-zinc-700 border-t-blue-500" />
              <span className="text-[10px] text-zinc-500">載入 trace...</span>
            </div>
          )}
          {error && <p className="text-[10px] text-red-400">{error}</p>}
          {noRun && <p className="text-[10px] text-zinc-500">此訊息沒有 pipeline trace（可能為 widget 回應或 capability rule 直接回覆）</p>}
          {run && (
            <>
              {/* Summary */}
              <div className="flex items-center gap-3 text-[10px] text-zinc-400 border-b border-zinc-800 pb-2 mb-2">
                <span>模式：<span className="text-zinc-300 uppercase">{run.mode}</span></span>
                <span>狀態：<span className={run.status === 'completed' ? 'text-green-400' : run.status === 'failed' ? 'text-red-400' : 'text-yellow-400'}>{run.status}</span></span>
                <span>總時間：<span className="text-zinc-300">{run.total_duration_ms}ms</span></span>
                <span>總成本：<span className="text-zinc-300">${run.total_cost_usd?.toFixed(6)}</span></span>
              </div>

              {/* Nodes list */}
              <div className="space-y-1.5">
                {(run.nodes_json?.nodes || []).map((node) => (
                  <NodeRow key={node.id} node={node} />
                ))}
              </div>

              {(!run.nodes_json?.nodes || run.nodes_json.nodes.length === 0) && (
                <p className="text-[10px] text-zinc-500">此 run 沒有記錄節點資訊</p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

function NodeRow({ node }: { node: NodeSpan }) {
  const [open, setOpen] = useState(false)
  const icon = NODE_TYPE_ICON[node.type] || '•'
  const borderColor = NODE_TYPE_COLOR[node.type] || 'border-zinc-600'
  const statusColor =
    node.status === 'ok' ? 'text-green-400' :
    node.status === 'error' ? 'text-red-400' :
    'text-yellow-400'

  return (
    <div className={`border-l-2 ${borderColor} pl-2`}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 text-left hover:bg-zinc-800/30 rounded px-1 py-0.5"
      >
        <span className="text-xs">{icon}</span>
        <span className="text-[11px] text-zinc-200 font-medium">{node.label}</span>
        <span className="text-[9px] uppercase text-zinc-600">{node.type}</span>
        <span className={`text-[9px] ${statusColor}`}>{node.status}</span>
        <div className="flex-1" />
        {node.latency_ms > 0 && <span className="text-[9px] text-zinc-500">{node.latency_ms}ms</span>}
        {node.tokens_in > 0 && <span className="text-[9px] text-zinc-500">in:{node.tokens_in}</span>}
        {node.tokens_out > 0 && <span className="text-[9px] text-zinc-500">out:{node.tokens_out}</span>}
        {node.cost_usd > 0 && <span className="text-[9px] text-zinc-500">${node.cost_usd.toFixed(6)}</span>}
        {node.model && <span className="text-[9px] text-violet-400 font-mono">{node.model}</span>}
        <span className="text-[9px] text-zinc-600">{open ? '▼' : '▶'}</span>
      </button>

      {open && (
        <div className="mt-1 ml-2 space-y-1.5 border-l border-zinc-800 pl-2">
          {node.input_ref != null && (
            <DetailBlock label="input" value={node.input_ref} />
          )}
          {node.output_ref != null && (
            <DetailBlock label="output" value={node.output_ref} />
          )}
          {node.metadata && Object.keys(node.metadata).length > 0 && (
            <DetailBlock label="metadata" value={node.metadata} />
          )}
          {node.error && (
            <div className="rounded border border-red-800 bg-red-900/20 p-1.5">
              <p className="text-[9px] text-red-400 font-semibold mb-0.5">error</p>
              <pre className="text-[10px] text-red-300 whitespace-pre-wrap break-words">{node.error}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function DetailBlock({ label, value }: { label: string; value: unknown }) {
  // If it's a messages array (common for input), render specially
  if (Array.isArray(value) && value.every((v) => v && typeof v === 'object' && 'role' in v)) {
    return (
      <div>
        <p className="text-[9px] text-zinc-500 uppercase mb-0.5">{label} · messages</p>
        <div className="space-y-1">
          {(value as Array<{ role: string; content: string }>).map((m, i) => (
            <div key={i} className="rounded bg-zinc-900/60 px-1.5 py-1">
              <span className="text-[9px] uppercase text-zinc-500 mr-1">{m.role}</span>
              <span className="text-[10px] text-zinc-300 whitespace-pre-wrap">{
                typeof m.content === 'string'
                  ? (m.content.length > 500 ? m.content.slice(0, 500) + '...' : m.content)
                  : JSON.stringify(m.content).slice(0, 500)
              }</span>
            </div>
          ))}
        </div>
      </div>
    )
  }

  // Plain text or object
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2)
  const truncated = text.length > 1500 ? text.slice(0, 1500) + '...(truncated)' : text

  return (
    <div>
      <p className="text-[9px] text-zinc-500 uppercase mb-0.5">{label}</p>
      <pre className="rounded bg-zinc-900/60 px-1.5 py-1 text-[10px] text-zinc-300 whitespace-pre-wrap break-words font-mono max-h-48 overflow-y-auto">{truncated}</pre>
    </div>
  )
}
