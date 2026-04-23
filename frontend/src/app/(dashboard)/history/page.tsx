'use client'

import { useEffect, useState, useCallback } from 'react'
import { useProject } from '@/lib/project-context'
import { listSessions, getSessionMessages } from '@/lib/ai-engine'
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

  useEffect(() => {
    loadSessionsList(0)
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

  if (!projectId) {
    return (
      <div className="h-full bg-zinc-900 p-6 flex items-center justify-center">
        <p className="text-sm text-zinc-500">尚未選擇專案</p>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-zinc-900">
      {/* Filter bar */}
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
              {messages.map((m) => (
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
                </div>
              ))}
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
