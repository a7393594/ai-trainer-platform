'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

export default function KnowledgePage() {
  const [projectId, setProjectId] = useState('')
  const [docs, setDocs] = useState<any[]>([])
  const [showUpload, setShowUpload] = useState(false)
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [uploading, setUploading] = useState(false)
  const [loading, setLoading] = useState(true)
  const { t } = useI18n()

  useEffect(() => {
    getDemoContext().then((ctx) => {
      setProjectId(ctx.project_id)
      loadDocs(ctx.project_id)
    }).catch(() => setLoading(false))
  }, [])

  const loadDocs = async (pid: string) => {
    const r = await fetch(`${AI}/api/v1/knowledge/${pid}`)
    const d = await r.json()
    setDocs(d.documents || [])
    setLoading(false)
  }

  const handleUpload = async () => {
    if (!title.trim() || !content.trim()) return
    setUploading(true)
    await fetch(`${AI}/api/v1/knowledge/upload`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, title, content, source_type: 'upload' }),
    })
    setTitle('')
    setContent('')
    setShowUpload(false)
    setUploading(false)
    loadDocs(projectId)
  }

  const handleDelete = async (docId: string) => {
    await fetch(`${AI}/api/v1/knowledge/${docId}`, { method: 'DELETE' })
    loadDocs(projectId)
  }

  const statusColor: Record<string, string> = {
    ready: 'bg-green-500/20 text-green-400',
    processing: 'bg-yellow-500/20 text-yellow-400',
    error: 'bg-red-500/20 text-red-400',
  }

  if (loading) return <div className="flex h-full items-center justify-center bg-zinc-900"><div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" /></div>

  return (
    <div className="h-full bg-zinc-900 p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-lg font-medium text-zinc-200">{t('knowledge.title')}</h1>
            <p className="text-xs text-zinc-500">{t('knowledge.desc')}</p>
          </div>
          <button onClick={() => setShowUpload(true)} className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500">{t('knowledge.upload')}</button>
        </div>

        {showUpload && (
          <div className="mb-6 rounded-lg border border-zinc-700 bg-zinc-800 p-4">
            <h3 className="text-sm font-medium text-zinc-200 mb-3">{t('knowledge.upload')}</h3>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t('knowledge.docTitle')} className="w-full mb-3 rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-blue-500" />
            <textarea value={content} onChange={(e) => setContent(e.target.value)} placeholder={t('knowledge.content')} rows={8} className="w-full mb-3 rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-blue-500" />
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowUpload(false)} className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700">{t('common.cancel')}</button>
              <button onClick={handleUpload} disabled={uploading || !title.trim() || !content.trim()} className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50">{uploading ? t('knowledge.uploading') : t('knowledge.upload')}</button>
            </div>
          </div>
        )}

        <div className="space-y-2">
          {docs.map((doc) => (
            <div key={doc.id} className="flex items-center justify-between rounded-lg border border-zinc-700 bg-zinc-800/50 px-4 py-3">
              <div>
                <p className="text-sm text-zinc-200">{doc.title}</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className={`rounded px-1.5 py-0.5 text-[10px] ${statusColor[doc.status] || ''}`}>{doc.status}</span>
                  <span className="text-[10px] text-zinc-500">{doc.chunk_count} chunks</span>
                  <span className="text-[10px] text-zinc-500">{new Date(doc.created_at).toLocaleDateString()}</span>
                </div>
              </div>
              <button onClick={() => handleDelete(doc.id)} className="text-xs text-red-400 hover:text-red-300">{t('knowledge.delete')}</button>
            </div>
          ))}
          {docs.length === 0 && <p className="text-sm text-zinc-500 text-center py-12">{t('knowledge.empty')}</p>}
        </div>
      </div>
    </div>
  )
}
