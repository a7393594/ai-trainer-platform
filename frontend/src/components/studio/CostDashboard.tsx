'use client'

import type { PipelineRunDetail } from '@/lib/studio/types'
import { formatCost, formatDuration } from '@/lib/studio/graph'

interface CostDashboardProps {
  run: PipelineRunDetail | null
  canForkToLab?: boolean
  forking?: boolean
  onForkToLab?: () => void
  onDeleteLabRun?: () => void
  deleting?: boolean
}

export default function CostDashboard({
  run,
  canForkToLab,
  forking,
  onForkToLab,
  onDeleteLabRun,
  deleting,
}: CostDashboardProps) {
  if (!run) {
    return (
      <header className="flex h-14 items-center border-b border-zinc-800 bg-zinc-950/60 px-6">
        <h1 className="text-sm font-semibold text-zinc-100">Pipeline Studio</h1>
        <span className="ml-4 text-xs text-zinc-500">
          從左側選取一個 run 以查看詳細分析
        </span>
      </header>
    )
  }

  const nodes = run.nodes_json?.nodes ?? []
  const modelNodes = nodes.filter((n) => n.type === 'model')
  const processNodes = nodes.filter(
    (n) => n.type !== 'model' && n.type !== 'input' && n.type !== 'output'
  )
  const modelCost = modelNodes.reduce((sum, n) => sum + n.cost_usd, 0)
  const processCost = processNodes.reduce((sum, n) => sum + n.cost_usd, 0)
  const modelTime = modelNodes.reduce((sum, n) => sum + n.latency_ms, 0)

  return (
    <header className="flex h-14 items-center gap-6 border-b border-zinc-800 bg-zinc-950/60 px-6">
      <h1 className="text-sm font-semibold text-zinc-100">Pipeline Studio</h1>

      <div className="flex items-center gap-6 text-xs">
        <Stat label="模式" value={run.mode.toUpperCase()} accent={run.mode === 'live' ? 'text-emerald-400' : 'text-amber-400'} />
        <Stat label="總成本" value={formatCost(run.total_cost_usd)} />
        <Stat label="總延遲" value={formatDuration(run.total_duration_ms)} />
        <Stat
          label="LLM 節點"
          value={`${modelNodes.length}(${formatCost(modelCost)} / ${formatDuration(
            modelTime
          )})`}
        />
        <Stat
          label="流程節點"
          value={`${processNodes.length}${
            processCost > 0 ? ` / ${formatCost(processCost)}` : ''
          }`}
        />
      </div>

      <div className="ml-auto flex items-center gap-3 text-[11px] text-zinc-500">
        <span>{new Date(run.created_at).toLocaleString()}</span>
        {canForkToLab && onForkToLab && (
          <button
            onClick={onForkToLab}
            disabled={forking}
            className="rounded border border-amber-500/60 bg-amber-950/40 px-2 py-1 text-[11px] text-amber-300 hover:bg-amber-900/60 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {forking ? 'Forking…' : '🧪 Fork to Lab'}
          </button>
        )}
        {run.mode === 'lab' && run.parent_run_id && (
          <span className="rounded border border-amber-500/60 bg-amber-950/40 px-2 py-1 text-[11px] text-amber-300">
            Lab fork of {run.parent_run_id.slice(0, 8)}
          </span>
        )}
        {run.mode === 'lab' && onDeleteLabRun && (
          <button
            onClick={onDeleteLabRun}
            disabled={deleting}
            className="rounded border border-red-500/60 bg-red-950/40 px-2 py-1 text-[11px] text-red-300 hover:bg-red-900/60 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {deleting ? '刪除中…' : '🗑 刪除'}
          </button>
        )}
      </div>
    </header>
  )
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string
  value: string
  accent?: string
}) {
  return (
    <div className="flex flex-col leading-tight">
      <span className="text-[10px] uppercase text-zinc-500">{label}</span>
      <span className={`font-mono ${accent ?? 'text-zinc-100'}`}>{value}</span>
    </div>
  )
}
