'use client'

import { useEffect, useState } from 'react'
import { getDemoContext } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'
import { useProject } from '@/lib/project-context'
import dynamic from 'next/dynamic'

const RefereeKnowledge = dynamic(() => import('../referee/knowledge/page'), { ssr: false })

const AI = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

interface DocDetail {
  document: any
  chunks: { content: string; chunk_index: number }[]
}

export default function KnowledgePage() {
  const { currentProject } = useProject()

  // Referee projects: show Rule Library
  if (currentProject?.project_type === 'referee') {
    return <RefereeKnowledge />
  }

  return <TrainerKnowledge />
}

function TrainerKnowledge() {
  const [projectId, setProjectId] = useState('')
  const [docs, setDocs] = useState<any[]>([])
  const [showUpload, setShowUpload] = useState(false)
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [uploading, setUploading] = useState(false)
  const [loading, setLoading] = useState(true)
  const { t } = useI18n()

  // View/Edit state
  const [selectedDoc, setSelectedDoc] = useState<DocDetail | null>(null)
  const [editMode, setEditMode] = useState(false)
  const [editTitle, setEditTitle] = useState('')
  const [editContent, setEditContent] = useState('')
  const [saving, setSaving] = useState(false)

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
    try {
      await fetch(`${AI}/api/v1/knowledge/upload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId, title, content, source_type: 'upload' }),
      })
      setTitle('')
      setContent('')
      setShowUpload(false)
    } catch {}
    setUploading(false)
    loadDocs(projectId)
  }

  const handleDelete = async (docId: string) => {
    // No native confirm — delete directly (can add custom modal later)
    try {
      await fetch(`${AI}/api/v1/knowledge/${docId}`, { method: 'DELETE' })
    } catch {}
    if (selectedDoc?.document?.id === docId) setSelectedDoc(null)
    loadDocs(projectId)
  }

  const handleView = async (docId: string) => {
    // Use doc from already-loaded list (includes raw_content)
    const doc = docs.find((d) => d.id === docId)
    if (!doc) return

    // Try to load chunks (may fail if endpoint not deployed yet)
    let chunks: any[] = []
    try {
      const r = await fetch(`${AI}/api/v1/knowledge/doc/${docId}`)
      if (r.ok) {
        const data = await r.json()
        chunks = data.chunks || []
      }
    } catch {}

    setSelectedDoc({ document: doc, chunks })
    setEditMode(false)
    setEditTitle(doc.title)
    setEditContent(doc.raw_content || '')
  }

  const handleStartEdit = () => {
    setEditMode(true)
  }

  const handleSave = async () => {
    if (!selectedDoc) return
    setSaving(true)
    try {
      const r = await fetch(`${AI}/api/v1/knowledge/doc/${selectedDoc.document.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: editTitle, content: editContent }),
      })
      if (!r.ok) {
        // Fallback: just reload list (endpoint may not exist on old backend)
        await loadDocs(projectId)
        setSelectedDoc(null)
        setSaving(false)
        setEditMode(false)
        return
      }
    } catch {
      await loadDocs(projectId)
      setSelectedDoc(null)
      setSaving(false)
      setEditMode(false)
      return
    }
    setSaving(false)
    setEditMode(false)
    await loadDocs(projectId)
    // Re-view to refresh
    const updated = docs.find((d) => d.id === selectedDoc.document.id)
    if (updated) {
      setSelectedDoc({ document: { ...updated, title: editTitle, raw_content: editContent }, chunks: selectedDoc.chunks })
    }
  }

  const handleClose = () => {
    setSelectedDoc(null)
    setEditMode(false)
  }

  const statusColor: Record<string, string> = {
    ready: 'bg-green-500/20 text-green-400',
    processing: 'bg-yellow-500/20 text-yellow-400',
    error: 'bg-red-500/20 text-red-400',
  }

  if (loading) return <div className="flex h-full items-center justify-center bg-zinc-900"><div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" /></div>

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-y-auto">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-lg font-medium text-zinc-200">{t('knowledge.title')}</h1>
            <p className="text-xs text-zinc-500">{t('knowledge.desc')}</p>
          </div>
          <button onClick={() => setShowUpload(true)} className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500">{t('knowledge.upload')}</button>
        </div>

        {/* Upload Form */}
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

        {/* Document List */}
        <div className="space-y-2">
          {docs.map((doc) => (
            <div
              key={doc.id}
              className={`rounded-lg border bg-zinc-800/50 px-4 py-3 transition-colors ${
                selectedDoc?.document?.id === doc.id ? 'border-blue-500/50' : 'border-zinc-700'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-zinc-200">{doc.title}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] ${statusColor[doc.status] || ''}`}>{doc.status}</span>
                    <span className="text-[10px] text-zinc-500">{doc.chunk_count} {t('knowledge.chunks')}</span>
                    <span className="text-[10px] text-zinc-500">{new Date(doc.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 ml-3">
                  <button onClick={() => handleView(doc.id)} className="text-xs text-blue-400 hover:text-blue-300">{t('knowledge.view')}</button>
                  <button onClick={() => handleDelete(doc.id)} className="text-xs text-red-400 hover:text-red-300">{t('knowledge.delete')}</button>
                </div>
              </div>
            </div>
          ))}
          {docs.length === 0 && <p className="text-sm text-zinc-500 text-center py-12">{t('knowledge.empty')}</p>}
        </div>

        {/* Document Detail Panel */}
        {selectedDoc && (
          <div className="mt-6 rounded-lg border border-zinc-700 bg-zinc-800 p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-medium text-zinc-200">
                {editMode ? t('knowledge.editTitle') : t('knowledge.viewContent')}
              </h3>
              <div className="flex items-center gap-2">
                {!editMode && (
                  <button onClick={handleStartEdit} className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500">
                    {t('knowledge.edit')}
                  </button>
                )}
                {editMode && (
                  <button onClick={handleSave} disabled={saving} className="rounded bg-green-600 px-3 py-1.5 text-xs text-white hover:bg-green-500 disabled:opacity-50">
                    {saving ? t('knowledge.saving') : t('knowledge.save')}
                  </button>
                )}
                <button onClick={handleClose} className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700">
                  {t('knowledge.close')}
                </button>
              </div>
            </div>

            {/* Title */}
            {editMode ? (
              <input
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                className="w-full mb-4 rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-blue-500"
              />
            ) : (
              <p className="text-sm text-zinc-300 mb-4 font-medium">{selectedDoc.document.title}</p>
            )}

            {/* Content */}
            {editMode ? (
              <textarea
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                rows={12}
                className="w-full rounded border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-blue-500 font-mono"
              />
            ) : (
              <pre className="whitespace-pre-wrap text-xs text-zinc-300 bg-zinc-900 rounded p-4 max-h-80 overflow-y-auto">
                {selectedDoc.document.raw_content || '(no content)'}
              </pre>
            )}

            {/* Chunks */}
            {!editMode && selectedDoc.chunks.length > 0 && (
              <div className="mt-4">
                <p className="text-xs text-zinc-400 mb-2">{t('knowledge.chunkList')} ({selectedDoc.chunks.length})</p>
                <div className="space-y-2 max-h-60 overflow-y-auto">
                  {selectedDoc.chunks.map((chunk, i) => (
                    <div key={i} className="rounded border border-zinc-700 bg-zinc-900 p-3">
                      <span className="text-[10px] text-zinc-500 mb-1 block">#{chunk.chunk_index}</span>
                      <p className="text-xs text-zinc-300 whitespace-pre-wrap">{chunk.content}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
