'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

type Tab = 'knowledge' | 'tools'

export default function EnhancePage() {
  const [projectId, setProjectId] = useState('')
  const [tenantId, setTenantId] = useState('')
  const [tab, setTab] = useState<Tab>('knowledge')
  const [loading, setLoading] = useState(true)

  // Knowledge state
  const [docs, setDocs] = useState<any[]>([])
  const [showUpload, setShowUpload] = useState(false)
  const [docTitle, setDocTitle] = useState('')
  const [docContent, setDocContent] = useState('')

  // Tools state
  const [tools, setTools] = useState<any[]>([])
  const [showToolForm, setShowToolForm] = useState(false)
  const [toolName, setToolName] = useState('')
  const [toolDesc, setToolDesc] = useState('')
  const [toolType, setToolType] = useState('api_call')
  const [toolConfig, setToolConfig] = useState('{}')

  const { t } = useI18n()

  useEffect(() => {
    getDemoContext().then(ctx => {
      setProjectId(ctx.project_id)
      setTenantId(ctx.tenant_id)
      loadDocs(ctx.project_id)
      loadTools(ctx.tenant_id)
    }).catch(() => setLoading(false))
  }, [])

  // === Knowledge ===
  const loadDocs = async (pid: string) => {
    const r = await fetch(`${AI}/api/v1/knowledge/${pid}`)
    setDocs((await r.json()).documents || [])
    setLoading(false)
  }

  const handleUpload = async () => {
    if (!docTitle.trim() || !docContent.trim()) return
    await fetch(`${AI}/api/v1/knowledge/upload`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, title: docTitle, content: docContent }),
    })
    setDocTitle(''); setDocContent(''); setShowUpload(false)
    loadDocs(projectId)
  }

  const handleDeleteDoc = async (docId: string) => {
    await fetch(`${AI}/api/v1/knowledge/${docId}`, { method: 'DELETE' })
    loadDocs(projectId)
  }

  // === Tools ===
  const loadTools = async (tid: string) => {
    const r = await fetch(`${AI}/api/v1/tools/${tid}`)
    setTools((await r.json()).tools || [])
  }

  const handleCreateTool = async () => {
    if (!toolName.trim()) return
    let config = {}
    try { config = JSON.parse(toolConfig) } catch {}
    await fetch(`${AI}/api/v1/tools`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tenant_id: tenantId, name: toolName, description: toolDesc, tool_type: toolType, config_json: config }),
    })
    setToolName(''); setToolDesc(''); setToolConfig('{}'); setShowToolForm(false)
    loadTools(tenantId)
  }

  const handleDeleteTool = async (id: string) => {
    await fetch(`${AI}/api/v1/tools/${id}`, { method: 'DELETE' })
    loadTools(tenantId)
  }

  if (loading) return <div className="flex h-full items-center justify-center bg-zinc-900"><div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" /></div>

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-auto">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-lg font-medium text-zinc-200 mb-1">{t('enhance.title')}</h1>
        <p className="text-xs text-zinc-500 mb-4">{t('enhance.desc')}</p>

        <div className="flex gap-1 mb-4">
          <button onClick={() => setTab('knowledge')} className={`px-4 py-1.5 rounded text-xs ${tab === 'knowledge' ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400'}`}>{t('enhance.knowledge')}</button>
          <button onClick={() => setTab('tools')} className={`px-4 py-1.5 rounded text-xs ${tab === 'tools' ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400'}`}>{t('enhance.tools')}</button>
        </div>

        {/* Knowledge Tab */}
        {tab === 'knowledge' && (
          <div className="space-y-3">
            <div className="flex justify-end">
              <button onClick={() => setShowUpload(true)} className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white">{t('enhance.uploadDoc')}</button>
            </div>
            {showUpload && (
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4 space-y-3">
                <input value={docTitle} onChange={e => setDocTitle(e.target.value)} placeholder={t('enhance.docTitle')} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
                <textarea value={docContent} onChange={e => setDocContent(e.target.value)} placeholder={t('enhance.docContent')} rows={6} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
                <div className="flex gap-2 justify-end">
                  <button onClick={() => setShowUpload(false)} className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300">Cancel</button>
                  <button onClick={handleUpload} className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white">{t('enhance.upload')}</button>
                </div>
              </div>
            )}
            {docs.map(doc => (
              <div key={doc.id} className="rounded-lg border border-zinc-700 bg-zinc-800/50 px-4 py-3 flex items-center justify-between">
                <div>
                  <p className="text-sm text-zinc-200">{doc.title}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] ${doc.status === 'ready' ? 'bg-green-500/20 text-green-400' : 'bg-yellow-500/20 text-yellow-400'}`}>{doc.status}</span>
                    <span className="text-[10px] text-zinc-500">{doc.chunk_count || 0} chunks</span>
                  </div>
                </div>
                <button onClick={() => handleDeleteDoc(doc.id)} className="text-xs text-red-400 hover:text-red-300">{t('enhance.delete')}</button>
              </div>
            ))}
            {docs.length === 0 && <p className="text-sm text-zinc-500 text-center py-12">{t('enhance.noDocs')}</p>}
          </div>
        )}

        {/* Tools Tab */}
        {tab === 'tools' && (
          <div className="space-y-3">
            <div className="flex justify-end">
              <button onClick={() => setShowToolForm(true)} className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white">{t('enhance.registerTool')}</button>
            </div>
            {showToolForm && (
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-4 space-y-3">
                <input value={toolName} onChange={e => setToolName(e.target.value)} placeholder={t('enhance.toolName')} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
                <input value={toolDesc} onChange={e => setToolDesc(e.target.value)} placeholder={t('enhance.toolDesc')} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none" />
                <select value={toolType} onChange={e => setToolType(e.target.value)} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none">
                  <option value="api_call">API Call</option>
                  <option value="webhook">Webhook</option>
                  <option value="mcp_server">MCP Server</option>
                </select>
                <textarea value={toolConfig} onChange={e => setToolConfig(e.target.value)} placeholder='{"url":"...","method":"POST","input_schema":{...}}' rows={4} className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-xs font-mono text-zinc-200 outline-none" />
                <div className="flex gap-2 justify-end">
                  <button onClick={() => setShowToolForm(false)} className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300">Cancel</button>
                  <button onClick={handleCreateTool} className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white">{t('enhance.register')}</button>
                </div>
              </div>
            )}
            {tools.map(tool => (
              <div key={tool.id} className="rounded-lg border border-zinc-700 bg-zinc-800/50 px-4 py-3 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-zinc-200">{tool.name}</span>
                    <span className={`rounded px-1.5 py-0.5 text-[10px] ${tool.tool_type === 'api_call' ? 'bg-blue-500/20 text-blue-400' : tool.tool_type === 'webhook' ? 'bg-green-500/20 text-green-400' : 'bg-purple-500/20 text-purple-400'}`}>{tool.tool_type}</span>
                  </div>
                  <p className="text-xs text-zinc-400 mt-1">{tool.description}</p>
                </div>
                <button onClick={() => handleDeleteTool(tool.id)} className="text-xs text-red-400 hover:text-red-300">{t('enhance.delete')}</button>
              </div>
            ))}
            {tools.length === 0 && <p className="text-sm text-zinc-500 text-center py-12">{t('enhance.noTools')}</p>}
          </div>
        )}
      </div>
    </div>
  )
}
