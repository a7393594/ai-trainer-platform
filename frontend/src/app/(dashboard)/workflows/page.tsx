'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

type TabKey = 'list' | 'runs'

const STEP_TEMPLATES = [
  { id: '', action: 'show_widget', label: 'Show Widget', widget: { type: 'confirm', question: '' } },
  { id: '', action: 'collect_input', label: 'Collect Input', widget: { type: 'form', fields: [] } },
  { id: '', action: 'api_call', label: 'API Call', config: { url: '', method: 'POST' } },
  { id: '', action: 'condition', label: 'Condition', config: { field: '', operator: '==', value: '' } },
]

export default function WorkflowsPage() {
  const [projectId, setProjectId] = useState('')
  const [userId, setUserId] = useState('')
  const [tab, setTab] = useState<TabKey>('list')
  const [workflows, setWorkflows] = useState<any[]>([])
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [trigger, setTrigger] = useState('')
  const [steps, setSteps] = useState<any[]>([{ id: 'step_1', action: 'show_widget', widget: { type: 'confirm', question: 'Continue?' } }])
  const [loading, setLoading] = useState(true)
  const [expandedWf, setExpandedWf] = useState<string | null>(null)
  const [wfRuns, setWfRuns] = useState<any[]>([])
  const [testingWf, setTestingWf] = useState<string | null>(null)
  const [testRun, setTestRun] = useState<any>(null)
  const { t } = useI18n()

  useEffect(() => {
    getDemoContext().then((ctx) => {
      setProjectId(ctx.project_id)
      setUserId(ctx.user_id)
      loadWorkflows(ctx.project_id)
    }).catch(() => setLoading(false))
  }, [])

  const loadWorkflows = async (pid: string) => {
    const r = await fetch(`${AI}/api/v1/workflows/${pid}`)
    const d = await r.json()
    setWorkflows(d.workflows || [])
    setLoading(false)
  }

  const handleCreate = async () => {
    if (!name.trim() || !trigger.trim()) return
    await fetch(`${AI}/api/v1/workflows`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, name, trigger_description: trigger, steps }),
    })
    setName(''); setTrigger(''); setSteps([{ id: 'step_1', action: 'show_widget', widget: { type: 'confirm', question: 'Continue?' } }])
    setShowCreate(false)
    loadWorkflows(projectId)
  }

  const handleDelete = async (id: string) => {
    await fetch(`${AI}/api/v1/workflows/${id}`, { method: 'DELETE' })
    loadWorkflows(projectId)
  }

  const addStep = () => {
    const idx = steps.length + 1
    setSteps([...steps, { id: `step_${idx}`, action: 'show_widget', widget: { type: 'confirm', question: '' } }])
  }

  const removeStep = (idx: number) => {
    setSteps(steps.filter((_, i) => i !== idx))
  }

  const updateStep = (idx: number, field: string, value: any) => {
    const updated = [...steps]
    updated[idx] = { ...updated[idx], [field]: value }
    setSteps(updated)
  }

  const loadRuns = async (wfId: string) => {
    if (expandedWf === wfId) { setExpandedWf(null); return }
    const r = await fetch(`${AI}/api/v1/workflows/${wfId}/runs`)
    const d = await r.json()
    setWfRuns(d.runs || [])
    setExpandedWf(wfId)
  }

  const handleTestRun = async (wfId: string) => {
    setTestingWf(wfId)
    try {
      const r = await fetch(`${AI}/api/v1/workflows/${wfId}/start`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: '', user_id: userId }),
      })
      const d = await r.json()
      setTestRun(d)
    } catch {}
    setTestingWf(null)
  }

  const handleAdvance = async () => {
    if (!testRun?.run_id) return
    try {
      const r = await fetch(`${AI}/api/v1/workflows/runs/${testRun.run_id}/advance`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ step_result: { completed: true } }),
      })
      const d = await r.json()
      setTestRun(d.status === 'completed' ? { ...d, done: true } : d)
    } catch {}
  }

  if (loading) return <div className="flex h-full items-center justify-center bg-zinc-900"><div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" /></div>

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-auto">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-lg font-medium text-zinc-200">{t('workflows.title')}</h1>
            <p className="text-xs text-zinc-500">{t('workflows.desc')}</p>
          </div>
          <button onClick={() => setShowCreate(true)} className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500">{t('workflows.create')}</button>
        </div>

        {/* Create Form with Step Builder */}
        {showCreate && (
          <div className="mb-6 rounded-lg border border-zinc-700 bg-zinc-800 p-4 space-y-3">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t('workflows.wfName')} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
            <input value={trigger} onChange={(e) => setTrigger(e.target.value)} placeholder={t('workflows.trigger')} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />

            <div>
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs text-zinc-400 font-medium">{t('workflows.steps')}</p>
                <button onClick={addStep} className="text-xs text-blue-400 hover:text-blue-300">+ {t('workflows.addStep')}</button>
              </div>
              <div className="space-y-2">
                {steps.map((step, idx) => (
                  <div key={idx} className="flex items-start gap-2 rounded border border-zinc-600 bg-zinc-700/50 p-2">
                    <span className="text-[10px] text-zinc-500 mt-2 w-4">{idx + 1}</span>
                    <div className="flex-1 space-y-1">
                      <div className="flex gap-2">
                        <select value={step.action} onChange={(e) => updateStep(idx, 'action', e.target.value)}
                          className="rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 outline-none">
                          <option value="show_widget">Show Widget</option>
                          <option value="collect_input">Collect Input</option>
                          <option value="api_call">API Call</option>
                          <option value="condition">Condition</option>
                        </select>
                        <input value={step.id} onChange={(e) => updateStep(idx, 'id', e.target.value)}
                          placeholder="step_id" className="flex-1 rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 outline-none" />
                      </div>
                      {step.action === 'show_widget' && (
                        <input value={step.widget?.question || ''} onChange={(e) => updateStep(idx, 'widget', { ...step.widget, question: e.target.value })}
                          placeholder="Widget question" className="w-full rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 outline-none" />
                      )}
                      {step.action === 'api_call' && (
                        <input value={step.config?.url || ''} onChange={(e) => updateStep(idx, 'config', { ...step.config, url: e.target.value })}
                          placeholder="API URL" className="w-full rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 outline-none" />
                      )}
                    </div>
                    <button onClick={() => removeStep(idx)} className="text-xs text-red-400 hover:text-red-300 mt-2">x</button>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowCreate(false)} className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300">Cancel</button>
              <button onClick={handleCreate} disabled={!name.trim() || !trigger.trim()} className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white disabled:opacity-50">{t('workflows.create')}</button>
            </div>
          </div>
        )}

        {/* Test Run Panel */}
        {testRun && (
          <div className="mb-4 rounded-lg border border-blue-500/30 bg-blue-500/5 p-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm text-blue-300 font-medium">{t('workflows.testRun')}</h3>
              <button onClick={() => setTestRun(null)} className="text-xs text-zinc-400 hover:text-zinc-200">x</button>
            </div>
            {testRun.done ? (
              <p className="text-xs text-green-400">{t('workflows.completed')}</p>
            ) : (
              <div className="space-y-2">
                <p className="text-xs text-zinc-300">{t('workflows.currentStep')}: <span className="text-blue-400">{testRun.current_step?.id || testRun.current_step}</span></p>
                {testRun.current_step?.widget && (
                  <p className="text-xs text-zinc-400">{testRun.current_step.widget.question}</p>
                )}
                <div className="flex gap-2">
                  <button onClick={handleAdvance} className="rounded bg-green-600 px-3 py-1 text-xs text-white hover:bg-green-500">{t('workflows.nextStep')}</button>
                </div>
                {testRun.step_index != null && testRun.total_steps && (
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-1.5 bg-zinc-700 rounded-full overflow-hidden">
                      <div className="h-full bg-blue-500 rounded-full" style={{ width: `${((testRun.step_index + 1) / testRun.total_steps) * 100}%` }} />
                    </div>
                    <span className="text-[10px] text-zinc-500">{testRun.step_index + 1}/{testRun.total_steps}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Workflow List */}
        <div className="space-y-2">
          {workflows.map((wf) => {
            const stepCount = Array.isArray(wf.steps_json) ? wf.steps_json.length : 0
            return (
              <div key={wf.id} className="rounded-lg border border-zinc-700 bg-zinc-800/50">
                <div className="flex items-center justify-between px-4 py-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm text-zinc-200">{wf.name}</p>
                      <span className="rounded bg-green-500/20 px-1.5 py-0.5 text-[10px] text-green-400">Active</span>
                      <span className="text-[10px] text-zinc-500">{stepCount} {t('workflows.steps')}</span>
                    </div>
                    <p className="text-xs text-zinc-400 mt-1">{wf.trigger_description}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button onClick={() => handleTestRun(wf.id)} disabled={testingWf === wf.id} className="rounded bg-green-600/80 px-2 py-1 text-[10px] text-white hover:bg-green-500 disabled:opacity-50">{t('workflows.test')}</button>
                    <button onClick={() => loadRuns(wf.id)} className="text-[10px] text-zinc-400 hover:text-zinc-200">{t('workflows.history')}</button>
                    <button onClick={() => handleDelete(wf.id)} className="text-xs text-red-400 hover:text-red-300">{t('workflows.del')}</button>
                  </div>
                </div>
                {/* Expanded: Run History */}
                {expandedWf === wf.id && (
                  <div className="border-t border-zinc-700 px-4 py-3">
                    {wfRuns.length > 0 ? wfRuns.map((run) => (
                      <div key={run.id} className="flex items-center justify-between py-1.5 border-b border-zinc-700/50 last:border-0">
                        <div className="flex items-center gap-3">
                          <span className="text-xs text-zinc-400">{new Date(run.started_at).toLocaleString('zh-TW')}</span>
                          <span className={`rounded px-1.5 py-0.5 text-[10px] ${
                            run.status === 'completed' ? 'bg-green-500/20 text-green-400' :
                            run.status === 'running' || run.status === 'waiting_input' ? 'bg-blue-500/20 text-blue-400' :
                            'bg-zinc-600/20 text-zinc-400'
                          }`}>{run.status}</span>
                        </div>
                        <span className="text-[10px] text-zinc-500">{run.current_step || '-'}</span>
                      </div>
                    )) : (
                      <p className="text-xs text-zinc-500 text-center py-4">{t('workflows.noRuns')}</p>
                    )}
                  </div>
                )}
              </div>
            )
          })}
          {workflows.length === 0 && <p className="text-sm text-zinc-500 text-center py-12">{t('workflows.empty')}</p>}
        </div>
      </div>
    </div>
  )
}
