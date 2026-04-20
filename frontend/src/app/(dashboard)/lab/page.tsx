'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth-context'
import { getDemoContext } from '@/lib/ai-engine'
import { getPipelineRunDetail } from '@/lib/studio/api'
import { useLabStore } from '@/lib/studio/labStore'
import type { DemoContext } from '@/types'
import type { NodeSpan, PipelineRunDetail } from '@/lib/studio/types'
import CaseBrowser from '@/components/lab/CaseBrowser'
import ExperimentPanel from '@/components/lab/ExperimentPanel'
import LabCanvas from '@/components/lab/LabCanvas'
import CaseHeader from '@/components/lab/CaseHeader'

export default function LabPage() {
  const { user } = useAuth()
  const [context, setContext] = useState<DemoContext | null>(null)
  const [ctxError, setCtxError] = useState<string | null>(null)

  const selectedCase = useLabStore((s) => s.selectedCase)
  const selectedNodeId = useLabStore((s) => s.selectedNodeId)
  const setSelectedNodeId = useLabStore((s) => s.setSelectedNodeId)

  const [pipelineDetail, setPipelineDetail] = useState<PipelineRunDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)

  useEffect(() => {
    getDemoContext(user?.email || undefined)
      .then(setContext)
      .catch((err) => setCtxError(err.message))
  }, [user])

  // When a pipeline case is selected, fetch its nodes_json for canvas preview
  useEffect(() => {
    if (!selectedCase || selectedCase.source_type !== 'pipeline') {
      setPipelineDetail(null)
      return
    }
    setLoadingDetail(true)
    setDetailError(null)
    getPipelineRunDetail(selectedCase.id)
      .then((res) => setPipelineDetail(res.run))
      .catch((err) => setDetailError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoadingDetail(false))
  }, [selectedCase])

  if (ctxError) {
    return (
      <div className="flex h-full items-center justify-center bg-zinc-900">
        <div className="rounded-lg border border-red-800 bg-red-900/20 p-6 text-center">
          <p className="text-sm text-red-400">無法連接後端</p>
          <p className="mt-1 text-xs text-zinc-500">{ctxError}</p>
          <p className="mt-3 text-xs text-zinc-400">
            請確認 ait-backend 已啟動（port 8000）
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
          <span className="text-sm">載入中…</span>
        </div>
      </div>
    )
  }

  const handleNodeSelect = (span: NodeSpan | null) => {
    setSelectedNodeId(span?.id ?? null)
  }

  return (
    <div className="flex h-full flex-col bg-zinc-900">
      <CaseHeader />
      <div className="flex flex-1 overflow-hidden">
        <CaseBrowser projectId={context.project_id} />

        <main className="relative flex min-h-0 flex-1 flex-col">
          {!selectedCase ? (
            <div className="flex flex-1 items-center justify-center p-6 text-center text-sm text-zinc-500">
              ← 從左側挑一個過往案例開始實驗
            </div>
          ) : (
            <LabCanvas
              sourceType={selectedCase.source_type}
              pipelineDetail={pipelineDetail}
              loading={loadingDetail}
              error={detailError}
              selectedNodeId={selectedNodeId}
              onSelectNode={handleNodeSelect}
            />
          )}
        </main>

        <ExperimentPanel projectId={context.project_id} />
      </div>
    </div>
  )
}
