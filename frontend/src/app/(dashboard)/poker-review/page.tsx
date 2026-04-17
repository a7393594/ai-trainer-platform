'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

const severityColors: Record<string, string> = {
  critical: 'text-red-400 bg-red-950/50 border-red-500/40',
  major: 'text-amber-400 bg-amber-950/50 border-amber-500/40',
  moderate: 'text-yellow-400 bg-yellow-950/50 border-yellow-500/40',
  minor: 'text-zinc-400 bg-zinc-800 border-zinc-600',
  none: 'text-emerald-400 bg-emerald-950/50 border-emerald-500/40',
}

export default function PokerReviewPage() {
  const [userId, setUserId] = useState('')
  const [projectId, setProjectId] = useState('')
  const [reports, setReports] = useState<any[]>([])
  const [selectedReport, setSelectedReport] = useState<any>(null)
  const [analyses, setAnalyses] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [reviewing, setReviewing] = useState(false)
  const { t } = useI18n()

  useEffect(() => {
    getDemoContext().then((ctx) => {
      setUserId(ctx.user_id)
      setProjectId(ctx.project_id)
      loadReports(ctx.user_id, ctx.project_id)
    }).catch(() => setLoading(false))
  }, [])

  const loadReports = async (uid: string, pid: string) => {
    try {
      const r = await fetch(`${AI}/api/v1/poker/review/list?user_id=${uid}&project_id=${pid}`)
      const d = await r.json()
      setReports(d.reports || [])
    } catch {}
    setLoading(false)
  }

  const startReview = async () => {
    setReviewing(true)
    try {
      const r = await fetch(`${AI}/api/v1/poker/review/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, project_id: projectId }),
      })
      const d = await r.json()
      if (d.report_id) {
        loadReports(userId, projectId)
        viewReport(d.report_id)
      }
    } catch {}
    setReviewing(false)
  }

  const viewReport = async (reportId: string) => {
    try {
      const r = await fetch(`${AI}/api/v1/poker/review/${reportId}`)
      const d = await r.json()
      setSelectedReport(d.report)
      setAnalyses(d.analyses || [])
    } catch {}
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-zinc-900">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
      </div>
    )
  }

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-y-auto">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-lg font-medium text-zinc-200">深度複盤</h1>
            <p className="text-xs text-zinc-500">AI 分析你的手牌決策品質，找出弱點</p>
          </div>
          <button
            onClick={startReview}
            disabled={reviewing}
            className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {reviewing ? '分析中...' : '開始複盤'}
          </button>
        </div>

        {/* Report Detail */}
        {selectedReport && (
          <div className="mb-8 space-y-4">
            {/* Summary Card */}
            <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-5">
              <h2 className="text-sm font-medium text-zinc-200 mb-2">複盤摘要</h2>
              <p className="text-xs text-zinc-400 mb-3">{selectedReport.summary || selectedReport.report_json?.executive_summary}</p>
              <div className="grid grid-cols-4 gap-3 text-center">
                <div>
                  <div className="text-lg font-bold text-zinc-200">{selectedReport.hand_count}</div>
                  <div className="text-[10px] text-zinc-500">總手數</div>
                </div>
                <div>
                  <div className="text-lg font-bold text-blue-400">{selectedReport.analyzed_count}</div>
                  <div className="text-[10px] text-zinc-500">深度分析</div>
                </div>
                <div>
                  <div className="text-lg font-bold text-amber-400">
                    {selectedReport.overall_ev_loss_mbb?.toFixed(1) || '0'} mbb
                  </div>
                  <div className="text-[10px] text-zinc-500">平均 EV 損失</div>
                </div>
                <div>
                  <div className={`text-lg font-bold ${selectedReport.status === 'completed' ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {selectedReport.status === 'completed' ? '完成' : '處理中'}
                  </div>
                  <div className="text-[10px] text-zinc-500">狀態</div>
                </div>
              </div>
            </div>

            {/* Weaknesses */}
            {selectedReport.top_weaknesses?.length > 0 && (
              <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-5">
                <h2 className="text-sm font-medium text-zinc-200 mb-3">主要弱點</h2>
                <div className="space-y-2">
                  {selectedReport.top_weaknesses.slice(0, 5).map((w: any, i: number) => (
                    <div key={i} className="flex items-center justify-between rounded border border-zinc-700 px-3 py-2">
                      <span className="text-xs text-zinc-300">{w.concept}</span>
                      <div className="flex items-center gap-3">
                        <span className="text-[10px] text-zinc-500">{w.frequency}x</span>
                        <span className="text-xs font-mono text-red-400">-{w.total_ev_loss?.toFixed(1)} mbb</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Hand Analyses */}
            {analyses.length > 0 && (
              <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 overflow-hidden">
                <div className="px-4 py-3 border-b border-zinc-700">
                  <h2 className="text-sm font-medium text-zinc-200">手牌分析（依 EV 損失排序）</h2>
                </div>
                <div className="divide-y divide-zinc-800/50">
                  {analyses.filter((a: any) => a.filter_pass).map((a: any, i: number) => (
                    <div key={i} className="px-4 py-3 hover:bg-zinc-800/30">
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-2">
                          <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${severityColors[a.mistake_severity] || ''}`}>
                            {a.mistake_severity || 'none'}
                          </span>
                          <span className="text-xs font-mono text-zinc-400">
                            -{a.ev_loss_mbb?.toFixed(1) || '0'} mbb
                          </span>
                        </div>
                        <span className="text-[10px] text-zinc-500">
                          {a.concepts_tagged?.join(', ') || ''}
                        </span>
                      </div>
                      {a.analysis_json?.key_mistake && (
                        <p className="text-xs text-zinc-400">{a.analysis_json.key_mistake}</p>
                      )}
                      {a.analysis_json?.analysis && (
                        <p className="text-[10px] text-zinc-500 mt-0.5">{a.analysis_json.analysis}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <button onClick={() => setSelectedReport(null)} className="text-xs text-zinc-500 hover:text-zinc-300">
              ← 返回報告列表
            </button>
          </div>
        )}

        {/* Report List */}
        {!selectedReport && (
          <div className="space-y-2">
            <h2 className="text-sm font-medium text-zinc-300 mb-3">複盤報告</h2>
            {reports.map((r) => (
              <button
                key={r.id}
                onClick={() => viewReport(r.id)}
                className="w-full text-left rounded-lg border border-zinc-700 bg-zinc-800/50 px-4 py-3 hover:border-zinc-600 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-zinc-200">{r.hand_count} 手 / {r.analyzed_count} 深度分析</p>
                    <p className="text-[10px] text-zinc-500 mt-0.5">
                      {r.summary?.slice(0, 80) || '...'} | {new Date(r.created_at).toLocaleString()}
                    </p>
                  </div>
                  <div className="text-right">
                    <div className="text-xs font-mono text-amber-400">
                      {r.overall_ev_loss_mbb?.toFixed(1) || '0'} mbb
                    </div>
                    <div className={`text-[10px] ${r.status === 'completed' ? 'text-emerald-400' : 'text-amber-400'}`}>
                      {r.status}
                    </div>
                  </div>
                </div>
              </button>
            ))}
            {reports.length === 0 && (
              <div className="text-center py-12">
                <p className="text-sm text-zinc-500 mb-2">尚無複盤報告</p>
                <p className="text-xs text-zinc-600">先上傳手牌歷史，再點擊「開始複盤」</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
