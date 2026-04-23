'use client'

import { useMemo, useState } from 'react'
import type { NodeSpan, PipelineComparison } from '@/lib/studio/types'
import { formatCost, formatDuration } from '@/lib/studio/graph'
import { humanize } from '@/lib/studio/humanize'
import ModelCompareGrid from './ModelCompareGrid'
import PromptEditor from './PromptEditor'

type Tab = 'input' | 'output' | 'metrics' | 'compare' | 'prompt'

interface NodeInspectorProps {
  span: NodeSpan | null
  runId: string | null
  runMode: 'live' | 'lab' | null
  comparisons: PipelineComparison[]
  onComparisonsChange: (rows: PipelineComparison[]) => void
  onClose: () => void
}

export default function NodeInspector({
  span,
  runId,
  runMode,
  comparisons,
  onComparisonsChange,
  onClose,
}: NodeInspectorProps) {
  const [tab, setTab] = useState<Tab>('input')

  const isLab = runMode === 'lab'
  const isModelNode = span?.type === 'model'

  const tabs: Tab[] = useMemo(() => {
    const base: Tab[] = ['input', 'output', 'metrics']
    if (isLab && isModelNode) {
      base.push('compare', 'prompt')
    }
    return base
  }, [isLab, isModelNode])

  // 若切換節點後目前分頁不在可用列表,切回 input
  if (span && !tabs.includes(tab)) {
    setTab('input')
  }

  if (!span) {
    return (
      <aside className="flex h-full w-[360px] flex-shrink-0 items-center justify-center border-l border-zinc-800 bg-zinc-950/50 p-6 text-center text-xs text-zinc-500">
        點擊任一節點以查看詳細資訊
      </aside>
    )
  }

  return (
    <aside className="flex h-full w-[440px] flex-shrink-0 flex-col border-l border-zinc-800 bg-zinc-950/80">
      {/* Header */}
      <div className="flex items-start justify-between border-b border-zinc-800 px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] uppercase text-zinc-400">
              {span.type}
            </span>
            <h2 className="truncate text-sm font-semibold text-zinc-100">
              {span.label}
            </h2>
          </div>
          {span.model && (
            <p className="mt-1 text-xs text-violet-300">{span.model}</p>
          )}
          {/* Humanize summary — one-line "what happened" */}
          <HumanizeSummary span={span} />
        </div>
        <button
          onClick={onClose}
          className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 ml-2 shrink-0"
          aria-label="Close inspector"
        >
          ✕
        </button>
      </div>

      {/* Tabs */}
      <nav className="flex border-b border-zinc-800 text-xs">
        {tabs.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 border-b-2 py-2 transition-colors ${
              tab === t
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            {t === 'input'
              ? '輸入'
              : t === 'output'
              ? '輸出'
              : t === 'metrics'
              ? '指標'
              : t === 'compare'
              ? '比較'
              : '編輯'}
          </button>
        ))}
      </nav>

      {/* Body */}
      <div className="flex-1 overflow-auto px-4 py-3 text-xs text-zinc-300">
        {tab === 'input' && <InputView span={span} />}
        {tab === 'output' && <OutputView span={span} />}
        {tab === 'metrics' && <MetricsView span={span} />}
        {tab === 'compare' && runId && (
          <ModelCompareGrid
            runId={runId}
            nodeId={span.id}
            currentModel={span.model}
            initialComparisons={comparisons}
            onComparisonsChange={onComparisonsChange}
          />
        )}
        {tab === 'prompt' && runId && (
          <PromptEditor
            runId={runId}
            span={span}
            onComparisonCreated={(cmp) =>
              onComparisonsChange([...comparisons, cmp])
            }
          />
        )}
      </div>
    </aside>
  )
}

