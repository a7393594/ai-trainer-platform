'use client'

/**
 * ModelSelector — shared dropdown showing all registered models grouped by provider.
 * Fetches from /api/v1/models, auto-caches the result, marks unavailable providers.
 */

import { useEffect, useState, useMemo, useRef } from 'react'
import { listModels, type ModelInfo } from '@/lib/ai-engine'

interface Props {
  value: string
  onChange: (modelId: string) => void
  /** 若指定，顯示「專案預設」標記並在該 option 前加 ★ */
  projectDefault?: string
  /** 顯示「（未配置 API key）」警告當選中的模型不可用 */
  showWarning?: boolean
  className?: string
  disabled?: boolean
  /** 只列這些 providers（undefined = 全部） */
  providers?: string[]
}

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: 'Anthropic (Claude)',
  openai: 'OpenAI',
  google: 'Google (Gemini)',
  groq: 'Groq',
  deepseek: 'DeepSeek',
  openrouter: 'OpenRouter',
}

// Module-level cache — models list doesn't change often during a session
let cached: ModelInfo[] | null = null
let inflight: Promise<ModelInfo[]> | null = null

async function fetchModels(): Promise<ModelInfo[]> {
  if (cached) return cached
  if (inflight) return inflight
  inflight = (async () => {
    const res = await listModels()
    cached = res.models || []
    inflight = null
    return cached
  })()
  return inflight
}

export function ModelSelector({
  value, onChange, projectDefault, showWarning, className, disabled, providers,
}: Props) {
  const [models, setModels] = useState<ModelInfo[]>([])
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchModels()
      .then((m) => setModels(m))
      .catch(() => setModels([]))
      .finally(() => setLoading(false))
  }, [])

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const filtered = useMemo(() => {
    const lo = search.toLowerCase()
    return models.filter((m) => {
      if (providers && !providers.includes(m.provider)) return false
      if (!lo) return true
      return (
        m.id.toLowerCase().includes(lo) ||
        m.label.toLowerCase().includes(lo) ||
        m.provider.toLowerCase().includes(lo)
      )
    })
  }, [models, search, providers])

  const grouped = useMemo(() => {
    const g: Record<string, ModelInfo[]> = {}
    for (const m of filtered) {
      ;(g[m.provider] ||= []).push(m)
    }
    return g
  }, [filtered])

  const selectedModel = models.find((m) => m.id === value)
  const isUnavailable = showWarning && selectedModel && selectedModel.available === false

  return (
    <div ref={containerRef} className={`relative ${className || ''}`}>
      <button
        type="button"
        onClick={() => !disabled && setOpen((o) => !o)}
        disabled={disabled}
        className={`w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-300 outline-none hover:bg-zinc-750 transition-colors flex items-center gap-2 ${
          disabled ? 'opacity-50 cursor-not-allowed' : ''
        }`}
      >
        {isUnavailable && (
          <span title="此 provider 未配置 API key" className="text-yellow-400">⚠</span>
        )}
        <span className="flex-1 text-left truncate">
          {selectedModel ? (
            <>
              {selectedModel.label}
              <span className="ml-1 text-[10px] text-zinc-500">
                ({selectedModel.provider})
              </span>
            </>
          ) : (
            loading ? '載入中...' : (value || '選擇模型')
          )}
        </span>
        <span className="text-zinc-500 text-[10px]">▼</span>
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1 z-50 w-[320px] max-h-[480px] overflow-y-auto rounded border border-zinc-700 bg-zinc-900 shadow-xl">
          {/* Search */}
          <div className="sticky top-0 bg-zinc-900 border-b border-zinc-800 p-2">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜尋模型..."
              autoFocus
              className="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500"
            />
            {loading && <p className="text-[10px] text-zinc-500 mt-1">載入中...</p>}
            {!loading && filtered.length === 0 && (
              <p className="text-[10px] text-zinc-500 mt-1">沒有符合的模型</p>
            )}
          </div>

          {/* Grouped list */}
          {Object.entries(grouped).map(([provider, list]) => {
            const anyAvailable = list.some((m) => m.available)
            return (
              <div key={provider}>
                <div className="sticky top-[52px] bg-zinc-900/95 backdrop-blur border-b border-zinc-800 px-3 py-1 flex items-center justify-between">
                  <span className="text-[10px] uppercase font-semibold text-zinc-400">
                    {PROVIDER_LABELS[provider] || provider}
                  </span>
                  {!anyAvailable && (
                    <span className="text-[9px] text-yellow-400">未配置 API key</span>
                  )}
                </div>
                {list.map((m) => {
                  const selected = m.id === value
                  const isDefault = m.id === projectDefault
                  return (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => {
                        if (!m.available) return
                        onChange(m.id)
                        setOpen(false)
                        setSearch('')
                      }}
                      disabled={!m.available}
                      className={`w-full text-left px-3 py-1.5 text-xs transition-colors ${
                        selected
                          ? 'bg-blue-500/20 text-blue-300'
                          : m.available
                            ? 'text-zinc-300 hover:bg-zinc-800'
                            : 'text-zinc-600 cursor-not-allowed'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        {isDefault && <span title="專案預設" className="text-yellow-400">★</span>}
                        <span className="flex-1 truncate">{m.label}</span>
                        {m.cost && (
                          <span className="text-[9px] text-zinc-500 font-mono">{m.cost}</span>
                        )}
                      </div>
                      {m.notes && (
                        <p className="text-[9px] text-zinc-600 truncate mt-0.5">{m.notes}</p>
                      )}
                    </button>
                  )
                })}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
