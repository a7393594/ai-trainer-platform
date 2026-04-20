'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

const LEVEL_COLORS: Record<string, string> = {
  disabled: 'text-zinc-400',
  insufficient_data: 'text-zinc-400',
  ok: 'text-green-400',
  negative_high: 'text-yellow-400',
  wrong_high: 'text-red-400',
}

type Status = {
  window_hours: number
  total: number
  correct: number
  partial: number
  wrong: number
  wrong_ratio: number
  negative_ratio: number
  wrong_threshold: number
  negative_threshold: number
  min_samples: number
  enabled: boolean
  webhook_configured: boolean
  level: keyof typeof LEVEL_COLORS
}

export default function QualityPage() {
  const [projectId, setProjectId] = useState('')
  const [status, setStatus] = useState<Status | null>(null)
  const [enabled, setEnabled] = useState(false)
  const [windowHours, setWindowHours] = useState('24')
  const [minSamples, setMinSamples] = useState('10')
  const [wrongThr, setWrongThr] = useState('0.3')
  const [negThr, setNegThr] = useState('0.5')
  const [webhook, setWebhook] = useState('')
  const [saving, setSaving] = useState(false)
  const [checking, setChecking] = useState(false)
  const [lastCheck, setLastCheck] = useState<any>(null)

  useEffect(() => {
    getDemoContext()
      .then((ctx) => {
        setProjectId(ctx.project_id)
        load(ctx.project_id)
      })
      .catch(() => {})
  }, [])

  const load = async (pid: string) => {
    const r = await fetch(`${AI}/api/v1/quality/${pid}`)
    const d = await r.json()
    setStatus(d)
    setEnabled(!!d.enabled)
    setWindowHours(String(d.window_hours ?? 24))
    setMinSamples(String(d.min_samples ?? 10))
    setWrongThr(String(d.wrong_threshold ?? 0.3))
    setNegThr(String(d.negative_threshold ?? 0.5))
  }

  const save = async () => {
    if (!projectId) return
    setSaving(true)
    try {
      await fetch(`${AI}/api/v1/quality/${projectId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enabled,
          window_hours: Number(windowHours) || 24,
          min_samples: Number(minSamples) || 10,
          wrong_ratio_threshold: Number(wrongThr) || 0.3,
          negative_ratio_threshold: Number(negThr) || 0.5,
          webhook: webhook || null,
        }),
      })
      await load(projectId)
    } catch {}
    setSaving(false)
  }

  const check = async () => {
    if (!projectId) return
    setChecking(true)
    try {
      const r = await fetch(`${AI}/api/v1/quality/${projectId}/check`, { method: 'POST' })
      setLastCheck(await r.json())
      await load(projectId)
    } catch {}
    setChecking(false)
  }

  if (!status) {
    return <div className="flex h-full items-center justify-center bg-zinc-900 text-xs text-zinc-500">Loading…</div>
  }

  const wrongPct = Math.round((status.wrong_ratio || 0) * 100)
  const negPct = Math.round((status.negative_ratio || 0) * 100)

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-auto">
      <div className="max-w-3xl mx-auto space-y-4">
        <div>
          <h1 className="text-lg font-medium text-zinc-200">對話品質監測</h1>
          <p className="text-xs text-zinc-500">負面回饋比率超過門檻時主動通知</p>
        </div>

        <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-zinc-400">最近 {status.window_hours}h · {status.total} 筆回饋</span>
            <span className={`text-xs font-medium ${LEVEL_COLORS[status.level] || 'text-zinc-400'}`}>
              {status.level.toUpperCase()}
            </span>
          </div>

          <div className="grid grid-cols-3 gap-3 text-center">
            <Stat value={status.correct} label="Correct" color="text-green-400" />
            <Stat value={status.partial} label="Partial" color="text-yellow-400" />
            <Stat value={status.wrong} label="Wrong" color="text-red-400" />
          </div>

          <div className="mt-4 space-y-2">
            <RatioBar label="Wrong 比率" pct={wrongPct} threshold={Math.round(status.wrong_threshold * 100)} red />
            <RatioBar label="負面 (wrong+partial)" pct={negPct} threshold={Math.round(status.negative_threshold * 100)} />
          </div>
        </div>

        <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4 space-y-3">
          <h3 className="text-sm font-medium text-zinc-200">設定</h3>

          <label className="flex items-center gap-2 text-xs text-zinc-300">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            啟用監測
          </label>

          <div className="grid grid-cols-2 gap-3">
            <Field label="時間視窗 (小時)"><input type="number" min={1} value={windowHours} onChange={(e) => setWindowHours(e.target.value)} className="w-full rounded border border-zinc-600 bg-zinc-700 px-2 py-1.5 text-xs text-zinc-200 outline-none" /></Field>
            <Field label="最少樣本數"><input type="number" min={1} value={minSamples} onChange={(e) => setMinSamples(e.target.value)} className="w-full rounded border border-zinc-600 bg-zinc-700 px-2 py-1.5 text-xs text-zinc-200 outline-none" /></Field>
            <Field label="Wrong 門檻 (0-1)"><input type="number" min={0} max={1} step="0.05" value={wrongThr} onChange={(e) => setWrongThr(e.target.value)} className="w-full rounded border border-zinc-600 bg-zinc-700 px-2 py-1.5 text-xs text-zinc-200 outline-none" /></Field>
            <Field label="負面門檻 (0-1)"><input type="number" min={0} max={1} step="0.05" value={negThr} onChange={(e) => setNegThr(e.target.value)} className="w-full rounded border border-zinc-600 bg-zinc-700 px-2 py-1.5 text-xs text-zinc-200 outline-none" /></Field>
          </div>

          <Field label="告警 Webhook URL (Slack / generic)">
            <input value={webhook} onChange={(e) => setWebhook(e.target.value)} placeholder={status.webhook_configured ? '（已設定 — 留空清除）' : 'https://hooks.slack.com/...'} className="w-full rounded border border-zinc-600 bg-zinc-700 px-2 py-1.5 text-xs text-zinc-200 outline-none" />
          </Field>

          <div className="flex gap-2 justify-end">
            <button onClick={check} disabled={checking} className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700 disabled:opacity-50">
              {checking ? 'Checking…' : '立即檢查'}
            </button>
            <button onClick={save} disabled={saving} className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50">
              {saving ? 'Saving…' : '儲存'}
            </button>
          </div>
        </div>

        {lastCheck && (
          <div className={`rounded-lg border px-3 py-2 text-[11px] ${
            lastCheck.notified ? 'border-green-500/30 bg-green-500/5 text-green-300' : 'border-zinc-700 bg-zinc-800 text-zinc-400'
          }`}>
            Check: level <strong>{lastCheck.level}</strong>
            {lastCheck.notified ? ' · 已發送 webhook' : ` · 未發送（${lastCheck.reason || lastCheck.webhook_detail || '-'}）`}
          </div>
        )}
      </div>
    </div>
  )
}

function Stat({ value, label, color }: { value: number; label: string; color: string }) {
  return (
    <div className="rounded border border-zinc-700 bg-zinc-900/40 py-2">
      <p className={`text-xl font-mono ${color}`}>{value}</p>
      <p className="text-[10px] text-zinc-500">{label}</p>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-[11px] text-zinc-400 block mb-1">{label}</label>
      {children}
    </div>
  )
}

function RatioBar({ label, pct, threshold, red }: { label: string; pct: number; threshold: number; red?: boolean }) {
  const over = pct >= threshold
  const barColor = over ? (red ? 'bg-red-500' : 'bg-yellow-500') : 'bg-green-500'
  return (
    <div>
      <div className="flex justify-between text-[11px] text-zinc-400">
        <span>{label}</span>
        <span>{pct}% · thr {threshold}%</span>
      </div>
      <div className="mt-1 h-2 w-full rounded-full bg-zinc-700 overflow-hidden">
        <div className={`h-full ${barColor}`} style={{ width: `${Math.min(100, pct)}%` }} />
      </div>
    </div>
  )
}
