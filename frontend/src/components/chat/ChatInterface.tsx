'use client'

/**
 * ChatInterface — 訓練對話介面
 *
 * 支援：文字對話 + 互動元件 + 回饋打分 + Onboarding 模式 + 歷史載入
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import {
  sendMessage, sendMessageStream, sendWidgetResponse, submitFeedback,
  startOnboarding, answerOnboarding, getSessionMessages,
} from '@/lib/ai-engine'
import { useI18n } from '@/lib/i18n'
import { WidgetRenderer } from '@/components/widgets/WidgetRenderer'
import { FeedbackBar } from '@/components/chat/FeedbackBar'
import { OnboardingProgress } from '@/components/chat/OnboardingProgress'
import type { ChatResponse, WidgetDefinition, Rating } from '@/types'

interface MessageItem {
  id: string
  role: 'user' | 'assistant'
  content: string
  widgets?: WidgetDefinition[]
  widgetAnswered?: boolean
  metadata?: Record<string, any>
}

export type ChatMode = 'freeform' | 'onboarding' | 'capability'

interface ChatInterfaceProps {
  projectId: string
  userId?: string
  sessionId?: string
  model?: string
  mode?: ChatMode
}

export function ChatInterface({
  projectId, userId, sessionId: initialSessionId,
  model, mode = 'freeform',
}: ChatInterfaceProps) {
  const [messages, setMessages] = useState<MessageItem[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState(initialSessionId)
  const [onboardingProgress, setOnboardingProgress] = useState<{ current: number; total: number } | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const { t } = useI18n()

  // 自動滾到底
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  // 載入既有 session 歷史
  useEffect(() => {
    if (initialSessionId) {
      loadSessionHistory(initialSessionId)
    }
  }, [initialSessionId])

  // 啟動 onboarding 模式
  useEffect(() => {
    if (mode === 'onboarding' && !initialSessionId) {
      handleStartOnboarding()
    }
  }, [mode])

  const loadSessionHistory = async (sid: string) => {
    try {
      const { messages: history } = await getSessionMessages(projectId, sid)
      const items: MessageItem[] = history
        .filter((m: any) => m.role === 'user' || m.role === 'assistant')
        .map((m: any) => ({
          id: m.id,
          role: m.role as 'user' | 'assistant',
          content: m.content,
          metadata: m.metadata,
        }))
      setMessages(items)
      setSessionId(sid)
    } catch (err) {
      console.error('Failed to load session history:', err)
    }
  }

  const handleStartOnboarding = async () => {
    if (!userId) return
    setLoading(true)
    try {
      const response = await startOnboarding(projectId, userId, 'poker')
      setSessionId(response.session_id)
      const progress = response.metadata?.progress
      if (progress) {
        setOnboardingProgress({ current: progress.current, total: progress.total })
      }
      handleResponse(response)
    } catch (err) {
      setMessages([{ id: crypto.randomUUID(), role: 'assistant', content: `Onboarding error: ${err}` }])
    } finally {
      setLoading(false)
    }
  }

  // 送出文字訊息（streaming）
  const handleSend = async () => {
    if (!input.trim() || loading) return

    const userMsg: MessageItem = {
      id: crypto.randomUUID(),
      role: 'user',
      content: input.trim(),
    }
    const streamingId = crypto.randomUUID()
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setLoading(true)

    // 先加一個空的 assistant message 用於 streaming 填充
    setMessages((prev) => [...prev, { id: streamingId, role: 'assistant', content: '' }])

    try {
      await sendMessageStream(
        {
          project_id: projectId,
          session_id: sessionId,
          user_id: userId,
          message: userMsg.content,
          model,
        },
        // onChunk: 逐字更新
        (chunk) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === streamingId ? { ...m, content: m.content + chunk } : m
            )
          )
        },
        // onDone: 更新 message_id + session_id
        (sid, messageId) => {
          if (!sessionId) setSessionId(sid)
          setMessages((prev) =>
            prev.map((m) =>
              m.id === streamingId ? { ...m, id: messageId } : m
            )
          )
        },
        // onError
        (error) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === streamingId ? { ...m, content: `Error: ${error}` } : m
            )
          )
        },
      )
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === streamingId
            ? { ...m, content: `Error: ${err instanceof Error ? err.message : err}` }
            : m
        )
      )
    } finally {
      setLoading(false)
    }
  }

  // 處理 AI 回覆
  const handleResponse = (response: ChatResponse) => {
    if (!sessionId) setSessionId(response.session_id)

    // 更新 onboarding 進度
    const progress = response.metadata?.progress
    if (progress) {
      setOnboardingProgress({ current: progress.current, total: progress.total })
    }

    // 檢查 onboarding 完成
    if (response.metadata?.onboarding_complete) {
      setOnboardingProgress(null)
    }

    const aiMsg: MessageItem = {
      id: response.message_id || crypto.randomUUID(),
      role: 'assistant',
      content: response.message.content,
      widgets: response.widgets?.length > 0 ? response.widgets : undefined,
      metadata: response.metadata,
    }
    setMessages((prev) => [...prev, aiMsg])
  }

  // 處理互動元件回覆
  const handleWidgetResponse = async (msgId: string, widget: WidgetDefinition, result: Record<string, any>) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === msgId ? { ...m, widgetAnswered: true } : m))
    )
    setLoading(true)

    try {
      // 找到對應的 question_id (onboarding 模式)
      const msg = messages.find((m) => m.id === msgId)
      const questionId = msg?.metadata?.question_id

      let response: ChatResponse
      if (questionId && sessionId) {
        // Onboarding 模式
        response = await answerOnboarding(sessionId, questionId, result)
      } else {
        // 一般元件回覆
        response = await sendWidgetResponse({
          session_id: sessionId!,
          widget_type: widget.widget_type,
          result,
        })
      }
      handleResponse(response)
    } catch (err) {
      console.error('Widget response error:', err)
    } finally {
      setLoading(false)
    }
  }

  // 處理回饋
  const handleFeedback = async (messageId: string, rating: Rating, correction?: string) => {
    try {
      await submitFeedback({ message_id: messageId, rating, correction_text: correction })
    } catch (err) {
      console.error('Feedback error:', err)
    }
  }

  return (
    <div className="flex h-full flex-col bg-zinc-900 min-h-0">
      {/* Onboarding 進度條 */}
      {onboardingProgress && (
        <OnboardingProgress current={onboardingProgress.current} total={onboardingProgress.total} />
      )}

      {/* 訊息列表 */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.length === 0 && !loading && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <p className="text-zinc-500 text-sm">{t('chat.empty')}</p>
              <p className="text-zinc-600 text-xs mt-1">{t('chat.emptyHint')}</p>
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[80%] rounded-xl px-4 py-3 ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-zinc-800 text-zinc-200 border border-zinc-700'
              }`}
            >
              <p className="text-sm whitespace-pre-wrap">{msg.content}</p>

              {msg.widgets?.map((widget, i) => (
                <WidgetRenderer
                  key={i}
                  widget={widget}
                  onResponse={(result) => handleWidgetResponse(msg.id, widget, result)}
                  disabled={msg.widgetAnswered}
                />
              ))}

              {msg.role === 'assistant' && !msg.metadata?.onboarding && (
                <FeedbackBar messageId={msg.id} onFeedback={handleFeedback} />
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="rounded-xl bg-zinc-800 border border-zinc-700 px-4 py-3">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 輸入框 */}
      <div className="border-t border-zinc-700 bg-zinc-800 px-4 py-3">
        <div className="flex gap-3">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder={onboardingProgress ? t('chat.placeholderOnboard') : t('chat.placeholder')}
            disabled={loading || !!onboardingProgress}
            className="flex-1 rounded-lg border border-zinc-600 bg-zinc-700 px-4 py-2.5 text-sm text-zinc-200 outline-none focus:border-blue-500 placeholder:text-zinc-500 disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim() || !!onboardingProgress}
            className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50 transition-colors"
          >
            {t('chat.send')}
          </button>
        </div>
      </div>
    </div>
  )
}
