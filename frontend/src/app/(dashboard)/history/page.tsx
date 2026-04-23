'use client'

import { useEffect, useState, useCallback } from 'react'
import { useProject } from '@/lib/project-context'
import {
  listSessions,
  getSessionMessages,
  submitFeedback,
  listPromptVersions,
  generateSuggestions,
  listSuggestions,
  applySuggestion,
  rejectSuggestion,
} from '@/lib/ai-engine'
import { FeedbackBar } from '@/components/chat/FeedbackBar'
import type { Rating } from '@/types'
import dynamic from 'next/dynamic'

const RefereeHistory = dynamic(() => import('../referee/history/page'), { ssr: false })

interface Session {
  id: string
  started_at: string
  ended_at?: string
  session_type?: string
  user_id?: string
  preview?: string
  message_count?: number
}

interface Message {
  id: string
  role: string
  content: string
  created_at: string
  metadata?: Record<string, unknown>
}

interface PromptVersion {
  id: string
  version: number
  is_active: boolean
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

const PAGE_SIZE = 50

export default function HistoryPage() {
  const { currentProject } = useProject()

  if (currentProject?.project_type === 'referee') {
    return <RefereeHistory />
  }

  return <TrainerHistory projectId={currentProject?.project_id} />
}

function TrainerHistory({ projectId }: { projectId?: string }) {
  const [sessions, setSessions] = useState<Session[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [userFilter, setUserFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [searchText, setSearchText] = useState('')
  const [page, setPage] = useState(0)
  const [hasMore, setHasMore] = useState(false)

  // Training state
  const [activeVersion, setActiveVersion] = useState<PromptVersion | null>(null)
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [applying, setApplying] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  // Feedback state: Map<messageId, rating> - tracks locally rated messages this session
  const [ratings, setRatings] = useState<Map<string, Rating>>(new Map())
  const [reRating, setReRating] = useState<Set<string>>(new Set())

  const loadSessionsList = useCallback(async (targetPage = 0) => {
    if (!projectId) return
    setLoading(true)
    setError(null)
    try {
      const res = await listSessions(projectId, {
        userId: userFilter || undefined,
        dateFrom: dateFrom || undefined,
        dateTo: dateTo ? `${dateTo}T23:59:59` : undefined,
        search: searchText || undefined,
        limit: PAGE_SIZE,
        offset: targetPage * PAGE_SIZE,
      })
      setSessions(res.sessions || [])
      setHasMore((res.sessions || []).length === PAGE_SIZE)
      setPage(targetPage)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Load failed')
    }
    setLoading(false)
  }, [projectId, userFilter, dateFrom, dateTo, searchText])

  const loadTrainingState = useCallback(async () => {
    if (!projectId) return
    try {
      const [versionsRes, sugRes] = await Promise.all([
        listPromptVersions(projectId),
        listSuggestions(projectId),
      ])
      const active = (versionsRes.versions || []).find((v: PromptVersion) => v.is_active) || null
      setActiveVersion(active)
      setSuggestions(sugRes.suggestions || [])
    } catch {
      // non-critical
    }
  }, [projectId])

  useEffect(() => {
    loadSessionsList(0)
    loadTrainingState()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  useEffect(() => {
    if (!selectedId || !projectId) return
    getSessionMessages(projectId, selectedId)
      .then((r) => setMessages(r.messages || []))
      .catch(() => setMessages([]))
  }, [selectedId, projectId])

  const handleApplyFilters = () => loadSessionsList(0)

  const handleClearFilters = () => {
    setUserFilter('')
    setDateFrom('')
    setDateTo('')
    setSearchText('')
    setTimeout(() => loadSessionsList(0), 0)
  }

  const handleFeedback = async (messageId: string, rating: Rating, correction?: string) => {
    try {
      await submitFeedback({ message_id: messageId, rating, correction_text: correction })
      setRatings(prev => new Map(prev).set(messageId, rating))
      setReRating(prev => { const next = new Set(prev); next.delete(messageId); return next })
      // Refresh suggestion count
      loadTrainingState()
    } catch (e) {
      setError(e instanceof Error ? e.message : '送出評分失敗')
    }
  }

  const handleGenerateSuggestions = async () => {
    if (!projectId) return
    setGenerating(true)
    setNotice(null)
    try {
      await generateSuggestions(projectId)
      await loadTrainingState()
      setShowSuggestions(true)
      setNotice('已產生建議，請審核')
    } catch (e) {
      setNotice(e instanceof Error ? e.message : '建議產生失敗（可能負評不足 3 筆）')
    }
    setGenerating(false)
    setTimeout(() => setNotice(null), 4000)
  }

  const handleApply = async (suggestionId: string) => {
    if (!projectId) return
    const confirmed = confirm(
      `將建立新版本並立即啟用，覆蓋目前 v${activeVersion?.version || '?'}。確定？`
    )
    if (!confirmed) return
    setApplying(suggestionId)
    try {
      await applySuggestion(suggestionId, projectId)
      await loadTrainingState()
      setNotice('已套用並啟用新版本')
    } catch (e) {
      setNotice(e instanceof Error ? e.message : '套用失敗')
    }
    setApplying(null)
    setTimeout(() => setNotice(null), 4000)
  }

  const handleReject = async (suggestionId: string) => {
    try {
      await rejectSuggestion(suggestionId)
      await loadTrainingState()
    } catch { /* ignore */ }
  }

  if (!projectId) {
    return (
      <div className="h-full bg-zinc-900 p-6 flex items-center justify-center">
        <p className="text-sm text-zinc-500">尚未選擇專案</p>
      </div>
    )
  }

  const borderColor: Record<string, string> = {
    add: 'border-green-500',
    remove: 'border-red-500',
    modify: 'border-yellow-500',
  }

  const ratingLabel: Record<Rating, string> = {
    correct: '正確',
    partial: '部分',
    wrong: '錯誤',
  }
  const ratingColor: Record<Rating, string> = {
    correct: 'text-green-400',
    partial: 'text-yellow-400',
    wrong: 'text-red-400',
  }

  return (
    <div className="h-full flex flex-col bg-zinc-900">
      {/* ── Training status bar ─────────────────────────── */}
      <div className="border-b border-zinc-800 bg-zinc-900/80 px-4 py-2.5 flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-zinc-500 uppercase">當前啟用</span>
          {activeVersion ? (
            <span className="rounded bg-green-500/10 border border-green-500/30 px-2 py-0.5 text-xs text-green-400 font-mono">
              v{activeVersion.version}
            </span>
          ) : (
            <span className="text-xs text-zinc-500">—</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-zinc-500 uppercase">待處理建議</span>
          <span className={`text-xs font-semibold ${suggestions.length > 0 ? 'text-yellow-400' : 'text-zinc-500'}`}>
            {suggestions.length} 筆
          </span>
        </div>
        <div className="flex-1" />
        <button
          onClick={handleGenerateSuggestions}
          disabled={generating}
          className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50"
          title="從累積的負評產生改進建議（需至少 3 筆）"
        >
          {generating ? '分析中...' : '⚡ 產生改進建議'}
        </button>
        {suggestions.length > 0 && (
          <button
            onClick={() => setShowSuggestions(s => !s)}
            className="rounded border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
          >
            {showSuggestions ? '收起審核' : '展開審核'}
          </button>
        )}
        {notice && (
          <span className="text-xs text-zinc-300 bg-zinc-800 rounded px-2 py-1">{notice}</span>
        )}
      </div>

      {/* ── Suggestion review drawer ─────────────────────── */}
      {showSuggestions && suggestions.length > 0 && (
        <div className="border-b border-zinc-800 bg-zinc-950/50 max-h-[40vh] overflow-y-auto p-3 space-y-3">
          {suggestions.map((s) => (
            <div key={s.id} className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-3">
              <p className="text-xs text-zinc-400 mb-2">基於 {s.based_on_feedback_count} 筆負評</p>
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
                  disabled={applying === s.id}
                  className="flex-1 rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50"
                  title="建立新版本並立即啟用"
                >
                  {applying === s.id ? '套用中...' : '套用並啟用'}
                </button>
                <button
                  onClick={() => handleReject(s.id)}
                  className="flex-1 rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700"
                >
                  忽略
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Filter bar ──────────────────────────────────── */}
      <div className="border-b border-zinc-800 p-3">
        <div className="flex items-center gap-2 flex-wrap">
          <input
            type="text"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleApplyFilters() }}
            placeholder="搜尋訊息文字..."
            className="flex-1 min-w-[200px] rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-200 outline-none focus:border-blue-500"
          />
          <input
            type="text"
            value={userFilter}
            onChange={(e) => setUserFilter(e.target.value)}
            placeholder="用戶 ID..."
            className="w-40 rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-200 outline-none focus:border-blue-500"
          />
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-xs text-zinc-200 outline-none focus:border-blue-500"
          />
          <span className="text-xs text-zinc-500">→</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-xs text-zinc-200 outline-none focus:border-blue-500"
          />
          <button
            onClick={handleApplyFilters}
            className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500"
          >
            套用
          </button>
          <button
            onClick={handleClearFilters}
            className="rounded border border-zinc-700 px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200"
          >
            清除
          </button>
        </div>
      </div>

      {/* ── Main panels ─────────────────────────────────── */}
      <div className="flex-1 flex overflow-hidden">
        {/* Session list */}
        <div className="w-80 border-r border-zinc-800 overflow-y-auto">
          {loading && (
            <div className="flex justify-center py-8">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
            </div>
          )}
          {error && <p className="text-xs text-red-400 p-3">{error}</p>}
          {!loading && sessions.length === 0 && (
            <p className="text-xs text-zinc-500 text-center py-8">沒有符合的會話</p>
          )}
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => setSelectedId(s.id)}
              className={`w-full text-left px-3 py-2 border-b border-zinc-800 hover:bg-zinc-800/50 ${
                selectedId === s.id ? 'bg-zinc-800' : ''
              }`}
            >
              <p className="text-xs text-zinc-300 truncate">{s.preview || '(空會話)'}</p>
              <div className="flex items-center justify-between mt-1">
                <span className="text-[10px] text-zinc-500">{s.message_count || 0} 則訊息</span>
                <span className="text-[10px] text-zinc-500">
                  {new Date(s.started_at).toLocaleDateString('zh-TW')}
                </span>
              </div>
              {s.user_id && (
                <p className="text-[10px] text-zinc-600 mt-0.5 truncate font-mono">
                  {s.user_id.slice(0, 8)}...
                </p>
              )}
            </button>
          ))}

          {/* Pagination */}
          {(hasMore || page > 0) && (
            <div className="flex gap-2 p-3">
              <button
                onClick={() => loadSessionsList(Math.max(0, page - 1))}
                disabled={page === 0 || loading}
                className="flex-1 rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 disabled:opacity-50"
              >
                上一頁
              </button>
              <span className="text-xs text-zinc-500 px-2 py-1">第 {page + 1} 頁</span>
              <button
                onClick={() => loadSessionsList(page + 1)}
                disabled={!hasMore || loading}
                className="flex-1 rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 disabled:opacity-50"
              >
                下一頁
              </button>
            </div>
          )}
        </div>

        {/* Message detail */}
        <div className="flex-1 overflow-y-auto p-4">
          {!selectedId ? (
            <div className="flex items-center justify-center h-full">
              <p className="text-sm text-zinc-500">選擇左側會話查看內容</p>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-3">
              {messages.map((m) => {
                const isAssistant = m.role === 'assistant'
                const existingRating = ratings.get(m.id)
                const showBar = isAssistant && (!existingRating || reRating.has(m.id))

                return (
                  <div
                    key={m.id}
                    className={`rounded-lg p-3 ${
                      m.role === 'user' ? 'bg-blue-500/10 border border-blue-500/20' : 'bg-zinc-800/50 border border-zinc-700'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] uppercase font-semibold text-zinc-400">{m.role}</span>
                      <span className="text-[10px] text-zinc-500">
                        {new Date(m.created_at).toLocaleString('zh-TW')}
                      </span>
                    </div>
                    <pre className="whitespace-pre-wrap text-xs text-zinc-200 font-sans">{m.content}</pre>

                    {/* Inline feedback for assistant messages */}
                    {isAssistant && existingRating && !reRating.has(m.id) && (
                      <div className="mt-2 flex items-center gap-2 text-[11px]">
                        <span className="text-zinc-500">已評分：</span>
                        <span className={ratingColor[existingRating]}>{ratingLabel[existingRating]}</span>
                        <span className="text-zinc-700">·</span>
                        <button
                          onClick={() => setReRating(prev => new Set(prev).add(m.id))}
                          className="text-blue-400 hover:underline"
                        >
                          重新評分
                        </button>
                      </div>
                    )}
                    {showBar && (
                      <FeedbackBar messageId={m.id} onFeedback={handleFeedback} />
                    )}
                  </div>
                )
              })}
              {messages.length === 0 && (
                <p className="text-xs text-zinc-500 text-center py-8">載入中...</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
