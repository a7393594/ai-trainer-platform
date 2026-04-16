'use client'

import { useProject } from '@/lib/project-context'
import dynamic from 'next/dynamic'

const RefereeHistory = dynamic(() => import('../referee/history/page'), { ssr: false })

export default function HistoryPage() {
  const { currentProject } = useProject()

  if (currentProject?.project_type === 'referee') {
    return <RefereeHistory />
  }

  // Trainer: show session history (placeholder — trainer sessions are on /chat sidebar)
  return (
    <div className="h-full bg-zinc-900 p-6 flex items-center justify-center">
      <p className="text-sm text-zinc-500">Training session history is available in the Chat sidebar.</p>
    </div>
  )
}
