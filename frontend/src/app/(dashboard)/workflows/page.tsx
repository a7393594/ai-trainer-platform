'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

export default function WorkflowsPage() {
  const [projectId, setProjectId] = useState('')
  const [workflows, setWorkflows] = useState<any[]>([])
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [trigger, setTrigger] = useState('')
  const [steps, setSteps] = useState('[\n  {\n    "id": "step_1",\n    "action": "show_widget",\n    "widget": { "type": "confirm", "question": "Continue?" }\n  }\n]')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getDemoContext().then((ctx) => {
      setProjectId(ctx.project_id)
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
    let stepsJson = []
    try { stepsJson = JSON.parse(steps) } catch { return }
    await fetch(`${AI}/api/v1/workflows`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, name, trigger_description: trigger, steps: stepsJson }),
    })
    setName(''); setTrigger(''); setShowCreate(false)
    loadWorkflows(projectId)
  }

  const handleDelete = async (id: string) => {
    await fetch(`${AI}/api/v1/workflows/${id}`, { method: 'DELETE' })
    loadWorkflows(projectId)
  }

  if (loading) return <div className="flex h-full items-center justify-center bg-zinc-900"><div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" /></div>

  return (
    <div className="h-full bg-zinc-900 p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-lg font-medium text-zinc-200">Workflows</h1>
            <p className="text-xs text-zinc-500">Create multi-step automated processes</p>
          </div>
          <button onClick={() => setShowCreate(true)} className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500">Create Workflow</button>
        </div>

        {showCreate && (
          <div className="mb-6 rounded-lg border border-zinc-700 bg-zinc-800 p-4 space-y-3">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Workflow name" className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
            <input value={trigger} onChange={(e) => setTrigger(e.target.value)} placeholder="Trigger description (e.g., 'When user wants to register')" className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
            <textarea value={steps} onChange={(e) => setSteps(e.target.value)} rows={8} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-xs font-mono text-zinc-200 outline-none" />
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowCreate(false)} className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300">Cancel</button>
              <button onClick={handleCreate} disabled={!name.trim() || !trigger.trim()} className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white disabled:opacity-50">Create</button>
            </div>
          </div>
        )}

        <div className="space-y-2">
          {workflows.map((wf) => {
            const stepCount = Array.isArray(wf.steps_json) ? wf.steps_json.length : 0
            return (
              <div key={wf.id} className="flex items-center justify-between rounded-lg border border-zinc-700 bg-zinc-800/50 px-4 py-3">
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm text-zinc-200">{wf.name}</p>
                    <span className="rounded bg-green-500/20 px-1.5 py-0.5 text-[10px] text-green-400">Active</span>
                    <span className="text-[10px] text-zinc-500">{stepCount} steps</span>
                  </div>
                  <p className="text-xs text-zinc-400 mt-1">{wf.trigger_description}</p>
                </div>
                <button onClick={() => handleDelete(wf.id)} className="text-xs text-red-400 hover:text-red-300">Delete</button>
              </div>
            )
          })}
          {workflows.length === 0 && <p className="text-sm text-zinc-500 text-center py-12">No workflows yet. Create one to automate multi-step processes.</p>}
        </div>
      </div>
    </div>
  )
}
