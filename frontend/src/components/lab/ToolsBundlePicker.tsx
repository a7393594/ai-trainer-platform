'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth-context'
import { getDemoContext } from '@/lib/ai-engine'
import { useLabStore } from '@/lib/studio/labStore'

const AI_ENGINE_URL =
  process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

interface ToolRow {
  id: string
  name: string
  description?: string | null
  tool_type?: string | null
}

interface Props {
  projectId: string
}

export default function ToolsBundlePicker({ projectId }: Props) {
  const { user } = useAuth()
  const overrides = useLabStore((s) => s.overrides)
  const setOverrides = useLabStore((s) => s.setOverrides)

  const [tools, setTools] = useState<ToolRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const ctx = await getDemoContext(user?.email || undefined)
        const res = await fetch(
          `${AI_ENGINE_URL}/api/v1/tools/${ctx.tenant_id}`
        )
        if (!res.ok) throw new Error(`${res.status}`)
        const data = await res.json()
        setTools(data.tools || [])
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setLoading(false)
      }
    }
    load()
    // projectId kept as dep so picker refreshes if caller scopes change later
  }, [user?.email, projectId])

  const bundle = new Set(overrides.tools_bundle || [])

  const toggle = (id: string) => {
    const next = new Set(bundle)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    const arr = Array.from(next)
    setOverrides({ tools_bundle: arr.length ? arr : undefined })
  }

  return (
    <div className="space-y-3">
      <p className="text-[11px] text-zinc-400">
        勾選的工具會取代 rerun 時的預設工具清單。不勾表示沿用專案預設（所有 active tools）。
      </p>

      {loading && <p className="text-[11px] text-zinc-500">載入工具清單…</p>}
      {error && <p className="text-[11px] text-red-400">{error}</p>}

      {!loading && tools.length === 0 && !error && (
        <p className="text-[11px] text-zinc-500">
          此租戶尚未註冊工具。先到 /tools 建立後再來。
        </p>
      )}

      <ul className="space-y-1">
        {tools.map((t) => {
          const checked = bundle.has(t.id)
          return (
            <li
              key={t.id}
              className={`rounded border p-2 ${
                checked
                  ? 'border-blue-500/60 bg-blue-950/20'
                  : 'border-zinc-800 bg-zinc-900/40'
              }`}
            >
              <label className="flex cursor-pointer items-start gap-2">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggle(t.id)}
                  className="mt-1 accent-blue-500"
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-semibold text-zinc-100">
                      {t.name}
                    </span>
                    {t.tool_type && (
                      <span className="rounded bg-zinc-800 px-1 text-[9px] text-zinc-400">
                        {t.tool_type}
                      </span>
                    )}
                  </div>
                  {t.description && (
                    <p className="mt-0.5 text-[10px] text-zinc-500">
                      {t.description}
                    </p>
                  )}
                </div>
              </label>
            </li>
          )
        })}
      </ul>

      {overrides.tools_bundle && overrides.tools_bundle.length > 0 && (
        <button
          onClick={() => setOverrides({ tools_bundle: undefined })}
          className="text-[10px] text-zinc-500 hover:text-zinc-300"
        >
          清除選擇（回到預設）
        </button>
      )}
    </div>
  )
}
