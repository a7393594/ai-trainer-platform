'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

const MODELS = [
  { id: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4', provider: 'anthropic' },
  { id: 'claude-opus-4-20250514', label: 'Claude Opus 4', provider: 'anthropic' },
  { id: 'claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5', provider: 'anthropic' },
  { id: 'gpt-4o', label: 'GPT-4o', provider: 'openai' },
  { id: 'gpt-4o-mini', label: 'GPT-4o Mini', provider: 'openai' },
  { id: 'gemini/gemini-2.0-flash', label: 'Gemini 2.0 Flash', provider: 'google' },
]

type Tab = 'project' | 'finetune' | 'eval'

export default function SettingsPage() {
  const [context, setContext] = useState<any>(null)
  const [tab, setTab] = useState<Tab>('project')
  const [loading, setLoading] = useState(true)
  const [selectedModel, setSelectedModel] = useState('')
  const [saving, setSaving] = useState(false)

  // Finetune state
  const [ftStats, setFtStats] = useState<any>(null)
  const [pairs, setPairs] = useState<any[]>([])
  const [exportFormat, setExportFormat] = useState('openai')
  const [exportedJsonl, setExportedJsonl] = useState('')
  const [jobs, setJobs] = useState<any[]>([])

  // Eval state
  const [cases, setCases] = useState<any[]>([])
  const [runs, setRuns] = useState<any[]>([])
  const [showAddCase, setShowAddCase] = useState(false)
  const [caseInput, setCaseInput] = useState('')
  const [caseExpected, setCaseExpected] = useState('')
  const [caseCategory, setCaseCategory] = useState('')
  const [running, setRunning] = useState(false)

  const { t } = useI18n()

  useEffect(() => {
    getDemoContext().then(async ctx => {
      setContext(ctx)
      // Load project model
      const pr = await fetch(`${AI}/api/v1/projects/${ctx.project_id}`).then(r => r.json()).catch(() => ({}))
      setSelectedModel(pr.default_model || 'claude-sonnet-4-20250514')
      // Load finetune
      setFtStats(await fetch(`${AI}/api/v1/finetune/stats/${ctx.project_id}`).then(r => r.json()).catch(() => null))
      setJobs((await fetch(`${AI}/api/v1/finetune/jobs/${ctx.project_id}`).then(r => r.json()).catch(() => ({ jobs: [] }))).jobs || [])
      // Load eval
      setCases((await fetch(`${AI}/api/v1/eval/test-cases/${ctx.project_id}`).then(r => r.json()).catch(() => ({ test_cases: [] }))).test_cases || [])
      setRuns((await fetch(`${AI}/api/v1/eval/runs/${ctx.project_id}`).then(r => r.json()).catch(() => ({ runs: [] }))).runs || [])
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const handleModelChange = async (modelId: string) => {
    setSelectedModel(modelId); setSaving(true)
    await fetch(`${AI}/api/v1/projects/${context.project_id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ default_model: modelId }),
    })
    setSaving(false)
  }

  const handleExport = async () => {
    const r = await fetch(`${AI}/api/v1/finetune/export/${context.project_id}`, { method: 'POST' })
    const d = await r.json()
    setExportedJsonl(d.jsonl || '')
  }

  const handleDownload = () => {
    if (!exportedJsonl) return
    const blob = new Blob([exportedJsonl], { type: 'application/jsonl' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = `training-data.jsonl`; a.click()
    URL.revokeObjectURL(url)
  }

  const handleAddCase = async () => {
    if (!caseInput.trim() || !caseExpected.trim()) return
    await fetch(`${AI}/api/v1/eval/test-cases`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: context.project_id, input_text: caseInput, expected_output: caseExpected, category: caseCategory || null }),
    })
    setCaseInput(''); setCaseExpected(''); setCaseCategory(''); setShowAddCase(false)
    const r = await fetch(`${AI}/api/v1/eval/test-cases/${context.project_id}`)
    setCases((await r.json()).test_cases || [])
  }

  const handleRunEval = async () => {
    setRunning(true)
    await fetch(`${AI}/api/v1/eval/run/${context.project_id}`, { method: 'POST' })
    const r = await fetch(`${AI}/api/v1/eval/runs/${context.project_id}`)
    setRuns((await r.json()).runs || [])
    setRunning(false)
  }

  if (loading) return <div className="flex h-full items-center justify-center bg-zinc-900"><div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" /></div>

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-auto">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-lg font-medium text-zinc-200 mb-1">{t('settings.title')}</h1>
        <p className="text-xs text-zinc-500 mb-4">{t('settings.desc')}</p>

        <div className="flex gap-1 mb-4">
          {(['project', 'finetune', 'eval'] as const).map(k => (
            <button key={k} onClick={() => setTab(k)} className={`px-4 py-1.5 rounded text-xs ${tab === k ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400'}`}>
              {k === 'project' ? t('settings.projectTab') : k === 'finetune' ? t('settings.finetuneTab') : t('settings.evalTab')}
            </button>
          ))}
        </div>

        {/* Project Tab */}
        {tab === 'project' && (
          <div className="space-y-4">
            <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
              <h2 className="text-sm font-medium text-zinc-200 mb-3">{t('settings.projectInfo')}</h2>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><span className="text-zinc-400">{t('settings.name')}:</span> <span className="text-zinc-200 ml-2">{context?.project_name}</span></div>
                <div><span className="text-zinc-400">ID:</span> <span className="text-zinc-500 ml-2 font-mono text-xs">{context?.project_id?.slice(0, 12)}...</span></div>
              </div>
            </div>
            <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-medium text-zinc-200">{t('settings.defaultModel')}</h2>
                {saving && <span className="text-[10px] text-blue-400 animate-pulse">saving...</span>}
              </div>
              {MODELS.map(m => (
                <button key={m.id} onClick={() => handleModelChange(m.id)}
                  className={`w-full flex items-center justify-between py-2 px-3 rounded-lg text-left mb-1 transition-colors ${selectedModel === m.id ? 'bg-blue-600/20 border border-blue-500/50' : 'hover:bg-zinc-700/50 border border-transparent'}`}>
                  <div className="flex items-center gap-2">
                    {selectedModel === m.id && <span className="text-blue-400 text-xs">✓</span>}
                    <span className={`text-sm ${selectedModel === m.id ? 'text-blue-300' : 'text-zinc-200'}`}>{m.label}</span>
                  </div>
                  <span className="text-xs text-zinc-500">{m.provider}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Finetune Tab */}
        {tab === 'finetune' && (
          <div className="space-y-4">
            {ftStats && (
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
                <h3 className="text-sm font-medium text-zinc-200 mb-3">{t('settings.finetuneStats')}</h3>
                <div className="grid grid-cols-3 gap-3">
                  <div className="text-center"><p className="text-2xl font-mono text-zinc-200">{ftStats.total_clean_pairs ?? 0}</p><p className="text-xs text-zinc-400">Clean Pairs</p></div>
                  <div className="text-center"><p className="text-2xl font-mono text-zinc-200">{ftStats.total_raw_pairs ?? 0}</p><p className="text-xs text-zinc-400">Raw Pairs</p></div>
                  <div className="text-center"><p className={`text-2xl font-mono ${ftStats.ready_for_training ? 'text-green-400' : 'text-yellow-400'}`}>{ftStats.ready_for_training ? 'Ready' : 'Not Ready'}</p><p className="text-xs text-zinc-400">Min: {ftStats.min_recommended}</p></div>
                </div>
              </div>
            )}
            <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
              <h3 className="text-sm font-medium text-zinc-200 mb-3">{t('settings.export')}</h3>
              <div className="flex items-center gap-3">
                <select value={exportFormat} onChange={e => setExportFormat(e.target.value)} className="rounded border border-zinc-600 bg-zinc-700 px-2 py-1.5 text-xs text-zinc-200 outline-none">
                  <option value="openai">OpenAI</option><option value="anthropic">Anthropic</option><option value="generic">Generic</option>
                </select>
                <button onClick={handleExport} className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white">{t('settings.exportBtn')}</button>
                {exportedJsonl && <button onClick={handleDownload} className="rounded bg-green-600 px-3 py-1.5 text-xs text-white">{t('settings.download')}</button>}
              </div>
            </div>
            {jobs.length > 0 && (
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
                <h3 className="text-sm font-medium text-zinc-200 mb-3">{t('settings.jobs')}</h3>
                {jobs.map(j => (
                  <div key={j.id} className="flex items-center justify-between py-1.5 border-b border-zinc-700/50 last:border-0">
                    <div className="flex items-center gap-2">
                      <span className={`rounded px-1.5 py-0.5 text-[10px] ${j.status === 'completed' ? 'bg-green-500/20 text-green-400' : j.status === 'running' ? 'bg-blue-500/20 text-blue-400' : 'bg-zinc-600/20 text-zinc-400'}`}>{j.status}</span>
                      <span className="text-xs text-zinc-300">{j.provider}/{j.model_base}</span>
                    </div>
                    <span className="text-[10px] text-zinc-500">{j.training_data_count} pairs</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Eval Tab */}
        {tab === 'eval' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-zinc-200">{cases.length} test cases</span>
              <div className="flex gap-2">
                <button onClick={() => setShowAddCase(true)} className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white">+ Add</button>
                <button onClick={handleRunEval} disabled={running || cases.length === 0} className="rounded bg-green-600 px-3 py-1.5 text-xs text-white disabled:opacity-50">{running ? '...' : 'Run Eval'}</button>
              </div>
            </div>
            {showAddCase && (
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4 space-y-2">
                <textarea value={caseInput} onChange={e => setCaseInput(e.target.value)} placeholder="Input" rows={2} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
                <textarea value={caseExpected} onChange={e => setCaseExpected(e.target.value)} placeholder="Expected output" rows={3} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
                <input value={caseCategory} onChange={e => setCaseCategory(e.target.value)} placeholder="Category (optional)" className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
                <div className="flex gap-2 justify-end">
                  <button onClick={() => setShowAddCase(false)} className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300">Cancel</button>
                  <button onClick={handleAddCase} className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white">Save</button>
                </div>
              </div>
            )}
            {cases.map(tc => (
              <div key={tc.id} className="rounded border border-zinc-700 bg-zinc-800/50 p-3">
                <p className="text-xs text-zinc-400">Input:</p>
                <p className="text-sm text-zinc-200 truncate">{tc.input_text}</p>
                <p className="text-xs text-zinc-400 mt-1">Expected:</p>
                <p className="text-xs text-zinc-300 truncate">{tc.expected_output}</p>
                {tc.category && <span className="rounded bg-purple-500/20 px-1.5 py-0.5 text-[10px] text-purple-400 mt-1 inline-block">{tc.category}</span>}
              </div>
            ))}
            {runs.length > 0 && (
              <div className="mt-4">
                <h3 className="text-sm text-zinc-200 mb-2">Recent Runs</h3>
                {runs.slice(0, 5).map(run => (
                  <div key={run.id} className="flex items-center justify-between py-1.5 border-b border-zinc-700/50">
                    <span className="text-xs text-zinc-400">{new Date(run.run_at).toLocaleString('zh-TW')}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-mono text-zinc-200">{Math.round(run.total_score)}%</span>
                      <span className="text-xs text-green-400">{run.passed_count}P</span>
                      <span className="text-xs text-red-400">{run.failed_count}F</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
