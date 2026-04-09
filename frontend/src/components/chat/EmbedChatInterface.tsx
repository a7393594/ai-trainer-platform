'use client'

/**
 * EmbedChatInterface — standalone chat UI for iframe embedding.
 *
 * Features (Phase 1.5):
 * - Sidebar with project picker (when token grants multi-project access)
 * - Session list + "New chat" button per selected project
 * - Stable external_user_id via URL ?uid= or localStorage fallback
 * - postMessage bridge with host page (ait:ready / ait:message-sent / ait:response-complete / ait:error)
 *   and incoming commands (ait:set-user, ait:new-session, ait:switch-project)
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import {
  sendEmbedMessageStream,
  getEmbedSessionHistory,
  listEmbedProjects,
  listEmbedSessions,
  type EmbedProject,
  type EmbedSession,
} from '@/lib/embed-client'

interface MessageItem {
  id: string
  role: 'user' | 'assistant'
  content: string
}

export interface EmbedLabels {
  empty: string
  emptyHint: string
  placeholder: string
  send: string
  error: string
  newChat: string
  history: string
  projects: string
  noSessions: string
}

const DEFAULT_LABELS: EmbedLabels = {
  empty: 'Start a conversation',
  emptyHint: 'Type a message below',
  placeholder: 'Type a message...',
  send: 'Send',
  error: 'Error',
  newChat: '+ New chat',
  history: 'History',
  projects: 'AI models',
  noSessions: 'No previous chats',
}

export interface EmbedChatInterfaceProps {
  projectId: string
  embedToken: string
  externalUserId?: string
  theme?: 'dark' | 'light'
  labels?: Partial<EmbedLabels>
  initialSessionId?: string
}

const UID_STORAGE_KEY = 'ait:uid'

/** Resolve stable external user id: prop > localStorage > generated. */
function resolveUid(propUid?: string): string {
  if (propUid) return propUid
  if (typeof window === 'undefined') return 'anon'
  try {
    const stored = window.localStorage.getItem(UID_STORAGE_KEY)
    if (stored) return stored
    const fresh = `anon_${crypto.randomUUID().slice(0, 12)}`
    window.localStorage.setItem(UID_STORAGE_KEY, fresh)
    return fresh
  } catch {
    return `anon_${Math.random().toString(36).slice(2, 10)}`
  }
}

function postToParent(payload: Record<string, unknown>) {
  if (typeof window === 'undefined') return
  try {
    window.parent?.postMessage(payload, '*')
  } catch {}
}

