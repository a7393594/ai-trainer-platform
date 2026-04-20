'use client'

import { useLabStore } from '@/lib/studio/labStore'

export default function ResultsMatrix() {
  const history = useLabStore((s) => s.history)
  const clearHistory = useLabStore((s) => s.clearHistory)

  if (history.length === 0) {
    return (
      <p className="text-[11px] text-zinc-500">
        尚無結果。點下方「Run」或「Batch Run」後會出現在這裡。
      </p>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-zinc-400">
          {history.length} 筆實驗結果
        </span>
        <button
          onClick={clearHistory}
          className="text-[10px] text-zinc-500 hover:text-zinc-300"
        >
          清空
        </button>
      </div>
      <ul className="space-y-2">
        {history.map((h, i) => {
          const r = h.result
          return (
            <li
              key={h.id}
              className="rounded border border-zinc-800 bg-zinc-900/60 p-2"
            >
              <div className="mb-1 flex items-center gap-2 text-[10px] text-zinc-500">
                <span className="rounded bg-zinc-800 px-1 font-mono">
                  #{i + 1}
                </span>
                <span className="uppercase text-blue-400">
                  {r.source_type}
                </span>
                {r.model && <span>· {r.model}</span>}
                {typeof r.cost_usd === 'number' && (
                  <span>· ${r.cost_usd.toFixed(6)}</span>
                )}
                {typeof r.latency_ms === 'number' && (
                  <span>· {r.latency_ms}ms</span>
                )}
                {r.status && r.status !== 'completed' && (
                  <span className="text-amber-400">· {r.status}</span>
                )}
              </div>
              <p className="mb-1 line-clamp-2 whitespace-pre-wrap text-[11px] text-zinc-300">
                <span className="mr-1 text-zinc-500">Q:</span>
                {h.input}
              </p>
              <p className="whitespace-pre-wrap break-words text-[11px] text-zinc-100">
                <span className="mr-1 text-zinc-500">A:</span>
                {r.output || r.error || '(empty)'}
              </p>
              {r.trace && r.trace.length > 0 && (
                <details className="mt-1">
                  <summary className="cursor-pointer text-[10px] text-zinc-500">
                    trace ({r.trace.length} steps)
                  </summary>
                  <pre className="mt-1 max-h-40 overflow-auto rounded bg-black/40 p-1 font-mono text-[9px] text-zinc-400">
                    {JSON.stringify(r.trace, null, 2)}
                  </pre>
                </details>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
