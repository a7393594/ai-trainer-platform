'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

const URGENCY_COLORS: Record<string, string> = {
  low: 'bg-zinc-600/30 text-zinc-300',
  normal: 'bg-blue-500/20 text-blue-300',
  high: 'bg-yellow-500/20 text-yellow-300',
  urgent: 'bg-red-500/20 text-red-300',
}

type PendingItem = {
  id: string
  session_id: string
  project_id: string
  created_at: string
  handoff: {
    status: string
    reason: string
    urgency: string
    triggered_by: string
    requested_at: string
  }
}

export default function HandoffPage() {
  const [tenantId, setTenantId] = useState('')
  const [items, setItems] = useState<PendingItem[]>([])
  const [loading, setLoading] = useState(true)
  const [resolvingId, setResolvingId] = useState<string | null>(null)
  const [agent, setAgent] = useState('agent')
  const [note, setNote] = useState('')

  useEffect(() => {
    getDemoContext()
      .then((ctx) => {
        setTenantId(ctx.tenant_id)
        load(ctx.tenant_id)
      })
      .catch(() => setLoading(false))
  }, [])

  const load = async (tid: string) => {
    setLoading(true)
    try {
      const r = await fetch(`${AI}/api/v1/handoff/pending/${tid}?limit=100`)
      const d = await r.json()
      setItems(d.pending || [])
    } catch {
      setItems([])
    }
    setLoading(false)
  }

  const handleResolve = async (id: string) => {
    setResolvingId(id)
    try {
      await fetch(`${AI}/api/v1/handoff/${id}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resolved_by: agent || 'agent', note }),
      })
      setNote('')
      if (tenantId) await load(tenantId)
    } catch {}
    setResolvingId(null)
  }

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-auto">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-lg font-medium text-zinc-200">Hand-off 儀表板</h1>
            <p className="text-xs text-zinc-500">真人客服處理尚未解決的 AI 升級請求</p>
          </div>
          <div className="flex items-center gap-2">
            <input
              value={agent}
              onChange={(e) => setAgent(e.target.value)}
              placeholder="客服名"
              className="rounded border border-zinc-600 bg-zinc-700 px-2 py-1.5 text-xs text-zinc-200 outline-none"
            />
            <button
              onClick={() => tenantId && load(tenantId)}
              className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700"
            >
              Refresh
            </button>
          </div>
        </div>

        {loading && <div className="text-xs text-zinc-500">Loading…</div>}

        {!loading && items.length === 0 && (
          <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-6 text-center text-sm text-zinc-500">
            沒有待處理的 hand-off
          </div>
        )}

        <div className="space-y-2">
          {items.map((item) => (
            <div key={item.id} className="rounded-lg border border-zinc-700 bg-zinc-800/60 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`rounded px-2 py-0.5 text-[10px] ${URGENCY_COLORS[item.handoff.urgency] || URGENCY_COLORS.normal}`}>
                      {item.handoff.urgency}
                    </span>
                    <span className="text-[11px] text-zinc-500">by {item.handoff.triggered_by}</span>
                    <span className="text-[11px] text-zinc-500">{new Date(item.handoff.requested_at).toLocaleString('zh-TW')}</span>
                  </div>
                  <p className="text-sm text-zinc-200">{item.handoff.reason}</p>
                  <p className="text-[11px] text-zinc-500 mt-1">
                    session <code>{item.session_id.slice(0, 8)}</code>
                    {' · '}
                    project <code>{item.project_id.slice(0, 8)}</code>
                  </p>
                </div>
                <div className="flex flex-col gap-2 items-end">
                  <input
                    value={resolvingId === item.id ? note : ''}
                    onChange={(e) => setNote(e.target.value)}
                    onFocus={() => setResolvingId(item.id)}
                    placeholder="解決備註（可選）"
                    className="w-60 rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-[11px] text-zinc-200 outline-none"
                  />
                  <button
                    onClick={() => handleResolve(item.id)}
                    disabled={resolvingId === item.id && !!note && note.length > 500}
                    className="rounded bg-green-600 px-3 py-1 text-[11px] text-white hover:bg-green-500 disabled:opacity-50"
                  >
                    {resolvingId === item.id ? 'Resolving…' : 'Mark Resolved'}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
