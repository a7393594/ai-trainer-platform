'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { listCases } from '@/lib/studio/api'
import {
  sourceTypeColor,
  sourceTypeLabel,
  useLabStore,
} from '@/lib/studio/labStore'
import type { CaseSummary, LabSourceType } from '@/lib/studio/types'

const SOURCE_TABS: Array<{ value: LabSourceType | 'all'; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'pipeline', label: 'Pipeline' },
  { value: 'workflow', label: 'Workflow' },
  { value: 'session', label: 'Chat' },
  { value: 'comparison', label: 'Compare' },
]

interface Props {
  projectId: string
}

export default function CaseBrowser({ projectId }: Props) {
  const selectedCase = useLabStore((s) => s.selectedCase)
  const setSelectedCase = useLabStore((s) => s.setSelectedCase)

  const [tab, setTab] = useState<LabSourceType | 'all'>('all')
  const [items, setItems] = useState<CaseSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const fetchCases = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    setError(null)
    try {
      const res = await listCases(projectId, {
        sourceType: tab === 'all' ? undefined : tab,
        limit: 40,
      })
      setItems(res.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [projectId, tab])

  useEffect(() => {
    fetchCases()
  }, [fetchCases])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return items
    return items.filter(
      (it) =>
        it.title.toLowerCase().includes(q) ||
        (it.summary || '').toLowerCase().includes(q)
    )
  }, [items, search])

  return (
    <aside className="flex h-full w-[320px] flex-shrink-0 flex-col border-r border-zinc-800 bg-zinc-950/60">
      <div className="border-b border-zinc-800 px-4 py-3">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-100">過往案例</h2>
          <button
            onClick={fetchCases}
            disabled={loading}
            className="rounded border border-zinc-700 px-2 py-1 text-[10px] text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
          >
            {loading ? '載入中…' : '🔄 重整'}
          </button>
        </div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="搜尋…"
          className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 placeholder-zinc-500 focus:border-blue-500 focus:outline-none"
        />
      </div>

      <div className="flex border-b border-zinc-800 px-2">
        {SOURCE_TABS.map((t) => (
          <button
            key={t.value}
            onClick={() => setTab(t.value)}
            className={`flex-1 border-b-2 px-2 py-2 text-[10px] transition-colors ${
              tab === t.value
                ? 'border-blue-500 text-blue-300'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="m-3 rounded border border-red-500/50 bg-red-950/40 p-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <ul className="flex-1 overflow-y-auto">
        {!loading && filtered.length === 0 && !error && (
          <li className="px-4 py-6 text-center text-xs text-zinc-500">
            暫無案例
          </li>
        )}

        {filtered.map((c) => {
          const key = `${c.source_type}:${c.id}`
          const selectedKey = selectedCase
            ? `${selectedCase.source_type}:${selectedCase.id}`
            : null
          const isActive = key === selectedKey
          return (
            <li key={key}>
              <button
                onClick={() => setSelectedCase(c)}
                className={`flex w-full flex-col gap-1 border-b border-zinc-900 px-4 py-3 text-left transition-colors ${
                  isActive ? 'bg-blue-950/30' : 'hover:bg-zinc-900/60'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span
                    className={`text-[10px] font-semibold uppercase ${sourceTypeColor(
                      c.source_type
                    )}`}
                  >
                    {sourceTypeLabel(c.source_type)}
                  </span>
                  <span className="text-[10px] text-zinc-500">
                    {c.created_at
                      ? new Date(c.created_at).toLocaleString()
                      : '-'}
                  </span>
                </div>
                <p className="line-clamp-2 text-xs text-zinc-200">{c.title}</p>
                <p className="line-clamp-1 text-[10px] text-zinc-500">
                  {c.summary}
                </p>
              </button>
            </li>
          )
        })}
      </ul>
    </aside>
  )
}
