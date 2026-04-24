'use client'

import { useEffect, useState } from 'react'
import {
  getDemoContext,
  listProviderKeys,
  setProviderKey,
  verifyProviderKey,
  removeProviderKey,
  type ProviderKeyRow,
} from '@/lib/ai-engine'
import { invalidateModelsCache } from '@/components/shared/ModelSelector'
import { useI18n } from '@/lib/i18n'
import { useProject } from '@/lib/project-context'
import dynamic from 'next/dynamic'

const RefereeSettings = dynamic(() => import('../referee/settings/page'), { ssr: false })

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

// Models loaded dynamically from API

type Tab = 'project' | 'providers' | 'finetune' | 'eval'

export default function SettingsPage() {
  const { currentProject } = useProject()

  if (currentProject?.project_type === 'referee') {
    return <RefereeSettings />
  }

  return <TrainerSettings />
}

function TrainerSettings() {
  const [context, setContext] = useState<any>(null)
  const [tab, setTab] = useState<Tab>('project')
  const [loading, setLoading] = useState(true)
  const [selectedModel, setSelectedModel] = useState('')
  const [saving, setSaving] = useState(false)
  const [models, setModels] = useState<any[]>([])

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
      // Load models from API + project settings
      setModels((await fetch(`${AI}/api/v1/models`).then(r => r.json()).catch(() => ({ models: [] }))).models || [])
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
          {(['project', 'providers', 'finetune', 'eval'] as const).map(k => (
            <button key={k} onClick={() => setTab(k)} className={`px-4 py-1.5 rounded text-xs ${tab === k ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400'}`}>
              {k === 'project' ? t('settings.projectTab')
                : k === 'providers' ? 'Provider API Keys'
                : k === 'finetune' ? t('settings.finetuneTab')
                : t('settings.evalTab')}
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
              {models.map((m: any) => (
                <button key={m.id} onClick={() => handleModelChange(m.id)}
                  className={`w-full flex items-center justify-between py-2 px-3 rounded-lg text-left mb-1 transition-colors ${selectedModel === m.id ? 'bg-blue-600/20 border border-blue-500/50' : 'hover:bg-zinc-700/50 border border-transparent'}`}>
                  <div className="flex items-center gap-2">
                    {selectedModel === m.id && <span className="text-blue-400 text-xs">✓</span>}
                    <span className={`text-sm ${selectedModel === m.id ? 'text-blue-300' : 'text-zinc-200'}`}>{m.label}</span>
                    <span className={`rounded px-1 py-0.5 text-[9px] ${m.tier === 'free' ? 'bg-green-500/20 text-green-400' : m.tier === 'free-tier' ? 'bg-cyan-500/20 text-cyan-400' : m.tier === 'low-cost' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-zinc-600/20 text-zinc-400'}`}>
                      {m.tier === 'free' ? 'FREE' : m.tier === 'free-tier' ? 'FREE TIER' : m.tier === 'low-cost' ? 'LOW COST' : 'PAID'}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-zinc-500 font-mono">{m.cost}</span>
                    <span className="text-[10px] text-zinc-600">{m.provider}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Provider API Keys Tab */}
        {tab === 'providers' && context?.tenant_id && (
          <ProviderKeysPanel tenantId={context.tenant_id} />
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

// ────────────────────────────────────────────────────────────────
// Provider API Keys panel
// ────────────────────────────────────────────────────────────────

const PROVIDER_META: Record<string, { label: string; docs?: string; docsLabel?: string; hint?: string }> = {
  openai: { label: 'OpenAI (GPT)', docs: 'https://platform.openai.com/api-keys', docsLabel: 'platform.openai.com', hint: 'sk-... 格式' },
  google: { label: 'Google (Gemini)', docs: 'https://aistudio.google.com/apikey', docsLabel: 'aistudio.google.com', hint: 'AIza... 格式' },
  groq: { label: 'Groq (Llama/Qwen 免費)', docs: 'https://console.groq.com/keys', docsLabel: 'console.groq.com', hint: 'gsk_... 格式' },
  deepseek: { label: 'DeepSeek', docs: 'https://platform.deepseek.com/api_keys', docsLabel: 'platform.deepseek.com', hint: 'sk-... 格式' },
  openrouter: { label: 'OpenRouter (多家聚合)', docs: 'https://openrouter.ai/keys', docsLabel: 'openrouter.ai', hint: 'sk-or-... 格式' },
}

function ProviderKeysPanel({ tenantId }: { tenantId: string }) {
  const [rows, setRows] = useState<ProviderKeyRow[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string>('')  // provider currently being acted on
  const [editing, setEditing] = useState<string>('')
  const [draftKey, setDraftKey] = useState<string>('')

  const load = async () => {
    setLoading(true)
    try {
      const res = await listProviderKeys(tenantId)
      setRows(res.keys || [])
    } catch (e) {
      setRows([])
    }
    setLoading(false)
  }

  useEffect(() => { load() }, [tenantId])

  const handleSave = async (provider: string) => {
    if (!draftKey.trim()) return
    setBusy(provider)
    try {
      await setProviderKey(tenantId, provider, draftKey.trim())
      setEditing(''); setDraftKey('')
      invalidateModelsCache(tenantId)
      await load()
    } catch (e: any) {
      alert(`儲存失敗：${e?.message || String(e)}`)
    } finally {
      setBusy('')
    }
  }

  const handleVerify = async (provider: string) => {
    setBusy(provider)
    try {
      await verifyProviderKey(tenantId, provider)
      invalidateModelsCache(tenantId)
      await load()
    } catch (e: any) {
      alert(`驗證失敗：${e?.message || String(e)}`)
    } finally {
      setBusy('')
    }
  }

  const handleRemove = async (provider: string) => {
    if (!confirm(`確定要刪除 ${PROVIDER_META[provider]?.label || provider} 的 API key 嗎？`)) return
    setBusy(provider)
    try {
      await removeProviderKey(tenantId, provider)
      invalidateModelsCache(tenantId)
      await load()
    } finally {
      setBusy('')
    }
  }

  if (loading) {
    return <div className="text-xs text-zinc-500">載入中...</div>
  }

  return (
    <div className="space-y-3">
      <div className="rounded border border-zinc-700 bg-zinc-800/50 p-3 text-xs text-zinc-400">
        <p className="text-zinc-300 font-medium mb-1">你自己的 LLM Provider API Key</p>
        <p>設定後，DAG 編輯器就能在節點中挑選對應 provider 的模型（GPT / Gemini / Groq / DeepSeek / OpenRouter）。Key 會加密存在資料庫裡，呼叫時動態注入，伺服器記憶體中不留副本。</p>
        <p className="mt-1 text-zinc-500">Anthropic (Claude) 由伺服器環境變數統一提供，不走這個表。</p>
      </div>

      {rows.map((row) => {
        const meta = PROVIDER_META[row.provider]
        const verified = !!row.verified_at
        const failed = !verified && !!row.last_error
        const isEditing = editing === row.provider
        const isBusy = busy === row.provider

        return (
          <div key={row.provider} className="rounded-lg border border-zinc-700 bg-zinc-800 p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-zinc-200">{meta?.label || row.provider}</span>
                  {isBusy ? (
                    <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] text-amber-300">⋯ 處理中</span>
                  ) : verified ? (
                    <span className="rounded bg-green-500/20 px-1.5 py-0.5 text-[10px] text-green-400" title={`last verified with ${row.last_verified_model || ''}`}>✓ Verified</span>
                  ) : failed ? (
                    <span className="rounded bg-red-500/20 px-1.5 py-0.5 text-[10px] text-red-400" title={row.last_error || ''}>✗ Failed</span>
                  ) : row.has_key ? (
                    <span className="rounded bg-zinc-600/30 px-1.5 py-0.5 text-[10px] text-zinc-400">– Not tested</span>
                  ) : (
                    <span className="rounded bg-zinc-700 px-1.5 py-0.5 text-[10px] text-zinc-500">– Not set</span>
                  )}
                </div>
                <div className="mt-1 text-[11px] text-zinc-500 font-mono">
                  {row.has_key ? `••••••••••${row.last4 || ''}` : '(未設定)'}
                </div>
                {row.last_error && !verified && (
                  <p className="mt-1 text-[11px] text-red-400 truncate" title={row.last_error}>錯誤：{row.last_error}</p>
                )}
                {meta?.docs && !isEditing && (
                  <p className="mt-1 text-[11px] text-zinc-500">
                    申請 key：<a href={meta.docs} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline">{meta.docsLabel}</a>
                    {meta.hint && <span className="ml-2 text-zinc-600">({meta.hint})</span>}
                  </p>
                )}
              </div>

              {!isEditing && (
                <div className="flex gap-1 shrink-0">
                  <button
                    onClick={() => { setEditing(row.provider); setDraftKey('') }}
                    disabled={isBusy}
                    className="rounded border border-zinc-600 px-2.5 py-1 text-[11px] text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
                  >
                    {row.has_key ? 'Edit' : 'Set Key'}
                  </button>
                  {row.has_key && (
                    <button
                      onClick={() => handleVerify(row.provider)}
                      disabled={isBusy}
                      className="rounded border border-zinc-600 px-2.5 py-1 text-[11px] text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
                    >
                      Test
                    </button>
                  )}
                  {row.has_key && (
                    <button
                      onClick={() => handleRemove(row.provider)}
                      disabled={isBusy}
                      className="rounded border border-red-600/50 px-2.5 py-1 text-[11px] text-red-400 hover:bg-red-900/30 disabled:opacity-50"
                    >
                      Remove
                    </button>
                  )}
                </div>
              )}
            </div>

            {isEditing && (
              <div className="mt-3 flex gap-2">
                <input
                  type="password"
                  autoFocus
                  value={draftKey}
                  onChange={(e) => setDraftKey(e.target.value)}
                  placeholder={meta?.hint || '貼上 API key'}
                  className="flex-1 rounded border border-zinc-600 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-200 outline-none focus:border-blue-500 font-mono"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleSave(row.provider)
                    if (e.key === 'Escape') { setEditing(''); setDraftKey('') }
                  }}
                />
                <button
                  onClick={() => handleSave(row.provider)}
                  disabled={!draftKey.trim() || isBusy}
                  className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white disabled:opacity-50"
                >
                  Save & Test
                </button>
                <button
                  onClick={() => { setEditing(''); setDraftKey('') }}
                  className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        )
      })}

      <div className="rounded border border-zinc-700/60 bg-zinc-800/30 p-3 text-xs text-zinc-500">
        <span className="text-zinc-400">Anthropic (Claude)</span>　— 由伺服器環境變數 <code className="text-zinc-400">ANTHROPIC_API_KEY</code> 管理，不需在此設定。
      </div>
    </div>
  )
}
