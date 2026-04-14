'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

type Tab = 'overview' | 'cost' | 'quality' | 'tools'

export default function OverviewPage() {
  const [projectId, setProjectId] = useState('')
  const [tab, setTab] = useState<Tab>('overview')
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(true)
  const [analytics, setAnalytics] = useState<any>(null)
  const [cost, setCost] = useState<any>(null)
  const [trend, setTrend] = useState<any[]>([])
  const [phaseStatus, setPhaseStatus] = useState<any>(null)
  const { t } = useI18n()

  useEffect(() => {
    getDemoContext().then(ctx => {
      setProjectId(ctx.project_id)
      loadAll(ctx.project_id, days)
    }).catch(() => setLoading(false))
  }, [])

  const loadAll = async (pid: string, d: number) => {
    setLoading(true)
    const [aRes, cRes, tRes, pRes] = await Promise.all([
      fetch(`${AI}/api/v1/analytics/${pid}?days=${d}`).then(r => r.json()).catch(() => null),
      fetch(`${AI}/api/v1/usage/cost/${pid}?days=${d}`).then(r => r.json()).catch(() => null),
      fetch(`${AI}/api/v1/eval/analytics/trend/${pid}`).then(r => r.json()).catch(() => ({ trend: [] })),
      fetch(`${AI}/api/v1/eval/analytics/phase-status/${pid}`).then(r => r.json()).catch(() => null),
    ])
    setAnalytics(aRes); setCost(cRes); setTrend(tRes.trend || []); setPhaseStatus(pRes)
    setLoading(false)
  }

  const changeDays = (d: number) => { setDays(d); if (projectId) loadAll(projectId, d) }

  if (loading) return <div className="flex h-full items-center justify-center bg-zinc-900"><div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" /></div>

  const o = analytics?.overview || {}
  const fb = analytics?.feedback || {}

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-auto">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-lg font-medium text-zinc-200">{t('overview.title')}</h1>
            <p className="text-xs text-zinc-500">{t('overview.desc')}</p>
          </div>
          <div className="flex gap-1">
            {[7, 30, 90].map(d => (
              <button key={d} onClick={() => changeDays(d)} className={`rounded px-3 py-1 text-xs ${days === d ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400'}`}>{d}D</button>
            ))}
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-4">
          {([
            { key: 'overview' as const, label: t('overview.tab.overview') },
            { key: 'cost' as const, label: t('overview.tab.cost') },
            { key: 'quality' as const, label: t('overview.tab.quality') },
            { key: 'tools' as const, label: t('overview.tab.tools') },
          ]).map(({ key, label }) => (
            <button key={key} onClick={() => setTab(key)} className={`px-4 py-1.5 rounded text-xs ${tab === key ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200'}`}>{label}</button>
          ))}
        </div>

        {/* Overview Tab */}
        {tab === 'overview' && analytics && (
          <div className="space-y-4">
            <div className="grid grid-cols-4 gap-3">
              <Card value={o.total_sessions || 0} label={t('overview.sessions')} color="text-blue-400" />
              <Card value={o.total_messages || 0} label={t('overview.messages')} color="text-green-400" />
              <Card value={o.user_messages || 0} label={t('overview.userMsgs')} color="text-purple-400" />
              <Card value={o.avg_messages_per_session || 0} label={t('overview.avgPerSession')} color="text-yellow-400" />
            </div>
            {/* Feedback */}
            <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
              <h3 className="text-sm font-medium text-zinc-200 mb-3">{t('overview.feedback')}</h3>
              <div className="grid grid-cols-4 gap-3">
                <div className="rounded bg-green-500/10 p-3 text-center"><p className="text-xl font-mono font-bold text-green-400">{fb.correct || 0}</p><p className="text-[10px] text-zinc-400">Correct</p></div>
                <div className="rounded bg-yellow-500/10 p-3 text-center"><p className="text-xl font-mono font-bold text-yellow-400">{fb.partial || 0}</p><p className="text-[10px] text-zinc-400">Partial</p></div>
                <div className="rounded bg-red-500/10 p-3 text-center"><p className="text-xl font-mono font-bold text-red-400">{fb.wrong || 0}</p><p className="text-[10px] text-zinc-400">Wrong</p></div>
                <div className="rounded bg-zinc-700/50 p-3 text-center"><p className="text-xl font-mono font-bold text-zinc-300">{fb.total || 0}</p><p className="text-[10px] text-zinc-400">Total</p></div>
              </div>
              {(fb.total || 0) > 0 && (
                <div className="mt-3 flex h-3 rounded-full overflow-hidden bg-zinc-700">
                  <div className="bg-green-500" style={{ width: `${(fb.correct / fb.total) * 100}%` }} />
                  <div className="bg-yellow-500" style={{ width: `${(fb.partial / fb.total) * 100}%` }} />
                  <div className="bg-red-500" style={{ width: `${(fb.wrong / fb.total) * 100}%` }} />
                </div>
              )}
            </div>
            {/* Project health */}
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
                <p className="text-xs text-zinc-400 mb-1">Prompt</p>
                <p className="text-2xl font-mono text-zinc-200">{analytics.prompts?.total_versions || 0}</p>
                <p className="text-[10px] text-zinc-500">{analytics.prompts?.active_version ? `v${analytics.prompts.active_version} active` : ''}</p>
              </div>
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
                <p className="text-xs text-zinc-400 mb-1">{t('overview.knowledge')}</p>
                <p className="text-2xl font-mono text-zinc-200">{analytics.knowledge?.total_docs || 0}</p>
                <p className="text-[10px] text-zinc-500">documents</p>
              </div>
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
                <p className="text-xs text-zinc-400 mb-1">Eval</p>
                <p className="text-2xl font-mono text-zinc-200">{analytics.eval?.total_runs || 0}</p>
                <p className="text-[10px] text-zinc-500">{analytics.eval?.latest_score != null ? `latest: ${Math.round(analytics.eval.latest_score)}%` : ''}</p>
              </div>
            </div>
          </div>
        )}

        {/* Cost Tab */}
        {tab === 'cost' && cost && (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <Card value={`$${cost.total_cost?.toFixed(4)}`} label={t('overview.totalCost')} color="text-green-400" />
              <Card value={(cost.total_tokens || 0).toLocaleString()} label={t('overview.totalTokens')} color="text-blue-400" />
              <Card value={cost.total_calls || 0} label={t('overview.totalCalls')} color="text-purple-400" />
            </div>
            <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
              <h3 className="text-sm font-medium text-zinc-200 mb-3">{t('overview.byModel')}</h3>
              {cost.by_model && Object.keys(cost.by_model).length > 0 ? (
                <div className="space-y-2">
                  {Object.entries(cost.by_model).sort((a: any, b: any) => b[1].cost - a[1].cost).map(([model, stats]: [string, any]) => {
                    const maxCost = Math.max(...Object.values(cost.by_model).map((s: any) => s.cost))
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
              ) : <p className="text-xs text-zinc-500 text-center py-4">{t('overview.noData')}</p>}
            </div>
            {cost.daily_trend?.length > 1 && (
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
                <h3 className="text-sm font-medium text-zinc-200 mb-3">{t('overview.dailyCost')}</h3>
                <CostChart data={cost.daily_trend} />
              </div>
            )}
          </div>
        )}

        {/* Quality Tab */}
        {tab === 'quality' && (
          <div className="space-y-4">
            {phaseStatus && (
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-medium text-zinc-200">{t('overview.phaseStatus')}</h3>
                  <span className={`rounded px-2 py-0.5 text-xs font-medium ${phaseStatus.current_phase === 'full-auto' ? 'bg-green-500/20 text-green-400' : phaseStatus.current_phase === 'semi-auto' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-zinc-600/20 text-zinc-400'}`}>
                    {phaseStatus.current_phase}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-zinc-400 mb-1">{phaseStatus.test_case_count}/200 test cases</p>
                    <div className="w-full h-2 bg-zinc-700 rounded-full overflow-hidden">
                      <div className="h-full bg-blue-500 rounded-full" style={{ width: `${Math.min(100, (phaseStatus.test_case_count / 200) * 100)}%` }} />
                    </div>
                  </div>
                  <div>
                    <p className="text-xs text-zinc-400 mb-1">{phaseStatus.agreement_rate ?? 0}%/90% agreement</p>
                    <div className="w-full h-2 bg-zinc-700 rounded-full overflow-hidden">
                      <div className="h-full bg-blue-500 rounded-full" style={{ width: `${Math.min(100, phaseStatus.agreement_rate ?? 0)}%` }} />
                    </div>
                  </div>
                </div>
              </div>
            )}
            {trend.length > 1 && (
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
                <h3 className="text-sm font-medium text-zinc-200 mb-3">{t('overview.scoreTrend')}</h3>
                <ScoreTrendChart data={[...trend].reverse()} />
              </div>
            )}
          </div>
        )}

        {/* Tools Tab */}
        {tab === 'tools' && analytics && (
          <div className="space-y-4">
            <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-2xl font-mono text-zinc-200">{analytics.tools?.registered || 0}</span>
                <span className="text-xs text-zinc-400">{t('overview.registeredTools')}</span>
              </div>
              {analytics.tools?.tool_names?.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {analytics.tools.tool_names.map((name: string, i: number) => (
                    <span key={i} className="rounded bg-blue-500/10 px-2 py-0.5 text-[10px] text-blue-400 font-mono">{name}</span>
                  ))}
                </div>
              )}
            </div>
            {cost?.by_model && (
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
                <h3 className="text-sm font-medium text-zinc-200 mb-2">{t('overview.endpointUsage')}</h3>
                {analytics.by_endpoint && Object.keys(analytics.by_endpoint).length > 0 ? (
                  <div className="space-y-1">
                    {Object.entries(analytics.by_endpoint).map(([ep, stats]: [string, any]) => (
                      <div key={ep} className="flex items-center justify-between py-1">
                        <span className="text-xs text-zinc-300 font-mono">{ep}</span>
                        <div className="flex gap-3">
                          <span className="text-[10px] text-zinc-500">{stats.calls} calls</span>
                          <span className="text-[10px] text-green-400">${stats.cost?.toFixed(4)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : <p className="text-xs text-zinc-500">{t('overview.noData')}</p>}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function Card({ value, label, color }: { value: number | string; label: string; color: string }) {
  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4 text-center">
      <p className={`text-2xl font-mono font-bold ${color}`}>{value}</p>
      <p className="text-[10px] text-zinc-400 mt-1">{label}</p>
    </div>
  )
}

function CostChart({ data }: { data: Array<{ date: string; cost: number }> }) {
  const W = 600, H = 160, PX = 50, PY = 20
  const chartW = W - PX * 2, chartH = H - PY * 2
  const maxC = Math.max(...data.map(d => d.cost)) * 1.2 || 0.001
  const points = data.map((d, i) => ({
    x: PX + (i / Math.max(data.length - 1, 1)) * chartW,
    y: PY + chartH - (d.cost / maxC) * chartH,
    date: d.date.slice(5),
  }))
  const polyline = points.map(p => `${p.x},${p.y}`).join(' ')
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 180 }}>
      <polygon fill="#22c55e" fillOpacity={0.1} points={`${PX},${PY + chartH} ${polyline} ${W - PX},${PY + chartH}`} />
      <polyline fill="none" stroke="#22c55e" strokeWidth={2} points={polyline} />
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

function ScoreTrendChart({ data }: { data: Array<{ total_score: number; run_at: string }> }) {
  if (data.length < 2) return null
  const W = 600, H = 160, PX = 40, PY = 20
  const chartW = W - PX * 2, chartH = H - PY * 2
  const scores = data.map(d => d.total_score)
  const minS = Math.max(0, Math.min(...scores) - 10)
  const maxS = Math.min(100, Math.max(...scores) + 10)
  const range = maxS - minS || 1
  const points = data.map((d, i) => ({
    x: PX + (i / (data.length - 1)) * chartW,
    y: PY + chartH - ((d.total_score - minS) / range) * chartH,
    score: d.total_score,
    date: new Date(d.run_at).toLocaleDateString('zh-TW', { month: 'short', day: 'numeric' }),
  }))
  const polyline = points.map(p => `${p.x},${p.y}`).join(' ')
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 180 }}>
      {70 >= minS && 70 <= maxS && (
        <line x1={PX} y1={PY + chartH - ((70 - minS) / range) * chartH} x2={W - PX} y2={PY + chartH - ((70 - minS) / range) * chartH} stroke="#22c55e" strokeWidth={0.5} strokeDasharray="4 2" opacity={0.4} />
      )}
      <polyline fill="none" stroke="#3b82f6" strokeWidth={2} points={polyline} />
      {points.map((p, i) => (
        <g key={i}>
          <circle cx={p.x} cy={p.y} r={3.5} fill={p.score >= 70 ? '#22c55e' : p.score >= 40 ? '#eab308' : '#ef4444'} stroke="#18181b" strokeWidth={1.5} />
          {(data.length <= 10 || i % 2 === 0) && (
            <text x={p.x} y={H - 2} textAnchor="middle" fill="#71717a" fontSize={8}>{p.date}</text>
          )}
        </g>
      ))}
    </svg>
  )
}
