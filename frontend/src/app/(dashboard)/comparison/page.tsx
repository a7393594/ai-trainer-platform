'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

const AVAILABLE_MODELS = [
  { id: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4', cost: '$3/$15' },
  { id: 'claude-opus-4-20250514', label: 'Claude Opus 4', cost: '$15/$75' },
  { id: 'claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5', cost: '$0.8/$4' },
  { id: 'gpt-4o', label: 'GPT-4o', cost: '$2.5/$10' },
  { id: 'gpt-4o-mini', label: 'GPT-4o Mini', cost: '$0.15/$0.6' },
  { id: 'gemini/gemini-2.0-flash', label: 'Gemini 2.0 Flash', cost: '$0.075/$0.3' },
]

type Tab = 'runs' | 'create' | 'gaps'

export default function ComparisonPage() {
  const [projectId, setProjectId] = useState('')
  const [tab, setTab] = useState<Tab>('runs')
  const [runs, setRuns] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedRun, setExpandedRun] = useState<string | null>(null)
  const [runResults, setRunResults] = useState<any>(null)
  const [gaps, setGaps] = useState<any[]>([])

  // Create form
  const [name, setName] = useState('')
  const [questions, setQuestions] = useState([{ id: 'q1', text: '' }])
  const [selectedModels, setSelectedModels] = useState<string[]>(['claude-sonnet-4-20250514', 'claude-haiku-4-5-20251001'])
  const [creating, setCreating] = useState(false)

  const { t } = useI18n()

  useEffect(() => {
    getDemoContext().then((ctx) => {
      setProjectId(ctx.project_id)
      loadRuns(ctx.project_id)
      loadGaps(ctx.project_id)
    }).catch(() => setLoading(false))
  }, [])

  const loadRuns = async (pid: string) => {
    const r = await fetch(`${AI}/api/v1/comparison/list/${pid}`)
    const d = await r.json()
    setRuns(d.runs || [])
    setLoading(false)
  }

  const loadGaps = async (pid: string) => {
    const r = await fetch(`${AI}/api/v1/comparison/gaps/list/${pid}`)
    const d = await r.json()
    setGaps(d.gaps || [])
  }

  const handleCreate = async () => {
    if (!name.trim() || questions.every(q => !q.text.trim())) return
    setCreating(true)
    const validQ = questions.filter(q => q.text.trim())
    await fetch(`${AI}/api/v1/comparison/create`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, name, questions: validQ, models: selectedModels }),
    })
    setName(''); setQuestions([{ id: 'q1', text: '' }])
    setCreating(false); setTab('runs')
    loadRuns(projectId)
  }

  const handleExecute = async (runId: string) => {
    await fetch(`${AI}/api/v1/comparison/${runId}/run`, { method: 'POST' })
    loadRuns(projectId)
  }

  const handleExpand = async (runId: string) => {
    if (expandedRun === runId) { setExpandedRun(null); return }
    const r = await fetch(`${AI}/api/v1/comparison/${runId}`)
    setRunResults(await r.json())
    setExpandedRun(runId)
  }

  const handleVote = async (responseId: string, isCorrect: boolean) => {
    await fetch(`${AI}/api/v1/comparison/vote`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ response_id: responseId, is_correct: isCorrect }),
    })
    if (expandedRun) handleExpand(expandedRun) // refresh
  }

  const handleSelectModel = async (runId: string, modelId: string) => {
    await fetch(`${AI}/api/v1/comparison/${runId}/select-model`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_id: modelId }),
    })
    loadRuns(projectId)
  }

  const handleAnalyzeGaps = async (runId: string) => {
    await fetch(`${AI}/api/v1/comparison/${runId}/gaps`)
    loadGaps(projectId)
    setTab('gaps')
  }

  const handleRemediate = async (gapId: string, type: string) => {
    await fetch(`${AI}/api/v1/comparison/gaps/${gapId}/remediate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type }),
    })
    loadGaps(projectId)
  }

  const [generating, setGenerating] = useState(false)
  const [judging, setJudging] = useState(false)
  const [recommendation, setRecommendation] = useState<any>(null)

  const handleAutoGenerate = async () => {
    setGenerating(true)
    try {
      const r = await fetch(`${AI}/api/v1/comparison/generate-questions/${projectId}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count: 15 }),
      })
      const d = await r.json()
      if (d.questions?.length) setQuestions(d.questions)
    } catch {}
    setGenerating(false)
  }

  const handleAutoJudge = async (runId: string) => {
    setJudging(true)
    await fetch(`${AI}/api/v1/comparison/${runId}/auto-judge`, { method: 'POST' })
    if (expandedRun) handleExpand(expandedRun)
    setJudging(false)
  }

  const handleRecommend = async (runId: string) => {
    const r = await fetch(`${AI}/api/v1/comparison/${runId}/recommend`)
    setRecommendation(await r.json())
  }

  const addQuestion = () => {
    setQuestions([...questions, { id: `q${questions.length + 1}`, text: '' }])
  }

  const toggleModel = (modelId: string) => {
    setSelectedModels(prev => prev.includes(modelId) ? prev.filter(m => m !== modelId) : [...prev, modelId])
  }

  if (loading) return <div className="flex h-full items-center justify-center bg-zinc-900"><div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" /></div>

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-auto">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-lg font-medium text-zinc-200 mb-1">{t('comparison.title')}</h1>
        <p className="text-xs text-zinc-500 mb-4">{t('comparison.desc')}</p>

        {/* Tabs */}
        <div className="flex gap-1 mb-4">
          {([
            { key: 'runs' as const, label: t('comparison.runs') },
            { key: 'create' as const, label: t('comparison.create') },
            { key: 'gaps' as const, label: t('comparison.gaps') },
          ]).map(({ key, label }) => (
            <button key={key} onClick={() => setTab(key)} className={`px-4 py-1.5 rounded text-xs ${tab === key ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200'}`}>
              {label}{key === 'gaps' && gaps.length > 0 && ` (${gaps.filter(g => g.remediation_status === 'pending').length})`}
            </button>
          ))}
        </div>

        {/* Create Tab */}
        {tab === 'create' && (
          <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4 space-y-4">
            <input value={name} onChange={e => setName(e.target.value)} placeholder={t('comparison.runName')} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />

            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-zinc-400">{t('comparison.questions')}</span>
                <div className="flex gap-2">
                  <button onClick={handleAutoGenerate} disabled={generating} className="text-xs text-green-400 hover:text-green-300 disabled:opacity-50">{generating ? '...' : '🤖 AI 產出問題'}</button>
                  <button onClick={addQuestion} className="text-xs text-blue-400 hover:text-blue-300">+ {t('comparison.addQ')}</button>
                </div>
              </div>
              {questions.map((q, i) => (
                <div key={i} className="flex gap-2 mb-1">
                  <span className="text-[10px] text-zinc-500 mt-2 w-6">{i + 1}</span>
                  <input value={q.text} onChange={e => { const next = [...questions]; next[i] = { ...next[i], text: e.target.value }; setQuestions(next) }}
                    placeholder={`${t('comparison.question')} ${i + 1}`} className="flex-1 rounded border border-zinc-600 bg-zinc-700 px-3 py-1.5 text-sm text-zinc-200 outline-none" />
                </div>
              ))}
            </div>

            <div>
              <span className="text-xs text-zinc-400 block mb-2">{t('comparison.selectModels')}</span>
              <div className="grid grid-cols-2 gap-1">
                {AVAILABLE_MODELS.map(m => (
                  <label key={m.id} className={`flex items-center gap-2 rounded border px-3 py-2 text-xs cursor-pointer ${selectedModels.includes(m.id) ? 'border-blue-500/50 bg-blue-500/10 text-zinc-200' : 'border-zinc-600 text-zinc-400'}`}>
                    <input type="checkbox" checked={selectedModels.includes(m.id)} onChange={() => toggleModel(m.id)} className="rounded" />
                    <span>{m.label}</span>
                    <span className="text-[10px] text-zinc-500 ml-auto font-mono">{m.cost}</span>
                  </label>
                ))}
              </div>
            </div>

            <button onClick={handleCreate} disabled={creating || !name.trim() || selectedModels.length < 2}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50 hover:bg-blue-500">
              {creating ? '...' : t('comparison.createRun')}
            </button>
          </div>
        )}

        {/* Runs Tab */}
        {tab === 'runs' && (
          <div className="space-y-2">
            {runs.map(run => (
              <div key={run.id} className="rounded-lg border border-zinc-700 bg-zinc-800/50">
                <button onClick={() => handleExpand(run.id)} className="w-full text-left px-4 py-3 flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-zinc-200">{run.name}</span>
                      <span className={`rounded px-1.5 py-0.5 text-[10px] ${run.status === 'completed' ? 'bg-green-500/20 text-green-400' : run.status === 'running' ? 'bg-blue-500/20 text-blue-400' : 'bg-zinc-600/20 text-zinc-400'}`}>{run.status}</span>
                      {run.selected_model && <span className="rounded bg-purple-500/20 px-1.5 py-0.5 text-[10px] text-purple-400">{run.selected_model}</span>}
                    </div>
                    <span className="text-[10px] text-zinc-500">{run.models?.length} models × {run.questions?.length} questions</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {run.status === 'pending' && <button onClick={(e) => { e.stopPropagation(); handleExecute(run.id) }} className="rounded bg-green-600 px-2 py-1 text-[10px] text-white">{t('comparison.execute')}</button>}
                    {run.status === 'completed' && <>
                      <button onClick={(e) => { e.stopPropagation(); handleAutoJudge(run.id) }} disabled={judging} className="rounded bg-purple-600 px-2 py-1 text-[10px] text-white disabled:opacity-50">{judging ? '...' : '🤖 AI 評審'}</button>
                      <button onClick={(e) => { e.stopPropagation(); handleRecommend(run.id) }} className="rounded bg-blue-600 px-2 py-1 text-[10px] text-white">⭐ 推薦</button>
                      <button onClick={(e) => { e.stopPropagation(); handleAnalyzeGaps(run.id) }} className="rounded bg-orange-600 px-2 py-1 text-[10px] text-white">{t('comparison.analyzeGaps')}</button>
                    </>}
                    <span className="text-zinc-600">{expandedRun === run.id ? '[-]' : '[+]'}</span>
                  </div>
                </button>

                {/* Expanded: Results */}
                {expandedRun === run.id && runResults && (
                  <div className="border-t border-zinc-700 p-4 space-y-4">
                    {/* Model Stats Matrix */}
                    {/* Recommendation Banner */}
                    {recommendation?.recommendation && (
                      <div className="rounded-lg border border-green-500/30 bg-green-500/10 px-4 py-3 flex items-center justify-between mb-3">
                        <div>
                          <span className="text-sm text-green-400 font-medium">⭐ 推薦模型：{recommendation.recommendation.split('-').slice(0, 3).join('-')}</span>
                          <span className="text-xs text-zinc-400 ml-2">綜合分數 {(recommendation.score * 100).toFixed(0)}</span>
                        </div>
                        <button onClick={() => handleSelectModel(expandedRun!, recommendation.recommendation)} className="rounded bg-green-600 px-3 py-1 text-xs text-white">選定此模型</button>
                      </div>
                    )}
                    {runResults.model_stats && (
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="text-zinc-500">
                              <th className="text-left py-1">{t('comparison.model')}</th>
                              <th className="text-center py-1">{t('comparison.accuracy')}</th>
                              <th className="text-center py-1">{t('comparison.avgCost')}</th>
                              <th className="text-center py-1">{t('comparison.avgLatency')}</th>
                              <th className="text-center py-1"></th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(runResults.model_stats).map(([model, stats]: [string, any]) => (
                              <tr key={model} className={`border-t border-zinc-700/50 ${run.selected_model === model ? 'bg-purple-500/10' : ''}`}>
                                <td className="py-2 text-zinc-200 font-mono text-[11px]">{model.split('-').slice(0, 2).join('-')}</td>
                                <td className="text-center py-2">
                                  <span className={`font-mono ${stats.accuracy >= 80 ? 'text-green-400' : stats.accuracy >= 50 ? 'text-yellow-400' : 'text-red-400'}`}>{stats.accuracy}%</span>
                                </td>
                                <td className="text-center py-2 font-mono text-zinc-400">${stats.avg_cost?.toFixed(4)}</td>
                                <td className="text-center py-2 font-mono text-zinc-400">{stats.avg_latency}ms</td>
                                <td className="text-center py-2">
                                  <button onClick={() => handleSelectModel(run.id, model)} className={`rounded px-2 py-0.5 text-[10px] ${run.selected_model === model ? 'bg-purple-500 text-white' : 'bg-zinc-700 text-zinc-400 hover:text-zinc-200'}`}>
                                    {run.selected_model === model ? '✓ 選定' : '選擇'}
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {/* Per-question responses */}
                    {runResults.responses && Object.entries(runResults.responses).map(([qId, resps]: [string, any]) => {
                      const q = run.questions?.find((q: any) => q.id === qId)
                      return (
                        <div key={qId} className="rounded border border-zinc-700 bg-zinc-800 p-3">
                          <p className="text-xs text-zinc-300 mb-2 font-medium">{q?.text || qId}</p>
                          <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${run.models?.length || 1}, 1fr)` }}>
                            {(resps as any[]).map((r: any) => (
                              <div key={r.id} className={`rounded border p-2 text-[11px] ${r.is_correct === true ? 'border-green-500/30 bg-green-500/5' : r.is_correct === false ? 'border-red-500/30 bg-red-500/5' : 'border-zinc-600'}`}>
                                <div className="flex items-center justify-between mb-1">
                                  <span className="text-zinc-400 font-mono text-[10px]">{r.model_id.split('-').slice(0, 2).join('-')}</span>
                                  <div className="flex gap-1">
                                    <button onClick={() => handleVote(r.id, true)} className={`rounded px-1 py-0.5 text-[9px] ${r.is_correct === true ? 'bg-green-500 text-white' : 'bg-zinc-700 text-zinc-500'}`}>✓</button>
                                    <button onClick={() => handleVote(r.id, false)} className={`rounded px-1 py-0.5 text-[9px] ${r.is_correct === false ? 'bg-red-500 text-white' : 'bg-zinc-700 text-zinc-500'}`}>✗</button>
                                  </div>
                                </div>
                                <p className="text-zinc-300 line-clamp-4">{r.response_text?.slice(0, 200)}</p>
                                <div className="flex gap-2 mt-1 text-[9px] text-zinc-500">
                                  <span>${r.cost_usd?.toFixed(4)}</span>
                                  <span>{r.latency_ms}ms</span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            ))}
            {runs.length === 0 && <p className="text-sm text-zinc-500 text-center py-12">{t('comparison.empty')}</p>}
          </div>
        )}

        {/* Gaps Tab */}
        {tab === 'gaps' && (
          <div className="space-y-2">
            {gaps.filter(g => g.remediation_status === 'pending').map(gap => (
              <div key={gap.id} className="rounded-lg border border-red-500/20 bg-red-500/5 p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-red-400 font-medium">{t('comparison.conceptGap')}</span>
                  <span className="text-[10px] text-zinc-500">{gap.selected_model} → {gap.correct_model}</span>
                </div>
                <p className="text-sm text-zinc-200">{gap.question_text}</p>
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div className="rounded border border-red-500/20 p-2">
                    <span className="text-red-400 text-[10px]">{gap.selected_model} (❌)</span>
                    <p className="text-zinc-400 line-clamp-3 mt-1">{gap.selected_model_response?.slice(0, 150)}</p>
                  </div>
                  <div className="rounded border border-green-500/20 p-2">
                    <span className="text-green-400 text-[10px]">{gap.correct_model} (✓)</span>
                    <p className="text-zinc-400 line-clamp-3 mt-1">{gap.correct_response?.slice(0, 150)}</p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => handleRemediate(gap.id, 'rag')} className="rounded bg-blue-600 px-3 py-1 text-[10px] text-white">→ RAG 知識庫</button>
                  <button onClick={() => handleRemediate(gap.id, 'prompt')} className="rounded bg-purple-600 px-3 py-1 text-[10px] text-white">→ Prompt 修正</button>
                  <button onClick={() => handleRemediate(gap.id, 'eval')} className="rounded bg-green-600 px-3 py-1 text-[10px] text-white">→ Eval 監控</button>
                </div>
              </div>
            ))}
            {gaps.filter(g => g.remediation_status === 'applied').length > 0 && (
              <div className="mt-4">
                <p className="text-xs text-zinc-500 mb-2">{t('comparison.remediated')}</p>
                {gaps.filter(g => g.remediation_status === 'applied').map(gap => (
                  <div key={gap.id} className="rounded border border-zinc-700 bg-zinc-800/50 px-4 py-2 mb-1 flex items-center justify-between">
                    <span className="text-xs text-zinc-400 truncate">{gap.question_text?.slice(0, 60)}</span>
                    <span className="text-[10px] text-green-400">{gap.remediation_type} ✓</span>
                  </div>
                ))}
              </div>
            )}
            {gaps.length === 0 && <p className="text-sm text-zinc-500 text-center py-12">{t('comparison.noGaps')}</p>}
          </div>
        )}
      </div>
    </div>
  )
}
