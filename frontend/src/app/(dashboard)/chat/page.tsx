'use client'

import { useEffect, useState } from 'react'
import { ChatInterface, type ChatMode } from '@/components/chat/ChatInterface'
import { SessionSidebar } from '@/components/chat/SessionSidebar'
import { PromptSuggestionButton } from '@/components/chat/PromptSuggestion'
import { getDemoContext } from '@/lib/ai-engine'
import { useAuth } from '@/lib/auth-context'
import type { DemoContext } from '@/types'

export default function ChatPage() {
  const { user } = useAuth()
  const [context, setContext] = useState<DemoContext | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string | undefined>()
  const [sessionKey, setSessionKey] = useState(0)
  const [model, setModel] = useState('claude-sonnet-4-20250514')
  const [mode, setMode] = useState<ChatMode>('freeform')

  useEffect(() => {
    getDemoContext(user?.email || undefined)
      .then(setContext)
      .catch((err) => setError(err.message))
  }, [user])

  const handleNewSession = () => {
    setSessionId(undefined)
    setMode('freeform')
    setSessionKey((k) => k + 1)
  }

  const handleSelectSession = (sid: string) => {
    setSessionId(sid)
    setMode('freeform')
    setSessionKey((k) => k + 1)
  }

  const handleModeChange = (newMode: ChatMode) => {
    setMode(newMode)
    if (newMode === 'onboarding') {
      // Start fresh onboarding session
      setSessionId(undefined)
      setSessionKey((k) => k + 1)
    }
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center bg-zinc-900">
        <div className="rounded-lg border border-red-800 bg-red-900/20 p-6 text-center">
          <p className="text-sm text-red-400">Cannot connect to AI Engine</p>
          <p className="mt-1 text-xs text-zinc-500">{error}</p>
          <p className="mt-3 text-xs text-zinc-400">
            Start backend: <code className="text-zinc-300">cd ai-engine && uvicorn app.main:app --reload</code>
          </p>
        </div>
      </div>
    )
  }

  if (!context) {
    return (
      <div className="flex h-full items-center justify-center bg-zinc-900">
        <div className="flex items-center gap-2 text-zinc-400">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
          <span className="text-sm">Connecting...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex overflow-hidden">
      {/* Session Sidebar */}
      <SessionSidebar
        projectId={context.project_id}
        currentSessionId={sessionId}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
      />

      {/* Main Area */}
      <div className="flex-1 flex flex-col min-w-0 min-h-0">
        {/* Header */}
        <header className="flex items-center justify-between border-b border-zinc-800 bg-zinc-900 px-4 py-3">
          <div>
            <h2 className="text-sm font-medium text-zinc-200">Training Chat</h2>
            <p className="text-xs text-zinc-500">{context.project_name}</p>
          </div>
          <div className="flex items-center gap-3">
            {/* Model */}
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-300 outline-none"
            >
              <option value="claude-sonnet-4-20250514">Claude Sonnet 4</option>
              <option value="claude-haiku-4-5-20251001">Claude Haiku 4.5</option>
              <option value="gemini/gemini-2.0-flash">Gemini Flash</option>
            </select>
            {/* Mode */}
            <select
              value={mode}
              onChange={(e) => handleModeChange(e.target.value as ChatMode)}
              className="rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-300 outline-none"
            >
              <option value="freeform">Free Training</option>
              <option value="onboarding">Guided Setup</option>
            </select>
            {/* Prompt Suggestion */}
            <PromptSuggestionButton projectId={context.project_id} />
          </div>
        </header>

        {/* Chat */}
        <div className="flex-1 min-h-0">
          <ChatInterface
            key={sessionKey}
            projectId={context.project_id}
            userId={context.user_id}
            sessionId={sessionId}
            model={model}
            mode={mode}
          />
        </div>
      </div>
    </div>
  )
}
