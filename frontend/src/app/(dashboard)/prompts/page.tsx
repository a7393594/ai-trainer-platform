'use client'

import { useEffect, useState } from 'react'
import {
  getDemoContext,
  listPromptVersions,
  activatePromptVersion,
  createPromptVersion,
} from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

interface PromptVersion {
  id: string
  version: number
  content: string
  is_active: boolean
  change_notes?: string
  created_at: string
}

type ModalMode = { type: 'create' } | { type: 'edit'; source: PromptVersion } | null

export default function PromptsPage() {
  const [versions, setVersions] = useState<PromptVersion[]>([])
  const [projectId, setProjectId] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<ModalMode>(null)
  const { t } = useI18n()

  useEffect(() => {
    getDemoContext()
      .then((ctx) => {
        setProjectId(ctx.project_id)
        return listPromptVersions(ctx.project_id)
      })
      .then((r) => setVersions(r.versions))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const refreshVersions = async () => {
    if (!projectId) return
    const r = await listPromptVersions(projectId)
    setVersions(r.versions)
  }

  const handleActivate = async (versionId: string) => {
    if (!projectId) return
    await activatePromptVersion(projectId, versionId)
    await refreshVersions()
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('zh-TW', {
      month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    })
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-zinc-900">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
      </div>
    )
  }

  return (
    <div className="h-full bg-zinc-900 p-6 overflow-y-auto">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-lg font-medium text-zinc-200 mb-1">{t('prompts.title')}</h1>
            <p className="text-xs text-zinc-500">{t('prompts.desc')}</p>
          </div>
          <button
            onClick={() => setModal({ type: 'create' })}
            className="rounded bg-blue-600 px-4 py-2 text-xs text-white hover:bg-blue-500 shrink-0"
          >
            + 新增版本
          </button>
        </div>

        <div className="space-y-2">
          {versions.map((v) => (
            <div
              key={v.id}
              className={`rounded-lg border ${
                v.is_active ? 'border-blue-500/50 bg-blue-500/5' : 'border-zinc-700 bg-zinc-800/50'
              }`}
            >
              <button
                onClick={() => setExpandedId(expandedId === v.id ? null : v.id)}
                className="w-full flex items-center justify-between px-4 py-3 text-left"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <span className="text-sm font-mono text-zinc-300 shrink-0">v{v.version}</span>
                  {v.is_active && (
                    <span className="rounded bg-green-500/20 px-2 py-0.5 text-[10px] text-green-400 shrink-0">
                      {t('prompts.active')}
                    </span>
                  )}
                  {v.change_notes && (
                    <span className="text-xs text-zinc-500 truncate">
                      {v.change_notes}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <span className="text-xs text-zinc-500">{formatDate(v.created_at)}</span>
                  <span className="text-zinc-600">{expandedId === v.id ? '[-]' : '[+]'}</span>
                </div>
              </button>

              {expandedId === v.id && (
                <div className="border-t border-zinc-700 px-4 py-3">
                  <pre className="whitespace-pre-wrap text-xs text-zinc-300 bg-zinc-900 rounded p-3 max-h-96 overflow-y-auto">
                    {v.content}
                  </pre>
                  <div className="mt-3 flex items-center gap-2">
                    {!v.is_active && (
                      <button
                        onClick={() => handleActivate(v.id)}
                        className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white hover:bg-blue-500"
                      >
                        {t('prompts.setActive')}
                      </button>
                    )}
                    <button
                      onClick={() => setModal({ type: 'edit', source: v })}
                      className="rounded border border-zinc-700 px-4 py-1.5 text-xs text-zinc-300 hover:text-zinc-100 hover:border-zinc-500"
                    >
                      編輯（建立新版本）
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>

        {versions.length === 0 && (
          <p className="text-sm text-zinc-500 text-center py-12">
            {t('prompts.empty')}
          </p>
        )}
      </div>

      {/* Create/Edit Modal */}
      {modal && projectId && (
        <PromptModal
          mode={modal}
          projectId={projectId}
          onClose={() => setModal(null)}
          onSaved={async () => {
            setModal(null)
            await refreshVersions()
          }}
        />
      )}
    </div>
  )
}

function PromptModal({
  mode, projectId, onClose, onSaved,
}: {
  mode: NonNullable<ModalMode>
  projectId: string
  onClose: () => void
  onSaved: () => Promise<void>
}) {
  const isEdit = mode.type === 'edit'
  const [content, setContent] = useState(isEdit ? mode.source.content : '')
  const [changeNotes, setChangeNotes] = useState(
    isEdit ? `編輯自 v${mode.source.version}` : ''
  )
  const [activate, setActivate] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSave = async () => {
    if (!content.trim()) { setError('內容不可為空'); return }
    setSaving(true)
    setError(null)
    try {
      await createPromptVersion(projectId, {
        content: content.trim(),
        change_notes: changeNotes.trim() || undefined,
        activate,
      })
      await onSaved()
    } catch (e) {
      setError(e instanceof Error ? e.message : '儲存失敗')
    }
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-3xl max-h-[90vh] flex flex-col rounded-lg border border-zinc-700 bg-zinc-900 shadow-xl">
        <div className="flex items-center justify-between border-b border-zinc-700 px-4 py-3">
          <h2 className="text-sm font-medium text-zinc-200">
            {isEdit ? `編輯 v${mode.source.version}（會建立新版本）` : '新增 Prompt 版本'}
          </h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          <div>
            <label className="text-xs text-zinc-400 block mb-1">Prompt 內容</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={18}
              className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 font-mono outline-none focus:border-blue-500 resize-y"
              placeholder="輸入 prompt 內容..."
            />
            <p className="text-[10px] text-zinc-600 mt-1">{content.length} 字元</p>
          </div>

          <div>
            <label className="text-xs text-zinc-400 block mb-1">變更備註（選填）</label>
            <input
              type="text"
              value={changeNotes}
              onChange={(e) => setChangeNotes(e.target.value)}
              className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-200 outline-none focus:border-blue-500"
              placeholder="例如：新增第 9 條鐵律..."
            />
          </div>

          <label className="flex items-center gap-2 text-xs text-zinc-400">
            <input
              type="checkbox"
              checked={activate}
              onChange={(e) => setActivate(e.target.checked)}
              className="rounded"
            />
            建立後立即啟用（會停用目前 active 版本）
          </label>

          {error && <p className="text-xs text-red-400">{error}</p>}
        </div>

        <div className="flex justify-end gap-2 border-t border-zinc-700 px-4 py-3">
          <button
            onClick={onClose}
            disabled={saving}
            className="rounded border border-zinc-700 px-4 py-1.5 text-xs text-zinc-300 hover:text-zinc-100 disabled:opacity-50"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !content.trim()}
            className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {saving ? '儲存中...' : '建立版本'}
          </button>
        </div>
      </div>
    </div>
  )
}
