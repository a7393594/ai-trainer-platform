'use client'

import { useProject } from '@/lib/project-context'
import { useI18n } from '@/lib/i18n'
import dynamic from 'next/dynamic'

const RefereeHistory = dynamic(() => import('../referee/history/page'), { ssr: false })

export default function HistoryPage() {
  const { currentProject } = useProject()
  const { t } = useI18n()

  if (currentProject?.project_type === 'referee') {
    return <RefereeHistory />
  }

  return (
    <div className="h-full bg-zinc-900 p-6 flex items-center justify-center">
      <p className="text-sm text-zinc-500">{t('history.trainerPlaceholder')}</p>
    </div>
  )
}
