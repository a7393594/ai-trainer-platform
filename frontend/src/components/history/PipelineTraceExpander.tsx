'use client'

/**
 * PipelineTraceExpander — history 頁面的訊息 trace 展開。
 * 使用 humanize() 產生人看得懂的摘要，parallel 節點支援樹狀展開。
 */

import { useState, useMemo } from 'react'
import { getPipelineRunByMessage } from '@/lib/studio/api'
import { humanize } from '@/lib/studio/humanize'
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
    if (expanded) { setExpanded(false); return }
    if (!run && !noRun) {
      setLoading(true)
      setError(null)
      try {
        const res = await getPipelineRunByMessage(messageId)
        if (!res) setNoRun(true)
        else setRun(res.run)
      } catch (e) {
        setError(e instanceof Error ? e.message : '載入失敗')
      }
      setLoading(false)
    }
    setExpanded(true)
  }

  // Build tree: nodes indexed by parent_id
  const tree = useMemo(() => {
    if (!run?.nodes_json?.nodes) return { roots: [] as NodeSpan[], childrenMap: new Map<string, NodeSpan[]>() }
    const childrenMap = new Map<string, NodeSpan[]>()
    const roots: NodeSpan[] = []
    for (const n of run.nodes_json.nodes) {
      if (n.parent_id) {
        const list = childrenMap.get(n.parent_id) || []
        list.push(n)
        childrenMap.set(n.parent_id, list)
      } else {
        roots.push(n)
      }
    }
    return { roots, childrenMap }
  }, [run])

  return (
    <div className="mt-2">
      <button
        onClick={handleToggle}
        className="text-[10px] text-zinc-500 hover:text-zinc-300 flex items-center gap-1"
      >
        <span className={`transition-transform inline-block ${expanded ? 'rotate-90' : ''}`}>▶</span>
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
              <div className="flex items-center gap-3 text-[10px] text-zinc-400 border-b border-zinc-800 pb-2 mb-2">
                <span>模式：<span className="text-zinc-300 uppercase">{run.mode}</span></span>
                <span>狀態：<span className={run.status === 'completed' ? 'text-green-400' : run.status === 'failed' ? 'text-red-400' : 'text-yellow-400'}>{run.status}</span></span>
                <span>總時間：<span className="text-zinc-300">{run.total_duration_ms}ms</span></span>
                <span>總成本：<span className="text-zinc-300">${run.total_cost_usd?.toFixed(6)}</span></span>
              </div>

              <div className="space-y-1.5">
                {tree.roots.map((node) => (
                  <NodeRow
                    key={node.id}
                    node={node}
                    childrenMap={tree.childrenMap}
                    depth={0}
                  />
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

function NodeRow({
  node, childrenMap, depth,
}: {
  node: NodeSpan
  childrenMap: Map<string, NodeSpan[]>
  depth: number
}) {
  const [open, setOpen] = useState(false)
  const [childrenOpen, setChildrenOpen] = useState(depth < 1)  // auto-expand depth 0+1

  const children = childrenMap.get(node.id) || []
  const hasChildren = children.length > 0
  const humanized = humanize(node)

  const icon = NODE_TYPE_ICON[node.type] || '•'
  const borderColor = NODE_TYPE_COLOR[node.type] || 'border-zinc-600'
  const statusColor =
    node.status === 'ok' ? 'text-green-400' :
    node.status === 'error' ? 'text-red-400' :
    'text-yellow-400'

  return (
    <div className={`border-l-2 ${borderColor} pl-2`} style={{ marginLeft: depth > 0 ? depth * 12 : 0 }}>
      {/* Header row */}
      <div className="flex items-start gap-2 hover:bg-zinc-800/30 rounded px-1 py-1">
        {hasChildren ? (
          <button onClick={() => setChildrenOpen((o) => !o)} className="text-[9px] text-zinc-500 hover:text-zinc-300 w-4 shrink-0 mt-0.5" title={childrenOpen ? '收合子節點' : '展開子節點'}>
            {childrenOpen ? '▼' : '▶'}
          </button>
        ) : <span className="w-4 shrink-0" />}

        <button onClick={() => setOpen((o) => !o)} className="flex-1 text-left" title="點擊查看詳情">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs">{icon}</span>
            <span className="text-[11px] text-zinc-200 font-medium">{node.label}</span>
            <span className="text-[9px] uppercase text-zinc-600">{node.type}</span>
            <span className={`text-[9px] ${statusColor}`}>{node.status}</span>
            {hasChildren && <span className="text-[9px] text-yellow-400">{children.length} 子節點</span>}
            <div className="flex-1" />
            {node.model && <span className="text-[9px] text-violet-400 font-mono">{node.model}</span>}
            {node.cost_usd > 0 && <span className="text-[9px] text-zinc-500">${node.cost_usd.toFixed(6)}</span>}
            {node.latency_ms > 0 && <span className="text-[9px] text-zinc-500">{node.latency_ms}ms</span>}
            <span className="text-[9px] text-zinc-600">{open ? '▼' : '▶'}</span>
          </div>
          {/* Humanize summary as subtitle */}
          {humanized.summary && (
            <p className="text-[10px] text-zinc-400 mt-0.5">{humanized.summary}</p>
          )}
        </button>
      </div>

      {/* Expanded node details */}
      {open && (
        <div className="ml-6 mt-1 space-y-1.5 border-l border-zinc-800 pl-2">
          {humanized.notices.length > 0 && (
            <div className="space-y-1">
              {humanized.notices.map((n, i) => (
                <div
                  key={i}
                  className={`rounded px-1.5 py-1 text-[10px] ${
                    n.level === 'error' ? 'bg-red-900/30 border border-red-800 text-red-300' :
                    n.level === 'warn' ? 'bg-yellow-900/30 border border-yellow-800 text-yellow-300' :
                    'bg-blue-900/20 border border-blue-800/50 text-blue-300'
                  }`}
                >
                  {n.text}
                </div>
              ))}
            </div>
          )}

          {humanized.details.length > 0 && (
            <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
              {humanized.details.map((d, i) => (
                <div key={i} className="text-[10px] flex items-center gap-1">
                  <span className="text-zinc-500">{d.label}：</span>
                  <span className={d.code ? 'font-mono text-zinc-300' : 'text-zinc-300'}>{d.value}</span>
                </div>
              ))}
            </div>
          )}

          {humanized.excerpts.map((ex, i) => (
            <div key={i}>
              <p className="text-[9px] text-zinc-500 uppercase mb-0.5">{ex.label}</p>
              <pre className="rounded bg-zinc-900/60 px-1.5 py-1 text-[10px] text-zinc-300 whitespace-pre-wrap break-words font-mono max-h-48 overflow-y-auto">{ex.content}</pre>
            </div>
          ))}

          {/* Original raw I/O (collapsed by default in a sub-section) */}
          <details className="text-[10px]">
            <summary className="cursor-pointer text-zinc-600 hover:text-zinc-400">原始 I/O（JSON）</summary>
            <div className="mt-1 space-y-1">
              {node.input_ref != null && (
                <div>
                  <p className="text-[9px] text-zinc-500 uppercase">input_ref</p>
                  <pre className="rounded bg-zinc-900/60 px-1.5 py-1 text-[10px] text-zinc-400 whitespace-pre-wrap break-words font-mono max-h-40 overflow-y-auto">{JSON.stringify(node.input_ref, null, 2)}</pre>
                </div>
              )}
              {node.output_ref != null && (
                <div>
                  <p className="text-[9px] text-zinc-500 uppercase">output_ref</p>
                  <pre className="rounded bg-zinc-900/60 px-1.5 py-1 text-[10px] text-zinc-400 whitespace-pre-wrap break-words font-mono max-h-40 overflow-y-auto">{JSON.stringify(node.output_ref, null, 2)}</pre>
                </div>
              )}
              {node.metadata && Object.keys(node.metadata).length > 0 && (
                <div>
                  <p className="text-[9px] text-zinc-500 uppercase">metadata</p>
                  <pre className="rounded bg-zinc-900/60 px-1.5 py-1 text-[10px] text-zinc-400 whitespace-pre-wrap break-words font-mono max-h-40 overflow-y-auto">{JSON.stringify(node.metadata, null, 2)}</pre>
                </div>
              )}
            </div>
          </details>
        </div>
      )}

      {/* Children (recursive) */}
      {hasChildren && childrenOpen && (
        <div className="mt-1 space-y-1">
          {children.map((child) => (
            <NodeRow
              key={child.id}
              node={child}
              childrenMap={childrenMap}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  )
}
