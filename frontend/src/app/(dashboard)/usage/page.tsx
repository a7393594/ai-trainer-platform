'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

export default function UsagePage() {
  const [projectId, setProjectId] = useState('')
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<any>(null)
  const [days, setDays] = useState(30)
  const { t } = useI18n()

  useEffect(() => {
    getDemoContext().then((ctx) => {
      setProjectId(ctx.project_id)
      loadData(ctx.project_id, days)
    }).catch(() => setLoading(false))
  }, [])

  const loadData = async (pid: string, d: number) => {
    setLoading(true)
    try {
      const r = await fetch(`${AI}/api/v1/usage/cost/${pid}?days=${d}`)
      setData(await r.json())
    } catch {}
    setLoading(false)
  }

  const changePeriod = (d: number) => {
    setDays(d)
    if (projectId) loadData(projectId, d)
  }

  if (loading) return <div className="flex h-full items-center justify-center bg-zinc-900"><div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" /></div>

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-auto">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-lg font-medium text-zinc-200">{t('usage.title')}</h1>
            <p className="text-xs text-zinc-500">{t('usage.desc')}</p>
          </div>
          <div className="flex gap-1">
            {[7, 30, 90].map(d => (
              <button key={d} onClick={() => changePeriod(d)} className={`rounded px-3 py-1 text-xs ${days === d ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400'}`}>
                {d}D
              </button>
            ))}
          </div>
        </div>

        {data && (
          <div className="space-y-4">
            {/* Summary Cards */}
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4 text-center">
                <p className="text-2xl font-mono font-bold text-green-400">${data.total_cost?.toFixed(4)}</p>
                <p className="text-xs text-zinc-400 mt-1">{t('usage.totalCost')}</p>
              </div>
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4 text-center">
                <p className="text-2xl font-mono font-bold text-blue-400">{(data.total_tokens || 0).toLocaleString()}</p>
                <p className="text-xs text-zinc-400 mt-1">{t('usage.totalTokens')}</p>
              </div>
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4 text-center">
                <p className="text-2xl font-mono font-bold text-purple-400">{data.total_calls || 0}</p>
                <p className="text-xs text-zinc-400 mt-1">{t('usage.totalCalls')}</p>
              </div>
            </div>

            {/* Model Breakdown */}
            <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
              <h3 className="text-sm font-medium text-zinc-200 mb-3">{t('usage.byModel')}</h3>
              {data.by_model && Object.keys(data.by_model).length > 0 ? (
                <div className="space-y-2">
                  {Object.entries(data.by_model).sort((a: any, b: any) => b[1].cost - a[1].cost).map(([model, stats]: [string, any]) => {
                    const maxCost = Math.max(...Object.values(data.by_model).map((s: any) => s.cost))
                    return (
                      <div key={model} className="flex items-center gap-3">
                        <span className="text-xs text-zinc-300 w-36 truncate font-mono">{model.split('-').slice(0, 3).join('-')}</span>
                        <div className="flex-1 h-2 bg-zinc-700 rounded-full overflow-hidden">
                          <div className="h-full bg-green-500 rounded-full" style={{ width: `${maxCost > 0 ? (stats.cost / maxCost) * 100 : 0}%` }} />
                        </div>
                        <span className="text-xs font-mono text-green-400 w-20 text-right">${stats.cost?.toFixed(4)}</span>
                        <span className="text-[10px] text-zinc-500 w-16 text-right">{stats.calls} calls</span>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-xs text-zinc-500 text-center py-4">{t('usage.noData')}</p>
              )}
            </div>

            {/* Daily Trend Chart (SVG) */}
            <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
              <h3 className="text-sm font-medium text-zinc-200 mb-3">{t('usage.dailyTrend')}</h3>
              {data.daily_trend?.length > 1 ? (
                <CostChart data={data.daily_trend} />
              ) : (
                <p className="text-xs text-zinc-500 text-center py-8">{t('usage.noData')}</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function CostChart({ data }: { data: Array<{ date: string; cost: number; calls: number }> }) {
  const W = 600, H = 160, PX = 50, PY = 20
  const chartW = W - PX * 2, chartH = H - PY * 2

  const costs = data.map(d => d.cost)
  const maxC = Math.max(...costs) * 1.2 || 0.001

  const points = data.map((d, i) => ({
    x: PX + (i / Math.max(data.length - 1, 1)) * chartW,
    y: PY + chartH - (d.cost / maxC) * chartH,
    cost: d.cost,
    date: d.date.slice(5), // MM-DD
    calls: d.calls,
  }))

  const polyline = points.map(p => `${p.x},${p.y}`).join(' ')

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 180 }}>
      {/* Grid */}
      {[0, 0.25, 0.5, 0.75, 1].map(pct => {
        const y = PY + chartH * (1 - pct)
        const val = (maxC * pct).toFixed(4)
        return (
          <g key={pct}>
            <line x1={PX} y1={y} x2={W - PX} y2={y} stroke="#3f3f46" strokeWidth={0.5} />
            <text x={PX - 4} y={y + 3} textAnchor="end" fill="#71717a" fontSize={8}>${val}</text>
          </g>
        )
      })}
      {/* Area fill */}
      <polygon fill="#22c55e" fillOpacity={0.1} points={`${PX},${PY + chartH} ${polyline} ${W - PX},${PY + chartH}`} />
      {/* Line */}
      <polyline fill="none" stroke="#22c55e" strokeWidth={2} points={polyline} />
      {/* Dots + labels */}
      {points.map((p, i) => (
        <g key={i}>
          <circle cx={p.x} cy={p.y} r={3} fill="#22c55e" stroke="#18181b" strokeWidth={1.5} />
          {(data.length <= 15 || i % Math.ceil(data.length / 10) === 0) && (
            <text x={p.x} y={H - 2} textAnchor="middle" fill="#71717a" fontSize={8}>{p.date}</text>
          )}
        </g>
      ))}
    </svg>
  )
}
