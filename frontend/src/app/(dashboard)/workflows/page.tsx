'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

type TabKey = 'list' | 'runs'

const TRACE_TYPE_COLOR: Record<string, string> = {
  action: 'bg-zinc-600/30 text-zinc-300',
  if: 'bg-amber-500/20 text-amber-300',
  parallel: 'bg-cyan-500/20 text-cyan-300',
  loop: 'bg-purple-500/20 text-purple-300',
}

function TraceView({ trace, vars, error }: { trace: any[]; vars: Record<string, any>; error?: string }) {
  return (
    <div className="border-t border-zinc-700 px-3 py-2 space-y-2">
      {error && (
        <div className="rounded border border-red-500/40 bg-red-500/5 px-2 py-1 text-[11px] text-red-300">
          {error}
        </div>
      )}
      <div>
        <p className="text-[10px] text-zinc-500 mb-1">Trace ({trace.length} steps)</p>
        {trace.length === 0 ? (
          <p className="text-[11px] text-zinc-500">no steps recorded</p>
        ) : (
          <div className="space-y-0.5">
            {trace.map((t, i) => (
              <div key={i} className="flex items-center gap-2 text-[11px]">
                <span className="text-zinc-600 font-mono w-6 text-right">{i + 1}.</span>
                <span className={`rounded px-1.5 py-0 text-[10px] ${TRACE_TYPE_COLOR[t.type] || 'bg-zinc-600/20 text-zinc-400'}`}>
                  {t.type}
                </span>
                <code className="text-zinc-300">{t.step}</code>
                {typeof t.branch === 'number' && (
                  <span className="text-cyan-400 text-[10px]">branch {t.branch}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
      {vars && Object.keys(vars).length > 0 && (
        <div>
          <p className="text-[10px] text-zinc-500 mb-1">Final vars</p>
          <pre className="max-h-40 overflow-auto rounded border border-zinc-700 bg-zinc-900/80 p-2 text-[10px] font-mono text-zinc-300">
            {JSON.stringify(vars, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}

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
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null)
  const [runDetails, setRunDetails] = useState<any>(null)
  const [testingWf, setTestingWf] = useState<string | null>(null)
  const [testRun, setTestRun] = useState<any>(null)
  const [autoRunningWf, setAutoRunningWf] = useState<string | null>(null)
  const [autoRunResult, setAutoRunResult] = useState<any>(null)
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

  const addBranchStep = (type: 'if' | 'parallel' | 'loop') => {
    const idx = steps.length + 1
    const id = `step_${idx}`
    if (type === 'if') {
      setSteps([...steps, { id, type: 'if', condition: 'x > 0', then: [], else: [] }])
    } else if (type === 'parallel') {
      setSteps([...steps, { id, type: 'parallel', branches: [[], []] }])
    } else {
      setSteps([...steps, { id, type: 'loop', mode: 'while', condition: 'i < 3', max_iterations: 10, body: [] }])
    }
  }

  const handleAutoRun = async (wfId: string) => {
    setAutoRunningWf(wfId)
    setAutoRunResult(null)
    try {
      const r = await fetch(`${AI}/api/v1/workflows/${wfId}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: '', user_id: userId, initial_vars: {} }),
      })
      setAutoRunResult(await r.json())
    } catch {
      /* ignore */
    }
    setAutoRunningWf(null)
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
    setExpandedRunId(null)
    setRunDetails(null)
  }

  const loadRunDetails = async (runId: string) => {
    if (expandedRunId === runId) { setExpandedRunId(null); setRunDetails(null); return }
    const r = await fetch(`${AI}/api/v1/workflows/runs/${runId}`)
    const d = await r.json()
    setRunDetails(d)
    setExpandedRunId(runId)
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
                <div className="flex gap-2">
                  <button onClick={addStep} className="text-xs text-blue-400 hover:text-blue-300">+ Action</button>
                  <button onClick={() => addBranchStep('if')} className="text-xs text-amber-400 hover:text-amber-300">+ If</button>
                  <button onClick={() => addBranchStep('parallel')} className="text-xs text-cyan-400 hover:text-cyan-300">+ Parallel</button>
                  <button onClick={() => addBranchStep('loop')} className="text-xs text-purple-400 hover:text-purple-300">+ Loop</button>
                </div>
              </div>
              <div className="space-y-2">
                {steps.map((step, idx) => {
                  const isBranch = step.type === 'if' || step.type === 'parallel' || step.type === 'loop'
                  const typeColor =
                    step.type === 'if' ? 'border-amber-600/60' :
                    step.type === 'parallel' ? 'border-cyan-600/60' :
                    step.type === 'loop' ? 'border-purple-600/60' :
                    'border-zinc-600'
                  return (
                    <div key={idx} className={`flex items-start gap-2 rounded border bg-zinc-700/50 p-2 ${typeColor}`}>
                      <span className="text-[10px] text-zinc-500 mt-2 w-4">{idx + 1}</span>
                      <div className="flex-1 space-y-1">
                        <div className="flex gap-2 items-center">
                          {isBranch ? (
                            <span className={`rounded px-2 py-1 text-[10px] font-medium ${
                              step.type === 'if' ? 'bg-amber-500/20 text-amber-300' :
                              step.type === 'parallel' ? 'bg-cyan-500/20 text-cyan-300' :
                              'bg-purple-500/20 text-purple-300'
                            }`}>{step.type}</span>
                          ) : (
                            <select value={step.action} onChange={(e) => updateStep(idx, 'action', e.target.value)}
                              className="rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 outline-none">
                              <option value="show_widget">Show Widget</option>
                              <option value="collect_input">Collect Input</option>
                              <option value="api_call">API Call</option>
                              <option value="condition">Condition</option>
                            </select>
                          )}
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
                        {step.type === 'if' && (
                          <input value={step.condition || ''} onChange={(e) => updateStep(idx, 'condition', e.target.value)}
                            placeholder="condition (e.g. x > 0)" className="w-full rounded border border-amber-600/40 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 outline-none font-mono" />
                        )}
                        {step.type === 'loop' && (
                          <div className="flex gap-2">
                            <select value={step.mode || 'while'} onChange={(e) => updateStep(idx, 'mode', e.target.value)}
                              className="rounded border border-purple-600/40 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 outline-none">
                              <option value="while">while</option>
                              <option value="foreach">foreach</option>
                            </select>
                            <input value={step.mode === 'foreach' ? (step.items_var || '') : (step.condition || '')}
                              onChange={(e) => updateStep(idx, step.mode === 'foreach' ? 'items_var' : 'condition', e.target.value)}
                              placeholder={step.mode === 'foreach' ? 'items_var' : 'condition'}
                              className="flex-1 rounded border border-purple-600/40 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 outline-none font-mono" />
                            <input type="number" value={step.max_iterations || 10}
                              onChange={(e) => updateStep(idx, 'max_iterations', Number(e.target.value))}
                              className="w-16 rounded border border-purple-600/40 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 outline-none" />
                          </div>
                        )}
                        {step.type === 'parallel' && (
                          <p className="text-[10px] text-cyan-400">{(step.branches || []).length} 條分支（建立後可在 JSON 編輯 body）</p>
                        )}
                      </div>
                      <button onClick={() => removeStep(idx)} className="text-xs text-red-400 hover:text-red-300 mt-2">x</button>
                    </div>
                  )
                })}
              </div>
            </div>

            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowCreate(false)} className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300">Cancel</button>
              <button onClick={handleCreate} disabled={!name.trim() || !trigger.trim()} className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white disabled:opacity-50">{t('workflows.create')}</button>
            </div>
          </div>
        )}

        {/* Auto-Run Result */}
        {autoRunResult && (
          <div className={`mb-4 rounded-lg border px-4 py-3 ${
            autoRunResult.status === 'completed' ? 'border-green-500/30 bg-green-500/5 text-green-300' :
            autoRunResult.status === 'failed' ? 'border-red-500/30 bg-red-500/5 text-red-300' :
            'border-zinc-700 bg-zinc-800 text-zinc-300'
          }`}>
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-sm font-medium">Auto-Run · {autoRunResult.status}</h3>
              <button onClick={() => setAutoRunResult(null)} className="text-xs opacity-70 hover:opacity-100">x</button>
            </div>
            <p className="text-[11px] opacity-80">run_id: <code>{autoRunResult.run_id}</code> · trace {autoRunResult.trace?.length || 0} steps</p>
            {autoRunResult.error && <p className="text-[11px] text-red-400 mt-1">{autoRunResult.error}</p>}
            {autoRunResult.vars && Object.keys(autoRunResult.vars).length > 0 && (
              <pre className="mt-2 max-h-32 overflow-auto rounded border border-current/20 bg-zinc-900/50 p-2 text-[10px] font-mono">
                {JSON.stringify(autoRunResult.vars, null, 2)}
              </pre>
            )}
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
                    <button onClick={() => handleAutoRun(wf.id)} disabled={autoRunningWf === wf.id} className="rounded bg-blue-600/80 px-2 py-1 text-[10px] text-white hover:bg-blue-500 disabled:opacity-50" title="跑到結束（支援 if/parallel/loop）">
                      {autoRunningWf === wf.id ? '…' : 'Auto-Run'}
                    </button>
                    <button onClick={() => loadRuns(wf.id)} className="text-[10px] text-zinc-400 hover:text-zinc-200">{t('workflows.history')}</button>
                    <button onClick={() => handleDelete(wf.id)} className="text-xs text-red-400 hover:text-red-300">{t('workflows.del')}</button>
                  </div>
                </div>
                {/* Expanded: Run History */}
                {expandedWf === wf.id && (
                  <div className="border-t border-zinc-700 px-4 py-3 space-y-1">
                    {wfRuns.length > 0 ? wfRuns.map((run) => {
                      const ctx = run.context_json || {}
                      const trace = Array.isArray(ctx._trace) ? ctx._trace : []
                      const vars = ctx.vars || {}
                      const isOpen = expandedRunId === run.id
                      return (
                        <div key={run.id} className="rounded border border-zinc-700/60 bg-zinc-800/40">
                          <button
                            onClick={() => loadRunDetails(run.id)}
                            className="w-full flex items-center justify-between py-1.5 px-2 text-left hover:bg-zinc-700/30"
                          >
                            <div className="flex items-center gap-3">
                              <span className="text-xs text-zinc-400">{new Date(run.started_at).toLocaleString('zh-TW')}</span>
                              <span className={`rounded px-1.5 py-0.5 text-[10px] ${
                                run.status === 'completed' ? 'bg-green-500/20 text-green-400' :
                                run.status === 'failed' ? 'bg-red-500/20 text-red-400' :
                                run.status === 'running' || run.status === 'waiting_input' ? 'bg-blue-500/20 text-blue-400' :
                                'bg-zinc-600/20 text-zinc-400'
                              }`}>{run.status}</span>
                              <span className="text-[10px] text-zinc-500">{trace.length || ctx._step_count || 0} steps</span>
                            </div>
                            <span className="text-zinc-600 text-[10px]">{isOpen ? '[-]' : '[+]'}</span>
                          </button>
                          {isOpen && runDetails?.id === run.id && (
                            <TraceView trace={((runDetails.context_json || {})._trace) || []} vars={(runDetails.context_json || {}).vars || {}} error={(runDetails.context_json || {})._error} />
                          )}
                        </div>
                      )
                    }) : (
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
