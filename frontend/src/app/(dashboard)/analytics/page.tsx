'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

export default function AnalyticsPage() {
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
      const r = await fetch(`${AI}/api/v1/analytics/${pid}?days=${d}`)
      setData(await r.json())
    } catch {}
    setLoading(false)
  }

  const changePeriod = (d: number) => {
    setDays(d)
    if (projectId) loadData(projectId, d)
  }

  if (loading) return <div className="flex h-full items-center justify-center bg-zinc-900"><div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" /></div>

  const o = data?.overview || {}
  const fb = data?.feedback || {}

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-auto">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-lg font-medium text-zinc-200">{t('analytics.title')}</h1>
            <p className="text-xs text-zinc-500">{t('analytics.desc')}</p>
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
            {/* Overview Cards */}
            <div className="grid grid-cols-4 gap-3">
              <StatCard value={o.total_sessions || 0} label={t('analytics.sessions')} color="text-blue-400" />
              <StatCard value={o.total_messages || 0} label={t('analytics.messages')} color="text-green-400" />
              <StatCard value={o.user_messages || 0} label={t('analytics.userMsgs')} color="text-purple-400" />
              <StatCard value={o.avg_messages_per_session || 0} label={t('analytics.avgPerSession')} color="text-yellow-400" />
            </div>

            {/* Feedback Distribution */}
            <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
              <h3 className="text-sm font-medium text-zinc-200 mb-3">{t('analytics.feedbackDist')}</h3>
              <div className="grid grid-cols-4 gap-3">
                <div className="rounded bg-green-500/10 p-3 text-center">
                  <p className="text-xl font-mono font-bold text-green-400">{fb.correct || 0}</p>
                  <p className="text-[10px] text-zinc-400">Correct</p>
                </div>
                <div className="rounded bg-yellow-500/10 p-3 text-center">
                  <p className="text-xl font-mono font-bold text-yellow-400">{fb.partial || 0}</p>
                  <p className="text-[10px] text-zinc-400">Partial</p>
                </div>
                <div className="rounded bg-red-500/10 p-3 text-center">
                  <p className="text-xl font-mono font-bold text-red-400">{fb.wrong || 0}</p>
                  <p className="text-[10px] text-zinc-400">Wrong</p>
                </div>
                <div className="rounded bg-zinc-700/50 p-3 text-center">
                  <p className="text-xl font-mono font-bold text-zinc-300">{fb.total || 0}</p>
                  <p className="text-[10px] text-zinc-400">Total</p>
                </div>
              </div>
              {/* Feedback rate bar */}
              {(fb.total || 0) > 0 && (
                <div className="mt-3 flex h-3 rounded-full overflow-hidden bg-zinc-700">
                  <div className="bg-green-500" style={{ width: `${(fb.correct / fb.total) * 100}%` }} />
                  <div className="bg-yellow-500" style={{ width: `${(fb.partial / fb.total) * 100}%` }} />
                  <div className="bg-red-500" style={{ width: `${(fb.wrong / fb.total) * 100}%` }} />
                </div>
              )}
            </div>

            {/* Project Health */}
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
                <h3 className="text-xs text-zinc-400 mb-2">{t('analytics.prompts')}</h3>
                <p className="text-2xl font-mono text-zinc-200">{data.prompts?.total_versions || 0}</p>
                <p className="text-[10px] text-zinc-500">versions {data.prompts?.active_version ? `(v${data.prompts.active_version} active)` : ''}</p>
              </div>
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
                <h3 className="text-xs text-zinc-400 mb-2">{t('analytics.knowledge')}</h3>
                <p className="text-2xl font-mono text-zinc-200">{data.knowledge?.total_docs || 0}</p>
                <p className="text-[10px] text-zinc-500">documents</p>
              </div>
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
                <h3 className="text-xs text-zinc-400 mb-2">{t('analytics.eval')}</h3>
                <p className="text-2xl font-mono text-zinc-200">{data.eval?.total_runs || 0}</p>
                <p className="text-[10px] text-zinc-500">{data.eval?.latest_score != null ? `latest: ${Math.round(data.eval.latest_score)}%` : 'no runs'}</p>
              </div>
            </div>

            {/* Tools */}
            <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
              <h3 className="text-sm font-medium text-zinc-200 mb-2">{t('analytics.tools')}</h3>
              <div className="flex items-center gap-2">
                <span className="text-2xl font-mono text-zinc-200">{data.tools?.registered || 0}</span>
                <span className="text-xs text-zinc-400">{t('analytics.registeredTools')}</span>
              </div>
              {data.tools?.tool_names?.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {data.tools.tool_names.map((name: string, i: number) => (
                    <span key={i} className="rounded bg-blue-500/10 px-2 py-0.5 text-[10px] text-blue-400 font-mono">{name}</span>
                  ))}
                </div>
              )}
            </div>

            {/* Daily Activity */}
            {data.daily_activity?.length > 1 && (
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
                <h3 className="text-sm font-medium text-zinc-200 mb-3">{t('analytics.dailyActivity')}</h3>
                <ActivityChart data={data.daily_activity} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function StatCard({ value, label, color }: { value: number | string; label: string; color: string }) {
  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4 text-center">
      <p className={`text-2xl font-mono font-bold ${color}`}>{value}</p>
      <p className="text-[10px] text-zinc-400 mt-1">{label}</p>
    </div>
  )
}

function ActivityChart({ data }: { data: Array<{ date: string; sessions: number }> }) {
  const maxS = Math.max(...data.map(d => d.sessions), 1)

  return (
    <div className="flex items-end gap-1" style={{ height: 80 }}>
      {data.map((d, i) => (
        <div key={i} className="flex-1 flex flex-col items-center gap-1">
          <div className="w-full rounded-t bg-blue-500/60" style={{ height: `${(d.sessions / maxS) * 60}px`, minHeight: d.sessions > 0 ? 4 : 0 }} />
          {(data.length <= 15 || i % Math.ceil(data.length / 10) === 0) && (
            <span className="text-[7px] text-zinc-500">{d.date.slice(5)}</span>
          )}
        </div>
      ))}
    </div>
  )
}