export function EmbedChatInterface({
  projectId: initialProjectId,
  embedToken,
  externalUserId: propUid,
  theme = 'dark',
  labels: labelsProp,
  initialSessionId,
}: EmbedChatInterfaceProps) {
  const labels = { ...DEFAULT_LABELS, ...labelsProp }

  // Core state
  const [uid, setUid] = useState<string>(() => resolveUid(propUid))
  const [projects, setProjects] = useState<EmbedProject[]>([])
  const [currentProjectId, setCurrentProjectId] = useState<string>(initialProjectId)
  const [sessions, setSessions] = useState<EmbedSession[]>([])
  const [sessionId, setSessionId] = useState<string | undefined>(initialSessionId)

  // Chat state
  const [messages, setMessages] = useState<MessageItem[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const scrollRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new message
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  // Initial load: projects
  useEffect(() => {
    listEmbedProjects(embedToken)
      .then((ps) => {
        setProjects(ps)
        // If token returned a different primary, keep initial URL param as long as it's allowed
        if (ps.length > 0 && !ps.some((p) => p.id === initialProjectId)) {
          const primary = ps.find((p) => p.is_primary) || ps[0]
          setCurrentProjectId(primary.id)
        }
      })
      .catch(() => {})
  }, [embedToken, initialProjectId])

  // Load session list whenever project or uid changes
  const refreshSessions = useCallback(async () => {
    if (!currentProjectId || !uid) return
    setSessionsLoading(true)
    try {
      const list = await listEmbedSessions(embedToken, currentProjectId, uid)
      setSessions(list)
    } catch {
      setSessions([])
    } finally {
      setSessionsLoading(false)
    }
  }, [embedToken, currentProjectId, uid])

  useEffect(() => {
    refreshSessions()
  }, [refreshSessions])

  // Load selected session history
  useEffect(() => {
    if (!sessionId) {
      setMessages([])
      return
    }
    getEmbedSessionHistory(sessionId, embedToken)
      .then((data) => {
        const items: MessageItem[] = (data.messages || []).map((m: any) => ({
          id: m.id,
          role: m.role,
          content: m.content,
        }))
        setMessages(items)
      })
      .catch(() => setMessages([]))
  }, [sessionId, embedToken])

  // Emit ready event on mount
  useEffect(() => {
    postToParent({ type: 'ait:ready', version: '1.5', project_id: currentProjectId })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Listen for host → iframe commands via postMessage
  useEffect(() => {
    function onMessage(e: MessageEvent) {
      const data = e.data
      if (!data || typeof data !== 'object' || typeof data.type !== 'string') return
      if (!data.type.startsWith('ait:')) return
      if (data.type === 'ait:set-user' && typeof data.uid === 'string') {
        try {
          window.localStorage.setItem(UID_STORAGE_KEY, data.uid)
        } catch {}
        setUid(data.uid)
        setSessionId(undefined)
        setMessages([])
      } else if (data.type === 'ait:new-session') {
        setSessionId(undefined)
        setMessages([])
      } else if (data.type === 'ait:switch-project' && typeof data.project_id === 'string') {
        setCurrentProjectId(data.project_id)
        setSessionId(undefined)
        setMessages([])
      }
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [])

  const handleNewChat = () => {
    setSessionId(undefined)
    setMessages([])
    postToParent({ type: 'ait:new-session', project_id: currentProjectId })
  }

  const handleSwitchProject = (pid: string) => {
    if (pid === currentProjectId) return
    setCurrentProjectId(pid)
    setSessionId(undefined)
    setMessages([])
    postToParent({ type: 'ait:switch-project', project_id: pid })
  }

  const handlePickSession = (sid: string) => {
    if (sid === sessionId) return
    setSessionId(sid)
  }

  // Theme tokens
  const isDark = theme === 'dark'
  const rootBg = isDark ? 'bg-zinc-900' : 'bg-white'
  const sidebarBg = isDark ? 'bg-zinc-950' : 'bg-zinc-50'
  const border = isDark ? 'border-zinc-800' : 'border-zinc-200'
  const inputBg = isDark ? 'bg-zinc-800' : 'bg-zinc-50'
  const textMuted = isDark ? 'text-zinc-500' : 'text-zinc-500'
  const textPrimary = isDark ? 'text-zinc-200' : 'text-zinc-900'
  const userBubble = 'bg-blue-600 text-white'
  const assistantBubble = isDark
    ? 'bg-zinc-800 text-zinc-200 border border-zinc-700'
    : 'bg-zinc-100 text-zinc-900 border border-zinc-200'
  const sessionBtnIdle = isDark
    ? 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
    : 'text-zinc-600 hover:bg-zinc-200 hover:text-zinc-900'
  const sessionBtnActive = isDark
    ? 'bg-blue-600/20 text-blue-400'
    : 'bg-blue-100 text-blue-700'

  const handleSend = async () => {
    if (!input.trim() || loading) return

    const text = input.trim()
    const userMsgId = crypto.randomUUID()
    const aiMsgId = crypto.randomUUID()
    const userMsg: MessageItem = { id: userMsgId, role: 'user', content: text }

    setMessages((prev) => [...prev, userMsg, { id: aiMsgId, role: 'assistant', content: '' }])
    setInput('')
    setLoading(true)

    postToParent({
      type: 'ait:message-sent',
      project_id: currentProjectId,
      session_id: sessionId,
      text,
    })

    try {
      await sendEmbedMessageStream(
        {
          message: text,
          session_id: sessionId,
          external_user_id: uid,
          project_id: currentProjectId,
        },
        embedToken,
        {
          onChunk: (chunk) => {
            setMessages((prev) =>
              prev.map((m) => (m.id === aiMsgId ? { ...m, content: m.content + chunk } : m))
            )
          },
          onDone: (sid, messageId) => {
            const wasNewSession = !sessionId
            if (wasNewSession) setSessionId(sid)
            setMessages((prev) =>
              prev.map((m) => (m.id === aiMsgId ? { ...m, id: messageId } : m))
            )
            postToParent({
              type: 'ait:response-complete',
              project_id: currentProjectId,
              session_id: sid,
              message_id: messageId,
            })
            if (wasNewSession) {
              // refresh sessions so sidebar shows new entry
              refreshSessions()
            }
          },
          onError: (error) => {
            setMessages((prev) =>
              prev.map((m) => (m.id === aiMsgId ? { ...m, content: `${labels.error}: ${error}` } : m))
            )
            postToParent({ type: 'ait:error', error })
          },
        },
      )
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setMessages((prev) =>
        prev.map((m) => (m.id === aiMsgId ? { ...m, content: `${labels.error}: ${msg}` } : m))
      )
      postToParent({ type: 'ait:error', error: msg })
    } finally {
      setLoading(false)
    }
  }

  const currentProject = projects.find((p) => p.id === currentProjectId)

  const sidebarVisible = sidebarOpen
  const showSidebar = projects.length > 0 || sessions.length > 0 || sessionsLoading

  const formatSessionLabel = (s: EmbedSession) => {
    const short = s.id.slice(0, 8)
    try {
      const d = new Date(s.started_at)
      const mm = String(d.getMonth() + 1).padStart(2, '0')
      const dd = String(d.getDate()).padStart(2, '0')
      const hh = String(d.getHours()).padStart(2, '0')
      const mi = String(d.getMinutes()).padStart(2, '0')
      return `${mm}/${dd} ${hh}:${mi}  ·  ${short}`
    } catch {
      return short
    }
  }

  return (
    <div className={`flex h-full ${rootBg} min-h-0`}>
      {/* Sidebar */}
      {showSidebar && sidebarVisible && (
        <aside className={`hidden md:flex w-60 flex-shrink-0 flex-col border-r ${border} ${sidebarBg}`}>
          {/* Project picker */}
          {projects.length > 1 && (
            <div className={`border-b ${border} px-3 py-3`}>
              <label className={`block text-[10px] uppercase tracking-wide ${textMuted} mb-1.5`}>
                {labels.projects}
              </label>
              <select
                value={currentProjectId}
                onChange={(e) => handleSwitchProject(e.target.value)}
                className={`w-full rounded border ${border} ${inputBg} px-2 py-1.5 text-xs ${textPrimary} outline-none focus:border-blue-500`}
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} {p.is_primary ? '★' : ''}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* New chat button */}
          <div className="px-3 py-3">
            <button
              onClick={handleNewChat}
              className="w-full rounded-lg bg-blue-600 px-3 py-2 text-xs font-medium text-white hover:bg-blue-500 transition-colors"
            >
              {labels.newChat}
            </button>
          </div>

          {/* Session list */}
          <div className="flex-1 overflow-y-auto px-2 pb-3">
            <p className={`px-2 text-[10px] uppercase tracking-wide ${textMuted} mb-1`}>
              {labels.history}
            </p>
            {sessionsLoading && (
              <p className={`px-2 py-2 text-[11px] ${textMuted}`}>…</p>
            )}
            {!sessionsLoading && sessions.length === 0 && (
              <p className={`px-2 py-2 text-[11px] ${textMuted}`}>{labels.noSessions}</p>
            )}
            <div className="space-y-0.5">
              {sessions.map((s) => (
                <button
                  key={s.id}
                  onClick={() => handlePickSession(s.id)}
                  className={`w-full text-left rounded px-2 py-1.5 text-[11px] font-mono transition-colors ${
                    s.id === sessionId ? sessionBtnActive : sessionBtnIdle
                  }`}
                  title={s.id}
                >
                  {formatSessionLabel(s)}
                </button>
              ))}
            </div>
          </div>
        </aside>
      )}

      {/* Main chat area */}
      <div className="flex flex-1 flex-col min-w-0 min-h-0">
        {/* Header (only when sidebar hidden or project info relevant) */}
        {currentProject && (
          <div className={`border-b ${border} px-4 py-2 flex items-center justify-between`}>
            <div className="min-w-0">
              <p className={`text-xs font-medium ${textPrimary} truncate`}>{currentProject.name}</p>
              {currentProject.description && (
                <p className={`text-[10px] ${textMuted} truncate`}>{currentProject.description}</p>
              )}
            </div>
            {showSidebar && (
              <button
                onClick={() => setSidebarOpen((v) => !v)}
                className={`md:block hidden text-[10px] ${textMuted} hover:text-blue-400 ml-2`}
                title="Toggle sidebar"
              >
                {sidebarVisible ? '◀' : '▶'}
              </button>
            )}
          </div>
        )}

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
          {messages.length === 0 && !loading && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <p className={`${textMuted} text-sm`}>{labels.empty}</p>
                <p className={`${isDark ? 'text-zinc-600' : 'text-zinc-400'} text-xs mt-1`}>{labels.emptyHint}</p>
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] rounded-xl px-4 py-3 ${msg.role === 'user' ? userBubble : assistantBubble}`}>
                <p className="text-sm whitespace-pre-wrap">
                  {msg.content || (loading && msg.role === 'assistant' ? '...' : '')}
                </p>
              </div>
            </div>
          ))}

          {loading && messages[messages.length - 1]?.role !== 'assistant' && (
            <div className="flex justify-start">
              <div className={`rounded-xl ${assistantBubble} px-4 py-3`}>
                <div className="flex gap-1">
                  <span className={`w-2 h-2 ${isDark ? 'bg-zinc-500' : 'bg-zinc-400'} rounded-full animate-bounce`} style={{ animationDelay: '0ms' }} />
                  <span className={`w-2 h-2 ${isDark ? 'bg-zinc-500' : 'bg-zinc-400'} rounded-full animate-bounce`} style={{ animationDelay: '150ms' }} />
                  <span className={`w-2 h-2 ${isDark ? 'bg-zinc-500' : 'bg-zinc-400'} rounded-full animate-bounce`} style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Input */}
        <div className={`border-t ${border} ${inputBg} px-4 py-3`}>
          <div className="flex gap-3">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
              placeholder={labels.placeholder}
              disabled={loading}
              className={`flex-1 rounded-lg border ${border} ${isDark ? 'bg-zinc-700 text-zinc-200 placeholder:text-zinc-500' : 'bg-white text-zinc-900 placeholder:text-zinc-400'} px-4 py-2.5 text-sm outline-none focus:border-blue-500 disabled:opacity-50`}
            />
            <button
              onClick={handleSend}
              disabled={loading || !input.trim()}
              className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50 transition-colors"
            >
              {labels.send}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
