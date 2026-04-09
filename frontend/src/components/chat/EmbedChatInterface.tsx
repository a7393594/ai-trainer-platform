'use client'

/**
 * EmbedChatInterface — standalone chat UI for iframe embedding.
 *
 * No dependencies on AuthProvider or I18nProvider.
 * All labels come from `labels` prop (defaults to English).
 * All API calls go through /embed/* with X-Embed-Token header.
 */

import { useState, useRef, useEffect } from 'react'
import { sendEmbedMessageStream, getEmbedSessionHistory } from '@/lib/embed-client'

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
}

const DEFAULT_LABELS: EmbedLabels = {
  empty: 'Start a conversation',
  emptyHint: 'Type a message below',
  placeholder: 'Type a message...',
  send: 'Send',
  error: 'Error',
}

export interface EmbedChatInterfaceProps {
  projectId: string
  embedToken: string
  externalUserId?: string
  theme?: 'dark' | 'light'
  labels?: Partial<EmbedLabels>
  initialSessionId?: string
}

export function EmbedChatInterface({
  embedToken,
  externalUserId,
  theme = 'dark',
  labels: labelsProp,
  initialSessionId,
}: EmbedChatInterfaceProps) {
  const labels = { ...DEFAULT_LABELS, ...labelsProp }

  const [messages, setMessages] = useState<MessageItem[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | undefined>(initialSessionId)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new message
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  // Load existing session history if provided
  useEffect(() => {
    if (initialSessionId) {
      getEmbedSessionHistory(initialSessionId, embedToken)
        .then((data) => {
          const items: MessageItem[] = (data.messages || []).map((m: any) => ({
            id: m.id,
            role: m.role,
            content: m.content,
          }))
          setMessages(items)
        })
        .catch(() => {})
    }
  }, [initialSessionId, embedToken])

  const isDark = theme === 'dark'
  const bg = isDark ? 'bg-zinc-900' : 'bg-white'
  const border = isDark ? 'border-zinc-700' : 'border-zinc-200'
  const inputBg = isDark ? 'bg-zinc-800' : 'bg-zinc-50'
  const textPrimary = isDark ? 'text-zinc-200' : 'text-zinc-900'
  const textMuted = isDark ? 'text-zinc-500' : 'text-zinc-500'
  const userBubble = 'bg-blue-600 text-white'
  const assistantBubble = isDark
    ? 'bg-zinc-800 text-zinc-200 border border-zinc-700'
    : 'bg-zinc-100 text-zinc-900 border border-zinc-200'

  const handleSend = async () => {
    if (!input.trim() || loading) return

    const userMsgId = crypto.randomUUID()
    const aiMsgId = crypto.randomUUID()
    const userMsg: MessageItem = { id: userMsgId, role: 'user', content: input.trim() }

    setMessages((prev) => [...prev, userMsg, { id: aiMsgId, role: 'assistant', content: '' }])
    setInput('')
    setLoading(true)

    try {
      await sendEmbedMessageStream(
        {
          message: userMsg.content,
          session_id: sessionId,
          external_user_id: externalUserId,
        },
        embedToken,
        {
          onChunk: (chunk) => {
            setMessages((prev) =>
              prev.map((m) => (m.id === aiMsgId ? { ...m, content: m.content + chunk } : m))
            )
          },
          onDone: (sid, messageId) => {
            if (!sessionId) setSessionId(sid)
            setMessages((prev) =>
              prev.map((m) => (m.id === aiMsgId ? { ...m, id: messageId } : m))
            )
          },
          onError: (error) => {
            setMessages((prev) =>
              prev.map((m) => (m.id === aiMsgId ? { ...m, content: `${labels.error}: ${error}` } : m))
            )
          },
        },
      )
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === aiMsgId ? { ...m, content: `${labels.error}: ${err instanceof Error ? err.message : err}` } : m
        )
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={`flex h-full flex-col ${bg} min-h-0`}>
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
              <p className="text-sm whitespace-pre-wrap">{msg.content || (loading && msg.role === 'assistant' ? '...' : '')}</p>
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
  )
}
