'use client'

import { useSearchParams } from 'next/navigation'
import { EmbedChatInterface, type EmbedLabels } from '@/components/chat/EmbedChatInterface'

interface PageProps {
  params: { projectId: string }
}

// Language presets for embed (keyed by URL ?lang= param)
const LANG_PRESETS: Record<string, Partial<EmbedLabels>> = {
  'zh-TW': {
    empty: '開始對話',
    emptyHint: '在下方輸入訊息',
    placeholder: '輸入訊息...',
    send: '送出',
    error: '錯誤',
  },
  'zh': {
    empty: '开始对话',
    emptyHint: '在下方输入消息',
    placeholder: '输入消息...',
    send: '发送',
    error: '错误',
  },
  'en': {
    empty: 'Start a conversation',
    emptyHint: 'Type a message below',
    placeholder: 'Type a message...',
    send: 'Send',
    error: 'Error',
  },
}

export default function EmbedChatPage({ params }: PageProps) {
  const { projectId } = params
  const sp = useSearchParams()
  const token = sp.get('token') || ''
  const externalUserId = sp.get('uid') || undefined
  const theme = (sp.get('theme') as 'dark' | 'light') || 'dark'
  const lang = sp.get('lang') || 'en'
  const sessionId = sp.get('session') || undefined

  const labels = LANG_PRESETS[lang] || LANG_PRESETS['en']

  if (!token) {
    return (
      <div className={`flex h-full items-center justify-center ${theme === 'dark' ? 'bg-zinc-900' : 'bg-white'}`}>
        <div className="rounded-lg border border-red-800 bg-red-900/20 p-6 text-center max-w-md mx-4">
          <p className="text-sm text-red-400 font-medium">Missing embed token</p>
          <p className="mt-2 text-xs text-zinc-500">
            Add <code className="text-zinc-300 bg-zinc-800 px-1 rounded">?token=et_live_...</code> to the URL.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className={`h-full ${theme === 'dark' ? 'bg-zinc-900' : 'bg-white'}`}>
      <EmbedChatInterface
        projectId={projectId}
        embedToken={token}
        externalUserId={externalUserId}
        theme={theme}
        labels={labels}
        initialSessionId={sessionId}
      />
    </div>
  )
}
