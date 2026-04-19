'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

const STATUS_COLORS: Record<string, string> = {
  success: 'bg-green-500/20 text-green-400',
  error: 'bg-red-500/20 text-red-400',
  dry_run: 'bg-zinc-600/30 text-zinc-300',
}

type AuditLog = {
  id: string
  tenant_id: string
  user_id?: string
  action_type: string
  tool_id?: string
  status?: string
  duration_ms?: number
  request_data?: unknown
  response_data?: unknown
  created_at: string
}

const PAGE_SIZE = 50

export default function AuditPage() {
  const [tenantId, setTenantId] = useState('')
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  // Filters
  const [actionType, setActionType] = useState('')
  const [status, setStatus] = useState('')
  const [offset, setOffset] = useState(0)

  useEffect(() => {
    getDemoContext()
      .then((ctx) => {
        setTenantId(ctx.tenant_id)
        load(ctx.tenant_id, '', '', 0)
      })
      .catch(() => setLoading(false))
  }, [])

  const load = async (tid: string, at: string, st: string, off: number) => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (at) params.set('action_type', at)
      if (st) params.set('status', st)
      params.set('limit', String(PAGE_SIZE))
      params.set('offset', String(off))
      const r = await fetch(`${AI}/api/v1/audit/${tid}?${params.toString()}`)
      const d = await r.json()
      setLogs(d.logs || [])
    } catch {
      setLogs([])
    }
    setLoading(false)
  }

  const applyFilters = () => {
    setOffset(0)
    if (tenantId) load(tenantId, actionType, status, 0)
  }

  const nextPage = () => {
    const o = offset + PAGE_SIZE
    setOffset(o)
    if (tenantId) load(tenantId, actionType, status, o)
  }

  const prevPage = () => {
    const o = Math.max(0, offset - PAGE_SIZE)
    setOffset(o)
    if (tenantId) load(tenantId, actionType, status, o)
  }

  const fmtJson = (v: unknown) => {
    try {
      return JSON.stringify(v, null, 2)
    } catch {
      return String(v)
    }
  }

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-auto">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-lg font-medium text-zinc-200 mb-1">稽核日誌</h1>
        <p className="text-xs text-zinc-500 mb-4">檢視租戶層級的工具呼叫、動作與錯誤</p>

        <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-3 mb-3 flex flex-wrap items-center gap-2">
          <input
            value={actionType}
            onChange={(e) => setActionType(e.target.value)}
            placeholder="action_type (如 tool_call)"
            className="rounded border border-zinc-600 bg-zinc-700 px-2 py-1.5 text-xs text-zinc-200 outline-none"
          />
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="rounded border border-zinc-600 bg-zinc-700 px-2 py-1.5 text-xs text-zinc-200 outline-none"
          >
            <option value="">All status</option>
            <option value="success">success</option>
            <option value="error">error</option>
            <option value="dry_run">dry_run</option>
          </select>
          <button
            onClick={applyFilters}
            className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500"
          >
            Apply
          </button>
          <div className="ml-auto flex items-center gap-2 text-xs text-zinc-400">
            <button
              onClick={prevPage}
              disabled={offset === 0}
              className="rounded border border-zinc-600 px-2 py-1 hover:bg-zinc-700 disabled:opacity-40"
            >
              Prev
            </button>
            <span>
              offset {offset}–{offset + logs.length}
            </span>
            <button
              onClick={nextPage}
              disabled={logs.length < PAGE_SIZE}
              className="rounded border border-zinc-600 px-2 py-1 hover:bg-zinc-700 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>

        {loading && <div className="text-xs text-zinc-500">Loading…</div>}

        {!loading && (
          <div className="rounded-lg border border-zinc-700 overflow-hidden">
            <div className="grid grid-cols-[140px_140px_1fr_80px_90px_80px] items-center gap-2 border-b border-zinc-700 bg-zinc-800 px-3 py-2 text-[11px] font-medium text-zinc-400">
              <span>Time</span>
              <span>Action</span>
              <span>Tool / User</span>
              <span>Status</span>
              <span className="text-right">Latency</span>
              <span></span>
            </div>
            {logs.length === 0 ? (
              <p className="text-sm text-zinc-500 text-center py-8">No logs</p>
            ) : (
              logs.map((log) => (
                <div key={log.id} className="border-b border-zinc-800 last:border-none">
                  <button
                    onClick={() => setExpandedId(expandedId === log.id ? null : log.id)}
                    className="w-full grid grid-cols-[140px_140px_1fr_80px_90px_80px] items-center gap-2 px-3 py-2 text-left text-xs hover:bg-zinc-800/50"
                  >
                    <span className="text-zinc-500">{new Date(log.created_at).toLocaleString('zh-TW')}</span>
                    <code className="text-zinc-300">{log.action_type}</code>
                    <span className="text-zinc-400 truncate">
                      {log.tool_id ? <code>{log.tool_id.slice(0, 8)}</code> : '—'}
                      {log.user_id && <span className="ml-2 text-zinc-500">user={log.user_id.slice(0, 6)}</span>}
                    </span>
                    <span className={`rounded px-1.5 py-0.5 text-[10px] ${STATUS_COLORS[log.status || ''] || 'bg-zinc-600/30 text-zinc-400'}`}>
                      {log.status || '-'}
                    </span>
                    <span className="text-right font-mono text-zinc-400">{log.duration_ms ?? '-'}ms</span>
                    <span className="text-zinc-600 text-right">{expandedId === log.id ? '[-]' : '[+]'}</span>
                  </button>
                  {expandedId === log.id && (
                    <div className="grid grid-cols-2 gap-2 border-t border-zinc-800 bg-zinc-900/60 p-3">
                      <div>
                        <p className="text-[10px] text-zinc-500 mb-1">Request</p>
                        <pre className="max-h-40 overflow-auto rounded border border-zinc-700 bg-zinc-900 p-2 text-[10px] text-zinc-300 font-mono">
                          {fmtJson(log.request_data)}
                        </pre>
                      </div>
                      <div>
                        <p className="text-[10px] text-zinc-500 mb-1">Response</p>
                        <pre className="max-h-40 overflow-auto rounded border border-zinc-700 bg-zinc-900 p-2 text-[10px] text-zinc-300 font-mono">
                          {fmtJson(log.response_data)}
                        </pre>
                      </div>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  )
}
