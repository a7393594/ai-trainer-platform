'use client'

import { sourceTypeColor, sourceTypeLabel, useLabStore } from '@/lib/studio/labStore'

export default function CaseHeader() {
  const c = useLabStore((s) => s.selectedCase)
  const labRunId = useLabStore((s) => s.labRunId)
  const clearCase = useLabStore((s) => s.setSelectedCase)

  return (
    <div className="flex items-center justify-between gap-3 border-b border-zinc-800 bg-zinc-950/80 px-4 py-2">
      <div className="flex min-w-0 items-center gap-3">
        <h1 className="text-sm font-semibold text-zinc-100">
          🧪 Experiment Studio
        </h1>
        {c ? (
          <div className="flex min-w-0 items-center gap-2 text-[11px]">
            <span
              className={`rounded px-2 py-0.5 font-semibold uppercase ${sourceTypeColor(
                c.source_type
              )} bg-zinc-800`}
            >
              {sourceTypeLabel(c.source_type)}
            </span>
            <span className="truncate text-zinc-300">{c.title}</span>
            {labRunId && (
              <span className="rounded bg-amber-900/40 px-2 py-0.5 text-[10px] text-amber-300">
                lab · {labRunId.slice(0, 8)}
              </span>
            )}
          </div>
        ) : (
          <span className="text-[11px] text-zinc-500">尚未選取案例</span>
        )}
      </div>
      {c && (
        <button
          onClick={() => clearCase(null)}
          className="rounded border border-zinc-700 px-2 py-1 text-[10px] text-zinc-400 hover:bg-zinc-800"
        >
          切換案例
        </button>
      )}
    </div>
  )
}
