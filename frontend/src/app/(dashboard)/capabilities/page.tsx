'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

const ACTION_TYPES = [
  { value: 'widget', label: 'Widget（互動元件）' },
  { value: 'tool_call', label: 'Tool Call（工具調用）' },
  { value: 'workflow', label: 'Workflow（工作流）' },
  { value: 'composite', label: 'Composite（複合）' },
]

const WIDGET_TYPES = ['single_select', 'multi_select', 'rank', 'confirm', 'form', 'slider']

export default function CapabilitiesPage() {
  const [projectId, setProjectId] = useState('')
  const [rules, setRules] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)

  // Form state
  const [trigger, setTrigger] = useState('')
  const [keywords, setKeywords] = useState('')
  const [actionType, setActionType] = useState('widget')
  const [priority, setPriority] = useState(0)
  const [actionConfig, setActionConfig] = useState('{}')

  // Widget builder state
  const [widgetType, setWidgetType] = useState('single_select')
  const [widgetQuestion, setWidgetQuestion] = useState('')
  const [widgetOptions, setWidgetOptions] = useState([{ id: 'a', label: '' }])
  const [widgetText, setWidgetText] = useState('')

  // Test state
  const [testMsg, setTestMsg] = useState('')
  const [testResult, setTestResult] = useState<any>(null)

  const { t } = useI18n()

  useEffect(() => {
    getDemoContext().then((ctx) => {
      setProjectId(ctx.project_id)
      loadRules(ctx.project_id)
    }).catch(() => setLoading(false))
  }, [])

  const loadRules = async (pid: string) => {
    const r = await fetch(`${AI}/api/v1/capabilities/${pid}`)
    const d = await r.json()
    setRules(d.rules || [])
    setLoading(false)
  }

  const buildActionConfig = () => {
    if (actionType === 'widget') {
      return {
        text: widgetText || '',
        widget: {
          widget_type: widgetType,
          question: widgetQuestion,
          options: widgetOptions.filter(o => o.label.trim()),
          config: {},
          allow_skip: false,
        },
      }
    }
    try { return JSON.parse(actionConfig) } catch { return {} }
  }

  const handleCreate = async () => {
    if (!trigger.trim()) return
    const config = buildActionConfig()
    await fetch(`${AI}/api/v1/capabilities`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: projectId,
        trigger_description: trigger,
        trigger_keywords: keywords.split(',').map(k => k.trim()).filter(Boolean),
        action_type: actionType,
        action_config: config,
        priority,
      }),
    })
    resetForm()
    loadRules(projectId)
  }

  const handleUpdate = async () => {
    if (!editingId) return
    const config = buildActionConfig()
    await fetch(`${AI}/api/v1/capabilities/${editingId}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        trigger_description: trigger,
        trigger_keywords: keywords.split(',').map(k => k.trim()).filter(Boolean),
        action_type: actionType,
        action_config: config,
        priority,
      }),
    })
    resetForm()
    loadRules(projectId)
  }

  const handleDelete = async (id: string) => {
    await fetch(`${AI}/api/v1/capabilities/${id}`, { method: 'DELETE' })
    loadRules(projectId)
  }

  const handleEdit = (rule: any) => {
    setEditingId(rule.id)
    setTrigger(rule.trigger_description || '')
    setKeywords((rule.trigger_keywords || []).join(', '))
    setActionType(rule.action_type || 'widget')
    setPriority(rule.priority || 0)
    if (rule.action_type === 'widget' && rule.action_config?.widget) {
      setWidgetType(rule.action_config.widget.widget_type || 'single_select')
      setWidgetQuestion(rule.action_config.widget.question || '')
      setWidgetOptions(rule.action_config.widget.options || [{ id: 'a', label: '' }])
      setWidgetText(rule.action_config.text || '')
    } else {
      setActionConfig(JSON.stringify(rule.action_config || {}, null, 2))
    }
    setShowCreate(true)
  }

  const resetForm = () => {
    setShowCreate(false); setEditingId(null)
    setTrigger(''); setKeywords(''); setActionType('widget'); setPriority(0)
    setWidgetType('single_select'); setWidgetQuestion(''); setWidgetOptions([{ id: 'a', label: '' }]); setWidgetText('')
    setActionConfig('{}')
  }

  const handleTest = async () => {
    if (!testMsg.trim()) return
    const r = await fetch(`${AI}/api/v1/capabilities/classify`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, message: testMsg }),
    })
    setTestResult(await r.json())
  }

  const addOption = () => {
    const next = String.fromCharCode(97 + widgetOptions.length) // a, b, c, d...
    setWidgetOptions([...widgetOptions, { id: next, label: '' }])
  }

  const updateOption = (idx: number, label: string) => {
    const updated = [...widgetOptions]
    updated[idx] = { ...updated[idx], label }
    setWidgetOptions(updated)
  }

  const removeOption = (idx: number) => {
    setWidgetOptions(widgetOptions.filter((_, i) => i !== idx))
  }

  if (loading) return <div className="flex h-full items-center justify-center bg-zinc-900"><div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" /></div>

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-auto">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-lg font-medium text-zinc-200">{t('capabilities.title')}</h1>
            <p className="text-xs text-zinc-500">{t('capabilities.desc')}</p>
          </div>
          <button onClick={() => { resetForm(); setShowCreate(true) }} className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500">
            {t('capabilities.create')}
          </button>
        </div>

        {/* Create / Edit Form */}
        {showCreate && (
          <div className="mb-6 rounded-lg border border-zinc-700 bg-zinc-800 p-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] text-zinc-400 mb-1 block">{t('capabilities.trigger')}</label>
                <input value={trigger} onChange={(e) => setTrigger(e.target.value)} placeholder="當使用者想要測試撲克水平時..." className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
              </div>
              <div>
                <label className="text-[10px] text-zinc-400 mb-1 block">{t('capabilities.keywords')}</label>
                <input value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="測試, 水平, 評估, quiz" className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] text-zinc-400 mb-1 block">{t('capabilities.actionType')}</label>
                <select value={actionType} onChange={(e) => setActionType(e.target.value)} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none">
                  {ACTION_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[10px] text-zinc-400 mb-1 block">{t('capabilities.priority')}</label>
                <input type="number" value={priority} onChange={(e) => setPriority(Number(e.target.value))} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
              </div>
            </div>

            {/* Widget Builder */}
            {actionType === 'widget' && (
              <div className="rounded border border-zinc-600 bg-zinc-700/30 p-3 space-y-2">
                <label className="text-[10px] text-zinc-400 block">{t('capabilities.widgetBuilder')}</label>
                <div className="grid grid-cols-2 gap-2">
                  <select value={widgetType} onChange={(e) => setWidgetType(e.target.value)} className="rounded border border-zinc-600 bg-zinc-700 px-2 py-1.5 text-xs text-zinc-200 outline-none">
                    {WIDGET_TYPES.map(w => <option key={w} value={w}>{w}</option>)}
                  </select>
                  <input value={widgetQuestion} onChange={(e) => setWidgetQuestion(e.target.value)} placeholder="Widget 問題文字" className="rounded border border-zinc-600 bg-zinc-700 px-2 py-1.5 text-xs text-zinc-200 outline-none" />
                </div>
                {(widgetType === 'single_select' || widgetType === 'multi_select' || widgetType === 'rank') && (
                  <div className="space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-zinc-400">{t('capabilities.options')}</span>
                      <button onClick={addOption} className="text-[10px] text-blue-400 hover:text-blue-300">+ 選項</button>
                    </div>
                    {widgetOptions.map((opt, i) => (
                      <div key={i} className="flex gap-1">
                        <span className="text-[10px] text-zinc-500 w-4 mt-1.5">{opt.id}</span>
                        <input value={opt.label} onChange={(e) => updateOption(i, e.target.value)} placeholder={`選項 ${opt.id.toUpperCase()}`} className="flex-1 rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 outline-none" />
                        <button onClick={() => removeOption(i)} className="text-xs text-red-400">×</button>
                      </div>
                    ))}
                  </div>
                )}
                <input value={widgetText} onChange={(e) => setWidgetText(e.target.value)} placeholder="附帶文字回覆（選填，空白則由 AI 生成）" className="w-full rounded border border-zinc-600 bg-zinc-700 px-2 py-1.5 text-xs text-zinc-200 outline-none" />
              </div>
            )}

            {/* JSON config for non-widget */}
            {actionType !== 'widget' && (
              <div>
                <label className="text-[10px] text-zinc-400 mb-1 block">Action Config (JSON)</label>
                <textarea value={actionConfig} onChange={(e) => setActionConfig(e.target.value)} rows={4} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-xs font-mono text-zinc-200 outline-none" />
              </div>
            )}

            <div className="flex gap-2 justify-end">
              <button onClick={resetForm} className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300">Cancel</button>
              <button onClick={editingId ? handleUpdate : handleCreate} disabled={!trigger.trim()} className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white disabled:opacity-50">
                {editingId ? t('capabilities.update') : t('capabilities.create')}
              </button>
            </div>
          </div>
        )}

        {/* Test Intent Classification */}
        <div className="mb-4 rounded-lg border border-zinc-700 bg-zinc-800 p-3">
          <div className="flex gap-2">
            <input value={testMsg} onChange={(e) => setTestMsg(e.target.value)} placeholder={t('capabilities.testPlaceholder')} className="flex-1 rounded border border-zinc-600 bg-zinc-700 px-3 py-1.5 text-sm text-zinc-200 outline-none" />
            <button onClick={handleTest} className="rounded bg-green-600 px-3 py-1.5 text-xs text-white hover:bg-green-500">{t('capabilities.test')}</button>
          </div>
          {testResult && (
            <div className="mt-2 rounded bg-zinc-700/30 p-2 text-xs">
              <div className="flex items-center gap-2">
                <span className={`rounded px-1.5 py-0.5 text-[10px] ${testResult.type === 'capability_rule' ? 'bg-green-500/20 text-green-400' : 'bg-zinc-600/20 text-zinc-400'}`}>
                  {testResult.type}
                </span>
                <span className="text-zinc-400">Confidence: {(testResult.confidence * 100).toFixed(0)}%</span>
                {testResult.matched_keywords?.length > 0 && (
                  <span className="text-zinc-500">Keywords: {testResult.matched_keywords.join(', ')}</span>
                )}
              </div>
              {testResult.rule && (
                <p className="text-zinc-300 mt-1 truncate">{testResult.rule.trigger_description}</p>
              )}
            </div>
          )}
        </div>

        {/* Rules List */}
        <div className="space-y-2">
          {rules.map((rule) => (
            <div key={rule.id} className="rounded-lg border border-zinc-700 bg-zinc-800/50 px-4 py-3">
              <div className="flex items-center justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] ${
                      rule.action_type === 'widget' ? 'bg-purple-500/20 text-purple-400' :
                      rule.action_type === 'tool_call' ? 'bg-blue-500/20 text-blue-400' :
                      rule.action_type === 'workflow' ? 'bg-orange-500/20 text-orange-400' :
                      'bg-zinc-600/20 text-zinc-400'
                    }`}>{rule.action_type}</span>
                    <span className="text-[10px] text-zinc-500">P{rule.priority}</span>
                  </div>
                  <p className="text-sm text-zinc-200 truncate">{rule.trigger_description}</p>
                  {rule.trigger_keywords?.length > 0 && (
                    <div className="flex gap-1 mt-1 flex-wrap">
                      {rule.trigger_keywords.map((kw: string, i: number) => (
                        <span key={i} className="rounded bg-zinc-700 px-1.5 py-0.5 text-[10px] text-zinc-400">{kw}</span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2 ml-3">
                  <button onClick={() => handleEdit(rule)} className="text-xs text-blue-400 hover:text-blue-300">{t('capabilities.edit')}</button>
                  <button onClick={() => handleDelete(rule.id)} className="text-xs text-red-400 hover:text-red-300">{t('capabilities.delete')}</button>
                </div>
              </div>
            </div>
          ))}
          {rules.length === 0 && <p className="text-sm text-zinc-500 text-center py-12">{t('capabilities.empty')}</p>}
        </div>
      </div>
    </div>
  )
}
