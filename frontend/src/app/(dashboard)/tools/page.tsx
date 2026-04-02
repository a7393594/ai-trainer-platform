'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'
const TOOL_TYPES = ['api_call', 'db_query', 'webhook', 'internal_fn', 'mcp_server']
const TYPE_COLORS: Record<string, string> = {
  api_call: 'bg-blue-500/20 text-blue-400',
  db_query: 'bg-green-500/20 text-green-400',
  webhook: 'bg-yellow-500/20 text-yellow-400',
  internal_fn: 'bg-purple-500/20 text-purple-400',
  mcp_server: 'bg-cyan-500/20 text-cyan-400',
}

export default function ToolsPage() {
  const [tenantId, setTenantId] = useState('')
  const [tools, setTools] = useState<any[]>([])
  const [showAdd, setShowAdd] = useState(false)
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [toolType, setToolType] = useState('api_call')
  const [config, setConfig] = useState('{\n  "method": "GET",\n  "url": "https://api.example.com/data"\n}')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getDemoContext().then((ctx) => {
      setTenantId(ctx.tenant_id)
      loadTools(ctx.tenant_id)
    }).catch(() => setLoading(false))
  }, [])

  const loadTools = async (tid: string) => {
    const r = await fetch(`${AI}/api/v1/tools/${tid}`)
    const d = await r.json()
    setTools(d.tools || [])
    setLoading(false)
  }

  const handleRegister = async () => {
    if (!name.trim()) return
    let configJson = {}
    try { configJson = JSON.parse(config) } catch { return }
    await fetch(`${AI}/api/v1/tools`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description: desc, tool_type: toolType, config_json: configJson }),
    })
    setName(''); setDesc(''); setShowAdd(false)
    loadTools(tenantId)
  }

  const handleDelete = async (id: string) => {
    await fetch(`${AI}/api/v1/tools/${id}`, { method: 'DELETE' })
    loadTools(tenantId)
  }

  const handleTest = async (id: string) => {
    const r = await fetch(`${AI}/api/v1/tools/${id}/test`, { method: 'POST' })
    const d = await r.json()
    alert(JSON.stringify(d, null, 2))
  }

  if (loading) return <div className="flex h-full items-center justify-center bg-zinc-900"><div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" /></div>

  return (
    <div className="h-full bg-zinc-900 p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-lg font-medium text-zinc-200">Tool Registry</h1>
            <p className="text-xs text-zinc-500">Register and manage external tools for your AI agent</p>
          </div>
          <button onClick={() => setShowAdd(true)} className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500">Register Tool</button>
        </div>

        {showAdd && (
          <div className="mb-6 rounded-lg border border-zinc-700 bg-zinc-800 p-4 space-y-3">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Tool name" className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
            <input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Description" className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
            <select value={toolType} onChange={(e) => setToolType(e.target.value)} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none">
              {TOOL_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <textarea value={config} onChange={(e) => setConfig(e.target.value)} rows={5} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-xs font-mono text-zinc-200 outline-none" />
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowAdd(false)} className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300">Cancel</button>
              <button onClick={handleRegister} disabled={!name.trim()} className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white disabled:opacity-50">Register</button>
            </div>
          </div>
        )}

        <div className="space-y-2">
          {tools.map((tool) => (
            <div key={tool.id} className="flex items-center justify-between rounded-lg border border-zinc-700 bg-zinc-800/50 px-4 py-3">
              <div>
                <div className="flex items-center gap-2">
                  <p className="text-sm text-zinc-200">{tool.name}</p>
                  <span className={`rounded px-1.5 py-0.5 text-[10px] ${TYPE_COLORS[tool.tool_type] || ''}`}>{tool.tool_type}</span>
                </div>
                {tool.description && <p className="text-xs text-zinc-400 mt-1">{tool.description}</p>}
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => handleTest(tool.id)} className="text-xs text-blue-400 hover:text-blue-300">Test</button>
                <button onClick={() => handleDelete(tool.id)} className="text-xs text-red-400 hover:text-red-300">Delete</button>
              </div>
            </div>
          ))}
          {tools.length === 0 && <p className="text-sm text-zinc-500 text-center py-12">No tools registered. Add one to extend your AI's capabilities.</p>}
        </div>
      </div>
    </div>
  )
}
