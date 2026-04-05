'use client'

import { useEffect, useState } from 'react'
import { getDemoContext, listPromptVersions, activatePromptVersion } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

interface PromptVersion {
  id: string
  version: number
  content: string
  is_active: boolean
  change_notes?: string
  created_at: string
}

export default function PromptsPage() {
  const [versions, setVersions] = useState<PromptVersion[]>([])
  const [projectId, setProjectId] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
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

  const handleActivate = async (versionId: string) => {
    if (!projectId) return
    await activatePromptVersion(projectId, versionId)
    const r = await listPromptVersions(projectId)
    setVersions(r.versions)
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
    <div className="h-full bg-zinc-900 p-6">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-lg font-medium text-zinc-200 mb-1">{t('prompts.title')}</h1>
        <p className="text-xs text-zinc-500 mb-6">{t('prompts.desc')}</p>

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
                <div className="flex items-center gap-3">
                  <span className="text-sm font-mono text-zinc-300">v{v.version}</span>
                  {v.is_active && (
                    <span className="rounded bg-green-500/20 px-2 py-0.5 text-[10px] text-green-400">
                      {t('prompts.active')}
                    </span>
                  )}
                  {v.change_notes && (
                    <span className="text-xs text-zinc-500 truncate max-w-xs">
                      {v.change_notes}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-zinc-500">{formatDate(v.created_at)}</span>
                  <span className="text-zinc-600">{expandedId === v.id ? '[-]' : '[+]'}</span>
                </div>
              </button>

              {expandedId === v.id && (
                <div className="border-t border-zinc-700 px-4 py-3">
                  <pre className="whitespace-pre-wrap text-xs text-zinc-300 bg-zinc-900 rounded p-3 max-h-96 overflow-y-auto">
                    {v.content}
                  </pre>
                  {!v.is_active && (
                    <button
                      onClick={() => handleActivate(v.id)}
                      className="mt-3 rounded bg-blue-600 px-4 py-1.5 text-xs text-white hover:bg-blue-500"
                    >
                      {t('prompts.setActive')}
                    </button>
                  )}
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
    </div>
  )
}
