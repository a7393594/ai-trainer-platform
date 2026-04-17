'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

type Tab = 'sessions' | 'costs' | 'uploads'

export default function AuditPage() {
  const { t } = useI18n()
  const [userId, setUserId] = useState('')
  const [projectId, setProjectId] = useState('')
  const [tab, setTab] = useState<Tab>('sessions')
  const [sessions, setSessions] = useState<any[]>([])
  const [costs, setCosts] = useState<any>(null)
  const [uploads, setUploads] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedSession, setExpandedSession] = useState<string | null>(null)

  useEffect(() => {
    getDemoContext().then(async (ctx) => {
      setUserId(ctx.user_id)
      setProjectId(ctx.project_id)
      const [sessRes, costRes, upRes] = await Promise.all([
        fetch(`${AI}/api/v1/poker/session-reports?user_id=${ctx.user_id}&project_id=${ctx.project_id}`).then(r => r.json()),
        fetch(`${AI}/api/v1/poker/admin/costs?project_id=${ctx.project_id}`).then(r => r.json()),
        fetch(`${AI}/api/v1/poker/uploads?user_id=${ctx.user_id}&project_id=${ctx.project_id}`).then(r => r.json()),
      ])
      setSessions(sessRes.reports || [])
      setCosts(costRes)
      setUploads(upRes.batches || [])
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  if (loading) {
    return <div className="flex h-full items-center justify-center bg-zinc-900"><div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" /></div>
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: 'sessions', label: '教練紀錄' },
    { key: 'costs', label: '成本明細' },
    { key: 'uploads', label: '上傳歷史' },
  ]

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-y-auto">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-lg font-medium text-zinc-200 mb-1">{t('nav.poker.audit')}</h1>
        <p className="text-xs text-zinc-500 mb-6">追蹤所有教練互動、成本支出、資料匯入紀錄</p>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 border-b border-zinc-800 pb-1">
          {tabs.map(tb => (
            <button
              key={tb.key}
              onClick={() => setTab(tb.key)}
              className={`px-4 py-2 text-xs font-medium rounded-t transition-colors ${tab === tb.key ? 'text-blue-400 bg-blue-600/10 border-b-2 border-blue-500' : 'text-zinc-400 hover:text-zinc-200'}`}
            >
              {tb.label}
            </button>
          ))}
        </div>

        {/* Sessions Tab */}
        {tab === 'sessions' && (
          <div className="space-y-2">
            {sessions.length === 0 && <p className="text-sm text-zinc-500 text-center py-12">尚無教練 session 紀錄</p>}
            {sessions.map((s) => {
              const report = s.report_json || {}
              const isExpanded = expandedSession === s.id
              return (
                <div key={s.id} className="rounded-lg border border-zinc-700 bg-zinc-800/50">
                  <button
                    onClick={() => setExpandedSession(isExpanded ? null : s.id)}
                    className="w-full text-left px-4 py-3 flex items-center justify-between hover:bg-zinc-800/80 transition-colors"
                  >
                    <div>
                      <p className="text-sm text-zinc-200">
                        {report.duration_mins || 0} 分鐘 | {report.messages_count || 0} 訊息
                      </p>
                      <p className="text-[10px] text-zinc-500">{new Date(s.created_at).toLocaleString()}</p>
                    </div>
                    <div className="flex items-center gap-3">
                      {report.concepts_covered?.length > 0 && (
                        <div className="flex gap-1">
                          {report.concepts_covered.slice(0, 3).map((c: string, i: number) => (
                            <span key={i} className="rounded bg-violet-900/40 px-1.5 py-0.5 text-[10px] text-violet-300">{c}</span>
                          ))}
                        </div>
                      )}
                      <span className="text-xs text-blue-400">+{report.xp_earned || 0} XP</span>
                      <span className="text-zinc-500">{isExpanded ? '▲' : '▼'}</span>
                    </div>
                  </button>
                  {isExpanded && (
                    <div className="border-t border-zinc-700 px-4 py-3 bg-zinc-900/50">
                      <div className="grid grid-cols-4 gap-3 text-center text-xs">
                        <div><div className="font-bold text-zinc-200">{report.user_messages || 0}</div><div className="text-[10px] text-zinc-500">用戶訊息</div></div>
                        <div><div className="font-bold text-zinc-200">{report.assistant_messages || 0}</div><div className="text-[10px] text-zinc-500">AI 回覆</div></div>
                        <div><div className="font-bold text-blue-400">{report.xp_earned || 0}</div><div className="text-[10px] text-zinc-500">XP 獲得</div></div>
                        <div><div className="font-bold text-zinc-200">{report.concepts_covered?.length || 0}</div><div className="text-[10px] text-zinc-500">概念觸及</div></div>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {/* Costs Tab */}
        {tab === 'costs' && costs && (
          <div className="space-y-4">
            {/* Summary Cards */}
            <div className="grid grid-cols-4 gap-3">
              <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-3 text-center">
                <div className="text-lg font-bold text-amber-400">${costs.total_cost_usd?.toFixed(2)}</div>
                <div className="text-[10px] text-zinc-500">總成本</div>
              </div>
              <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-3 text-center">
                <div className="text-lg font-bold text-zinc-200">{costs.total_calls?.toLocaleString()}</div>
                <div className="text-[10px] text-zinc-500">API 呼叫</div>
              </div>
              <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-3 text-center">
                <div className="text-lg font-bold text-zinc-200">{((costs.total_input_tokens || 0) / 1000).toFixed(0)}K</div>
                <div className="text-[10px] text-zinc-500">Input Tokens</div>
              </div>
              <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-3 text-center">
                <div className="text-lg font-bold text-zinc-200">${costs.avg_cost_per_call?.toFixed(4)}</div>
                <div className="text-[10px] text-zinc-500">每次平均</div>
              </div>
            </div>

            {/* By Model */}
            <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
              <h3 className="text-sm font-medium text-zinc-300 mb-3">模型成本分佈</h3>
              <div className="space-y-2">
                {Object.entries(costs.by_model || {}).map(([model, data]: [string, any]) => (
                  <div key={model} className="flex items-center justify-between rounded border border-zinc-700 px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-zinc-200 truncate max-w-[200px]">{model}</span>
                      <span className="text-[10px] text-zinc-500">{data.calls} 次</span>
                    </div>
                    <span className="text-xs font-mono text-amber-400">${data.cost?.toFixed(4)}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Daily Cost Chart */}
            {costs.daily_cost && Object.keys(costs.daily_cost).length > 0 && (
              <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
                <h3 className="text-sm font-medium text-zinc-300 mb-3">每日成本</h3>
                <div className="flex items-end gap-1 h-24">
                  {(() => {
                    const entries = Object.entries(costs.daily_cost).slice(-14)
                    const max = Math.max(...entries.map(([, v]) => v as number), 0.01)
                    return entries.map(([day, cost]) => (
                      <div key={day} className="flex-1 flex flex-col items-center gap-0.5">
                        <div className="w-full bg-blue-600/60 rounded-t" style={{ height: `${((cost as number) / max) * 80}px` }} title={`${day}: $${(cost as number).toFixed(4)}`} />
                        <span className="text-[8px] text-zinc-600 -rotate-45">{(day as string).slice(5)}</span>
                      </div>
                    ))
                  })()}
                </div>
              </div>
            )}
          </div>
        )}
        {tab === 'costs' && !costs && <p className="text-sm text-zinc-500 text-center py-12">無成本資料</p>}

        {/* Uploads Tab */}
        {tab === 'uploads' && (
          <div className="space-y-2">
            {uploads.length === 0 && <p className="text-sm text-zinc-500 text-center py-12">尚無上傳紀錄</p>}
            {uploads.map((b) => (
              <div key={b.id} className="rounded-lg border border-zinc-700 bg-zinc-800/50 px-4 py-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-zinc-200">{b.filename}</p>
                    <p className="text-[10px] text-zinc-500">{b.source} | {new Date(b.created_at).toLocaleString()}</p>
                  </div>
                  <div className="flex items-center gap-3 text-xs">
                    <span className="text-zinc-300">{b.parsed_hands} 手</span>
                    {b.failed_hands > 0 && <span className="text-red-400">{b.failed_hands} 失敗</span>}
                    <span className={`rounded px-2 py-0.5 text-[10px] ${b.status === 'completed' ? 'bg-emerald-500/20 text-emerald-400' : b.status === 'error' ? 'bg-red-500/20 text-red-400' : 'bg-amber-500/20 text-amber-400'}`}>{b.status}</span>
                  </div>
                </div>
                {b.error_log?.length > 0 && (
                  <div className="mt-2 text-[10px] text-red-400 bg-red-950/20 rounded p-2">
                    {b.error_log.map((e: any, i: number) => <div key={i}>{e.error || JSON.stringify(e)}</div>)}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
