'use client'

import { useEffect, useMemo, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

type PromptVersion = {
  id: string
  version: number
  content: string
  is_active: boolean
  eval_score: number | null
}

type VariantForm = {
  prompt_version_id: string
  weight: string
  label: string
}

type VariantResult = {
  label: string
  prompt_version_id: string
  sessions: number
  correct: number
  partial: number
  wrong: number
  total: number
  correct_rate: number
}

export default function ABTestPage() {
  const [projectId, setProjectId] = useState('')
  const [status, setStatus] = useState<any>(null)
  const [prompts, setPrompts] = useState<PromptVersion[]>([])
  const [variants, setVariants] = useState<VariantForm[]>([
    { prompt_version_id: '', weight: '0.5', label: 'A' },
    { prompt_version_id: '', weight: '0.5', label: 'B' },
  ])
  const [enabled, setEnabled] = useState(true)
  const [saving, setSaving] = useState(false)
  const [results, setResults] = useState<VariantResult[]>([])
  const [loadingResults, setLoadingResults] = useState(false)
  const [concludingLabel, setConcludingLabel] = useState<string | null>(null)

  useEffect(() => {
    getDemoContext()
      .then((ctx) => {
        setProjectId(ctx.project_id)
        Promise.all([loadStatus(ctx.project_id), loadPrompts(ctx.project_id)])
      })
      .catch(() => {})
  }, [])

  const loadStatus = async (pid: string) => {
    const r = await fetch(`${AI}/api/v1/ab-test/${pid}`)
    const d = await r.json()
    setStatus(d)
    setEnabled(!!d.enabled)
    if (Array.isArray(d.variants) && d.variants.length > 0) {
      setVariants(d.variants.map((v: any) => ({
        prompt_version_id: v.prompt_version_id || '',
        weight: String(v.weight ?? 0.5),
        label: v.label || '',
      })))
    }
  }

  const loadPrompts = async (pid: string) => {
    const r = await fetch(`${AI}/api/v1/prompts/${pid}`)
    const d = await r.json()
    setPrompts(d.versions || [])
  }

  const loadResults = async () => {
    if (!projectId) return
    setLoadingResults(true)
    try {
      const r = await fetch(`${AI}/api/v1/ab-test/${projectId}/results`)
      const d = await r.json()
      setResults(d.variants || [])
    } catch {}
    setLoadingResults(false)
  }

  const updateVariant = (idx: number, patch: Partial<VariantForm>) => {
    setVariants((vs) => vs.map((v, i) => (i === idx ? { ...v, ...patch } : v)))
  }

  const addVariant = () => {
    setVariants([...variants, { prompt_version_id: '', weight: '0.5', label: String.fromCharCode(65 + variants.length) }])
  }

  const removeVariant = (idx: number) => {
    if (variants.length <= 2) return
    setVariants(variants.filter((_, i) => i !== idx))
  }

  const saveConfig = async () => {
    if (!projectId) return
    setSaving(true)
    try {
      await fetch(`${AI}/api/v1/ab-test/${projectId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enabled,
          variants: variants
            .filter((v) => v.prompt_version_id)
            .map((v) => ({
              prompt_version_id: v.prompt_version_id,
              weight: Number(v.weight) || 0,
              label: v.label || v.prompt_version_id.slice(0, 4),
            })),
        }),
      })
      await loadStatus(projectId)
    } catch {}
    setSaving(false)
  }

  const concludeWith = async (label: string) => {
    if (!projectId) return
    if (!confirm(`確定以變體 "${label}" 結束測試並啟用此 prompt 版本？`)) return
    setConcludingLabel(label)
    try {
      await fetch(`${AI}/api/v1/ab-test/${projectId}/conclude`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ winner_label: label }),
      })
      await Promise.all([loadStatus(projectId), loadResults(), loadPrompts(projectId)])
    } catch {}
    setConcludingLabel(null)
  }

  const totalWeight = useMemo(
    () => variants.reduce((sum, v) => sum + (Number(v.weight) || 0), 0),
    [variants],
  )

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-auto">
      <div className="max-w-4xl mx-auto space-y-4">
        <div>
          <h1 className="text-lg font-medium text-zinc-200">Prompt A/B 測試</h1>
          <p className="text-xs text-zinc-500">
            流量分流到多個 prompt 版本，根據回饋選出最佳。
            {status?.enabled && ' · 當前啟用中'}
          </p>
        </div>

        {/* Config */}
        <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-zinc-200">變體設定</h3>
            <label className="flex items-center gap-2 text-[11px] text-zinc-300">
              <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
              啟用測試
            </label>
          </div>

          {variants.map((v, idx) => (
            <div key={idx} className="rounded border border-zinc-700 bg-zinc-900/40 p-3 space-y-2">
              <div className="flex items-center gap-2">
                <input
                  value={v.label}
                  onChange={(e) => updateVariant(idx, { label: e.target.value })}
                  placeholder="Label (A/B/Control/Treatment)"
                  className="w-32 rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 outline-none"
                />
                <select
                  value={v.prompt_version_id}
                  onChange={(e) => updateVariant(idx, { prompt_version_id: e.target.value })}
                  className="flex-1 rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 outline-none"
                >
                  <option value="">-- 選擇 prompt 版本 --</option>
                  {prompts.map((p) => (
                    <option key={p.id} value={p.id}>
                      v{p.version}{p.is_active ? ' (active)' : ''}{p.eval_score != null ? ` · score ${Math.round(p.eval_score)}` : ''}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  value={v.weight}
                  onChange={(e) => updateVariant(idx, { weight: e.target.value })}
                  className="w-20 rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 outline-none"
                />
                <button
                  onClick={() => removeVariant(idx)}
                  disabled={variants.length <= 2}
                  className="text-xs text-red-400 hover:text-red-300 disabled:opacity-30"
                >
                  x
                </button>
              </div>
            </div>
          ))}

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button onClick={addVariant} className="text-xs text-blue-400 hover:text-blue-300">+ 新增變體</button>
              <span className="text-[11px] text-zinc-500">權重總和 {totalWeight.toFixed(2)}（會自動正規化）</span>
            </div>
            <button
              onClick={saveConfig}
              disabled={saving}
              className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50"
            >
              {saving ? 'Saving…' : '儲存配置'}
            </button>
          </div>
        </div>

        {/* Results */}
        <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-zinc-200">結果比對</h3>
            <button
              onClick={loadResults}
              disabled={loadingResults}
              className="rounded border border-zinc-600 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-700 disabled:opacity-50"
            >
              {loadingResults ? 'Loading…' : 'Refresh'}
            </button>
          </div>

          {results.length === 0 ? (
            <p className="text-xs text-zinc-500 text-center py-4">尚無結果（需先啟用測試並累積對話）</p>
          ) : (
            <div className="space-y-2">
              {results.map((r) => (
                <div key={r.label} className="rounded border border-zinc-700 bg-zinc-900/40 p-3">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <span className="text-sm text-zinc-200 font-medium">{r.label}</span>
                      <span className="ml-2 text-[10px] text-zinc-500">{r.prompt_version_id.slice(0, 8)}</span>
                    </div>
                    <button
                      onClick={() => concludeWith(r.label)}
                      disabled={concludingLabel === r.label || !status?.enabled}
                      className="rounded bg-green-600 px-3 py-1 text-[11px] text-white hover:bg-green-500 disabled:opacity-50"
                    >
                      {concludingLabel === r.label ? 'Concluding…' : '以此結束'}
                    </button>
                  </div>
                  <div className="grid grid-cols-5 gap-2 text-center">
                    <Mini value={r.sessions} label="sessions" />
                    <Mini value={r.correct} label="correct" color="text-green-400" />
                    <Mini value={r.partial} label="partial" color="text-yellow-400" />
                    <Mini value={r.wrong} label="wrong" color="text-red-400" />
                    <Mini value={`${Math.round(r.correct_rate * 100)}%`} label="correct rate" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function Mini({ value, label, color = 'text-zinc-200' }: { value: string | number; label: string; color?: string }) {
  return (
    <div>
      <p className={`text-sm font-mono ${color}`}>{value}</p>
      <p className="text-[10px] text-zinc-500">{label}</p>
    </div>
  )
}
