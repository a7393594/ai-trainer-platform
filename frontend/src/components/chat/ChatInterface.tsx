'use client'

/**
 * ChatInterface — 訓練對話介面
 *
 * 支援：文字對話 + 互動元件 + 回饋打分 + Onboarding 模式 + 歷史載入
 */

import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import {
  sendMessage, sendMessageStream, sendWidgetResponse, submitFeedback,
  startOnboarding, answerOnboarding, getSessionMessages,
  type StreamProgressEvent,
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
  const sessionIdRef = useRef(initialSessionId) // 即時追蹤最新 session_id
  const [onboardingProgress, setOnboardingProgress] = useState<{ current: number; total: number } | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const { t } = useI18n()

  // 工具呼叫進度狀態（streaming 期間顯示）
  type ToolStat = { name: string; status: 'running' | 'done' | 'error' }
  const [progressPhase, setProgressPhase] = useState<string | null>(null)
  const [progressMessage, setProgressMessage] = useState<string>('')
  const [toolStats, setToolStats] = useState<ToolStat[]>([])

  // Widget bottom-sheet 狀態：自動綁定最新未回答的 widgets
  const [widgetSheetOpen, setWidgetSheetOpen] = useState(true)
  const activeWidgetMsg = useMemo(
    () => [...messages].reverse().find((m) => m.widgets && m.widgets.length > 0 && !m.widgetAnswered),
    [messages],
  )
  // 有新 widgets 出現時自動展開 sheet
  useEffect(() => {
    if (activeWidgetMsg) setWidgetSheetOpen(true)
  }, [activeWidgetMsg?.id])

  // 同步 ref 到最新 state
  const updateSessionId = useCallback((sid: string) => {
    sessionIdRef.current = sid
    setSessionId(sid)
  }, [])

  // 同步外部 sessionId prop 到 ref
  useEffect(() => {
    if (initialSessionId) {
      sessionIdRef.current = initialSessionId
      setSessionId(initialSessionId)
    }
  }, [initialSessionId])

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
      updateSessionId(sid)
    } catch (err) {
      console.error('Failed to load session history:', err)
    }
  }

  const handleStartOnboarding = async () => {
    if (!userId) return
    setLoading(true)
    try {
      const response = await startOnboarding(projectId, userId, 'poker')
      updateSessionId(response.session_id)
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
    setProgressPhase(null)
    setProgressMessage('')
    setToolStats([])

    // 先加一個空的 assistant message 用於 streaming 填充
    setMessages((prev) => [...prev, { id: streamingId, role: 'assistant', content: '' }])

    try {
      await sendMessageStream(
        {
          project_id: projectId,
          session_id: sessionIdRef.current, // 用 ref 確保最新值
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
        // onDone: 更新 message_id + session_id，帶上 widgets（從 stream 尾端來的）
        (sid, messageId, widgets) => {
          if (sid) updateSessionId(sid)
          setMessages((prev) =>
            prev.map((m) =>
              m.id === streamingId
                ? {
                    ...m,
                    id: messageId,
                    widgets: widgets && (widgets as WidgetDefinition[]).length > 0
                      ? (widgets as WidgetDefinition[])
                      : m.widgets,
                  }
                : m
            )
          )
          // Progress 狀態清掉
          setProgressPhase(null)
          setProgressMessage('')
          setToolStats([])
        },
        // onError
        (error) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === streamingId ? { ...m, content: `Error: ${error}` } : m
            )
          )
        },
        // onProgress: 即時 DAG 執行進度
        (ev: StreamProgressEvent) => {
          setProgressPhase(ev.status)
          if (ev.message) setProgressMessage(ev.message)
          if (ev.status === 'tool_plan' && ev.tools) {
            setToolStats(ev.tools.map((t) => ({ name: t.name, status: 'running' })))
          } else if (ev.status === 'tool_start' && ev.tool_name) {
            setToolStats((prev) => {
              // 若 plan 沒先送（避免 race），補一個
              if (!prev.some((t) => t.name === ev.tool_name)) {
                return [...prev, { name: ev.tool_name!, status: 'running' }]
              }
              return prev
            })
          } else if (ev.status === 'tool_done' && ev.tool_name) {
            setToolStats((prev) =>
              prev.map((t) =>
                t.name === ev.tool_name ? { ...t, status: ev.ok ? 'done' : 'error' } : t
              )
            )
          }
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
      setProgressPhase(null)
      setProgressMessage('')
      setToolStats([])
    }
  }

  // 處理 AI 回覆
  const handleResponse = (response: ChatResponse) => {
    if (response.session_id) updateSessionId(response.session_id)

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

              {/* widgets 不再在這裡 inline 顯示 — 改由下方 WidgetSheet 統一處理 */}
              {msg.widgets && msg.widgets.length > 0 && (
                <div className="mt-2 text-[10px] text-zinc-500 italic">
                  ↓ 回覆下方有 {msg.widgets.length} 個選項可回答
                </div>
              )}

              {msg.role === 'assistant' && !msg.metadata?.onboarding && (
                <FeedbackBar messageId={msg.id} onFeedback={handleFeedback} />
              )}
            </div>
          </div>
        ))}

        {/* Tool-call progress chip — 在 streaming 期間若有工具進度就顯示 */}
        {loading && (progressPhase || toolStats.length > 0) && (
          <div className="flex justify-start">
            <div className="rounded-xl bg-indigo-950/40 border border-indigo-700/40 px-3 py-2 max-w-[85%] space-y-1">
              {progressMessage && (
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-pulse" />
                  <span className="text-xs text-indigo-200">{progressMessage}</span>
                </div>
              )}
              {toolStats.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {toolStats.map((ts, i) => (
                    <span
                      key={`${ts.name}-${i}`}
                      className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                        ts.status === 'done'
                          ? 'bg-emerald-900/40 border-emerald-700/50 text-emerald-300'
                          : ts.status === 'error'
                          ? 'bg-red-900/40 border-red-700/50 text-red-300'
                          : 'bg-zinc-800/60 border-zinc-600 text-zinc-300 animate-pulse'
                      }`}
                    >
                      {ts.status === 'done' ? '✓' : ts.status === 'error' ? '✗' : '⋯'} {ts.name}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {loading && !progressPhase && toolStats.length === 0 && (
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

      {/* Widget bottom-sheet — 只在有未回答 widget 時出現，由下往上滑出 */}
      {activeWidgetMsg && activeWidgetMsg.widgets && (
        <div className="border-t border-zinc-700 bg-zinc-850">
          <button
            onClick={() => setWidgetSheetOpen((v) => !v)}
            className="w-full flex items-center justify-between px-4 py-2 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50 transition-colors"
          >
            <span className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 bg-amber-400 rounded-full animate-pulse" />
              待回答的選項（{activeWidgetMsg.widgets.length}）
            </span>
            <span className="text-zinc-500">{widgetSheetOpen ? '▼ 收起' : '▲ 展開'}</span>
          </button>
          {widgetSheetOpen && (
            <div
              className="px-4 pb-3 pt-1 bg-zinc-900/60 border-t border-zinc-800 max-h-[40vh] overflow-y-auto space-y-2 animate-in slide-in-from-bottom duration-200"
              style={{ animation: 'slideUp 200ms ease-out' }}
            >
              {activeWidgetMsg.widgets.map((widget, i) => (
                <WidgetRenderer
                  key={i}
                  widget={widget}
                  onResponse={(result) => handleWidgetResponse(activeWidgetMsg.id, widget, result)}
                  disabled={activeWidgetMsg.widgetAnswered}
                />
              ))}
            </div>
          )}
        </div>
      )}

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
