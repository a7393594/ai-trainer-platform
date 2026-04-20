'use client'

import { useEffect, useState } from 'react'
import { useLabStore } from '@/lib/studio/labStore'

const AI_ENGINE_URL =
  process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

interface DocRow {
  id: string
  title: string
  status?: string | null
  chunk_count?: number | null
  source_type?: string | null
}

interface Props {
  projectId: string
}

type BackendChoice = '' | 'pgvector' | 'qdrant' | 'keyword'

export default function KnowledgeOverridePanel({ projectId }: Props) {
  const overrides = useLabStore((s) => s.overrides)
  const setOverrides = useLabStore((s) => s.setOverrides)

  const [docs, setDocs] = useState<DocRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!projectId) return
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch(
          `${AI_ENGINE_URL}/api/v1/knowledge/${projectId}`
        )
        if (!res.ok) throw new Error(`${res.status}`)
        const data = await res.json()
        setDocs(data.documents || [])
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [projectId])

  const ko = overrides.knowledge_override || {}
  const include = new Set(ko.doc_ids_include || [])
  const exclude = new Set(ko.doc_ids_exclude || [])

  const setMode = (docId: string, mode: 'default' | 'include' | 'exclude') => {
    const nextInc = new Set(include)
    const nextExc = new Set(exclude)
    nextInc.delete(docId)
    nextExc.delete(docId)
    if (mode === 'include') nextInc.add(docId)
    if (mode === 'exclude') nextExc.add(docId)

    const next = {
      ...ko,
      doc_ids_include: nextInc.size ? Array.from(nextInc) : undefined,
      doc_ids_exclude: nextExc.size ? Array.from(nextExc) : undefined,
    }
    const empty =
      !next.doc_ids_include && !next.doc_ids_exclude && !next.backend
    setOverrides({ knowledge_override: empty ? undefined : next })
  }

  const setBackend = (b: BackendChoice) => {
    const next = { ...ko, backend: b || undefined }
    const empty = !next.doc_ids_include && !next.doc_ids_exclude && !next.backend
    setOverrides({
      knowledge_override: empty
        ? undefined
        : (next as typeof overrides.knowledge_override),
    })
  }

  return (
    <div className="space-y-3">
      <p className="text-[11px] text-zinc-400">
        選「只用」限制只搜索特定文件；選「排除」把該文件從 RAG 結果剔除。不勾表示沿用預設。
      </p>

      <div>
        <label className="block text-[11px] text-zinc-400">
          Vector Backend 覆寫
        </label>
        <select
          value={ko.backend || ''}
          onChange={(e) => setBackend(e.target.value as BackendChoice)}
          className="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 p-2 text-xs text-zinc-100 focus:border-blue-500 focus:outline-none"
        >
          <option value="">（沿用 env 預設）</option>
          <option value="pgvector">pgvector</option>
          <option value="qdrant">qdrant</option>
          <option value="keyword">keyword (fallback)</option>
        </select>
      </div>

      {loading && <p className="text-[11px] text-zinc-500">載入文件清單…</p>}
      {error && <p className="text-[11px] text-red-400">{error}</p>}

      {!loading && docs.length === 0 && !error && (
        <p className="text-[11px] text-zinc-500">
          此專案尚無知識庫文件。先到 /knowledge 上傳後再來。
        </p>
      )}

      <ul className="space-y-1">
        {docs.map((d) => {
          const mode = include.has(d.id)
            ? 'include'
            : exclude.has(d.id)
              ? 'exclude'
              : 'default'
          return (
            <li
              key={d.id}
              className="rounded border border-zinc-800 bg-zinc-900/40 p-2"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[11px] font-semibold text-zinc-100">
                    {d.title}
                  </p>
                  <p className="text-[10px] text-zinc-500">
                    {d.status || '?'} · {d.chunk_count || 0} chunks
                  </p>
                </div>
                <div className="flex gap-1">
                  {(['default', 'include', 'exclude'] as const).map((m) => (
                    <button
                      key={m}
                      onClick={() => setMode(d.id, m)}
                      className={`rounded px-2 py-0.5 text-[10px] transition-colors ${
                        mode === m
                          ? m === 'include'
                            ? 'bg-emerald-600 text-white'
                            : m === 'exclude'
                              ? 'bg-red-600 text-white'
                              : 'bg-zinc-700 text-white'
                          : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
                      }`}
                    >
                      {m === 'default' ? '預設' : m === 'include' ? '只用' : '排除'}
                    </button>
                  ))}
                </div>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
