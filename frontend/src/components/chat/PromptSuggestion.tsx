'use client'

import { useState, useEffect } from 'react'
import {
  generateSuggestions,
  listSuggestions,
  applySuggestion,
  rejectSuggestion,
} from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

interface PromptSuggestionProps {
  projectId: string
}

interface SuggestionChange {
  type: 'modify' | 'add' | 'remove'
  section: string
  reason: string
  before?: string
  after?: string
}

interface Suggestion {
  id: string
  based_on_feedback_count: number
  changes: SuggestionChange[]
  status: string
  created_at: string
}

export function PromptSuggestionButton({ projectId }: PromptSuggestionProps) {
  const [open, setOpen] = useState(false)
  const [count, setCount] = useState(0)
  const { t } = useI18n()

  useEffect(() => {
    listSuggestions(projectId)
      .then((r) => setCount(r.suggestions.length))
      .catch(() => {})
  }, [projectId])

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="relative rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700 transition-colors"
      >
        {t('chat.promptOpt')}
        {count > 0 && (
          <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] text-white">
            {count}
          </span>
        )}
      </button>
      {open && (
        <SuggestionPanel
          projectId={projectId}
          onClose={() => setOpen(false)}
          onCountChange={setCount}
        />
      )}
    </>
  )
}

function SuggestionPanel({
  projectId,
  onClose,
  onCountChange,
}: {
  projectId: string
  onClose: () => void
  onCountChange: (n: number) => void
}) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const { t } = useI18n()

  const load = async () => {
    setLoading(true)
    try {
      const r = await listSuggestions(projectId)
      setSuggestions(r.suggestions)
      onCountChange(r.suggestions.length)
    } catch {}
    setLoading(false)
  }

  useEffect(() => { load() }, [projectId])

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      await generateSuggestions(projectId)
      await load()
    } catch {}
    setGenerating(false)
  }

  const handleApply = async (id: string) => {
    try {
      await applySuggestion(id, projectId)
      await load()
    } catch {}
  }

  const handleReject = async (id: string) => {
    try {
      await rejectSuggestion(id)
      await load()
    } catch {}
  }

  const borderColor: Record<string, string> = {
    add: 'border-green-500',
    remove: 'border-red-500',
    modify: 'border-yellow-500',
  }

  return (
    <div className="fixed inset-y-0 right-0 z-50 w-96 bg-zinc-900 border-l border-zinc-700 shadow-2xl flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-zinc-700 px-4 py-3">
        <h3 className="text-sm font-medium text-zinc-200">{t('suggestion.title')}</h3>
        <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 text-lg">&times;</button>
      </div>

      {/* Actions */}
      <div className="px-4 py-3 border-b border-zinc-800">
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="w-full rounded bg-blue-600 px-3 py-2 text-sm text-white hover:bg-blue-500 disabled:opacity-50 transition-colors"
        >
          {generating ? t('suggestion.analyzing') : t('suggestion.generate')}
        </button>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {loading && <p className="text-xs text-zinc-500">{t('suggestion.loading')}</p>}
        {!loading && suggestions.length === 0 && (
          <p className="text-xs text-zinc-500">{t('suggestion.empty')}</p>
        )}
        {suggestions.map((s) => (
          <div key={s.id} className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-3">
            <p className="text-xs text-zinc-400 mb-2">
              {t('suggestion.basedOn', { count: s.based_on_feedback_count })}
            </p>
            <div className="space-y-2">
              {s.changes.map((c, i) => (
                <div key={i} className={`border-l-2 ${borderColor[c.type] || 'border-zinc-600'} pl-3`}>
                  <p className="text-xs font-medium text-zinc-200">
                    <span className={`mr-1 ${c.type === 'add' ? 'text-green-400' : c.type === 'remove' ? 'text-red-400' : 'text-yellow-400'}`}>
                      {c.type === 'add' ? '+' : c.type === 'remove' ? '-' : '~'}
                    </span>
                    {c.section}
                  </p>
                  <p className="text-xs text-zinc-400 mt-0.5">{c.reason}</p>
                  {c.before && (
                    <p className="text-xs text-red-400/70 mt-1 line-through">{c.before.slice(0, 100)}</p>
                  )}
                  {c.after && (
                    <p className="text-xs text-green-400/70 mt-0.5">{c.after.slice(0, 100)}</p>
                  )}
                </div>
              ))}
            </div>
            <div className="flex gap-2 mt-3">
              <button
                onClick={() => handleApply(s.id)}
                className="flex-1 rounded bg-blue-600 px-2 py-1.5 text-xs text-white hover:bg-blue-500"
              >
                {t('suggestion.apply')}
              </button>
              <button
                onClick={() => handleReject(s.id)}
                className="flex-1 rounded border border-zinc-600 px-2 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700"
              >
                {t('suggestion.dismiss')}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
