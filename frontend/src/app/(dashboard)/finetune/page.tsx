'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

type TabKey = 'data' | 'jobs'

export default function FinetunePage() {
  const [projectId, setProjectId] = useState('')
  const [tab, setTab] = useState<TabKey>('data')
  const [loading, setLoading] = useState(true)

  // Data tab
  const [stats, setStats] = useState<any>(null)
  const [pairs, setPairs] = useState<any[]>([])
  const [exportFormat, setExportFormat] = useState('openai')
  const [exportedJsonl, setExportedJsonl] = useState('')
  const [exporting, setExporting] = useState(false)

  // Jobs tab
  const [jobs, setJobs] = useState<any[]>([])
  const [creating, setCreating] = useState(false)
  const [jobProvider, setJobProvider] = useState('openai')
  const [jobModel, setJobModel] = useState('gpt-4o-mini')

  const { t } = useI18n()

  useEffect(() => {
    getDemoContext().then((ctx) => {
      setProjectId(ctx.project_id)
      loadStats(ctx.project_id)
      loadJobs(ctx.project_id)
    }).catch(() => setLoading(false))
  }, [])

  const loadStats = async (pid: string) => {
    try {
      const r = await fetch(`${AI}/api/v1/finetune/stats/${pid}`)
      setStats(await r.json())
    } catch {}
    setLoading(false)
  }

  const loadPairs = async () => {
    try {
      const r = await fetch(`${AI}/api/v1/finetune/extract/${projectId}`, { method: 'POST' })
      const d = await r.json()
      setPairs(d.pairs || [])
    } catch {}
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const r = await fetch(`${AI}/api/v1/finetune/export/${projectId}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format: exportFormat }),
      })
      const d = await r.json()
      setExportedJsonl(d.jsonl || '')
    } catch {}
    setExporting(false)
  }

  const handleDownload = () => {
    if (!exportedJsonl) return
    const blob = new Blob([exportedJsonl], { type: 'application/jsonl' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `training-data-${exportFormat}.jsonl`
    a.click()
    URL.revokeObjectURL(url)
  }

  const loadJobs = async (pid: string) => {
    try {
      const r = await fetch(`${AI}/api/v1/finetune/jobs/${pid}`)
      const d = await r.json()
      setJobs(d.jobs || [])
    } catch {}
  }

  const handleCreateJob = async () => {
    setCreating(true)
    try {
      await fetch(`${AI}/api/v1/finetune/jobs/${projectId}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: jobProvider, model_base: jobModel }),
      })
      await loadJobs(projectId)
    } catch {}
    setCreating(false)
  }

  if (loading) return <div className="flex h-full items-center justify-center bg-zinc-900"><div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" /></div>

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-auto">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-lg font-medium text-zinc-200 mb-1">{t('finetune.title')}</h1>
        <p className="text-xs text-zinc-500 mb-4">{t('finetune.desc')}</p>

        {/* Tabs */}
        <div className="flex gap-1 mb-4">
          {([
            { key: 'data' as const, label: t('finetune.trainingData') },
            { key: 'jobs' as const, label: t('finetune.jobs') },
          ]).map(({ key, label }) => (
            <button key={key} onClick={() => setTab(key)} className={`px-4 py-1.5 rounded text-xs ${tab === key ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200'}`}>
              {label}
            </button>
          ))}
        </div>

        {/* ====== Data Tab ====== */}
        {tab === 'data' && (
          <div className="space-y-4">
            {/* Stats Card */}
            {stats && (
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
                <h3 className="text-sm font-medium text-zinc-200 mb-3">{t('finetune.stats')}</h3>
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <p className="text-2xl font-mono text-zinc-200">{stats.total_clean_pairs ?? stats.total_training_pairs ?? 0}</p>
                    <p className="text-xs text-zinc-400">{t('finetune.cleanPairs')}</p>
                  </div>
                  <div>
                    <p className="text-2xl font-mono text-zinc-200">{stats.total_raw_pairs ?? stats.total_training_pairs ?? 0}</p>
                    <p className="text-xs text-zinc-400">{t('finetune.rawPairs')}</p>
                  </div>
                  <div>
                    <p className={`text-2xl font-mono ${stats.ready_for_training ? 'text-green-400' : 'text-yellow-400'}`}>
                      {stats.ready_for_training ? 'Ready' : 'Not Ready'}
                    </p>
                    <p className="text-xs text-zinc-400">{t('finetune.minPairs')}: {stats.min_recommended || 50}</p>
                  </div>
                </div>
                {/* Progress bar */}
                <div className="mt-3">
                  <div className="w-full h-2 bg-zinc-700 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${stats.ready_for_training ? 'bg-green-500' : 'bg-yellow-500'}`}
                      style={{ width: `${Math.min(100, ((stats.total_clean_pairs ?? stats.total_training_pairs ?? 0) / (stats.min_recommended || 50)) * 100)}%` }} />
                  </div>
                </div>
              </div>
            )}

            {/* Preview Training Pairs */}
            <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-medium text-zinc-200">{t('finetune.preview')}</h3>
                <button onClick={loadPairs} className="text-xs text-blue-400 hover:text-blue-300">{t('finetune.extract')}</button>
              </div>
              {pairs.length > 0 ? (
                <div className="space-y-2 max-h-64 overflow-auto">
                  {pairs.slice(0, 20).map((pair, i) => (
                    <div key={i} className="rounded border border-zinc-700 bg-zinc-700/30 p-2 text-xs">
                      <p className="text-blue-400 truncate">U: {pair.user_message}</p>
                      <p className="text-green-400 truncate mt-1">A: {pair.assistant_message}</p>
                    </div>
                  ))}
                  {pairs.length > 20 && <p className="text-xs text-zinc-500 text-center">...{pairs.length - 20} more</p>}
                </div>
              ) : (
                <p className="text-xs text-zinc-500 text-center py-4">{t('finetune.noPairs')}</p>
              )}
            </div>

            {/* Export */}
            <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
              <h3 className="text-sm font-medium text-zinc-200 mb-3">{t('finetune.export')}</h3>
              <div className="flex items-center gap-3">
                <select value={exportFormat} onChange={(e) => setExportFormat(e.target.value)}
                  className="rounded border border-zinc-600 bg-zinc-700 px-2 py-1.5 text-xs text-zinc-200 outline-none">
                  <option value="openai">OpenAI format</option>
                  <option value="anthropic">Anthropic format</option>
                  <option value="generic">Generic (input/output)</option>
                </select>
                <button onClick={handleExport} disabled={exporting} className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50">
                  {exporting ? '...' : t('finetune.exportBtn')}
                </button>
                {exportedJsonl && (
                  <button onClick={handleDownload} className="rounded bg-green-600 px-3 py-1.5 text-xs text-white hover:bg-green-500">
                    {t('finetune.download')}
                  </button>
                )}
              </div>
              {exportedJsonl && (
                <pre className="mt-3 max-h-32 overflow-auto rounded border border-zinc-700 bg-zinc-900 p-2 text-[10px] text-zinc-400 font-mono">
                  {exportedJsonl.slice(0, 500)}{exportedJsonl.length > 500 ? '...' : ''}
                </pre>
              )}
            </div>
          </div>
        )}

        {/* ====== Jobs Tab ====== */}
        {tab === 'jobs' && (
          <div className="space-y-4">
            {/* Create Job */}
            <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
              <h3 className="text-sm font-medium text-zinc-200 mb-3">{t('finetune.createJob')}</h3>
              <div className="flex items-center gap-3">
                <select value={jobProvider} onChange={(e) => setJobProvider(e.target.value)}
                  className="rounded border border-zinc-600 bg-zinc-700 px-2 py-1.5 text-xs text-zinc-200 outline-none">
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="together">Together AI</option>
                </select>
                <input value={jobModel} onChange={(e) => setJobModel(e.target.value)} placeholder="Base model"
                  className="flex-1 rounded border border-zinc-600 bg-zinc-700 px-2 py-1.5 text-xs text-zinc-200 outline-none" />
                <button onClick={handleCreateJob} disabled={creating} className="rounded bg-green-600 px-4 py-1.5 text-xs text-white hover:bg-green-500 disabled:opacity-50">
                  {creating ? '...' : t('finetune.startTraining')}
                </button>
              </div>
              <p className="text-[10px] text-zinc-500 mt-2">{t('finetune.jobNote')}</p>
            </div>

            {/* Job List */}
            <div className="space-y-2">
              {jobs.map((job) => (
                <div key={job.id} className="rounded-lg border border-zinc-700 bg-zinc-800/50 px-4 py-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className={`rounded px-2 py-0.5 text-[10px] font-medium ${
                        job.status === 'completed' ? 'bg-green-500/20 text-green-400' :
                        job.status === 'running' ? 'bg-blue-500/20 text-blue-400' :
                        job.status === 'failed' ? 'bg-red-500/20 text-red-400' :
                        'bg-zinc-600/20 text-zinc-400'
                      }`}>{job.status}</span>
                      <span className="text-xs text-zinc-300">{job.provider} / {job.model_base}</span>
                      <span className="text-[10px] text-zinc-500">{job.training_data_count} pairs</span>
                    </div>
                    <span className="text-xs text-zinc-400">{new Date(job.created_at).toLocaleString('zh-TW')}</span>
                  </div>
                  {job.result_model_id && (
                    <p className="text-xs text-green-400 mt-1">{t('finetune.resultModel')}: {job.result_model_id}</p>
                  )}
                  {job.error_message && (
                    <p className="text-xs text-red-400 mt-1">{job.error_message}</p>
                  )}
                </div>
              ))}
              {jobs.length === 0 && <p className="text-sm text-zinc-500 text-center py-12">{t('finetune.noJobs')}</p>}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
