'use client'

import type { PipelineRunSummary } from '@/lib/studio/types'
import { formatCost, formatDuration } from '@/lib/studio/graph'

interface RunListProps {
  runs: PipelineRunSummary[]
  selectedId: string | null
  loading: boolean
  error: string | null
  onSelect: (runId: string) => void
  onRefresh: () => void
}

export default function RunList({
  runs,
  selectedId,
  loading,
  error,
  onSelect,
  onRefresh,
}: RunListProps) {
  return (
    <aside className="flex h-full w-[300px] flex-shrink-0 flex-col border-r border-zinc-800 bg-zinc-950/60">
      <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
        <h2 className="text-sm font-semibold text-zinc-100">最近 Pipeline Runs</h2>
        <button
          onClick={onRefresh}
          className="rounded border border-zinc-700 px-2 py-1 text-[10px] text-zinc-300 hover:bg-zinc-800"
          disabled={loading}
        >
          {loading ? '載入中…' : '🔄 重整'}
        </button>
      </div>

      {error && (
        <div className="m-3 rounded border border-red-500/50 bg-red-950/40 p-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <ul className="flex-1 overflow-y-auto">
        {!loading && runs.length === 0 && !error && (
          <li className="px-4 py-6 text-center text-xs text-zinc-500">
            暫無 pipeline runs。先到{' '}
            <a href="/chat" className="text-blue-400 underline">
              /chat
            </a>{' '}
            發送一則訊息,這裡就會出現。
          </li>
        )}

        {runs.map((run) => {
          const isActive = run.id === selectedId
          return (
            <li key={run.id}>
              <button
                onClick={() => onSelect(run.id)}
                className={`flex w-full flex-col gap-1 border-b border-zinc-900 px-4 py-3 text-left transition-colors ${
                  isActive ? 'bg-blue-950/30' : 'hover:bg-zinc-900/60'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span
                    className={`text-[10px] uppercase ${
                      run.mode === 'live'
                        ? 'text-emerald-400'
                        : 'text-amber-400'
                    }`}
                  >
                    {run.mode}
                  </span>
                  <span className="text-[10px] text-zinc-500">
                    {new Date(run.created_at).toLocaleString()}
                  </span>
                </div>
                <p className="line-clamp-2 text-xs text-zinc-200">
                  {run.input_text || '(empty input)'}
                </p>
                <div className="flex items-center justify-between text-[10px] text-zinc-500">
                  <span>{formatDuration(run.total_duration_ms)}</span>
                  <span>{formatCost(run.total_cost_usd)}</span>
                </div>
              </button>
            </li>
          )
        })}
      </ul>
    </aside>
  )
}
