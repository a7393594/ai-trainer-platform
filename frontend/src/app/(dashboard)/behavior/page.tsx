'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

type Tab = 'capabilities' | 'workflows'

export default function BehaviorPage() {
  const [projectId, setProjectId] = useState('')
  const [userId, setUserId] = useState('')
  const [tab, setTab] = useState<Tab>('capabilities')
  const [loading, setLoading] = useState(true)

  // Capabilities state
  const [rules, setRules] = useState<any[]>([])
  const [showCapForm, setShowCapForm] = useState(false)
  const [capTrigger, setCapTrigger] = useState('')
  const [capKeywords, setCapKeywords] = useState('')
  const [capActionType, setCapActionType] = useState('widget')
  const [capPriority, setCapPriority] = useState(0)

  // Workflows state
  const [workflows, setWorkflows] = useState<any[]>([])
  const [showWfForm, setShowWfForm] = useState(false)
  const [wfName, setWfName] = useState('')
  const [wfTrigger, setWfTrigger] = useState('')
  const [wfSteps, setWfSteps] = useState([{ id: 'step_1', action: 'show_widget', widget: { type: 'confirm', question: '' } }])
  const [testRun, setTestRun] = useState<any>(null)
  const [expandedWf, setExpandedWf] = useState<string | null>(null)
  const [wfRuns, setWfRuns] = useState<any[]>([])

  const { t } = useI18n()

  useEffect(() => {
    getDemoContext().then(ctx => {
      setProjectId(ctx.project_id)
      setUserId(ctx.user_id)
      loadRules(ctx.project_id)
      loadWorkflows(ctx.project_id)
    }).catch(() => setLoading(false))
  }, [])

  // === Capabilities ===
  const loadRules = async (pid: string) => {
    const r = await fetch(`${AI}/api/v1/capabilities/${pid}`)
    setRules((await r.json()).rules || [])
    setLoading(false)
  }

  const handleCreateRule = async () => {
    if (!capTrigger.trim()) return
    await fetch(`${AI}/api/v1/capabilities`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: projectId, trigger_description: capTrigger,
        trigger_keywords: capKeywords.split(',').map(k => k.trim()).filter(Boolean),
        action_type: capActionType, action_config: {}, priority: capPriority,
      }),
    })
    setCapTrigger(''); setCapKeywords(''); setShowCapForm(false)
    loadRules(projectId)
  }

  const handleToggleRule = async (ruleId: string, isActive: boolean) => {
    if (isActive) {
      await fetch(`${AI}/api/v1/capabilities/${ruleId}`, { method: 'DELETE' })
    }
    loadRules(projectId)
  }

  // === Workflows ===
  const loadWorkflows = async (pid: string) => {
    const r = await fetch(`${AI}/api/v1/workflows/${pid}`)
    setWorkflows((await r.json()).workflows || [])
  }

  const handleCreateWf = async () => {
    if (!wfName.trim() || !wfTrigger.trim()) return
    await fetch(`${AI}/api/v1/workflows`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, name: wfName, trigger_description: wfTrigger, steps: wfSteps }),
    })
    setWfName(''); setWfTrigger(''); setShowWfForm(false)
    loadWorkflows(projectId)
  }

  const handleTestWf = async (wfId: string) => {
    const r = await fetch(`${AI}/api/v1/workflows/${wfId}/start`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: '', user_id: userId }),
    })
    setTestRun(await r.json())
  }

  const handleAdvance = async () => {
    if (!testRun?.run_id) return
    const r = await fetch(`${AI}/api/v1/workflows/runs/${testRun.run_id}/advance`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ step_result: { completed: true } }),
    })
    const d = await r.json()
    setTestRun(d.status === 'completed' ? { ...d, done: true } : d)
  }

  const loadRuns = async (wfId: string) => {
    if (expandedWf === wfId) { setExpandedWf(null); return }
    const r = await fetch(`${AI}/api/v1/workflows/${wfId}/runs`)
    setWfRuns((await r.json()).runs || [])
    setExpandedWf(wfId)
  }

  const handleDeleteWf = async (id: string) => {
    await fetch(`${AI}/api/v1/workflows/${id}`, { method: 'DELETE' })
    loadWorkflows(projectId)
  }

  if (loading) return <div className="flex h-full items-center justify-center bg-zinc-900"><div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" /></div>

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-auto">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-lg font-medium text-zinc-200 mb-1">{t('behavior.title')}</h1>
        <p className="text-xs text-zinc-500 mb-4">{t('behavior.desc')}</p>

        <div className="flex gap-1 mb-4">
          <button onClick={() => setTab('capabilities')} className={`px-4 py-1.5 rounded text-xs ${tab === 'capabilities' ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400'}`}>{t('behavior.capabilities')}</button>
          <button onClick={() => setTab('workflows')} className={`px-4 py-1.5 rounded text-xs ${tab === 'workflows' ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400'}`}>{t('behavior.workflows')}</button>
        </div>

        {/* Capabilities Tab */}
        {tab === 'capabilities' && (
          <div className="space-y-3">
            <div className="flex justify-end">
              <button onClick={() => setShowCapForm(true)} className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white">{t('behavior.addCapability')}</button>
            </div>

            {showCapForm && (
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4 space-y-3">
                <input value={capTrigger} onChange={e => setCapTrigger(e.target.value)} placeholder={t('behavior.scenarioDesc')} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
                <input value={capKeywords} onChange={e => setCapKeywords(e.target.value)} placeholder={t('behavior.keywords')} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
                <div className="flex gap-2 justify-end">
                  <button onClick={() => setShowCapForm(false)} className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300">Cancel</button>
                  <button onClick={handleCreateRule} className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white">{t('behavior.save')}</button>
                </div>
              </div>
            )}

            {rules.map(rule => (
              <div key={rule.id} className="rounded-lg border border-zinc-700 bg-zinc-800/50 px-4 py-3">
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="w-2 h-2 rounded-full bg-green-500" title="Active" />
                      <span className={`rounded px-1.5 py-0.5 text-[10px] ${rule.action_type === 'widget' ? 'bg-purple-500/20 text-purple-400' : rule.action_type === 'tool_call' ? 'bg-blue-500/20 text-blue-400' : rule.action_type === 'workflow' ? 'bg-orange-500/20 text-orange-400' : 'bg-zinc-600/20 text-zinc-400'}`}>{rule.action_type}</span>
                      <span className="text-[10px] text-zinc-500">P{rule.priority}</span>
                    </div>
                    <p className="text-sm text-zinc-200">{rule.trigger_description}</p>
                    {rule.trigger_keywords?.length > 0 && (
                      <div className="flex gap-1 mt-1 flex-wrap">
                        {rule.trigger_keywords.map((kw: string, i: number) => (
                          <span key={i} className="rounded bg-zinc-700 px-1.5 py-0.5 text-[10px] text-zinc-400">{kw}</span>
                        ))}
                      </div>
                    )}
                  </div>
                  <button onClick={() => handleToggleRule(rule.id, true)} className="text-xs text-red-400 hover:text-red-300 ml-3">{t('behavior.disable')}</button>
                </div>
                {/* Impact preview */}
                <div className="mt-2 rounded bg-zinc-900/50 px-3 py-1.5 text-[10px] text-zinc-500 border-l-2 border-blue-500/30">
                  💡 {rule.action_type === 'widget' && t('behavior.impactWidget')}
                  {rule.action_type === 'tool_call' && t('behavior.impactTool')}
                  {rule.action_type === 'workflow' && t('behavior.impactWorkflow')}
                  {rule.action_type === 'composite' && t('behavior.impactComposite')}
                </div>
              </div>
            ))}
            {rules.length === 0 && <p className="text-sm text-zinc-500 text-center py-12">{t('behavior.noCapabilities')}</p>}
          </div>
        )}

        {/* Workflows Tab */}
        {tab === 'workflows' && (
          <div className="space-y-3">
            <div className="flex justify-end">
              <button onClick={() => setShowWfForm(true)} className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white">{t('behavior.addWorkflow')}</button>
            </div>

            {showWfForm && (
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4 space-y-3">
                <input value={wfName} onChange={e => setWfName(e.target.value)} placeholder={t('behavior.wfName')} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
                <input value={wfTrigger} onChange={e => setWfTrigger(e.target.value)} placeholder={t('behavior.wfTrigger')} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
                <div className="flex gap-2 justify-end">
                  <button onClick={() => setShowWfForm(false)} className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300">Cancel</button>
                  <button onClick={handleCreateWf} className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white">{t('behavior.save')}</button>
                </div>
              </div>
            )}

            {/* Test Run Panel */}
            {testRun && (
              <div className="rounded-lg border border-blue-500/30 bg-blue-500/5 p-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm text-blue-300 font-medium">{t('behavior.testRun')}</h3>
                  <button onClick={() => setTestRun(null)} className="text-xs text-zinc-400">✕</button>
                </div>
                {testRun.done ? (
                  <p className="text-xs text-green-400">{t('behavior.completed')}</p>
                ) : (
                  <div className="space-y-2">
                    <p className="text-xs text-zinc-300">{t('behavior.currentStep')}: <span className="text-blue-400">{testRun.current_step?.id}</span></p>
                    <button onClick={handleAdvance} className="rounded bg-green-600 px-3 py-1 text-xs text-white">{t('behavior.nextStep')}</button>
                  </div>
                )}
              </div>
            )}

            {workflows.map(wf => (
              <div key={wf.id} className="rounded-lg border border-zinc-700 bg-zinc-800/50">
                <div className="flex items-center justify-between px-4 py-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-zinc-200">{wf.name}</span>
                      <span className="rounded bg-green-500/20 px-1.5 py-0.5 text-[10px] text-green-400">Active</span>
                      <span className="text-[10px] text-zinc-500">{Array.isArray(wf.steps_json) ? wf.steps_json.length : 0} steps</span>
                    </div>
                    <p className="text-xs text-zinc-400 mt-1">{wf.trigger_description}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button onClick={() => handleTestWf(wf.id)} className="rounded bg-green-600/80 px-2 py-1 text-[10px] text-white">{t('behavior.test')}</button>
                    <button onClick={() => loadRuns(wf.id)} className="text-[10px] text-zinc-400 hover:text-zinc-200">{t('behavior.history')}</button>
                    <button onClick={() => handleDeleteWf(wf.id)} className="text-xs text-red-400">✕</button>
                  </div>
                </div>
                {expandedWf === wf.id && (
                  <div className="border-t border-zinc-700 px-4 py-3">
                    {wfRuns.length > 0 ? wfRuns.map(run => (
                      <div key={run.id} className="flex items-center justify-between py-1.5 border-b border-zinc-700/50 last:border-0">
                        <span className="text-xs text-zinc-400">{new Date(run.started_at).toLocaleString('zh-TW')}</span>
                        <span className={`rounded px-1.5 py-0.5 text-[10px] ${run.status === 'completed' ? 'bg-green-500/20 text-green-400' : 'bg-blue-500/20 text-blue-400'}`}>{run.status}</span>
                      </div>
                    )) : <p className="text-xs text-zinc-500 text-center py-4">{t('behavior.noRuns')}</p>}
                  </div>
                )}
              </div>
            ))}
            {workflows.length === 0 && <p className="text-sm text-zinc-500 text-center py-12">{t('behavior.noWorkflows')}</p>}
          </div>
        )}
      </div>
    </div>
  )
}