function InputView({ span }: { span: NodeSpan }) {
  if (!span.input_ref) {
    return <p className="text-zinc-500">此節點沒有輸入快照</p>
  }
  // 如果是 messages(model span),特別格式化
  if (Array.isArray(span.input_ref)) {
    return (
      <div className="space-y-2">
        {(span.input_ref as Array<{ role: string; content: unknown }>).map(
          (msg, i) => (
            <div
              key={i}
              className="rounded border border-zinc-800 bg-zinc-900/60 p-2"
            >
              <div className="mb-1 text-[10px] uppercase text-zinc-500">
                {msg.role}
              </div>
              <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-zinc-200">
                {typeof msg.content === 'string'
                  ? msg.content
                  : JSON.stringify(msg.content, null, 2)}
              </pre>
            </div>
          )
        )}
      </div>
    )
  }
  return <JsonBlock data={span.input_ref} />
}

function OutputView({ span }: { span: NodeSpan }) {
  if (!span.output_ref) {
    return <p className="text-zinc-500">此節點沒有輸出快照</p>
  }
  // model span 的 output 通常是 { text: ... }
  if (
    typeof span.output_ref === 'object' &&
    span.output_ref !== null &&
    'text' in (span.output_ref as Record<string, unknown>)
  ) {
    const text = (span.output_ref as { text: string }).text
    return (
      <pre className="whitespace-pre-wrap break-words rounded border border-zinc-800 bg-zinc-900/60 p-3 font-mono text-[11px] leading-relaxed text-zinc-100">
        {text}
      </pre>
    )
  }
  return <JsonBlock data={span.output_ref} />
}

function MetricsView({ span }: { span: NodeSpan }) {
  return (
    <dl className="space-y-2">
      <Metric label="狀態" value={span.status} />
      <Metric label="延遲" value={formatDuration(span.latency_ms)} />
      <Metric label="成本" value={formatCost(span.cost_usd)} />
      {span.model && <Metric label="模型" value={span.model} />}
      {span.tokens_in > 0 && (
        <Metric label="Input tokens" value={span.tokens_in.toLocaleString()} />
      )}
      {span.tokens_out > 0 && (
        <Metric label="Output tokens" value={span.tokens_out.toLocaleString()} />
      )}
      <Metric
        label="開始時間"
        value={new Date(span.started_at_ms).toISOString()}
      />
      {span.finished_at_ms && (
        <Metric
          label="結束時間"
          value={new Date(span.finished_at_ms).toISOString()}
        />
      )}
      {span.error && (
        <div className="mt-4 rounded border border-red-500/60 bg-red-950/40 p-2 text-red-300">
          <div className="mb-1 text-[10px] uppercase">Error</div>
          <pre className="whitespace-pre-wrap break-words">{span.error}</pre>
        </div>
      )}
      {Object.keys(span.metadata || {}).length > 0 && (
        <div className="mt-4">
          <div className="mb-1 text-[10px] uppercase text-zinc-500">Metadata</div>
          <JsonBlock data={span.metadata} />
        </div>
      )}
    </dl>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-zinc-500">{label}</dt>
      <dd className="truncate font-mono text-zinc-200">{value}</dd>
    </div>
  )
}

function JsonBlock({ data }: { data: unknown }) {
  return (
    <pre className="whitespace-pre-wrap break-words rounded border border-zinc-800 bg-zinc-900/60 p-3 font-mono text-[11px] leading-relaxed text-zinc-200">
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}

/** 「做了什麼」一行話 + 小細節列表（放在 header 下方） */
function HumanizeSummary({ span }: { span: NodeSpan }) {
  const h = humanize(span)
  if (!h.summary && h.details.length === 0) return null
  return (
    <div className="mt-2 rounded bg-zinc-900/60 border border-zinc-800 px-2 py-1.5">
      {h.summary && <p className="text-[11px] text-zinc-300">{h.summary}</p>}
      {h.details.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
          {h.details.slice(0, 4).map((d, i) => (
            <span key={i} className="text-[10px] text-zinc-500">
              {d.label}：<span className={d.code ? 'font-mono text-zinc-300' : 'text-zinc-300'}>{d.value}</span>
            </span>
          ))}
        </div>
      )}
      {h.notices.length > 0 && h.notices[0].level === 'error' && (
        <p className="mt-1 text-[10px] text-red-400">⚠ {h.notices[0].text}</p>
      )}
    </div>
  )
}
