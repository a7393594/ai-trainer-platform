'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'
import type { EvalTrendPoint, CategoryAnalytics, PhaseStatus } from '@/types'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

type TabKey = 'cases' | 'runs' | 'analytics' | 'compare'

export default function EvalPage() {
  const [projectId, setProjectId] = useState('')
  const [tab, setTab] = useState<TabKey>('cases')
  const [cases, setCases] = useState<any[]>([])
  const [runs, setRuns] = useState<any[]>([])
  const [showAdd, setShowAdd] = useState(false)
  const [input, setInput] = useState('')
  const [expected, setExpected] = useState('')
  const [category, setCategory] = useState('')
  const [running, setRunning] = useState(false)
  const [expandedRun, setExpandedRun] = useState<string | null>(null)
  const [runDetails, setRunDetails] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [lastEvalResult, setLastEvalResult] = useState<any>(null)

  // Analytics state
  const [trend, setTrend] = useState<EvalTrendPoint[]>([])
  const [categories, setCategories] = useState<CategoryAnalytics[]>([])
  const [phaseStatus, setPhaseStatus] = useState<PhaseStatus | null>(null)
  const [analyticsLoading, setAnalyticsLoading] = useState(false)

  // Compare state
  const [promptVersions, setPromptVersions] = useState<any[]>([])
  const [selectedVersions, setSelectedVersions] = useState<string[]>([])
  const [compareData, setCompareData] = useState<any[]>([])
  const [comparing, setComparing] = useState(false)

  const { t } = useI18n()

  useEffect(() => {
    getDemoContext().then((ctx) => {
      setProjectId(ctx.project_id)
      loadCases(ctx.project_id)
      loadRuns(ctx.project_id)
    }).catch(() => setLoading(false))
  }, [])

  const loadCases = async (pid: string) => {
    const r = await fetch(`${AI}/api/v1/eval/test-cases/${pid}`)
    const d = await r.json()
    setCases(d.test_cases || [])
    setLoading(false)
  }
  const loadRuns = async (pid: string) => {
    const r = await fetch(`${AI}/api/v1/eval/runs/${pid}`)
    const d = await r.json()
    setRuns(d.runs || [])
  }

  const handleAddCase = async () => {
    if (!input.trim() || !expected.trim()) return
    await fetch(`${AI}/api/v1/eval/test-cases`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, input_text: input, expected_output: expected, category: category || null }),
    })
    setInput(''); setExpected(''); setCategory(''); setShowAdd(false)
    loadCases(projectId)
  }

  const handleDeleteCase = async (id: string) => {
    await fetch(`${AI}/api/v1/eval/test-cases/${id}`, { method: 'DELETE' })
    loadCases(projectId)
  }

  const handleRunEval = async () => {
    setRunning(true)
    try {
      const r = await fetch(`${AI}/api/v1/eval/run/${projectId}`, { method: 'POST' })
      const result = await r.json()
      setLastEvalResult(result)
      await loadRuns(projectId)
    } catch {}
    setRunning(false)
  }

  const handleExpandRun = async (runId: string) => {
    if (expandedRun === runId) { setExpandedRun(null); return }
    const r = await fetch(`${AI}/api/v1/eval/runs/${runId}/details`)
    setRunDetails(await r.json())
    setExpandedRun(runId)
  }

  // Analytics loaders
  const loadAnalytics = async (pid: string) => {
    setAnalyticsLoading(true)
    try {
      const [trendRes, phaseRes] = await Promise.all([
        fetch(`${AI}/api/v1/eval/analytics/trend/${pid}`),
        fetch(`${AI}/api/v1/eval/analytics/phase-status/${pid}`),
      ])
      const trendData = await trendRes.json()
      const phaseData = await phaseRes.json()
      const trendItems = trendData.trend || []
      setTrend(trendItems)
      setPhaseStatus(phaseData)

      // Load category analytics for latest run
      if (trendItems.length > 0) {
        const catRes = await fetch(`${AI}/api/v1/eval/analytics/categories/${pid}/${trendItems[0].id}`)
        const catData = await catRes.json()
        setCategories(catData.categories || [])
      }
    } catch {}
    setAnalyticsLoading(false)
  }

  const loadPromptVersions = async (pid: string) => {
    try {
      const r = await fetch(`${AI}/api/v1/prompts/${pid}`)
      const d = await r.json()
      setPromptVersions(d.versions || [])
    } catch {}
  }

  const handleCompare = async () => {
    if (selectedVersions.length < 2) return
    setComparing(true)
    try {
      const r = await fetch(`${AI}/api/v1/eval/analytics/compare-versions/${projectId}?version_ids=${selectedVersions.join(',')}`)
      const d = await r.json()
      setCompareData(d.versions || [])
    } catch {}
    setComparing(false)
  }

  const toggleVersion = (vid: string) => {
    setSelectedVersions((prev) =>
      prev.includes(vid) ? prev.filter((v) => v !== vid)
        : prev.length >= 3 ? prev : [...prev, vid]
    )
  }

  // Tab change handler
  const handleTabChange = (tb: TabKey) => {
    setTab(tb)
    if (tb === 'analytics' && trend.length === 0 && projectId) loadAnalytics(projectId)
    if (tb === 'compare' && promptVersions.length === 0 && projectId) loadPromptVersions(projectId)
  }

  // Score delta arrow for runs
  const getDelta = (idx: number) => {
    if (idx >= runs.length - 1) return null
    return Math.round(runs[idx].total_score - runs[idx + 1].total_score)
  }

  if (loading) return <div className="flex h-full items-center justify-center bg-zinc-900"><div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" /></div>

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-auto">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-lg font-medium text-zinc-200 mb-1">{t('eval.title')}</h1>
        <p className="text-xs text-zinc-500 mb-4">{t('eval.desc')}</p>

        {/* Tabs */}
        <div className="flex gap-1 mb-4">
          {([
            { key: 'cases' as const, label: t('eval.testCases') },
            { key: 'runs' as const, label: t('eval.runHistory') },
            { key: 'analytics' as const, label: t('eval.analytics') },
            { key: 'compare' as const, label: t('eval.compare') },
          ]).map(({ key, label }) => (
            <button key={key} onClick={() => handleTabChange(key)} className={`px-4 py-1.5 rounded text-xs ${tab === key ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200'}`}>
              {label}
            </button>
          ))}
        </div>

        {/* ====== Test Cases Tab ====== */}
        {tab === 'cases' && (
          <>
            <div className="flex justify-end mb-3">
              <button onClick={() => setShowAdd(true)} className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500">{t('eval.addCase')}</button>
            </div>
            {showAdd && (
              <div className="mb-4 rounded-lg border border-zinc-700 bg-zinc-800 p-4 space-y-3">
                <textarea value={input} onChange={(e) => setInput(e.target.value)} placeholder={t('eval.input')} rows={2} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
                <textarea value={expected} onChange={(e) => setExpected(e.target.value)} placeholder={t('eval.expected')} rows={3} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
                <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder={t('eval.category')} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
                <div className="flex gap-2 justify-end">
                  <button onClick={() => setShowAdd(false)} className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300">Cancel</button>
                  <button onClick={handleAddCase} disabled={!input.trim() || !expected.trim()} className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white disabled:opacity-50">{t('eval.save')}</button>
                </div>
              </div>
            )}
            <div className="space-y-2">
              {cases.map((tc) => (
                <div key={tc.id} className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-3">
                  <div className="flex justify-between items-start">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-zinc-400 mb-1">Input:</p>
                      <p className="text-sm text-zinc-200 truncate">{tc.input_text}</p>
                      <p className="text-xs text-zinc-400 mt-2 mb-1">Expected:</p>
                      <p className="text-xs text-zinc-300 truncate">{tc.expected_output}</p>
                    </div>
                    <div className="flex items-center gap-2 ml-3">
                      {tc.category && <span className="rounded bg-purple-500/20 px-1.5 py-0.5 text-[10px] text-purple-400">{tc.category}</span>}
                      <button onClick={() => handleDeleteCase(tc.id)} className="text-xs text-red-400 hover:text-red-300">{t('eval.del')}</button>
                    </div>
                  </div>
                </div>
              ))}
              {cases.length === 0 && <p className="text-sm text-zinc-500 text-center py-12">{t('eval.emptyCase')}</p>}
            </div>
          </>
        )}

        {/* ====== Runs Tab (Enhanced) ====== */}
        {tab === 'runs' && (
          <>
            <div className="flex justify-end mb-3">
              <button onClick={handleRunEval} disabled={running || cases.length === 0} className="rounded bg-green-600 px-4 py-1.5 text-xs text-white hover:bg-green-500 disabled:opacity-50">
                {running ? t('eval.running') : t('eval.runEval')}
              </button>
            </div>

            {/* Regression warning after running */}
            {lastEvalResult?.regression_detected && (
              <div className="mb-3 rounded-lg border border-red-500/50 bg-red-500/10 px-4 py-3 flex items-center gap-3">
                <span className="text-red-400 text-lg">!</span>
                <div>
                  <p className="text-sm text-red-300 font-medium">{t('eval.regression')}</p>
                  <p className="text-xs text-red-400">{t('eval.regressionDetected').replace('{delta}', String(Math.abs(lastEvalResult.overall_delta || 0)))}{lastEvalResult.regressions?.length > 0 && ` | ${lastEvalResult.regressions.length} ${t('eval.casesRegressed')}`}</p>
                </div>
              </div>
            )}

            <div className="space-y-2">
              {runs.map((run, idx) => {
                const delta = getDelta(idx)
                return (
                  <div key={run.id} className="rounded-lg border border-zinc-700 bg-zinc-800/50">
                    <button onClick={() => handleExpandRun(run.id)} className="w-full text-left px-4 py-3 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-zinc-400">{new Date(run.run_at).toLocaleString('zh-TW')}</span>
                        <span className="text-sm font-mono text-zinc-200">{Math.round(run.total_score)}%</span>
                        {delta !== null && delta !== 0 && (
                          <span className={`text-xs font-mono ${delta > 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {delta > 0 ? '+' : ''}{delta}
                          </span>
                        )}
                        <div className="w-24 h-1.5 bg-zinc-700 rounded-full overflow-hidden">
                          <div className={`h-full rounded-full ${run.total_score >= 70 ? 'bg-green-500' : run.total_score >= 40 ? 'bg-yellow-500' : 'bg-red-500'}`} style={{ width: `${run.total_score}%` }} />
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-green-400">{run.passed_count} {t('eval.passed')}</span>
                        <span className="text-xs text-red-400">{run.failed_count} {t('eval.failed')}</span>
                        <span className="text-zinc-600">{expandedRun === run.id ? '[-]' : '[+]'}</span>
                      </div>
                    </button>
                    {expandedRun === run.id && runDetails && (
                      <div className="border-t border-zinc-700 px-4 py-3 space-y-2">
                        {runDetails.results?.map((r: any, i: number) => (
                          <div key={i} className={`rounded p-2 text-xs border-l-2 ${r.passed ? 'border-green-500 bg-green-500/5' : 'border-red-500 bg-red-500/5'}`}>
                            <p className="text-zinc-300"><strong>{t('eval.score')}:</strong> {r.score} | {r.passed ? 'PASS' : 'FAIL'}</p>
                            <p className="text-zinc-400 mt-1 truncate">A: {r.actual_output?.slice(0, 100)}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
              {runs.length === 0 && <p className="text-sm text-zinc-500 text-center py-12">{t('eval.emptyRun')}</p>}
            </div>
          </>
        )}

        {/* ====== Analytics Tab ====== */}
        {tab === 'analytics' && (
          <div className="space-y-6">
            {analyticsLoading ? (
              <div className="flex justify-center py-12"><div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" /></div>
            ) : (
              <>
                {/* Phase Status Banner */}
                {phaseStatus && (
                  <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-medium text-zinc-200">{t('eval.phaseStatus')}</h3>
                      <span className={`rounded px-2 py-0.5 text-xs font-medium ${
                        phaseStatus.current_phase === 'full-auto' ? 'bg-green-500/20 text-green-400' :
                        phaseStatus.current_phase === 'semi-auto' ? 'bg-yellow-500/20 text-yellow-400' :
                        'bg-zinc-600/20 text-zinc-400'
                      }`}>
                        {phaseStatus.current_phase === 'full-auto' ? t('eval.phaseFullAuto') :
                         phaseStatus.current_phase === 'semi-auto' ? t('eval.phaseSemiAuto') :
                         t('eval.phaseManual')}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-xs text-zinc-400 mb-1">{t('eval.testCaseTarget').replace('{count}', String(phaseStatus.test_case_count))}</p>
                        <div className="w-full h-2 bg-zinc-700 rounded-full overflow-hidden">
                          <div className={`h-full rounded-full ${phaseStatus.test_case_count >= 200 ? 'bg-green-500' : phaseStatus.test_case_count >= 100 ? 'bg-yellow-500' : 'bg-blue-500'}`} style={{ width: `${Math.min(100, (phaseStatus.test_case_count / 200) * 100)}%` }} />
                        </div>
                      </div>
                      <div>
                        <p className="text-xs text-zinc-400 mb-1">{t('eval.agreementTarget').replace('{rate}', String(phaseStatus.agreement_rate ?? 0))}</p>
                        <div className="w-full h-2 bg-zinc-700 rounded-full overflow-hidden">
                          <div className={`h-full rounded-full ${(phaseStatus.agreement_rate ?? 0) >= 90 ? 'bg-green-500' : (phaseStatus.agreement_rate ?? 0) >= 70 ? 'bg-yellow-500' : 'bg-blue-500'}`} style={{ width: `${Math.min(100, phaseStatus.agreement_rate ?? 0)}%` }} />
                        </div>
                      </div>
                    </div>
                    <div className="flex gap-4 mt-3 text-xs text-zinc-500">
                      <span>{phaseStatus.run_count} runs</span>
                      {phaseStatus.latest_score !== null && <span>Latest: {Math.round(phaseStatus.latest_score)}%</span>}
                    </div>
                  </div>
                )}

                {/* Score Trend Chart (SVG) */}
                <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
                  <h3 className="text-sm font-medium text-zinc-200 mb-3">{t('eval.trend')}</h3>
                  {trend.length > 1 ? (
                    <ScoreTrendChart data={[...trend].reverse()} />
                  ) : (
                    <p className="text-xs text-zinc-500 text-center py-8">{t('eval.emptyRun')}</p>
                  )}
                </div>

                {/* Category Breakdown */}
                <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
                  <h3 className="text-sm font-medium text-zinc-200 mb-3">{t('eval.categoryBreakdown')}</h3>
                  {categories.length > 0 ? (
                    <div className="space-y-2">
                      {categories.map((cat) => (
                        <div key={cat.category} className="flex items-center gap-3">
                          <span className="text-xs text-zinc-300 w-28 truncate">{cat.category}</span>
                          <div className="flex-1 h-2 bg-zinc-700 rounded-full overflow-hidden">
                            <div className={`h-full rounded-full ${cat.avg_score >= 70 ? 'bg-green-500' : cat.avg_score >= 40 ? 'bg-yellow-500' : 'bg-red-500'}`} style={{ width: `${cat.avg_score}%` }} />
                          </div>
                          <span className="text-xs font-mono text-zinc-300 w-10 text-right">{cat.avg_score}%</span>
                          <span className="text-[10px] text-green-400 w-8">{cat.passed_count}P</span>
                          <span className="text-[10px] text-red-400 w-8">{cat.failed_count}F</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-zinc-500 text-center py-4">{t('eval.emptyRun')}</p>
                  )}
                </div>
              </>
            )}
          </div>
        )}

        {/* ====== Compare Tab ====== */}
        {tab === 'compare' && (
          <div className="space-y-4">
            <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
              <h3 className="text-sm font-medium text-zinc-200 mb-3">{t('eval.selectVersions')}</h3>
              <div className="space-y-1 max-h-48 overflow-auto">
                {promptVersions.map((v: any) => (
                  <label key={v.id} className="flex items-center gap-2 py-1 px-2 rounded hover:bg-zinc-700/50 cursor-pointer">
                    <input type="checkbox" checked={selectedVersions.includes(v.id)} onChange={() => toggleVersion(v.id)}
                      className="rounded border-zinc-600 bg-zinc-700 text-blue-500" />
                    <span className="text-xs text-zinc-300 flex-1">v{v.version_number || '?'} — {v.content?.slice(0, 60)}...</span>
                    {v.is_active && <span className="rounded bg-green-500/20 px-1.5 py-0.5 text-[10px] text-green-400">active</span>}
                    {v.eval_score != null && <span className="text-[10px] text-zinc-500">{Math.round(v.eval_score)}%</span>}
                  </label>
                ))}
                {promptVersions.length === 0 && <p className="text-xs text-zinc-500 py-4 text-center">No prompt versions</p>}
              </div>
              <div className="flex justify-end mt-3">
                <button onClick={handleCompare} disabled={selectedVersions.length < 2 || comparing} className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white disabled:opacity-50 hover:bg-blue-500">
                  {comparing ? '...' : t('eval.compareBtn')}
                </button>
              </div>
            </div>

            {/* Comparison results */}
            {compareData.length > 0 && (
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 overflow-hidden">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-zinc-700 bg-zinc-800/80">
                      <th className="text-left px-3 py-2 text-zinc-400"></th>
                      {compareData.map((v, i) => (
                        <th key={i} className="text-center px-3 py-2 text-zinc-300">v{v.prompt_version_id?.slice(0, 8)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-b border-zinc-700/50">
                      <td className="px-3 py-2 text-zinc-400">{t('eval.score')}</td>
                      {compareData.map((v, i) => {
                        const best = Math.max(...compareData.filter((d) => d.total_score != null).map((d) => d.total_score))
                        return (
                          <td key={i} className={`text-center px-3 py-2 font-mono ${v.total_score === best ? 'text-green-400' : 'text-zinc-300'}`}>
                            {v.total_score != null ? `${Math.round(v.total_score)}%` : t('eval.noEvalData')}
                          </td>
                        )
                      })}
                    </tr>
                    <tr className="border-b border-zinc-700/50">
                      <td className="px-3 py-2 text-zinc-400">{t('eval.passed')}</td>
                      {compareData.map((v, i) => (
                        <td key={i} className="text-center px-3 py-2 text-green-400">{v.passed_count ?? '-'}</td>
                      ))}
                    </tr>
                    <tr className="border-b border-zinc-700/50">
                      <td className="px-3 py-2 text-zinc-400">{t('eval.failed')}</td>
                      {compareData.map((v, i) => (
                        <td key={i} className="text-center px-3 py-2 text-red-400">{v.failed_count ?? '-'}</td>
                      ))}
                    </tr>
                    <tr>
                      <td className="px-3 py-2 text-zinc-400">Run date</td>
                      {compareData.map((v, i) => (
                        <td key={i} className="text-center px-3 py-2 text-zinc-500">{v.run_at ? new Date(v.run_at).toLocaleDateString('zh-TW') : '-'}</td>
                      ))}
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/* ====== SVG Score Trend Chart ====== */
function ScoreTrendChart({ data }: { data: EvalTrendPoint[] }) {
  if (data.length < 2) return null

  const W = 600, H = 180, PX = 40, PY = 20
  const chartW = W - PX * 2
  const chartH = H - PY * 2

  const scores = data.map((d) => d.total_score)
  const minS = Math.max(0, Math.min(...scores) - 10)
  const maxS = Math.min(100, Math.max(...scores) + 10)
  const range = maxS - minS || 1

  const points = data.map((d, i) => ({
    x: PX + (i / (data.length - 1)) * chartW,
    y: PY + chartH - ((d.total_score - minS) / range) * chartH,
    score: d.total_score,
    date: new Date(d.run_at).toLocaleDateString('zh-TW', { month: 'short', day: 'numeric' }),
  }))

  const polyline = points.map((p) => `${p.x},${p.y}`).join(' ')

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 200 }}>
      {/* Grid lines */}
      {[0, 25, 50, 75, 100].filter((v) => v >= minS && v <= maxS).map((v) => {
        const y = PY + chartH - ((v - minS) / range) * chartH
        return (
          <g key={v}>
            <line x1={PX} y1={y} x2={W - PX} y2={y} stroke="#3f3f46" strokeWidth={0.5} />
            <text x={PX - 4} y={y + 3} textAnchor="end" fill="#71717a" fontSize={9}>{v}</text>
          </g>
        )
      })}
      {/* Pass threshold line */}
      {70 >= minS && 70 <= maxS && (
        <line x1={PX} y1={PY + chartH - ((70 - minS) / range) * chartH} x2={W - PX} y2={PY + chartH - ((70 - minS) / range) * chartH} stroke="#22c55e" strokeWidth={0.5} strokeDasharray="4 2" opacity={0.4} />
      )}
      {/* Line */}
      <polyline fill="none" stroke="#3b82f6" strokeWidth={2} points={polyline} />
      {/* Dots */}
      {points.map((p, i) => (
        <g key={i}>
          <circle cx={p.x} cy={p.y} r={3.5} fill={p.score >= 70 ? '#22c55e' : p.score >= 40 ? '#eab308' : '#ef4444'} stroke="#18181b" strokeWidth={1.5} />
          {/* Date labels (every other or all if few) */}
          {(data.length <= 10 || i % 2 === 0) && (
            <text x={p.x} y={H - 2} textAnchor="middle" fill="#71717a" fontSize={8}>{p.date}</text>
          )}
        </g>
      ))}
    </svg>
  )
}
