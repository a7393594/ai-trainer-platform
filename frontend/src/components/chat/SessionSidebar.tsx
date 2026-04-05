'use client'

import { useState, useEffect } from 'react'
import { listSessions } from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'

interface SessionSidebarProps {
  projectId: string
  currentSessionId?: string
  onSelectSession: (sessionId: string) => void
  onNewSession: () => void
}

interface SessionItem {
  id: string
  session_type: string
  started_at: string
  ended_at?: string
}

const TYPE_STYLES: Record<string, { label: string; color: string }> = {
  freeform: { label: 'Free', color: 'bg-blue-500/20 text-blue-400' },
  onboarding: { label: 'Onboard', color: 'bg-green-500/20 text-green-400' },
  capability: { label: 'Capability', color: 'bg-purple-500/20 text-purple-400' },
}

export function SessionSidebar({ projectId, currentSessionId, onSelectSession, onNewSession }: SessionSidebarProps) {
  const [sessions, setSessions] = useState<SessionItem[]>([])
  const { t } = useI18n()

  function timeAgo(dateStr: string): string {
    const diff = Date.now() - new Date(dateStr).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return t('common.justNow')
    if (mins < 60) return t('common.mAgo', { n: mins })
    const hrs = Math.floor(mins / 60)
    if (hrs < 24) return t('common.hAgo', { n: hrs })
    const days = Math.floor(hrs / 24)
    return t('common.dAgo', { n: days })
  }

  useEffect(() => {
    listSessions(projectId).then((r) => setSessions(r.sessions)).catch(() => {})
  }, [projectId])

  return (
    <div className="w-56 border-r border-zinc-800 bg-zinc-900 flex flex-col">
      <div className="flex items-center justify-between px-3 py-3 border-b border-zinc-800">
        <span className="text-xs font-medium text-zinc-400">{t('chat.sessions')}</span>
        <button onClick={onNewSession} className="rounded bg-zinc-800 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-700">
          {t('chat.newSession')}
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {sessions.map((s) => {
          const style = TYPE_STYLES[s.session_type] || TYPE_STYLES.freeform
          const isActive = s.id === currentSessionId
          return (
            <button key={s.id} onClick={() => onSelectSession(s.id)} className={`w-full text-left px-3 py-2.5 border-b border-zinc-800/50 transition-colors ${isActive ? 'bg-blue-500/10 border-l-2 border-l-blue-500' : 'hover:bg-zinc-800/50 border-l-2 border-l-transparent'}`}>
              <div className="flex items-center gap-2">
                <span className={`rounded px-1.5 py-0.5 text-[10px] ${style.color}`}>{style.label}</span>
                <span className="text-[10px] text-zinc-500">{timeAgo(s.started_at)}</span>
              </div>
              <p className="text-xs text-zinc-400 mt-1 truncate">{s.id.slice(0, 8)}...</p>
            </button>
          )
        })}
      </div>
    </div>
  )
}
