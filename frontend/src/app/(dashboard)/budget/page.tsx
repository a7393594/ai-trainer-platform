'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

const LEVEL_COLOR: Record<string, string> = {
  disabled: 'text-zinc-400',
  ok: 'text-green-400',
  threshold: 'text-yellow-400',
  exceeded: 'text-red-400',
}

type Status = {
  month: string
  budget_usd: number
  spent_usd: number
  pct: number
  threshold: number
  level: 'disabled' | 'ok' | 'threshold' | 'exceeded'
  webhook_configured: boolean
  last_alert_sent_for: string | null
  last_alert_month: string | null
}

export default function BudgetPage() {
  const [tenantId, setTenantId] = useState('')
  const [status, setStatus] = useState<Status | null>(null)
  const [budget, setBudget] = useState('')
  const [threshold, setThreshold] = useState('0.8')
  const [webhook, setWebhook] = useState('')
  const [saving, setSaving] = useState(false)
  const [checking, setChecking] = useState(false)
  const [lastCheck, setLastCheck] = useState<any>(null)

  useEffect(() => {
    getDemoContext()
      .then((ctx) => {
        setTenantId(ctx.tenant_id)
        load(ctx.tenant_id)
      })
      .catch(() => {})
  }, [])

  const load = async (tid: string) => {
    const r = await fetch(`${AI}/api/v1/budget/${tid}`)
    const d = await r.json()
    setStatus(d)
    if (typeof d.budget_usd === 'number' && d.budget_usd > 0) setBudget(String(d.budget_usd))
    if (typeof d.threshold === 'number') setThreshold(String(d.threshold))
  }

  const handleSave = async () => {
    if (!tenantId) return
    setSaving(true)
    try {
      await fetch(`${AI}/api/v1/budget/${tenantId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          monthly_budget_usd: budget ? Number(budget) : 0,
          budget_alert_threshold: threshold ? Number(threshold) : 0.8,
          budget_alert_webhook: webhook || null,
        }),
      })
      await load(tenantId)
    } catch {}
    setSaving(false)
  }

  const handleCheck = async () => {
    if (!tenantId) return
    setChecking(true)
    try {
      const r = await fetch(`${AI}/api/v1/budget/${tenantId}/check`, { method: 'POST' })
      setLastCheck(await r.json())
      await load(tenantId)
    } catch {}
    setChecking(false)
  }

  const pct = Math.round((status?.pct || 0) * 100)
  const barColor =
    status?.level === 'exceeded' ? 'bg-red-500'
    : status?.level === 'threshold' ? 'bg-yellow-500'
    : 'bg-green-500'

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-auto">
      <div className="max-w-3xl mx-auto space-y-4">
        <div>
          <h1 className="text-lg font-medium text-zinc-200">預算告警</h1>
          <p className="text-xs text-zinc-500">設定租戶月度成本上限並接入 webhook 告警</p>
        </div>

        {status && (
          <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-zinc-400">{status.month}</span>
              <span className={`text-xs font-medium ${LEVEL_COLOR[status.level] || 'text-zinc-400'}`}>
                {status.level.toUpperCase()}
              </span>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-mono text-zinc-200">${status.spent_usd.toFixed(2)}</span>
              <span className="text-xs text-zinc-500">
                / ${status.budget_usd > 0 ? status.budget_usd.toFixed(2) : '∞'} ({pct}%)
              </span>
            </div>
            <div className="mt-2 h-2 w-full rounded-full bg-zinc-700 overflow-hidden">
              <div className={`h-full ${barColor}`} style={{ width: `${Math.min(100, pct)}%` }} />
            </div>
            {status.last_alert_sent_for && (
              <p className="mt-2 text-[11px] text-zinc-500">
                本月已發送 <strong>{status.last_alert_sent_for}</strong> 告警
              </p>
            )}
          </div>
        )}

        <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4 space-y-3">
          <h3 className="text-sm font-medium text-zinc-200">設定</h3>
          <div>
            <label className="text-[11px] text-zinc-400">月預算上限 (USD)</label>
            <input
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              type="number"
              placeholder="0 = 停用"
              className="w-full mt-1 rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none"
            />
          </div>
          <div>
            <label className="text-[11px] text-zinc-400">告警門檻 (0-1，達到此比例會觸發告警)</label>
            <input
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              type="number"
              step="0.05"
              min="0"
              max="1"
              className="w-full mt-1 rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none"
            />
          </div>
          <div>
            <label className="text-[11px] text-zinc-400">告警 Webhook URL</label>
            <input
              value={webhook}
              onChange={(e) => setWebhook(e.target.value)}
              placeholder="https://hooks.slack.com/..."
              className="w-full mt-1 rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none"
            />
            <p className="mt-1 text-[11px] text-zinc-500">
              {status?.webhook_configured ? '✓ 已設定（留空清除）' : '尚未設定'}
            </p>
          </div>
          <div className="flex gap-2 justify-end">
            <button
              onClick={handleCheck}
              disabled={checking}
              className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700 disabled:opacity-50"
            >
              {checking ? 'Checking…' : '立即檢查'}
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50"
            >
              {saving ? 'Saving…' : '儲存'}
            </button>
          </div>
        </div>

        {lastCheck && (
          <div className={`rounded-lg border px-3 py-2 text-[11px] ${
            lastCheck.notified ? 'border-green-500/30 bg-green-500/5 text-green-300'
            : 'border-zinc-700 bg-zinc-800 text-zinc-400'
          }`}>
            Check: level <strong>{lastCheck.level}</strong>
            {lastCheck.notified ? ' · 已發送 webhook' : ` · 未發送（${lastCheck.reason || lastCheck.webhook_detail || '-'}）`}
          </div>
        )}
      </div>
    </div>
  )
}
